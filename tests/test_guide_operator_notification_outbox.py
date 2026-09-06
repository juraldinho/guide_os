"""GO10A1: durable guide-notification outbox for Guide Operator intake."""

from __future__ import annotations

import copy
import json
import sqlite3
from uuid import uuid4

import pytest

from database.db import get_connection, init_db
from database.queries import (
    count_guide_operator_guide_notifications,
    get_guide_operator_guide_notification_by_source_event_id,
    get_guide_os_id,
    get_user_id_by_guide_os_id,
    list_guide_operator_guide_notifications_for_guide,
    register_user,
)
from services import guide_operator_assignment_service as go_assignments
from services import guide_operator_connection_service as go_connections
from services.guide_operator_assignment_service import (
    AssignmentCancellationIntake,
    AssignmentOfferIntake,
    AssignmentVersionPublishedIntake,
    accept_assignment,
    apply_assignment_cancellation,
    apply_ordinary_assignment_version,
    intake_critical_assignment_version,
    receive_assignment_offer,
)
from services.guide_operator_connection_service import (
    ConnectionDisconnectIntake,
    ConnectionInvitationIntake,
    confirm_connection,
    ensure_confirmed_connection_for_tests,
    receive_connection_disconnect,
    receive_connection_invitation,
)
from services.guide_operator_notification_outbox import (
    deep_link_target_for_assignment,
    deep_link_target_for_connection,
)


def _seed_guide(user_id: int = 1101) -> str:
    register_user(user_id)
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    return guide_os_id


def _invitation(
    guide_os_id: str,
    *,
    event_id: str | None = None,
    connection_id: str | None = None,
    company_name: str = "Operator Co",
    invited_at: str = "2026-09-01T10:00:00+00:00",
) -> ConnectionInvitationIntake:
    return ConnectionInvitationIntake(
        event_id=event_id or str(uuid4()),
        connection_id=connection_id or str(uuid4()),
        company_id=str(uuid4()),
        company_name=company_name,
        guide_os_id=guide_os_id,
        invitation_expires_at="2099-12-31T23:59:59+00:00",
        invited_at=invited_at,
    )


