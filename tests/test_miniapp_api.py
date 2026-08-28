import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from database.queries import register_user
from services.miniapp_api_settings import MiniAppApiSettings
from services.tour_service import TourEntryDraft, create_tour_entry, SOURCE_MINI_APP
from web_api.app import create_miniapp_api_app, start_miniapp_api
from web_api.auth import dev_session_token

ROOT = Path(__file__).resolve().parents[1]
API_USER = 887001


def run(awaitable):
    return asyncio.run(awaitable)


def _settings(dev_auth=True):
    return MiniAppApiSettings(
        enabled=True,
        host="127.0.0.1",
        port=8083,
        dev_auth=dev_auth,
    )


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
    assert body["data"]["token"] == dev_session_token(seeded_user)
    assert body["data"]["user"]["telegram_id"] == str(seeded_user)


def test_session_rejects_init_data_stub():
    response = api_request(
        "POST",
        "/app/v1/session",
        json={"init_data": "stub"},
    )
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_invalid"


def test_session_disabled_when_dev_auth_off():
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
