"""GO8C3: Mini App API for Guide Operator connection consent."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from aiohttp.test_utils import TestClient, TestServer

from database.queries import get_guide_os_id, register_user
from services.guide_operator_connection_service import (
    ConnectionInvitationIntake,
    confirm_connection,
    receive_connection_disconnect,
    receive_connection_invitation,
    ConnectionDisconnectIntake,
)
from services.miniapp_api_settings import MiniAppApiSettings
from web_api.app import create_miniapp_api_app
from web_api.auth import dev_session_token

API_USER = 706301
OTHER_USER = 706302
TEST_BOT_TOKEN = "7000000000:TEST_miniapp_connection_bot_token"


def run(awaitable):
    return asyncio.run(awaitable)


def _settings(**overrides):
    values = {
        "enabled": True,
        "dev_auth": True,
        "bot_token": TEST_BOT_TOKEN,
        "session_ttl_seconds": 3600,
        "initdata_max_age_seconds": 86400,
        "allowlist": frozenset(),
    }
    values.update(overrides)
    return MiniAppApiSettings(**values)


def _auth_headers(user_id=API_USER, **extra):
    headers = {
        "Authorization": f"Bearer {dev_session_token(user_id)}",
        "Content-Type": "application/json",
    }
    headers.update(extra)
    return headers


async def _with_client(coro):
    app = create_miniapp_api_app(_settings())
    client = TestClient(TestServer(app))
    async with client:
        response = await coro(client)
        response._body_text = await response.text()
        return response


def response_json(response):
    return json.loads(response._body_text)


def response_data(response):
    return response_json(response)["data"]


def response_error(response):
    return response_json(response)["error"]


def api_request(method, path, **kwargs):
    async def _call(client):
        return await client.request(method, path, **kwargs)

    return run(_with_client(_call))


@pytest.fixture
def seeded_guides():
    register_user(API_USER)
    register_user(OTHER_USER)
    owner = get_guide_os_id(API_USER)
    stranger = get_guide_os_id(OTHER_USER)
    assert owner and stranger
    return owner, stranger


def _invite(guide_os_id: str, **overrides):
    payload = {
        "event_id": str(uuid4()),
        "connection_id": str(uuid4()),
        "company_id": str(uuid4()),
        "company_name": "API Operator",
        "guide_os_id": guide_os_id,
        "invitation_expires_at": "2099-12-31T23:59:59+00:00",
        "invited_at": "2026-09-01T10:00:00+00:00",
    }
    payload.update(overrides)
    return receive_connection_invitation(ConnectionInvitationIntake(**payload))


def test_list_requires_auth():
    response = api_request("GET", "/app/v1/guide-operator/connections")
    assert response.status == 401


def test_list_is_session_isolated(seeded_guides):
    owner, stranger = seeded_guides
    invited = _invite(owner, company_name="Owner Co")
    _invite(stranger, company_name="Stranger Co")

    owned = api_request("GET", "/app/v1/guide-operator/connections", headers=_auth_headers())
    assert owned.status == 200
    body = response_data(owned)
    assert [row["companyName"] for row in body["connections"]] == ["Owner Co"]
    assert body["connections"][0]["id"] == invited["connection_id"]
    assert set(body["connections"][0]) == {
        "id",
        "companyName",
        "status",
        "invitedAt",
        "invitationExpiresAt",
        "decidedAt",
        "disconnectedAt",
        "expired",
        "actionable",
    }
    assert "companyId" not in body["connections"][0]
    assert "guideOsId" not in body["connections"][0]

    other = api_request(
        "GET",
        "/app/v1/guide-operator/connections",
        headers=_auth_headers(OTHER_USER),
    )
    assert [row["companyName"] for row in response_data(other)["connections"]] == [
        "Stranger Co"
    ]


def test_confirm_and_idempotent_replay(seeded_guides):
    owner, _stranger = seeded_guides
    invited = _invite(owner)
    decision_event_id = str(uuid4())
    first = api_request(
        "POST",
        f"/app/v1/guide-operator/connections/{invited['connection_id']}/confirm",
        headers=_auth_headers(),
        json={"decisionEventId": decision_event_id},
    )
    assert first.status == 200
    body = response_data(first)
    assert body["status"] == "confirmed"
    assert body["decision"] == "confirm"
    assert body["replayed"] is False

    replay = api_request(
        "POST",
        f"/app/v1/guide-operator/connections/{invited['connection_id']}/confirm",
        headers=_auth_headers(),
        json={"decisionEventId": decision_event_id},
    )
    assert replay.status == 200
    assert response_data(replay)["replayed"] is True

    listed = response_data(
        api_request("GET", "/app/v1/guide-operator/connections", headers=_auth_headers())
    )
    assert listed["connections"][0]["status"] == "confirmed"
    assert listed["connections"][0]["actionable"] is False


def test_decline_invitation(seeded_guides):
    owner, _ = seeded_guides
    invited = _invite(owner)
    response = api_request(
        "POST",
        f"/app/v1/guide-operator/connections/{invited['connection_id']}/decline",
        headers=_auth_headers(),
        json={"decisionEventId": str(uuid4())},
    )
    assert response.status == 200
    assert response_data(response)["status"] == "declined"


def test_expired_and_stale_decisions_fail_closed(seeded_guides):
    owner, stranger = seeded_guides
    expired = _invite(
        owner,
        invitation_expires_at="2026-01-01T00:00:00+00:00",
        invited_at="2025-12-01T00:00:00+00:00",
    )
    expired_resp = api_request(
        "POST",
        f"/app/v1/guide-operator/connections/{expired['connection_id']}/confirm",
        headers=_auth_headers(),
        json={"decisionEventId": str(uuid4())},
    )
    assert expired_resp.status == 409
    assert response_error(expired_resp)["code"] == "connection_not_actionable"

    invited = _invite(owner)
    stranger_resp = api_request(
        "POST",
        f"/app/v1/guide-operator/connections/{invited['connection_id']}/confirm",
        headers=_auth_headers(OTHER_USER),
        json={"decisionEventId": str(uuid4())},
    )
    assert stranger_resp.status == 404

    confirm_connection(owner, invited["connection_id"], decision_event_id=str(uuid4()))
    stale = api_request(
        "POST",
        f"/app/v1/guide-operator/connections/{invited['connection_id']}/decline",
        headers=_auth_headers(),
        json={"decisionEventId": str(uuid4())},
    )
    assert stale.status == 409
    assert response_error(stale)["code"] == "connection_not_actionable"


def test_disconnected_state_in_list(seeded_guides):
    owner, _ = seeded_guides
    invited = _invite(owner, company_name="Then Disconnect")
    confirm_connection(owner, invited["connection_id"], decision_event_id=str(uuid4()))
    receive_connection_disconnect(
        ConnectionDisconnectIntake(
            event_id=str(uuid4()),
            connection_id=invited["connection_id"],
            company_id=invited["company_id"],
            company_name=invited["company_name"],
            guide_os_id=owner,
            disconnected_at="2026-09-05T12:00:00+00:00",
        )
    )
    listed = response_data(
        api_request("GET", "/app/v1/guide-operator/connections", headers=_auth_headers())
    )
    row = listed["connections"][0]
    assert row["status"] == "disconnected"
    assert row["actionable"] is False
    assert row["disconnectedAt"] == "2026-09-05T12:00:00+00:00"
