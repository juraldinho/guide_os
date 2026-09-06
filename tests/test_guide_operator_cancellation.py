"""GO7B1: idempotent assignment.cancelled.v1 application and projection release."""

from __future__ import annotations

import sqlite3
from uuid import uuid4

import pytest

from database.db import get_connection
from database.queries import (
    count_guide_operator_projections,
    get_guide_operator_assignment_version,
    get_guide_operator_cancellation_inbox,
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
    AssignmentCancellationIntake,
    AssignmentConflictError,
    AssignmentNotActionableError,
    AssignmentNotFoundError,
    AssignmentOfferIntake,
    AssignmentValidationError,
    CANCELLATION_ACK_EVENT_TYPE,
    accept_assignment,
    apply_assignment_cancellation,
    decline_assignment,
    find_assignment_conflicts,
    get_assignment_for_guide,
    list_cancellation_ack_outbox,
    receive_assignment_offer,
)
from services.tour_service import (
    delete_tour,
    edit_tour_company,
    save_tour,
)
from utils.constants import SOURCE_GUIDE_OPERATOR, STATUS_CONFIRMED


def _seed_guide(user_id: int = 701) -> str:
    register_user(user_id)
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    return guide_os_id


def _offer(
    guide_os_id: str,
    *,
    assignment_id: str | None = None,
    start_date: str = "2026-06-10",
    end_date: str = "2026-06-12",
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
        working_package={
            "tour": {
                "title": "Cancelable tour",
                "city_or_route": "Samarkand",
                "reference": "T-CANCEL",
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
                }
            ],
        },
    )


def _accept(guide_os_id: str, offer: AssignmentOfferIntake):
    receive_assignment_offer(offer)
    return accept_assignment(
        guide_os_id,
        offer.assignment_id,
        decision_event_id=str(uuid4()),
    )


def _cancellation(
    guide_os_id: str,
    assignment_id: str,
    *,
    event_id: str | None = None,
    version_number: int = 1,
    cancelled_at: str = "2026-06-01T10:00:00+00:00",
) -> AssignmentCancellationIntake:
    return AssignmentCancellationIntake(
        event_id=event_id or str(uuid4()),
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
        version_number=version_number,
        cancelled_at=cancelled_at,
    )


def test_cancellation_releases_projection_and_retains_history():
    guide_os_id = _seed_guide(701)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    assert tour_id is not None
    assert get_tour_by_id(user_id, tour_id) is not None
    assert get_guide_operator_decision(offer.assignment_id) is not None
    assert get_guide_operator_assignment_version(offer.assignment_id, 1) is not None

    event = _cancellation(guide_os_id, offer.assignment_id)
    result = apply_assignment_cancellation(event)

    assert result.replayed is False
    assert result.status == "cancelled"
    assert result.projection_released is True
    assert result.cancellation_event_id == event.event_id
    assert count_guide_operator_projections(offer.assignment_id) == 0
    assert get_tour_by_id(user_id, tour_id) is None

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["status"] == "cancelled"
    assert stored["projection_tour_id"] is None
    assert stored["cancelled_at"] == event.cancelled_at
    assert stored["cancellation_event_id"] == event.event_id
    assert get_guide_operator_decision(offer.assignment_id)["decision_type"] == "accept"
    version = get_guide_operator_assignment_version(offer.assignment_id, 1)
    assert version is not None
    assert "Cancelable tour" in version["working_package_json"]

    acks = list_cancellation_ack_outbox(offer.assignment_id)
    assert len(acks) == 1
    assert acks[0]["event_type"] == CANCELLATION_ACK_EVENT_TYPE
    assert acks[0]["event_id"] == event.event_id


def test_duplicate_cancellation_is_idempotent_exactly_one_ack():
    guide_os_id = _seed_guide(702)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    event = _cancellation(guide_os_id, offer.assignment_id)

    first = apply_assignment_cancellation(event)
    second = apply_assignment_cancellation(event)

    assert first.replayed is False
    assert second.replayed is True
    assert second.status == "cancelled"
    assert len(list_cancellation_ack_outbox(offer.assignment_id)) == 1
    assert count_guide_operator_projections(offer.assignment_id) == 0
    inbox = get_guide_operator_cancellation_inbox(event.event_id)
    assert inbox is not None
    assert inbox["result_status"] == "applied"


