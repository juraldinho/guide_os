"""GO8D2: authenticated guide discovery and availability HTTP."""

from __future__ import annotations

import asyncio
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
from database.queries import get_guide_os_id, get_user_id_by_guide_os_id, register_user
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
    SCOPE_AVAILABILITY_READ,
    SCOPE_CONNECTIONS_WRITE,
    SCOPE_OFFERS_WRITE,
)
from services.tour_service import (
    TourEntryDraft,
    create_tour_entry,
    save_day_off,
    save_tour,
)
from utils.constants import SOURCE_MINI_APP, STATUS_CONFIRMED
from web_api.guide_operator_integration import create_guide_operator_integration_app

FIXED_NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
NOW_TS = int(FIXED_NOW.timestamp())
INBOUND_KID = "guide-operator-test-key"
OUTBOUND_KID = "guide-os-test-key-01"
API_USER = 808402
OTHER_USER = 808403


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
    issuer: str = INBOUND_ISSUER,
    audience: str = INBOUND_AUDIENCE,
) -> str:
    claims = {
        "iss": issuer,
        "aud": audience,
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


async def _with_client(auth_settings, clock, coro):
    app = create_guide_operator_integration_app(
        auth_settings=auth_settings,
        clock=clock,
    )
    client = TestClient(TestServer(app))
    async with client:
        return await coro(client)


def api_post(auth_settings, clock, path: str, *, token: str | None, body):
    async def _call(client):
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        response = await client.post(path, json=body, headers=headers)
        response._body_text = await response.text()
        return response

    return run(_with_client(auth_settings, clock, _call))


def response_json(response):
    return json.loads(response._body_text)


# --- discovery ---


def test_discovery_valid_guide(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    response = api_post(
        auth_settings,
        clock,
        "/integration/v1/guides/discovery",
        token=mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE),
        body={"guide_os_id": guide_os_id},
    )
    assert response.status == 200
    data = response_json(response)["data"]
    assert data == {
        "guideOsId": guide_os_id,
        "canReceiveInvitation": True,
    }
    text = response._body_text
    assert str(API_USER) not in text
    assert "display" not in text.lower()
    assert "phone" not in text.lower()
    assert "email" not in text.lower()
    assert "telegram" not in text.lower()


def test_discovery_unknown_guide_404(auth_settings, clock, keys):
    response = api_post(
        auth_settings,
        clock,
        "/integration/v1/guides/discovery",
        token=mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE),
        body={"guide_os_id": str(uuid4())},
    )
    assert response.status == 404
    assert response_json(response)["error"]["code"] == "not_found"


def test_discovery_malformed_guide_id(auth_settings, clock, keys):
    response = api_post(
        auth_settings,
        clock,
        "/integration/v1/guides/discovery",
        token=mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE),
        body={"guide_os_id": "not-a-uuid"},
    )
    assert response.status == 400


