"""GO6A: Guide Operator assignment intake, decision, and calendar projection."""

from __future__ import annotations

import sqlite3
from uuid import uuid4

import pytest

from database.db import get_connection
from database.queries import (
    count_guide_operator_projections,
    get_guide_operator_decision,
    get_guide_os_id,
    get_tour_by_id,
    get_user_id_by_guide_os_id,
    list_guide_operator_outbox_events,
    register_user,
)
from services import guide_operator_assignment_service as go_assignments
from services.guide_operator_connection_service import (
    ensure_confirmed_connection_for_tests,
)
from services.guide_operator_assignment_service import (
    AssignmentConflictError,
    AssignmentNotFoundError,
    AssignmentOfferIntake,
    CalendarConflictError,
    accept_assignment,
    decline_assignment,
    find_assignment_conflicts,
    get_assignment_for_guide,
    list_pending_offers,
    receive_assignment_offer,
)
from services.tour_service import (
    TourEntryDraft,
    delete_tour,
    edit_tour_company,
    edit_tour_note,
    save_tour,
    update_tour_entry,
)
from utils.constants import SOURCE_GUIDE_OPERATOR, STATUS_CONFIRMED


def _seed_guide(user_id: int = 501) -> str:
    register_user(user_id)
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    assert get_user_id_by_guide_os_id(guide_os_id) == user_id
    return guide_os_id


def _offer(
    guide_os_id: str,
    *,
    assignment_id: str | None = None,
    event_id: str | None = None,
    start_date: str = "2026-04-17",
    end_date: str = "2026-04-19",
    company_name: str = "Operator Co",
) -> AssignmentOfferIntake:
    assignment_id = assignment_id or str(uuid4())
    connection = ensure_confirmed_connection_for_tests(
        guide_os_id, company_name=company_name
    )
    return AssignmentOfferIntake(
        event_id=event_id or str(uuid4()),
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
        company_id=connection["company_id"],
        company_name=company_name,
        guide_connection_id=connection["connection_id"],
        role="main_guide",
        start_date=start_date,
        end_date=end_date,
        operator_message="Please confirm",
        working_package={
            "tour": {
                "title": "Samarkand classic",
                "city_or_route": "Samarkand",
                "reference": "T-100",
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
                    "city_or_route": "Samarkand",
                },
                {
                    "date": end_date,
                    "title": "Day last",
                    "city_or_route": "Bukhara",
                },
            ],
        },
    )


def test_wrong_guide_cannot_read_or_decide_offer():
    owner = _seed_guide(601)
    stranger = _seed_guide(602)
    offer = _offer(owner)
    receive_assignment_offer(offer)

    with pytest.raises(AssignmentNotFoundError):
        get_assignment_for_guide(stranger, offer.assignment_id)

    assert list_pending_offers(stranger) == []
    assert len(list_pending_offers(owner)) == 1

    with pytest.raises(AssignmentNotFoundError):
        accept_assignment(
            stranger,
            offer.assignment_id,
            decision_event_id=str(uuid4()),
        )


def test_duplicate_offer_event_is_idempotent_and_conflicting_payload_fails():
    guide_os_id = _seed_guide(603)
    offer = _offer(guide_os_id)
    first = receive_assignment_offer(offer)
    second = receive_assignment_offer(offer)
    assert first["assignment_id"] == second["assignment_id"]
    assert first["status"] == "offered"
    assert len(list_pending_offers(guide_os_id)) == 1

    conflicting = AssignmentOfferIntake(
        event_id=offer.event_id,
        assignment_id=offer.assignment_id,
        guide_os_id=guide_os_id,
        company_id=offer.company_id,
        company_name="Other company",
        guide_connection_id=offer.guide_connection_id,
        role=offer.role,
        start_date=offer.start_date,
        end_date=offer.end_date,
        working_package=offer.working_package,
    )
    with pytest.raises(AssignmentConflictError):
        receive_assignment_offer(conflicting)


def test_accept_creates_exactly_one_projection_and_outbox_event():
    guide_os_id = _seed_guide(604)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    receive_assignment_offer(offer)

    decision_event_id = str(uuid4())
    result = accept_assignment(
        guide_os_id,
        offer.assignment_id,
        decision_event_id=decision_event_id,
    )

    assert result.status == "accepted"
    assert result.projection_tour_id is not None
    assert count_guide_operator_projections(offer.assignment_id) == 1

    tour = get_tour_by_id(user_id, result.projection_tour_id)
    assert tour is not None
    assert tour["source"] == SOURCE_GUIDE_OPERATOR
    assert tour["status"] == STATUS_CONFIRMED
    assert tour["start_date"] == "2026-04-17"
    assert tour["end_date"] == "2026-04-19"
    assert tour["income"] is None
    assert tour["day_locations_json"] is not None
    assert "2026-04-17" in tour["day_locations_json"]
    assert "Samarkand" in tour["day_locations_json"]

    from services.tour_service import get_entry, list_entries
    from web_api.dto import entry_to_api

    entry = get_entry(user_id, str(result.projection_tour_id))
    assert entry is not None
    assert entry["guide_operator_assignment_id"] == offer.assignment_id
    assert entry["guide_operator_version"] == 1
    assert entry["income"] is None
    assert entry["payment"] is None
    api = entry_to_api(entry)
    assert api["guideOperatorAssignmentId"] == offer.assignment_id
    assert api["guideOperatorVersion"] == 1
    assert api["source"] == "Guide Operator"
    assert api["income"] is None
    assert api["payment"] is None
    listed = list_entries(user_id, "2026-04-01", "2026-04-30")
    assert any(
        row.get("guide_operator_assignment_id") == offer.assignment_id for row in listed
    )

    outbox = list_guide_operator_outbox_events(
        assignment_id=offer.assignment_id, event_type="assignment.decision.v1"
    )
    assert len(outbox) == 1
    assert outbox[0]["event_id"] == decision_event_id
    assert list_pending_offers(guide_os_id) == []


