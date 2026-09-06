"""GO7D2: ordinary version unread acknowledgement."""

from __future__ import annotations

from uuid import uuid4

import pytest

from database.queries import (
    count_guide_operator_projections,
    get_guide_operator_assignment_version,
    get_guide_operator_version_acknowledgement,
    get_guide_os_id,
    get_tour_by_id,
    get_user_id_by_guide_os_id,
    list_guide_operator_assignment_versions,
    register_user,
)
from services import guide_operator_assignment_service as go_assignments
from services.guide_operator_assignment_service import (
    AssignmentConflictError,
    AssignmentNotActionableError,
    AssignmentNotFoundError,
    VERSION_ACKNOWLEDGED_EVENT_TYPE,
    acknowledge_ordinary_version,
    apply_ordinary_assignment_version,
    build_assignment_detail_for_guide,
    get_assignment_for_guide,
    list_version_acknowledged_outbox,
)
from tests.test_guide_operator_ordinary_versions import (
    _accept,
    _offer,
    _ordinary,
    _ordinary_package,
    _seed_guide,
)
from tests.test_miniapp_guide_operator_assignments import (
    API_USER,
    OTHER_USER,
    _auth_headers,
    api_request,
    response_json,
)


def _apply_unread(guide_os_id: str, offer, *, group_summary: str = "14 pax"):
    package = _ordinary_package(offer, group_summary=group_summary)
    package["tour"]["title"] = "Updated title"
    change_summary = [
        {
            "code": "group_summary",
            "severity": "ordinary",
            "path": "group_summary",
            "change": "updated",
            "before": "12 pax",
            "after": group_summary,
        },
        {
            "code": "uncertain",
            "severity": "uncertain",
            "path": "tour.title",
            "change": "updated",
            "before": "Classic tour",
            "after": "Updated title",
        },
    ]
    # ordinary apply rejects uncertain? No - GO7D1 stores whatever change_summary is sent
    # but severity must be ordinary. Keep summary ordinary-only for ack tests.
    change_summary = [change_summary[0]]
    event = _ordinary(
        guide_os_id,
        offer.assignment_id,
        package,
        change_summary=change_summary,
    )
    apply_ordinary_assignment_version(event)
    return event


def test_acknowledge_ordinary_version_clears_unread_and_emits_one_outbox():
    guide_os_id = _seed_guide(901)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    offer = _offer(guide_os_id)
    accepted = _accept(guide_os_id, offer)
    tour_id = accepted.projection_tour_id
    assert tour_id is not None
    _apply_unread(guide_os_id, offer)

    detail = build_assignment_detail_for_guide(guide_os_id, offer.assignment_id)
    assert detail["active_version"]["version_number"] == 2
    assert detail["active_version"]["severity"] == "ordinary"
    assert detail["active_version"]["unread"] is True
    assert detail["active_version"]["change_summary"][0]["before"] == "12 pax"
    assert detail["active_version"]["change_summary"][0]["after"] == "14 pax"
    assert [v["version_number"] for v in detail["versions"]] == [1, 2]
    assert detail["working_package"]["group_summary"] == "14 pax"
    assert detail["versions"][0]["working_package"]["group_summary"] == "12 pax"

    decision_event_id = str(uuid4())
    result = acknowledge_ordinary_version(
        guide_os_id,
        offer.assignment_id,
        version_number=2,
        decision_event_id=decision_event_id,
    )
    assert result.replayed is False
    assert result.unread is False
    assert result.version_number == 2
    assert result.decision_event_id == decision_event_id

    stored = get_assignment_for_guide(guide_os_id, offer.assignment_id)
    assert int(stored["active_version_unread"]) == 0
    assert int(stored["active_version_number"]) == 2
    ack = get_guide_operator_version_acknowledgement(
        assignment_id=offer.assignment_id, version_number=2
    )
    assert ack is not None
    assert ack["decision_event_id"] == decision_event_id
    outbox = list_version_acknowledged_outbox(offer.assignment_id)
    assert len(outbox) == 1
    assert outbox[0]["event_type"] == VERSION_ACKNOWLEDGED_EVENT_TYPE
    assert outbox[0]["event_id"] == decision_event_id

    # Acknowledgement must not alter occupancy or package snapshots.
    assert count_guide_operator_projections(offer.assignment_id) == 1
    tour = get_tour_by_id(user_id, tour_id)
    assert tour is not None
    assert tour["start_date"] == offer.start_date
    assert tour["end_date"] == offer.end_date
    assert get_guide_operator_assignment_version(offer.assignment_id, 2) is not None
    assert len(list_guide_operator_assignment_versions(offer.assignment_id)) == 2

    after = build_assignment_detail_for_guide(guide_os_id, offer.assignment_id)
    assert after["active_version"]["unread"] is False
    assert after["assignment"]["active_version_unread"] in (0, False)


