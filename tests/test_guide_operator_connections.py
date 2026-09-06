"""GO8C2: Guide Operator connection-consent domain."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from database.queries import (
    get_guide_operator_assignment,
    get_guide_os_id,
    get_user_id_by_guide_os_id,
    list_guide_operator_outbox_events,
    register_user,
)
from services import guide_operator_connection_service as go_connections
from services.guide_operator_assignment_service import (
    AssignmentOfferIntake,
    AssignmentValidationError,
    accept_assignment,
    get_assignment_for_guide,
    receive_assignment_offer,
)
from services.guide_operator_connection_service import (
    CONNECTION_DECIDED_EVENT_TYPE,
    ConnectionConflictError,
    ConnectionDisconnectIntake,
    ConnectionInvitationIntake,
    ConnectionNotActionableError,
    ConnectionNotFoundError,
    confirm_connection,
    decline_connection,
    ensure_confirmed_connection_for_tests,
    get_connection_for_guide,
    list_connection_decision_outbox,
    receive_connection_disconnect,
    receive_connection_invitation,
)


def _seed_guide(user_id: int = 801) -> str:
    register_user(user_id)
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    assert get_user_id_by_guide_os_id(guide_os_id) == user_id
    return guide_os_id


def _invitation(
    guide_os_id: str,
    *,
    connection_id: str | None = None,
    company_id: str | None = None,
    company_name: str = "Operator Co",
    invitation_expires_at: str = "2099-12-31T23:59:59+00:00",
    invited_at: str = "2026-09-01T10:00:00+00:00",
    event_id: str | None = None,
) -> ConnectionInvitationIntake:
    return ConnectionInvitationIntake(
        event_id=event_id or str(uuid4()),
        connection_id=connection_id or str(uuid4()),
        company_id=company_id or str(uuid4()),
        company_name=company_name,
        guide_os_id=guide_os_id,
        invitation_expires_at=invitation_expires_at,
        invited_at=invited_at,
    )


def _offer_for_connection(
    guide_os_id: str,
    connection: dict,
    *,
    assignment_id: str | None = None,
    company_id: str | None = None,
    guide_connection_id: str | None = None,
) -> AssignmentOfferIntake:
    assignment_id = assignment_id or str(uuid4())
    start_date = "2026-10-01"
    end_date = "2026-10-03"
    return AssignmentOfferIntake(
        event_id=str(uuid4()),
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
        company_id=company_id or connection["company_id"],
        company_name=connection["company_name"],
        guide_connection_id=guide_connection_id or connection["connection_id"],
        role="main_guide",
        start_date=start_date,
        end_date=end_date,
        working_package={
            "tour": {"title": "Consent tour", "city_or_route": "Tashkent"},
            "assignment": {
                "id": assignment_id,
                "role": "main_guide",
                "start_date": start_date,
                "end_date": end_date,
            },
            "days": [{"date": start_date, "title": "Day 1", "city_or_route": "Tashkent"}],
        },
    )


def test_invitation_intake_confirm_and_exactly_one_decision_outbox():
    guide_os_id = _seed_guide(801)
    invite = _invitation(guide_os_id)
    stored = receive_connection_invitation(invite)
    assert stored["status"] == "invited"
    assert stored["connection_id"] == invite.connection_id
    assert stored["company_id"] == invite.company_id
    assert stored["guide_os_id"] == guide_os_id

    decision_event_id = str(uuid4())
    result = confirm_connection(
        guide_os_id,
        invite.connection_id,
        decision_event_id=decision_event_id,
        decided_at="2026-09-02T12:00:00+00:00",
    )
    assert result.status == "confirmed"
    assert result.decision == "confirm"
    assert result.replayed is False

    connection = get_connection_for_guide(guide_os_id, invite.connection_id)
    assert connection["status"] == "confirmed"
    assert connection["decided_at"] == "2026-09-02T12:00:00+00:00"

    outbox = list_connection_decision_outbox(invite.connection_id)
    assert len(outbox) == 1
    assert outbox[0]["event_id"] == decision_event_id
    assert outbox[0]["event_type"] == CONNECTION_DECIDED_EVENT_TYPE
    payload = json.loads(outbox[0]["payload_json"])
    assert payload == {
        "company_id": invite.company_id,
        "company_name": invite.company_name,
        "connection_id": invite.connection_id,
        "decided_at": "2026-09-02T12:00:00+00:00",
        "decision": "confirm",
        "guide_os_id": guide_os_id,
    }

    replay = confirm_connection(
        guide_os_id,
        invite.connection_id,
        decision_event_id=decision_event_id,
    )
    assert replay.replayed is True
    assert len(list_connection_decision_outbox(invite.connection_id)) == 1


def test_decline_invitation():
    guide_os_id = _seed_guide(802)
    invite = _invitation(guide_os_id)
    receive_connection_invitation(invite)
    result = decline_connection(
        guide_os_id,
        invite.connection_id,
        decision_event_id=str(uuid4()),
    )
    assert result.status == "declined"
    assert result.decision == "decline"
    connection = get_connection_for_guide(guide_os_id, invite.connection_id)
    assert connection["status"] == "declined"
    assert len(list_connection_decision_outbox(invite.connection_id)) == 1


def test_expired_invitation_cannot_be_confirmed():
    guide_os_id = _seed_guide(803)
    invite = _invitation(
        guide_os_id,
        invitation_expires_at="2026-01-01T00:00:00+00:00",
        invited_at="2025-12-01T00:00:00+00:00",
    )
    receive_connection_invitation(invite)
    with pytest.raises(ConnectionNotActionableError) as exc:
        confirm_connection(
            guide_os_id,
            invite.connection_id,
            decision_event_id=str(uuid4()),
        )
    assert exc.value.details.get("code") == "connection_expired"
    assert list_connection_decision_outbox(invite.connection_id) == []


def test_disconnect_is_terminal_for_new_offers_and_retains_history():
    guide_os_id = _seed_guide(804)
    connection = ensure_confirmed_connection_for_tests(guide_os_id)
    offer = _offer_for_connection(guide_os_id, connection)
    receive_assignment_offer(offer)
    accepted = accept_assignment(
        guide_os_id, offer.assignment_id, decision_event_id=str(uuid4())
    )
    assert accepted.status == "accepted"

    disconnected = receive_connection_disconnect(
        ConnectionDisconnectIntake(
            event_id=str(uuid4()),
            connection_id=connection["connection_id"],
            company_id=connection["company_id"],
            company_name=connection["company_name"],
            guide_os_id=guide_os_id,
            disconnected_at="2026-09-05T08:00:00+00:00",
        )
    )
    assert disconnected["status"] == "disconnected"

    historical = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert historical["status"] == "accepted"
    assert historical["guide_connection_id"] == connection["connection_id"]

    with pytest.raises(AssignmentValidationError) as exc:
        receive_assignment_offer(_offer_for_connection(guide_os_id, connection))
    assert exc.value.details.get("code") == "connection_disconnected"

    blocked = _offer_for_connection(guide_os_id, connection)
    with pytest.raises(AssignmentValidationError):
        receive_assignment_offer(blocked)
    assert get_guide_operator_assignment(blocked.assignment_id) is None


def test_duplicate_invitation_and_disconnect_replay_conflicts_fail_closed():
    guide_os_id = _seed_guide(805)
    invite = _invitation(guide_os_id)
    first = receive_connection_invitation(invite)
    second = receive_connection_invitation(invite)
    assert first["connection_id"] == second["connection_id"]

    conflicting = ConnectionInvitationIntake(
        event_id=invite.event_id,
        connection_id=invite.connection_id,
        company_id=invite.company_id,
        company_name="Other Name",
        guide_os_id=guide_os_id,
        invitation_expires_at=invite.invitation_expires_at,
        invited_at=invite.invited_at,
    )
    with pytest.raises(ConnectionConflictError):
        receive_connection_invitation(conflicting)

    confirm_connection(
        guide_os_id, invite.connection_id, decision_event_id=str(uuid4())
    )
    disconnect = ConnectionDisconnectIntake(
        event_id=str(uuid4()),
        connection_id=invite.connection_id,
        company_id=invite.company_id,
        company_name=invite.company_name,
        guide_os_id=guide_os_id,
        disconnected_at="2026-09-05T09:00:00+00:00",
    )
    receive_connection_disconnect(disconnect)
    again = receive_connection_disconnect(disconnect)
    assert again["status"] == "disconnected"

    conflict_disconnect = ConnectionDisconnectIntake(
        event_id=disconnect.event_id,
        connection_id=invite.connection_id,
        company_id=invite.company_id,
        company_name="Other Name",
        guide_os_id=guide_os_id,
        disconnected_at=disconnect.disconnected_at,
    )
    with pytest.raises(ConnectionConflictError):
        receive_connection_disconnect(conflict_disconnect)


def test_unrelated_guide_cannot_read_or_decide_connection():
    owner = _seed_guide(806)
    stranger = _seed_guide(807)
    invite = _invitation(owner)
    receive_connection_invitation(invite)

    with pytest.raises(ConnectionNotFoundError):
        get_connection_for_guide(stranger, invite.connection_id)
    with pytest.raises(ConnectionNotFoundError):
        confirm_connection(
            stranger, invite.connection_id, decision_event_id=str(uuid4())
        )


def test_offer_requires_confirmed_matching_connection():
    guide_os_id = _seed_guide(808)
    connection = ensure_confirmed_connection_for_tests(guide_os_id)

    # Missing connection
    missing = _offer_for_connection(
        guide_os_id,
        connection,
        guide_connection_id=str(uuid4()),
    )
    with pytest.raises(AssignmentValidationError) as missing_exc:
        receive_assignment_offer(missing)
    assert missing_exc.value.details.get("code") == "connection_missing"
    assert get_guide_operator_assignment(missing.assignment_id) is None

    # Company mismatch
    mismatch = _offer_for_connection(
        guide_os_id, connection, company_id=str(uuid4())
    )
    with pytest.raises(AssignmentValidationError) as mismatch_exc:
        receive_assignment_offer(mismatch)
    assert mismatch_exc.value.details.get("code") == "connection_company_mismatch"
    assert get_guide_operator_assignment(mismatch.assignment_id) is None

    # Declined connection
    invite = _invitation(guide_os_id)
    receive_connection_invitation(invite)
    decline_connection(
        guide_os_id, invite.connection_id, decision_event_id=str(uuid4())
    )
    declined_offer = AssignmentOfferIntake(
        event_id=str(uuid4()),
        assignment_id=str(uuid4()),
        guide_os_id=guide_os_id,
        company_id=invite.company_id,
        company_name=invite.company_name,
        guide_connection_id=invite.connection_id,
        role="main_guide",
        start_date="2026-11-01",
        end_date="2026-11-02",
        working_package={"tour": {"title": "X"}},
    )
    with pytest.raises(AssignmentValidationError) as declined_exc:
        receive_assignment_offer(declined_offer)
    assert declined_exc.value.details.get("code") == "connection_declined"
    assert get_guide_operator_assignment(declined_offer.assignment_id) is None

    # Happy path still works
    ok = _offer_for_connection(guide_os_id, connection)
    stored = receive_assignment_offer(ok)
    assert stored["guide_connection_id"] == connection["connection_id"]


def test_decision_atomic_rollback_leaves_no_outbox():
    guide_os_id = _seed_guide(809)
    invite = _invitation(guide_os_id)
    receive_connection_invitation(invite)

    def boom():
        raise RuntimeError("forced decide failure")

    go_connections._CONNECTION_DECIDE_FAILURE_HOOK = boom
    try:
        with pytest.raises(RuntimeError):
            confirm_connection(
                guide_os_id,
                invite.connection_id,
                decision_event_id=str(uuid4()),
            )
    finally:
        go_connections._CONNECTION_DECIDE_FAILURE_HOOK = None

    connection = get_connection_for_guide(guide_os_id, invite.connection_id)
    assert connection["status"] == "invited"
    assert list_connection_decision_outbox(invite.connection_id) == []
    outbox = list_guide_operator_outbox_events(
        assignment_id=invite.connection_id,
        event_type=CONNECTION_DECIDED_EVENT_TYPE,
    )
    assert outbox == []


def test_offer_rejected_for_invited_not_confirmed():
    guide_os_id = _seed_guide(810)
    invite = _invitation(guide_os_id)
    receive_connection_invitation(invite)
    offer = AssignmentOfferIntake(
        event_id=str(uuid4()),
        assignment_id=str(uuid4()),
        guide_os_id=guide_os_id,
        company_id=invite.company_id,
        company_name=invite.company_name,
        guide_connection_id=invite.connection_id,
        role="main_guide",
        start_date="2026-12-01",
        end_date="2026-12-02",
        working_package={"tour": {"title": "Pending consent"}},
    )
    with pytest.raises(AssignmentValidationError) as exc:
        receive_assignment_offer(offer)
    assert exc.value.details.get("code") == "connection_not_confirmed"
    assert get_guide_operator_assignment(offer.assignment_id) is None
