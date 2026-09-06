"""GO8D1: authenticated Guide Operator inbound event HTTP routes."""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

import jwt
import pytest
from aiohttp.test_utils import TestClient, TestServer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from database.db import init_db
from database.queries import (
    get_guide_operator_assignment,
    get_guide_operator_connection,
    get_guide_operator_connection_inbox,
    get_guide_operator_offer_inbox,
    get_guide_operator_version_inbox,
    get_guide_os_id,
    register_user,
)
from services.guide_operator_assignment_service import accept_assignment
from services.guide_operator_connection_service import (
    ensure_confirmed_connection_for_tests,
)
from services.guide_operator_integration_settings import (
    GuideOperatorIntegrationConfigurationError,
    GuideOperatorIntegrationSettings,
)
from services.guide_operator_service_auth_settings import (
    GuideOperatorServiceAuthSettings,
    reset_guide_operator_service_auth_for_tests,
)
from services.guide_operator_service_jwt import (
    ALGORITHM,
    INBOUND_AUDIENCE,
    INBOUND_ISSUER,
    INBOUND_SUBJECT,
    INBOUND_TOKEN_TYPE,
    MAX_TTL_SECONDS,
    SCOPE_CANCELLATIONS_WRITE,
    SCOPE_CONNECTIONS_WRITE,
    SCOPE_OFFERS_WRITE,
    SCOPE_VERSIONS_WRITE,
)
from web_api.guide_operator_integration import (
    EVENT_ASSIGNMENT_CANCELLED,
    EVENT_ASSIGNMENT_OFFERED,
    EVENT_CONNECTION_DISCONNECTED,
    EVENT_CONNECTION_INVITED,
    EVENT_VERSION_PUBLISHED,
    create_guide_operator_integration_app,
)

FIXED_NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
NOW_TS = int(FIXED_NOW.timestamp())
INBOUND_KID = "guide-operator-test-key"
OUTBOUND_KID = "guide-os-test-key-01"
API_USER = 808401


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


def mint_token(
    private_pem: str,
    *,
    scope: str,
    jti: str | None = None,
    issued_at: int = NOW_TS,
    expires_at: int | None = None,
) -> str:
    claims = {
        "iss": INBOUND_ISSUER,
        "aud": INBOUND_AUDIENCE,
        "sub": INBOUND_SUBJECT,
        "scope": scope,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + MAX_TTL_SECONDS if expires_at is None else expires_at,
        "jti": jti or f"jti-{uuid4().hex}",
    }
    key = serialization.load_pem_private_key(
        private_pem.encode("ascii"), password=None
    )
    return jwt.encode(
        claims,
        key,
        algorithm=ALGORITHM,
        headers={"alg": ALGORITHM, "typ": INBOUND_TOKEN_TYPE, "kid": INBOUND_KID},
    )


@pytest.fixture
def keys() -> tuple[str, str]:
    return _pem_pair()


@pytest.fixture
def outbound_private() -> str:
    return _pem_pair()[0]


@pytest.fixture
def auth_settings(keys: tuple[str, str], outbound_private: str) -> GuideOperatorServiceAuthSettings:
    return GuideOperatorServiceAuthSettings.enabled_with(
        app_env="test",
        public_keys={INBOUND_KID: keys[1]},
        signing_kid=OUTBOUND_KID,
        signing_private_key_pem=outbound_private,
    )


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture(autouse=True)
def _reset_db_and_auth() -> Iterator[None]:
    reset_guide_operator_service_auth_for_tests()
    init_db()
    yield
    reset_guide_operator_service_auth_for_tests()


def run(awaitable):
    return asyncio.run(awaitable)


def _seed_guide(user_id: int = API_USER) -> str:
    register_user(user_id)
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    return guide_os_id


def _envelope(event_type: str, payload: dict, *, event_id: str | None = None) -> dict:
    return {
        "event_id": event_id or str(uuid4()),
        "event_type": event_type,
        "occurred_at": "2026-09-05T10:00:00+00:00",
        "payload": payload,
    }


def _package(
    assignment_id: str,
    guide_os_id: str,
    *,
    start: str = "2026-10-01",
    end: str = "2026-10-03",
) -> dict:
    return {
        "tour": {"title": "Integration tour", "city_or_route": "Tashkent"},
        "assignment": {
            "id": assignment_id,
            "guide_os_id": guide_os_id,
            "role": "main_guide",
            "start_date": start,
            "end_date": end,
        },
        "days": [
            {"date": start, "title": "Day 1", "city_or_route": "Tashkent"},
            {"date": end, "title": "Day last", "city_or_route": "Samarkand"},
        ],
        "group_summary": "12 pax",
    }


