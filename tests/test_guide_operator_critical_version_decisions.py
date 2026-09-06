"""GO7E2: guide confirm/reject of one pending critical assignment version."""

from __future__ import annotations

import copy
from uuid import uuid4

import pytest

from database.queries import (
    count_guide_operator_projections,
    get_guide_operator_assignment_version,
    get_guide_operator_critical_version_decision,
    get_guide_operator_version_acknowledgement,
    get_guide_os_id,
    get_tour_by_id,
    get_user_id_by_guide_os_id,
    list_guide_operator_assignment_versions,
    register_user,
)
from services import guide_operator_assignment_service as go_assignments
from services.guide_operator_connection_service import (
    ensure_confirmed_connection_for_tests,
)
from services.guide_operator_assignment_service import (
    AssignmentCancellationIntake,
    AssignmentConflictError,
    AssignmentNotActionableError,
    AssignmentNotFoundError,
    AssignmentOfferIntake,
    AssignmentValidationError,
    AssignmentVersionPublishedIntake,
    CRITICAL_VERSION_DECISION_EVENT_TYPE,
    CalendarConflictError,
    accept_assignment,
    apply_assignment_cancellation,
    decide_critical_assignment_version,
    get_assignment_for_guide,
    intake_critical_assignment_version,
    list_critical_version_decision_outbox,
    receive_assignment_offer,
)
from services.tour_service import save_tour
from utils.constants import SOURCE_GUIDE_OPERATOR, STATUS_CONFIRMED


def _seed_guide(user_id: int = 1001) -> str:
    register_user(user_id)
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    return guide_os_id


def _package(
    assignment_id: str,
    guide_os_id: str,
    *,
    start_date: str = "2026-08-10",
    end_date: str = "2026-08-12",
    role: str = "main_guide",
    title: str = "Critical base",
    city: str = "Samarkand",
    group_summary: str = "10 pax",
) -> dict:
    return {
        "tour": {
            "title": title,
            "city_or_route": city,
            "reference": "T-CRIT-DEC",
        },
        "assignment": {
            "id": assignment_id,
            "guide_os_id": guide_os_id,
            "role": role,
            "start_date": start_date,
            "end_date": end_date,
        },
        "days": [
            {
                "date": start_date,
                "title": "Day 1",
                "city_or_route": city,
                "events": [
                    {
                        "start_time": "09:00",
                        "end_time": "12:00",
                        "title": "Morning",
                        "event_type": "tour",
                    }
                ],
            },
            {
                "date": end_date,
                "title": "Day last",
                "city_or_route": city,
                "events": [
                    {
                        "start_time": "10:00",
                        "end_time": "13:00",
                        "title": "Museum",
                        "event_type": "tour",
                    }
                ],
            },
        ],
        "group_summary": group_summary,
        "working_conditions": "Lunch included",
        "drivers": [{"name": "Ali", "phone": "+99890"}],
        "contacts": [{"name": "Ops", "phone": "+99891"}],
    }


def _offer(
    guide_os_id: str,
    *,
    assignment_id: str | None = None,
    start_date: str = "2026-08-10",
    end_date: str = "2026-08-12",
) -> AssignmentOfferIntake:
    assignment_id = assignment_id or str(uuid4())
    connection = ensure_confirmed_connection_for_tests(guide_os_id)
    return AssignmentOfferIntake(
        event_id=str(uuid4()),
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
        company_id=connection["company_id"],
        company_name="Operator Co",
        guide_connection_id=connection["connection_id"],
        role="main_guide",
        start_date=start_date,
        end_date=end_date,
        working_package=_package(
            assignment_id, guide_os_id, start_date=start_date, end_date=end_date
        ),
    )


def _accept(guide_os_id: str, offer: AssignmentOfferIntake):
    receive_assignment_offer(offer)
    return accept_assignment(
        guide_os_id,
        offer.assignment_id,
        decision_event_id=str(uuid4()),
    )


