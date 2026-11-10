"""Session-scoped explicit assignment lifecycle; receive and outbound stay gated."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest

from database.db import get_db_connection, run_write_with_retry
from database.queries import register_user
from services import guide_operator_assignment_service as domain
from services.tour_service import save_tour
from tests.test_guide_operator_assignment_v2_contract import published
from tests.test_guide_operator_assignment_v2_intake import (
    decide,
    fingerprint,
    legacy_fixture,
    receive,
    seed,
)
from tests.test_guide_operator_daily_projections import rows, state
from tests.test_miniapp_guide_operator_assignments import (
    _auth_headers,
    api_request,
    response_json,
)


def call(event, action=None, *, user=501, method=None, body=None, suffix=""):
    identity = event["payload"]["assignment_id"]
    path = f"/app/v1/guide-operator/assignments/{identity}"
    if action:
        path += "/" + action
    if suffix:
        path += suffix
    response = api_request(
        method or ("POST" if action else "GET"),
        path,
        headers=_auth_headers(user),
        **({"json": body or {"decisionEventId": str(uuid4())}} if action else {}),
    )
    return response.status, response_json(response)


def critical(event, *, number=2, previous=1, date="2026-11-13"):
    result = published(event, number=number, previous=previous, severity="critical")
    result["payload"]["working_package"]["days"][1]["date"] = date
    result["payload"]["working_package"]["assignment"]["end_date"] = date
    receive(result)
    return result


def decision(event, action, *, version=None, event_id=None, user=501, **extra):
    body = {"decisionEventId": event_id or str(uuid4()), **extra}
    if version is not None:
        body["versionNumber"] = version
    return call(event, action, body=body, user=user)


def test_session_sparse_offer_reads_actions_and_intake_off(monkeypatch):
    event = seed()
    receive(event)
    monkeypatch.setenv(
        "GUIDE_OS_GUIDE_OPERATOR_ASSIGNMENT_EXPLICIT_DAYS_V2_RECEIVE_ENABLED", "false"
    )
    status, detail = call(event)
    assert status == 200
    assert detail["data"]["assignment"]["status"] == "offered"
    assert detail["data"]["assignment"]["projectionTourId"] is None
    assert detail["data"]["workingPackage"] == event["payload"]["working_package"]
    pending = api_request(
        "GET", "/app/v1/guide-operator/assignments/pending", headers=_auth_headers(501)
    )
    assert event["payload"]["assignment_id"] in {
        a["id"] for a in response_json(pending)["data"]["assignments"]
    }
    status, accepted = decision(event, "accept", guideOsId=str(uuid4()), userId=777)
    assert status == 200 and accepted["data"]["projectionTourId"] is None
    assert [r["calendar_date"] for r in rows(event["payload"]["assignment_id"])] == [
        "2026-11-10",
        "2026-11-12",
    ]
    before = fingerprint()
    assert decision(event, "accept")[1]["data"]["replayed"]
    assert decision(event, "decline")[0] == 409
    assert fingerprint() == before
    # Disabling intake never becomes a guide-action gate.
    ordinary = published(event)
    receive(ordinary)
    assert decision(event, "acknowledge-version", version=2)[0] == 200


@pytest.mark.parametrize(
    "action",
    [
        None,
        "accept",
        "decline",
        "confirm-critical",
        "reject-critical",
        "acknowledge-version",
    ],
)
def test_other_guide_cannot_read_or_act_even_with_body_and_navigation_spoof(action):
    event = seed()
    receive(event)
    register_user(777)
    if action in {"confirm-critical", "reject-critical", "acknowledge-version"}:
        assert decision(event, "accept")[0] == 200
        if action == "acknowledge-version":
            receive(published(event))
        else:
            critical(event)
    before = fingerprint()
    if action is None:
        status, _ = call(
            event,
            user=777,
            suffix=f"?guideOsId={event['payload']['guide_os_id']}&userId=501",
        )
    else:
        status, _ = decision(
            event,
            action,
            user=777,
            version=2,
            guide_os_id=event["payload"]["guide_os_id"],
            userId=501,
        )
    assert status == 404
    assert fingerprint() == before
    pending = api_request(
        "GET",
        "/app/v1/guide-operator/assignments/pending?userId=501",
        headers=_auth_headers(777),
    )
    assert response_json(pending)["data"]["assignments"] == []


@pytest.mark.parametrize(
    "action",
    [
        None,
        "accept",
        "decline",
        "confirm-critical",
        "reject-critical",
        "acknowledge-version",
    ],
)
def test_missing_session_is_rejected(action):
    event = seed()
    receive(event)
    path = f"/app/v1/guide-operator/assignments/{event['payload']['assignment_id']}"
    if action:
        path += "/" + action
    before = fingerprint()
    response = api_request(
        "POST" if action else "GET",
        path,
        json={
            "decisionEventId": str(uuid4()),
            "versionNumber": 2,
            "guideOsId": event["payload"]["guide_os_id"],
        },
    )
    assert response.status == 401
    assert fingerprint() == before


def test_decline_and_replays_use_existing_decision_identity(monkeypatch):
    event = seed()
    receive(event)
    event_id = str(uuid4())
    status, first = decision(event, "decline", event_id=event_id)
    assert status == 200 and first["data"]["status"] == "declined"
    monkeypatch.setattr(domain, "_utc_now", lambda: "2026-11-09T23:00:00+00:00")
    before = fingerprint()
    for token in (event_id, str(uuid4())):
        status, replay = decision(event, "decline", event_id=token)
        assert status == 200 and replay["data"]["replayed"]
        assert replay["data"]["decisionEventId"] == event_id
    assert fingerprint() == before
    assert not rows(event["payload"]["assignment_id"])
    assert call(event)[0] == 200


def test_active_pending_rejected_and_latest_versions_with_public_actions(monkeypatch):
    event = seed()
    receive(event)
    assert decision(event, "accept")[0] == 200
    receive(published(event))
    before_dates = [r["calendar_date"] for r in rows(event["payload"]["assignment_id"])]
    critical(event, number=3, previous=2)
    status, detail = call(event)
    data = detail["data"]
    assert status == 200 and data["activeVersion"]["versionNumber"] == 2
    assert data["pendingCriticalVersion"]["versionNumber"] == 3
    assert data["workingPackage"]["days"][-1]["date"] == "2026-11-12"
    assert (
        data["pendingCriticalVersion"]["workingPackage"]["days"][-1]["date"]
        == "2026-11-13"
    )
    assert decision(event, "acknowledge-version", version=1)[0] == 409
    ack_id = str(uuid4())
    assert decision(event, "acknowledge-version", version=2, event_id=ack_id)[0] == 200
    assert (
        decision(event, "acknowledge-version", version=2)[1]["data"]["decisionEventId"]
        == ack_id
    )
    assert decision(event, "acknowledge-version", version=3)[0] == 409
    reject_id = str(uuid4())
    assert decision(event, "reject-critical", version=3, event_id=reject_id)[0] == 200
    assert [
        r["calendar_date"] for r in rows(event["payload"]["assignment_id"])
    ] == before_dates
    monkeypatch.setattr(domain, "_utc_now", lambda: "2026-11-09T10:00:00+00:00")
    assert decision(event, "reject-critical", version=3, event_id=reject_id)[1]["data"][
        "replayed"
    ]
    assert (
        decision(event, "reject-critical", version=3)[1]["data"]["decisionEventId"]
        == reject_id
    )
    assert decision(event, "confirm-critical", version=3)[0] == 409
    critical(event, number=4, previous=2)
    # Replay an old rejection must report the current pending pointer, without clearing it.
    assert (
        decision(event, "reject-critical", version=3, event_id=reject_id)[1]["data"][
            "pendingCriticalVersionNumber"
        ]
        == 4
    )
    assert decision(event, "confirm-critical", version=3)[0] == 409
    status, confirmed = decision(event, "confirm-critical", version=4)
    assert status == 200 and confirmed["data"]["activeVersionNumber"] == 4
    assert confirmed["data"]["projectionTourId"] is None
    assert [r["calendar_date"] for r in rows(event["payload"]["assignment_id"])] == [
        "2026-11-10",
        "2026-11-13",
    ]
    detail = call(event)[1]["data"]
    assert [v["versionNumber"] for v in detail["versions"]] == [1, 2, 3, 4]
    assert detail["pendingCriticalVersion"] is None


def test_same_tour_roles_overlap_and_cancel_does_not_restore_or_hide_peer():
    event = seed()
    connection = {
        "company_id": event["payload"]["company_id"],
        "connection_id": event["payload"]["guide_connection_id"],
    }
    peer = seed(
        connection=connection,
        tour=event["payload"]["working_package"]["tour"]["id"],
        role="local_guide",
    )
    for value in (event, peer):
        receive(value)
        assert decision(value, "accept")[0] == 200
    decide(event, "cancel")
    before = fingerprint()
    status, replay = decision(event, "accept")
    assert (
        status == 200
        and replay["data"]["replayed"]
        and replay["data"]["status"] == "cancelled"
    )
    assert fingerprint() == before
    assert not rows(event["payload"]["assignment_id"])
    assert len(rows(peer["payload"]["assignment_id"])) == 2


def test_unrelated_occupancy_conflicts_are_atomic_for_accept_and_confirm():
    event = seed()
    receive(event)
    save_tour(501, "Personal", "City", "2026-11-10", "reserved")
    domain.ensure_db_ready()  # Existing initialization normalizes NULL personal title.
    before = fingerprint()
    assert decision(event, "accept")[0] == 409
    assert fingerprint() == before
    with get_db_connection() as conn:
        conn.execute("DELETE FROM tours WHERE source!='guide_operator'")
        conn.commit()
    assert decision(event, "accept")[0] == 200
    critical(event)
    save_tour(501, "Personal", "City", "2026-11-13", "confirmed")
    domain.ensure_db_ready()
    before = fingerprint()
    status, body = decision(event, "confirm-critical", version=2)
    assert status == 409 and body["error"]["details"]["dates"] == ["2026-11-13"]
    assert fingerprint() == before
    assert (
        state(event["payload"]["assignment_id"])["pending_critical_version_number"] == 2
    )
    assert call(event)[1]["data"]["pendingCriticalVersion"]["conflictDates"] == [
        "2026-11-13"
    ]


@pytest.mark.parametrize(
    "fault",
    [
        "gap",
        "event_reuse",
        "ack_reuse",
        "critical_reuse",
        "stale_version",
        "bool_version",
    ],
)
def test_unsafe_requests_do_not_write(fault):
    event = seed()
    receive(event)
    if fault == "event_reuse":
        before = fingerprint()
        assert decision(event, "accept", event_id=event["event_id"])[0] == 409
    else:
        assert decision(event, "accept")[0] == 200
        receive(published(event))
        if fault == "ack_reuse":
            before = fingerprint()
            assert (
                decision(
                    event, "acknowledge-version", version=2, event_id=event["event_id"]
                )[0]
                == 409
            )
        else:
            critical(event, number=3, previous=2)
            if fault == "gap":
                run_write_with_retry(
                    lambda c: c.execute(
                        "DELETE FROM guide_operator_assignment_versions WHERE assignment_id=? AND version_number=2",
                        (event["payload"]["assignment_id"],),
                    )
                )
            before = fingerprint()
            status, _ = decision(
                event,
                "confirm-critical",
                version=True
                if fault == "bool_version"
                else 4
                if fault == "stale_version"
                else 3,
                event_id=event["event_id"] if fault == "critical_reuse" else None,
            )
            assert status in (400, 409)
    assert fingerprint() == before


@pytest.mark.parametrize("action", ["confirm-critical", "reject-critical"])
def test_session_decision_cancel_races_are_terminal(action):
    event = seed()
    receive(event)
    assert decision(event, "accept")[0] == 200
    critical(event)
    barrier = Barrier(2)

    def run(which):
        barrier.wait()
        if which == "cancel":
            try:
                return decide(event, "cancel", version=1)
            except (
                domain.AssignmentConflictError,
                domain.AssignmentNotActionableError,
            ):
                return None
        return decision(event, which, version=2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, (action, "cancel")))
    identity = event["payload"]["assignment_id"]
    current = state(identity)
    assert current["pending_critical_version_number"] is None
    if current["status"] == "cancelled":
        assert not rows(identity)
    else:
        assert action == "confirm-critical" and current["active_version_number"] == 2
        assert len(rows(identity)) == 2


def test_concurrent_identical_session_acceptance_and_ack():
    event = seed()
    receive(event)
    event_id = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: decision(event, "accept", event_id=event_id), (0, 1))
        )
    assert [r[0] for r in results] == [200, 200]
    assert sorted(r[1]["data"]["replayed"] for r in results) == [False, True]
    receive(published(event))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: decision(event, "acknowledge-version", version=2), (0, 1)
            )
        )
    assert [r[0] for r in results] == [200, 200]
    assert len(rows(event["payload"]["assignment_id"])) == 2


def test_legacy_pending_v2_transition_uses_sparse_detail_and_public_decision():
    legacy, event = legacy_fixture()
    critical(event)
    save_tour(501, "Personal", "City", "2026-11-11", "confirmed")
    domain.ensure_db_ready()
    status, detail = call(event)
    assert status == 200
    assert detail["data"]["assignment"]["projectionTourId"] is not None
    assert detail["data"]["pendingCriticalVersion"]["conflictDates"] == []
    assert decision(event, "confirm-critical", version=2)[0] == 200
    assert state(legacy.assignment_id)["projection_mode"] == "explicit_days"


def test_session_payloads_validate_with_actual_operator_frozen_contract():
    event = seed()
    receive(event)
    assert decision(event, "accept")[0] == 200
    receive(published(event))
    assert decision(event, "acknowledge-version", version=2)[0] == 200
    critical(event, number=3, previous=2)
    assert decision(event, "reject-critical", version=3)[0] == 200
    critical(event, number=4, previous=2)
    assert decision(event, "confirm-critical", version=4)[0] == 200
    with get_db_connection() as conn:
        envelopes = [
            {
                "event_id": r["event_id"],
                "event_type": r["event_type"],
                "occurred_at": r["created_at"],
                "payload": json.loads(r["payload_json"]),
            }
            for r in conn.execute(
                "SELECT * FROM guide_operator_outbox WHERE aggregate_type='guide_assignment' AND aggregate_id=? ORDER BY rowid",
                (event["payload"]["assignment_id"],),
            )
        ]
    root = Path(__file__).resolve().parents[2] / "guide operator"
    runtime = root / ".venv/bin/python"
    if not runtime.exists():
        pytest.skip(
            "Guide Operator test runtime unavailable: frozen validators unverified"
        )
    code = """import json, os, sys
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
from services.inbound_events import FrozenEventEnvelope, AssignmentDecisionPayload, CriticalVersionDecidedPayload, VersionAcknowledgedPayload, VersionAppliedAckPayload, VersionReceivedAckPayload
models = {"assignment.decision.v1": AssignmentDecisionPayload, "assignment.critical_version.decided.v1": CriticalVersionDecidedPayload, "assignment.version.acknowledged.v1": VersionAcknowledgedPayload, "assignment.version.applied.ack.v1": VersionAppliedAckPayload, "assignment.version.received.ack.v1": VersionReceivedAckPayload}
items = json.load(sys.stdin)
for item in items:
    envelope = FrozenEventEnvelope.model_validate(item)
    models[envelope.event_type].model_validate(envelope.payload)
