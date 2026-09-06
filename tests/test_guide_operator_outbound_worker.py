"""GO8F2B: bounded Guide OS → Guide Operator outbound delivery worker."""

from __future__ import annotations

import inspect
import json
import logging
import threading
from collections.abc import Iterator
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import bot as bot_module
import guide_operator_integration_api as integration_api
from database.db import init_db, run_write_with_retry
from database.queries import get_guide_operator_outbox_by_event_id, get_guide_os_id, register_user
from services.guide_operator_outbound_delivery import (
    CLAIM_LEASE,
    ERROR_AUTHENTICATION,
    ERROR_RETRY_EXHAUSTED,
    ERROR_TIMEOUT,
    ERROR_UNAVAILABLE,
    ERROR_UNSUPPORTED,
    EVENT_ASSIGNMENT_DECISION,
    EVENT_CONNECTION_DECIDED,
    MAX_DELIVERY_ATTEMPTS,
    MAX_RETRY_DELAY,
    RETRY_JITTER_FRACTION,
    SignedHttpResult,
    retry_delay,
)
from services.guide_operator_outbound_settings import GuideOperatorOutboundSettings
from services.guide_operator_outbound_worker import (
    GuideOperatorOutboundDeliveryWorker,
    GuideOperatorOutboundWorkerConfigurationError,
    GuideOperatorOutboundWorkerSettings,
    _log_result,
    install_signal_handlers,
    parse_args,
)
from services.guide_operator_outbound_worker import logger as worker_logger
from services.guide_operator_service_auth_settings import (
    GuideOperatorServiceAuthSettings,
    reset_guide_operator_service_auth_for_tests,
)

FIXED_NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
INBOUND_KID = "guide-operator-test-key"
OUTBOUND_KID = "guide-os-test-key-01"
BASE_URL = "https://operator.test"
JWT_MARKER = "eyJ"
PEM_MARKER = "BEGIN PRIVATE KEY"
SECRET_CONTACT = "Secret Contact Person"


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


@pytest.fixture(autouse=True)
def _reset(auth_settings) -> Iterator[None]:
    reset_guide_operator_service_auth_for_tests()
    init_db()
    register_user(9001)
    yield
    reset_guide_operator_service_auth_for_tests()


class FakeHttp:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[SignedHttpResult] = []
        self._on_call: Any = None

    def queue(self, result: SignedHttpResult) -> None:
        self.responses.append(result)

    def on_call(self, callback: Any) -> None:
        self._on_call = callback

    def post_signed(
        self, *, url: str, authorization: str, body: bytes
    ) -> SignedHttpResult:
        self.calls.append(
            {"url": url, "authorization": authorization, "body": body}
        )
        if self._on_call is not None:
            self._on_call()
        if not self.responses:
            return SignedHttpResult(status_code=200, data=None, transport_error=None)
        return self.responses.pop(0)


def _ack(event_id: str, event_type: str) -> SignedHttpResult:
    return SignedHttpResult(
        status_code=200,
        data={
            "status": "applied",
            "eventId": event_id,
            "eventType": event_type,
            "replayed": False,
        },
        transport_error=None,
    )


def _seed_guide() -> str:
    guide_os_id = get_guide_os_id(9001)
    assert guide_os_id is not None
    return guide_os_id


def _connection_payload(guide_os_id: str, connection_id: str) -> dict[str, Any]:
    return {
        "connection_id": connection_id,
        "guide_os_id": guide_os_id,
        "company_id": str(uuid4()),
        "company_name": "Operator Co",
        "decision": "confirm",
        "decided_at": "2026-09-05T10:00:00+00:00",
    }


def _insert_outbox(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    guide_os_id: str,
    payload: dict[str, Any],
    event_id: str | None = None,
    attempt_count: int = 0,
    next_attempt_at: str | None = None,
    last_error_code: str | None = None,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                eid,
                event_type,
                aggregate_type,
                aggregate_id,
                guide_os_id,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                created_at,
                attempt_count,
                next_attempt_at,
                last_error_code,
            ),
        )

    run_write_with_retry(operation)
    return eid