def test_conflicting_duplicate_cancellation_event_fails_closed():
    guide_os_id = _seed_guide(703)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    event_id = str(uuid4())
    apply_assignment_cancellation(
        _cancellation(guide_os_id, offer.assignment_id, event_id=event_id)
    )

    with pytest.raises(AssignmentConflictError):
        apply_assignment_cancellation(
            AssignmentCancellationIntake(
                event_id=event_id,
                assignment_id=offer.assignment_id,
                guide_os_id=guide_os_id,
                version_number=1,
                cancelled_at="2026-06-02T12:00:00+00:00",
            )
        )

    assert len(list_cancellation_ack_outbox(offer.assignment_id)) == 1


def test_wrong_guide_and_wrong_version_do_not_change_calendar():
    owner = _seed_guide(704)
    stranger = _seed_guide(705)
    offer = _offer(owner)
    accepted = _accept(owner, offer)
    tour_id = accepted.projection_tour_id
    assert tour_id is not None

    with pytest.raises(AssignmentNotFoundError):
        apply_assignment_cancellation(
            _cancellation(stranger, offer.assignment_id)
        )

    with pytest.raises(AssignmentConflictError):
        apply_assignment_cancellation(
            _cancellation(owner, offer.assignment_id, version_number=2)
        )

    assert count_guide_operator_projections(offer.assignment_id) == 1
    assert get_assignment_for_guide(owner, offer.assignment_id)["status"] == "accepted"
    assert list_cancellation_ack_outbox(offer.assignment_id) == []


def test_forbidden_states_cannot_be_cancelled():
    guide_os_id = _seed_guide(706)
    offered = _offer(guide_os_id, start_date="2026-07-01", end_date="2026-07-02")
    receive_assignment_offer(offered)
    with pytest.raises(AssignmentNotActionableError):
        apply_assignment_cancellation(
            _cancellation(guide_os_id, offered.assignment_id)
        )

    declined = _offer(guide_os_id, start_date="2026-07-10", end_date="2026-07-11")
    receive_assignment_offer(declined)
    decline_assignment(
        guide_os_id, declined.assignment_id, decision_event_id=str(uuid4())
    )
    with pytest.raises(AssignmentNotActionableError):
        apply_assignment_cancellation(
            _cancellation(guide_os_id, declined.assignment_id)
        )

    already = _offer(guide_os_id, start_date="2026-07-20", end_date="2026-07-21")
    _accept(guide_os_id, already)
    apply_assignment_cancellation(_cancellation(guide_os_id, already.assignment_id))
    with pytest.raises(AssignmentNotActionableError):
        apply_assignment_cancellation(
            _cancellation(guide_os_id, already.assignment_id)
        )


def test_malformed_cancellation_is_rejected():
    guide_os_id = _seed_guide(707)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)

    with pytest.raises(AssignmentValidationError):
        apply_assignment_cancellation(
            AssignmentCancellationIntake(
                event_id="",
                assignment_id=offer.assignment_id,
                guide_os_id=guide_os_id,
                version_number=1,
                cancelled_at="2026-06-01T10:00:00+00:00",
            )
        )
    with pytest.raises(AssignmentValidationError):
        apply_assignment_cancellation(
            AssignmentCancellationIntake(
                event_id=str(uuid4()),
                assignment_id=offer.assignment_id,
                guide_os_id=guide_os_id,
                version_number=1,
                cancelled_at="not-a-timestamp",
            )
        )
    assert count_guide_operator_projections(offer.assignment_id) == 1