print(len(items))
"""
    result = subprocess.run(
        [str(runtime), "-c", code],
        input=json.dumps(envelopes),
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert int(result.stdout) == len(envelopes) == 7


@pytest.mark.parametrize(
    "action", ["accept", "confirm-critical", "acknowledge-version"]
)
def test_public_operation_failure_rolls_back_all_domain_writes(monkeypatch, action):
    event = seed()
    receive(event)
    version = None
    if action != "accept":
        assert decision(event, "accept")[0] == 200
        if action == "confirm-critical":
            critical(event)
        else:
            receive(published(event))
        version = 2
    hook = {
        "accept": "_ACCEPT_FAILURE_HOOK",
        "confirm-critical": "_CRITICAL_VERSION_DECISION_FAILURE_HOOK",
        "acknowledge-version": "_VERSION_ACK_FAILURE_HOOK",
    }[action]

    def fail():
        raise RuntimeError("injected rollback")

    monkeypatch.setattr(domain, hook, fail)
    before = fingerprint()
    path = f"/app/v1/guide-operator/assignments/{event['payload']['assignment_id']}/{action}"
    body = {"decisionEventId": str(uuid4())}
    if version:
        body["versionNumber"] = version
    response = api_request("POST", path, headers=_auth_headers(501), json=body)
    assert response.status == 500
    assert fingerprint() == before


@pytest.mark.parametrize(
    "action", ["accept", "confirm-critical", "acknowledge-version"]
)
def test_explicit_actions_require_wire_compatible_event_identity(action):
    event = seed()
    receive(event)
    if action != "accept":
        assert decision(event, "accept")[0] == 200
        if action == "confirm-critical":
            critical(event)
        else:
            receive(published(event))
    before = fingerprint()
    status, _ = decision(
        event,
        action,
        version=2 if action != "accept" else None,
        event_id="not-a-wire-uuid",
    )
    assert status == 400
    assert fingerprint() == before