async def _with_client(auth_settings, clock, coro):
    app = create_guide_operator_integration_app(
        auth_settings=auth_settings,
        clock=clock,
    )
    client = TestClient(TestServer(app))
    async with client:
        return await coro(client)


def api_post(auth_settings, clock, path: str, *, token: str | None, body, **kwargs):
    async def _call(client):
        headers = {"Content-Type": kwargs.get("content_type", "application/json")}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        if isinstance(body, (dict, list)):
            response = await client.post(path, json=body, headers=headers)
        else:
            response = await client.post(path, data=body, headers=headers)
        response._body_text = await response.text()
        return response

    return run(_with_client(auth_settings, clock, _call))


def api_posts(auth_settings, clock, calls: list[dict]):
    """Multiple POSTs against one app/loop (avoids aiohttp loop reuse errors)."""

    async def _call(client):
        responses = []
        for item in calls:
            headers = {"Content-Type": "application/json"}
            token = item.get("token")
            if token is not None:
                headers["Authorization"] = f"Bearer {token}"
            response = await client.post(
                item["path"], json=item["body"], headers=headers
            )
            response._body_text = await response.text()
            responses.append(response)
        return responses

    return run(_with_client(auth_settings, clock, _call))


def response_json(response):
    return json.loads(response._body_text)


# --- settings ---


def test_integration_settings_default_disabled():
    settings = GuideOperatorIntegrationSettings.from_env({})
    assert settings.enabled is False
    assert settings.host == "127.0.0.1"
    assert settings.port == 8084


def test_integration_settings_enabled():
    settings = GuideOperatorIntegrationSettings.from_env(
        {
            "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED": "true",
            "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_HOST": "127.0.0.1",
            "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_PORT": "8099",
        }
    )
    assert settings.enabled is True
    assert settings.port == 8099


def test_integration_settings_production_rejects_wildcard():
    with pytest.raises(GuideOperatorIntegrationConfigurationError):
        GuideOperatorIntegrationSettings.from_env(
            {
                "APP_ENV": "production",
                "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED": "true",
                "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_HOST": "0.0.0.0",
            }
        )


# --- auth gate ---


def test_disabled_auth_returns_503(clock: FrozenClock):
    response = api_post(
        GuideOperatorServiceAuthSettings.disabled(),
        clock,
        f"/integration/v1/guide-connections/{uuid4()}/invited",
        token="not-a-jwt",
        body=_envelope(EVENT_CONNECTION_INVITED, {"connection_id": "x"}),
    )
    assert response.status == 503
    body = response_json(response)
    assert body["error"]["code"] == "service_authentication_unavailable"


def test_missing_bearer_returns_401(auth_settings, clock, keys):
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guide-connections/{uuid4()}/invited",
        token=None,
        body=_envelope(EVENT_CONNECTION_INVITED, {"connection_id": "x"}),
    )
    assert response.status == 401


def test_expired_token_returns_401(auth_settings, clock, keys):
    connection_id = str(uuid4())
    token = mint_token(
        keys[0],
        scope=SCOPE_CONNECTIONS_WRITE,
        issued_at=NOW_TS - 120,
        expires_at=NOW_TS - 60,
    )
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guide-connections/{connection_id}/invited",
        token=token,
        body=_envelope(
            EVENT_CONNECTION_INVITED,
            {
                "connection_id": connection_id,
                "company_id": str(uuid4()),
                "company_name": "Co",
                "guide_os_id": _seed_guide(),
                "invitation_expires_at": "2099-01-01T00:00:00+00:00",
            },
        ),
    )
    assert response.status == 401


def test_scope_isolation_rejects_wrong_scope(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    connection_id = str(uuid4())
    token = mint_token(keys[0], scope=SCOPE_OFFERS_WRITE)
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guide-connections/{connection_id}/invited",
        token=token,
        body=_envelope(
            EVENT_CONNECTION_INVITED,
            {
                "connection_id": connection_id,
                "company_id": str(uuid4()),
                "company_name": "Co",
                "guide_os_id": guide_os_id,
                "invitation_expires_at": "2099-01-01T00:00:00+00:00",
            },
        ),
    )
    assert response.status == 401