def _queue_connection() -> tuple[str, str, dict[str, Any]]:
    guide_os_id = _seed_guide()
    connection_id = str(uuid4())
    payload = _connection_payload(guide_os_id, connection_id)
    event_id = _insert_outbox(
        event_type=EVENT_CONNECTION_DECIDED,
        aggregate_type="guide_connection",
        aggregate_id=connection_id,
        guide_os_id=guide_os_id,
        payload=payload,
    )
    return event_id, guide_os_id, payload


def _make_worker(
    outbound_settings: GuideOperatorOutboundSettings,
    http: FakeHttp,
    *,
    batch_size: int = 10,
    clock: FrozenClock | None = None,
    jitter_unit: float = 0.0,
    sleep: Any = None,
    enabled: bool = True,
) -> GuideOperatorOutboundDeliveryWorker:
    if enabled:
        settings = GuideOperatorOutboundWorkerSettings.enabled_with(
            once=True,
            poll_interval_seconds=5.0,
            batch_size=batch_size,
            outbound=outbound_settings,
        )
    else:
        settings = GuideOperatorOutboundWorkerSettings.disabled()
    return GuideOperatorOutboundDeliveryWorker(
        settings=settings,
        outbound_settings=outbound_settings
        if enabled
        else GuideOperatorOutboundSettings.disabled("test"),
        http_client=http,
        clock=clock or FrozenClock(FIXED_NOW),
        jitter_unit=lambda: jitter_unit,
        sleep=sleep,
        random_bytes=lambda n: b"\x03" * n,
    )


def test_worker_defaults_disabled() -> None:
    settings = GuideOperatorOutboundWorkerSettings.from_env({})
    assert settings.enabled is False
    assert settings.batch_size == 10
    assert settings.poll_interval_seconds == 5.0


def test_worker_enabled_without_outbound_fails_closed() -> None:
    with pytest.raises(GuideOperatorOutboundWorkerConfigurationError):
        GuideOperatorOutboundWorkerSettings.from_env(
            {"GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ENABLED": "true"}
        )


def test_worker_enabled_with_incomplete_outbound_fails_closed() -> None:
    with pytest.raises(GuideOperatorOutboundWorkerConfigurationError):
        GuideOperatorOutboundWorkerSettings.from_env(
            {
                "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ENABLED": "true",
                "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_ENABLED": "true",
                "GUIDE_OS_GUIDE_OPERATOR_BASE_URL": BASE_URL,
                "GUIDE_OS_SERVICE_AUTH_ENABLED": "true",
            }
        )


def test_retry_delay_uses_capped_jitter() -> None:
    assert retry_delay(1, jitter_unit=0.0) == timedelta(seconds=15)
    assert retry_delay(1, jitter_unit=1.0) == timedelta(
        seconds=15 * (1 + RETRY_JITTER_FRACTION)
    )
    assert retry_delay(20, jitter_unit=1.0) == MAX_RETRY_DELAY


def test_parse_once_flag() -> None:
    assert parse_args(["--once"]).once is True
    assert parse_args([]).once is False


def test_bot_and_integration_api_do_not_start_worker() -> None:
    bot_source = inspect.getsource(bot_module)
    integration_source = inspect.getsource(integration_api)
    for source in (bot_source, integration_source):
        assert "GuideOperatorOutboundDeliveryWorker" not in source
        assert "guide_operator_outbound_worker" not in source
        assert "OUTBOUND_WORKER" not in source


def test_empty_queue(outbound_settings) -> None:
    http = FakeHttp()
    worker = _make_worker(outbound_settings, http)
    assert worker.run_once() == []
    assert http.calls == []


def test_successful_batch(outbound_settings) -> None:
    first_id, _, first_payload = _queue_connection()
    second_id, _, second_payload = _queue_connection()
    third_id, _, third_payload = _queue_connection()
    originals = {
        first_id: deepcopy(first_payload),
        second_id: deepcopy(second_payload),
        third_id: deepcopy(third_payload),
    }
    http = FakeHttp()
    for event_id in (first_id, second_id, third_id):
        http.queue(_ack(event_id, EVENT_CONNECTION_DECIDED))

    worker = _make_worker(outbound_settings, http, batch_size=2)
    first_cycle = worker.run_once()
    second_cycle = worker.run_once()
    assert [item.outcome for item in first_cycle] == ["delivered", "delivered"]
    assert [item.outcome for item in second_cycle] == ["delivered"]
    assert len(http.calls) == 3
    for event_id, payload in originals.items():
        row = get_guide_operator_outbox_by_event_id(event_id)
        assert row is not None
        assert row["delivered_at"] is not None
        assert json.loads(row["payload_json"]) == payload