def _package(
    assignment_id: str,
    guide_os_id: str,
    *,
    start_date: str = "2026-09-10",
    end_date: str = "2026-09-12",
    title: str = "Notify tour",
    secret_contact: str = "Hidden Ops Contact",
) -> dict:
    return {
        "tour": {
            "title": title,
            "city_or_route": "Samarkand",
            "reference": "T-NOTIFY",
        },
        "assignment": {
            "id": assignment_id,
            "guide_os_id": guide_os_id,
            "role": "main_guide",
            "start_date": start_date,
            "end_date": end_date,
        },
        "days": [
            {
                "date": start_date,
                "title": "Day 1",
                "city_or_route": "Samarkand",
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
                "city_or_route": "Bukhara",
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
        "group_summary": "12 pax",
        "working_conditions": "internal comment must not leak",
        "drivers": [{"name": "Ali", "phone": "+998901111111"}],
        "contacts": [{"name": secret_contact, "phone": "+998902222222"}],
    }


def _offer(
    guide_os_id: str,
    *,
    event_id: str | None = None,
    assignment_id: str | None = None,
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
        start_date="2026-09-10",
        end_date="2026-09-12",
        working_package=_package(assignment_id, guide_os_id),
    )


def _accept(guide_os_id: str, offer: AssignmentOfferIntake):
    receive_assignment_offer(offer)
    return accept_assignment(
        guide_os_id,
        offer.assignment_id,
        decision_event_id=str(uuid4()),
    )


def _assert_safe_row(row: dict) -> None:
    serialized = json.dumps(row, ensure_ascii=False, sort_keys=True)
    assert "working_package" not in serialized
    assert "working_conditions" not in serialized
    assert "Hidden Ops Contact" not in serialized
    assert "+99890" not in serialized
    assert "eyJ" not in serialized
    assert "BEGIN PRIVATE KEY" not in serialized
    assert "telegram" not in serialized.lower()
    assert "user_id" not in row
    assert row["delivery_status"] == "pending"
    assert row["delivered_at"] is None
    assert row["failed_at"] is None
    assert int(row["attempt_count"]) == 0
    assert row["last_error_code"] is None


def test_connection_invitation_creates_notification():
    guide_os_id = _seed_guide(1101)
    invite = _invitation(guide_os_id, company_name="Invite Co")
    receive_connection_invitation(invite)
    row = get_guide_operator_guide_notification_by_source_event_id(invite.event_id)
    assert row is not None
    assert row["guide_os_id"] == guide_os_id
    assert row["notification_type"] == "connection_invitation"
    assert row["company_name"] == "Invite Co"
    assert row["connection_id"] == invite.connection_id
    assert row["assignment_id"] is None
    assert row["version_number"] is None
    assert row["deep_link_target"] == deep_link_target_for_connection(
        invite.connection_id
    )
    assert row["created_at"] == invite.invited_at
    _assert_safe_row(row)


def test_assignment_offer_creates_notification():
    guide_os_id = _seed_guide(1102)
    offer = _offer(guide_os_id, company_name="Offer Co")
    receive_assignment_offer(offer)
    row = get_guide_operator_guide_notification_by_source_event_id(offer.event_id)
    assert row is not None
    assert row["notification_type"] == "assignment_offer"
    assert row["company_name"] == "Offer Co"
    assert row["assignment_id"] == offer.assignment_id
    assert row["connection_id"] is None
    assert int(row["version_number"]) == 1
    assert row["deep_link_target"] == deep_link_target_for_assignment(
        offer.assignment_id
    )
    _assert_safe_row(row)


def test_ordinary_version_creates_notification():
    guide_os_id = _seed_guide(1103)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    package = copy.deepcopy(offer.working_package)
    package["group_summary"] = "14 pax"
    event = AssignmentVersionPublishedIntake(
        event_id=str(uuid4()),
        assignment_id=offer.assignment_id,
        guide_os_id=guide_os_id,
        version_number=2,
        previous_active_version_number=1,
        severity="ordinary",
        working_package=package,
        change_summary=[
            {"code": "group_summary", "severity": "ordinary", "path": "group_summary"}
        ],
        published_at="2026-09-03T09:00:00+00:00",
    )
    apply_ordinary_assignment_version(event)
    row = get_guide_operator_guide_notification_by_source_event_id(event.event_id)
    assert row is not None
    assert row["notification_type"] == "ordinary_version_change"
    assert int(row["version_number"]) == 2
    assert row["assignment_id"] == offer.assignment_id
    _assert_safe_row(row)


def test_critical_version_creates_notification():
    guide_os_id = _seed_guide(1104)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    package = copy.deepcopy(offer.working_package)
    package["assignment"]["start_date"] = "2026-09-11"
    package["assignment"]["end_date"] = "2026-09-13"
    package["days"][0]["date"] = "2026-09-11"
    package["days"][1]["date"] = "2026-09-13"
    event = AssignmentVersionPublishedIntake(
        event_id=str(uuid4()),
        assignment_id=offer.assignment_id,
        guide_os_id=guide_os_id,
        version_number=2,
        previous_active_version_number=1,
        severity="critical",
        working_package=package,
        change_summary=[
            {
                "code": "start_date_changed",
                "severity": "critical",
                "path": "assignment.start_date",
                "change": "updated",
                "before": "2026-09-10",
                "after": "2026-09-11",
            }
        ],
        published_at="2026-09-03T10:00:00+00:00",
    )
    intake_critical_assignment_version(event)
    row = get_guide_operator_guide_notification_by_source_event_id(event.event_id)
    assert row is not None
    assert row["notification_type"] == "critical_confirmation_required"
    assert int(row["version_number"]) == 2
    _assert_safe_row(row)


def test_cancellation_creates_historical_notification():
    guide_os_id = _seed_guide(1105)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    event = AssignmentCancellationIntake(
        event_id=str(uuid4()),
        assignment_id=offer.assignment_id,
        guide_os_id=guide_os_id,
        version_number=1,
        cancelled_at="2026-09-04T12:00:00+00:00",
    )
    apply_assignment_cancellation(event)
    row = get_guide_operator_guide_notification_by_source_event_id(event.event_id)
    assert row is not None
    assert row["notification_type"] == "assignment_cancellation"
    assert int(row["version_number"]) == 1
    assert row["delivery_status"] == "pending"
    # Historical/inspectable: row remains after successful cancel.
    assert count_guide_operator_guide_notifications(
        guide_os_id=guide_os_id, notification_type="assignment_cancellation"
    ) == 1
    _assert_safe_row(row)


def test_disconnection_creates_historical_notification():
    guide_os_id = _seed_guide(1106)
    invite = _invitation(guide_os_id, company_name="Leave Co")
    receive_connection_invitation(invite)
    confirm_connection(
        guide_os_id,
        invite.connection_id,
        decision_event_id=str(uuid4()),
        decided_at="2026-09-02T12:00:00+00:00",
    )
    disconnect = ConnectionDisconnectIntake(
        event_id=str(uuid4()),
        connection_id=invite.connection_id,
        company_id=invite.company_id,
        company_name=invite.company_name,
        guide_os_id=guide_os_id,
        disconnected_at="2026-09-05T08:00:00+00:00",
    )
    receive_connection_disconnect(disconnect)
    row = get_guide_operator_guide_notification_by_source_event_id(disconnect.event_id)
    assert row is not None
    assert row["notification_type"] == "connection_disconnection"
    assert row["connection_id"] == invite.connection_id
    assert row["company_name"] == "Leave Co"
    assert count_guide_operator_guide_notifications(
        guide_os_id=guide_os_id, notification_type="connection_disconnection"
    ) == 1
    _assert_safe_row(row)


def test_duplicate_intake_does_not_duplicate_notifications():
    guide_os_id = _seed_guide(1107)
    invite = _invitation(guide_os_id)
    receive_connection_invitation(invite)
    receive_connection_invitation(invite)
    assert count_guide_operator_guide_notifications(guide_os_id=guide_os_id) == 1

    offer = _offer(guide_os_id)
    receive_assignment_offer(offer)
    receive_assignment_offer(offer)
    assert (
        count_guide_operator_guide_notifications(
            guide_os_id=guide_os_id, notification_type="assignment_offer"
        )
        == 1
    )

    _accept(guide_os_id, offer)
    package = copy.deepcopy(offer.working_package)
    package["group_summary"] = "15 pax"
    ordinary = AssignmentVersionPublishedIntake(
        event_id=str(uuid4()),
        assignment_id=offer.assignment_id,
        guide_os_id=guide_os_id,
        version_number=2,
        previous_active_version_number=1,
        severity="ordinary",
        working_package=package,
        change_summary=[
            {"code": "group_summary", "severity": "ordinary", "path": "group_summary"}
        ],
        published_at="2026-09-03T09:00:00+00:00",
    )
    apply_ordinary_assignment_version(ordinary)
    apply_ordinary_assignment_version(ordinary)
    assert (
        count_guide_operator_guide_notifications(
            guide_os_id=guide_os_id, notification_type="ordinary_version_change"
        )
        == 1
    )


def test_failed_intake_rolls_back_notification(monkeypatch):
    guide_os_id = _seed_guide(1108)
    invite = _invitation(guide_os_id)

    def boom():
        raise RuntimeError("forced invitation failure")

    monkeypatch.setattr(go_connections, "_CONNECTION_INTAKE_FAILURE_HOOK", boom)
    with pytest.raises(RuntimeError, match="forced invitation failure"):
        receive_connection_invitation(invite)
    assert get_guide_operator_guide_notification_by_source_event_id(invite.event_id) is None
    assert count_guide_operator_guide_notifications(guide_os_id=guide_os_id) == 0

    monkeypatch.setattr(go_connections, "_CONNECTION_INTAKE_FAILURE_HOOK", None)
    receive_connection_invitation(invite)
    confirm_connection(
        guide_os_id,
        invite.connection_id,
        decision_event_id=str(uuid4()),
    )

    assignment_id = str(uuid4())
    offer = AssignmentOfferIntake(
        event_id=str(uuid4()),
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
        company_id=invite.company_id,
        company_name=invite.company_name,
        guide_connection_id=invite.connection_id,
        role="main_guide",
        start_date="2026-09-10",
        end_date="2026-09-12",
        working_package=_package(assignment_id, guide_os_id),
    )

    def offer_boom():
        raise RuntimeError("forced offer failure")

    monkeypatch.setattr(go_assignments, "_OFFER_INTAKE_FAILURE_HOOK", offer_boom)
    with pytest.raises(RuntimeError, match="forced offer failure"):
        receive_assignment_offer(offer)
    assert get_guide_operator_guide_notification_by_source_event_id(offer.event_id) is None
    assert (
        count_guide_operator_guide_notifications(
            guide_os_id=guide_os_id, notification_type="assignment_offer"
        )
        == 0
    )


def test_wrong_guide_cannot_list_other_notifications():
    guide_a = _seed_guide(1109)
    guide_b = _seed_guide(1110)
    invite = _invitation(guide_a, company_name="Only A")
    receive_connection_invitation(invite)
    rows_a = list_guide_operator_guide_notifications_for_guide(guide_a)
    rows_b = list_guide_operator_guide_notifications_for_guide(guide_b)
    assert len(rows_a) == 1
    assert rows_a[0]["source_event_id"] == invite.event_id
    assert rows_b == []


def test_notification_ordering_newest_first():
    guide_os_id = _seed_guide(1111)
    first = _invitation(
        guide_os_id, company_name="First Co", invited_at="2026-09-01T10:00:00+00:00"
    )
    second = _invitation(
        guide_os_id, company_name="Second Co", invited_at="2026-09-02T10:00:00+00:00"
    )
    receive_connection_invitation(first)
    receive_connection_invitation(second)
    rows = list_guide_operator_guide_notifications_for_guide(guide_os_id)
    assert [row["company_name"] for row in rows] == ["Second Co", "First Co"]


def test_privacy_excludes_packages_contacts_and_secrets():
    guide_os_id = _seed_guide(1112)
    offer = _offer(guide_os_id)
    receive_assignment_offer(offer)
    row = get_guide_operator_guide_notification_by_source_event_id(offer.event_id)
    assert row is not None
    _assert_safe_row(row)
    assert set(row.keys()) >= {
        "source_event_id",
        "guide_os_id",
        "notification_type",
        "company_name",
        "assignment_id",
        "version_number",
        "deep_link_target",
        "created_at",
        "delivery_status",
        "delivered_at",
        "failed_at",
        "attempt_count",
        "last_error_code",
        "next_attempt_at",
    }
    assert "working_package_json" not in row
    assert "payload_json" not in row


def test_existing_database_migrates_notification_table(monkeypatch, tmp_path):
    import database.db as db_module

    path = tmp_path / "pre-go10a1.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            first_seen TEXT,
            last_seen TEXT,
            guide_os_id TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO users VALUES (77, '2025-01-01', '2025-01-02', ?)",
        (str(uuid4()),),
    )
    conn.execute(
        """
        CREATE TABLE guide_operator_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            event_type TEXT NOT NULL,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            guide_os_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            delivered_at TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO guide_operator_outbox (
            event_id, event_type, aggregate_type, aggregate_id,
            guide_os_id, payload_json, created_at, delivered_at, attempt_count
        ) VALUES ('evt-keep', 'assignment.decision.v1', 'guide_assignment',
                  'a1', 'g1', '{}', '2026-01-01T00:00:00+00:00', NULL, 0)
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_module, "DB_PATH", str(path))
    init_db()
    init_db()
    conn = get_connection()
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "guide_operator_guide_notifications" in tables
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(guide_operator_guide_notifications)"
            )
        }
        assert {
            "source_event_id",
            "guide_os_id",
            "notification_type",
            "company_name",
            "deep_link_target",
            "delivery_status",
            "delivered_at",
            "failed_at",
            "attempt_count",
        } <= columns
        kept = conn.execute(
            "SELECT event_id FROM guide_operator_outbox WHERE event_id = 'evt-keep'"
        ).fetchone()
        assert kept is not None
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM guide_operator_guide_notifications"
            ).fetchone()[0]
            == 0
        )
    finally:
        conn.close()


def test_failed_validation_creates_no_notification():
    guide_os_id = _seed_guide(1113)
    with pytest.raises(Exception):
        receive_connection_invitation(
            ConnectionInvitationIntake(
                event_id=str(uuid4()),
                connection_id=str(uuid4()),
                company_id=str(uuid4()),
                company_name="X",
                guide_os_id="not-a-uuid",
                invitation_expires_at="2099-12-31T23:59:59+00:00",
                invited_at="2026-09-01T10:00:00+00:00",
            )
        )
    assert count_guide_operator_guide_notifications() == 0
    assert get_user_id_by_guide_os_id(guide_os_id) is not None
