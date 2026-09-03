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
from services.guide_shop_client import (
    DisabledGuideShopClient,
    GuideShopAccessDeniedError,
    GuideShopAuthenticationError,
    GuideShopClientError,
    GuideShopObjectNotFoundError,
    GuideShopTemporarilyUnavailableError,
    InMemoryGuideShopClient,
)
from services.guide_shop_contracts import CompanyDTO
from services.guide_shop_runtime import (
    RequestScopedGuideShopUIServiceProvider,
    StaticGuideShopUIServiceProvider,
)
from services.guide_shop_ui import GuideShopUIService
from services.tour_service import TourEntryDraft, create_tour_entry, SOURCE_MINI_APP
from types import SimpleNamespace
from web_api.app import (
    CORS_ALLOWED_HEADERS,
    CORS_ALLOWED_METHODS,
    create_miniapp_api_app,
    register_miniapp_api_on_app,
    start_miniapp_api,
)
from web_api.auth import dev_session_token
from web_api.routes.guideshop_companies import configure_miniapp_guideshop_provider

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


def _assert_not_found(response):
    assert response.status == 404
    assert response_json(response)["error"]["code"] == "not_found"


def _place_payload(**overrides):
    payload = {
        "name": "Company name",
        "category": None,
        "generalLocation": None,
        "landmark": None,
        "note": None,
    }
    payload.update(overrides)
    return payload


def _post_place(user_id, payload=None, **header_overrides):
    return api_request(
        "POST",
        "/app/v1/personal-places",
        headers=_auth_headers(user_id, **header_overrides),
        json=payload if payload is not None else _place_payload(),
    )


def _put_place(user_id, place_id, payload=None, **header_overrides):
    return api_request(
        "PUT",
        f"/app/v1/personal-places/{place_id}",
        headers=_auth_headers(user_id, **header_overrides),
        json=payload if payload is not None else _place_payload(),
    )


def _get_place(user_id, place_id):
    return api_request(
        "GET",
        f"/app/v1/personal-places/{place_id}",
        headers=_auth_headers(user_id),
    )


def _list_places(user_id, query=""):
    return api_request(
        "GET",
        f"/app/v1/personal-places{query}",
        headers=_auth_headers(user_id),
    )


def _deactivate_place(user_id, place_id, **header_overrides):
    headers = _auth_headers(user_id, **header_overrides)
    return api_request(
        "POST",
        f"/app/v1/personal-places/{place_id}/deactivate",
        headers=headers,
    )


def _create_place_for_user(user_id):
    response = _post_place(user_id)
    body = response_json(response)
    assert response.status == 201
    return body["data"]["id"]


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


def _commission_reports(user_id, query, **header_overrides):
    return api_request(
        "GET",
        f"/app/v1/reports/commissions{query}",
        headers=_auth_headers(user_id, **header_overrides),
    )


def test_commission_reports_route_registered_once():
    app = create_miniapp_api_app(_settings())
    routes = [
        (route.method, route.resource.canonical)
        for route in app.router.routes()
    ]
    assert routes.count(("GET", "/app/v1/reports/commissions")) == 1
    assert routes.count(("GET", "/app/v1/reports/summary")) == 1


def test_commission_reports_auth_required():
    response = api_request("GET", "/app/v1/reports/commissions?from=2026-09-01&to=2026-09-30")
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_required"


def test_commission_reports_empty_and_camel_case(seeded_user):
    response = _commission_reports(seeded_user, "?from=2026-08-01&to=2026-08-31")
    body = response_json(response)
    assert response.status == 200
    assert body["data"] == {
        "totalCommission": 0,
        "recordCount": 0,
        "byCompany": [],
        "period": {"from": "2026-08-01", "to": "2026-08-31"},
    }


def test_commission_reports_multi_company_breakdown(seeded_user):
    register_user(PROFILE_USER_B)
    place_a = _create_place_for_user(seeded_user)
    place_b_resp = _post_place(
        seeded_user,
        _place_payload(name="Company B"),
    )
    place_b = response_json(place_b_resp)["data"]["id"]
    _create_commission_for_user(
        seeded_user,
        place_a,
        occurredAt="2026-08-05T12:00:00+05:00",
        receivedPoints=25,
        purchaseAmountMinor=None,
        receivedIncomeMinor=None,
        currency=None,
        note=None,
    )
    _create_commission_for_user(
        seeded_user,
        place_a,
        occurredAt="2026-08-06T12:00:00+05:00",
        receivedPoints=30,
        purchaseAmountMinor=None,
        receivedIncomeMinor=None,
        currency=None,
    )
    _create_commission_for_user(
        seeded_user,
        place_b,
        occurredAt="2026-08-07T12:00:00+05:00",
        receivedPoints=30,
        purchaseAmountMinor=None,
        receivedIncomeMinor=None,
        currency=None,
    )
    foreign_place = _create_place_for_user(PROFILE_USER_B)
    _create_commission_for_user(
        PROFILE_USER_B,
        foreign_place,
        occurredAt="2026-08-05T12:00:00+05:00",
        receivedPoints=999,
        purchaseAmountMinor=None,
        receivedIncomeMinor=None,
        currency=None,
    )

    response = _commission_reports(seeded_user, "?from=2026-08-01&to=2026-08-31")
    body = response_json(response)
    assert response.status == 200
    data = body["data"]
    assert data["totalCommission"] == 85
    assert data["recordCount"] == 3
    assert data["period"] == {"from": "2026-08-01", "to": "2026-08-31"}
    assert len(data["byCompany"]) == 2
    assert data["byCompany"][0]["totalCommission"] == 55
    assert data["byCompany"][0]["recordCount"] == 2
    assert data["byCompany"][0]["placeId"] == place_a
    assert "userId" not in data
    assert "purchaseAmountMinor" not in str(body)
    assert "receivedIncomeMinor" not in str(body)
    assert "999" not in str(data)


def test_commission_reports_validation_errors(seeded_user):
    cases = [
        "?to=2026-08-31",
        "?from=2026-08-01",
        "?from=2026-08-01&from=2026-08-02&to=2026-08-31",
        "?from=2026-08-01&to=2026-08-31&to=2026-08-29",
        "?from=2026-13-01&to=2026-08-31",
        "?from=2026-08-31&to=2026-08-01",
        "?from=2026-08-01&to=2026-08-31&userId=1",
        "?from=2026-08-01&to=2026-08-31&status=all",
        "?from=2026-08-01&to=2026-08-31&payment=paid",
        "?from=2026-08-01&to=2026-08-31&company=X",
        "?from=2026-08-01&to=2026-08-31&location=Y",
    ]
    for query in cases:
        response = _commission_reports(seeded_user, query)
        _assert_validation_error(response)
        assert response.status != 500


def test_commission_reports_inactive_legacy_and_deactivated_company(seeded_user):
    place_id, commission_id = _create_commission_for_user(
        seeded_user,
        occurredAt="2026-08-10T12:00:00+05:00",
        receivedPoints=11,
        purchaseAmountMinor=None,
        receivedIncomeMinor=None,
        currency=None,
    )
    _deactivate_commission(seeded_user, commission_id)
    _post_commission(
        seeded_user,
        place_id,
        {
            "occurredAt": "2026-08-11T12:00:00+05:00",
            "purchaseAmountMinor": 10000,
            "receivedIncomeMinor": 1000,
            "receivedPoints": None,
            "currency": "USD",
            "note": None,
        },
    )
    historical = _create_place_for_user(seeded_user)
    _put_place(seeded_user, historical, _place_payload(name="Hist Co"))
    _create_commission_for_user(
        seeded_user,
        historical,
        occurredAt="2026-08-12T12:00:00+05:00",
        receivedPoints=17,
        purchaseAmountMinor=None,
        receivedIncomeMinor=None,
        currency=None,
    )
    _deactivate_place(seeded_user, historical)

    response = _commission_reports(seeded_user, "?from=2026-08-01&to=2026-08-31")
    body = response_json(response)
    assert response.status == 200
    assert body["data"]["totalCommission"] == 17
    assert body["data"]["recordCount"] == 1
    assert body["data"]["byCompany"][0]["companyName"] == "Hist Co"


