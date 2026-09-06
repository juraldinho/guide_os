"""GO11A: Guide OS local projection reconciliation snapshots."""

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
from database.queries import get_guide_os_id, register_user
from services.guide_operator_assignment_service import (
    AssignmentOfferIntake,
    accept_assignment,
    receive_assignment_offer,
)
from services.guide_operator_connection_service import ensure_confirmed_connection_for_tests
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
    SCOPE_CONNECTIONS_WRITE,
    SCOPE_OPERATOR_RECONCILE,
)
from web_api.guide_operator_integration import create_guide_operator_integration_app

FIXED_NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
NOW_TS = int(FIXED_NOW.timestamp())
INBOUND_KID = "guide-operator-test-key"
OUTBOUND_KID = "guide-os-test-key-01"
API_USER = 808411
OTHER_USER = 808412
PRIVACY_MARKERS = (
    "telegram",
    "working_package",
    "operator_message",
    "phone",
    "BEGIN PRIVATE",
    "income",
)


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
) -> str:
    claims = {
        "iss": INBOUND_ISSUER,
        "aud": INBOUND_AUDIENCE,
        "sub": INBOUND_SUBJECT,
        "scope": scope,
        "iat": NOW_TS,
        "nbf": NOW_TS,
        "exp": NOW_TS + MAX_TTL_SECONDS,
        "jti": jti or f"jti-{uuid4().hex}",
    }
    key = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
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


def api_get(auth_settings, clock, path: str, *, token: str | None):
    async def _call(client):
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        response = await client.get(path, headers=headers)
        response._body_text = await response.text()
        return response

    return run(_with_client(auth_settings, clock, _call))


def response_json(response):
    return json.loads(response._body_text)


def _seed_accepted_assignment(guide_os_id: str) -> tuple[str, str]:
    connection = ensure_confirmed_connection_for_tests(guide_os_id)
    assignment_id = str(uuid4())
    offer = AssignmentOfferIntake(
        event_id=str(uuid4()),
        assignment_id=assignment_id,
        guide_connection_id=connection["connection_id"],
        company_id=connection["company_id"],
        company_name="Operator Co",
        guide_os_id=guide_os_id,
        role="main_guide",
        start_date="2026-09-14",
        end_date="2026-09-16",
        response_deadline=None,
        operator_message="hidden operator note",
        offered_at="2026-09-05T10:00:00+00:00",
        working_package={
            "tour": {"title": "Hidden", "city_or_route": "Samarkand"},
            "assignment": {
                "id": assignment_id,
                "role": "main_guide",
                "start_date": "2026-09-14",
                "end_date": "2026-09-16",
            },
            "days": [
                {
                    "date": "2026-09-14",
                    "title": "Day 1",
                    "city_or_route": "Samarkand",
                }
            ],
        },
    )
    receive_assignment_offer(offer)
    accept_assignment(
        guide_os_id,
        assignment_id,
        decision_event_id=str(uuid4()),
        decided_at="2026-09-05T11:00:00+00:00",
    )
    return connection["connection_id"], assignment_id