def _critical_event(
    guide_os_id: str,
    assignment_id: str,
    working_package: dict,
    *,
    change_code: str = "start_date_changed",
    path: str = "assignment.start_date",
) -> AssignmentVersionPublishedIntake:
    return AssignmentVersionPublishedIntake(
        event_id=str(uuid4()),
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
        version_number=2,
        previous_active_version_number=1,
        severity="critical",
        working_package=working_package,
        change_summary=[
            {
                "code": change_code,
                "severity": "critical",
                "path": path,
                "change": "updated",
            }
        ],
        published_at="2026-08-02T09:00:00+00:00",
    )


def _with_dates(
    offer: AssignmentOfferIntake,
    *,
    start_date: str,
    end_date: str,
    role: str | None = None,
    title: str | None = None,
    city: str | None = None,
) -> dict:
    package = copy.deepcopy(offer.working_package)
    package["assignment"]["start_date"] = start_date
    package["assignment"]["end_date"] = end_date
    if role is not None:
        package["assignment"]["role"] = role
    if title is not None:
        package["tour"]["title"] = title
    if city is not None:
        package["tour"]["city_or_route"] = city
        package["days"][0]["city_or_route"] = city
        package["days"][1]["city_or_route"] = city
    package["days"][0]["date"] = start_date
    package["days"][1]["date"] = end_date
    return package


def _intake_shifted(guide_os_id: str, offer: AssignmentOfferIntake, package: dict):
    event = _critical_event(guide_os_id, offer.assignment_id, package)
    return intake_critical_assignment_version(event), event


def test_reject_critical_keeps_active_and_clears_pending():
    guide_os_id = _seed_guide(1001)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    before = get_tour_by_id(user_id, tour_id)
    package = _with_dates(offer, start_date="2026-08-11", end_date="2026-08-13")
    _intake_shifted(guide_os_id, offer, package)

    decision_event_id = str(uuid4())
    result = decide_critical_assignment_version(
        guide_os_id,
        offer.assignment_id,
        version_number=2,
        decision="reject_critical",
        decision_event_id=decision_event_id,
    )

    assert result.replayed is False
    assert result.decision == "reject_critical"
    assert result.pending_critical_version_number is None
    assert result.active_version_number == 1
    assert result.projection_tour_id == tour_id

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["pending_critical_version_number"] is None
    assert int(stored["active_version_number"]) == 1
    assert stored["start_date"] == offer.start_date
    assert stored["end_date"] == offer.end_date
    assert stored["role"] == "main_guide"
    assert stored["projection_tour_id"] == tour_id

    after = get_tour_by_id(user_id, tour_id)
    assert after == before
    assert get_guide_operator_assignment_version(offer.assignment_id, 2) is not None
    assert get_guide_operator_critical_version_decision(
        assignment_id=offer.assignment_id, version_number=2
    )["decision_type"] == "reject_critical"
    acks = list_critical_version_decision_outbox(offer.assignment_id)
    assert len(acks) == 1
    assert acks[0]["event_id"] == decision_event_id
    assert acks[0]["event_type"] == CRITICAL_VERSION_DECISION_EVENT_TYPE


def test_confirm_critical_activates_and_updates_exact_one_projection():
    guide_os_id = _seed_guide(1002)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    package = _with_dates(
        offer,
        start_date="2026-08-11",
        end_date="2026-08-14",
        role="assistant_guide",
        title="Expanded critical tour",
        city="Bukhara",
    )
    _intake_shifted(guide_os_id, offer, package)

    result = decide_critical_assignment_version(
        guide_os_id,
        offer.assignment_id,
        version_number=2,
        decision="confirm_critical",
        decision_event_id=str(uuid4()),
    )

    assert result.decision == "confirm_critical"
    assert result.active_version_number == 2
    assert result.pending_critical_version_number is None
    assert result.projection_tour_id == tour_id

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert int(stored["active_version_number"]) == 2
    assert stored["pending_critical_version_number"] is None
    assert stored["start_date"] == "2026-08-11"
    assert stored["end_date"] == "2026-08-14"
    assert stored["role"] == "assistant_guide"
    assert int(stored["active_version_unread"] or 0) == 0
    assert stored["projection_tour_id"] == tour_id
    assert count_guide_operator_projections(offer.assignment_id) == 1

    after = get_tour_by_id(user_id, tour_id)
    assert after is not None
    assert after["start_date"] == "2026-08-11"
    assert after["end_date"] == "2026-08-14"
    assert after["title"] == "Expanded critical tour"
    assert after["city"] == "Bukhara"
    assert after["source"] == SOURCE_GUIDE_OPERATOR
    assert after["income"] is None
    assert get_guide_operator_version_acknowledgement(
        assignment_id=offer.assignment_id, version_number=2
    ) is None
    assert len(list_critical_version_decision_outbox(offer.assignment_id)) == 1