def test_jti_replay_rejects_second_use_of_same_token(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    connection_id = str(uuid4())
    token = mint_token(
        keys[0], scope=SCOPE_CONNECTIONS_WRITE, jti="reuse-once-jti-01"
    )
    payload = {
        "connection_id": connection_id,
        "company_id": str(uuid4()),
        "company_name": "Co",
        "guide_os_id": guide_os_id,
        "invitation_expires_at": "2099-01-01T00:00:00+00:00",
        "invited_at": "2026-09-05T10:00:00+00:00",
    }
    first, second = api_posts(
        auth_settings,
        clock,
        [
            {
                "path": f"/integration/v1/guide-connections/{connection_id}/invited",
                "token": token,
                "body": _envelope(EVENT_CONNECTION_INVITED, payload),
            },
            {
                "path": f"/integration/v1/guide-connections/{connection_id}/disconnected",
                "token": token,
                "body": _envelope(
                    EVENT_CONNECTION_DISCONNECTED,
                    {
                        "connection_id": connection_id,
                        "company_id": payload["company_id"],
                        "company_name": "Co",
                        "guide_os_id": guide_os_id,
                        "disconnected_at": "2026-09-05T11:00:00+00:00",
                    },
                ),
            },
        ],
    )
    assert first.status == 200
    assert second.status == 401


# --- envelope / path validation ---


def test_malformed_envelope_extra_key(auth_settings, clock, keys):
    connection_id = str(uuid4())
    token = mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE)
    body = _envelope(
        EVENT_CONNECTION_INVITED,
        {"connection_id": connection_id},
    )
    body["extra"] = "nope"
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guide-connections/{connection_id}/invited",
        token=token,
        body=body,
    )
    assert response.status == 400
    assert response_json(response)["error"]["code"] == "invalid_request"


def test_event_type_mismatch_on_route(auth_settings, clock, keys):
    connection_id = str(uuid4())
    token = mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE)
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guide-connections/{connection_id}/invited",
        token=token,
        body=_envelope(
            EVENT_CONNECTION_DISCONNECTED,
            {"connection_id": connection_id},
        ),
    )
    assert response.status == 400


def test_path_payload_id_mismatch(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    path_id = str(uuid4())
    token = mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE)
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guide-connections/{path_id}/invited",
        token=token,
        body=_envelope(
            EVENT_CONNECTION_INVITED,
            {
                "connection_id": str(uuid4()),
                "company_id": str(uuid4()),
                "company_name": "Co",
                "guide_os_id": guide_os_id,
                "invitation_expires_at": "2099-01-01T00:00:00+00:00",
            },
        ),
    )
    assert response.status == 400


# --- happy paths + replay ---


def test_connection_invited_applied_and_replayed(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    connection_id = str(uuid4())
    company_id = str(uuid4())
    event_id = str(uuid4())
    payload = {
        "connection_id": connection_id,
        "company_id": company_id,
        "company_name": "Operator Co",
        "guide_os_id": guide_os_id,
        "invitation_expires_at": "2099-12-31T23:59:59+00:00",
        "invited_at": "2026-09-05T10:00:00+00:00",
    }
    envelope = _envelope(EVENT_CONNECTION_INVITED, payload, event_id=event_id)
    path = f"/integration/v1/guide-connections/{connection_id}/invited"

    first, second = api_posts(
        auth_settings,
        clock,
        [
            {
                "path": path,
                "token": mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE),
                "body": envelope,
            },
            {
                "path": path,
                "token": mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE),
                "body": envelope,
            },
        ],
    )
    assert first.status == 200
    data = response_json(first)["data"]
    assert data["status"] == "applied"
    assert data["eventId"] == event_id
    assert data["eventType"] == EVENT_CONNECTION_INVITED
    assert data["replayed"] is False
    assert get_guide_operator_connection(connection_id)["status"] == "invited"
    assert get_guide_operator_connection_inbox(event_id) is not None

    assert second.status == 200
    assert response_json(second)["data"]["status"] == "replayed"
    assert response_json(second)["data"]["replayed"] is True


def test_connection_disconnected(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    connection = ensure_confirmed_connection_for_tests(guide_os_id)
    connection_id = connection["connection_id"]
    token = mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE)
    event_id = str(uuid4())
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guide-connections/{connection_id}/disconnected",
        token=token,
        body=_envelope(
            EVENT_CONNECTION_DISCONNECTED,
            {
                "connection_id": connection_id,
                "company_id": connection["company_id"],
                "company_name": connection["company_name"],
                "guide_os_id": guide_os_id,
                "disconnected_at": "2026-09-05T12:00:00+00:00",
            },
            event_id=event_id,
        ),
    )
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "applied"
    assert get_guide_operator_connection(connection_id)["status"] == "disconnected"