def test_discovery_rejects_wrong_scope(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    response = api_post(
        auth_settings,
        clock,
        "/integration/v1/guides/discovery",
        token=mint_token(keys[0], scope=SCOPE_AVAILABILITY_READ),
        body={"guide_os_id": guide_os_id},
    )
    assert response.status == 401


def test_discovery_rejects_wrong_audience(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    response = api_post(
        auth_settings,
        clock,
        "/integration/v1/guides/discovery",
        token=mint_token(
            keys[0],
            scope=SCOPE_CONNECTIONS_WRITE,
            audience="wrong-audience",
        ),
        body={"guide_os_id": guide_os_id},
    )
    assert response.status == 401


def test_discovery_rejects_wrong_issuer(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    response = api_post(
        auth_settings,
        clock,
        "/integration/v1/guides/discovery",
        token=mint_token(
            keys[0],
            scope=SCOPE_CONNECTIONS_WRITE,
            issuer="wrong-issuer",
        ),
        body={"guide_os_id": guide_os_id},
    )
    assert response.status == 401


def test_discovery_disabled_auth_503(clock, keys):
    guide_os_id = _seed_guide()
    response = api_post(
        GuideOperatorServiceAuthSettings.disabled(),
        clock,
        "/integration/v1/guides/discovery",
        token=mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE),
        body={"guide_os_id": guide_os_id},
    )
    assert response.status == 503


# --- availability ---


def test_availability_free_range(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guides/{guide_os_id}/availability",
        token=mint_token(keys[0], scope=SCOPE_AVAILABILITY_READ),
        body={"start_date": "2026-11-01", "end_date": "2026-11-03"},
    )
    assert response.status == 200
    data = response_json(response)["data"]
    assert data == {
        "guideOsId": guide_os_id,
        "startDate": "2026-11-01",
        "endDate": "2026-11-03",
        "status": "free",
    }
    assert set(data) == {"guideOsId", "startDate", "endDate", "status"}


def test_availability_busy_full_day_tour(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    assert user_id is not None
    save_tour(
        user_id,
        company="Secret Operator",
        city="Samarkand",
        date_text="2026-11-05",
        status=STATUS_CONFIRMED,
        income=250,
    )
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guides/{guide_os_id}/availability",
        token=mint_token(keys[0], scope=SCOPE_AVAILABILITY_READ),
        body={"start_date": "2026-11-05", "end_date": "2026-11-05"},
    )
    assert response.status == 200
    data = response_json(response)["data"]
    assert data["status"] == "busy"
    text = response._body_text
    assert "Secret Operator" not in text
    assert "Samarkand" not in text
    assert "250" not in text
    assert "income" not in text.lower()
    assert "note" not in text.lower()


def test_availability_busy_day_off(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    assert user_id is not None
    save_day_off(user_id, "2026-11-06")
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guides/{guide_os_id}/availability",
        token=mint_token(keys[0], scope=SCOPE_AVAILABILITY_READ),
        body={"start_date": "2026-11-06", "end_date": "2026-11-06"},
    )
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "busy"


def test_availability_partial_timed_tour(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    assert user_id is not None
    create_tour_entry(
        user_id,
        TourEntryDraft(
            title="Morning only",
            company="Hidden Co",
            location="Bukhara",
            start_date="2026-11-07",
            end_date="2026-11-07",
            start_time="09:00",
            end_time="12:00",
            income=90,
            source=SOURCE_MINI_APP,
        ),
    )
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guides/{guide_os_id}/availability",
        token=mint_token(keys[0], scope=SCOPE_AVAILABILITY_READ),
        body={"start_date": "2026-11-07", "end_date": "2026-11-07"},
    )
    assert response.status == 200
    data = response_json(response)["data"]
    assert data["status"] == "partial"
    assert "Morning only" not in response._body_text
    assert "Hidden Co" not in response._body_text


def test_availability_partial_mixed_days(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    assert user_id is not None
    save_tour(
        user_id,
        company="Busy Co",
        city="Tashkent",
        date_text="2026-11-10",
        status=STATUS_CONFIRMED,
        income=100,
    )
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guides/{guide_os_id}/availability",
        token=mint_token(keys[0], scope=SCOPE_AVAILABILITY_READ),
        body={"start_date": "2026-11-10", "end_date": "2026-11-11"},
    )
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "partial"


def test_availability_unknown_guide_unavailable(auth_settings, clock, keys):
    missing = str(uuid4())
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guides/{missing}/availability",
        token=mint_token(keys[0], scope=SCOPE_AVAILABILITY_READ),
        body={"start_date": "2026-11-01", "end_date": "2026-11-02"},
    )
    assert response.status == 200
    data = response_json(response)["data"]
    assert data["status"] == "unavailable"
    assert data["guideOsId"] == missing
    assert "tour" not in response._body_text.lower()


def test_availability_rejects_wrong_scope(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guides/{guide_os_id}/availability",
        token=mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE),
        body={"start_date": "2026-11-01", "end_date": "2026-11-02"},
    )
    assert response.status == 401


def test_availability_rejects_offers_scope(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guides/{guide_os_id}/availability",
        token=mint_token(keys[0], scope=SCOPE_OFFERS_WRITE),
        body={"start_date": "2026-11-01", "end_date": "2026-11-02"},
    )
    assert response.status == 401


def test_availability_rejects_wrong_audience(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guides/{guide_os_id}/availability",
        token=mint_token(
            keys[0],
            scope=SCOPE_AVAILABILITY_READ,
            audience="guide-shop",
        ),
        body={"start_date": "2026-11-01", "end_date": "2026-11-02"},
    )
    assert response.status == 401


def test_availability_malformed_range(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guides/{guide_os_id}/availability",
        token=mint_token(keys[0], scope=SCOPE_AVAILABILITY_READ),
        body={"start_date": "2026-11-10", "end_date": "2026-11-01"},
    )
    assert response.status == 400


def test_availability_excessive_range(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guides/{guide_os_id}/availability",
        token=mint_token(keys[0], scope=SCOPE_AVAILABILITY_READ),
        body={"start_date": "2026-01-01", "end_date": "2026-12-31"},
    )
    assert response.status == 400
    assert response_json(response)["error"]["code"] == "validation_error"


def test_availability_does_not_leak_other_guide_calendar(auth_settings, clock, keys):
    guide_a = _seed_guide(API_USER)
    guide_b = _seed_guide(OTHER_USER)
    user_b = get_user_id_by_guide_os_id(guide_b)
    assert user_b is not None
    save_tour(
        user_b,
        company="Other Guide Tour",
        city="Khiva",
        date_text="2026-11-15",
        status=STATUS_CONFIRMED,
        income=999,
    )
    response = api_post(
        auth_settings,
        clock,
        f"/integration/v1/guides/{guide_a}/availability",
        token=mint_token(keys[0], scope=SCOPE_AVAILABILITY_READ),
        body={"start_date": "2026-11-15", "end_date": "2026-11-15"},
    )
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "free"
    assert "Other Guide Tour" not in response._body_text
    assert guide_b not in response._body_text


def test_availability_disabled_auth_503(clock, keys):
    guide_os_id = _seed_guide()
    response = api_post(
        GuideOperatorServiceAuthSettings.disabled(),
        clock,
        f"/integration/v1/guides/{guide_os_id}/availability",
        token=mint_token(keys[0], scope=SCOPE_AVAILABILITY_READ),
        body={"start_date": "2026-11-01", "end_date": "2026-11-02"},
    )
    assert response.status == 503
