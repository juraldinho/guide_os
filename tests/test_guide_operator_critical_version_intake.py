"""GO7E1: idempotent critical assignment.version.published.v1 intake (no apply)."""

from __future__ import annotations

import copy
import json
from uuid import uuid4

import pytest

from database.queries import (
    count_guide_operator_projections,
    get_guide_operator_assignment_version,
    get_guide_operator_version_inbox,
    get_guide_os_id,
    get_tour_by_id,
    get_user_id_by_guide_os_id,
    list_guide_operator_assignment_versions,
    list_guide_operator_outbox_events,
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
    CRITICAL_VERSION_RECEIVED_ACK_EVENT_TYPE,
    accept_assignment,
    apply_assignment_cancellation,
    apply_ordinary_assignment_version,
    get_assignment_for_guide,
    intake_critical_assignment_version,
    list_critical_version_received_ack_outbox,
    list_ordinary_version_ack_outbox,
    receive_assignment_offer,
)
from utils.constants import SOURCE_GUIDE_OPERATOR


def _seed_guide(user_id: int = 901) -> str:
    register_user(user_id)
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    return guide_os_id


def _package(
    assignment_id: str,
    guide_os_id: str,
    *,
    start_date: str = "2026-07-10",
    end_date: str = "2026-07-12",
    role: str = "main_guide",
    title: str = "Critical base",
    city: str = "Samarkand",
    group_summary: str = "10 pax",
) -> dict:
    return {
        "tour": {
            "title": title,
            "city_or_route": city,
            "reference": "T-CRIT",
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
    start_date: str = "2026-07-10",
    end_date: str = "2026-07-12",
    package: dict | None = None,
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
        working_package=package
        or _package(assignment_id, guide_os_id, start_date=start_date, end_date=end_date),
    )


def _accept(guide_os_id: str, offer: AssignmentOfferIntake):
    receive_assignment_offer(offer)
    return accept_assignment(
        guide_os_id,
        offer.assignment_id,
        decision_event_id=str(uuid4()),
    )


def _critical_package(offer: AssignmentOfferIntake, **overrides) -> dict:
    package = copy.deepcopy(offer.working_package)
    package.update(overrides)
    return package


def _critical(
    guide_os_id: str,
    assignment_id: str,
    working_package: dict,
    *,
    event_id: str | None = None,
    version_number: int = 2,
    previous_active_version_number: int = 1,
    severity: str = "critical",
    change_summary: list | None = None,
    published_at: str = "2026-07-02T09:00:00+00:00",
) -> AssignmentVersionPublishedIntake:
    return AssignmentVersionPublishedIntake(
        event_id=event_id or str(uuid4()),
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
        version_number=version_number,
        previous_active_version_number=previous_active_version_number,
        severity=severity,
        working_package=working_package,
        change_summary=change_summary
        if change_summary is not None
        else [
            {
                "code": "start_date_changed",
                "severity": "critical",
                "path": "assignment.start_date",
                "change": "updated",
                "before": "2026-07-10",
                "after": "2026-07-11",
            }
        ],
        published_at=published_at,
    )


def _shifted_dates_package(offer: AssignmentOfferIntake) -> dict:
    package = _critical_package(offer)
    package["assignment"]["start_date"] = "2026-07-11"
    package["assignment"]["end_date"] = "2026-07-13"
    package["days"][0]["date"] = "2026-07-11"
    package["days"][1]["date"] = "2026-07-13"
    return package


def test_critical_intake_stores_pending_without_applying():
    guide_os_id = _seed_guide(901)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    assert tour_id is not None
    before = get_tour_by_id(user_id, tour_id)
    assert before is not None
    version_one = get_guide_operator_assignment_version(offer.assignment_id, 1)

    event = _critical(
        guide_os_id, offer.assignment_id, _shifted_dates_package(offer)
    )
    result = intake_critical_assignment_version(event)

    assert result.replayed is False
    assert result.status == "accepted"
    assert result.version_number == 2
    assert result.previous_active_version_number == 1
    assert result.pending_critical_version_number == 2
    assert result.active_version_number == 1
    assert result.unread is False
    assert result.projection_tour_id == tour_id
    assert result.source_event_id == event.event_id

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert int(stored["active_version_number"]) == 1
    assert stored["pending_critical_version_number"] == 2
    assert int(stored["active_version_unread"] or 0) == 0
    assert stored["start_date"] == offer.start_date
    assert stored["end_date"] == offer.end_date
    assert stored["projection_tour_id"] == tour_id
    assert count_guide_operator_projections(offer.assignment_id) == 1

    after = get_tour_by_id(user_id, tour_id)
    assert after is not None
    assert after["start_date"] == before["start_date"]
    assert after["end_date"] == before["end_date"]
    assert after["title"] == before["title"]
    assert after["city"] == before["city"]
    assert after["day_locations_json"] == before["day_locations_json"]
    assert after["source"] == SOURCE_GUIDE_OPERATOR

    assert get_guide_operator_assignment_version(offer.assignment_id, 1) == version_one
    pending = get_guide_operator_assignment_version(offer.assignment_id, 2)
    assert pending is not None
    assert pending["severity"] == "critical"
    assert pending["source_event_id"] == event.event_id
    summary = json.loads(pending["change_summary_json"])
    assert summary[0]["severity"] == "critical"

    inbox = get_guide_operator_version_inbox(event.event_id)
    assert inbox is not None
    assert inbox["result_status"] == "applied"
    acks = list_critical_version_received_ack_outbox(offer.assignment_id)
    assert len(acks) == 1
    assert acks[0]["event_type"] == CRITICAL_VERSION_RECEIVED_ACK_EVENT_TYPE
    assert acks[0]["event_id"] == event.event_id
    assert list_ordinary_version_ack_outbox(offer.assignment_id) == []


def test_critical_intake_duplicate_replay_is_safe():
    guide_os_id = _seed_guide(902)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    event = _critical(
        guide_os_id, offer.assignment_id, _shifted_dates_package(offer)
    )
    first = intake_critical_assignment_version(event)
    second = intake_critical_assignment_version(event)

    assert first.replayed is False
    assert second.replayed is True
    assert second.pending_critical_version_number == 2
    assert second.active_version_number == 1
    assert len(list_critical_version_received_ack_outbox(offer.assignment_id)) == 1
    assert len(list_guide_operator_assignment_versions(offer.assignment_id)) == 2


def test_critical_intake_conflicting_event_payload_fails_closed():
    guide_os_id = _seed_guide(903)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    event = _critical(
        guide_os_id, offer.assignment_id, _shifted_dates_package(offer)
    )
    intake_critical_assignment_version(event)

    conflict_package = _shifted_dates_package(offer)
    conflict_package["group_summary"] = "conflict body"
    conflict = AssignmentVersionPublishedIntake(
        event_id=event.event_id,
        assignment_id=offer.assignment_id,
        guide_os_id=guide_os_id,
        version_number=2,
        previous_active_version_number=1,
        severity="critical",
        working_package=conflict_package,
        change_summary=[
            {
                "code": "group_summary",
                "severity": "critical",
                "path": "group_summary",
            }
        ],
        published_at=event.published_at,
    )
    with pytest.raises(AssignmentConflictError):
        intake_critical_assignment_version(conflict)

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["pending_critical_version_number"] == 2
    assert int(stored["active_version_number"]) == 1
    assert len(list_critical_version_received_ack_outbox(offer.assignment_id)) == 1


def test_existing_pending_critical_rejects_new_intake():
    guide_os_id = _seed_guide(904)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    first = _critical(
        guide_os_id, offer.assignment_id, _shifted_dates_package(offer)
    )
    intake_critical_assignment_version(first)

    second_package = _shifted_dates_package(offer)
    second_package["group_summary"] = "another critical attempt"
    with pytest.raises(AssignmentConflictError, match="already pending"):
        intake_critical_assignment_version(
            _critical(guide_os_id, offer.assignment_id, second_package)
        )
    assert len(list_critical_version_received_ack_outbox(offer.assignment_id)) == 1


def test_gap_and_stale_previous_version_fail_closed():
    guide_os_id = _seed_guide(905)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    package = _shifted_dates_package(offer)

    with pytest.raises(AssignmentConflictError, match="monotonic"):
        intake_critical_assignment_version(
            _critical(
                guide_os_id,
                offer.assignment_id,
                package,
                version_number=3,
                previous_active_version_number=1,
            )
        )
    with pytest.raises(AssignmentConflictError, match="Previous active"):
        intake_critical_assignment_version(
            _critical(
                guide_os_id,
                offer.assignment_id,
                package,
                version_number=2,
                previous_active_version_number=2,
            )
        )
    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["pending_critical_version_number"] is None
    assert int(stored["active_version_number"]) == 1
    assert list_critical_version_received_ack_outbox(offer.assignment_id) == []


def test_wrong_guide_fails_closed():
    guide_a = _seed_guide(906)
    guide_b = _seed_guide(907)
    offer = _offer(guide_a)
    _accept(guide_a, offer)
    # Package bound to attacker guide_os_id so snapshot validation passes;
    # assignment ownership still fails closed.
    attacker_package = _shifted_dates_package(offer)
    attacker_package["assignment"]["guide_os_id"] = guide_b
    with pytest.raises(AssignmentNotFoundError):
        intake_critical_assignment_version(
            _critical(guide_b, offer.assignment_id, attacker_package)
        )
    stored = get_assignment_for_guide(guide_a, offer.assignment_id)
    assert stored["pending_critical_version_number"] is None


def test_cancelled_assignment_rejects_critical_intake():
    guide_os_id = _seed_guide(908)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    apply_assignment_cancellation(
        AssignmentCancellationIntake(
            event_id=str(uuid4()),
            assignment_id=offer.assignment_id,
            guide_os_id=guide_os_id,
            version_number=1,
            cancelled_at="2026-07-03T10:00:00+00:00",
        )
    )
    with pytest.raises(AssignmentNotActionableError):
        intake_critical_assignment_version(
            _critical(
                guide_os_id, offer.assignment_id, _shifted_dates_package(offer)
            )
        )
    assert list_critical_version_received_ack_outbox(offer.assignment_id) == []


def test_cancellation_supersedes_pending_critical_without_applying():
    guide_os_id = _seed_guide(909)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    event = _critical(
        guide_os_id, offer.assignment_id, _shifted_dates_package(offer)
    )
    intake_critical_assignment_version(event)
    assert get_assignment_for_guide(guide_os_id, offer.assignment_id)[
        "pending_critical_version_number"
    ] == 2

    apply_assignment_cancellation(
        AssignmentCancellationIntake(
            event_id=str(uuid4()),
            assignment_id=offer.assignment_id,
            guide_os_id=guide_os_id,
            version_number=1,
            cancelled_at="2026-07-04T10:00:00+00:00",
        )
    )
    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["status"] == "cancelled"
    assert stored["pending_critical_version_number"] is None
    assert int(stored["active_version_number"]) == 1
    assert stored["projection_tour_id"] is None
    assert get_tour_by_id(user_id, tour_id) is None
    # Immutable pending snapshot retained; never activated.
    pending = get_guide_operator_assignment_version(offer.assignment_id, 2)
    assert pending is not None
    assert pending["severity"] == "critical"
    assert len(list_critical_version_received_ack_outbox(offer.assignment_id)) == 1


def test_critical_intake_accepts_operator_mixed_change_summary():
    guide_os_id = _seed_guide(909)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    package = _shifted_dates_package(offer)
    package["tour"]["title"] = "Renamed critical tour"
    result = intake_critical_assignment_version(
        _critical(
            guide_os_id,
            offer.assignment_id,
            package,
            change_summary=[
                {
                    "code": "assignment_dates",
                    "severity": "critical",
                    "path": "assignment.dates",
                },
                {
                    "code": "driver",
                    "severity": "ordinary",
                    "path": "drivers",
                },
                {
                    "code": "uncertain",
                    "severity": "uncertain",
                    "path": "tour.title",
                },
            ],
        )
    )
    assert result.replayed is False
    assert result.pending_critical_version_number == 2
    assert result.active_version_number == 1


def test_noop_and_malformed_critical_snapshots_are_rejected():
    guide_os_id = _seed_guide(910)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)

    with pytest.raises(AssignmentValidationError):
        intake_critical_assignment_version(
            _critical(
                guide_os_id,
                offer.assignment_id,
                copy.deepcopy(offer.working_package),
                change_summary=[
                    {
                        "code": "noop",
                        "severity": "critical",
                        "path": "group_summary",
                    }
                ],
            )
        )
    with pytest.raises(AssignmentValidationError, match="empty"):
        intake_critical_assignment_version(
            _critical(
                guide_os_id,
                offer.assignment_id,
                _shifted_dates_package(offer),
                change_summary=[],
            )
        )
    with pytest.raises(AssignmentValidationError):
        intake_critical_assignment_version(
            _critical(
                guide_os_id,
                offer.assignment_id,
                _shifted_dates_package(offer),
                severity="ordinary",
            )
        )
    with pytest.raises(AssignmentValidationError):
        intake_critical_assignment_version(
            AssignmentVersionPublishedIntake(
                event_id=str(uuid4()),
                assignment_id=offer.assignment_id,
                guide_os_id=guide_os_id,
                version_number=2,
                previous_active_version_number=1,
                severity="critical",
                working_package={},
                change_summary=[
                    {
                        "code": "x",
                        "severity": "critical",
                        "path": "y",
                    }
                ],
                published_at="2026-07-02T09:00:00+00:00",
            )
        )
    with pytest.raises(AssignmentValidationError, match="code"):
        intake_critical_assignment_version(
            _critical(
                guide_os_id,
                offer.assignment_id,
                _shifted_dates_package(offer),
                change_summary=[{"severity": "critical", "path": "x"}],
            )
        )

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["pending_critical_version_number"] is None
    assert int(stored["active_version_number"]) == 1
    assert list_critical_version_received_ack_outbox(offer.assignment_id) == []
    assert count_guide_operator_projections(offer.assignment_id) == 1