def test_retry_scheduling_and_backoff(outbound_settings) -> None:
    event_id, _, original = _queue_connection()
    clock = FrozenClock(FIXED_NOW)
    http = FakeHttp()
    http.queue(
        SignedHttpResult(status_code=503, data=None, transport_error=None)
    )
    http.queue(
        SignedHttpResult(status_code=503, data=None, transport_error=None)
    )
    worker = _make_worker(
        outbound_settings, http, clock=clock, jitter_unit=0.0
    )
    first = worker.run_once()
    assert first[0].outcome == "retrying"
    assert first[0].error_code == ERROR_UNAVAILABLE
    row = get_guide_operator_outbox_by_event_id(event_id)
    assert row is not None
    assert row["next_attempt_at"] == (FIXED_NOW + timedelta(seconds=15)).isoformat()
    assert json.loads(row["payload_json"]) == original
    assert worker.run_once() == []
    clock.now = FIXED_NOW + timedelta(seconds=15)
    second = worker.run_once()
    assert second[0].outcome == "retrying"
    assert len(http.calls) == 2


def test_maximum_attempt_exhaustion(outbound_settings) -> None:
    guide_os_id = _seed_guide()
    connection_id = str(uuid4())
    payload = _connection_payload(guide_os_id, connection_id)
    event_id = _insert_outbox(
        event_type=EVENT_CONNECTION_DECIDED,
        aggregate_type="guide_connection",
        aggregate_id=connection_id,
        guide_os_id=guide_os_id,
        payload=payload,
        attempt_count=MAX_DELIVERY_ATTEMPTS,
        next_attempt_at=FIXED_NOW.isoformat(),
        last_error_code=ERROR_TIMEOUT,
    )
    http = FakeHttp()
    results = _make_worker(outbound_settings, http).run_once()
    assert results[0].outcome == "failed"
    assert results[0].error_code == ERROR_RETRY_EXHAUSTED
    assert http.calls == []
    row = get_guide_operator_outbox_by_event_id(event_id)
    assert row is not None
    assert row["delivered_at"] is None
    assert row["last_error_code"] == ERROR_RETRY_EXHAUSTED
    assert json.loads(row["payload_json"]) == payload
    assert int(row["attempt_count"]) == MAX_DELIVERY_ATTEMPTS + 1


def test_permanent_failure_remains_inspectable(outbound_settings) -> None:
    event_id, _, original = _queue_connection()
    http = FakeHttp()
    http.queue(
        SignedHttpResult(
            status_code=401,
            data={"error": {"message": SECRET_CONTACT}},
            transport_error=None,
        )
    )
    worker = _make_worker(outbound_settings, http)
    first = worker.run_once()
    assert first[0].error_code == ERROR_AUTHENTICATION
    assert worker.run_once() == []
    row = get_guide_operator_outbox_by_event_id(event_id)
    assert row is not None
    assert row["delivered_at"] is None
    assert row["last_error_code"] == ERROR_AUTHENTICATION
    assert json.loads(row["payload_json"]) == original


def test_expired_claim_recovery(outbound_settings) -> None:
    guide_os_id = _seed_guide()
    connection_id = str(uuid4())
    payload = _connection_payload(guide_os_id, connection_id)
    event_id = _insert_outbox(
        event_type=EVENT_CONNECTION_DECIDED,
        aggregate_type="guide_connection",
        aggregate_id=connection_id,
        guide_os_id=guide_os_id,
        payload=payload,
        attempt_count=1,
        next_attempt_at=(FIXED_NOW + CLAIM_LEASE).isoformat(),
    )
    clock = FrozenClock(FIXED_NOW)
    http = FakeHttp()
    http.queue(_ack(event_id, EVENT_CONNECTION_DECIDED))
    worker = _make_worker(outbound_settings, http, clock=clock)
    assert worker.run_once() == []
    assert http.calls == []
    clock.now = FIXED_NOW + CLAIM_LEASE
    recovered = worker.run_once()
    assert recovered[0].outcome == "delivered"
    assert recovered[0].event_id == event_id
    assert len(http.calls) == 1