def test_assignment_offered(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    connection = ensure_confirmed_connection_for_tests(guide_os_id)
    assignment_id = str(uuid4())
    event_id = str(uuid4())
    payload = {
        "assignment_id": assignment_id,
        "guide_os_id": guide_os_id,
        "company_id": connection["company_id"],
        "company_name": connection["company_name"],
        "guide_connection_id": connection["connection_id"],
        "role": "main_guide",
        "start_date": "2026-10-01",
        "end_date": "2026-10-03",
        "working_package": _package(assignment_id, guide_os_id),
        "version_number": 1,
        "offered_at": "2026-09-05T10:00:00+00:00",
    }
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/assignments/{assignment_id}/offered",
        token=mint_token(keys[0], scope=SCOPE_OFFERS_WRITE),
        body=_envelope(EVENT_ASSIGNMENT_OFFERED, payload, event_id=event_id),
    )
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "applied"
    assert get_guide_operator_assignment(assignment_id)["status"] == "offered"
    assert get_guide_operator_offer_inbox(event_id) is not None


def test_assignment_offered_without_connection_fails_closed(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id = str(uuid4())
    payload = {
        "assignment_id": assignment_id,
        "guide_os_id": guide_os_id,
        "company_id": str(uuid4()),
        "company_name": "Ghost Co",
        "guide_connection_id": str(uuid4()),
        "role": "main_guide",
        "start_date": "2026-10-01",
        "end_date": "2026-10-03",
        "working_package": _package(assignment_id, guide_os_id),
        "version_number": 1,
        "offered_at": "2026-09-05T10:00:00+00:00",
    }
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/assignments/{assignment_id}/offered",
        token=mint_token(keys[0], scope=SCOPE_OFFERS_WRITE),
        body=_envelope(EVENT_ASSIGNMENT_OFFERED, payload),
    )
    assert response.status == 400
    assert response_json(response)["error"]["code"] == "validation_error"
    assert get_guide_operator_assignment(assignment_id) is None