def test_commission_reports_script_name_remains_inert_json(seeded_user):
    place_resp = _post_place(
        seeded_user,
        _place_payload(name="<script>alert(1)</script>"),
    )
    place_id = response_json(place_resp)["data"]["id"]
    _create_commission_for_user(
        seeded_user,
        place_id,
        occurredAt="2026-08-15T12:00:00+05:00",
        receivedPoints=3,
        purchaseAmountMinor=None,
        receivedIncomeMinor=None,
        currency=None,
    )
    response = _commission_reports(seeded_user, "?from=2026-08-01&to=2026-08-31")
    body = response_json(response)
    assert response.status == 200
    assert body["data"]["byCompany"][0]["companyName"] == "<script>alert(1)</script>"
    assert "<script>" in response._body_text


def test_commission_reports_preserves_existing_tour_summary(seeded_user):
    headers = _auth_headers(seeded_user)
    create_tour_entry(
        API_USER,
        TourEntryDraft(
            title="Tour stays",
            company="Co",
            location="Самарканд",
            start_date="2026-08-20",
            end_date="2026-08-20",
            status="confirmed",
            payment="paid",
            income=100,
            source=SOURCE_MINI_APP,
        ),
    )
    tour_response = api_request(
        "GET",
        "/app/v1/reports/summary?from=2026-08-01&to=2026-08-31&status=all&payment=all",
        headers=headers,
    )
    assert tour_response.status == 200
    assert response_json(tour_response)["data"]["tourCount"] >= 1


def test_commission_reports_cors_and_auth_apply():
    response = cors_request(
        "GET",
        "/app/v1/reports/commissions?from=2026-08-01&to=2026-08-31",
        origin=PRODUCTION_FRONTEND_ORIGIN,
    )
    assert response.status == 401
    assert response.headers.get("Access-Control-Allow-Origin") == PRODUCTION_FRONTEND_ORIGIN


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


def test_personal_places_routes_registered_on_miniapp_app():
    from aiohttp import web

    app = web.Application()
    register_miniapp_api_on_app(app, _settings())
    routes = {(route.method, route.resource.canonical) for route in app.router.routes()}
    assert ("GET", "/app/v1/personal-places") in routes
    assert ("POST", "/app/v1/personal-places") in routes
    assert ("GET", "/app/v1/personal-places/{placeId}") in routes
    assert ("PUT", "/app/v1/personal-places/{placeId}") in routes
    assert ("POST", "/app/v1/personal-places/{placeId}/deactivate") in routes


def test_personal_places_auth_required_for_all_endpoints():
    place_id = "place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    endpoints = [
        ("GET", "/app/v1/personal-places"),
        ("POST", "/app/v1/personal-places", {"json": _place_payload()}),
        ("GET", f"/app/v1/personal-places/{place_id}"),
        ("PUT", f"/app/v1/personal-places/{place_id}", {"json": _place_payload()}),
        ("POST", f"/app/v1/personal-places/{place_id}/deactivate"),
    ]
    for method, path, *extra in endpoints:
        kwargs = extra[0] if extra else {}
        response = api_request(method, path, **kwargs)
        body = response_json(response)
        assert response.status == 401
        assert body["error"]["code"] == "auth_required"


def test_personal_places_create_rejects_owner_override(seeded_user):
    _assert_validation_error(
        _post_place(seeded_user, {"name": "X", "userId": PROFILE_USER_B})
    )


def test_personal_places_list_empty(seeded_user):
    response = _list_places(seeded_user)
    body = response_json(response)
    assert response.status == 200
    assert body["data"]["places"] == []