def test_failed_cancellation_rolls_back_atomically(monkeypatch):
    guide_os_id = _seed_guide(708)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    assert tour_id is not None

    def boom():
        raise RuntimeError("forced cancel failure")

    monkeypatch.setattr(go_assignments, "_CANCEL_FAILURE_HOOK", boom)

    with pytest.raises(RuntimeError, match="forced cancel failure"):
        apply_assignment_cancellation(
            _cancellation(guide_os_id, offer.assignment_id)
        )

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["status"] == "accepted"
    assert stored["projection_tour_id"] == tour_id
    assert stored["cancelled_at"] is None
    assert get_tour_by_id(user_id, tour_id) is not None
    assert count_guide_operator_projections(offer.assignment_id) == 1
    assert list_cancellation_ack_outbox(offer.assignment_id) == []
    assert list_guide_operator_outbox_events(
        assignment_id=offer.assignment_id, event_type=CANCELLATION_ACK_EVENT_TYPE
    ) == []


def test_no_calendar_conflict_after_cancellation_and_history_stays_immutable():
    guide_os_id = _seed_guide(709)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id, start_date="2026-08-01", end_date="2026-08-03")
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    assert tour_id is not None

    # Protection still holds before cancellation.
    assert edit_tour_company(user_id, tour_id, "Hacked") is False
    assert delete_tour(user_id, tour_id) is False

    apply_assignment_cancellation(_cancellation(guide_os_id, offer.assignment_id))

    assert find_assignment_conflicts(guide_os_id, offer.assignment_id) == []
    save_tour(
        user_id=user_id,
        company="Personal after cancel",
        city="Khiva",
        date_text="2026-08-02",
        status=STATUS_CONFIRMED,
        income=80,
    )

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert stored["status"] == "cancelled"
    assert count_guide_operator_projections(offer.assignment_id) == 0

    decision_before = get_guide_operator_decision(offer.assignment_id)
    version_before = get_guide_operator_assignment_version(offer.assignment_id, 1)
    assert decision_before is not None
    assert version_before is not None

    replay = accept_assignment(
        guide_os_id,
        offer.assignment_id,
        decision_event_id=decision_before["decision_event_id"],
    )
    assert replay.status == "cancelled"
    assert replay.replayed is True
    assert count_guide_operator_projections(offer.assignment_id) == 0

    assert get_guide_operator_decision(offer.assignment_id) == decision_before
    assert get_guide_operator_assignment_version(offer.assignment_id, 1) == version_before

    # Ordinary UPDATE/DELETE paths remain blocked for operator-managed rows.
    conn = get_connection()
    cursor = conn.execute(
        """
        INSERT INTO tours (
            user_id, company, city, start_date, end_date, status,
            income, payment_status, note, entry_type, tour_group_id,
            title, source
        ) VALUES (?, 'X', 'Y', '2026-09-01', '2026-09-01', ?, NULL, 'unpaid',
                  ?, 'tour', ?, 'Fake', ?)
        """,
        (
            user_id,
            STATUS_CONFIRMED,
            f"go_assignment:{uuid4()}",
            str(uuid4()),
            SOURCE_GUIDE_OPERATOR,
        ),
    )
    fake_id = int(cursor.lastrowid)
    with pytest.raises(sqlite3.IntegrityError, match="operator-managed"):
        conn.execute("UPDATE tours SET company = ? WHERE id = ?", ("Hack", fake_id))
        conn.commit()
    conn.rollback()
    conn.execute(
        "INSERT INTO tours ("
        "user_id, company, city, start_date, end_date, status, income,"
        " payment_status, note, entry_type, tour_group_id, title, source"
        ") VALUES (?, 'X', 'Y', '2026-09-02', '2026-09-02', ?, NULL, 'unpaid',"
        " ?, 'tour', ?, 'Fake2', ?)",
        (
            user_id,
            STATUS_CONFIRMED,
            f"go_assignment:{uuid4()}",
            str(uuid4()),
            SOURCE_GUIDE_OPERATOR,
        ),
    )
    fake_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    with pytest.raises(sqlite3.IntegrityError, match="operator-managed"):
        conn.execute("DELETE FROM tours WHERE id = ?", (fake_id,))
        conn.commit()
    conn.rollback()
    conn.close()