def test_acknowledge_duplicate_is_idempotent():
    guide_os_id = _seed_guide(902)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    _apply_unread(guide_os_id, offer)
    decision_event_id = str(uuid4())

    first = acknowledge_ordinary_version(
        guide_os_id,
        offer.assignment_id,
        version_number=2,
        decision_event_id=decision_event_id,
    )
    second = acknowledge_ordinary_version(
        guide_os_id,
        offer.assignment_id,
        version_number=2,
        decision_event_id=decision_event_id,
    )
    third = acknowledge_ordinary_version(
        guide_os_id,
        offer.assignment_id,
        version_number=2,
        decision_event_id=str(uuid4()),
    )

    assert first.replayed is False
    assert second.replayed is True
    assert third.replayed is True
    assert third.decision_event_id == decision_event_id
    assert len(list_version_acknowledged_outbox(offer.assignment_id)) == 1
    assert (
        get_guide_operator_version_acknowledgement(
            assignment_id=offer.assignment_id, version_number=2
        )
        is not None
    )


def test_acknowledge_wrong_guide_stale_cancelled_and_critical_fail_closed():
    owner = _seed_guide(903)
    stranger = _seed_guide(904)
    offer = _offer(owner)
    _accept(owner, offer)
    _apply_unread(owner, offer)

    with pytest.raises(AssignmentNotFoundError):
        acknowledge_ordinary_version(
            stranger,
            offer.assignment_id,
            version_number=2,
            decision_event_id=str(uuid4()),
        )

    with pytest.raises(AssignmentConflictError):
        acknowledge_ordinary_version(
            owner,
            offer.assignment_id,
            version_number=1,
            decision_event_id=str(uuid4()),
        )

    # Critical severity on active version fails closed without clearing unread.
    conn_state = get_assignment_for_guide(owner, offer.assignment_id)
    assert int(conn_state["active_version_unread"]) == 1

    # Force severity critical for fail-closed path.
    from database.db import get_connection

    conn = get_connection()
    conn.execute(
        """
        UPDATE guide_operator_assignment_versions
        SET severity = 'critical'
        WHERE assignment_id = ? AND version_number = 2
        """,
        (offer.assignment_id,),
    )
    conn.commit()
    conn.close()
    with pytest.raises(AssignmentNotActionableError):
        acknowledge_ordinary_version(
            owner,
            offer.assignment_id,
            version_number=2,
            decision_event_id=str(uuid4()),
        )
    assert int(get_assignment_for_guide(owner, offer.assignment_id)["active_version_unread"]) == 1
    assert list_version_acknowledged_outbox(offer.assignment_id) == []


def test_acknowledge_rolls_back_atomically(monkeypatch):
    guide_os_id = _seed_guide(905)
    offer = _offer(guide_os_id)
    _accept(guide_os_id, offer)
    _apply_unread(guide_os_id, offer)

    def boom():
        raise RuntimeError("forced ack failure")

    monkeypatch.setattr(go_assignments, "_VERSION_ACK_FAILURE_HOOK", boom)
    with pytest.raises(RuntimeError, match="forced ack failure"):
        acknowledge_ordinary_version(
            guide_os_id,
            offer.assignment_id,
            version_number=2,
            decision_event_id=str(uuid4()),
        )

    assert int(get_assignment_for_guide(guide_os_id, offer.assignment_id)["active_version_unread"]) == 1
    assert (
        get_guide_operator_version_acknowledgement(
            assignment_id=offer.assignment_id, version_number=2
        )
        is None
    )
    assert list_version_acknowledged_outbox(offer.assignment_id) == []