def test_failed_critical_intake_rolls_back_atomically(monkeypatch):
    guide_os_id = _seed_guide(911)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_before = get_tour_by_id(user_id, accepted.projection_tour_id)
    version_one = get_guide_operator_assignment_version(offer.assignment_id, 1)

    def boom():
        raise RuntimeError("forced critical intake failure")

    monkeypatch.setattr(go_assignments, "_CRITICAL_VERSION_INTAKE_FAILURE_HOOK", boom)
    event = _critical(
        guide_os_id, offer.assignment_id, _shifted_dates_package(offer)
    )
    with pytest.raises(RuntimeError, match="forced critical intake failure"):
        intake_critical_assignment_version(event)

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["status"] == "accepted"
    assert int(stored["active_version_number"]) == 1
    assert stored["pending_critical_version_number"] is None
    assert int(stored["active_version_unread"] or 0) == 0
    assert stored["projection_tour_id"] == accepted.projection_tour_id
    assert get_guide_operator_assignment_version(offer.assignment_id, 1) == version_one
    assert get_guide_operator_assignment_version(offer.assignment_id, 2) is None
    assert get_guide_operator_version_inbox(event.event_id) is None
    assert list_critical_version_received_ack_outbox(offer.assignment_id) == []
    tour_after = get_tour_by_id(user_id, accepted.projection_tour_id)
    assert tour_after == tour_before


def test_ordinary_apply_still_rejects_critical_severity():
    guide_os_id = _seed_guide(912)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    with pytest.raises(AssignmentValidationError):
        apply_ordinary_assignment_version(
            _critical(
                guide_os_id, offer.assignment_id, _shifted_dates_package(offer)
            )
        )
    assert get_assignment_for_guide(guide_os_id, offer.assignment_id)[
        "pending_critical_version_number"
    ] is None
