"""GO6B5/GO7B2: guide-facing assignment lifecycle lists."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from database.queries import (
    count_guide_operator_projections,
    get_guide_os_id,
    register_user,
)
from services.guide_operator_connection_service import (
    ensure_confirmed_connection_for_tests,
)
from services.guide_operator_assignment_service import (
    AssignmentCancellationIntake,
    AssignmentOfferIntake,
    accept_assignment,
    apply_assignment_cancellation,
    decline_assignment,
    get_assignment_for_guide,
    list_assignment_lifecycle,
    receive_assignment_offer,
)

from tests.test_miniapp_guide_operator_assignments import (
    API_USER,
    OTHER_USER,
    _auth_headers,
    api_request,
    response_json,
)


def _offer(
    guide_os_id: str,
    *,
    assignment_id: str | None = None,
    start_date: str,
    end_date: str,
    company_name: str = "Operator Co",
) -> AssignmentOfferIntake:
    assignment_id = assignment_id or str(uuid4())
    connection = ensure_confirmed_connection_for_tests(
        guide_os_id, company_name=company_name
    )
    return AssignmentOfferIntake(
        event_id=str(uuid4()),
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
        company_id=connection["company_id"],
        company_name=company_name,
        guide_connection_id=connection["connection_id"],
        role="main_guide",
        start_date=start_date,
        end_date=end_date,
        operator_message=None,
        working_package={
            "tour": {
                "title": company_name,
                "city_or_route": "City",
                "reference": "T-1",
            },
            "assignment": {
                "id": assignment_id,
                "role": "main_guide",
                "start_date": start_date,
                "end_date": end_date,
            },
            "days": [
                {
                    "date": start_date,
                    "title": "Day 1",
                    "city_or_route": "City",
                }
            ],
        },
    )


def _seed(user_id: int) -> str:
    register_user(user_id)
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    return guide_os_id


def _accept(guide_os_id: str, offer: AssignmentOfferIntake) -> None:
    receive_assignment_offer(offer)
    accept_assignment(
        guide_os_id,
        offer.assignment_id,
        decision_event_id=str(uuid4()),
    )


def test_lifecycle_partitions_by_business_date_boundaries():
    guide_os_id = _seed(7201)
    today = date(2026, 8, 28)

    offered = _offer(guide_os_id, start_date="2026-10-01", end_date="2026-10-02")
    receive_assignment_offer(offered)

    upcoming_early = _offer(
        guide_os_id,
        start_date="2026-09-03",
        end_date="2026-09-03",
        company_name="Sort Earlier",
    )
    _accept(guide_os_id, upcoming_early)
    upcoming_late = _offer(
        guide_os_id,
        start_date="2026-09-05",
        end_date="2026-09-05",
        company_name="Sort Later",
    )
    _accept(guide_os_id, upcoming_late)

    in_progress_start = _offer(
        guide_os_id,
        start_date="2026-08-28",
        end_date="2026-08-28",
        company_name="Start Today",
    )
    _accept(guide_os_id, in_progress_start)

    completed_newer = _offer(
        guide_os_id,
        start_date="2026-08-15",
        end_date="2026-08-20",
        company_name="Completed Newer",
    )
    _accept(guide_os_id, completed_newer)
    completed_older = _offer(
        guide_os_id,
        start_date="2026-07-01",
        end_date="2026-07-05",
        company_name="Completed Older",
    )
    _accept(guide_os_id, completed_older)

    just_ended = _offer(
        guide_os_id,
        start_date="2026-08-25",
        end_date="2026-08-27",
        company_name="Just Ended",
    )
    _accept(guide_os_id, just_ended)

    tomorrow = _offer(
        guide_os_id,
        start_date="2026-08-29",
        end_date="2026-08-29",
        company_name="Tomorrow",
    )
    _accept(guide_os_id, tomorrow)

    buckets = list_assignment_lifecycle(guide_os_id, as_of=today)
    assert buckets["as_of_date"] == "2026-08-28"
    assert [r["assignment_id"] for r in buckets["awaiting"]] == [offered.assignment_id]

    upcoming_starts = [r["start_date"] for r in buckets["upcoming"]]
    assert upcoming_starts == sorted(upcoming_starts)
    assert upcoming_starts[0] == "2026-08-29"
    assert "2026-09-03" in upcoming_starts
    assert "2026-09-05" in upcoming_starts

    in_ids = {r["assignment_id"] for r in buckets["in_progress"]}
    assert in_progress_start.assignment_id in in_ids
    assert just_ended.assignment_id not in in_ids
    assert tomorrow.assignment_id not in in_ids

    completed_names = [r["company_name"] for r in buckets["completed"]]
    assert completed_names[0] == "Just Ended"
    assert completed_names.index("Just Ended") < completed_names.index("Completed Newer")
    assert completed_names.index("Completed Newer") < completed_names.index(
        "Completed Older"
    )
    assert "Just Ended" in completed_names


def test_lifecycle_inclusive_end_equals_today():
    guide_os_id = _seed(7204)
    today = date(2026, 8, 28)
    offer = _offer(
        guide_os_id,
        start_date="2026-08-20",
        end_date="2026-08-28",
        company_name="Ends Today",
    )
    _accept(guide_os_id, offer)
    buckets = list_assignment_lifecycle(guide_os_id, as_of=today)
    assert [r["assignment_id"] for r in buckets["in_progress"]] == [offer.assignment_id]
    assert buckets["completed"] == []
    assert buckets["upcoming"] == []


def test_lifecycle_excludes_declined_and_other_guides():
    owner = _seed(7202)
    stranger = _seed(7203)
    today = date(2026, 8, 28)

    offer = _offer(owner, start_date="2026-09-10", end_date="2026-09-11")
    receive_assignment_offer(offer)
    decline_assignment(owner, offer.assignment_id, decision_event_id=str(uuid4()))

    accepted = _offer(owner, start_date="2026-09-01", end_date="2026-09-02")
    _accept(owner, accepted)

    stranger_offer = _offer(stranger, start_date="2026-09-03", end_date="2026-09-03")
    receive_assignment_offer(stranger_offer)

    owner_buckets = list_assignment_lifecycle(owner, as_of=today)
    assert owner_buckets["awaiting"] == []
    assert [r["assignment_id"] for r in owner_buckets["upcoming"]] == [
        accepted.assignment_id
    ]

    stranger_buckets = list_assignment_lifecycle(stranger, as_of=today)
    assert [r["assignment_id"] for r in stranger_buckets["awaiting"]] == [
        stranger_offer.assignment_id
    ]
    assert stranger_buckets["upcoming"] == []


def test_lists_api_requires_auth_and_keeps_pending_compatible():
    register_user(API_USER)
    register_user(OTHER_USER)
    owner_id = get_guide_os_id(API_USER)
    other_id = get_guide_os_id(OTHER_USER)
    assert owner_id and other_id

    offer = _offer(owner_id, start_date="2026-09-10", end_date="2026-09-12")
    receive_assignment_offer(offer)
    other_offer = _offer(other_id, start_date="2026-09-15", end_date="2026-09-15")
    receive_assignment_offer(other_offer)

    unauth = api_request("GET", "/app/v1/guide-operator/assignments/lists")
    assert unauth.status == 401

    headers = _auth_headers(API_USER)
    pending = api_request(
        "GET", "/app/v1/guide-operator/assignments/pending", headers=headers
    )
    assert pending.status == 200
    pending_body = response_json(pending)["data"]
    assert {row["id"] for row in pending_body["assignments"]} == {offer.assignment_id}

    lists = api_request(
        "GET", "/app/v1/guide-operator/assignments/lists", headers=headers
    )
    assert lists.status == 200
    data = response_json(lists)["data"]
    assert "asOfDate" in data
    assert {row["id"] for row in data["awaiting"]} == {offer.assignment_id}
    assert other_offer.assignment_id not in {row["id"] for row in data["awaiting"]}
    assert data["upcoming"] == []
    assert data["inProgress"] == []
    assert data["completed"] == []
    assert data["cancelled"] == []


def test_cancelled_section_isolation_sorting_and_detail():
    owner = _seed(7210)
    stranger = _seed(7211)
    today = date(2026, 8, 28)

    older = _offer(owner, start_date="2026-09-01", end_date="2026-09-02", company_name="Older Cancel")
    _accept(owner, older)
    apply_assignment_cancellation(
        AssignmentCancellationIntake(
            event_id=str(uuid4()),
            assignment_id=older.assignment_id,
            guide_os_id=owner,
            version_number=1,
            cancelled_at="2026-08-10T09:00:00+00:00",
        )
    )

    newer = _offer(owner, start_date="2026-10-01", end_date="2026-10-03", company_name="Newer Cancel")
    _accept(owner, newer)
    apply_assignment_cancellation(
        AssignmentCancellationIntake(
            event_id=str(uuid4()),
            assignment_id=newer.assignment_id,
            guide_os_id=owner,
            version_number=1,
            cancelled_at="2026-08-20T14:00:00+00:00",
        )
    )

    still_upcoming = _offer(
        owner, start_date="2026-09-15", end_date="2026-09-16", company_name="Still Upcoming"
    )
    _accept(owner, still_upcoming)

    stranger_cancelled = _offer(
        stranger, start_date="2026-09-05", end_date="2026-09-06", company_name="Stranger"
    )
    _accept(stranger, stranger_cancelled)
    apply_assignment_cancellation(
        AssignmentCancellationIntake(
            event_id=str(uuid4()),
            assignment_id=stranger_cancelled.assignment_id,
            guide_os_id=stranger,
            version_number=1,
            cancelled_at="2026-08-25T10:00:00+00:00",
        )
    )

    buckets = list_assignment_lifecycle(owner, as_of=today)
    cancelled_ids = [r["assignment_id"] for r in buckets["cancelled"]]
    assert cancelled_ids == [newer.assignment_id, older.assignment_id]
    assert buckets["cancelled"][0]["cancelled_at"] == "2026-08-20T14:00:00+00:00"
    assert stranger_cancelled.assignment_id not in cancelled_ids
    assert newer.assignment_id not in {r["assignment_id"] for r in buckets["upcoming"]}
    assert newer.assignment_id not in {r["assignment_id"] for r in buckets["completed"]}
    assert newer.assignment_id not in {r["assignment_id"] for r in buckets["in_progress"]}
    assert newer.assignment_id not in {r["assignment_id"] for r in buckets["awaiting"]}
    assert [r["assignment_id"] for r in buckets["upcoming"]] == [
        still_upcoming.assignment_id
    ]
    assert count_guide_operator_projections(newer.assignment_id) == 0

    stored = get_assignment_for_guide(owner, newer.assignment_id)
    assert stored["status"] == "cancelled"
    assert stored["projection_tour_id"] is None

    register_user(API_USER)
    api_owner = get_guide_os_id(API_USER)
    assert api_owner
    api_offer = _offer(api_owner, start_date="2026-11-01", end_date="2026-11-02")
    _accept(api_owner, api_offer)
    apply_assignment_cancellation(
        AssignmentCancellationIntake(
            event_id=str(uuid4()),
            assignment_id=api_offer.assignment_id,
            guide_os_id=api_owner,
            version_number=1,
            cancelled_at="2026-08-28T11:00:00+00:00",
        )
    )

    lists = api_request(
        "GET",
        "/app/v1/guide-operator/assignments/lists",
        headers=_auth_headers(API_USER),
    )
    assert lists.status == 200
    data = response_json(lists)["data"]
    assert {row["id"] for row in data["cancelled"]} == {api_offer.assignment_id}
    assert data["cancelled"][0]["cancelledAt"] == "2026-08-28T11:00:00+00:00"
    assert data["cancelled"][0]["projectionTourId"] is None

    pending = api_request(
        "GET",
        "/app/v1/guide-operator/assignments/pending",
        headers=_auth_headers(API_USER),
    )
    assert api_offer.assignment_id not in {
        row["id"] for row in response_json(pending)["data"]["assignments"]
    }

    detail = api_request(
        "GET",
        f"/app/v1/guide-operator/assignments/{api_offer.assignment_id}",
        headers=_auth_headers(API_USER),
    )
    assert detail.status == 200
    body = response_json(detail)["data"]
    assert body["assignment"]["status"] == "cancelled"
    assert body["assignment"]["cancelledAt"] == "2026-08-28T11:00:00+00:00"
    assert body["workingPackage"]["tour"]["title"]
    assert body["conflictDates"] == []
