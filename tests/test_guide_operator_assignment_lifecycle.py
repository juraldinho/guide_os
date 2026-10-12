"""GO13I1: fail-closed withdrawal/expiry intake for pending offers."""

from __future__ import annotations

import sqlite3
from uuid import uuid4

import pytest

from database.db import _migrate_guide_operator_assignments_lifecycle, get_connection
from database.queries import (
    count_guide_operator_projections,
    get_guide_operator_assignment_lifecycle_inbox,
    get_guide_os_id,
    list_guide_operator_assignment_versions,
    register_user,
)
from services.guide_operator_assignment_service import (
    AssignmentConflictError,
    AssignmentLifecycleIntake,
    AssignmentNotActionableError,
    AssignmentNotFoundError,
    AssignmentOfferIntake,
    accept_assignment,
    apply_assignment_cancellation,
    apply_assignment_lifecycle_transition,
    decline_assignment,
    get_assignment_for_guide,
    list_assignment_lifecycle,
    list_pending_offers,
    receive_assignment_offer,
    AssignmentCancellationIntake,
)
from services.guide_operator_connection_service import ensure_confirmed_connection_for_tests


def _guide(user_id: int) -> str:
    register_user(user_id)
    value = get_guide_os_id(user_id)
    assert value is not None
    return value


def _offer(guide_os_id: str) -> AssignmentOfferIntake:
    assignment_id = str(uuid4())
    connection = ensure_confirmed_connection_for_tests(guide_os_id)
    return AssignmentOfferIntake(
        event_id=str(uuid4()),
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
        company_id=connection["company_id"],
        company_name=connection["company_name"],
        guide_connection_id=connection["connection_id"],
        role="main_guide",
        start_date="2026-11-01",
        end_date="2026-11-02",
        working_package={
            "tour": {"title": "Lifecycle", "city_or_route": "Samarkand"},
            "assignment": {
                "id": assignment_id,
                "role": "main_guide",
                "start_date": "2026-11-01",
                "end_date": "2026-11-02",
            },
            "days": [{"date": "2026-11-01", "title": "Day 1"}],
        },
    )


def _event(
    offer: AssignmentOfferIntake,
    *,
    event_type: str = "assignment.withdrawn.v1",
    event_id: str | None = None,
    guide_os_id: str | None = None,
) -> AssignmentLifecycleIntake:
    return AssignmentLifecycleIntake(
        event_id=event_id or str(uuid4()),
        event_type=event_type,
        assignment_id=offer.assignment_id,
        guide_os_id=guide_os_id or offer.guide_os_id,
        transitioned_at="2026-10-01T12:00:00+00:00",
    )


@pytest.mark.parametrize(
    ("event_type", "status"),
    [
        ("assignment.withdrawn.v1", "withdrawn"),
        ("assignment.expired.v1", "expired"),
    ],
)
def test_offered_transition_is_idempotent_and_leaves_pending_lists(
    event_type: str, status: str
) -> None:
    guide_os_id = _guide(7310 if status == "withdrawn" else 7311)
    offer = _offer(guide_os_id)
    receive_assignment_offer(offer)
    event = _event(offer, event_type=event_type)

    first = apply_assignment_lifecycle_transition(event)
    second = apply_assignment_lifecycle_transition(event)

    assert first.status == status and first.replayed is False
    assert second.status == status and second.replayed is True
    assert list_pending_offers(guide_os_id) == []
    assert list_assignment_lifecycle(guide_os_id)["awaiting"] == []
    assert len(list_guide_operator_assignment_versions(offer.assignment_id)) == 1
    assert count_guide_operator_projections(offer.assignment_id) == 0
    inbox = get_guide_operator_assignment_lifecycle_inbox(event.event_id)
    assert inbox is not None and inbox["result_status"] == "applied"


def test_conflicting_event_identity_and_wrong_guide_fail_closed() -> None:
    owner = _guide(7312)
    stranger = _guide(7313)
    offer = _offer(owner)
    receive_assignment_offer(offer)
    event_id = str(uuid4())
    apply_assignment_lifecycle_transition(_event(offer, event_id=event_id))

    with pytest.raises(AssignmentConflictError):
        apply_assignment_lifecycle_transition(
            _event(
                offer,
                event_id=event_id,
                event_type="assignment.expired.v1",
            )
        )
    with pytest.raises(AssignmentNotFoundError):
        apply_assignment_lifecycle_transition(
            _event(_offer(stranger), guide_os_id=stranger)
        )


