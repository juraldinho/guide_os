import asyncio
import time

import pytest
from aiohttp.test_utils import TestClient, TestServer

from database.queries import register_user
from services.miniapp_api_settings import MiniAppApiSettings
from web_api.app import create_miniapp_api_app
from web_api.telegram_auth import build_synthetic_init_data

from tests.test_miniapp_api import API_USER, response_json, run

TEST_BOT_TOKEN = "7000000000:TEST_miniapp_synthetic_bot_token"
TELEGRAM_USER = 912345678


def _now_timestamp():
    return int(time.time())


def _settings(**overrides):
    values = {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8083,
        "dev_auth": False,
        "bot_token": TEST_BOT_TOKEN,
        "session_ttl_seconds": 3600,
        "initdata_max_age_seconds": 86400,
        "allowlist": frozenset(),
    }
    values.update(overrides)
    return MiniAppApiSettings(**values)


async def _with_client(settings, coro):
    app = create_miniapp_api_app(settings)
    client = TestClient(TestServer(app))
    async with client:
        response = await coro(client)
        response._body_text = await response.text()
        return response


def api_request(settings, method, path, **kwargs):
    async def _call(client):
        return await client.request(method, path, **kwargs)

    return run(_with_client(settings, _call))


def _valid_init_data(user_id=TELEGRAM_USER, auth_date=None):
    return build_synthetic_init_data(
        TEST_BOT_TOKEN,
        user_id,
        auth_date if auth_date is not None else _now_timestamp(),
    )


def _create_session(settings, init_data=None, **kwargs):
    body = {"init_data": init_data or _valid_init_data()}
    return api_request(
        settings,
        "POST",
        "/app/v1/session",
        json=body,
        **kwargs,
    )


def _session_token_from_response(response):
    body = response_json(response)
    return body["data"]["session_token"]


@pytest.fixture
def production_settings():
    return _settings()


def test_valid_init_data_creates_session_and_allows_entries(production_settings):
    register_user(TELEGRAM_USER)
    session = _create_session(production_settings)
    body = response_json(session)
    assert session.status == 200
    token = body["data"]["session_token"]
    assert token and not token.startswith("dev:")
    assert body["data"]["session_expires_at"]
    assert body["data"]["user"]["telegram_id"] == str(TELEGRAM_USER)

    entries = api_request(
        production_settings,
        "GET",
        "/app/v1/entries?from=2026-09-01&to=2026-09-30",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    assert entries.status == 200
    assert "entries" in response_json(entries)["data"]


def test_tampered_init_data_hash_rejected(production_settings):
    init_data = _valid_init_data()
    tampered = init_data.rsplit("hash=", 1)[0] + "hash=0000000000000000000000000000000000000000000000000000000000000000"
    response = _create_session(production_settings, init_data=tampered)
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_invalid"


def test_expired_init_data_rejected(production_settings):
    expired = _valid_init_data(auth_date=_now_timestamp() - 90000)
    response = _create_session(production_settings, init_data=expired)
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_invalid"


def test_protected_route_without_token_returns_auth_required(production_settings):
    response = api_request(production_settings, "GET", "/app/v1/profile")
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_required"


def test_delete_session_revokes_token(production_settings):
    session = _create_session(production_settings)
    token = _session_token_from_response(session)
    headers = {"Authorization": f"Bearer {token}"}

    delete_resp = api_request(
        production_settings,
        "DELETE",
        "/app/v1/session",
        headers=headers,
    )
    assert delete_resp.status == 200

    profile = api_request(production_settings, "GET", "/app/v1/profile", headers=headers)
    body = response_json(profile)
    assert profile.status == 401
    assert body["error"]["code"] == "auth_required"


def test_dev_auth_regression_when_flag_enabled():
    settings = _settings(dev_auth=True)
    response = api_request(
        settings,
        "POST",
        "/app/v1/session",
        json={"dev_user_id": API_USER},
    )
    body = response_json(response)
    assert response.status == 200
    assert body["data"]["session_token"] == f"dev:{API_USER}"


def test_allowlist_blocks_session_create(production_settings):
    settings = _settings(allowlist=frozenset({999888777}))
    response = _create_session(settings)
    body = response_json(response)
    assert response.status == 403
    assert body["error"]["code"] == "forbidden"