def test_local_connection_and_assignment_snapshots(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    connection_id, assignment_id = _seed_accepted_assignment(guide_os_id)

    connections = api_get(
        auth_settings,
        clock,
        f"/integration/v1/reconcile/guides/{guide_os_id}/connections",
        token=mint_token(keys[0], scope=SCOPE_OPERATOR_RECONCILE),
    )
    assert connections.status == 200
    payload = response_json(connections)["data"]
    assert payload["schema_version"] == "reconcile.snapshot.v1"
    assert payload["guide_os_id"] == guide_os_id
    assert len(payload["items"]) == 1
    assert payload["items"][0]["connection_id"] == connection_id
    assert payload["items"][0]["status"] == "confirmed"
    assert "local_fields" in payload

    one = api_get(
        auth_settings,
        clock,
        f"/integration/v1/reconcile/guides/{guide_os_id}/connections/{connection_id}",
        token=mint_token(keys[0], scope=SCOPE_OPERATOR_RECONCILE),
    )
    assert one.status == 200

    assignments = api_get(
        auth_settings,
        clock,
        f"/integration/v1/reconcile/guides/{guide_os_id}/assignments",
        token=mint_token(keys[0], scope=SCOPE_OPERATOR_RECONCILE),
    )
    assert assignments.status == 200
    assign_payload = response_json(assignments)["data"]
    assert len(assign_payload["items"]) == 1
    item = assign_payload["items"][0]
    assert item["assignment_id"] == assignment_id
    assert item["status"] == "accepted"
    assert item["calendar_projection"]["exists"] is True
    assert item["calendar_projection"]["start_date"] == "2026-09-14"
    assert item["calendar_projection"]["version_number"] == 1
    blob = connections._body_text + assignments._body_text + one._body_text
    for marker in PRIVACY_MARKERS:
        assert marker not in blob
    assert "hidden operator note" not in blob
    assert "Hidden" not in blob


def test_empty_results_pagination_and_wrong_resource(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    other = _seed_guide(OTHER_USER)
    connection_id, assignment_id = _seed_accepted_assignment(guide_os_id)

    empty = api_get(
        auth_settings,
        clock,
        f"/integration/v1/reconcile/guides/{other}/assignments",
        token=mint_token(keys[0], scope=SCOPE_OPERATOR_RECONCILE),
    )
    assert empty.status == 200
    assert response_json(empty)["data"]["items"] == []

    page = api_get(
        auth_settings,
        clock,
        f"/integration/v1/reconcile/guides/{guide_os_id}/assignments?limit=1",
        token=mint_token(keys[0], scope=SCOPE_OPERATOR_RECONCILE),
    )
    assert page.status == 200
    assert len(response_json(page)["data"]["items"]) == 1

    bad_limit = api_get(
        auth_settings,
        clock,
        f"/integration/v1/reconcile/guides/{guide_os_id}/assignments?limit=0",
        token=mint_token(keys[0], scope=SCOPE_OPERATOR_RECONCILE),
    )
    assert bad_limit.status == 400

    cross = api_get(
        auth_settings,
        clock,
        f"/integration/v1/reconcile/guides/{other}/assignments/{assignment_id}",
        token=mint_token(keys[0], scope=SCOPE_OPERATOR_RECONCILE),
    )
    assert cross.status == 404

    unknown = api_get(
        auth_settings,
        clock,
        f"/integration/v1/reconcile/guides/{guide_os_id}/connections/{uuid4()}",
        token=mint_token(keys[0], scope=SCOPE_OPERATOR_RECONCILE),
    )
    assert unknown.status == 404
    assert connection_id


def test_wrong_scope_and_disabled_auth(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    wrong = mint_token(keys[0], scope=SCOPE_CONNECTIONS_WRITE)
    scoped = api_get(
        auth_settings,
        clock,
        f"/integration/v1/reconcile/guides/{guide_os_id}/connections",
        token=wrong,
    )
    assert scoped.status == 401

    missing = api_get(
        auth_settings,
        clock,
        f"/integration/v1/reconcile/guides/{guide_os_id}/connections",
        token=None,
    )
    assert missing.status == 401

    disabled = GuideOperatorServiceAuthSettings.disabled()
    token = mint_token(keys[0], scope=SCOPE_OPERATOR_RECONCILE)
    response = api_get(
        disabled,
        clock,
        f"/integration/v1/reconcile/guides/{guide_os_id}/connections",
        token=token,
    )
    assert response.status == 503
    assert response_json(response)["error"]["code"] == "service_authentication_unavailable"


def test_malformed_guide_id(auth_settings, clock, keys):
    token = mint_token(keys[0], scope=SCOPE_OPERATOR_RECONCILE)
    response = api_get(
        auth_settings,
        clock,
        "/integration/v1/reconcile/guides/not-a-uuid/connections",
        token=token,
    )
    assert response.status == 400
