"""GO7E3: Mini App API for critical version confirm/reject."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from aiohttp.test_utils import TestClient, TestServer

from database.queries import (
    count_guide_operator_projections,
    get_guide_operator_critical_version_decision,
    get_guide_os_id,
    get_tour_by_id,
    get_user_id_by_guide_os_id,
    register_user,
)
from services.guide_operator_assignment_service import (
    AssignmentOfferIntake,
    AssignmentVersionPublishedIntake,
    accept_assignment,
    intake_critical_assignment_version,
    receive_assignment_offer,
)
from services.guide_operator_connection_service import (
    ensure_confirmed_connection_for_tests,
)
from services.miniapp_api_settings import MiniAppApiSettings
from services.tour_service import save_tour
from utils.constants import SOURCE_GUIDE_OPERATOR, STATUS_CONFIRMED
from web_api.app import create_miniapp_api_app
from web_api.auth import dev_session_token

API_USER = 706201
OTHER_USER = 706202
TEST_BOT_TOKEN = "7000000000:TEST_miniapp_critical_bot_token"


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
def seeded_guide():
    register_user(API_USER)
    register_user(OTHER_USER)
    guide_os_id = get_guide_os_id(API_USER)
    assert guide_os_id is not None
    return guide_os_id


def _package(assignment_id, guide_os_id, *, start="2026-09-10", end="2026-09-12"):
    return {
        "tour": {"title": "API critical", "city_or_route": "Samarkand", "reference": "T-API"},
        "assignment": {
            "id": assignment_id,
            "guide_os_id": guide_os_id,
            "role": "main_guide",
            "start_date": start,
            "end_date": end,
        },
        "days": [
            {
                "date": start,
                "title": "D1",
                "city_or_route": "Samarkand",
                "events": [
                    {
                        "start_time": "09:00",
                        "end_time": "12:00",
                        "title": "A",
                        "event_type": "tour",
                    }
                ],
            },
            {
                "date": end,
                "title": "D2",
                "city_or_route": "Samarkand",
                "events": [
                    {
                        "start_time": "10:00",
                        "end_time": "13:00",
                        "title": "B",
                        "event_type": "tour",
                    }
                ],
            },
        ],
        "group_summary": "10 pax",
    }


def _seed_pending_critical(guide_os_id: str, *, expand_end: str = "2026-09-14"):
    assignment_id = str(uuid4())
    connection = ensure_confirmed_connection_for_tests(
        guide_os_id, company_name="API Co"
    )
    offer = AssignmentOfferIntake(
        event_id=str(uuid4()),
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
        company_id=connection["company_id"],
        company_name="API Co",
        guide_connection_id=connection["connection_id"],
        role="main_guide",
        start_date="2026-09-10",
        end_date="2026-09-12",
        working_package=_package(assignment_id, guide_os_id),
    )
    receive_assignment_offer(offer)
    accepted = accept_assignment(
        guide_os_id, assignment_id, decision_event_id=str(uuid4())
    )
    next_pkg = _package(assignment_id, guide_os_id, start="2026-09-10", end=expand_end)
    next_pkg["assignment"]["role"] = "assistant_guide"
    next_pkg["tour"]["title"] = "API critical expanded"
    intake_critical_assignment_version(
        AssignmentVersionPublishedIntake(
            event_id=str(uuid4()),
            assignment_id=assignment_id,
            guide_os_id=guide_os_id,
            version_number=2,
            previous_active_version_number=1,
            severity="critical",
            working_package=next_pkg,
            change_summary=[
                {
                    "code": "end_date_changed",
                    "severity": "critical",
                    "path": "assignment.end_date",
                    "before": "2026-09-12",
                    "after": expand_end,
                }
            ],
            published_at="2026-09-02T09:00:00+00:00",
        )
    )
    return assignment_id, accepted.projection_tour_id


def test_detail_exposes_pending_critical_and_lists_indicator(seeded_guide):
    assignment_id, _tour_id = _seed_pending_critical(seeded_guide)
    detail = api_request(
        "GET",
        f"/app/v1/guide-operator/assignments/{assignment_id}",
        headers=_auth_headers(),
    )
    assert detail.status == 200
    body = response_json(detail)["data"]
    assert body["assignment"]["pendingCriticalVersionNumber"] == 2
    assert body["assignment"]["activeVersionNumber"] == 1
    assert body["pendingCriticalVersion"]["versionNumber"] == 2
    assert body["pendingCriticalVersion"]["severity"] == "critical"
    assert body["pendingCriticalVersion"]["changeSummary"]
    assert "workingPackage" in body["pendingCriticalVersion"]
    assert body["workingPackage"]["tour"]["title"] == "API critical"
    assert body["pendingCriticalVersion"]["workingPackage"]["tour"]["title"] == (
        "API critical expanded"
    )

    lists = api_request(
        "GET",
        "/app/v1/guide-operator/assignments/lists",
        headers=_auth_headers(),
    )
    assert lists.status == 200
    rows = response_json(lists)["data"]["upcoming"]
    match = next(row for row in rows if row["id"] == assignment_id)
    assert match["pendingCriticalVersionNumber"] == 2


def test_confirm_critical_api_updates_projection_and_is_idempotent(seeded_guide):
    assignment_id, tour_id = _seed_pending_critical(seeded_guide)
    user_id = get_user_id_by_guide_os_id(seeded_guide)
    decision_event_id = str(uuid4())
    first = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{assignment_id}/confirm-critical",
        headers=_auth_headers(),
        json={"decisionEventId": decision_event_id, "versionNumber": 2},
    )
    assert first.status == 200
    data = response_json(first)["data"]
    assert data["decision"] == "confirm_critical"
    assert data["activeVersionNumber"] == 2
    assert data["pendingCriticalVersionNumber"] is None
    assert data["replayed"] is False

    second = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{assignment_id}/confirm-critical",
        headers=_auth_headers(),
        json={"decisionEventId": decision_event_id, "versionNumber": 2},
    )
    assert second.status == 200
    assert response_json(second)["data"]["replayed"] is True

    detail = api_request(
        "GET",
        f"/app/v1/guide-operator/assignments/{assignment_id}",
        headers=_auth_headers(),
    )
    body = response_json(detail)["data"]
    assert body["pendingCriticalVersion"] is None
    assert body["assignment"]["activeVersionNumber"] == 2
    assert body["assignment"]["endDate"] == "2026-09-14"
    assert count_guide_operator_projections(assignment_id) == 1
    tour = get_tour_by_id(user_id, tour_id)
    assert tour is not None
    assert tour["end_date"] == "2026-09-14"
    assert tour["source"] == SOURCE_GUIDE_OPERATOR
    assert get_guide_operator_critical_version_decision(
        assignment_id=assignment_id, version_number=2
    )["decision_type"] == "confirm_critical"


def test_reject_critical_api_keeps_active_and_history(seeded_guide):
    assignment_id, tour_id = _seed_pending_critical(seeded_guide)
    user_id = get_user_id_by_guide_os_id(seeded_guide)
    before = get_tour_by_id(user_id, tour_id)
    decision_event_id = str(uuid4())
    response = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{assignment_id}/reject-critical",
        headers=_auth_headers(),
        json={"decisionEventId": decision_event_id, "versionNumber": 2},
    )
    assert response.status == 200
    data = response_json(response)["data"]
    assert data["decision"] == "reject_critical"
    assert data["activeVersionNumber"] == 1
    assert data["pendingCriticalVersionNumber"] is None

    detail = api_request(
        "GET",
        f"/app/v1/guide-operator/assignments/{assignment_id}",
        headers=_auth_headers(),
    )
    body = response_json(detail)["data"]
    assert body["pendingCriticalVersion"] is None
    assert body["assignment"]["activeVersionNumber"] == 1
    assert any(v["versionNumber"] == 2 and v["severity"] == "critical" for v in body["versions"])
    assert get_tour_by_id(user_id, tour_id) == before


def test_confirm_conflict_retains_pending_via_api(seeded_guide):
    assignment_id, _tour_id = _seed_pending_critical(
        seeded_guide, expand_end="2026-09-20"
    )
    user_id = get_user_id_by_guide_os_id(seeded_guide)
    save_tour(user_id, "Personal", "City", "2026-09-18", STATUS_CONFIRMED, income=50)

    detail = api_request(
        "GET",
        f"/app/v1/guide-operator/assignments/{assignment_id}",
        headers=_auth_headers(),
    )
    pending = response_json(detail)["data"]["pendingCriticalVersion"]
    assert "2026-09-18" in pending["conflictDates"]

    response = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{assignment_id}/confirm-critical",
        headers=_auth_headers(),
        json={"decisionEventId": str(uuid4()), "versionNumber": 2},
    )
    assert response.status == 409
    err = response_json(response)["error"]
    assert err["code"] == "calendar_conflict"
    assert "2026-09-18" in err["details"]["dates"]

    after = api_request(
        "GET",
        f"/app/v1/guide-operator/assignments/{assignment_id}",
        headers=_auth_headers(),
    )
    body = response_json(after)["data"]
    assert body["assignment"]["pendingCriticalVersionNumber"] == 2
    assert body["assignment"]["activeVersionNumber"] == 1


def test_critical_api_isolation_and_stale(seeded_guide):
    assignment_id, _tour_id = _seed_pending_critical(seeded_guide)
    other = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{assignment_id}/confirm-critical",
        headers=_auth_headers(OTHER_USER),
        json={"decisionEventId": str(uuid4()), "versionNumber": 2},
    )
    assert other.status == 404

    wrong_version = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{assignment_id}/confirm-critical",
        headers=_auth_headers(),
        json={"decisionEventId": str(uuid4()), "versionNumber": 3},
    )
    assert wrong_version.status == 409
