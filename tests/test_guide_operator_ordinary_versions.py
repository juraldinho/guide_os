"""GO7D1: idempotent ordinary assignment.version.published.v1 application."""

from __future__ import annotations

import copy
import json
import sqlite3
from uuid import uuid4

import pytest

from database.db import get_connection
from database.queries import (
    count_guide_operator_projections,
    get_guide_operator_assignment_version,
    get_guide_operator_decision,
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
    ORDINARY_VERSION_ACK_EVENT_TYPE,
    accept_assignment,
    apply_assignment_cancellation,
    apply_ordinary_assignment_version,
    get_assignment_for_guide,
    list_ordinary_version_ack_outbox,
    receive_assignment_offer,
)
from utils.constants import SOURCE_GUIDE_OPERATOR


def _seed_guide(user_id: int = 801) -> str:
    register_user(user_id)
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    return guide_os_id


def _package(
    assignment_id: str,
    guide_os_id: str,
    *,
    start_date: str = "2026-06-10",
    end_date: str = "2026-06-12",
    role: str = "main_guide",
    title: str = "Classic tour",
    city: str = "Samarkand",
    group_summary: str = "12 pax",
    days: list[dict] | None = None,
) -> dict:
    return {
        "tour": {
            "title": title,
            "city_or_route": city,
            "reference": "T-ORD",
        },
        "assignment": {
            "id": assignment_id,
            "guide_os_id": guide_os_id,
            "role": role,
            "start_date": start_date,
            "end_date": end_date,
        },
        "days": days
        or [
            {
                "date": start_date,
                "title": "Day 1",
                "city_or_route": city,
                "events": [
                    {
                        "start_time": "09:00",
                        "end_time": "12:00",
                        "title": "Morning walk",
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
    start_date: str = "2026-06-10",
    end_date: str = "2026-06-12",
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


def _ordinary(
    guide_os_id: str,
    assignment_id: str,
    working_package: dict,
    *,
    event_id: str | None = None,
    version_number: int = 2,
    previous_active_version_number: int = 1,
    severity: str = "ordinary",
    change_summary: list | None = None,
    published_at: str = "2026-06-02T09:00:00+00:00",
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
        or [{"code": "group_summary", "severity": "ordinary", "path": "group_summary"}],
        published_at=published_at,
    )


def _ordinary_package(offer: AssignmentOfferIntake, **overrides) -> dict:
    package = copy.deepcopy(offer.working_package)
    package.update(overrides)
    return package


def test_ordinary_version_applies_and_keeps_occupancy():
    guide_os_id = _seed_guide(801)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    assert tour_id is not None
    before = get_tour_by_id(user_id, tour_id)
    assert before is not None

    next_package = _ordinary_package(offer, group_summary="14 pax")
    next_package["tour"]["title"] = "Classic tour updated"
    next_package["tour"]["city_or_route"] = "Bukhara"
    next_package["days"][0]["city_or_route"] = "Bukhara"
    next_package["days"][0]["events"] = [
        {
            "start_time": "09:00",
            "end_time": "10:30",
            "title": "Morning walk",
            "event_type": "tour",
        },
        {
            "start_time": "10:30",
            "end_time": "12:00",
            "title": "Tea house",
            "event_type": "tour",
        },
    ]
    event = _ordinary(guide_os_id, offer.assignment_id, next_package)
    result = apply_ordinary_assignment_version(event)

    assert result.replayed is False
    assert result.status == "accepted"
    assert result.version_number == 2
    assert result.previous_active_version_number == 1
    assert result.unread is True
    assert result.projection_tour_id == tour_id
    assert result.source_event_id == event.event_id

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["status"] == "accepted"
    assert int(stored["active_version_number"]) == 2
    assert int(stored["active_version_unread"]) == 1
    assert stored["start_date"] == offer.start_date
    assert stored["end_date"] == offer.end_date
    assert stored["role"] == "main_guide"
    assert stored["projection_tour_id"] == tour_id
    assert count_guide_operator_projections(offer.assignment_id) == 1

    after = get_tour_by_id(user_id, tour_id)
    assert after is not None
    assert after["start_date"] == before["start_date"]
    assert after["end_date"] == before["end_date"]
    assert after["title"] == "Classic tour updated"
    assert after["city"] == "Bukhara"
    assert after["source"] == SOURCE_GUIDE_OPERATOR
    locations = json.loads(after["day_locations_json"])
    assert locations[offer.start_date] == "Bukhara"


def test_ordinary_version_retains_immutable_history_and_unread():
    guide_os_id = _seed_guide(802)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    version_one_before = get_guide_operator_assignment_version(offer.assignment_id, 1)
    decision_before = get_guide_operator_decision(offer.assignment_id)
    assert version_one_before is not None
    assert decision_before is not None

    next_package = _ordinary_package(offer, group_summary="updated group")
    event = _ordinary(guide_os_id, offer.assignment_id, next_package)
    apply_ordinary_assignment_version(event)

    version_one_after = get_guide_operator_assignment_version(offer.assignment_id, 1)
    assert version_one_after == version_one_before
    assert get_guide_operator_decision(offer.assignment_id) == decision_before

    versions = list_guide_operator_assignment_versions(offer.assignment_id)
    assert [row["version_number"] for row in versions] == [1, 2]
    assert versions[0]["severity"] == "initial"
    assert versions[1]["severity"] == "ordinary"
    assert versions[1]["source_event_id"] == event.event_id
    stored_package = json.loads(versions[1]["working_package_json"])
    assert stored_package["group_summary"] == "updated group"
    assert json.loads(versions[0]["working_package_json"])["group_summary"] == "12 pax"

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert int(stored["active_version_unread"]) == 1
    inbox = get_guide_operator_version_inbox(event.event_id)
    assert inbox is not None
    assert inbox["result_status"] == "applied"
    assert inbox["assignment_id"] == offer.assignment_id
    assert inbox["guide_os_id"] == guide_os_id


def test_ordinary_version_duplicate_is_idempotent_exactly_one_ack():
    guide_os_id = _seed_guide(803)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    next_package = _ordinary_package(offer, group_summary="14 pax")
    event = _ordinary(guide_os_id, offer.assignment_id, next_package)

    first = apply_ordinary_assignment_version(event)
    second = apply_ordinary_assignment_version(event)

    assert first.replayed is False
    assert second.replayed is True
    assert second.version_number == 2
    assert second.unread is True
    assert len(list_ordinary_version_ack_outbox(offer.assignment_id)) == 1
    assert (
        list_ordinary_version_ack_outbox(offer.assignment_id)[0]["event_type"]
        == ORDINARY_VERSION_ACK_EVENT_TYPE
    )
    assert list_ordinary_version_ack_outbox(offer.assignment_id)[0]["event_id"] == event.event_id
    assert len(list_guide_operator_assignment_versions(offer.assignment_id)) == 2
    assert count_guide_operator_projections(offer.assignment_id) == 1
    tour = get_tour_by_id(user_id, accepted.projection_tour_id)
    assert tour is not None
    assert tour["start_date"] == offer.start_date
    assert tour["end_date"] == offer.end_date


def test_conflicting_duplicate_version_event_fails_closed():
    guide_os_id = _seed_guide(804)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    event_id = str(uuid4())
    apply_ordinary_assignment_version(
        _ordinary(
            guide_os_id,
            offer.assignment_id,
            _ordinary_package(offer, group_summary="14 pax"),
            event_id=event_id,
        )
    )

    with pytest.raises(AssignmentConflictError):
        apply_ordinary_assignment_version(
            _ordinary(
                guide_os_id,
                offer.assignment_id,
                _ordinary_package(offer, group_summary="16 pax"),
                event_id=event_id,
            )
        )

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert int(stored["active_version_number"]) == 2
    assert json.loads(
        get_guide_operator_assignment_version(offer.assignment_id, 2)["working_package_json"]
    )["group_summary"] == "14 pax"
    assert len(list_ordinary_version_ack_outbox(offer.assignment_id)) == 1


@pytest.mark.parametrize(
    "mutator,expected_code",
    [
        (
            lambda package: package["assignment"].__setitem__("start_date", "2026-06-11")
            or package["assignment"].__setitem__("end_date", "2026-06-13"),
            "assignment_dates",
        ),
        (
            lambda package: package["assignment"].__setitem__("role", "assistant"),
            "assignment_role",
        ),
        (
            lambda package: package["days"].pop(),
            "day_set",
        ),
        (
            lambda package: package["days"][0]["events"].__setitem__(
                0, {**package["days"][0]["events"][0], "end_time": "18:00"}
            ),
            "occupancy_envelope",
        ),
    ],
)
def test_ordinary_version_rejects_occupancy_changes(mutator, expected_code):
    guide_os_id = _seed_guide(805)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_before = get_tour_by_id(user_id, accepted.projection_tour_id)
    version_one = get_guide_operator_assignment_version(offer.assignment_id, 1)

    next_package = _ordinary_package(offer, group_summary="changed")
    mutator(next_package)
    with pytest.raises(AssignmentValidationError, match="occupancy") as exc_info:
        apply_ordinary_assignment_version(
            _ordinary(guide_os_id, offer.assignment_id, next_package)
        )
    assert expected_code in exc_info.value.details["codes"]

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert int(stored["active_version_number"]) == 1
    assert int(stored["active_version_unread"] or 0) == 0
    assert get_guide_operator_assignment_version(offer.assignment_id, 1) == version_one
    assert get_guide_operator_assignment_version(offer.assignment_id, 2) is None
    assert list_ordinary_version_ack_outbox(offer.assignment_id) == []
    assert count_guide_operator_projections(offer.assignment_id) == 1
    tour_after = get_tour_by_id(user_id, accepted.projection_tour_id)
    assert tour_after == tour_before


def test_version_gap_is_rejected():
    guide_os_id = _seed_guide(806)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)

    with pytest.raises(AssignmentConflictError, match="next monotonic"):
        apply_ordinary_assignment_version(
            _ordinary(
                guide_os_id,
                offer.assignment_id,
                _ordinary_package(offer, group_summary="14 pax"),
                version_number=3,
                previous_active_version_number=1,
            )
        )
    assert int(
        get_assignment_for_guide(guide_os_id, offer.assignment_id)["active_version_number"]
    ) == 1
    assert list_ordinary_version_ack_outbox(offer.assignment_id) == []


def test_stale_previous_version_is_rejected():
    guide_os_id = _seed_guide(807)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    apply_ordinary_assignment_version(
        _ordinary(
            guide_os_id,
            offer.assignment_id,
            _ordinary_package(offer, group_summary="14 pax"),
        )
    )

    with pytest.raises(AssignmentConflictError, match="Previous active version"):
        apply_ordinary_assignment_version(
            _ordinary(
                guide_os_id,
                offer.assignment_id,
                _ordinary_package(offer, group_summary="16 pax"),
                version_number=3,
                previous_active_version_number=1,
            )
        )
    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert int(stored["active_version_number"]) == 2
    assert len(list_guide_operator_assignment_versions(offer.assignment_id)) == 2
    assert len(list_ordinary_version_ack_outbox(offer.assignment_id)) == 1


def test_wrong_guide_does_not_apply_ordinary_version():
    owner = _seed_guide(808)
    stranger = _seed_guide(809)
    offer = _offer(owner)
    _accept(owner, offer)
    package = _ordinary_package(offer, group_summary="14 pax")
    package["assignment"]["guide_os_id"] = stranger

    with pytest.raises(AssignmentNotFoundError):
        apply_ordinary_assignment_version(
            _ordinary(stranger, offer.assignment_id, package)
        )
    stored = get_assignment_for_guide(owner, offer.assignment_id)
    assert int(stored["active_version_number"]) == 1
    assert list_ordinary_version_ack_outbox(offer.assignment_id) == []


def test_cancelled_assignment_cannot_receive_ordinary_version():
    guide_os_id = _seed_guide(810)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    apply_assignment_cancellation(
        AssignmentCancellationIntake(
            event_id=str(uuid4()),
            assignment_id=offer.assignment_id,
            guide_os_id=guide_os_id,
            version_number=1,
            cancelled_at="2026-06-03T10:00:00+00:00",
        )
    )

    with pytest.raises(AssignmentNotActionableError):
        apply_ordinary_assignment_version(
            _ordinary(
                guide_os_id,
                offer.assignment_id,
                _ordinary_package(offer, group_summary="14 pax"),
            )
        )
    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["status"] == "cancelled"
    assert int(stored["active_version_number"]) == 1
    assert list_ordinary_version_ack_outbox(offer.assignment_id) == []


def test_malformed_and_critical_snapshots_are_rejected():
    guide_os_id = _seed_guide(811)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    valid = _ordinary_package(offer, group_summary="14 pax")

    with pytest.raises(AssignmentValidationError):
        apply_ordinary_assignment_version(
            _ordinary(guide_os_id, offer.assignment_id, valid, severity="critical")
        )
    with pytest.raises(AssignmentValidationError):
        apply_ordinary_assignment_version(
            AssignmentVersionPublishedIntake(
                event_id=str(uuid4()),
                assignment_id=offer.assignment_id,
                guide_os_id=guide_os_id,
                version_number=2,
                previous_active_version_number=1,
                severity="ordinary",
                working_package={},
                change_summary=[],
                published_at="2026-06-02T09:00:00+00:00",
            )
        )
    broken_days = _ordinary_package(offer)
    broken_days["days"] = "not-a-list"
    with pytest.raises(AssignmentValidationError):
        apply_ordinary_assignment_version(
            _ordinary(guide_os_id, offer.assignment_id, broken_days)
        )
    duplicate_days = _ordinary_package(offer)
    duplicate_days["days"] = [
        duplicate_days["days"][0],
        copy.deepcopy(duplicate_days["days"][0]),
    ]
    with pytest.raises(AssignmentValidationError, match="duplicate dates"):
        apply_ordinary_assignment_version(
            _ordinary(guide_os_id, offer.assignment_id, duplicate_days)
        )

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert int(stored["active_version_number"]) == 1
    assert list_ordinary_version_ack_outbox(offer.assignment_id) == []
    assert count_guide_operator_projections(offer.assignment_id) == 1


def test_failed_ordinary_version_rolls_back_atomically(monkeypatch):
    guide_os_id = _seed_guide(812)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_before = get_tour_by_id(user_id, accepted.projection_tour_id)
    version_one = get_guide_operator_assignment_version(offer.assignment_id, 1)

    def boom():
        raise RuntimeError("forced ordinary version failure")

    monkeypatch.setattr(go_assignments, "_ORDINARY_VERSION_FAILURE_HOOK", boom)
    event = _ordinary(
        guide_os_id,
        offer.assignment_id,
        _ordinary_package(offer, group_summary="14 pax"),
    )
    with pytest.raises(RuntimeError, match="forced ordinary version failure"):
        apply_ordinary_assignment_version(event)

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["status"] == "accepted"
    assert int(stored["active_version_number"]) == 1
    assert int(stored["active_version_unread"] or 0) == 0
    assert stored["projection_tour_id"] == accepted.projection_tour_id
    assert get_guide_operator_assignment_version(offer.assignment_id, 1) == version_one
    assert get_guide_operator_assignment_version(offer.assignment_id, 2) is None
    assert get_guide_operator_version_inbox(event.event_id) is None
    assert list_ordinary_version_ack_outbox(offer.assignment_id) == []
    assert list_guide_operator_outbox_events(
        assignment_id=offer.assignment_id, event_type=ORDINARY_VERSION_ACK_EVENT_TYPE
    ) == []
    assert get_tour_by_id(user_id, accepted.projection_tour_id) == tour_before
    assert count_guide_operator_projections(offer.assignment_id) == 1


def test_projection_allowlist_cannot_change_occupancy_dates():
    guide_os_id = _seed_guide(813)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    assert tour_id is not None

    conn = get_connection()
    conn.execute(
        "INSERT INTO go_operator_projection_metadata_update (tour_id) VALUES (?)",
        (tour_id,),
    )
    with pytest.raises(sqlite3.IntegrityError, match="operator-managed"):
        conn.execute(
            "UPDATE tours SET start_date = ? WHERE id = ?",
            ("2026-07-01", tour_id),
        )
        conn.commit()
    conn.rollback()
    conn.execute(
        "DELETE FROM go_operator_projection_metadata_update WHERE tour_id = ?",
        (tour_id,),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="operator-managed"):
        conn.execute("UPDATE tours SET city = ? WHERE id = ?", ("Hacked", tour_id))
        conn.commit()
    conn.rollback()
    conn.close()

    tour = get_tour_by_id(user_id, tour_id)
    assert tour["start_date"] == offer.start_date
    assert tour["city"] == "Samarkand"
