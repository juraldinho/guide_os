import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from database.db import get_connection, init_db
from database.queries import (
    get_user_profile,
    register_user,
    update_user_guide_languages,
    update_user_guide_types,
)
from web_api.dto import (
    guide_types_for_storage,
    normalize_guide_languages,
    normalize_guide_types,
)
from services.miniapp_api_settings import (
    MiniAppApiSettings,
    derive_miniapp_allowed_origin,
    normalize_miniapp_public_url,
)
from services.tour_service import TourEntryDraft, create_tour_entry, SOURCE_MINI_APP
from web_api.app import (
    CORS_ALLOWED_HEADERS,
    CORS_ALLOWED_METHODS,
    create_miniapp_api_app,
    start_miniapp_api,
)
from web_api.auth import dev_session_token

ROOT = Path(__file__).resolve().parents[1]
API_USER = 887001
PROFILE_USER_B = 887002
TEST_BOT_TOKEN = "7000000000:TEST_miniapp_synthetic_bot_token"


def run(awaitable):
    return asyncio.run(awaitable)


def _settings(dev_auth=True, **overrides):
    values = {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8083,
        "dev_auth": dev_auth,
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


async def _with_client(coro, dev_auth=True):
    app = create_miniapp_api_app(_settings(dev_auth=dev_auth))
    client = TestClient(TestServer(app))
    async with client:
        response = await coro(client)
        response._body_text = await response.text()
        return response


def response_json(response):
    return json.loads(response._body_text)


def api_request(method, path, dev_auth=True, **kwargs):
    async def _call(client):
        return await client.request(method, path, **kwargs)

    return run(_with_client(_call, dev_auth=dev_auth))


def _tour_payload(**overrides):
    payload = {
        "title": "Тур API",
        "company": "Компания",
        "location": "Самарканд",
        "startDate": "2026-09-10",
        "endDate": "2026-09-10",
        "status": "confirmed",
        "payment": "unpaid",
        "income": 150,
        "note": "note",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def seeded_user():
    register_user(API_USER)
    return API_USER


def test_health():
    response = api_request("GET", "/health")
    assert response.status == 200
    assert response_json(response) == {"status": "ok"}


def test_settings_disabled_by_default():
    settings = MiniAppApiSettings.from_env({"MINI_APP_API_ENABLED": "false"})
    assert settings.enabled is False
    assert settings.dev_auth is False


def test_start_miniapp_api_returns_none_when_disabled():
    runner = run(start_miniapp_api({"MINI_APP_API_ENABLED": "false"}))
    assert runner is None


def test_entrypoint_import_without_bot_modules():
    env = os.environ.copy()
    env.pop("BOT_TOKEN", None)
    env["PYTHONPATH"] = str(ROOT)
    script = (
        "import os, sys\n"
        "assert 'BOT_TOKEN' not in os.environ\n"
        "import guide_os_miniapp_api\n"
        "assert 'bot' not in sys.modules\n"
        "assert 'aiogram' not in sys.modules\n"
        "print('ok')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_entrypoint_module_does_not_reference_telegram_runtime():
    source = (ROOT / "guide_os_miniapp_api.py").read_text(encoding="utf-8")
    assert "BOT_TOKEN" not in source
    assert "aiogram" not in source
    assert "Dispatcher" not in source
    assert "start_polling" not in source
    assert "import bot" not in source
    assert "from bot" not in source


def test_session_dev_auth_creates_token(seeded_user):
    response = api_request(
        "POST",
        "/app/v1/session",
        json={"dev_user_id": seeded_user},
    )
    body = response_json(response)
    assert response.status == 200
    assert body["data"]["session_token"] == dev_session_token(seeded_user)
    assert body["data"]["user"]["telegram_id"] == str(seeded_user)


def test_session_rejects_invalid_init_data():
    response = api_request(
        "POST",
        "/app/v1/session",
        dev_auth=False,
        json={"init_data": "stub"},
    )
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_invalid"


def test_session_dev_user_id_rejected_when_dev_auth_off():
    response = api_request(
        "POST",
        "/app/v1/session",
        dev_auth=False,
        json={"dev_user_id": API_USER},
    )
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_invalid"


def test_auth_required_without_token():
    response = api_request("GET", "/app/v1/profile")
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_required"


def test_create_list_get_update_delete_tour(seeded_user):
    headers = _auth_headers(seeded_user)
    create = api_request(
        "POST",
        "/app/v1/tours",
        headers=headers,
        json=_tour_payload(),
    )
    create_body = response_json(create)
    assert create.status == 201
    entry = create_body["data"]
    assert entry["title"] == "Тур API"
    assert entry["startDate"] == "2026-09-10"
    entry_id = entry["id"]

    list_resp = api_request(
        "GET",
        "/app/v1/entries?from=2026-09-01&to=2026-09-30",
        headers=headers,
    )
    list_body = response_json(list_resp)
    assert list_resp.status == 200
    assert any(item["id"] == entry_id for item in list_body["data"]["entries"])

    get_resp = api_request(
        "GET",
        f"/app/v1/entries/{entry_id}",
        headers=headers,
    )
    assert get_resp.status == 200
    assert response_json(get_resp)["data"]["id"] == entry_id

    patch_resp = api_request(
        "PATCH",
        f"/app/v1/entries/{entry_id}",
        headers=headers,
        json=_tour_payload(title="Обновлён", income=200),
    )
    assert patch_resp.status == 200
    assert response_json(patch_resp)["data"]["title"] == "Обновлён"

    delete_resp = api_request(
        "DELETE",
        f"/app/v1/entries/{entry_id}",
        headers=headers,
    )
    assert delete_resp.status == 200
    assert response_json(delete_resp)["data"] == {}


def test_day_off_and_conflict(seeded_user):
    headers = _auth_headers(seeded_user)
    tour = api_request(
        "POST",
        "/app/v1/tours",
        headers=headers,
        json=_tour_payload(startDate="2026-09-15", endDate="2026-09-15"),
    )
    assert tour.status == 201

    day_off = api_request(
        "POST",
        "/app/v1/day-offs",
        headers=headers,
        json={"startDate": "2026-09-20", "endDate": "2026-09-20"},
    )
    assert day_off.status == 201
    assert response_json(day_off)["data"]["type"] == "day_off"

    conflict = api_request(
        "POST",
        "/app/v1/day-offs",
        headers=headers,
        json={"startDate": "2026-09-15", "endDate": "2026-09-15"},
    )
    conflict_body = response_json(conflict)
    assert conflict.status == 409
    assert conflict_body["error"]["code"] in ("day_off_conflict", "time_conflict", "date_warning")


def test_copy_tour_and_day_locations(seeded_user):
    headers = _auth_headers(seeded_user)
    create = api_request(
        "POST",
        "/app/v1/tours",
        headers=headers,
        json=_tour_payload(startDate="2026-10-01", endDate="2026-10-03"),
    )
    entry_id = response_json(create)["data"]["id"]

    locations = api_request(
        "PATCH",
        f"/app/v1/entries/{entry_id}/day-locations",
        headers=headers,
        json={"locations": {"2026-10-01": "Самарканд", "2026-10-02": "Бухара"}},
    )
    loc_body = response_json(locations)
    assert locations.status == 200
    assert loc_body["data"]["dayLocations"]["2026-10-02"] == "Бухара"

    copied = api_request(
        "POST",
        f"/app/v1/entries/{entry_id}/copy",
        headers=headers,
        json={"startDate": "2026-11-01", "endDate": "2026-11-03"},
    )
    copied_body = response_json(copied)
    assert copied.status == 201
    assert copied_body["data"]["startDate"] == "2026-11-01"


def test_profile_get_and_patch(seeded_user):
    headers = _auth_headers(seeded_user)
    get_resp = api_request("GET", "/app/v1/profile", headers=headers)
    assert get_resp.status == 200
    profile = response_json(get_resp)["data"]
    assert profile["telegramId"] == str(seeded_user)
    assert profile["types"] == []
    assert profile["languages"] == []

    patch_resp = api_request(
        "PATCH",
        "/app/v1/profile",
        headers=headers,
        json={"name": "Гид Тест", "notifications": {"enabled": True, "time": "20:30"}},
    )
    patch_body = response_json(patch_resp)
    assert patch_resp.status == 200
    assert patch_body["data"]["name"] == "Гид Тест"
    assert patch_body["data"]["notifications"]["time"] == "20:30"
    assert patch_body["data"]["types"] == []
    assert patch_body["data"]["languages"] == []


def _local_type(city="Самарканд"):
    return {"type": "local", "geo": [city], "allUzbekistan": False}


def _route_type(geo=None, all_uzbekistan=False):
    return {
        "type": "route",
        "geo": geo if geo is not None else ["Самарканд", "Бухара"],
        "allUzbekistan": all_uzbekistan,
    }


def _accompanying_type(geo=None, all_uzbekistan=False):
    return {
        "type": "accompanying",
        "geo": geo if geo is not None else ["Ташкент"],
        "allUzbekistan": all_uzbekistan,
    }


def _patch_profile(user_id, payload):
    return api_request(
        "PATCH",
        "/app/v1/profile",
        headers=_auth_headers(user_id),
        json=payload,
    )


def _assert_validation_error(response):
    assert response.status == 400
    assert response_json(response)["error"]["code"] == "validation_error"


def test_profile_migration_adds_json_columns():
    conn = get_connection()
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)")]
    conn.close()
    assert "guide_types_json" in columns
    assert "guide_languages_json" in columns


def test_profile_new_user_empty_defaults(seeded_user):
    response = api_request("GET", "/app/v1/profile", headers=_auth_headers(seeded_user))
    data = response_json(response)["data"]
    assert response.status == 200
    assert data["types"] == []
    assert data["languages"] == []


def test_init_db_preserves_saved_profile_json():
    user_id = 888777
    register_user(user_id)
    types = normalize_guide_types([_local_type()])
    languages = normalize_guide_languages(["Русский", "Английский"])
    update_user_guide_types(user_id, guide_types_for_storage(types))
    update_user_guide_languages(user_id, languages)
    init_db()
    profile = get_user_profile(user_id)
    assert profile is not None
    get_resp = api_request("GET", "/app/v1/profile", headers=_auth_headers(user_id))
    data = response_json(get_resp)["data"]
    assert data["types"] == types
    assert data["languages"] == languages


def test_profile_save_local_type_with_one_city(seeded_user):
    response = _patch_profile(seeded_user, {"types": [_local_type()]})
    data = response_json(response)["data"]
    assert response.status == 200
    assert data["types"] == [
        {
            "type": "local",
            "label": "Локальный гид",
            "geo": ["Самарканд"],
            "allUzbekistan": False,
        }
    ]


def test_profile_save_route_multiple_cities(seeded_user):
    response = _patch_profile(seeded_user, {"types": [_route_type()]})
    data = response_json(response)["data"]
    assert response.status == 200
    assert data["types"][0]["geo"] == ["Самарканд", "Бухара"]
    assert data["types"][0]["allUzbekistan"] is False


def test_profile_save_route_all_uzbekistan(seeded_user):
    response = _patch_profile(seeded_user, {"types": [_route_type(geo=[], all_uzbekistan=True)]})
    data = response_json(response)["data"]
    assert response.status == 200
    assert data["types"][0]["geo"] == []
    assert data["types"][0]["allUzbekistan"] is True


def test_profile_save_accompanying_type(seeded_user):
    response = _patch_profile(seeded_user, {"types": [_accompanying_type()]})
    data = response_json(response)["data"]
    assert response.status == 200
    assert data["types"][0]["type"] == "accompanying"
    assert data["types"][0]["label"] == "Сопровождающий гид"


def test_profile_save_multiple_guide_types(seeded_user):
    response = _patch_profile(
        seeded_user,
        {
            "types": [
                _local_type(),
                _route_type(geo=[], all_uzbekistan=True),
            ]
        },
    )
    data = response_json(response)["data"]
    assert response.status == 200
    assert len(data["types"]) == 2
    assert data["types"][0]["type"] == "local"
    assert data["types"][1]["type"] == "route"


def test_profile_save_multiple_languages(seeded_user):
    response = _patch_profile(
        seeded_user,
        {"languages": ["Русский", "Английский", "Узбекский"]},
    )
    data = response_json(response)["data"]
    assert response.status == 200
    assert data["languages"] == ["Русский", "Английский", "Узбекский"]


def test_profile_get_after_patch_returns_persisted_profile(seeded_user):
    _patch_profile(
        seeded_user,
        {
            "types": [_local_type("Бухара")],
            "languages": ["Французский"],
        },
    )
    get_resp = api_request("GET", "/app/v1/profile", headers=_auth_headers(seeded_user))
    data = response_json(get_resp)["data"]
    assert get_resp.status == 200
    assert data["types"][0]["geo"] == ["Бухара"]
    assert data["languages"] == ["Французский"]


def test_profile_name_patch_preserves_types_and_languages(seeded_user):
    _patch_profile(
        seeded_user,
        {
            "types": [_local_type()],
            "languages": ["Русский"],
        },
    )
    response = _patch_profile(seeded_user, {"name": "Сохранённый гид"})
    data = response_json(response)["data"]
    assert response.status == 200
    assert data["name"] == "Сохранённый гид"
    assert data["types"][0]["type"] == "local"
    assert data["languages"] == ["Русский"]


def test_profile_explicit_empty_arrays_clear_sections(seeded_user):
    _patch_profile(
        seeded_user,
        {
            "types": [_local_type()],
            "languages": ["Русский"],
        },
    )
    response = _patch_profile(seeded_user, {"types": [], "languages": []})
    data = response_json(response)["data"]
    assert response.status == 200
    assert data["types"] == []
    assert data["languages"] == []


def test_profile_corrupt_json_fail_closed_to_empty():
    user_id = 888001
    register_user(user_id)
    conn = get_connection()
    conn.execute(
        "UPDATE users SET guide_types_json = ?, guide_languages_json = ? WHERE user_id = ?",
        ("not-json", "{bad", user_id),
    )
    conn.commit()
    conn.close()
    response = api_request("GET", "/app/v1/profile", headers=_auth_headers(user_id))
    data = response_json(response)["data"]
    assert response.status == 200
    assert data["types"] == []
    assert data["languages"] == []


def test_profile_rejects_unknown_guide_type(seeded_user):
    _assert_validation_error(
        _patch_profile(seeded_user, {"types": [{"type": "unknown", "geo": ["Самарканд"]}]})
    )


def test_profile_rejects_duplicate_guide_type(seeded_user):
    _assert_validation_error(
        _patch_profile(seeded_user, {"types": [_local_type(), _local_type("Бухара")]})
    )


def test_profile_rejects_client_provided_label(seeded_user):
    _assert_validation_error(
        _patch_profile(
            seeded_user,
            {
                "types": [
                    {
                        "type": "local",
                        "label": "Fake label",
                        "geo": ["Самарканд"],
                        "allUzbekistan": False,
                    }
                ]
            },
        )
    )


def test_profile_rejects_local_without_city(seeded_user):
    _assert_validation_error(
        _patch_profile(seeded_user, {"types": [{"type": "local", "geo": [], "allUzbekistan": False}]})
    )


def test_profile_save_local_type_with_multiple_cities(seeded_user):
    response = _patch_profile(
        seeded_user,
        {"types": [{"type": "local", "geo": ["Самарканд", "Бухара"], "allUzbekistan": False}]},
    )
    data = response_json(response)["data"]
    assert response.status == 200
    assert data["types"] == [
        {
            "type": "local",
            "label": "Локальный гид",
            "geo": ["Самарканд", "Бухара"],
            "allUzbekistan": False,
        }
    ]


def test_profile_rejects_local_duplicate_geography(seeded_user):
    _assert_validation_error(
        _patch_profile(
            seeded_user,
            {
                "types": [
                    {
                        "type": "local",
                        "geo": ["Самарканд", "Самарканд"],
                        "allUzbekistan": False,
                    }
                ]
            },
        )
    )


def test_profile_rejects_local_all_uzbekistan(seeded_user):
    _assert_validation_error(
        _patch_profile(
            seeded_user,
            {"types": [{"type": "local", "geo": ["Самарканд"], "allUzbekistan": True}]},
        )
    )


def test_profile_rejects_unknown_geography(seeded_user):
    _assert_validation_error(
        _patch_profile(seeded_user, {"types": [_local_type("Нукус")]})
    )


def test_profile_rejects_duplicate_geography(seeded_user):
    _assert_validation_error(
        _patch_profile(
            seeded_user,
            {
                "types": [
                    {
                        "type": "route",
                        "geo": ["Самарканд", "Самарканд"],
                        "allUzbekistan": False,
                    }
                ]
            },
        )
    )


def test_profile_rejects_route_without_geography_or_all_uzbekistan(seeded_user):
    _assert_validation_error(
        _patch_profile(seeded_user, {"types": [{"type": "route", "geo": [], "allUzbekistan": False}]})
    )


def test_profile_rejects_all_uzbekistan_with_geography(seeded_user):
    _assert_validation_error(
        _patch_profile(
            seeded_user,
            {
                "types": [
                    {
                        "type": "route",
                        "geo": ["Самарканд"],
                        "allUzbekistan": True,
                    }
                ]
            },
        )
    )


def test_profile_rejects_non_array_types(seeded_user):
    _assert_validation_error(_patch_profile(seeded_user, {"types": "local"}))


def test_profile_rejects_non_object_type_entry(seeded_user):
    _assert_validation_error(_patch_profile(seeded_user, {"types": ["local"]}))


def test_profile_rejects_non_boolean_all_uzbekistan(seeded_user):
    _assert_validation_error(
        _patch_profile(
            seeded_user,
            {"types": [{"type": "route", "geo": [], "allUzbekistan": "yes"}]},
        )
    )


def test_profile_rejects_non_array_languages(seeded_user):
    _assert_validation_error(_patch_profile(seeded_user, {"languages": "Русский"}))


def test_profile_rejects_non_string_language(seeded_user):
    _assert_validation_error(_patch_profile(seeded_user, {"languages": [1]}))


def test_profile_rejects_blank_language(seeded_user):
    _assert_validation_error(_patch_profile(seeded_user, {"languages": ["   "]}))


def test_profile_rejects_language_longer_than_50_chars(seeded_user):
    _assert_validation_error(_patch_profile(seeded_user, {"languages": ["x" * 51]}))


def test_profile_rejects_more_than_20_languages(seeded_user):
    _assert_validation_error(
        _patch_profile(seeded_user, {"languages": [f"Lang{i}" for i in range(21)]})
    )


def test_profile_rejects_case_insensitive_duplicate_languages(seeded_user):
    _assert_validation_error(
        _patch_profile(seeded_user, {"languages": ["Русский", "русский"]})
    )


def test_profile_isolation_between_users():
    register_user(PROFILE_USER_B)
    save_a = _patch_profile(
        API_USER,
        {
            "types": [_local_type()],
            "languages": ["Русский"],
        },
    )
    assert save_a.status == 200
    get_b = api_request("GET", "/app/v1/profile", headers=_auth_headers(PROFILE_USER_B))
    data_b = response_json(get_b)["data"]
    assert get_b.status == 200
    assert data_b["types"] == []
    assert data_b["languages"] == []
    save_b = _patch_profile(
        PROFILE_USER_B,
        {
            "types": [_route_type(geo=["Ташкент"], all_uzbekistan=False)],
            "languages": ["Английский"],
        },
    )
    assert save_b.status == 200
    get_a = api_request("GET", "/app/v1/profile", headers=_auth_headers(API_USER))
    data_a = response_json(get_a)["data"]
    assert get_a.status == 200
    assert data_a["types"][0]["type"] == "local"
    assert data_a["languages"] == ["Русский"]
    assert data_a["types"][0]["geo"] == ["Самарканд"]


def test_profile_idempotency_replay(seeded_user):
    headers = _auth_headers(seeded_user)
    headers["Idempotency-Key"] = "profile-idem-1"
    payload = {"types": [_local_type()], "languages": ["Русский"]}
    first = api_request("PATCH", "/app/v1/profile", headers=headers, json=payload)
    second = api_request("PATCH", "/app/v1/profile", headers=headers, json=payload)
    assert first.status == 200
    assert second.status == 200
    assert response_json(first)["data"]["types"][0]["type"] == "local"
    assert response_json(second)["data"]["languages"] == ["Русский"]


def test_profile_notifications_update_still_works(seeded_user):
    response = _patch_profile(
        seeded_user,
        {"notifications": {"enabled": False, "time": "09:15"}},
    )
    data = response_json(response)["data"]
    assert response.status == 200
    assert data["notifications"]["enabled"] is False
    assert data["notifications"]["time"] == "09:15"


def _get_profile_data(user_id):
    response = api_request("GET", "/app/v1/profile", headers=_auth_headers(user_id))
    return response_json(response)["data"]


def _seed_profile(user_id):
    response = _patch_profile(
        user_id,
        {
            "name": "Seed Name",
            "types": [_local_type()],
            "languages": ["Русский"],
            "notifications": {"enabled": True, "time": "21:00"},
        },
    )
    assert response.status == 200
    return _get_profile_data(user_id)


def test_profile_invalid_languages_does_not_save_types(seeded_user):
    before = _seed_profile(seeded_user)
    response = _patch_profile(
        seeded_user,
        {"types": [_route_type()], "languages": [123]},
    )
    _assert_validation_error(response)
    after = _get_profile_data(seeded_user)
    assert after["types"] == before["types"]
    assert after["languages"] == before["languages"]


def test_profile_invalid_types_does_not_save_languages(seeded_user):
    before = _seed_profile(seeded_user)
    response = _patch_profile(
        seeded_user,
        {"types": [{"type": "unknown", "geo": ["Самарканд"]}], "languages": ["Английский"]},
    )
    _assert_validation_error(response)
    after = _get_profile_data(seeded_user)
    assert after["types"] == before["types"]
    assert after["languages"] == before["languages"]


def test_profile_invalid_types_does_not_change_name(seeded_user):
    before = _seed_profile(seeded_user)
    response = _patch_profile(
        seeded_user,
        {"name": "New Name", "types": "bad"},
    )
    _assert_validation_error(response)
    after = _get_profile_data(seeded_user)
    assert after["name"] == before["name"]
    assert after["types"] == before["types"]


def test_profile_invalid_notification_time_does_not_change_notifications(seeded_user):
    before = _seed_profile(seeded_user)
    response = _patch_profile(
        seeded_user,
        {"notifications": {"enabled": False, "time": "99:99"}},
    )
    _assert_validation_error(response)
    after = _get_profile_data(seeded_user)
    assert after["notifications"] == before["notifications"]


def test_profile_rejects_null_types(seeded_user):
    _assert_validation_error(_patch_profile(seeded_user, {"types": None}))


def test_profile_rejects_null_languages(seeded_user):
    _assert_validation_error(_patch_profile(seeded_user, {"languages": None}))


def test_profile_rejects_null_notifications(seeded_user):
    _assert_validation_error(_patch_profile(seeded_user, {"notifications": None}))


def test_profile_rejects_notifications_array(seeded_user):
    _assert_validation_error(_patch_profile(seeded_user, {"notifications": []}))


def test_profile_rejects_string_notifications_enabled(seeded_user):
    _assert_validation_error(
        _patch_profile(seeded_user, {"notifications": {"enabled": "false"}})
    )


def test_profile_rejects_numeric_notifications_enabled(seeded_user):
    _assert_validation_error(
        _patch_profile(seeded_user, {"notifications": {"enabled": 1}})
    )


def test_profile_rejects_invalid_notification_time_format(seeded_user):
    _assert_validation_error(
        _patch_profile(seeded_user, {"notifications": {"time": "9:00"}})
    )


def test_profile_rejects_telegram_id_mutation(seeded_user):
    _assert_validation_error(
        _patch_profile(seeded_user, {"telegramId": "another-id"})
    )


def test_profile_partial_patch_preserves_omitted_fields(seeded_user):
    seeded = _seed_profile(seeded_user)
    response = _patch_profile(seeded_user, {"name": "Only Name"})
    data = response_json(response)["data"]
    assert response.status == 200
    assert data["name"] == "Only Name"
    assert data["types"] == seeded["types"]
    assert data["languages"] == seeded["languages"]
    assert data["notifications"] == seeded["notifications"]


def test_reports_summary(seeded_user):
    headers = _auth_headers(seeded_user)
    create_tour_entry(
        API_USER,
        TourEntryDraft(
            title="Отчёт",
            company="Co",
            location="Самарканд",
            start_date="2026-09-05",
            end_date="2026-09-05",
            status="confirmed",
            payment="paid",
            income=100,
            source=SOURCE_MINI_APP,
        ),
    )
    response = api_request(
        "GET",
        "/app/v1/reports/summary?from=2026-09-01&to=2026-09-30&status=all&payment=all",
        headers=headers,
    )
    body = response_json(response)
    assert response.status == 200
    assert body["data"]["tourCount"] >= 1
    assert body["data"]["period"]["from"] == "2026-09-01"


def test_availability_preview(seeded_user):
    headers = _auth_headers(seeded_user)
    response = api_request(
        "POST",
        "/app/v1/availability/preview",
        headers=headers,
        json={"from": "2026-09-01", "to": "2026-09-30"},
    )
    body = response_json(response)
    assert response.status == 200
    assert "freeDates" in body["data"]
    assert "ranges" in body["data"]


def test_idempotency_replay_and_conflict(seeded_user):
    headers = _auth_headers(seeded_user)
    headers["Idempotency-Key"] = "idem-test-1"
    payload = _tour_payload(startDate="2026-12-01", endDate="2026-12-01")

    first = api_request("POST", "/app/v1/tours", headers=headers, json=payload)
    second = api_request("POST", "/app/v1/tours", headers=headers, json=payload)
    assert first.status == 201
    assert second.status == 201
    assert response_json(first)["data"]["id"] == response_json(second)["data"]["id"]

    conflict_headers = dict(headers)
    conflict_headers["Idempotency-Key"] = "idem-test-1"
    conflict = api_request(
        "POST",
        "/app/v1/tours",
        headers=conflict_headers,
        json=_tour_payload(startDate="2026-12-02", endDate="2026-12-02"),
    )
    conflict_body = response_json(conflict)
    assert conflict.status == 409
    assert conflict_body["error"]["code"] == "idempotency_replay"


PRODUCTION_FRONTEND_ORIGIN = "https://guide-os-miniapp.example"


def _cors_settings(**overrides):
    values = {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8083,
        "dev_auth": True,
        "bot_token": TEST_BOT_TOKEN,
        "session_ttl_seconds": 3600,
        "initdata_max_age_seconds": 86400,
        "allowlist": frozenset(),
        "allowed_origin": PRODUCTION_FRONTEND_ORIGIN,
    }
    values.update(overrides)
    return MiniAppApiSettings(**values)


def cors_request(method, path, origin=None, settings=None, **kwargs):
    headers = dict(kwargs.pop("headers", {}))
    if origin is not None:
        headers["Origin"] = origin

    app_settings = settings if settings is not None else _cors_settings()

    async def _run():
        app = create_miniapp_api_app(app_settings)
        client = TestClient(TestServer(app))
        async with client:
            response = await client.request(method, path, headers=headers, **kwargs)
            response._body_text = await response.text()
            return response

    return run(_run())


def test_cors_allowed_origin_header_on_api_request():
    response = cors_request(
        "GET",
        "/app/v1/profile",
        origin=PRODUCTION_FRONTEND_ORIGIN,
        headers=_auth_headers(),
    )
    assert response.status == 200
    assert response.headers.get("Access-Control-Allow-Origin") == PRODUCTION_FRONTEND_ORIGIN


def test_cors_vary_origin_header():
    response = cors_request(
        "GET",
        "/app/v1/profile",
        origin=PRODUCTION_FRONTEND_ORIGIN,
        headers=_auth_headers(),
    )
    assert response.headers.get("Vary") == "Origin"


def test_cors_allowed_preflight_succeeds():
    response = cors_request(
        "OPTIONS",
        "/app/v1/session",
        origin=PRODUCTION_FRONTEND_ORIGIN,
    )
    assert response.status == 200
    assert response.headers.get("Access-Control-Allow-Origin") == PRODUCTION_FRONTEND_ORIGIN


def test_cors_preflight_methods_restricted():
    response = cors_request(
        "OPTIONS",
        "/app/v1/session",
        origin=PRODUCTION_FRONTEND_ORIGIN,
    )
    assert response.headers.get("Access-Control-Allow-Methods") == CORS_ALLOWED_METHODS


def test_cors_preflight_headers_restricted():
    response = cors_request(
        "OPTIONS",
        "/app/v1/session",
        origin=PRODUCTION_FRONTEND_ORIGIN,
    )
    assert response.headers.get("Access-Control-Allow-Headers") == CORS_ALLOWED_HEADERS


def test_cors_disallowed_origin_no_allow_header():
    response = cors_request(
        "GET",
        "/app/v1/profile",
        origin="https://evil.example",
        headers=_auth_headers(),
    )
    assert response.status == 200
    assert "Access-Control-Allow-Origin" not in response.headers


def test_cors_disallowed_preflight_fails_closed():
    response = cors_request(
        "OPTIONS",
        "/app/v1/session",
        origin="https://evil.example",
    )
    assert response.status == 403
    assert "Access-Control-Allow-Origin" not in response.headers


def test_cors_no_wildcard_origin():
    response = cors_request(
        "OPTIONS",
        "/app/v1/session",
        origin="https://evil.example",
    )
    allow_origin = response.headers.get("Access-Control-Allow-Origin")
    assert allow_origin is None or allow_origin != "*"


def test_cors_request_without_origin_works(seeded_user):
    response = api_request(
        "POST",
        "/app/v1/session",
        json={"dev_user_id": seeded_user},
    )
    assert response.status == 200
    assert "Access-Control-Allow-Origin" not in response.headers


def test_health_without_origin_has_no_cors_headers():
    response = api_request("GET", "/health")
    assert response.status == 200
    assert "Access-Control-Allow-Origin" not in response.headers


def test_cors_auth_behavior_unchanged_with_allowed_origin(seeded_user):
    response = cors_request(
        "GET",
        "/app/v1/profile",
        origin=PRODUCTION_FRONTEND_ORIGIN,
    )
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_required"


def test_cors_production_http_public_url_not_allowed_origin():
    settings = MiniAppApiSettings.from_env(
        {
            "MINI_APP_API_ENABLED": "true",
            "MINI_APP_PUBLIC_URL": "http://guide-os-miniapp.example",
            "APP_ENV": "production",
            "BOT_TOKEN": TEST_BOT_TOKEN,
        }
    )
    assert settings.allowed_origin is None

    response = cors_request(
        "OPTIONS",
        "/app/v1/session",
        origin="http://guide-os-miniapp.example",
        settings=settings,
    )
    assert response.status == 403
    assert "Access-Control-Allow-Origin" not in response.headers


def test_cors_origin_derived_from_public_url_with_path():
    public_url = "https://guide-os-miniapp.example/app"
    normalized = normalize_miniapp_public_url(public_url, "production")
    assert normalized == public_url
    assert derive_miniapp_allowed_origin(normalized) == PRODUCTION_FRONTEND_ORIGIN

    settings = MiniAppApiSettings.from_env(
        {
            "MINI_APP_API_ENABLED": "true",
            "MINI_APP_PUBLIC_URL": public_url,
            "APP_ENV": "production",
            "BOT_TOKEN": TEST_BOT_TOKEN,
        }
    )
    assert settings.allowed_origin == PRODUCTION_FRONTEND_ORIGIN
