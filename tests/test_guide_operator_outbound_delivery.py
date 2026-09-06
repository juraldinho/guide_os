"""GO8F2A: authenticated single-event Guide OS → Guide Operator delivery."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from database.db import get_connection, init_db, run_write_with_retry
from database.queries import get_guide_operator_outbox_by_event_id, get_guide_os_id, register_user
from services.guide_operator_outbound_delivery import (
    DELIVERABLE_EVENT_TYPES,
    ERROR_AUTHENTICATION,
    ERROR_CONTRACT,
    ERROR_IDENTIFIER_MISMATCH,
    ERROR_TIMEOUT,
    ERROR_UNAVAILABLE,
    ERROR_VALIDATION,
    EVENT_ASSIGNMENT_DECISION,
    EVENT_CANCELLATION_ACK,
    EVENT_CONNECTION_DECIDED,
    EVENT_CRITICAL_VERSION_DECIDED,
    EVENT_VERSION_ACKNOWLEDGED,
    EVENT_VERSION_APPLIED_ACK,
    EVENT_VERSION_RECEIVED_ACK,
    SignedHttpResult,
    deliver_one,
    delivery_path,
    delivery_scope,
    dumps_event_envelope,
    serialize_event_envelope,
)
from services.guide_operator_outbound_settings import (
    GuideOperatorOutboundConfigurationError,
    GuideOperatorOutboundSettings,
)
from services.guide_operator_service_auth_settings import (
    GuideOperatorServiceAuthSettings,
    reset_guide_operator_service_auth_for_tests,
)
from services.guide_operator_service_jwt import (
    ALGORITHM,
    MAX_TTL_SECONDS,
    OUTBOUND_AUDIENCE,
    OUTBOUND_ISSUER,
    OUTBOUND_TOKEN_TYPE,
    SCOPE_ASSIGNMENTS_DECIDE,
    SCOPE_CONNECTIONS_DECIDE,
    SCOPE_VERSIONS_DECIDE,
)

FIXED_NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
INBOUND_KID = "guide-operator-test-key"
OUTBOUND_KID = "guide-os-test-key-01"
BASE_URL = "https://operator.test"


class FrozenClock:
    def __init__(self, now: datetime = FIXED_NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _pem_pair() -> tuple[str, str]:
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return private_pem, public_pem


@pytest.fixture
def keys() -> tuple[str, str]:
    return _pem_pair()


@pytest.fixture
def auth_settings(keys: tuple[str, str]) -> GuideOperatorServiceAuthSettings:
    inbound_private, inbound_public = _pem_pair()
    del inbound_private
    return GuideOperatorServiceAuthSettings.enabled_with(
        app_env="test",
        public_keys={INBOUND_KID: inbound_public},
        signing_kid=OUTBOUND_KID,
        signing_private_key_pem=keys[0],
    )


@pytest.fixture
def outbound_settings(auth_settings) -> GuideOperatorOutboundSettings:
    assert auth_settings.outbound is not None
    return GuideOperatorOutboundSettings.enabled_with(
        app_env="test",
        base_url=BASE_URL,
        outbound_jwt=auth_settings.outbound,
    )


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture(autouse=True)
def _reset(auth_settings) -> Iterator[None]:
    reset_guide_operator_service_auth_for_tests()
    init_db()
    register_user(9001)
    # Bind a known guide_os_id for deterministic JWT subject checks where needed.
    yield
    reset_guide_operator_service_auth_for_tests()


def _seed_guide() -> str:
    guide_os_id = get_guide_os_id(9001)
    assert guide_os_id is not None
    return guide_os_id


def _insert_outbox(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    guide_os_id: str,
    payload: dict[str, Any],
    event_id: str | None = None,
    created_at: str = "2026-09-05T10:00:00+00:00",
) -> str:
    eid = event_id or str(uuid4())

    def operation(conn):
        conn.execute(
            """
            INSERT INTO guide_operator_outbox (
                event_id, event_type, aggregate_type, aggregate_id,
                guide_os_id, payload_json, created_at, delivered_at, attempt_count,
                next_attempt_at, last_error_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL, NULL)
            """,
            (
                eid,
                event_type,
                aggregate_type,
                aggregate_id,
                guide_os_id,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                created_at,
            ),
        )

    run_write_with_retry(operation)
    return eid


class FakeHttp:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[SignedHttpResult] = []

    def queue(self, result: SignedHttpResult) -> None:
        self.responses.append(result)

    def post_signed(
        self, *, url: str, authorization: str, body: bytes
    ) -> SignedHttpResult:
        self.calls.append(
            {"url": url, "authorization": authorization, "body": body}
        )
        if not self.responses:
            return SignedHttpResult(status_code=200, data=None, transport_error=None)
        return self.responses.pop(0)


def _ack(event_id: str, event_type: str, *, replayed: bool = False) -> SignedHttpResult:
    return SignedHttpResult(
        status_code=200,
        data={
            "status": "replayed" if replayed else "applied",
            "eventId": event_id,
            "eventType": event_type,
            "replayed": replayed,
        },
        transport_error=None,
    )


# --- mappings / scopes ---


@pytest.mark.parametrize(
    ("event_type", "scope"),
    [
        (EVENT_CONNECTION_DECIDED, SCOPE_CONNECTIONS_DECIDE),
        (EVENT_ASSIGNMENT_DECISION, SCOPE_ASSIGNMENTS_DECIDE),
        (EVENT_CANCELLATION_ACK, SCOPE_ASSIGNMENTS_DECIDE),
        (EVENT_VERSION_APPLIED_ACK, SCOPE_VERSIONS_DECIDE),
        (EVENT_VERSION_RECEIVED_ACK, SCOPE_VERSIONS_DECIDE),
        (EVENT_CRITICAL_VERSION_DECIDED, SCOPE_VERSIONS_DECIDE),
        (EVENT_VERSION_ACKNOWLEDGED, SCOPE_VERSIONS_DECIDE),
    ],
)
def test_delivery_scope_mapping(event_type: str, scope: str) -> None:
    assert delivery_scope(event_type) == scope


def test_all_seven_events_have_paths() -> None:
    assert len(DELIVERABLE_EVENT_TYPES) == 7
    for event_type in DELIVERABLE_EVENT_TYPES:
        field = "connection_id" if event_type == EVENT_CONNECTION_DECIDED else "assignment_id"
        path = delivery_path(
            event_type,
            {field: "agg-1"},
            aggregate_id="agg-1",
        )
        assert path.startswith("/integration/v1/")


# --- settings ---


def test_outbound_defaults_disabled() -> None:
    settings = GuideOperatorOutboundSettings.from_env({})
    assert settings.enabled is False


def test_outbound_requires_https_outside_local(auth_settings) -> None:
    assert auth_settings.outbound is not None
    with pytest.raises(GuideOperatorOutboundConfigurationError):
        GuideOperatorOutboundSettings.enabled_with(
            app_env="production",
            base_url="http://operator.example",
            outbound_jwt=auth_settings.outbound,
        )


def test_disabled_configuration_does_not_claim(outbound_settings, clock) -> None:
    guide_os_id = _seed_guide()
    connection_id = str(uuid4())
    event_id = _insert_outbox(
        event_type=EVENT_CONNECTION_DECIDED,
        aggregate_type="guide_connection",
        aggregate_id=connection_id,
        guide_os_id=guide_os_id,
        payload={
            "connection_id": connection_id,
            "guide_os_id": guide_os_id,
            "company_id": str(uuid4()),
            "company_name": "Co",
            "decision": "confirm",
            "decided_at": "2026-09-05T10:00:00+00:00",
        },
    )
    result = deliver_one(
        settings=GuideOperatorOutboundSettings.disabled("test"),
        clock=clock,
        http_client=FakeHttp(),
    )
    assert result is None
    row = get_guide_operator_outbox_by_event_id(event_id)
    assert row is not None
    assert row["delivered_at"] is None
    assert int(row["attempt_count"]) == 0


# --- envelope ---


def test_envelope_serialization_is_canonical(outbound_settings, clock, keys) -> None:
    guide_os_id = _seed_guide()
    connection_id = str(uuid4())
    payload = {
        "company_name": "Co",
        "connection_id": connection_id,
        "decision": "confirm",
        "decided_at": "2026-09-05T10:00:00+00:00",
        "company_id": str(uuid4()),
        "guide_os_id": guide_os_id,
    }
    event_id = _insert_outbox(
        event_type=EVENT_CONNECTION_DECIDED,
        aggregate_type="guide_connection",
        aggregate_id=connection_id,
        guide_os_id=guide_os_id,
        payload=payload,
    )
    row = get_guide_operator_outbox_by_event_id(event_id)
    assert row is not None
    original_payload_json = row["payload_json"]
    envelope = serialize_event_envelope(row)
    wire = dumps_event_envelope(row)
    assert set(envelope) == {"event_id", "event_type", "occurred_at", "payload"}
    assert wire == json.dumps(
        envelope, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    assert get_guide_operator_outbox_by_event_id(event_id)["payload_json"] == original_payload_json


# --- successful delivery for all seven ---


def _payload_for(event_type: str, guide_os_id: str, aggregate_id: str) -> dict[str, Any]:
    if event_type == EVENT_CONNECTION_DECIDED:
        return {
            "connection_id": aggregate_id,
            "guide_os_id": guide_os_id,
            "company_id": str(uuid4()),
            "company_name": "Operator Co",
            "decision": "confirm",
            "decided_at": "2026-09-05T10:00:00+00:00",
        }
    if event_type == EVENT_ASSIGNMENT_DECISION:
        return {
            "assignment_id": aggregate_id,
            "guide_os_id": guide_os_id,
            "decision": "accept",
            "version_number": 1,
            "decided_at": "2026-09-05T10:00:00+00:00",
            "projection_tour_id": 42,
        }
    if event_type == EVENT_CANCELLATION_ACK:
        return {
            "assignment_id": aggregate_id,
            "guide_os_id": guide_os_id,
            "version_number": 1,
            "cancelled_at": "2026-09-05T10:00:00+00:00",
            "source_event_id": str(uuid4()),
        }
    if event_type == EVENT_VERSION_APPLIED_ACK:
        return {
            "assignment_id": aggregate_id,
            "guide_os_id": guide_os_id,
            "version_number": 2,
            "previous_active_version_number": 1,
            "severity": "ordinary",
            "source_event_id": str(uuid4()),
            "published_at": "2026-09-05T09:00:00+00:00",
            "applied_at": "2026-09-05T10:00:00+00:00",
        }
    if event_type == EVENT_VERSION_RECEIVED_ACK:
        return {
            "assignment_id": aggregate_id,
            "guide_os_id": guide_os_id,
            "version_number": 2,
            "previous_active_version_number": 1,
            "severity": "critical",
            "source_event_id": str(uuid4()),
            "published_at": "2026-09-05T09:00:00+00:00",
            "received_at": "2026-09-05T10:00:00+00:00",
        }
    if event_type == EVENT_CRITICAL_VERSION_DECIDED:
        return {
            "assignment_id": aggregate_id,
            "guide_os_id": guide_os_id,
            "decision": "confirm_critical",
            "version_number": 2,
            "decided_at": "2026-09-05T10:00:00+00:00",
            "projection_tour_id": 7,
            "active_version_number": 2,
        }
    if event_type == EVENT_VERSION_ACKNOWLEDGED:
        return {
            "assignment_id": aggregate_id,
            "guide_os_id": guide_os_id,
            "version_number": 2,
            "acknowledged_at": "2026-09-05T10:00:00+00:00",
            "decision_event_id": str(uuid4()),
        }
    raise AssertionError(event_type)


@pytest.mark.parametrize("event_type", sorted(DELIVERABLE_EVENT_TYPES))
def test_deliver_one_success_all_mappings(
    event_type: str, outbound_settings, clock, keys
) -> None:
    guide_os_id = _seed_guide()
    aggregate_id = str(uuid4())
    aggregate_type = (
        "guide_connection"
        if event_type == EVENT_CONNECTION_DECIDED
        else "guide_assignment"
    )
    payload = _payload_for(event_type, guide_os_id, aggregate_id)
    event_id = _insert_outbox(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        guide_os_id=guide_os_id,
        payload=payload,
    )
    http = FakeHttp()
    http.queue(_ack(event_id, event_type))
    result = deliver_one(
        settings=outbound_settings,
        clock=clock,
        http_client=http,
        event_id=event_id,
        random_bytes=lambda n: b"\x01" * n,
    )
    assert result is not None
    assert result.outcome == "delivered"
    assert result.event_type == event_type
    assert result.replayed is False
    row = get_guide_operator_outbox_by_event_id(event_id)
    assert row is not None
    assert row["delivered_at"] is not None
    assert row["last_error_code"] is None

    assert len(http.calls) == 1
    call = http.calls[0]
    expected_path = delivery_path(
        event_type,
        payload,
        aggregate_id=aggregate_id,
    )
    assert call["url"] == f"{BASE_URL}{expected_path}"
    assert call["authorization"].startswith("Bearer ")
    token = call["authorization"][7:]
    claims = jwt.decode(
        token,
        serialization.load_pem_public_key(keys[1].encode("ascii")),
        algorithms=[ALGORITHM],
        audience=OUTBOUND_AUDIENCE,
        options={
            "require": ["exp", "iat", "nbf", "sub", "iss", "aud", "scope", "jti"],
            "verify_exp": False,
            "verify_nbf": False,
        },
    )
    assert claims["iss"] == OUTBOUND_ISSUER
    assert claims["aud"] == OUTBOUND_AUDIENCE
    assert claims["sub"] == guide_os_id
    assert claims["scope"] == delivery_scope(event_type)
    assert claims["iat"] == int(FIXED_NOW.timestamp())
    assert claims["exp"] - claims["iat"] == MAX_TTL_SECONDS
    header = jwt.get_unverified_header(token)
    assert header["typ"] == OUTBOUND_TOKEN_TYPE
    assert header["kid"] == OUTBOUND_KID

    body = json.loads(call["body"].decode("utf-8"))
    assert body["event_id"] == event_id
    assert body["event_type"] == event_type
    assert set(body) == {"event_id", "event_type", "occurred_at", "payload"}



def test_replay_success_marks_delivered(outbound_settings, clock) -> None:
    guide_os_id = _seed_guide()
    assignment_id = str(uuid4())
    event_id = _insert_outbox(
        event_type=EVENT_ASSIGNMENT_DECISION,
        aggregate_type="guide_assignment",
        aggregate_id=assignment_id,
        guide_os_id=guide_os_id,
        payload=_payload_for(EVENT_ASSIGNMENT_DECISION, guide_os_id, assignment_id),
    )
    http = FakeHttp()
    http.queue(_ack(event_id, EVENT_ASSIGNMENT_DECISION, replayed=True))
    result = deliver_one(
        settings=outbound_settings,
        clock=clock,
        http_client=http,
        event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "delivered"
    assert result.replayed is True


# --- failures ---


def test_retryable_unavailable(outbound_settings, clock) -> None:
    guide_os_id = _seed_guide()
    assignment_id = str(uuid4())
    event_id = _insert_outbox(
        event_type=EVENT_CANCELLATION_ACK,
        aggregate_type="guide_assignment",
        aggregate_id=assignment_id,
        guide_os_id=guide_os_id,
        payload=_payload_for(EVENT_CANCELLATION_ACK, guide_os_id, assignment_id),
    )
    http = FakeHttp()
    http.queue(
        SignedHttpResult(status_code=503, data=None, transport_error=None)
    )
    result = deliver_one(
        settings=outbound_settings,
        clock=clock,
        http_client=http,
        event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "retrying"
    assert result.error_code == ERROR_UNAVAILABLE
    row = get_guide_operator_outbox_by_event_id(event_id)
    assert row is not None
    assert row["delivered_at"] is None
    assert row["last_error_code"] == ERROR_UNAVAILABLE
    assert row["next_attempt_at"] is not None


def test_timeout_is_retryable(outbound_settings, clock) -> None:
    guide_os_id = _seed_guide()
    assignment_id = str(uuid4())
    event_id = _insert_outbox(
        event_type=EVENT_VERSION_APPLIED_ACK,
        aggregate_type="guide_assignment",
        aggregate_id=assignment_id,
        guide_os_id=guide_os_id,
        payload=_payload_for(EVENT_VERSION_APPLIED_ACK, guide_os_id, assignment_id),
    )
    http = FakeHttp()
    http.queue(
        SignedHttpResult(status_code=None, data=None, transport_error=ERROR_TIMEOUT)
    )
    result = deliver_one(
        settings=outbound_settings,
        clock=clock,
        http_client=http,
        event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "retrying"
    assert result.error_code == ERROR_TIMEOUT


def test_permanent_auth_failure(outbound_settings, clock) -> None:
    guide_os_id = _seed_guide()
    assignment_id = str(uuid4())
    event_id = _insert_outbox(
        event_type=EVENT_VERSION_RECEIVED_ACK,
        aggregate_type="guide_assignment",
        aggregate_id=assignment_id,
        guide_os_id=guide_os_id,
        payload=_payload_for(EVENT_VERSION_RECEIVED_ACK, guide_os_id, assignment_id),
    )
    http = FakeHttp()
    http.queue(
        SignedHttpResult(status_code=401, data=None, transport_error=None)
    )
    result = deliver_one(
        settings=outbound_settings,
        clock=clock,
        http_client=http,
        event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "failed"
    assert result.error_code == ERROR_AUTHENTICATION
    # Permanent failures stay inspectable and are not reclaimed.
    http2 = FakeHttp()
    http2.queue(_ack(event_id, EVENT_VERSION_RECEIVED_ACK))
    assert (
        deliver_one(
            settings=outbound_settings,
            clock=clock,
            http_client=http2,
            event_id=event_id,
        )
        is None
    )


def test_contract_failure_on_bad_ack(outbound_settings, clock) -> None:
    guide_os_id = _seed_guide()
    assignment_id = str(uuid4())
    event_id = _insert_outbox(
        event_type=EVENT_CRITICAL_VERSION_DECIDED,
        aggregate_type="guide_assignment",
        aggregate_id=assignment_id,
        guide_os_id=guide_os_id,
        payload=_payload_for(EVENT_CRITICAL_VERSION_DECIDED, guide_os_id, assignment_id),
    )
    http = FakeHttp()
    http.queue(
        SignedHttpResult(
            status_code=200,
            data={
                "status": "applied",
                "eventId": event_id,
                "eventType": EVENT_CRITICAL_VERSION_DECIDED,
                "replayed": True,
            },
            transport_error=None,
        )
    )
    result = deliver_one(
        settings=outbound_settings,
        clock=clock,
        http_client=http,
        event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "failed"
    assert result.error_code == ERROR_CONTRACT


def test_identifier_mismatch_is_permanent(outbound_settings, clock) -> None:
    guide_os_id = _seed_guide()
    assignment_id = str(uuid4())
    payload = _payload_for(EVENT_VERSION_ACKNOWLEDGED, guide_os_id, assignment_id)
    payload["assignment_id"] = str(uuid4())
    event_id = _insert_outbox(
        event_type=EVENT_VERSION_ACKNOWLEDGED,
        aggregate_type="guide_assignment",
        aggregate_id=assignment_id,
        guide_os_id=guide_os_id,
        payload=payload,
    )
    result = deliver_one(
        settings=outbound_settings,
        clock=clock,
        http_client=FakeHttp(),
        event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "failed"
    assert result.error_code == ERROR_IDENTIFIER_MISMATCH


def test_malformed_payload_is_permanent(outbound_settings, clock) -> None:
    guide_os_id = _seed_guide()
    assignment_id = str(uuid4())
    event_id = _insert_outbox(
        event_type=EVENT_ASSIGNMENT_DECISION,
        aggregate_type="guide_assignment",
        aggregate_id=assignment_id,
        guide_os_id=guide_os_id,
        payload={"assignment_id": assignment_id},
    )
    result = deliver_one(
        settings=outbound_settings,
        clock=clock,
        http_client=FakeHttp(),
        event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "failed"
    assert result.error_code == ERROR_VALIDATION


def test_unsupported_events_remain_unsent(outbound_settings, clock) -> None:
    guide_os_id = _seed_guide()
    event_id = _insert_outbox(
        event_type="assignment.withdrawn.v1",
        aggregate_type="guide_assignment",
        aggregate_id=str(uuid4()),
        guide_os_id=guide_os_id,
        payload={"assignment_id": str(uuid4()), "guide_os_id": guide_os_id},
    )
    result = deliver_one(
        settings=outbound_settings,
        clock=clock,
        http_client=FakeHttp(),
    )
    assert result is None
    row = get_guide_operator_outbox_by_event_id(event_id)
    assert row is not None
    assert row["delivered_at"] is None
    assert int(row["attempt_count"]) == 0


def test_concurrent_claim_sends_once(outbound_settings, clock) -> None:
    guide_os_id = _seed_guide()
    assignment_id = str(uuid4())
    event_id = _insert_outbox(
        event_type=EVENT_ASSIGNMENT_DECISION,
        aggregate_type="guide_assignment",
        aggregate_id=assignment_id,
        guide_os_id=guide_os_id,
        payload=_payload_for(EVENT_ASSIGNMENT_DECISION, guide_os_id, assignment_id),
    )
    results: list[Any] = []
    lock = threading.Lock()
    http_a = FakeHttp()
    http_a.queue(_ack(event_id, EVENT_ASSIGNMENT_DECISION))
    http_b = FakeHttp()
    http_b.queue(_ack(event_id, EVENT_ASSIGNMENT_DECISION))

    def worker_a():
        result = deliver_one(
            settings=outbound_settings,
            clock=clock,
            http_client=http_a,
            event_id=event_id,
        )
        with lock:
            results.append(result)

    def worker_b():
        result = deliver_one(
            settings=outbound_settings,
            clock=clock,
            http_client=http_b,
            event_id=event_id,
        )
        with lock:
            results.append(result)

    threads = [
        threading.Thread(target=worker_a),
        threading.Thread(target=worker_b),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    outcomes = [r.outcome if r is not None else None for r in results]
    assert outcomes.count("delivered") == 1
    assert outcomes.count(None) == 1
    row = get_guide_operator_outbox_by_event_id(event_id)
    assert row is not None
    assert int(row["attempt_count"]) == 1
    assert row["delivered_at"] is not None
    assert len(http_a.calls) + len(http_b.calls) == 1


def test_privacy_no_secrets_in_logs(
    outbound_settings, clock, keys, caplog
) -> None:
    guide_os_id = _seed_guide()
    assignment_id = str(uuid4())
    secret_name = "Secret Contact Person"
    payload = _payload_for(EVENT_ASSIGNMENT_DECISION, guide_os_id, assignment_id)
    # company/tour secrets must never appear even if present in unrelated fields;
    # our payload schema is fixed, so verify logs from a failed transport call.
    event_id = _insert_outbox(
        event_type=EVENT_ASSIGNMENT_DECISION,
        aggregate_type="guide_assignment",
        aggregate_id=assignment_id,
        guide_os_id=guide_os_id,
        payload=payload,
    )
    http = FakeHttp()
    http.queue(
        SignedHttpResult(
            status_code=500,
            data={"error": {"message": secret_name, "token": "eyJabc.def.ghi"}},
            transport_error=None,
        )
    )
    with caplog.at_level(logging.WARNING):
        deliver_one(
            settings=outbound_settings,
            clock=clock,
            http_client=http,
            event_id=event_id,
            random_bytes=lambda n: b"\x02" * n,
        )
    joined = " ".join(record.getMessage() for record in caplog.records)
    assert "eyJ" not in joined
    assert "BEGIN PRIVATE KEY" not in joined
    assert keys[0] not in joined
    assert secret_name not in joined
    assert "working_package" not in joined