@pytest.mark.parametrize("later_status", ["accepted", "declined", "cancelled"])
def test_out_of_order_lifecycle_cannot_regress_later_state(later_status: str) -> None:
    guide_os_id = _guide({"accepted": 7314, "declined": 7315, "cancelled": 7316}[later_status])
    offer = _offer(guide_os_id)
    receive_assignment_offer(offer)
    if later_status == "declined":
        decline_assignment(guide_os_id, offer.assignment_id, decision_event_id=str(uuid4()))
    else:
        accepted = accept_assignment(
            guide_os_id, offer.assignment_id, decision_event_id=str(uuid4())
        )
        if later_status == "cancelled":
            apply_assignment_cancellation(
                AssignmentCancellationIntake(
                    event_id=str(uuid4()),
                    assignment_id=offer.assignment_id,
                    guide_os_id=guide_os_id,
                    version_number=1,
                    cancelled_at="2026-10-02T12:00:00+00:00",
                )
            )
        else:
            assert accepted.projection_tour_id is not None

    projections_before = count_guide_operator_projections(offer.assignment_id)
    with pytest.raises(AssignmentNotActionableError):
        apply_assignment_lifecycle_transition(_event(offer))
    assert get_assignment_for_guide(guide_os_id, offer.assignment_id)["status"] == later_status
    assert count_guide_operator_projections(offer.assignment_id) == projections_before


def test_unexpected_projection_on_offered_assignment_fails_without_deletion() -> None:
    guide_os_id = _guide(7317)
    offer = _offer(guide_os_id)
    receive_assignment_offer(offer)
    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "UPDATE guide_operator_assignments SET projection_tour_id = 999999 WHERE assignment_id = ?",
            (offer.assignment_id,),
        )
        conn.commit()
    with pytest.raises(AssignmentConflictError):
        apply_assignment_lifecycle_transition(_event(offer))
    assert get_assignment_for_guide(guide_os_id, offer.assignment_id)["status"] == "offered"


def test_status_check_migration_preserves_existing_assignment_columns() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE guide_operator_assignments (
            assignment_id TEXT PRIMARY KEY, guide_os_id TEXT NOT NULL,
            company_id TEXT NOT NULL, company_name TEXT NOT NULL,
            guide_connection_id TEXT, role TEXT NOT NULL,
            start_date TEXT NOT NULL, end_date TEXT NOT NULL,
            response_deadline TEXT, operator_message TEXT,
            status TEXT NOT NULL CHECK(
                status IN ('offered', 'accepted', 'declined', 'cancelled')
            ),
            active_version_number INTEGER NOT NULL DEFAULT 1,
            projection_tour_id INTEGER UNIQUE, offer_event_id TEXT NOT NULL UNIQUE,
            offered_at TEXT NOT NULL, decided_at TEXT, cancelled_at TEXT,
            cancellation_event_id TEXT UNIQUE, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, active_version_unread INTEGER NOT NULL DEFAULT 0,
            pending_critical_version_number INTEGER
        )
        """
    )
    values = (
        "assignment-a",
        "11111111-1111-4111-8111-111111111111",
        "company-a",
        "Operator",
        "connection-a",
        "main_guide",
        "2026-11-01",
        "2026-11-02",
        "offered",
        "offer-a",
        "2026-10-01T00:00:00+00:00",
    )
    conn.execute(
        """
        INSERT INTO guide_operator_assignments (
            assignment_id, guide_os_id, company_id, company_name,
            guide_connection_id, role, start_date, end_date, status,
            offer_event_id, offered_at, created_at, updated_at,
            active_version_unread, pending_critical_version_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 2)
        """,
        (*values, values[-1], values[-1]),
    )
    _migrate_guide_operator_assignments_lifecycle(conn)

    row = conn.execute("SELECT * FROM guide_operator_assignments").fetchone()
    assert row is not None
    assert row["guide_connection_id"] == "connection-a"
    assert row["active_version_unread"] == 1
    assert row["pending_critical_version_number"] == 2
    conn.execute(
        "UPDATE guide_operator_assignments SET status = 'withdrawn' WHERE assignment_id = ?",
        ("assignment-a",),
    )
    conn.execute(
        "UPDATE guide_operator_assignments SET status = 'expired' WHERE assignment_id = ?",
        ("assignment-a",),
    )
    conn.close()