def test_personal_places_list_active_only_by_default(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    _deactivate_place(seeded_user, place_id)
    body = response_json(_list_places(seeded_user))
    assert body["data"]["places"] == []


def test_personal_places_list_include_inactive_true(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    _deactivate_place(seeded_user, place_id)
    body = response_json(_list_places(seeded_user, "?includeInactive=true"))
    assert len(body["data"]["places"]) == 1
    assert body["data"]["places"][0]["id"] == place_id
    assert body["data"]["places"][0]["status"] == "inactive"


def test_personal_places_list_include_inactive_false(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    body = response_json(_list_places(seeded_user, "?includeInactive=false"))
    assert len(body["data"]["places"]) == 1
    assert body["data"]["places"][0]["id"] == place_id


def test_personal_places_list_rejects_invalid_include_inactive(seeded_user):
    _assert_validation_error(_list_places(seeded_user, "?includeInactive=yes"))
    _assert_validation_error(
        _list_places(seeded_user, "?includeInactive=true&includeInactive=false")
    )


def test_personal_places_get_returns_camel_case_dto(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    response = _get_place(seeded_user, place_id)
    body = response_json(response)
    assert response.status == 200
    place = body["data"]
    assert place["id"] == place_id
    assert place["name"] == "Company name"
    assert place["category"] is None
    assert place["generalLocation"] is None
    assert place["landmark"] is None
    assert place["note"] is None
    assert place["status"] == "active"
    assert "createdAt" in place
    assert "updatedAt" in place
    assert "user_id" not in place
    assert "userId" not in place


def test_personal_places_get_foreign_id_not_found(seeded_user):
    register_user(PROFILE_USER_B)
    foreign_id = _create_place_for_user(PROFILE_USER_B)
    _assert_not_found(_get_place(seeded_user, foreign_id))


def test_personal_places_get_malformed_id_not_found(seeded_user):
    _assert_not_found(_get_place(seeded_user, "place_invalid"))


def test_personal_places_create_full_payload(seeded_user):
    response = _post_place(
        seeded_user,
        {
            "name": "Full place",
            "category": "shop",
            "generalLocation": "district",
            "landmark": "landmark",
            "note": "note",
        },
    )
    body = response_json(response)
    assert response.status == 201
    assert body["data"]["name"] == "Full place"
    assert body["data"]["category"] == "shop"
    assert body["data"]["generalLocation"] == "district"
    assert body["data"]["landmark"] == "landmark"
    assert body["data"]["note"] == "note"


def test_personal_places_create_minimal_payload(seeded_user):
    response = _post_place(seeded_user, {"name": "Minimal"})
    body = response_json(response)
    assert response.status == 201
    assert body["data"]["name"] == "Minimal"
    assert body["data"]["category"] is None


def test_personal_places_create_trims_and_preserves_limits(seeded_user):
    response = _post_place(
        seeded_user,
        {
            "name": "  Trimmed name  ",
            "category": "  cat  ",
            "generalLocation": "  loc  ",
            "landmark": "  mark  ",
            "note": "  note  ",
        },
    )
    body = response_json(response)
    assert response.status == 201
    assert body["data"]["name"] == "Trimmed name"
    assert body["data"]["category"] == "cat"


def test_personal_places_create_rejects_missing_name(seeded_user):
    _assert_validation_error(_post_place(seeded_user, {"category": "shop"}))


def test_personal_places_create_rejects_empty_name(seeded_user):
    _assert_validation_error(_post_place(seeded_user, {"name": "   "}))


def test_personal_places_create_rejects_too_long_name(seeded_user):
    _assert_validation_error(_post_place(seeded_user, {"name": "x" * 101}))


def test_personal_places_create_rejects_invalid_optional_types(seeded_user):
    _assert_validation_error(_post_place(seeded_user, {"name": "X", "category": 1}))
    _assert_validation_error(_post_place(seeded_user, {"name": "X", "note": []}))


def test_personal_places_create_rejects_too_long_optional_fields(seeded_user):
    _assert_validation_error(_post_place(seeded_user, {"name": "X", "category": "x" * 101}))
    _assert_validation_error(
        _post_place(seeded_user, {"name": "X", "generalLocation": "x" * 201})
    )
    _assert_validation_error(_post_place(seeded_user, {"name": "X", "note": "x" * 501}))


def test_personal_places_create_rejects_server_owned_keys(seeded_user):
    _assert_validation_error(_post_place(seeded_user, {"name": "X", "id": "place_fake"}))
    _assert_validation_error(_post_place(seeded_user, {"name": "X", "status": "active"}))


def test_personal_places_create_response_never_contains_user_id(seeded_user):
    response = _post_place(seeded_user)
    serialized = response._body_text
    assert "user_id" not in serialized
    assert "userId" not in serialized


def test_personal_places_update_full_replacement(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    response = _put_place(
        seeded_user,
        place_id,
        {
            "name": "Updated",
            "category": "new",
            "generalLocation": "new loc",
            "landmark": "new mark",
            "note": "new note",
        },
    )
    body = response_json(response)
    assert response.status == 200
    assert body["data"]["name"] == "Updated"
    assert body["data"]["category"] == "new"
    assert body["data"]["generalLocation"] == "new loc"


def test_personal_places_update_omitted_optionals_become_null(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    response = _put_place(seeded_user, place_id, {"name": "Only name"})
    body = response_json(response)
    assert response.status == 200
    assert body["data"]["name"] == "Only name"
    assert body["data"]["category"] is None
    assert body["data"]["generalLocation"] is None
    assert body["data"]["landmark"] is None
    assert body["data"]["note"] is None


def test_personal_places_update_validation_failure_no_partial_write(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    _assert_validation_error(_put_place(seeded_user, place_id, {"name": ""}))
    body = response_json(_get_place(seeded_user, place_id))
    assert body["data"]["name"] == "Company name"


def test_personal_places_update_foreign_malformed_inactive_not_found(seeded_user):
    register_user(PROFILE_USER_B)
    foreign_id = _create_place_for_user(PROFILE_USER_B)
    _assert_not_found(_put_place(seeded_user, foreign_id, {"name": "Hack"}))
    _assert_not_found(_put_place(seeded_user, "place_badid", {"name": "Hack"}))
    own_id = _create_place_for_user(seeded_user)
    _deactivate_place(seeded_user, own_id)
    _assert_not_found(_put_place(seeded_user, own_id, {"name": "Again"}))


def test_personal_places_deactivate_soft_delete(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    response = _deactivate_place(seeded_user, place_id)
    assert response.status == 200
    assert response_json(response)["data"] == {}
    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM personal_places WHERE public_id = ?",
        (place_id,),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["status"] == "inactive"


def test_personal_places_deactivate_hidden_from_default_list(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    _deactivate_place(seeded_user, place_id)
    assert response_json(_list_places(seeded_user))["data"]["places"] == []


def test_personal_places_deactivate_visible_with_include_inactive(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    _deactivate_place(seeded_user, place_id)
    places = response_json(_list_places(seeded_user, "?includeInactive=true"))["data"]["places"]
    assert any(item["id"] == place_id and item["status"] == "inactive" for item in places)


def test_personal_places_deactivate_repeat_without_idempotency_not_found(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    assert _deactivate_place(seeded_user, place_id).status == 200
    _assert_not_found(_deactivate_place(seeded_user, place_id))


def test_personal_places_deactivate_foreign_not_found(seeded_user):
    register_user(PROFILE_USER_B)
    foreign_id = _create_place_for_user(PROFILE_USER_B)
    _assert_not_found(_deactivate_place(seeded_user, foreign_id))


def test_personal_places_deactivate_rejects_non_empty_body(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    response = api_request(
        "POST",
        f"/app/v1/personal-places/{place_id}/deactivate",
        headers=_auth_headers(seeded_user),
        data=b"{}",
    )
    _assert_validation_error(response)
    body = response_json(_get_place(seeded_user, place_id))
    assert body["data"]["status"] == "active"


def test_personal_places_create_idempotency_replay(seeded_user):
    first = _post_place(seeded_user, **{"Idempotency-Key": "place-create-1"})
    second = _post_place(seeded_user, **{"Idempotency-Key": "place-create-1"})
    assert first.status == 201
    assert second.status == 201
    first_id = response_json(first)["data"]["id"]
    assert response_json(second)["data"]["id"] == first_id
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM personal_places WHERE user_id = ?",
        (seeded_user,),
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_personal_places_update_idempotency_replay(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    payload = {"name": "Replay name"}
    first = _put_place(
        seeded_user,
        place_id,
        payload,
        **{"Idempotency-Key": "place-update-1"},
    )
    second = _put_place(
        seeded_user,
        place_id,
        payload,
        **{"Idempotency-Key": "place-update-1"},
    )
    assert first.status == 200
    assert second.status == 200
    assert response_json(first)["data"]["name"] == "Replay name"
    assert response_json(second)["data"]["name"] == "Replay name"


def test_personal_places_deactivate_idempotency_replay(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    first = _deactivate_place(
        seeded_user,
        place_id,
        **{"Idempotency-Key": "place-deactivate-1"},
    )
    second = _deactivate_place(
        seeded_user,
        place_id,
        **{"Idempotency-Key": "place-deactivate-1"},
    )
    assert first.status == 200
    assert second.status == 200
    assert response_json(first)["data"] == {}
    assert response_json(second)["data"] == {}


def test_personal_places_idempotency_replay_conflict(seeded_user):
    first = _post_place(
        seeded_user,
        {"name": "First"},
        **{"Idempotency-Key": "place-conflict-1"},
    )
    assert first.status == 201
    conflict = _post_place(
        seeded_user,
        {"name": "Second"},
        **{"Idempotency-Key": "place-conflict-1"},
    )
    body = response_json(conflict)
    assert conflict.status == 409
    assert body["error"]["code"] == "idempotency_replay"


def test_personal_places_idempotency_isolated_between_users(seeded_user):
    register_user(PROFILE_USER_B)
    first = _post_place(
        seeded_user,
        {"name": "User A"},
        **{"Idempotency-Key": "shared-place-key"},
    )
    second = _post_place(
        PROFILE_USER_B,
        {"name": "User B"},
        **{"Idempotency-Key": "shared-place-key"},
    )
    assert first.status == 201
    assert second.status == 201
    assert response_json(first)["data"]["id"] != response_json(second)["data"]["id"]


def test_cors_preflight_allows_put_method():
    response = cors_request(
        "OPTIONS",
        "/app/v1/personal-places",
        origin=PRODUCTION_FRONTEND_ORIGIN,
    )
    assert response.status == 200
    assert "PUT" in response.headers.get("Access-Control-Allow-Methods", "")


COMMISSION_OCCURRED_AT = "2026-08-15T10:00:00+05:00"
COMMISSION_OCCURRED_AT_UTC = "2026-08-15T05:00:00Z"


def _commission_payload(**overrides):
    payload = {
        "occurredAt": COMMISSION_OCCURRED_AT,
        "purchaseAmountMinor": 10000,
        "receivedIncomeMinor": 1000,
        "receivedPoints": 5,
        "currency": "USD",
        "note": "Optional note",
    }
    payload.update(overrides)
    return payload


def _post_commission(user_id, place_id, payload=None, **header_overrides):
    return api_request(
        "POST",
        f"/app/v1/personal-places/{place_id}/commissions",
        headers=_auth_headers(user_id, **header_overrides),
        json=payload if payload is not None else _commission_payload(),
    )


def _list_commissions(user_id, place_id, query=""):
    return api_request(
        "GET",
        f"/app/v1/personal-places/{place_id}/commissions{query}",
        headers=_auth_headers(user_id),
    )


def _get_commission(user_id, commission_id):
    return api_request(
        "GET",
        f"/app/v1/personal-commissions/{commission_id}",
        headers=_auth_headers(user_id),
    )


def _put_commission(user_id, commission_id, payload=None, **header_overrides):
    return api_request(
        "PUT",
        f"/app/v1/personal-commissions/{commission_id}",
        headers=_auth_headers(user_id, **header_overrides),
        json=payload if payload is not None else _commission_payload(),
    )


def _deactivate_commission(user_id, commission_id, **header_overrides):
    return api_request(
        "POST",
        f"/app/v1/personal-commissions/{commission_id}/deactivate",
        headers=_auth_headers(user_id, **header_overrides),
    )


def _create_commission_for_user(user_id, place_id=None, **payload_overrides):
    if place_id is None:
        place_id = _create_place_for_user(user_id)
    response = _post_commission(user_id, place_id, _commission_payload(**payload_overrides))
    body = response_json(response)
    assert response.status == 201, body
    return place_id, body["data"]["id"]


def _assert_personal_commission_routes(app):
    routes = {(route.method, route.resource.canonical) for route in app.router.routes()}
    assert ("GET", "/app/v1/personal-places/{placeId}/commissions") in routes
    assert ("POST", "/app/v1/personal-places/{placeId}/commissions") in routes
    assert ("GET", "/app/v1/personal-commissions/{commissionId}") in routes
    assert ("PUT", "/app/v1/personal-commissions/{commissionId}") in routes
    assert ("POST", "/app/v1/personal-commissions/{commissionId}/deactivate") in routes


def test_personal_commissions_routes_registered_on_create_miniapp_api_app():
    _assert_personal_commission_routes(create_miniapp_api_app(_settings()))


def test_personal_commissions_routes_registered_on_miniapp_app():
    from aiohttp import web

    app = web.Application()
    register_miniapp_api_on_app(app, _settings())
    _assert_personal_commission_routes(app)


def test_personal_commissions_auth_required_for_all_endpoints():
    place_id = "place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    commission_id = "entry_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    endpoints = [
        ("GET", f"/app/v1/personal-places/{place_id}/commissions"),
        (
            "POST",
            f"/app/v1/personal-places/{place_id}/commissions",
            {"json": _commission_payload()},
        ),
        ("GET", f"/app/v1/personal-commissions/{commission_id}"),
        (
            "PUT",
            f"/app/v1/personal-commissions/{commission_id}",
            {"json": _commission_payload()},
        ),
        ("POST", f"/app/v1/personal-commissions/{commission_id}/deactivate"),
    ]
    for method, path, *extra in endpoints:
        kwargs = extra[0] if extra else {}
        response = api_request(method, path, **kwargs)
        body = response_json(response)
        assert response.status == 401
        assert body["error"]["code"] == "auth_required"


def test_personal_commissions_create_rejects_owner_override(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    _assert_validation_error(
        _post_commission(
            seeded_user,
            place_id,
            _commission_payload(userId=PROFILE_USER_B, receivedPoints=1, purchaseAmountMinor=None, receivedIncomeMinor=None, currency=None),
        )
    )


def test_personal_commissions_list_empty(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    response = _list_commissions(seeded_user, place_id)
    body = response_json(response)
    assert response.status == 200
    assert body["data"]["commissions"] == []


def test_personal_commissions_list_active_only_by_default(seeded_user):
    place_id, commission_id = _create_commission_for_user(seeded_user)
    _deactivate_commission(seeded_user, commission_id)
    body = response_json(_list_commissions(seeded_user, place_id))
    assert body["data"]["commissions"] == []


def test_personal_commissions_list_include_inactive_true(seeded_user):
    place_id, commission_id = _create_commission_for_user(seeded_user)
    _deactivate_commission(seeded_user, commission_id)
    body = response_json(_list_commissions(seeded_user, place_id, "?includeInactive=true"))
    assert len(body["data"]["commissions"]) == 1
    assert body["data"]["commissions"][0]["id"] == commission_id
    assert body["data"]["commissions"][0]["status"] == "inactive"


def test_personal_commissions_list_include_inactive_false(seeded_user):
    place_id, commission_id = _create_commission_for_user(seeded_user)
    body = response_json(_list_commissions(seeded_user, place_id, "?includeInactive=false"))
    assert len(body["data"]["commissions"]) == 1
    assert body["data"]["commissions"][0]["id"] == commission_id


def test_personal_commissions_list_rejects_invalid_include_inactive(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    _assert_validation_error(_list_commissions(seeded_user, place_id, "?includeInactive=yes"))
    _assert_validation_error(
        _list_commissions(seeded_user, place_id, "?includeInactive=true&includeInactive=false")
    )


def test_personal_commissions_get_returns_camel_case_dto(seeded_user):
    place_id, commission_id = _create_commission_for_user(seeded_user)
    response = _get_commission(seeded_user, commission_id)
    body = response_json(response)
    assert response.status == 200
    item = body["data"]
    assert item["id"] == commission_id
    assert item["placeId"] == place_id
    assert item["occurredAt"] == COMMISSION_OCCURRED_AT_UTC
    assert item["purchaseAmountMinor"] == 10000
    assert item["receivedIncomeMinor"] == 1000
    assert item["receivedPoints"] == 5
    assert item["currency"] == "USD"
    assert item["note"] == "Optional note"
    assert item["status"] == "active"
    assert "createdAt" in item
    assert "updatedAt" in item
    assert "user_id" not in item
    assert "userId" not in item


def test_personal_commissions_owner_can_read_inactive(seeded_user):
    _, commission_id = _create_commission_for_user(seeded_user)
    _deactivate_commission(seeded_user, commission_id)
    response = _get_commission(seeded_user, commission_id)
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "inactive"


def test_personal_commissions_get_foreign_and_malformed_not_found(seeded_user):
    register_user(PROFILE_USER_B)
    _, foreign_id = _create_commission_for_user(PROFILE_USER_B)
    _assert_not_found(_get_commission(seeded_user, foreign_id))
    _assert_not_found(_get_commission(seeded_user, "entry_invalid"))
    _assert_not_found(_get_commission(seeded_user, "not-an-id"))


def test_personal_commissions_list_foreign_or_malformed_parent_not_found(seeded_user):
    register_user(PROFILE_USER_B)
    foreign_place = _create_place_for_user(PROFILE_USER_B)
    _assert_not_found(_list_commissions(seeded_user, foreign_place))
    _assert_not_found(_list_commissions(seeded_user, "place_bad"))


def test_personal_commissions_create_full_payload(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    response = _post_commission(seeded_user, place_id)
    body = response_json(response)
    assert response.status == 201
    assert body["data"]["placeId"] == place_id
    assert body["data"]["occurredAt"] == COMMISSION_OCCURRED_AT_UTC
    assert body["data"]["currency"] == "USD"


def test_personal_commissions_create_points_only(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    response = _post_commission(
        seeded_user,
        place_id,
        {
            "occurredAt": COMMISSION_OCCURRED_AT,
            "receivedPoints": 3,
        },
    )
    body = response_json(response)
    assert response.status == 201
    assert body["data"]["receivedPoints"] == 3
    assert body["data"]["currency"] is None
    assert body["data"]["purchaseAmountMinor"] is None


def test_personal_commissions_create_income_only_with_currency(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    response = _post_commission(
        seeded_user,
        place_id,
        {
            "occurredAt": COMMISSION_OCCURRED_AT,
            "receivedIncomeMinor": 500,
            "currency": "uzs",
        },
    )
    body = response_json(response)
    assert response.status == 201
    assert body["data"]["receivedIncomeMinor"] == 500
    assert body["data"]["currency"] == "UZS"


def test_personal_commissions_create_purchase_only_with_currency(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    response = _post_commission(
        seeded_user,
        place_id,
        {
            "occurredAt": COMMISSION_OCCURRED_AT,
            "purchaseAmountMinor": 2500,
            "currency": "USD",
        },
    )
    body = response_json(response)
    assert response.status == 201
    assert body["data"]["purchaseAmountMinor"] == 2500
    assert body["data"]["currency"] == "USD"


def test_personal_commissions_create_rejects_invalid_timestamps(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    for bad in ("2026-09-02", "2026-09-02T00:00:00", "invalid", None, 123):
        payload = _commission_payload(receivedPoints=1, purchaseAmountMinor=None, receivedIncomeMinor=None, currency=None)
        payload["occurredAt"] = bad
        _assert_validation_error(_post_commission(seeded_user, place_id, payload))


def test_personal_commissions_create_rejects_future_timestamp(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    _assert_validation_error(
        _post_commission(
            seeded_user,
            place_id,
            {
                "occurredAt": "2099-01-01T00:00:00Z",
                "receivedPoints": 1,
            },
        )
    )


def test_personal_commissions_create_rejects_invalid_money_and_points(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    for field, value in (
        ("purchaseAmountMinor", True),
        ("purchaseAmountMinor", 1.5),
        ("purchaseAmountMinor", "10"),
        ("purchaseAmountMinor", []),
        ("receivedIncomeMinor", {}),
        ("receivedPoints", 0),
        ("receivedPoints", -1),
        ("receivedPoints", True),
        ("receivedPoints", "5"),
    ):
        payload = _commission_payload(receivedPoints=1, purchaseAmountMinor=None, receivedIncomeMinor=None, currency=None)
        payload[field] = value
        _assert_validation_error(_post_commission(seeded_user, place_id, payload))


def test_personal_commissions_create_rejects_currency_and_empty_outcome(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    _assert_validation_error(
        _post_commission(
            seeded_user,
            place_id,
            {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 1, "currency": "USD"},
        )
    )
    _assert_validation_error(
        _post_commission(
            seeded_user,
            place_id,
            {"occurredAt": COMMISSION_OCCURRED_AT, "purchaseAmountMinor": 10},
        )
    )
    _assert_validation_error(
        _post_commission(
            seeded_user,
            place_id,
            {"occurredAt": COMMISSION_OCCURRED_AT, "purchaseAmountMinor": 10, "currency": "ZZZ"},
        )
    )
    _assert_validation_error(
        _post_commission(
            seeded_user,
            place_id,
            {"occurredAt": COMMISSION_OCCURRED_AT},
        )
    )


def test_personal_commissions_create_rejects_note_limit_and_server_keys(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    _assert_validation_error(
        _post_commission(
            seeded_user,
            place_id,
            {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 1, "note": "x" * 501},
        )
    )
    _assert_validation_error(
        _post_commission(
            seeded_user,
            place_id,
            _commission_payload(id="entry_fake", receivedPoints=1, purchaseAmountMinor=None, receivedIncomeMinor=None, currency=None),
        )
    )
    _assert_validation_error(
        _post_commission(
            seeded_user,
            place_id,
            _commission_payload(placeId=place_id, receivedPoints=1, purchaseAmountMinor=None, receivedIncomeMinor=None, currency=None),
        )
    )


def test_personal_commissions_create_inactive_missing_foreign_parent_not_found(seeded_user):
    register_user(PROFILE_USER_B)
    place_id = _create_place_for_user(seeded_user)
    _deactivate_place(seeded_user, place_id)
    _assert_not_found(
        _post_commission(
            seeded_user,
            place_id,
            {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 1},
        )
    )
    foreign_place = _create_place_for_user(PROFILE_USER_B)
    _assert_not_found(
        _post_commission(
            seeded_user,
            foreign_place,
            {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 1},
        )
    )
    _assert_not_found(
        _post_commission(
            seeded_user,
            "place_not_a_valid_hex_place_id_here",
            {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 1},
        )
    )


def test_personal_commissions_create_response_never_contains_user_id(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    response = _post_commission(
        seeded_user,
        place_id,
        {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 1},
    )
    assert "user_id" not in response._body_text
    assert "userId" not in response._body_text


def test_personal_commissions_update_full_replacement(seeded_user):
    place_id, commission_id = _create_commission_for_user(seeded_user)
    response = _put_commission(
        seeded_user,
        commission_id,
        {
            "occurredAt": COMMISSION_OCCURRED_AT,
            "receivedPoints": 9,
            "note": "Updated",
        },
    )
    body = response_json(response)
    assert response.status == 200
    assert body["data"]["receivedPoints"] == 9
    assert body["data"]["note"] == "Updated"
    assert body["data"]["purchaseAmountMinor"] is None
    assert body["data"]["currency"] is None
    assert body["data"]["placeId"] == place_id


def test_personal_commissions_update_validation_failure_no_partial_write(seeded_user):
    _, commission_id = _create_commission_for_user(seeded_user)
    before = response_json(_get_commission(seeded_user, commission_id))["data"]
    _assert_validation_error(
        _put_commission(
            seeded_user,
            commission_id,
            {"occurredAt": COMMISSION_OCCURRED_AT},
        )
    )
    after = response_json(_get_commission(seeded_user, commission_id))["data"]
    assert after == before


def test_personal_commissions_update_foreign_malformed_inactive_not_found(seeded_user):
    register_user(PROFILE_USER_B)
    _, foreign_id = _create_commission_for_user(PROFILE_USER_B)
    _assert_not_found(
        _put_commission(
            seeded_user,
            foreign_id,
            {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 1},
        )
    )
    _assert_not_found(
        _put_commission(
            seeded_user,
            "entry_bad",
            {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 1},
        )
    )
    _, own_id = _create_commission_for_user(seeded_user)
    _deactivate_commission(seeded_user, own_id)
    _assert_not_found(
        _put_commission(
            seeded_user,
            own_id,
            {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 1},
        )
    )


def test_personal_commissions_deactivate_soft_delete_and_visibility(seeded_user):
    place_id, commission_id = _create_commission_for_user(seeded_user)
    response = _deactivate_commission(seeded_user, commission_id)
    assert response.status == 200
    assert response_json(response)["data"] == {}
    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM personal_place_entries WHERE public_id = ?",
        (commission_id,),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["status"] == "inactive"
    assert response_json(_list_commissions(seeded_user, place_id))["data"]["commissions"] == []
    places = response_json(
        _list_commissions(seeded_user, place_id, "?includeInactive=true")
    )["data"]["commissions"]
    assert any(item["id"] == commission_id and item["status"] == "inactive" for item in places)
    assert response_json(_get_commission(seeded_user, commission_id))["data"]["status"] == "inactive"


def test_personal_commissions_deactivate_repeat_and_foreign_not_found(seeded_user):
    register_user(PROFILE_USER_B)
    _, commission_id = _create_commission_for_user(seeded_user)
    assert _deactivate_commission(seeded_user, commission_id).status == 200
    _assert_not_found(_deactivate_commission(seeded_user, commission_id))
    _, foreign_id = _create_commission_for_user(PROFILE_USER_B)
    _assert_not_found(_deactivate_commission(seeded_user, foreign_id))


def test_personal_commissions_deactivate_rejects_non_empty_body(seeded_user):
    _, commission_id = _create_commission_for_user(seeded_user)
    response = api_request(
        "POST",
        f"/app/v1/personal-commissions/{commission_id}/deactivate",
        headers=_auth_headers(seeded_user),
        data=b"{}",
    )
    _assert_validation_error(response)
    assert response_json(_get_commission(seeded_user, commission_id))["data"]["status"] == "active"


def test_personal_commissions_create_idempotency_replay(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    first = _post_commission(
        seeded_user,
        place_id,
        {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 2},
        **{"Idempotency-Key": "commission-create-1"},
    )
    second = _post_commission(
        seeded_user,
        place_id,
        {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 2},
        **{"Idempotency-Key": "commission-create-1"},
    )
    assert first.status == 201
    assert second.status == 201
    first_id = response_json(first)["data"]["id"]
    assert response_json(second)["data"]["id"] == first_id
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM personal_place_entries WHERE user_id = ?",
        (seeded_user,),
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_personal_commissions_update_idempotency_replay(seeded_user):
    _, commission_id = _create_commission_for_user(seeded_user)
    payload = {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 8}
    first = _put_commission(
        seeded_user,
        commission_id,
        payload,
        **{"Idempotency-Key": "commission-update-1"},
    )
    second = _put_commission(
        seeded_user,
        commission_id,
        payload,
        **{"Idempotency-Key": "commission-update-1"},
    )
    assert first.status == 200
    assert second.status == 200
    assert response_json(first)["data"]["receivedPoints"] == 8
    assert response_json(second)["data"]["receivedPoints"] == 8


def test_personal_commissions_deactivate_idempotency_replay(seeded_user):
    _, commission_id = _create_commission_for_user(seeded_user)
    first = _deactivate_commission(
        seeded_user,
        commission_id,
        **{"Idempotency-Key": "commission-deactivate-1"},
    )
    second = _deactivate_commission(
        seeded_user,
        commission_id,
        **{"Idempotency-Key": "commission-deactivate-1"},
    )
    assert first.status == 200
    assert second.status == 200
    assert response_json(first)["data"] == {}
    assert response_json(second)["data"] == {}


def test_personal_commissions_idempotency_replay_conflict(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    first = _post_commission(
        seeded_user,
        place_id,
        {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 1},
        **{"Idempotency-Key": "commission-conflict-1"},
    )
    assert first.status == 201
    conflict = _post_commission(
        seeded_user,
        place_id,
        {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 2},
        **{"Idempotency-Key": "commission-conflict-1"},
    )
    body = response_json(conflict)
    assert conflict.status == 409
    assert body["error"]["code"] == "idempotency_replay"


def test_personal_commissions_idempotency_isolated_between_users(seeded_user):
    register_user(PROFILE_USER_B)
    place_a = _create_place_for_user(seeded_user)
    place_b = _create_place_for_user(PROFILE_USER_B)
    first = _post_commission(
        seeded_user,
        place_a,
        {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 1},
        **{"Idempotency-Key": "shared-commission-key"},
    )
    second = _post_commission(
        PROFILE_USER_B,
        place_b,
        {"occurredAt": COMMISSION_OCCURRED_AT, "receivedPoints": 1},
        **{"Idempotency-Key": "shared-commission-key"},
    )
    assert first.status == 201
    assert second.status == 201
    assert response_json(first)["data"]["id"] != response_json(second)["data"]["id"]


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


# --- GSMA5 official GuideShop companies ---

GUIDE_OS_A = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee1"
GUIDE_OS_B = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee2"
OFFICIAL_COMPANY_FIELDS = {
    "id",
    "displayName",
    "status",
    "phone",
    "address",
    "description",
    "type",
}


@pytest.fixture(autouse=True)
def _reset_miniapp_guideshop_provider():
    configure_miniapp_guideshop_provider(None, reads_enabled=False)
    yield
    configure_miniapp_guideshop_provider(None, reads_enabled=False)


def _official_company(
    company_id="company-1",
    name="Silk Road",
    status="active",
    phone=None,
    address=None,
    description=None,
    company_type=None,
):
    return CompanyDTO.model_validate(
        {
            "company_id": company_id,
            "display_name": name,
            "status": status,
            "phone": phone,
            "address": address,
            "description": description,
            "type": company_type,
        }
    )


def _configure_static_official(service, *, reads_enabled=True):
    configure_miniapp_guideshop_provider(
        StaticGuideShopUIServiceProvider(service),
        reads_enabled=reads_enabled,
    )


def _list_official(user_id=API_USER, query=""):
    return api_request(
        "GET",
        f"/app/v1/guideshop/companies{query}",
        headers=_auth_headers(user_id),
    )


def _get_official(user_id, company_id):
    return api_request(
        "GET",
        f"/app/v1/guideshop/companies/{company_id}",
        headers=_auth_headers(user_id),
    )


class TrackingInMemoryGuideShopClient(InMemoryGuideShopClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


def test_official_guideshop_routes_registered_once():
    app = create_miniapp_api_app(_settings())
    routes = [
        (route.method, route.resource.canonical)
        for route in app.router.routes()
    ]
    assert routes.count(("GET", "/app/v1/guideshop/companies")) == 1
    assert routes.count(("GET", "/app/v1/guideshop/companies/{companyId}")) == 1
    assert ("POST", "/app/v1/guideshop/companies") not in routes
    assert ("PUT", "/app/v1/guideshop/companies/{companyId}") not in routes
    assert ("PATCH", "/app/v1/guideshop/companies/{companyId}") not in routes
    assert ("DELETE", "/app/v1/guideshop/companies/{companyId}") not in routes


def test_official_companies_list_success_field_mapping(seeded_user):
    company = _official_company(
        company_id="cmp_silk01",
        name="Silk Road",
        status="active",
        phone="+998901112233",
        address="Samarkand",
        description="Crafts",
        company_type="shop",
    )
    _configure_static_official(
        GuideShopUIService(InMemoryGuideShopClient(companies=(company,)))
    )
    response = _list_official(seeded_user)
    body = response_json(response)
    assert response.status == 200
    assert set(body["data"].keys()) == {"companies", "page"}
    assert body["data"]["page"] == {"nextCursor": None}
    assert len(body["data"]["companies"]) == 1
    mapped = body["data"]["companies"][0]
    assert set(mapped.keys()) == OFFICIAL_COMPANY_FIELDS
    assert mapped == {
        "id": "cmp_silk01",
        "displayName": "Silk Road",
        "status": "active",
        "phone": "+998901112233",
        "address": "Samarkand",
        "description": "Crafts",
        "type": "shop",
    }
    dumped = response._body_text
    assert "guide_os_id" not in dumped
    assert "company_id" not in dumped
    assert "display_name" not in dumped


def test_official_companies_optional_null_and_status_contract_value(seeded_user):
    companies = (
        _official_company(company_id="cmp_active", name="Active Co", status="active"),
        _official_company(company_id="cmp_inactv", name="Quiet Co", status="inactive"),
        _official_company(company_id="cmp_unknow", name="Mystery", status="unknown"),
    )
    _configure_static_official(
        GuideShopUIService(InMemoryGuideShopClient(companies=companies))
    )
    body = response_json(_list_official(seeded_user))
    by_id = {item["id"]: item for item in body["data"]["companies"]}
    for item in by_id.values():
        assert item["phone"] is None
        assert item["address"] is None
        assert item["description"] is None
        assert item["type"] is None
    assert by_id["cmp_active"]["status"] == "active"
    assert by_id["cmp_inactv"]["status"] == "inactive"
    assert by_id["cmp_unknow"]["status"] == "unknown"


def test_official_companies_page_cursor_remains_opaque(seeded_user):
    cursor = "opaque_cursor_token_01"

    class FakeService:
        async def list_official_companies(self):
            return SimpleNamespace(
                data=[_official_company(company_id="cmp_page01", name="Paged")],
                page=SimpleNamespace(next_cursor=cursor, has_more=True),
            )

    _configure_static_official(FakeService())
    body = response_json(_list_official(seeded_user))
    assert body["data"]["page"] == {"nextCursor": cursor}
    assert body["data"]["page"]["nextCursor"] == cursor
    assert "has_more" not in body["data"]["page"]
    assert "hasMore" not in body["data"]["page"]


def test_official_company_detail_success_exact_id_match(seeded_user):
    companies = (
        _official_company(company_id="cmp_alpha", name="Alpha"),
        _official_company(company_id="cmp_alpha2", name="Alpha Two"),
    )
    _configure_static_official(
        GuideShopUIService(InMemoryGuideShopClient(companies=companies))
    )
    response = _get_official(seeded_user, "cmp_alpha")
    body = response_json(response)
    assert response.status == 200
    assert set(body["data"].keys()) == OFFICIAL_COMPANY_FIELDS
    assert body["data"]["id"] == "cmp_alpha"
    assert body["data"]["displayName"] == "Alpha"
    assert body["data"]["status"] == "active"


def test_official_company_detail_missing_is_not_found(seeded_user):
    _configure_static_official(
        GuideShopUIService(
            InMemoryGuideShopClient(companies=(_official_company(),))
        )
    )
    response = _get_official(seeded_user, "missing-company")
    body = response_json(response)
    assert response.status == 404
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Компания не найдена."
    assert "missing-company" not in response._body_text


def test_official_company_detail_unsafe_id_is_safe_not_found(seeded_user):
    from urllib.parse import quote

    from services.guide_shop_contracts import _opaque_id

    calls = []

    class CountingService:
        async def get_official_company(self, company_id):
            calls.append(company_id)
            return None

        async def list_official_companies(self):
            calls.append("list")
            return SimpleNamespace(data=[], page=SimpleNamespace(next_cursor=None))

    _configure_static_official(CountingService())
    unsafe_ids = ["short", "12345678", "cmp_ok!", "bad id", "ab"]
    for company_id in unsafe_ids:
        with pytest.raises(ValueError):
            _opaque_id(company_id)
        response = api_request(
            "GET",
            f"/app/v1/guideshop/companies/{quote(company_id, safe='')}",
            headers=_auth_headers(seeded_user),
        )
        body = response_json(response)
        assert response.status == 404
        assert body["error"]["code"] == "not_found"
        assert company_id not in body["error"]["code"]
        assert company_id not in body["error"]["message"]
        assert response.status != 500
    assert calls == []


def test_official_companies_mutations_unavailable(seeded_user):
    calls = []

    class CountingService:
        async def list_official_companies(self):
            calls.append("list")
            return SimpleNamespace(data=[], page=SimpleNamespace(next_cursor=None))

        async def get_official_company(self, company_id):
            calls.append(("get", company_id))
            return None

    _configure_static_official(CountingService())
    company_id = "cmp_mutate"
    mutations = [
        ("POST", "/app/v1/guideshop/companies", {"json": {"displayName": "X"}}),
        ("PUT", f"/app/v1/guideshop/companies/{company_id}", {"json": {}}),
        ("PATCH", f"/app/v1/guideshop/companies/{company_id}", {"json": {}}),
        ("DELETE", f"/app/v1/guideshop/companies/{company_id}", {}),
    ]
    for method, path, kwargs in mutations:
        response = api_request(method, path, headers=_auth_headers(seeded_user), **kwargs)
        assert response.status in {404, 405}
        assert response.status != 500
    assert calls == []


def test_official_companies_auth_required():
    response = api_request("GET", "/app/v1/guideshop/companies")
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_required"


def test_official_companies_provider_absent_is_integration_disabled(seeded_user):
    response = _list_official(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "integration_disabled"
    assert body["error"]["message"] == "Раздел GuideShop временно отключён."


def test_official_companies_disabled_client_is_integration_disabled(seeded_user):
    _configure_static_official(GuideShopUIService(DisabledGuideShopClient()))
    response = _list_official(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "integration_disabled"


def test_official_companies_reads_disabled_flag(seeded_user):
    _configure_static_official(
        GuideShopUIService(InMemoryGuideShopClient(companies=(_official_company(),))),
        reads_enabled=False,
    )
    response = _list_official(seeded_user)
    assert response.status == 503
    assert response_json(response)["error"]["code"] == "integration_disabled"


def test_official_companies_missing_identity_is_access_denied(seeded_user):
    provider = RequestScopedGuideShopUIServiceProvider(
        lambda _user_id: None,
        lambda _guide_os_id: TrackingInMemoryGuideShopClient(),
    )
    configure_miniapp_guideshop_provider(provider, reads_enabled=True)
    response = _list_official(seeded_user)
    body = response_json(response)
    assert response.status == 403
    assert body["error"]["code"] == "access_denied"
    assert body["error"]["message"] == "Нет доступа к данным GuideShop."


@pytest.mark.parametrize(
    "error",
    [
        GuideShopAuthenticationError("secret-token"),
        GuideShopAccessDeniedError("secret-deny"),
    ],
)
def test_official_companies_auth_and_access_denied(seeded_user, error):
    class FakeService:
        async def list_official_companies(self):
            raise error

    _configure_static_official(FakeService())
    response = _list_official(seeded_user)
    body = response_json(response)
    assert response.status == 403
    assert body["error"]["code"] == "access_denied"
    assert "secret" not in response._body_text


def test_official_companies_upstream_not_found(seeded_user):
    class FakeService:
        async def list_official_companies(self):
            raise GuideShopObjectNotFoundError("missing upstream object xyz")

    _configure_static_official(FakeService())
    response = _list_official(seeded_user)
    body = response_json(response)
    assert response.status == 404
    assert body["error"]["code"] == "not_found"
    assert "xyz" not in response._body_text


def test_official_companies_temporary_outage(seeded_user):
    class FakeService:
        async def list_official_companies(self):
            raise GuideShopTemporarilyUnavailableError("timeout upstream")

    _configure_static_official(FakeService())
    response = _list_official(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "temporarily_unavailable"
    assert body["error"]["message"] == (
        "GuideShop временно недоступен. Попробуйте позже."
    )
    assert "timeout" not in response._body_text


def test_official_companies_generic_client_and_lifecycle_not_http_500(seeded_user):
    class FakeService:
        async def list_official_companies(self):
            raise GuideShopClientError("generic failure detail")

    _configure_static_official(FakeService())
    response = _list_official(seeded_user)
    assert response.status == 503
    assert response_json(response)["error"]["code"] == "temporarily_unavailable"
    assert response.status != 500
    assert "generic failure" not in response._body_text

    provider = RequestScopedGuideShopUIServiceProvider(
        lambda _user_id: GUIDE_OS_A,
        lambda _guide_os_id: (_ for _ in ()).throw(RuntimeError("create failed")),
    )
    configure_miniapp_guideshop_provider(provider, reads_enabled=True)
    lifecycle = _list_official(seeded_user)
    assert lifecycle.status == 503
    assert response_json(lifecycle)["error"]["code"] == "temporarily_unavailable"
    assert lifecycle.status != 500
    assert "create failed" not in lifecycle._body_text


def test_official_companies_request_scoped_cleanup_after_success_and_failure(
    seeded_user,
):
    created = []

    def factory(guide_os_id):
        assert guide_os_id == GUIDE_OS_A
        client = TrackingInMemoryGuideShopClient(
            companies=(_official_company(company_id="cmp_track1"),)
        )
        created.append(client)
        return client

    configure_miniapp_guideshop_provider(
        RequestScopedGuideShopUIServiceProvider(
            lambda user_id: GUIDE_OS_A if user_id == seeded_user else None,
            factory,
        ),
        reads_enabled=True,
    )
    ok = _list_official(seeded_user)
    assert ok.status == 200
    assert created[0].close_calls == 1

    class BoomClient(TrackingInMemoryGuideShopClient):
        async def list_companies(self):
            raise GuideShopTemporarilyUnavailableError("boom")

    boom_clients = []

    def boom_factory(_guide_os_id):
        client = BoomClient()
        boom_clients.append(client)
        return client

    configure_miniapp_guideshop_provider(
        RequestScopedGuideShopUIServiceProvider(
            lambda user_id: GUIDE_OS_A if user_id == seeded_user else None,
            boom_factory,
        ),
        reads_enabled=True,
    )
    failed = _list_official(seeded_user)
    assert failed.status == 503
    assert boom_clients[0].close_calls == 1


def test_official_companies_user_isolation_and_no_user_override(seeded_user):
    register_user(PROFILE_USER_B)
    clients_by_identity = {}

    def factory(guide_os_id):
        if guide_os_id == GUIDE_OS_A:
            client = TrackingInMemoryGuideShopClient(
                companies=(_official_company(company_id="cmp_user_a", name="For A"),)
            )
        else:
            client = TrackingInMemoryGuideShopClient(
                companies=(_official_company(company_id="cmp_user_b", name="For B"),)
            )
        clients_by_identity[guide_os_id] = client
        return client

    configure_miniapp_guideshop_provider(
        RequestScopedGuideShopUIServiceProvider(
            lambda user_id: {
                seeded_user: GUIDE_OS_A,
                PROFILE_USER_B: GUIDE_OS_B,
            }[user_id],
            factory,
        ),
        reads_enabled=True,
    )
    body_a = response_json(_list_official(seeded_user))
    body_b = response_json(_list_official(PROFILE_USER_B))
    assert [c["id"] for c in body_a["data"]["companies"]] == ["cmp_user_a"]
    assert [c["id"] for c in body_b["data"]["companies"]] == ["cmp_user_b"]
    assert GUIDE_OS_A not in _list_official(seeded_user)._body_text
    assert GUIDE_OS_B not in _list_official(PROFILE_USER_B)._body_text

    spoofed = _list_official(
        seeded_user,
        query=f"?userId={PROFILE_USER_B}&telegramUserId={PROFILE_USER_B}&guideOsId={GUIDE_OS_B}",
    )
    spoofed_body = response_json(spoofed)
    assert spoofed.status == 200
    assert [c["id"] for c in spoofed_body["data"]["companies"]] == ["cmp_user_a"]
    assert GUIDE_OS_B not in spoofed._body_text
    assert "Bearer" not in spoofed._body_text


def test_official_companies_script_like_strings_remain_inert(seeded_user):
    scriptish = "<script>alert(1)</script>"
    company = _official_company(
        company_id="cmp_script",
        name=scriptish,
        description=scriptish,
    )
    _configure_static_official(
        GuideShopUIService(InMemoryGuideShopClient(companies=(company,)))
    )
    response = _list_official(seeded_user)
    body = response_json(response)
    assert response.status == 200
    assert body["data"]["companies"][0]["displayName"] == scriptish
    assert body["data"]["companies"][0]["description"] == scriptish
    assert scriptish in response._body_text
    assert json.loads(response._body_text)["data"]["companies"][0]["displayName"] == (
        scriptish
    )


def test_official_failure_does_not_break_personal_places(seeded_user):
    place_id = _create_place_for_user(seeded_user)

    class FakeService:
        async def list_official_companies(self):
            raise GuideShopTemporarilyUnavailableError("outage")

    _configure_static_official(FakeService())
    official = _list_official(seeded_user)
    assert official.status == 503
    assert response_json(official)["error"]["code"] == "temporarily_unavailable"

    places = _list_places(seeded_user)
    body = response_json(places)
    assert places.status == 200
    assert any(item["id"] == place_id for item in body["data"]["places"])


def test_repeated_provider_configure_replaces_state(seeded_user):
    _configure_static_official(
        GuideShopUIService(
            InMemoryGuideShopClient(
                companies=(_official_company(company_id="cmp_first1"),)
            )
        )
    )
    first = response_json(_list_official(seeded_user))
    assert first["data"]["companies"][0]["id"] == "cmp_first1"

    _configure_static_official(
        GuideShopUIService(
            InMemoryGuideShopClient(
                companies=(_official_company(company_id="cmp_secon1"),)
            )
        )
    )
    second = response_json(_list_official(seeded_user))
    assert second["data"]["companies"][0]["id"] == "cmp_secon1"

    configure_miniapp_guideshop_provider(None, reads_enabled=False)
    cleared = _list_official(seeded_user)
    assert cleared.status == 503
    assert response_json(cleared)["error"]["code"] == "integration_disabled"


def test_disabled_runtime_clears_miniapp_official_provider(seeded_user):
    import bot as bot_module

    _configure_static_official(
        GuideShopUIService(InMemoryGuideShopClient(companies=(_official_company(),)))
    )
    assert _list_official(seeded_user).status == 200
    bot_module.configure_guide_shop_runtime({"GUIDESHOP_READS_ENABLED": "false"})
    response = _list_official(seeded_user)
    assert response.status == 503
    assert response_json(response)["error"]["code"] == "integration_disabled"


def test_fake_runtime_serves_empty_official_list(seeded_user):
    import bot as bot_module

    bot_module.configure_guide_shop_runtime(
        {
            "GUIDESHOP_READS_ENABLED": "true",
            "GUIDESHOP_USE_FAKE": "true",
            "APP_ENV": "development",
        }
    )
    response = _list_official(seeded_user)
    body = response_json(response)
    assert response.status == 200
    assert body["data"]["companies"] == []
    assert body["data"]["page"] == {"nextCursor": None}


def test_official_company_personal_place_id_is_not_reinterpreted(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    _configure_static_official(
        GuideShopUIService(InMemoryGuideShopClient(companies=(_official_company(),)))
    )
    response = _get_official(seeded_user, place_id)
    body = response_json(response)
    assert response.status == 404
    assert body["error"]["code"] == "not_found"
    assert place_id not in response._body_text
