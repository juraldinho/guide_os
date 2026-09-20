from __future__ import annotations

import asyncio
import json
import logging
import time

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from database.db import get_connection
from database.queries import register_user
from services.miniapp_analytics import (
    CLIENT_MINIAPP_EVENTS,
    SERVER_MINIAPP_EVENTS,
    track_miniapp_event_safely,
)
from services.miniapp_api_settings import MiniAppApiSettings
from web_api.app import create_miniapp_api_app, register_miniapp_api_on_app
from web_api.auth import dev_session_token
from web_api.telegram_auth import build_synthetic_init_data

USER_A = 950001
USER_B = 950002
TEST_BOT_TOKEN = "7000000000:TEST_miniapp_analytics_bot_token"


def run(awaitable):
    return asyncio.run(awaitable)


def _settings(**overrides):
    values = {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8083,
        "dev_auth": True,
        "bot_token": TEST_BOT_TOKEN,
        "session_ttl_seconds": 3600,
        "initdata_max_age_seconds": 86400,
        "allowlist": frozenset(),
    }
    values.update(overrides)
    return MiniAppApiSettings(**values)


async def _with_client(settings, call):
    client = TestClient(TestServer(create_miniapp_api_app(settings)))
    async with client:
        response = await call(client)
        response._body_text = await response.text()
        return response


def _request(method, path, *, settings=None, **kwargs):
    async def call(client):
        return await client.request(method, path, **kwargs)

    return run(_with_client(settings or _settings(), call))


def _json(response):
    return json.loads(response._body_text)


def _headers(user_id=USER_A, key="analytics-key"):
    return {
        "Authorization": f"Bearer {dev_session_token(user_id)}",
        "Content-Type": "application/json",
        "Idempotency-Key": key,
    }


def _analytics(name="miniapp_calendar_opened", *, user_id=USER_A, key="event-key"):
    return _request(
        "POST",
        "/app/v1/analytics/events",
        headers=_headers(user_id, key),
        json={"name": name},
    )