def test_confirm_supports_date_reduction_and_changed_occupancy():
    guide_os_id = _seed_guide(1003)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id, start_date="2026-08-10", end_date="2026-08-15")
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    package = _with_dates(offer, start_date="2026-08-12", end_date="2026-08-13")
    _intake_shifted(guide_os_id, offer, package)

    decide_critical_assignment_version(
        guide_os_id,
        offer.assignment_id,
        version_number=2,
        decision="confirm_critical",
        decision_event_id=str(uuid4()),
    )

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["start_date"] == "2026-08-12"
    assert stored["end_date"] == "2026-08-13"
    after = get_tour_by_id(user_id, tour_id)
    assert after["start_date"] == "2026-08-12"
    assert after["end_date"] == "2026-08-13"
    assert count_guide_operator_projections(offer.assignment_id) == 1


def test_confirm_conflict_retains_pending_and_active_state():
    guide_os_id = _seed_guide(1004)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    before = get_tour_by_id(user_id, tour_id)
    package = _with_dates(offer, start_date="2026-08-20", end_date="2026-08-22")
    _intake_shifted(guide_os_id, offer, package)

    save_tour(
        user_id,
        "Personal Co",
        "Tashkent",
        "2026-08-21",
        STATUS_CONFIRMED,
        income=100,
    )

    with pytest.raises(CalendarConflictError):
        decide_critical_assignment_version(
            guide_os_id,
            offer.assignment_id,
            version_number=2,
            decision="confirm_critical",
            decision_event_id=str(uuid4()),
        )

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["pending_critical_version_number"] == 2
    assert int(stored["active_version_number"]) == 1
    assert stored["start_date"] == offer.start_date
    assert stored["end_date"] == offer.end_date
    assert stored["projection_tour_id"] == tour_id
    assert get_tour_by_id(user_id, tour_id) == before
    assert list_critical_version_decision_outbox(offer.assignment_id) == []
    assert get_guide_operator_critical_version_decision(
        assignment_id=offer.assignment_id, version_number=2
    ) is None


def test_duplicate_decision_replays_and_conflicting_reuse_fails():
    guide_os_id = _seed_guide(1005)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    package = _with_dates(offer, start_date="2026-08-11", end_date="2026-08-13")
    _intake_shifted(guide_os_id, offer, package)
    decision_event_id = str(uuid4())

    first = decide_critical_assignment_version(
        guide_os_id,
        offer.assignment_id,
        version_number=2,
        decision="reject_critical",
        decision_event_id=decision_event_id,
    )
    second = decide_critical_assignment_version(
        guide_os_id,
        offer.assignment_id,
        version_number=2,
        decision="reject_critical",
        decision_event_id=decision_event_id,
    )
    assert first.replayed is False
    assert second.replayed is True
    assert len(list_critical_version_decision_outbox(offer.assignment_id)) == 1

    with pytest.raises(AssignmentConflictError):
        decide_critical_assignment_version(
            guide_os_id,
            offer.assignment_id,
            version_number=2,
            decision="confirm_critical",
            decision_event_id=str(uuid4()),
        )
    with pytest.raises(AssignmentConflictError):
        decide_critical_assignment_version(
            guide_os_id,
            offer.assignment_id,
            version_number=2,
            decision="confirm_critical",
            decision_event_id=decision_event_id,
        )