def test_offer_payload_hash_mismatch_conflict(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    connection = ensure_confirmed_connection_for_tests(guide_os_id)
    assignment_id = str(uuid4())
    event_id = str(uuid4())
    payload = {
        "assignment_id": assignment_id,
        "guide_os_id": guide_os_id,
        "company_id": connection["company_id"],
        "company_name": connection["company_name"],
        "guide_connection_id": connection["connection_id"],
        "role": "main_guide",
        "start_date": "2026-10-01",
        "end_date": "2026-10-03",
        "working_package": _package(assignment_id, guide_os_id),
        "version_number": 1,
        "offered_at": "2026-09-05T10:00:00+00:00",
    }
    path = f"/integration/v1/assignments/{assignment_id}/offered"
    altered = copy.deepcopy(payload)
    altered["role"] = "assistant_guide"
    first, second = api_posts(
        auth_settings,
        clock,
        [
            {
                "path": path,
                "token": mint_token(keys[0], scope=SCOPE_OFFERS_WRITE),
                "body": _envelope(EVENT_ASSIGNMENT_OFFERED, payload, event_id=event_id),
            },
            {
                "path": path,
                "token": mint_token(keys[0], scope=SCOPE_OFFERS_WRITE),
                "body": _envelope(EVENT_ASSIGNMENT_OFFERED, altered, event_id=event_id),
            },
        ],
    )
    assert first.status == 200
    assert second.status == 409
    assert response_json(second)["error"]["code"] == "idempotency_conflict"


def _seed_accepted_assignment(guide_os_id: str):
    connection = ensure_confirmed_connection_for_tests(guide_os_id)
    assignment_id = str(uuid4())
    from services.guide_operator_assignment_service import (
        AssignmentOfferIntake,
        receive_assignment_offer,
    )

    offer = AssignmentOfferIntake(
        event_id=str(uuid4()),
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
        company_id=connection["company_id"],
        company_name=connection["company_name"],
        guide_connection_id=connection["connection_id"],
        role="main_guide",
        start_date="2026-10-01",
        end_date="2026-10-03",
        working_package=_package(assignment_id, guide_os_id),
        offered_at="2026-09-05T09:00:00+00:00",
    )
    receive_assignment_offer(offer)
    accept_assignment(
        guide_os_id,
        assignment_id,
        decision_event_id=str(uuid4()),
    )
    return assignment_id, offer


def test_ordinary_version_dispatch(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id, offer = _seed_accepted_assignment(guide_os_id)
    next_package = copy.deepcopy(offer.working_package)
    next_package["group_summary"] = "14 pax"
    next_package["tour"]["title"] = "Updated tour"
    event_id = str(uuid4())
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/assignments/{assignment_id}/versions",
        token=mint_token(keys[0], scope=SCOPE_VERSIONS_WRITE),
        body=_envelope(
            EVENT_VERSION_PUBLISHED,
            {
                "assignment_id": assignment_id,
                "guide_os_id": guide_os_id,
                "version_number": 2,
                "previous_active_version_number": 1,
                "severity": "ordinary",
                "working_package": next_package,
                "change_summary": [
                    {
                        "code": "group_summary",
                        "severity": "ordinary",
                        "path": "group_summary",
                    }
                ],
                "published_at": "2026-09-05T11:00:00+00:00",
            },
            event_id=event_id,
        ),
    )
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "applied"
    stored = get_guide_operator_assignment(assignment_id)
    assert stored["active_version_number"] == 2
    assert get_guide_operator_version_inbox(event_id) is not None


def test_critical_version_dispatch_keeps_active(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id, offer = _seed_accepted_assignment(guide_os_id)
    next_package = copy.deepcopy(offer.working_package)
    next_package["assignment"]["start_date"] = "2026-10-05"
    next_package["assignment"]["end_date"] = "2026-10-07"
    next_package["days"] = [
        {"date": "2026-10-05", "title": "Day 1", "city_or_route": "Bukhara"},
        {"date": "2026-10-07", "title": "Day last", "city_or_route": "Bukhara"},
    ]
    event_id = str(uuid4())
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/assignments/{assignment_id}/versions",
        token=mint_token(keys[0], scope=SCOPE_VERSIONS_WRITE),
        body=_envelope(
            EVENT_VERSION_PUBLISHED,
            {
                "assignment_id": assignment_id,
                "guide_os_id": guide_os_id,
                "version_number": 2,
                "previous_active_version_number": 1,
                "severity": "critical",
                "working_package": next_package,
                "change_summary": [
                    {
                        "code": "dates",
                        "severity": "critical",
                        "path": "assignment.start_date",
                    }
                ],
                "published_at": "2026-09-05T11:00:00+00:00",
            },
            event_id=event_id,
        ),
    )
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "applied"
    stored = get_guide_operator_assignment(assignment_id)
    assert stored["active_version_number"] == 1
    assert stored["pending_critical_version_number"] == 2


def test_invalid_severity_rejected(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id, offer = _seed_accepted_assignment(guide_os_id)
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/assignments/{assignment_id}/versions",
        token=mint_token(keys[0], scope=SCOPE_VERSIONS_WRITE),
        body=_envelope(
            EVENT_VERSION_PUBLISHED,
            {
                "assignment_id": assignment_id,
                "guide_os_id": guide_os_id,
                "version_number": 2,
                "previous_active_version_number": 1,
                "severity": "urgent",
                "working_package": offer.working_package,
                "change_summary": [],
                "published_at": "2026-09-05T11:00:00+00:00",
            },
        ),
    )
    assert response.status == 400


def test_cancellation_applied(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id, _offer = _seed_accepted_assignment(guide_os_id)
    event_id = str(uuid4())
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/assignments/{assignment_id}/cancelled",
        token=mint_token(keys[0], scope=SCOPE_CANCELLATIONS_WRITE),
        body=_envelope(
            EVENT_ASSIGNMENT_CANCELLED,
            {
                "assignment_id": assignment_id,
                "guide_os_id": guide_os_id,
                "version_number": 1,
                "cancelled_at": "2026-09-05T12:30:00+00:00",
            },
            event_id=event_id,
        ),
    )
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "applied"
    assert get_guide_operator_assignment(assignment_id)["status"] == "cancelled"


def test_cancellation_unknown_assignment_404(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id = str(uuid4())
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/assignments/{assignment_id}/cancelled",
        token=mint_token(keys[0], scope=SCOPE_CANCELLATIONS_WRITE),
        body=_envelope(
            EVENT_ASSIGNMENT_CANCELLED,
            {
                "assignment_id": assignment_id,
                "guide_os_id": guide_os_id,
                "version_number": 1,
                "cancelled_at": "2026-09-05T12:30:00+00:00",
            },
        ),
    )
    assert response.status == 404
    err = response_json(response)["error"]
    assert err["code"] == "not_found"
    assert "calendar" not in err["message"].lower()
    assert guide_os_id not in json.dumps(err)


def test_errors_do_not_leak_private_fields(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    connection_id = str(uuid4())
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guide-connections/{connection_id}/invited",
        token=mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE),
        body=_envelope(
            EVENT_CONNECTION_INVITED,
            {
                "connection_id": connection_id,
                "company_id": "not-a-uuid",
                "company_name": "Secret Operator Name XYZ",
                "guide_os_id": guide_os_id,
                "invitation_expires_at": "bad-date",
            },
        ),
    )
    assert response.status == 400
    text = response._body_text
    assert "Secret Operator Name XYZ" not in text
    assert guide_os_id not in text