def _event_rows(event_name=None):
    conn = get_connection()
    if event_name is None:
        rows = conn.execute(
            "SELECT user_id, event_name, created_at FROM events ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT user_id, event_name, created_at
            FROM events
            WHERE event_name = ?
            ORDER BY id
            """,
            (event_name,),
        ).fetchall()
    conn.close()
    return rows


def _tour_payload(**overrides):
    payload = {
        "title": "Synthetic tour",
        "company": "Synthetic company",
        "location": "Synthetic location",
        "startDate": "2027-02-10",
        "endDate": "2027-02-10",
        "status": "confirmed",
        "payment": "unpaid",
        "income": 100,
        "note": "synthetic note",
    }
    payload.update(overrides)
    return payload


def _create_tour(user_id=USER_A, *, key="tour-key", payload=None):
    return _request(
        "POST",
        "/app/v1/tours",
        headers=_headers(user_id, key),
        json=payload or _tour_payload(),
    )


def test_client_and_server_event_allowlists_are_disjoint_and_fixed():
    assert CLIENT_MINIAPP_EVENTS == frozenset(
        {
            "miniapp_calendar_opened",
            "miniapp_month_picker_opened",
            "miniapp_day_opened",
            "miniapp_tour_create_started",
            "miniapp_tour_step_dates_completed",
            "miniapp_tour_step_details_completed",
            "miniapp_tour_save_clicked",
            "miniapp_tour_create_cancelled",
            "miniapp_tour_edit_started",
            "miniapp_tour_delete_started",
            "miniapp_reports_opened",
            "miniapp_profile_opened",
            "miniapp_guideshop_opened",
            "miniapp_guide_operator_opened",
        }
    )
    assert SERVER_MINIAPP_EVENTS == frozenset(
        {
            "miniapp_opened",
            "miniapp_tour_created",
            "miniapp_day_off_created",
            "miniapp_tour_updated",
            "miniapp_entry_deleted",
        }
    )
    assert CLIENT_MINIAPP_EVENTS.isdisjoint(SERVER_MINIAPP_EVENTS)


def test_valid_authenticated_event_is_stored_for_session_user():
    response = _analytics()
    assert response.status == 200
    assert _json(response)["data"] == {}
    rows = _event_rows("miniapp_calendar_opened")
    assert [(row["user_id"], row["event_name"]) for row in rows] == [
        (USER_A, "miniapp_calendar_opened")
    ]
    assert rows[0]["created_at"] is not None


@pytest.mark.parametrize(
    ("headers", "expected_status", "expected_code"),
    [
        ({"Content-Type": "application/json", "Idempotency-Key": "k"}, 401, "auth_required"),
        (
            {
                "Authorization": "Bearer invalid",
                "Content-Type": "application/json",
                "Idempotency-Key": "k",
            },
            401,
            "auth_required",
        ),
    ],
)
def test_analytics_endpoint_requires_valid_auth(headers, expected_status, expected_code):
    response = _request(
        "POST",
        "/app/v1/analytics/events",
        headers=headers,
        json={"name": "miniapp_calendar_opened"},
    )
    assert response.status == expected_status
    assert _json(response)["error"]["code"] == expected_code
    assert _event_rows() == []


@pytest.mark.parametrize(
    "body",
    [
        {"name": "miniapp_calendar_opened", "userId": USER_B},
        {"name": "miniapp_calendar_opened", "metadata": {}},
        {},
        {"name": 123},
        {"name": "unknown_event"},
        {"name": " miniapp_calendar_opened"},
        {"name": "miniapp_calendar_opened "},
        {"name": "miniapp_opened"},
    ],
)
def test_analytics_endpoint_rejects_non_contract_bodies(body):
    response = _request(
        "POST",
        "/app/v1/analytics/events",
        headers=_headers(),
        json=body,
    )
    assert response.status == 400
    assert _json(response)["error"]["code"] == "validation_error"
    assert _event_rows() == []


def test_analytics_endpoint_rejects_malformed_json_and_missing_key():
    malformed = _request(
        "POST",
        "/app/v1/analytics/events",
        headers=_headers(),
        data=b"{",
    )
    assert malformed.status == 400
    assert _json(malformed)["error"]["code"] == "validation_error"

    headers = _headers()
    headers.pop("Idempotency-Key")
    missing_key = _request(
        "POST",
        "/app/v1/analytics/events",
        headers=headers,
        json={"name": "miniapp_calendar_opened"},
    )
    assert missing_key.status == 400
    assert _json(missing_key)["error"]["code"] == "validation_error"
    assert _event_rows() == []


def test_analytics_idempotency_replays_and_conflicts_without_duplicates():
    first = _analytics(key="same-key")
    replay = _analytics(key="same-key")
    conflict = _analytics("miniapp_reports_opened", key="same-key")

    assert first.status == replay.status == 200
    assert conflict.status == 409
    assert _json(conflict)["error"]["code"] == "idempotency_replay"
    assert len(_event_rows("miniapp_calendar_opened")) == 1
    assert _event_rows("miniapp_reports_opened") == []


def test_analytics_idempotency_is_scoped_by_user():
    assert _analytics(user_id=USER_A, key="shared-key").status == 200
    assert _analytics(user_id=USER_B, key="shared-key").status == 200
    assert [row["user_id"] for row in _event_rows("miniapp_calendar_opened")] == [
        USER_A,
        USER_B,
    ]


def test_unknown_internal_event_fails_closed_without_database_write():
    assert track_miniapp_event_safely(USER_A, "not_allowlisted") is False
    assert _event_rows() == []


def test_safe_tracker_contains_database_failure_without_sensitive_logging(
    monkeypatch, caplog
):
    sensitive_error = "sensitive database failure"

    def fail_write(*_args):
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr("services.miniapp_analytics.track_event", fail_write)
    with caplog.at_level(logging.WARNING):
        assert (
            track_miniapp_event_safely(USER_A, "miniapp_calendar_opened")
            is False
        )
    assert "event=miniapp_calendar_opened outcome=write_failed" in caplog.text
    assert sensitive_error not in caplog.text
    assert str(USER_A) not in caplog.text


def test_successful_dev_and_telegram_session_bootstraps_record_opened():
    dev = _request(
        "POST",
        "/app/v1/session",
        json={"dev_user_id": USER_A},
    )
    init_data = build_synthetic_init_data(
        TEST_BOT_TOKEN,
        USER_B,
        int(time.time()),
    )
    telegram = _request(
        "POST",
        "/app/v1/session",
        settings=_settings(dev_auth=False),
        json={"init_data": init_data},
    )
    assert dev.status == telegram.status == 200
    assert [row["user_id"] for row in _event_rows("miniapp_opened")] == [
        USER_A,
        USER_B,
    ]


def test_invalid_or_forbidden_session_bootstrap_records_no_opened():
    invalid = _request(
        "POST",
        "/app/v1/session",
        settings=_settings(dev_auth=False),
        json={"init_data": "invalid"},
    )
    forbidden = _request(
        "POST",
        "/app/v1/session",
        settings=_settings(allowlist=frozenset({USER_B})),
        json={"dev_user_id": USER_A},
    )
    assert invalid.status == 401
    assert forbidden.status == 403
    assert _event_rows("miniapp_opened") == []


def test_analytics_failure_does_not_break_session(monkeypatch):
    monkeypatch.setattr(
        "web_api.routes.session.track_miniapp_event_safely",
        lambda *_args: False,
    )
    response = _request(
        "POST",
        "/app/v1/session",
        json={"dev_user_id": USER_A},
    )
    assert response.status == 200
    assert _json(response)["data"]["session_token"] == dev_session_token(USER_A)


def test_tour_create_tracks_once_and_validation_failure_tracks_nothing():
    first = _create_tour(key="create-once")
    replay = _create_tour(key="create-once")
    invalid = _create_tour(key="invalid", payload={"title": "missing fields"})
    assert first.status == replay.status == 201
    assert invalid.status == 400
    assert len(_event_rows("miniapp_tour_created")) == 1


def test_day_off_update_and_delete_track_success_events():
    day_off = _request(
        "POST",
        "/app/v1/day-offs",
        headers=_headers(key="day-off"),
        json={"startDate": "2027-03-01", "endDate": "2027-03-01"},
    )
    assert day_off.status == 201

    created = _create_tour(key="for-update")
    entry_id = _json(created)["data"]["id"]
    updated = _request(
        "PATCH",
        f"/app/v1/entries/{entry_id}",
        headers=_headers(key="update"),
        json=_tour_payload(title="Updated synthetic tour"),
    )
    deleted = _request(
        "DELETE",
        f"/app/v1/entries/{entry_id}",
        headers=_headers(key="delete"),
    )
    assert updated.status == 200
    assert deleted.status == 200
    assert len(_event_rows("miniapp_day_off_created")) == 1
    assert len(_event_rows("miniapp_tour_updated")) == 1
    assert len(_event_rows("miniapp_entry_deleted")) == 1


def test_missing_and_foreign_update_delete_track_no_success_events():
    missing_update = _request(
        "PATCH",
        "/app/v1/entries/999999",
        headers=_headers(key="missing-update"),
        json=_tour_payload(),
    )
    missing_delete = _request(
        "DELETE",
        "/app/v1/entries/999999",
        headers=_headers(key="missing-delete"),
    )
    created = _create_tour(user_id=USER_B, key="foreign-source")
    entry_id = _json(created)["data"]["id"]
    foreign_update = _request(
        "PATCH",
        f"/app/v1/entries/{entry_id}",
        headers=_headers(USER_A, "foreign-update"),
        json=_tour_payload(),
    )
    foreign_delete = _request(
        "DELETE",
        f"/app/v1/entries/{entry_id}",
        headers=_headers(USER_A, "foreign-delete"),
    )
    assert [
        missing_update.status,
        missing_delete.status,
        foreign_update.status,
        foreign_delete.status,
    ] == [404, 404, 404, 404]
    assert _event_rows("miniapp_tour_updated") == []
    assert _event_rows("miniapp_entry_deleted") == []


def test_analytics_failure_does_not_break_mutation_or_domain_write(monkeypatch):
    monkeypatch.setattr(
        "web_api.routes.entries.track_miniapp_event_safely",
        lambda *_args: False,
    )
    response = _create_tour(key="analytics-failure")
    assert response.status == 201
    entry_id = _json(response)["data"]["id"]
    get_response = _request(
        "GET",
        f"/app/v1/entries/{entry_id}",
        headers=_headers(key="unused"),
    )
    assert get_response.status == 200
    assert _event_rows("miniapp_tour_created") == []


def test_error_and_logs_do_not_expose_body_values(caplog):
    private_value = "private-company-and-income-value"
    with caplog.at_level(logging.INFO):
        response = _request(
            "POST",
            "/app/v1/analytics/events",
            headers=_headers(),
            json={"name": "miniapp_calendar_opened", "company": private_value},
        )
    assert response.status == 400
    assert private_value not in response._body_text
    assert private_value not in caplog.text


def test_analytics_route_registered_once_in_standalone_and_combined_runtime():
    standalone = create_miniapp_api_app(_settings())
    standalone_routes = [
        route
        for route in standalone.router.routes()
        if route.method == "POST"
        and route.resource.canonical == "/app/v1/analytics/events"
    ]
    assert len(standalone_routes) == 1

    combined = web.Application()
    combined.router.add_get("/integration-health", lambda _request: web.Response())
    register_miniapp_api_on_app(combined, _settings())
    combined_routes = [
        route
        for route in combined.router.routes()
        if route.method == "POST"
        and route.resource.canonical == "/app/v1/analytics/events"
    ]
    assert len(combined_routes) == 1


def test_no_analytics_case_accepts_http_500():
    responses = [
        _analytics(),
        _analytics("unknown", key="unknown"),
        _request(
            "POST",
            "/app/v1/analytics/events",
            headers={"Content-Type": "application/json", "Idempotency-Key": "missing-auth"},
            json={"name": "miniapp_calendar_opened"},
        ),
    ]
    assert [response.status for response in responses] == [200, 400, 401]