def test_concurrent_workers_use_database_claims(outbound_settings) -> None:
    event_id, _, _ = _queue_connection()
    http_a = FakeHttp()
    http_a.queue(_ack(event_id, EVENT_CONNECTION_DECIDED))
    http_b = FakeHttp()
    http_b.queue(_ack(event_id, EVENT_CONNECTION_DECIDED))
    first = _make_worker(outbound_settings, http_a)
    second = _make_worker(outbound_settings, http_b)
    results: list[Any] = []
    lock = threading.Lock()

    def run(worker: GuideOperatorOutboundDeliveryWorker) -> None:
        batch = worker.run_once()
        with lock:
            results.append(batch)

    threads = [
        threading.Thread(target=run, args=(first,)),
        threading.Thread(target=run, args=(second,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    delivered = [
        item
        for batch in results
        for item in batch
        if item.outcome == "delivered"
    ]
    assert len(delivered) == 1
    assert delivered[0].event_id == event_id
    assert len(http_a.calls) + len(http_b.calls) == 1


def test_in_process_cycles_do_not_overlap(outbound_settings) -> None:
    event_id, _, _ = _queue_connection()
    http = FakeHttp()
    http.queue(_ack(event_id, EVENT_CONNECTION_DECIDED))
    worker = _make_worker(outbound_settings, http)
    batches: list[Any] = []
    lock = threading.Lock()

    def run() -> None:
        batch = worker.run_once()
        with lock:
            batches.append(batch)

    threads = [threading.Thread(target=run), threading.Thread(target=run)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    delivered = [
        item
        for batch in batches
        for item in batch
        if item.outcome == "delivered"
    ]
    assert len(delivered) == 1
    assert delivered[0].event_id == event_id
    assert len(http.calls) == 1


def test_graceful_stop_finishes_current_event(outbound_settings) -> None:
    first_id, _, _ = _queue_connection()
    second_id, _, _ = _queue_connection()
    third_id, _, _ = _queue_connection()
    ids = {first_id, second_id, third_id}
    holder: list[GuideOperatorOutboundDeliveryWorker] = []
    http = FakeHttp()
    for event_id in (first_id, second_id, third_id):
        http.queue(_ack(event_id, EVENT_CONNECTION_DECIDED))

    def stop_after_first() -> None:
        holder[0].request_stop()

    http.on_call(stop_after_first)
    worker = _make_worker(outbound_settings, http, batch_size=10)
    holder.append(worker)
    results = worker.run_once()
    assert len(results) == 1
    assert results[0].event_id in ids
    pending = 0
    for event_id in ids:
        row = get_guide_operator_outbox_by_event_id(event_id)
        assert row is not None
        if row["delivered_at"] is None:
            pending += 1
    assert pending == 2


def test_graceful_stop_exits_polling_loop(outbound_settings) -> None:
    sleeps = {"count": 0}

    def sleep(_seconds: float) -> None:
        sleeps["count"] += 1
        worker.request_stop()

    http = FakeHttp()
    worker = _make_worker(outbound_settings, http, sleep=sleep)
    worker.run_forever()
    assert sleeps["count"] == 1


def test_one_cycle_does_not_poll(outbound_settings) -> None:
    def sleep(_seconds: float) -> None:
        raise AssertionError("must not poll")

    http = FakeHttp()
    worker = _make_worker(outbound_settings, http, sleep=sleep)
    assert worker.run_once() == []


def test_disabled_configuration_does_not_claim(outbound_settings) -> None:
    event_id, _, _ = _queue_connection()
    http = FakeHttp()
    worker = _make_worker(outbound_settings, http, enabled=False)
    assert worker.run_once() == []
    assert http.calls == []
    row = get_guide_operator_outbox_by_event_id(event_id)
    assert row is not None
    assert int(row["attempt_count"]) == 0
    assert row["delivered_at"] is None


def test_unsupported_events_remain_unsent(outbound_settings) -> None:
    decided_id, guide_os_id, _ = _queue_connection()
    unsupported_id = str(uuid4())
    assignment_id = str(uuid4())
    unsupported_payload = {
        "assignment_id": assignment_id,
        "guide_os_id": guide_os_id,
        "decision": "accept",
    }
    _insert_outbox(
        event_type="assignment.offered.v1",
        aggregate_type="guide_assignment",
        aggregate_id=assignment_id,
        guide_os_id=guide_os_id,
        payload=unsupported_payload,
        event_id=unsupported_id,
    )
    http = FakeHttp()
    http.queue(_ack(decided_id, EVENT_CONNECTION_DECIDED))
    results = _make_worker(outbound_settings, http).run_once()
    assert [item.event_id for item in results] == [decided_id]
    assert len(http.calls) == 1
    row = get_guide_operator_outbox_by_event_id(unsupported_id)
    assert row is not None
    assert row["delivered_at"] is None
    assert int(row["attempt_count"]) == 0
    assert row["last_error_code"] is None
    assert json.loads(row["payload_json"]) == unsupported_payload
    assert row["last_error_code"] != ERROR_UNSUPPORTED


def test_privacy_excludes_secrets(outbound_settings, keys) -> None:
    _queue_connection()
    guide_os_id = _seed_guide()
    assignment_id = str(uuid4())
    _insert_outbox(
        event_type=EVENT_ASSIGNMENT_DECISION,
        aggregate_type="guide_assignment",
        aggregate_id=assignment_id,
        guide_os_id=guide_os_id,
        payload={
            "assignment_id": assignment_id,
            "guide_os_id": guide_os_id,
            "decision": "accept",
            "version_number": 1,
            "decided_at": "2026-09-05T10:00:00+00:00",
            "projection_tour_id": 42,
        },
    )
    http = FakeHttp()
    http.queue(
        SignedHttpResult(
            status_code=503,
            data={"error": {"message": SECRET_CONTACT, "package": "internal_comment"}},
            transport_error=None,
        )
    )
    http.queue(
        SignedHttpResult(
            status_code=503,
            data={"error": {"message": SECRET_CONTACT}},
            transport_error=None,
        )
    )
    results = _make_worker(outbound_settings, http, batch_size=2).run_once()
    assert results
    combined = str(results)
    assert SECRET_CONTACT not in combined
    assert JWT_MARKER not in combined
    assert PEM_MARKER not in combined
    assert keys[0] not in combined
    assert "internal_comment" not in combined
    assert "working_package" not in combined


def test_operational_log_contains_only_safe_fields() -> None:
    records: list[str] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _ListHandler()
    previous_disabled = worker_logger.disabled
    previous_level = worker_logger.level
    worker_logger.disabled = False
    worker_logger.setLevel(logging.INFO)
    worker_logger.addHandler(handler)
    try:
        from services.guide_operator_outbound_delivery import OutboundDeliveryResult

        _log_result(
            OutboundDeliveryResult(
                event_id="evt-1",
                event_type=EVENT_CONNECTION_DECIDED,
                outcome="retrying",
                error_code=ERROR_UNAVAILABLE,
                attempt_count=2,
            ),
            7,
        )
    finally:
        worker_logger.removeHandler(handler)
        worker_logger.disabled = previous_disabled
        worker_logger.setLevel(previous_level)
    assert records == [
        "outbound delivery event_id=evt-1 event_type=guide_connection.decided.v1 "
        "attempt=2 outcome=retrying error_code=unavailable elapsed_ms=7"
    ]
    assert SECRET_CONTACT not in records[0]
    assert JWT_MARKER not in records[0]
    assert "working_package" not in records[0]


def test_signal_handlers_bind(outbound_settings) -> None:
    http = FakeHttp()
    worker = _make_worker(outbound_settings, http, enabled=False)
    install_signal_handlers(worker)
    worker.request_stop()
    assert worker._stop.is_set()


def test_jitter_unit_callable_affects_backoff(outbound_settings) -> None:
    event_id, _, _ = _queue_connection()
    clock = FrozenClock(FIXED_NOW)
    http = FakeHttp()
    http.queue(
        SignedHttpResult(status_code=503, data=None, transport_error=None)
    )
    worker = _make_worker(
        outbound_settings, http, clock=clock, jitter_unit=1.0
    )
    worker.run_once()
    row = get_guide_operator_outbox_by_event_id(event_id)
    assert row is not None
    expected = FIXED_NOW + retry_delay(1, jitter_unit=1.0)
    assert row["next_attempt_at"] == expected.isoformat()