def test_repeated_accept_is_idempotent_and_does_not_duplicate_projection():
    guide_os_id = _seed_guide(605)
    offer = _offer(guide_os_id)
    receive_assignment_offer(offer)
    decision_event_id = str(uuid4())

    first = accept_assignment(
        guide_os_id, offer.assignment_id, decision_event_id=decision_event_id
    )
    second = accept_assignment(
        guide_os_id, offer.assignment_id, decision_event_id=decision_event_id
    )

    assert second.replayed is True
    assert second.projection_tour_id == first.projection_tour_id
    assert count_guide_operator_projections(offer.assignment_id) == 1
    assert len(list_guide_operator_outbox_events(assignment_id=offer.assignment_id)) == 1

    with pytest.raises(AssignmentConflictError):
        decline_assignment(
            guide_os_id,
            offer.assignment_id,
            decision_event_id=str(uuid4()),
        )


def test_calendar_conflict_blocks_acceptance_without_projection_or_decision():
    guide_os_id = _seed_guide(606)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    save_tour(
        user_id=user_id,
        company="Personal",
        city="Bukhara",
        date_text="2026-04-18",
        status=STATUS_CONFIRMED,
        income=100,
    )
    offer = _offer(guide_os_id)
    receive_assignment_offer(offer)

    conflicts = find_assignment_conflicts(guide_os_id, offer.assignment_id)
    assert "2026-04-18" in conflicts

    with pytest.raises(CalendarConflictError) as exc_info:
        accept_assignment(
            guide_os_id,
            offer.assignment_id,
            decision_event_id=str(uuid4()),
        )

    assert exc_info.value.details["dates"] == ["2026-04-18"]
    assert get_guide_operator_decision(offer.assignment_id) is None
    assert count_guide_operator_projections(offer.assignment_id) == 0
    assert list_guide_operator_outbox_events(assignment_id=offer.assignment_id) == []
    assert get_assignment_for_guide(guide_os_id, offer.assignment_id)["status"] == "offered"


def test_failed_acceptance_rolls_back_decision_projection_and_outbox(monkeypatch):
    guide_os_id = _seed_guide(607)
    offer = _offer(guide_os_id)
    receive_assignment_offer(offer)

    def boom():
        raise RuntimeError("forced accept failure")

    monkeypatch.setattr(go_assignments, "_ACCEPT_FAILURE_HOOK", boom)

    with pytest.raises(RuntimeError, match="forced accept failure"):
        accept_assignment(
            guide_os_id,
            offer.assignment_id,
            decision_event_id=str(uuid4()),
        )

    assert get_assignment_for_guide(guide_os_id, offer.assignment_id)["status"] == "offered"
    assert get_guide_operator_decision(offer.assignment_id) is None
    assert count_guide_operator_projections(offer.assignment_id) == 0
    assert list_guide_operator_outbox_events(assignment_id=offer.assignment_id) == []


def test_decline_has_no_calendar_occupancy_and_is_repeatable():
    guide_os_id = _seed_guide(608)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id, start_date="2026-05-01", end_date="2026-05-03")
    receive_assignment_offer(offer)
    decision_event_id = str(uuid4())

    result = decline_assignment(
        guide_os_id, offer.assignment_id, decision_event_id=decision_event_id
    )
    assert result.status == "declined"
    assert result.projection_tour_id is None
    assert count_guide_operator_projections(offer.assignment_id) == 0
    assert find_assignment_conflicts(guide_os_id, offer.assignment_id) == []

    replay = decline_assignment(
        guide_os_id, offer.assignment_id, decision_event_id=decision_event_id
    )
    assert replay.replayed is True
    assert list_guide_operator_outbox_events(assignment_id=offer.assignment_id)
    save_tour(
        user_id=user_id,
        company="Personal after decline",
        city="Khiva",
        date_text="2026-05-02",
        status=STATUS_CONFIRMED,
        income=50,
    )


def test_operator_projection_is_protected_from_personal_tour_mutation():
    guide_os_id = _seed_guide(609)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    receive_assignment_offer(offer)
    result = accept_assignment(
        guide_os_id,
        offer.assignment_id,
        decision_event_id=str(uuid4()),
    )
    tour_id = result.projection_tour_id
    assert tour_id is not None

    assert edit_tour_company(user_id, tour_id, "Hacked") is False
    assert edit_tour_note(user_id, tour_id, "changed") is False
    assert delete_tour(user_id, tour_id) is False
    assert (
        update_tour_entry(
            user_id,
            str(tour_id),
            TourEntryDraft(
                title="Hacked",
                company="Hacked",
                location="Nowhere",
                start_date="2026-04-17",
                end_date="2026-04-19",
            ),
        )
        is None
    )

    still = get_tour_by_id(user_id, tour_id)
    assert still is not None
    assert still["company"] == "Operator Co"
    assert still["source"] == SOURCE_GUIDE_OPERATOR

    conn = get_connection()
    with pytest.raises(sqlite3.IntegrityError, match="operator-managed"):
        conn.execute("UPDATE tours SET company = ? WHERE id = ?", ("SQL hack", tour_id))
        conn.commit()
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="operator-managed"):
        conn.execute("DELETE FROM tours WHERE id = ?", (tour_id,))
        conn.commit()
    conn.close()

    still = get_tour_by_id(user_id, tour_id)
    assert still is not None
    assert still["company"] == "Operator Co"