def test_wrong_guide_and_wrong_version_fail_closed():
    guide_a = _seed_guide(1006)
    guide_b = _seed_guide(1007)
    offer = _offer(guide_a)
    _accept(guide_a, offer)
    package = _with_dates(offer, start_date="2026-08-11", end_date="2026-08-13")
    _intake_shifted(guide_a, offer, package)

    with pytest.raises(AssignmentNotFoundError):
        decide_critical_assignment_version(
            guide_b,
            offer.assignment_id,
            version_number=2,
            decision="confirm_critical",
            decision_event_id=str(uuid4()),
        )
    with pytest.raises(AssignmentConflictError, match="pending"):
        decide_critical_assignment_version(
            guide_a,
            offer.assignment_id,
            version_number=3,
            decision="confirm_critical",
            decision_event_id=str(uuid4()),
        )
    stored = get_assignment_for_guide(guide_a, offer.assignment_id)
    assert stored["pending_critical_version_number"] == 2
    assert int(stored["active_version_number"]) == 1


def test_cancellation_race_wins_as_terminal_state():
    guide_os_id = _seed_guide(1008)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    package = _with_dates(offer, start_date="2026-08-11", end_date="2026-08-13")
    _intake_shifted(guide_os_id, offer, package)

    apply_assignment_cancellation(
        AssignmentCancellationIntake(
            event_id=str(uuid4()),
            assignment_id=offer.assignment_id,
            guide_os_id=guide_os_id,
            version_number=1,
            cancelled_at="2026-08-03T10:00:00+00:00",
        )
    )
    with pytest.raises(AssignmentNotActionableError):
        decide_critical_assignment_version(
            guide_os_id,
            offer.assignment_id,
            version_number=2,
            decision="confirm_critical",
            decision_event_id=str(uuid4()),
        )

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["status"] == "cancelled"
    assert stored["pending_critical_version_number"] is None
    assert int(stored["active_version_number"]) == 1
    assert get_tour_by_id(user_id, tour_id) is None
    assert list_critical_version_decision_outbox(offer.assignment_id) == []
    # Pending snapshot retained historically; never activated.
    assert get_guide_operator_assignment_version(offer.assignment_id, 2) is not None
    assert len(list_guide_operator_assignment_versions(offer.assignment_id)) == 2


def test_failed_critical_decision_rolls_back_atomically(monkeypatch):
    guide_os_id = _seed_guide(1009)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_before = get_tour_by_id(user_id, accepted.projection_tour_id)
    package = _with_dates(offer, start_date="2026-08-11", end_date="2026-08-13")
    _intake_shifted(guide_os_id, offer, package)

    def boom():
        raise RuntimeError("forced critical decision failure")

    monkeypatch.setattr(
        go_assignments, "_CRITICAL_VERSION_DECISION_FAILURE_HOOK", boom
    )
    with pytest.raises(RuntimeError, match="forced critical decision failure"):
        decide_critical_assignment_version(
            guide_os_id,
            offer.assignment_id,
            version_number=2,
            decision="confirm_critical",
            decision_event_id=str(uuid4()),
        )

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["pending_critical_version_number"] == 2
    assert int(stored["active_version_number"]) == 1
    assert stored["start_date"] == offer.start_date
    assert stored["end_date"] == offer.end_date
    assert get_tour_by_id(user_id, accepted.projection_tour_id) == tour_before
    assert get_guide_operator_critical_version_decision(
        assignment_id=offer.assignment_id, version_number=2
    ) is None
    assert list_critical_version_decision_outbox(offer.assignment_id) == []


def test_invalid_decision_type_fails_closed():
    guide_os_id = _seed_guide(1010)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    package = _with_dates(offer, start_date="2026-08-11", end_date="2026-08-13")
    _intake_shifted(guide_os_id, offer, package)
    with pytest.raises(AssignmentValidationError):
        decide_critical_assignment_version(
            guide_os_id,
            offer.assignment_id,
            version_number=2,
            decision="accept",
            decision_event_id=str(uuid4()),
        )
