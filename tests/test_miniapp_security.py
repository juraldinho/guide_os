"""
Mini App API security regression suite.

Executable evidence for IDOR, auth, CORS, idempotency, validation, and leakage controls.
Does not modify production code; failures document vulnerabilities.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer
from multidict import CIMultiDict

from database.db import get_connection
from database.queries import register_user
from services.miniapp_api_settings import MiniAppApiSettings
from services.tour_service import (
    SOURCE_MINI_APP,
    TourEntryDraft,
    create_day_off_entry,
    create_tour_entry,
    get_entry,
)
from web_api.app import (
    CORS_ALLOWED_HEADERS,
    CORS_ALLOWED_METHODS,
    MAX_REQUEST_BODY_BYTES,
    create_miniapp_api_app,
)
from web_api.auth import (
    _hash_session_token,
    create_miniapp_session,
    dev_session_token,
    idempotency_lookup,
    resolve_session_user_id,
    revoke_miniapp_session,
)
from web_api.telegram_auth import build_synthetic_init_data

# Reuse stable IDs from existing miniapp API tests where practical.
from tests.test_miniapp_api import (
    API_USER,
    PRODUCTION_FRONTEND_ORIGIN,
    TEST_BOT_TOKEN,
    response_json,
    run,
)

USER_A = 881001
USER_B = 882002
TELEGRAM_USER_A = 991001001
TELEGRAM_USER_B = 991002002

OWNER_TOUR_TITLE = "OWNER_SECRET_TITLE_A"
OWNER_COMPANY = "OWNER_COMPANY_A"
OWNER_NOTE = "OWNER_NOTE_SECRET_A"
OWNER_LOCATION = "OWNER_LOC_SECRET_A"
ATTACKER_TOUR_TITLE = "ATTACKER_TOUR_B"

FORBIDDEN_LEAK_MARKERS = (
    OWNER_TOUR_TITLE,
    OWNER_COMPANY,
    OWNER_NOTE,
    OWNER_LOCATION,
    "OWNER_DAY_OFF",
    str(USER_A),
    TEST_BOT_TOKEN,
    "traceback",
    "sqlite",
    "SELECT ",
    "INSERT ",
    "/Users/",
    "WebAppData",
)


def _settings(dev_auth: bool = True, **overrides) -> MiniAppApiSettings:
    values = {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8083,
        "dev_auth": dev_auth,
        "bot_token": TEST_BOT_TOKEN,
        "session_ttl_seconds": 3600,
        "initdata_max_age_seconds": 86400,
        "allowlist": frozenset(),
        "allowed_origin": PRODUCTION_FRONTEND_ORIGIN,
    }
    values.update(overrides)
    return MiniAppApiSettings(**values)


async def _with_client(settings: MiniAppApiSettings, coro):
    app = create_miniapp_api_app(settings)
    client = TestClient(TestServer(app))
    async with client:
        response = await coro(client)
        response._body_text = await response.text()
        return response


def api_request(
    settings: MiniAppApiSettings,
    method: str,
    path: str,
    **kwargs,
):
    async def _call(client):
        return await client.request(method, path, **kwargs)

    return run(_with_client(settings, _call))


def cors_request(
    method: str,
    path: str,
    origin: str | None = None,
    settings: MiniAppApiSettings | None = None,
    **kwargs,
):
    headers = dict(kwargs.pop("headers", {}))
    if origin is not None:
        headers["Origin"] = origin
    return api_request(settings or _settings(), method, path, headers=headers, **kwargs)


def bearer_headers(token: str, **extra) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    headers.update(extra)
    return headers


def dev_headers(user_id: int, **extra) -> dict[str, str]:
    return bearer_headers(dev_session_token(user_id), **extra)


def _tour_payload(**overrides) -> dict[str, Any]:
    payload = {
        "title": "Тур security",
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


def _now_timestamp() -> int:
    return int(time.time())


def _valid_init_data(user_id: int, auth_date: int | None = None, bot_token: str = TEST_BOT_TOKEN):
    return build_synthetic_init_data(
        bot_token,
        user_id,
        auth_date if auth_date is not None else _now_timestamp(),
    )


def _session_via_init_data(settings: MiniAppApiSettings, user_id: int) -> str:
    register_user(user_id)
    response = api_request(
        settings,
        "POST",
        "/app/v1/session",
        json={"init_data": _valid_init_data(user_id)},
    )
    body = response_json(response)
    assert response.status == 200
    return body["data"]["session_token"]


def _response_text(response) -> str:
    return response._body_text


def _assert_no_leak(text: str, extra_forbidden: tuple[str, ...] = ()) -> None:
    lowered = text.lower()
    for marker in FORBIDDEN_LEAK_MARKERS + extra_forbidden:
        if marker and marker.lower() in lowered:
            pytest.fail(f"Sensitive marker leaked in response: {marker!r}")


def _not_found_body(body: dict[str, Any]) -> dict[str, Any]:
    assert body["error"]["code"] == "not_found"
    assert "request_id" in body["meta"]
    return body


@dataclass
class SecurityContext:
    settings: MiniAppApiSettings
    owner_id: int
    attacker_id: int
    owner_tour_id: str
    owner_day_off_id: str
    attacker_tour_id: str
    owner_token: str
    attacker_token: str
    owner_dev_token: str
    attacker_dev_token: str
    owner_tour_title: str
    owner_company: str
    owner_note: str
    owner_locations: dict[str, str]


@pytest.fixture
def security_context() -> SecurityContext:
    settings = _settings(dev_auth=True)
    register_user(USER_A)
    register_user(USER_B)

    owner_tour = create_tour_entry(
        USER_A,
        TourEntryDraft(
            title=OWNER_TOUR_TITLE,
            company=OWNER_COMPANY,
            location=OWNER_LOCATION,
            start_date="2026-10-01",
            end_date="2026-10-03",
            status="confirmed",
            payment="paid",
            income=999,
            note=OWNER_NOTE,
            source=SOURCE_MINI_APP,
        ),
    )
    owner_day_off = create_day_off_entry(USER_A, "2026-07-15", "2026-07-15")
    attacker_tour = create_tour_entry(
        USER_B,
        TourEntryDraft(
            title=ATTACKER_TOUR_TITLE,
            company="AttackerCo",
            location="Бухара",
            start_date="2026-11-05",
            end_date="2026-11-05",
            status="reserved",
            payment="unpaid",
            income=111,
            source=SOURCE_MINI_APP,
        ),
    )

    owner_token, _ = create_miniapp_session(USER_A, settings.session_ttl_seconds)
    attacker_token, _ = create_miniapp_session(USER_B, settings.session_ttl_seconds)

    owner_locations = {
        "2026-10-01": "OWNER_LOC_DAY1",
        "2026-10-02": "OWNER_LOC_DAY2",
        "2026-10-03": "OWNER_LOC_DAY3",
    }
    from services.tour_service import update_day_locations

    update_day_locations(USER_A, owner_tour["id"], owner_locations)

    return SecurityContext(
        settings=settings,
        owner_id=USER_A,
        attacker_id=USER_B,
        owner_tour_id=str(owner_tour["id"]),
        owner_day_off_id=str(owner_day_off["id"]),
        attacker_tour_id=str(attacker_tour["id"]),
        owner_token=owner_token,
        attacker_token=attacker_token,
        owner_dev_token=dev_session_token(USER_A),
        attacker_dev_token=dev_session_token(USER_B),
        owner_tour_title=OWNER_TOUR_TITLE,
        owner_company=OWNER_COMPANY,
        owner_note=OWNER_NOTE,
        owner_locations=owner_locations,
    )


# ---------------------------------------------------------------------------
# A. IDOR / BOLA
# ---------------------------------------------------------------------------


class TestIdorBola:
    def test_list_entries_never_includes_owner_rows(self, security_context: SecurityContext):
        ctx = security_context
        response = api_request(
            ctx.settings,
            "GET",
            "/app/v1/entries?from=2026-01-01&to=2026-12-31",
            headers=bearer_headers(ctx.attacker_token),
        )
        body = response_json(response)
        assert response.status == 200
        ids = {item["id"] for item in body["data"]["entries"]}
        titles = {item["title"] for item in body["data"]["entries"]}
        assert ctx.owner_tour_id not in ids
        assert ctx.owner_day_off_id not in ids
        assert ctx.owner_tour_title not in titles
        assert ctx.attacker_tour_id in ids

    def test_get_owner_entry_returns_not_found(self, security_context: SecurityContext):
        ctx = security_context
        response = api_request(
            ctx.settings,
            "GET",
            f"/app/v1/entries/{ctx.owner_tour_id}",
            headers=bearer_headers(ctx.attacker_token),
        )
        body = _not_found_body(response_json(response))
        assert response.status == 404
        _assert_no_leak(_response_text(response))

    def test_patch_owner_entry_returns_not_found_and_preserves_data(
        self, security_context: SecurityContext
    ):
        ctx = security_context
        before = get_entry(ctx.owner_id, ctx.owner_tour_id)
        response = api_request(
            ctx.settings,
            "PATCH",
            f"/app/v1/entries/{ctx.owner_tour_id}",
            headers=bearer_headers(ctx.attacker_token),
            json=_tour_payload(title="HACKED_BY_B", income=1),
        )
        body = _not_found_body(response_json(response))
        assert response.status == 404
        _assert_no_leak(_response_text(response))
        after = get_entry(ctx.owner_id, ctx.owner_tour_id)
        assert after is not None
        assert after["title"] == before["title"]
        assert after["income"] == before["income"]

    def test_delete_owner_entry_returns_not_found_and_preserves_row(
        self, security_context: SecurityContext
    ):
        ctx = security_context
        response = api_request(
            ctx.settings,
            "DELETE",
            f"/app/v1/entries/{ctx.owner_tour_id}",
            headers=bearer_headers(ctx.attacker_token),
        )
        _not_found_body(response_json(response))
        assert response.status == 404
        assert get_entry(ctx.owner_id, ctx.owner_tour_id) is not None

    def test_copy_owner_entry_returns_not_found_without_new_row(
        self, security_context: SecurityContext
    ):
        ctx = security_context
        list_before = api_request(
            ctx.settings,
            "GET",
            "/app/v1/entries?from=2026-01-01&to=2026-12-31",
            headers=bearer_headers(ctx.attacker_token),
        )
        count_before = len(response_json(list_before)["data"]["entries"])
        response = api_request(
            ctx.settings,
            "POST",
            f"/app/v1/entries/{ctx.owner_tour_id}/copy",
            headers=bearer_headers(ctx.attacker_token),
            json={"startDate": "2026-12-01", "endDate": "2026-12-03"},
        )
        _not_found_body(response_json(response))
        assert response.status == 404
        list_after = api_request(
            ctx.settings,
            "GET",
            "/app/v1/entries?from=2026-01-01&to=2026-12-31",
            headers=bearer_headers(ctx.attacker_token),
        )
        count_after = len(response_json(list_after)["data"]["entries"])
        assert count_after == count_before
        owner_list = api_request(
            ctx.settings,
            "GET",
            "/app/v1/entries?from=2026-01-01&to=2026-12-31",
            headers=bearer_headers(ctx.owner_token),
        )
        owner_titles = [e["title"] for e in response_json(owner_list)["data"]["entries"]]
        assert sum(1 for t in owner_titles if t == ctx.owner_tour_title) == 1

    def test_patch_day_locations_owner_returns_not_found_and_preserves(
        self, security_context: SecurityContext
    ):
        ctx = security_context
        response = api_request(
            ctx.settings,
            "PATCH",
            f"/app/v1/entries/{ctx.owner_tour_id}/day-locations",
            headers=bearer_headers(ctx.attacker_token),
            json={"locations": {"2026-10-01": "HACKED_LOC"}},
        )
        _not_found_body(response_json(response))
        assert response.status == 404
        entry = get_entry(ctx.owner_id, ctx.owner_tour_id)
        assert entry is not None
        assert entry.get("day_locations") == ctx.owner_locations

    def test_day_off_idor_operations_fail_closed(self, security_context: SecurityContext):
        ctx = security_context
        for method, path, kwargs in (
            ("GET", f"/app/v1/entries/{ctx.owner_day_off_id}", {}),
            ("PATCH", f"/app/v1/entries/{ctx.owner_day_off_id}", {"json": _tour_payload()}),
            ("DELETE", f"/app/v1/entries/{ctx.owner_day_off_id}", {}),
            (
                "POST",
                f"/app/v1/entries/{ctx.owner_day_off_id}/copy",
                {"json": {"startDate": "2026-12-10", "endDate": "2026-12-10"}},
            ),
        ):
            response = api_request(
                ctx.settings,
                method,
                path,
                headers=bearer_headers(ctx.attacker_token),
                **kwargs,
            )
            body = _not_found_body(response_json(response))
            assert response.status == 404
            _assert_no_leak(_response_text(response), extra_forbidden=("day_off", "выходной"))
        assert get_entry(ctx.owner_id, ctx.owner_day_off_id) is not None

    def test_cross_user_and_invalid_id_not_found_envelopes_match(
        self, security_context: SecurityContext
    ):
        ctx = security_context
        cross = api_request(
            ctx.settings,
            "GET",
            f"/app/v1/entries/{ctx.owner_tour_id}",
            headers=bearer_headers(ctx.attacker_token),
        )
        invalid = api_request(
            ctx.settings,
            "GET",
            "/app/v1/entries/999999999",
            headers=bearer_headers(ctx.attacker_token),
        )
        cross_body = response_json(cross)
        invalid_body = response_json(invalid)
        assert cross.status == 404
        assert invalid.status == 404
        assert cross_body["error"]["code"] == "not_found"
        assert invalid_body["error"]["code"] == "not_found"
        assert cross_body["error"]["message"] == invalid_body["error"]["message"]
        assert cross_body["meta"]["request_id"] != invalid_body["meta"]["request_id"]


# ---------------------------------------------------------------------------
# B. User-scoped aggregates
# ---------------------------------------------------------------------------


class TestUserScopedAggregates:
    def test_reports_summary_isolated_between_users(self, security_context: SecurityContext):
        ctx = security_context
        owner_report = api_request(
            ctx.settings,
            "GET",
            "/app/v1/reports/summary?from=2026-01-01&to=2026-12-31&status=all&payment=all",
            headers=bearer_headers(ctx.owner_token),
        )
        attacker_report = api_request(
            ctx.settings,
            "GET",
            "/app/v1/reports/summary?from=2026-01-01&to=2026-12-31&status=all&payment=all",
            headers=bearer_headers(ctx.attacker_token),
        )
        owner_body = response_json(owner_report)["data"]
        attacker_body = response_json(attacker_report)["data"]
        assert owner_report.status == 200
        assert attacker_report.status == 200
        assert owner_body["income"] != attacker_body["income"]
        assert owner_body["income"] >= 999
        assert attacker_body["income"] == 111
        assert owner_body["workDays"] != attacker_body["workDays"]
        assert owner_body["paidTours"] >= 1
        assert attacker_body["unpaidTours"] == 1
        _assert_no_leak(_response_text(attacker_report))

    def test_availability_preview_scoped_to_caller(self, security_context: SecurityContext):
        ctx = security_context
        owner_preview = api_request(
            ctx.settings,
            "POST",
            "/app/v1/availability/preview",
            headers=bearer_headers(ctx.owner_token),
            json={"from": "2026-10-01", "to": "2026-10-31"},
        )
        attacker_preview = api_request(
            ctx.settings,
            "POST",
            "/app/v1/availability/preview",
            headers=bearer_headers(ctx.attacker_token),
            json={"from": "2026-10-01", "to": "2026-10-31"},
        )
        owner_text = response_json(owner_preview)["data"]["text"]
        attacker_text = response_json(attacker_preview)["data"]["text"]
        assert OWNER_TOUR_TITLE not in attacker_text
        assert ATTACKER_TOUR_TITLE not in owner_text

    def test_profile_endpoints_return_own_identity_only(self, security_context: SecurityContext):
        ctx = security_context
        owner_profile = api_request(
            ctx.settings,
            "GET",
            "/app/v1/profile",
            headers=bearer_headers(ctx.owner_token),
        )
        attacker_profile = api_request(
            ctx.settings,
            "GET",
            "/app/v1/profile",
            headers=bearer_headers(ctx.attacker_token),
        )
        owner_data = response_json(owner_profile)["data"]
        attacker_data = response_json(attacker_profile)["data"]
        assert owner_data["telegramId"] == str(ctx.owner_id)
        assert attacker_data["telegramId"] == str(ctx.attacker_id)
        assert owner_data["telegramId"] != attacker_data["telegramId"]

    def test_conflict_check_scoped_to_attacker_entries_only(
        self, security_context: SecurityContext
    ):
        ctx = security_context
        response = api_request(
            ctx.settings,
            "POST",
            "/app/v1/day-offs",
            headers=bearer_headers(ctx.attacker_token),
            json={"startDate": "2026-11-05", "endDate": "2026-11-05"},
        )
        body = response_json(response)
        assert response.status == 409
        details = body.get("error", {}).get("details", {})
        existing = details.get("existing_entry") or {}
        assert existing.get("title") == ATTACKER_TOUR_TITLE
        _assert_no_leak(_response_text(response))


# ---------------------------------------------------------------------------
# C. Idempotency isolation
# ---------------------------------------------------------------------------


class TestIdempotencyIsolation:
    def test_same_key_different_users_do_not_share_cache(self, security_context: SecurityContext):
        ctx = security_context
        key = "shared-key-cross-user"
        owner_headers = bearer_headers(ctx.owner_token, **{"Idempotency-Key": key})
        attacker_headers = bearer_headers(ctx.attacker_token, **{"Idempotency-Key": key})
        payload = _tour_payload(startDate="2026-12-11", endDate="2026-12-11", title="Idem A")
        owner_resp = api_request(
            ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=owner_headers,
            json=payload,
        )
        attacker_resp = api_request(
            ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=attacker_headers,
            json=payload,
        )
        owner_id = response_json(owner_resp)["data"]["id"]
        attacker_id = response_json(attacker_resp)["data"]["id"]
        assert owner_resp.status == 201
        assert attacker_resp.status == 201
        assert owner_id != attacker_id

    def test_same_user_same_key_same_body_replays_stored_response(
        self, security_context: SecurityContext
    ):
        ctx = security_context
        key = "idem-replay-same-user"
        headers = bearer_headers(ctx.owner_token, **{"Idempotency-Key": key})
        payload = _tour_payload(startDate="2026-12-12", endDate="2026-12-12", title="Idem replay")
        first = api_request(ctx.settings, "POST", "/app/v1/tours", headers=headers, json=payload)
        second = api_request(ctx.settings, "POST", "/app/v1/tours", headers=headers, json=payload)
        assert first.status == 201
        assert second.status == 201
        assert response_json(first) == response_json(second)

    def test_same_user_same_key_different_body_returns_conflict(
        self, security_context: SecurityContext
    ):
        ctx = security_context
        key = "idem-conflict-body"
        headers = bearer_headers(ctx.owner_token, **{"Idempotency-Key": key})
        first = api_request(
            ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=headers,
            json=_tour_payload(startDate="2026-12-13", endDate="2026-12-13"),
        )
        assert first.status == 201
        conflict = api_request(
            ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=headers,
            json=_tour_payload(startDate="2026-12-14", endDate="2026-12-14"),
        )
        body = response_json(conflict)
        assert conflict.status == 409
        assert body["error"]["code"] == "idempotency_replay"

    def test_idempotency_rows_are_user_scoped_in_database(self, security_context: SecurityContext):
        ctx = security_context
        key = "db-scope-key"
        body_bytes = json.dumps(_tour_payload(startDate="2026-12-15")).encode()
        stored_a = idempotency_lookup(ctx.owner_id, "POST /app/v1/tours", key, body_bytes)
        stored_b = idempotency_lookup(ctx.attacker_id, "POST /app/v1/tours", key, body_bytes)
        assert stored_a is None or stored_b is None or stored_a != stored_b


# ---------------------------------------------------------------------------
# D. Bearer-session security
# ---------------------------------------------------------------------------


class TestBearerSessionSecurity:
    def test_missing_authorization_rejected(self):
        settings = _settings()
        response = api_request(settings, "GET", "/app/v1/profile")
        body = response_json(response)
        assert response.status == 401
        assert body["error"]["code"] == "auth_required"

    def test_empty_and_malformed_bearer_rejected(self):
        settings = _settings()
        for auth_value in ("Bearer ", "Token abc", "Bearer", "not-bearer token"):
            response = api_request(
                settings,
                "GET",
                "/app/v1/profile",
                headers={"Authorization": auth_value},
            )
            assert response.status == 401

    def test_random_token_rejected(self):
        settings = _settings()
        response = api_request(
            settings,
            "GET",
            "/app/v1/profile",
            headers=bearer_headers("totally-invalid-random-token-value"),
        )
        assert response.status == 401

    def test_duplicate_authorization_headers_rejected(self):
        settings = _settings()
        headers = CIMultiDict()
        headers.add("Authorization", "Bearer one")
        headers.add("Authorization", "Bearer two")
        response = api_request(settings, "GET", "/app/v1/profile", headers=headers)
        assert response.status == 401

    def test_expired_session_rejected(self, security_context: SecurityContext):
        ctx = security_context
        token, _ = create_miniapp_session(ctx.owner_id, 60, now_timestamp=_now_timestamp() - 120)
        response = api_request(
            ctx.settings,
            "GET",
            "/app/v1/profile",
            headers=bearer_headers(token),
        )
        assert response.status == 401

    def test_revoked_session_rejected(self, security_context: SecurityContext):
        ctx = security_context
        token, _ = create_miniapp_session(ctx.owner_id, 3600)
        revoke_miniapp_session(token)
        response = api_request(
            ctx.settings,
            "GET",
            "/app/v1/profile",
            headers=bearer_headers(token),
        )
        assert response.status == 401

    def test_token_not_echoed_in_error_responses(self, security_context: SecurityContext):
        ctx = security_context
        token = ctx.owner_token
        response = api_request(
            ctx.settings,
            "GET",
            "/app/v1/profile",
            headers=bearer_headers(token + "tampered"),
        )
        text = _response_text(response)
        assert token not in text

    def test_only_session_hash_stored_in_sqlite(self, security_context: SecurityContext):
        token, _ = create_miniapp_session(USER_A, 3600)
        conn = get_connection()
        rows = conn.execute("SELECT token_hash FROM miniapp_sessions").fetchall()
        conn.close()
        hashes = [row["token_hash"] for row in rows]
        assert token not in hashes
        assert _hash_session_token(token) in hashes

    def test_delete_session_only_revokes_own_token(self, security_context: SecurityContext):
        ctx = security_context
        victim_token = ctx.owner_token
        attacker_headers = bearer_headers(ctx.attacker_token)
        delete_resp = api_request(
            ctx.settings,
            "DELETE",
            "/app/v1/session",
            headers=attacker_headers,
        )
        assert delete_resp.status == 200
        victim_profile = api_request(
            ctx.settings,
            "GET",
            "/app/v1/profile",
            headers=bearer_headers(victim_token),
        )
        assert victim_profile.status == 200

    def test_body_user_id_fields_do_not_change_session_identity(self, security_context: SecurityContext):
        ctx = security_context
        response = api_request(
            ctx.settings,
            "PATCH",
            "/app/v1/profile",
            headers=bearer_headers(ctx.owner_token),
            json={
                "name": "Owner Name",
                "user_id": ctx.attacker_id,
                "telegram_id": str(ctx.attacker_id),
            },
        )
        profile = api_request(
            ctx.settings,
            "GET",
            "/app/v1/profile",
            headers=bearer_headers(ctx.owner_token),
        )
        data = response_json(profile)["data"]
        assert response.status == 200
        assert data["telegramId"] == str(ctx.owner_id)


# ---------------------------------------------------------------------------
# E. Telegram initData validation
# ---------------------------------------------------------------------------


class TestTelegramInitDataValidation:
    @pytest.fixture
    def prod_settings(self):
        return _settings(dev_auth=False)

    def test_valid_signed_init_data_creates_session(self, prod_settings):
        register_user(TELEGRAM_USER_A)
        response = api_request(
            prod_settings,
            "POST",
            "/app/v1/session",
            json={"init_data": _valid_init_data(TELEGRAM_USER_A)},
        )
        body = response_json(response)
        assert response.status == 200
        assert body["data"]["session_token"]
        assert not body["data"]["session_token"].startswith("dev:")

    def test_missing_hash_rejected(self, prod_settings):
        init_data = _valid_init_data(TELEGRAM_USER_A)
        stripped = init_data.split("&hash=", 1)[0]
        response = api_request(prod_settings, "POST", "/app/v1/session", json={"init_data": stripped})
        assert response.status == 401

    def test_modified_hash_rejected(self, prod_settings):
        init_data = _valid_init_data(TELEGRAM_USER_A)
        tampered = init_data.rsplit("hash=", 1)[0] + "hash=00"
        response = api_request(prod_settings, "POST", "/app/v1/session", json={"init_data": tampered})
        assert response.status == 401

    def test_modified_user_payload_after_signing_rejected(self, prod_settings):
        init_data = _valid_init_data(TELEGRAM_USER_A)
        swapped_user = init_data.replace(
            str(TELEGRAM_USER_A),
            str(TELEGRAM_USER_B),
            1,
        )
        response = api_request(prod_settings, "POST", "/app/v1/session", json={"init_data": swapped_user})
        assert response.status == 401

    def test_expired_auth_date_rejected(self, prod_settings):
        expired = _valid_init_data(TELEGRAM_USER_A, auth_date=_now_timestamp() - 999999)
        response = api_request(prod_settings, "POST", "/app/v1/session", json={"init_data": expired})
        assert response.status == 401

    def test_zero_and_negative_auth_date_rejected(self, prod_settings):
        for auth_date in (0, -1):
            init_data = build_synthetic_init_data(TEST_BOT_TOKEN, TELEGRAM_USER_A, auth_date)
            response = api_request(
                prod_settings,
                "POST",
                "/app/v1/session",
                json={"init_data": init_data},
            )
            assert response.status == 401

    def test_future_auth_date_rejected(self, prod_settings):
        future = _valid_init_data(TELEGRAM_USER_A, auth_date=_now_timestamp() + 3600)
        response = api_request(prod_settings, "POST", "/app/v1/session", json={"init_data": future})
        assert response.status == 401

    def test_missing_user_rejected(self, prod_settings):
        init_data = build_synthetic_init_data(TEST_BOT_TOKEN, TELEGRAM_USER_A, _now_timestamp())
        without_user = "&".join(part for part in init_data.split("&") if not part.startswith("user="))
        response = api_request(prod_settings, "POST", "/app/v1/session", json={"init_data": without_user})
        assert response.status == 401

    def test_malformed_user_json_rejected(self, prod_settings):
        broken = f"auth_date={_now_timestamp()}&user=%7Bbroken&hash=00"
        response = api_request(prod_settings, "POST", "/app/v1/session", json={"init_data": broken})
        assert response.status == 401

    def test_invalid_telegram_user_ids_rejected(self, prod_settings):
        for bad_id in (0, -5, 2**63):
            init_data = build_synthetic_init_data(TEST_BOT_TOKEN, bad_id, _now_timestamp())
            response = api_request(
                prod_settings,
                "POST",
                "/app/v1/session",
                json={"init_data": init_data},
            )
            assert response.status == 401

    def test_missing_bot_token_rejected(self):
        settings = _settings(dev_auth=False, bot_token="")
        response = api_request(
            settings,
            "POST",
            "/app/v1/session",
            json={"init_data": _valid_init_data(TELEGRAM_USER_A)},
        )
        assert response.status == 401

    def test_signature_from_different_bot_token_rejected(self, prod_settings):
        other_bot = "8000000000:OTHER_test_bot_token_for_security"
        init_data = _valid_init_data(TELEGRAM_USER_A, bot_token=other_bot)
        response = api_request(prod_settings, "POST", "/app/v1/session", json={"init_data": init_data})
        assert response.status == 401

    def test_duplicate_sensitive_fields_rejected(self, prod_settings):
        base = _valid_init_data(TELEGRAM_USER_A)
        duplicate_hash = base + "&hash=deadbeef"
        response = api_request(
            prod_settings,
            "POST",
            "/app/v1/session",
            json={"init_data": duplicate_hash},
        )
        body = response_json(response)
        assert response.status == 401
        assert body["error"]["code"] == "auth_invalid"

    def test_unsigned_user_object_payload_rejected(self, prod_settings):
        response = api_request(
            prod_settings,
            "POST",
            "/app/v1/session",
            json={"user": {"id": TELEGRAM_USER_A, "first_name": "Unsafe"}},
        )
        body = response_json(response)
        assert response.status == 400
        assert body["error"]["code"] == "validation_error"


# ---------------------------------------------------------------------------
# F. Dev-auth and allowlist
# ---------------------------------------------------------------------------


class TestDevAuthAndAllowlist:
    def test_dev_user_id_rejected_when_dev_auth_disabled(self):
        settings = _settings(dev_auth=False)
        response = api_request(
            settings,
            "POST",
            "/app/v1/session",
            json={"dev_user_id": API_USER},
        )
        assert response.status == 401

    def test_bearer_dev_scheme_rejected_when_dev_auth_disabled(self):
        settings = _settings(dev_auth=False)
        response = api_request(
            settings,
            "GET",
            "/app/v1/profile",
            headers=dev_headers(API_USER),
        )
        assert response.status == 401

    def test_x_dev_user_header_rejected_when_dev_auth_disabled(self):
        settings = _settings(dev_auth=False)
        response = api_request(
            settings,
            "GET",
            "/app/v1/profile",
            headers={"X-Dev-User-Id": str(API_USER)},
        )
        assert response.status == 401

    def test_invalid_dev_ids_rejected(self):
        settings = _settings(dev_auth=True)
        for bad in (0, -1, 2**63):
            response = api_request(
                settings,
                "POST",
                "/app/v1/session",
                json={"dev_user_id": bad},
            )
            body = response_json(response)
            assert response.status == 400
            assert body["error"]["code"] == "validation_error"
        response = api_request(
            settings,
            "POST",
            "/app/v1/session",
            json={"dev_user_id": "not-a-number"},
        )
        body = response_json(response)
        assert response.status == 400
        assert body["error"]["code"] == "validation_error"

    def test_allowlist_blocks_session_create_for_outside_user(self):
        settings = _settings(dev_auth=False, allowlist=frozenset({999888777}))
        register_user(TELEGRAM_USER_A)
        response = api_request(
            settings,
            "POST",
            "/app/v1/session",
            json={"init_data": _valid_init_data(TELEGRAM_USER_A)},
        )
        assert response.status == 403

    def test_allowlist_enforced_on_existing_bearer_session(self):
        settings_open = _settings(dev_auth=False, allowlist=frozenset())
        token = _session_via_init_data(settings_open, TELEGRAM_USER_A)
        settings_closed = _settings(dev_auth=False, allowlist=frozenset({999888777}))
        response = api_request(
            settings_closed,
            "GET",
            "/app/v1/profile",
            headers=bearer_headers(token),
        )
        assert response.status == 403

    def test_empty_allowlist_allows_any_valid_telegram_user(self):
        settings = _settings(dev_auth=False, allowlist=frozenset())
        register_user(TELEGRAM_USER_B)
        response = api_request(
            settings,
            "POST",
            "/app/v1/session",
            json={"init_data": _valid_init_data(TELEGRAM_USER_B)},
        )
        assert response.status == 200


# ---------------------------------------------------------------------------
# G. CORS
# ---------------------------------------------------------------------------


class TestCorsSecurity:
    def test_exact_allowed_origin_reflected(self):
        response = cors_request(
            "GET",
            "/app/v1/profile",
            origin=PRODUCTION_FRONTEND_ORIGIN,
            headers=dev_headers(API_USER),
        )
        assert response.headers.get("Access-Control-Allow-Origin") == PRODUCTION_FRONTEND_ORIGIN

    def test_arbitrary_origin_not_reflected(self):
        response = cors_request(
            "GET",
            "/app/v1/profile",
            origin="https://evil.example",
            headers=dev_headers(API_USER),
        )
        assert "Access-Control-Allow-Origin" not in response.headers

    def test_wildcard_origin_never_returned(self):
        response = cors_request("OPTIONS", "/app/v1/session", origin="https://evil.example")
        allow = response.headers.get("Access-Control-Allow-Origin")
        assert allow is None or allow != "*"

    def test_disallowed_preflight_fails_closed(self):
        response = cors_request("OPTIONS", "/app/v1/session", origin="https://evil.example")
        assert response.status == 403

    def test_preflight_methods_and_headers_restricted(self):
        response = cors_request("OPTIONS", "/app/v1/session", origin=PRODUCTION_FRONTEND_ORIGIN)
        assert response.headers.get("Access-Control-Allow-Methods") == CORS_ALLOWED_METHODS
        assert response.headers.get("Access-Control-Allow-Headers") == CORS_ALLOWED_HEADERS

    def test_cors_does_not_bypass_authentication(self):
        response = cors_request("GET", "/app/v1/profile", origin=PRODUCTION_FRONTEND_ORIGIN)
        assert response.status == 401

    def test_no_allow_credentials_header(self):
        response = cors_request(
            "GET",
            "/app/v1/profile",
            origin=PRODUCTION_FRONTEND_ORIGIN,
            headers=dev_headers(API_USER),
        )
        assert response.headers.get("Access-Control-Allow-Credentials") is None

    def test_deceptive_suffix_origin_rejected(self):
        deceptive = f"https://{PRODUCTION_FRONTEND_ORIGIN.replace('https://', '')}.attacker.example"
        response = cors_request("OPTIONS", "/app/v1/session", origin=deceptive)
        assert response.status == 403

    def test_scheme_and_port_mismatch_rejected(self):
        http_origin = PRODUCTION_FRONTEND_ORIGIN.replace("https://", "http://")
        response = cors_request("OPTIONS", "/app/v1/session", origin=http_origin)
        assert response.status == 403

    def test_health_without_cors_headers(self):
        response = api_request(_settings(), "GET", "/health")
        assert response.status == 200
        assert "Access-Control-Allow-Origin" not in response.headers


# ---------------------------------------------------------------------------
# H. Payload and validation boundaries
# ---------------------------------------------------------------------------


class TestPayloadValidation:
    @pytest.fixture
    def write_ctx(self, security_context: SecurityContext):
        return security_context

    def test_wrong_content_type_rejected(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers={
                "Authorization": f"Bearer {write_ctx.owner_token}",
                "Content-Type": "text/plain",
            },
            data="not json",
        )
        assert response.status == 400

    def test_malformed_json_rejected(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            data="{not-json",
        )
        assert response.status == 400

    def test_json_array_body_rejected(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            data=json.dumps([{"title": "x"}]),
        )
        assert response.status == 400

    def test_empty_body_tour_create_validation_error(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            data="",
        )
        assert response.status == 400

    def test_oversized_body_rejected(self, write_ctx: SecurityContext):
        huge = json.dumps({"title": "x", "note": "a" * (MAX_REQUEST_BODY_BYTES + 1)})
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            data=huge,
        )
        assert response.status == 413

    def test_identity_override_fields_ignored(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(
                title="Identity override probe",
                user_id=write_ctx.attacker_id,
                telegram_id=str(write_ctx.attacker_id),
                owner_id=write_ctx.attacker_id,
            ),
        )
        assert response.status == 201
        entry_id = response_json(response)["data"]["id"]
        entry = get_entry(write_ctx.owner_id, entry_id)
        assert entry is not None
        assert entry["title"] == "Identity override probe"

    def test_invalid_entry_id_format_on_get(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "GET",
            "/app/v1/entries/not-a-valid-id",
            headers=bearer_headers(write_ctx.owner_token),
        )
        assert response.status == 404

    def test_extremely_long_strings_accepted_without_server_error(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(title="T", note="N" * 20000),
        )
        assert response.status == 201
        assert _response_text(response).startswith("{")
        body = response_json(response)
        assert body["data"]["note"] == "N" * 20000

    def test_invalid_dates_and_ranges_rejected(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(startDate="2026-13-40", endDate="2026-01-01"),
        )
        assert response.status == 400

    def test_invalid_times_rejected(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(useTime=True, startTime="99:99", endTime="12:00"),
        )
        assert response.status == 400
        assert response_json(response)["error"]["code"] == "validation_error"

    def test_numeric_start_time_rejected_when_use_time(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(useTime=True, startTime=900, endTime="12:00"),
        )
        body = response_json(response)
        assert response.status == 400
        assert body["error"]["code"] == "validation_error"

    def test_object_start_time_rejected_when_use_time(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(useTime=True, startTime={"hour": 9}, endTime="12:00"),
        )
        body = response_json(response)
        assert response.status == 400
        assert body["error"]["code"] == "validation_error"

    def test_missing_end_time_rejected_when_use_time(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(useTime=True, startTime="10:00"),
        )
        body = response_json(response)
        assert response.status == 400
        assert body["error"]["code"] == "validation_error"

    def test_23_59_time_accepted_when_use_time(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(useTime=True, startTime="10:00", endTime="23:59"),
        )
        assert response.status == 201
        body = response_json(response)
        assert body["data"]["endTime"] == "23:59"

    def test_24_00_time_rejected_when_use_time(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(useTime=True, startTime="24:00", endTime="12:00"),
        )
        body = response_json(response)
        assert response.status == 400
        assert body["error"]["code"] == "validation_error"

    def test_nested_company_rejected(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(company={"nested": True}),
        )
        body = response_json(response)
        assert response.status == 400
        assert body["error"]["code"] == "validation_error"

    def test_nested_location_rejected(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(location=["Samarkand"]),
        )
        body = response_json(response)
        assert response.status == 400
        assert body["error"]["code"] == "validation_error"

    def test_nested_note_rejected(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(note={"secret": 1}),
        )
        body = response_json(response)
        assert response.status == 400
        assert body["error"]["code"] == "validation_error"

    def test_nested_day_location_value_rejected(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "PATCH",
            f"/app/v1/entries/{write_ctx.owner_tour_id}/day-locations",
            headers=bearer_headers(write_ctx.owner_token),
            json={"locations": {"2026-10-01": {"nested": True}}},
        )
        body = response_json(response)
        assert response.status == 400
        assert body["error"]["code"] == "validation_error"

    def test_impossible_day_location_date_rejected(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "PATCH",
            f"/app/v1/entries/{write_ctx.owner_tour_id}/day-locations",
            headers=bearer_headers(write_ctx.owner_token),
            json={"locations": {"2026-13-40": "Bad date key"}},
        )
        body = response_json(response)
        assert response.status == 400
        assert body["error"]["code"] == "validation_error"

    def test_invalid_status_payment_rejected(self, write_ctx: SecurityContext):
        for field, value in (("status", "hacked"), ("payment", "stolen")):
            payload = _tour_payload(**{field: value})
            response = api_request(
                write_ctx.settings,
                "POST",
                "/app/v1/tours",
                headers=bearer_headers(write_ctx.owner_token),
                json=payload,
            )
            assert response.status == 400

    def test_invalid_income_values_rejected(self, write_ctx: SecurityContext):
        for income in (-1, "NaN", "Infinity", {"bad": True}):
            response = api_request(
                write_ctx.settings,
                "POST",
                "/app/v1/tours",
                headers=bearer_headers(write_ctx.owner_token),
                json=_tour_payload(income=income),
            )
            assert response.status == 400

    def test_huge_income_rejected(self, write_ctx: SecurityContext):
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(income=1e30),
        )
        assert response.status == 400

    def test_malicious_html_stored_as_inert_data(self, write_ctx: SecurityContext):
        malicious = "<script>alert('xss')</script>"
        response = api_request(
            write_ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(write_ctx.owner_token),
            json=_tour_payload(title=malicious, note=malicious, company=malicious),
        )
        assert response.status == 201
        entry_id = response_json(response)["data"]["id"]
        fetched = api_request(
            write_ctx.settings,
            "GET",
            f"/app/v1/entries/{entry_id}",
            headers=bearer_headers(write_ctx.owner_token),
        )
        assert fetched.status == 200
        assert _response_text(fetched).startswith("{")
        data = response_json(fetched)["data"]
        assert data["title"] == malicious
        assert malicious in _response_text(fetched)


# ---------------------------------------------------------------------------
# I. Error leakage
# ---------------------------------------------------------------------------


class TestErrorLeakage:
    def test_auth_errors_do_not_leak_secrets(self):
        settings = _settings(dev_auth=False)
        init_data = _valid_init_data(TELEGRAM_USER_A)
        response = api_request(
            settings,
            "POST",
            "/app/v1/session",
            json={"init_data": init_data + "tamper"},
        )
        _assert_no_leak(_response_text(response), extra_forbidden=(init_data,))

    def test_idor_errors_do_not_leak_owner_data(self, security_context: SecurityContext):
        ctx = security_context
        response = api_request(
            ctx.settings,
            "GET",
            f"/app/v1/entries/{ctx.owner_tour_id}",
            headers=bearer_headers(ctx.attacker_token),
        )
        _assert_no_leak(_response_text(response))

    def test_validation_errors_do_not_leak_internals(self, security_context: SecurityContext):
        ctx = security_context
        response = api_request(
            ctx.settings,
            "POST",
            "/app/v1/tours",
            headers=bearer_headers(ctx.owner_token),
            json={"title": 123},
        )
        _assert_no_leak(_response_text(response))

