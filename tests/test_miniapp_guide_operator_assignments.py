"""GO6B1: Mini App API transport for Guide Operator assignments."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from aiohttp.test_utils import TestClient, TestServer

from database.queries import (
    count_guide_operator_projections,
    get_guide_os_id,
    get_guide_operator_decision,
    list_guide_operator_outbox_events,
    register_user,
)
from services.guide_operator_assignment_service import (
    AssignmentOfferIntake,
    receive_assignment_offer,
)
from services.guide_operator_connection_service import (
    ensure_confirmed_connection_for_tests,
)
from services.miniapp_api_settings import MiniAppApiSettings
from services.tour_service import save_tour
from utils.constants import STATUS_CONFIRMED
from web_api.app import create_miniapp_api_app
from web_api.auth import dev_session_token

API_USER = 706101
OTHER_USER = 706102
TEST_BOT_TOKEN = "7000000000:TEST_miniapp_synthetic_bot_token"


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


def api_request(method, path, **kwargs):
    async def _call(client):
        return await client.request(method, path, **kwargs)

    return run(_with_client(_call))


@pytest.fixture
def seeded_user():
    register_user(API_USER)
    return API_USER


@pytest.fixture
def other_user():
    register_user(OTHER_USER)
    return OTHER_USER


def _seed_offer(user_id: int, **overrides):
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    assignment_id = overrides.pop("assignment_id", str(uuid4()))
    company_name = overrides.pop("company_name", "Operator Co")
    connection = ensure_confirmed_connection_for_tests(
        guide_os_id, company_name=company_name
    )
    offer = AssignmentOfferIntake(
        event_id=overrides.pop("event_id", str(uuid4())),
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
        company_id=connection["company_id"],
        company_name=company_name,
        guide_connection_id=connection["connection_id"],
        role="main_guide",
        start_date=overrides.pop("start_date", "2026-06-10"),
        end_date=overrides.pop("end_date", "2026-06-12"),
        operator_message="Please confirm",
        working_package={
            "tour": {
                "title": "Bukhara route",
                "city_or_route": "Bukhara",
                "reference": "T-200",
            },
            "assignment": {
                "id": assignment_id,
                "role": "main_guide",
            },
        },
        **overrides,
    )
    receive_assignment_offer(offer)
    return offer


def test_pending_and_detail_require_auth():
    response = api_request("GET", "/app/v1/guide-operator/assignments/pending")
    assert response.status == 401
    body = response_json(response)
    assert body["error"]["code"] == "auth_required"

    response = api_request(
        "GET", f"/app/v1/guide-operator/assignments/{uuid4()}"
    )
    assert response.status == 401


def test_list_pending_and_get_detail_for_session_guide(seeded_user):
    offer = _seed_offer(seeded_user)
    headers = _auth_headers(seeded_user)

    listed = api_request(
        "GET", "/app/v1/guide-operator/assignments/pending", headers=headers
    )
    assert listed.status == 200
    payload = response_json(listed)["data"]
    assert len(payload["assignments"]) == 1
    assert payload["assignments"][0]["id"] == offer.assignment_id
    assert payload["assignments"][0]["status"] == "offered"
    assert "guide_os_id" not in payload["assignments"][0]

    detail = api_request(
        "GET",
        f"/app/v1/guide-operator/assignments/{offer.assignment_id}",
        headers=headers,
    )
    assert detail.status == 200
    data = response_json(detail)["data"]
    assert data["assignment"]["id"] == offer.assignment_id
    assert data["workingPackage"]["tour"]["title"] == "Bukhara route"
    assert data["conflictDates"] == []


def test_wrong_guide_cannot_read_or_decide(seeded_user, other_user):
    offer = _seed_offer(seeded_user)
    other_headers = _auth_headers(other_user)

    listed = api_request(
        "GET",
        "/app/v1/guide-operator/assignments/pending",
        headers=other_headers,
    )
    assert listed.status == 200
    assert response_json(listed)["data"]["assignments"] == []

    detail = api_request(
        "GET",
        f"/app/v1/guide-operator/assignments/{offer.assignment_id}",
        headers=other_headers,
    )
    assert detail.status == 404

    accept = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{offer.assignment_id}/accept",
        headers=other_headers,
        json={
            "decisionEventId": str(uuid4()),
            "guide_os_id": get_guide_os_id(seeded_user),
            "userId": seeded_user,
        },
    )
    assert accept.status == 404


def test_body_identity_spoof_ignored_on_accept(seeded_user, other_user):
    offer = _seed_offer(seeded_user)
    decision_event_id = str(uuid4())
    response = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{offer.assignment_id}/accept",
        headers=_auth_headers(seeded_user),
        json={
            "decisionEventId": decision_event_id,
            "guide_os_id": get_guide_os_id(other_user),
            "userId": other_user,
            "telegramId": str(other_user),
        },
    )
    assert response.status == 200
    data = response_json(response)["data"]
    assert data["status"] == "accepted"
    assert data["decisionEventId"] == decision_event_id
    assert data["projectionTourId"] is not None
    assert count_guide_operator_projections(offer.assignment_id) == 1


def test_accept_conflict_and_decline_preserve_go6a(seeded_user):
    offer = _seed_offer(seeded_user)
    save_tour(
        user_id=seeded_user,
        company="Personal",
        city="Bukhara",
        date_text="2026-06-11",
        status=STATUS_CONFIRMED,
        income=100,
    )

    conflict = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{offer.assignment_id}/accept",
        headers=_auth_headers(seeded_user),
        json={"decisionEventId": str(uuid4())},
    )
    assert conflict.status == 409
    body = response_json(conflict)
    assert body["error"]["code"] == "calendar_conflict"
    assert body["error"]["details"]["dates"] == ["2026-06-11"]
    assert get_guide_operator_decision(offer.assignment_id) is None
    assert count_guide_operator_projections(offer.assignment_id) == 0

    free_offer = _seed_offer(
        seeded_user,
        start_date="2026-07-01",
        end_date="2026-07-02",
    )
    decision_event_id = str(uuid4())
    declined = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{free_offer.assignment_id}/decline",
        headers=_auth_headers(seeded_user),
        json={"decisionEventId": decision_event_id},
    )
    assert declined.status == 200
    data = response_json(declined)["data"]
    assert data["status"] == "declined"
    assert data["projectionTourId"] is None
    assert count_guide_operator_projections(free_offer.assignment_id) == 0

    replay = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{free_offer.assignment_id}/decline",
        headers=_auth_headers(seeded_user),
        json={"decisionEventId": decision_event_id},
    )
    assert replay.status == 200
    assert response_json(replay)["data"]["replayed"] is True
    assert (
        len(
            list_guide_operator_outbox_events(
                assignment_id=free_offer.assignment_id,
                event_type="assignment.decision.v1",
            )
        )
        == 1
    )


def test_repeated_accept_is_idempotent(seeded_user):
    offer = _seed_offer(seeded_user, start_date="2026-08-01", end_date="2026-08-01")
    decision_event_id = str(uuid4())
    first = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{offer.assignment_id}/accept",
        headers=_auth_headers(seeded_user),
        json={"decisionEventId": decision_event_id},
    )
    second = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{offer.assignment_id}/accept",
        headers=_auth_headers(seeded_user),
        json={"decisionEventId": decision_event_id},
    )
    assert first.status == 200
    assert second.status == 200
    assert response_json(second)["data"]["replayed"] is True
    assert count_guide_operator_projections(offer.assignment_id) == 1

    opposite = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{offer.assignment_id}/decline",
        headers=_auth_headers(seeded_user),
        json={"decisionEventId": str(uuid4())},
    )
    assert opposite.status == 409
    assert response_json(opposite)["error"]["code"] == "idempotency_conflict"
