import asyncio
import hashlib
import hmac
import json
import time
from unittest.mock import patch
from urllib.parse import quote

import pytest
from aiohttp.test_utils import TestClient, TestServer

from database.queries import register_user
from services.miniapp_api_settings import MiniAppApiSettings
from web_api.app import create_miniapp_api_app
from web_api.telegram_auth import (
    InitDataValidationError,
    MAX_FUTURE_CLOCK_SKEW_SECONDS,
    build_synthetic_init_data,
    validate_telegram_init_data,
    _build_data_check_string,
    _telegram_secret_key,
)

from tests.test_miniapp_api import API_USER, response_json, run

TEST_BOT_TOKEN = "7000000000:TEST_miniapp_synthetic_bot_token"
TELEGRAM_USER = 912345678
FIXED_NOW_TIMESTAMP = 1_700_000_000
INITDATA_MAX_AGE_SECONDS = 86400


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
        "initdata_max_age_seconds": INITDATA_MAX_AGE_SECONDS,
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


def _build_signed_init_data_fields(bot_token: str, fields: dict[str, str]) -> str:
    data_check_string = _build_data_check_string(fields)
    secret_key = _telegram_secret_key(bot_token)
    signed_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    signed_fields = dict(fields)
    signed_fields["hash"] = signed_hash
    return "&".join(f"{key}={value}" for key, value in signed_fields.items())


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


def test_validate_telegram_init_data_future_skew_plus_30_accepted():
    init_data = build_synthetic_init_data(
        TEST_BOT_TOKEN,
        TELEGRAM_USER,
        FIXED_NOW_TIMESTAMP + MAX_FUTURE_CLOCK_SKEW_SECONDS,
    )
    user_id, _ = validate_telegram_init_data(
        init_data,
        TEST_BOT_TOKEN,
        INITDATA_MAX_AGE_SECONDS,
        FIXED_NOW_TIMESTAMP,
    )
    assert user_id == TELEGRAM_USER


def test_validate_telegram_init_data_future_skew_plus_31_rejected():
    init_data = build_synthetic_init_data(
        TEST_BOT_TOKEN,
        TELEGRAM_USER,
        FIXED_NOW_TIMESTAMP + MAX_FUTURE_CLOCK_SKEW_SECONDS + 1,
    )
    with pytest.raises(InitDataValidationError):
        validate_telegram_init_data(
            init_data,
            TEST_BOT_TOKEN,
            INITDATA_MAX_AGE_SECONDS,
            FIXED_NOW_TIMESTAMP,
        )


def test_validate_telegram_init_data_max_age_boundary_accepted():
    auth_date = FIXED_NOW_TIMESTAMP - INITDATA_MAX_AGE_SECONDS
    init_data = build_synthetic_init_data(TEST_BOT_TOKEN, TELEGRAM_USER, auth_date)
    user_id, _ = validate_telegram_init_data(
        init_data,
        TEST_BOT_TOKEN,
        INITDATA_MAX_AGE_SECONDS,
        FIXED_NOW_TIMESTAMP,
    )
    assert user_id == TELEGRAM_USER


def test_validate_telegram_init_data_one_second_beyond_max_age_rejected():
    auth_date = FIXED_NOW_TIMESTAMP - INITDATA_MAX_AGE_SECONDS - 1
    init_data = build_synthetic_init_data(TEST_BOT_TOKEN, TELEGRAM_USER, auth_date)
    with pytest.raises(InitDataValidationError):
        validate_telegram_init_data(
            init_data,
            TEST_BOT_TOKEN,
            INITDATA_MAX_AGE_SECONDS,
            FIXED_NOW_TIMESTAMP,
        )


def test_init_data_within_clock_skew_accepted(production_settings):
    register_user(TELEGRAM_USER)
    skewed = build_synthetic_init_data(
        TEST_BOT_TOKEN,
        TELEGRAM_USER,
        FIXED_NOW_TIMESTAMP + MAX_FUTURE_CLOCK_SKEW_SECONDS,
    )
    with patch("web_api.routes.session._utc_now_timestamp", return_value=FIXED_NOW_TIMESTAMP):
        response = _create_session(production_settings, init_data=skewed)
    assert response.status == 200


def test_init_data_beyond_clock_skew_rejected(production_settings):
    beyond = build_synthetic_init_data(
        TEST_BOT_TOKEN,
        TELEGRAM_USER,
        FIXED_NOW_TIMESTAMP + MAX_FUTURE_CLOCK_SKEW_SECONDS + 1,
    )
    with patch("web_api.routes.session._utc_now_timestamp", return_value=FIXED_NOW_TIMESTAMP):
        response = _create_session(production_settings, init_data=beyond)
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_invalid"


def test_init_data_duplicate_hash_rejected_by_duplicate_field_count(production_settings):
    init_data = _valid_init_data() + "&hash=deadbeef"
    response = _create_session(production_settings, init_data=init_data)
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_invalid"


def test_init_data_duplicate_auth_date_rejected_by_duplicate_field_count(production_settings):
    init_data = _valid_init_data() + f"&auth_date={FIXED_NOW_TIMESTAMP}"
    response = _create_session(production_settings, init_data=init_data)
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_invalid"


def test_init_data_duplicate_user_rejected_by_duplicate_field_count(production_settings):
    user_json = json.dumps({"id": TELEGRAM_USER, "first_name": "Dup"}, separators=(",", ":"))
    init_data = _valid_init_data() + "&user=" + quote(user_json, safe="")
    response = _create_session(production_settings, init_data=init_data)
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_invalid"


def test_signed_init_data_malformed_user_json_rejected(production_settings):
    init_data = _build_signed_init_data_fields(
        TEST_BOT_TOKEN,
        {
            "auth_date": str(FIXED_NOW_TIMESTAMP),
            "user": "{not-json",
        },
    )
    with patch("web_api.routes.session._utc_now_timestamp", return_value=FIXED_NOW_TIMESTAMP):
        response = _create_session(production_settings, init_data=init_data)
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_invalid"


def test_validate_telegram_init_data_signed_malformed_user_json_rejected():
    init_data = _build_signed_init_data_fields(
        TEST_BOT_TOKEN,
        {
            "auth_date": str(FIXED_NOW_TIMESTAMP),
            "user": "{not-json",
        },
    )
    with pytest.raises(InitDataValidationError):
        validate_telegram_init_data(
            init_data,
            TEST_BOT_TOKEN,
            INITDATA_MAX_AGE_SECONDS,
            FIXED_NOW_TIMESTAMP,
        )


def test_init_data_signature_from_other_bot_rejected(production_settings):
    other_bot = "8000000000:OTHER_test_bot_token_for_security"
    init_data = build_synthetic_init_data(other_bot, TELEGRAM_USER, _now_timestamp())
    response = _create_session(production_settings, init_data=init_data)
    assert response.status == 401


def test_init_data_modified_payload_rejected(production_settings):
    init_data = _valid_init_data()
    tampered = init_data.replace(str(TELEGRAM_USER), str(TELEGRAM_USER + 1), 1)
    response = _create_session(production_settings, init_data=tampered)
    assert response.status == 401