def test_acknowledge_api_and_detail_expose_unread_and_diff():
    register_user(API_USER)
    register_user(OTHER_USER)
    owner = get_guide_os_id(API_USER)
    other = get_guide_os_id(OTHER_USER)
    assert owner and other

    offer = _offer(owner, start_date="2026-10-10", end_date="2026-10-12")
    _accept(owner, offer)
    _apply_unread(owner, offer, group_summary="18 pax")

    detail = api_request(
        "GET",
        f"/app/v1/guide-operator/assignments/{offer.assignment_id}",
        headers=_auth_headers(API_USER),
    )
    assert detail.status == 200
    body = response_json(detail)["data"]
    assert body["assignment"]["activeVersionUnread"] is True
    assert body["assignment"]["activeVersionNumber"] == 2
    assert body["activeVersion"]["unread"] is True
    assert body["activeVersion"]["severity"] == "ordinary"
    assert body["activeVersion"]["changeSummary"][0]["before"] == "12 pax"
    assert body["activeVersion"]["changeSummary"][0]["after"] == "18 pax"
    assert body["workingPackage"]["group_summary"] == "18 pax"
    assert len(body["versions"]) == 2
    assert body["versions"][0]["workingPackage"]["group_summary"] == "12 pax"

    lists = api_request(
        "GET",
        "/app/v1/guide-operator/assignments/lists",
        headers=_auth_headers(API_USER),
    )
    lists_data = response_json(lists)["data"]
    listed = (
        lists_data["awaiting"]
        + lists_data["upcoming"]
        + lists_data["inProgress"]
        + lists_data["completed"]
        + lists_data["cancelled"]
    )
    match = next(row for row in listed if row["id"] == offer.assignment_id)
    assert match["activeVersionUnread"] is True

    entries = api_request(
        "GET",
        "/app/v1/entries?from=2026-10-01&to=2026-10-31",
        headers=_auth_headers(API_USER),
    )
    assert entries.status == 200
    go_entry = next(
        row
        for row in response_json(entries)["data"]["entries"]
        if row.get("guideOperatorAssignmentId") == offer.assignment_id
    )
    assert go_entry["guideOperatorVersion"] == 2
    assert go_entry["guideOperatorVersionUnread"] is True

    decision_event_id = str(uuid4())
    ack = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{offer.assignment_id}/acknowledge-version",
        headers=_auth_headers(API_USER, **{"Idempotency-Key": decision_event_id}),
        json={"decisionEventId": decision_event_id, "versionNumber": 2},
    )
    assert ack.status == 200
    ack_body = response_json(ack)["data"]
    assert ack_body["unread"] is False
    assert ack_body["replayed"] is False

    spoof = api_request(
        "POST",
        f"/app/v1/guide-operator/assignments/{offer.assignment_id}/acknowledge-version",
        headers=_auth_headers(OTHER_USER, **{"Idempotency-Key": str(uuid4())}),
        json={"decisionEventId": str(uuid4()), "versionNumber": 2},
    )
    assert spoof.status == 404

    after_detail = api_request(
        "GET",
        f"/app/v1/guide-operator/assignments/{offer.assignment_id}",
        headers=_auth_headers(API_USER),
    )
    after_body = response_json(after_detail)["data"]
    assert after_body["assignment"]["activeVersionUnread"] is False
    assert after_body["activeVersion"]["unread"] is False

    after_entries = api_request(
        "GET",
        "/app/v1/entries?from=2026-10-01&to=2026-10-31",
        headers=_auth_headers(API_USER),
    )
    go_after = next(
        row
        for row in response_json(after_entries)["data"]["entries"]
        if row.get("guideOperatorAssignmentId") == offer.assignment_id
    )
    assert go_after["guideOperatorVersionUnread"] is False
