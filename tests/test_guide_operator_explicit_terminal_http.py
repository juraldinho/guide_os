"""Frozen v1 terminal intake for explicit-day assignments, without v2 receive activation."""

import asyncio
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from aiohttp.test_utils import TestClient, TestServer

from database.db import get_db_connection, run_write_with_retry
from database.queries import (
    claim_guide_operator_guide_notification_for_delivery,
    get_guide_os_id,
    is_guide_operator_guide_notification_current,
    register_user,
)
from services import guide_operator_assignment_service as domain
from services.guide_operator_integration_settings import (
    GuideOperatorIntegrationSettings,
)
from services.guide_operator_service_auth_settings import (
    GuideOperatorServiceAuthSettings,
)
from services.guide_operator_service_jwt import (
    SCOPE_CANCELLATIONS_WRITE,
    SCOPE_OFFERS_WRITE,
)
from tests.test_guide_operator_assignment_v2_contract import NOW
from tests.test_guide_operator_assignment_v2_http import post, request
from tests.test_guide_operator_assignment_v2_intake import (
    fingerprint,
    legacy_fixture,
    receive,
    seed,
)
from tests.test_guide_operator_daily_projections import rows, state
from tests.test_guide_operator_daily_repair import extra
from tests.test_guide_operator_integration_http import (
    _pem_pair,
    _reset_db_and_auth,
    auth_settings,
    clock,
    keys,
    mint_token,
    outbound_private,
)
from tests.test_miniapp_guide_operator_explicit_lifecycle import critical, decision
from web_api.guide_operator_integration import create_guide_operator_integration_app

__all__ = ["_reset_db_and_auth", "auth_settings", "clock", "keys", "outbound_private"]
OFF = GuideOperatorIntegrationSettings(enabled=True)


def terminal(offer, kind="cancelled", *, version=1):
    payload = {
        "assignment_id": offer["payload"]["assignment_id"],
        "guide_os_id": offer["payload"]["guide_os_id"],
    }
    if kind == "cancelled":
        payload.update(version_number=version, cancelled_at=NOW)
    return {
        "event_id": str(uuid4()),
        "event_type": f"assignment.{kind}.v1",
        "occurred_at": NOW,
        "payload": payload,
    }


def target(event):
    kind = event["event_type"].split(".")[1]
    return f"/integration/v1/assignments/{event['payload']['assignment_id']}/{kind}"


def scope(event):
    return (
        SCOPE_CANCELLATIONS_WRITE
        if event["event_type"] == "assignment.cancelled.v1"
        else SCOPE_OFFERS_WRITE
    )


def send(auth, clock, keys, event, **kwargs):
    token = kwargs.pop("token", mint_token(keys[0], scope=scope(event)))
    return post(
        auth,
        clock,
        event,
        target=kwargs.pop("target", target(event)),
        config=OFF,
        token=token,
        **kwargs,
    )


def accepted():
    event = seed()
    receive(event)
    assert decision(event, "accept")[0] == 200
    return event


def evidence(identity):
    with get_db_connection() as conn:
        tables = (
            "guide_operator_cancellation_inbox",
            "guide_operator_assignment_lifecycle_inbox",
            "guide_operator_daily_operation_inbox",
            "guide_operator_assignment_versions",
            "guide_operator_assignment_decisions",
            "guide_operator_critical_version_decisions",
            "guide_operator_outbox",
            "guide_operator_guide_notifications",
        )
        return {
            t: [
                dict(r)
                for r in conn.execute(
                    f"SELECT * FROM {t} WHERE {'aggregate_id' if t == 'guide_operator_outbox' else 'assignment_id'}=? ORDER BY rowid",
                    (identity,),
                )
            ]
            for t in tables
        }


def test_sparse_cancel_pending_keeps_peer_history_and_notifications(
    auth_settings, clock, keys
):
    event = accepted()
    connection = {
        "company_id": event["payload"]["company_id"],
        "connection_id": event["payload"]["guide_connection_id"],
    }
    peer = seed(
        connection=connection,
        tour=event["payload"]["working_package"]["tour"]["id"],
        role="local_guide",
    )
    receive(peer)
    assert decision(peer, "accept")[0] == 200
    critical(event)
    identity = event["payload"]["assignment_id"]
    old = evidence(identity)
    peer_before = rows(peer["payload"]["assignment_id"])
    cancel = terminal(event)
    status, body = send(auth_settings, clock, keys, cancel)
    assert status == 200 and body["data"]["status"] == "applied"
    assert state(identity)["status"] == "cancelled"
    assert state(identity)["pending_critical_version_number"] is None
    assert state(identity)["active_version_number"] == 1
    assert not rows(identity) and rows(peer["payload"]["assignment_id"]) == peer_before
    new = evidence(identity)
    assert (
        new["guide_operator_assignment_versions"]
        == old["guide_operator_assignment_versions"]
    )
    assert (
        new["guide_operator_assignment_decisions"]
        == old["guide_operator_assignment_decisions"]
    )
    notifications = new["guide_operator_guide_notifications"]
    cancelled = [
        r for r in notifications if r["notification_type"] == "assignment_cancellation"
    ]
    assert len(cancelled) == 1
    for row in notifications:
        assert is_guide_operator_guide_notification_current(
            notification_id=row["id"], now_iso=NOW
        ) is (row["notification_type"] == "assignment_cancellation")
    assert (
        claim_guide_operator_guide_notification_for_delivery(
            now_iso=NOW,
            lease_until_iso="2026-11-08T00:00:00+00:00",
            permanent_error_codes=(),
            notification_id=cancelled[0]["id"],
        )
        is None
    )
    command = domain.AssignmentCancellationIntake(
        event_id=cancel["event_id"], **cancel["payload"]
    )
    assert new["guide_operator_cancellation_inbox"][0][
        "payload_hash"
    ] == domain._canonical_hash(domain._normalize_cancellation(command))
    assert (
        len(
            [
                r
                for r in new["guide_operator_outbox"]
                if r["event_type"] == "assignment.cancellation.ack.v1"
            ]
        )
        == 1
    )
    before = fingerprint()
    assert send(auth_settings, clock, keys, cancel)[1]["data"]["status"] == "replayed"
    assert fingerprint() == before and evidence(identity) == new
    assert decision(event, "confirm-critical", version=2)[0] == 409


@pytest.mark.parametrize("kind", ["withdrawn", "expired"])
def test_offered_terminal_has_no_occupancy_ack_or_new_notification(
    auth_settings, clock, keys, kind
):
    event = seed()
    receive(event)
    identity = event["payload"]["assignment_id"]
    before = evidence(identity)
    value = terminal(event, kind)
    status, body = send(auth_settings, clock, keys, value)
    assert status == 200 and body["data"]["status"] == "applied"
    assert state(identity)["status"] == kind and not rows(identity)
    after = evidence(identity)
    assert after["guide_operator_outbox"] == before["guide_operator_outbox"]
    assert (
        after["guide_operator_guide_notifications"]
        == before["guide_operator_guide_notifications"]
    )
    assert (
        after["guide_operator_assignment_versions"]
        == before["guide_operator_assignment_versions"]
    )
    assert len(after["guide_operator_assignment_lifecycle_inbox"]) == 1
    note = after["guide_operator_guide_notifications"][0]
    assert (
        is_guide_operator_guide_notification_current(
            notification_id=note["id"], now_iso=NOW
        )
        is False
    )
    before_state = fingerprint()
    assert send(auth_settings, clock, keys, value)[1]["data"]["replayed"]
    assert fingerprint() == before_state
    assert decision(event, "accept")[0] == 409
    assert decision(event, "decline")[0] == 409


@pytest.mark.parametrize("kind", ["cancelled", "withdrawn", "expired"])
@pytest.mark.parametrize(
    "fault",
    [
        "missing_auth",
        "wrong_scope",
        "bad_key",
        "auth_off",
        "jti_reuse",
        "foreign_guide",
        "path",
        "invalid_transition",
        "event_type",
        "conflicting_reuse",
        "reserved_event",
    ],
)
def test_bad_terminal_requests_do_not_change_domain(
    auth_settings, clock, keys, kind, fault
):
    event = accepted() if kind == "cancelled" else seed()
    if kind != "cancelled":
        receive(event)
    value = terminal(event, kind)
    kwargs = {}
    auth = auth_settings
    expected = (400, 404, 409)
    if fault == "missing_auth":
        kwargs["token"] = None
        expected = (401,)
    elif fault == "wrong_scope":
        kwargs["token"] = mint_token(
            keys[0],
            scope=SCOPE_OFFERS_WRITE
            if kind == "cancelled"
            else SCOPE_CANCELLATIONS_WRITE,
        )
        expected = (401,)
    elif fault == "bad_key":
        kwargs["token"] = mint_token(_pem_pair()[0], scope=scope(value))
        expected = (401,)
    elif fault == "auth_off":
        auth = GuideOperatorServiceAuthSettings.disabled()
        expected = (503,)
    elif fault == "jti_reuse":
        token = mint_token(keys[0], scope=scope(value))
        assert send(auth, clock, keys, value, token=token, raw="{}")[0] == 400
        kwargs["token"] = token
        expected = (401,)
    elif fault == "foreign_guide":
        register_user(777)
        value["payload"]["guide_os_id"] = get_guide_os_id(777)
    elif fault == "path":
        kwargs["target"] = target(value).replace(
            value["payload"]["assignment_id"], str(uuid4())
        )
    elif fault == "invalid_transition":
        if kind == "cancelled":
            value["payload"]["version_number"] = 2
        else:
            assert decision(event, "accept")[0] == 200
    elif fault == "event_type":
        kwargs["target"] = target(value)
        kwargs["token"] = mint_token(keys[0], scope=scope(value))
        value["event_type"] = "assignment.offered.v2"
    elif fault == "conflicting_reuse":
        assert send(auth, clock, keys, value)[0] == 200
        value["occurred_at"] = "2026-11-08T10:00:00+00:00"
        if kind == "cancelled":
            value["payload"]["cancelled_at"] = value["occurred_at"]
    elif fault == "reserved_event":
        value["event_id"] = event["event_id"]
    before = fingerprint()
    status, _ = send(auth, clock, keys, value, **kwargs)
    assert status in expected
    assert fingerprint() == before


@pytest.mark.parametrize("kind", ["cancelled", "withdrawn", "expired"])
def test_stored_company_binding_mismatch_is_refused(auth_settings, clock, keys, kind):
    event = accepted() if kind == "cancelled" else seed()
    if kind != "cancelled":
        receive(event)
    foreign = seed()  # Another company connection for this guide.
    run_write_with_retry(
        lambda c: c.execute(
            "UPDATE guide_operator_assignments SET guide_connection_id=? WHERE assignment_id=?",
            (
                foreign["payload"]["guide_connection_id"],
                event["payload"]["assignment_id"],
            ),
        )
    )
    before = fingerprint()
    assert send(auth_settings, clock, keys, terminal(event, kind))[0] == 400
    assert fingerprint() == before


@pytest.mark.parametrize("kind", ["cancelled", "withdrawn", "expired"])
def test_disconnect_and_disabled_intake_do_not_strand_terminal_events(
    auth_settings, clock, keys, kind
):
    event = accepted() if kind == "cancelled" else seed()
    if kind != "cancelled":
        receive(event)
    run_write_with_retry(
        lambda c: c.execute(
            "UPDATE guide_operator_connections SET status='disconnected' WHERE connection_id=?",
            (event["payload"]["guide_connection_id"],),
        )
    )
    assert send(auth_settings, clock, keys, terminal(event, kind))[0] == 200


@pytest.mark.parametrize("kind", ["cancelled", "withdrawn", "expired"])
def test_concurrent_replay_uses_transaction_result(auth_settings, clock, keys, kind):
    event = accepted() if kind == "cancelled" else seed()
    if kind != "cancelled":
        receive(event)
    value = terminal(event, kind)

    async def run():
        app = create_guide_operator_integration_app(
            auth_settings=auth_settings, clock=clock, integration_settings=OFF
        )
        async with TestClient(TestServer(app)) as client:
            tasks = [
                request(
                    client,
                    target(value),
                    value,
                    token=mint_token(keys[0], scope=scope(value)),
                )
                for _ in range(2)
            ]
            return await asyncio.gather(*tasks)

    responses = asyncio.run(run())
    assert [r[0] for r in responses] == [200, 200]
    assert sorted(r[1]["data"]["replayed"] for r in responses) == [False, True]


@pytest.mark.parametrize("kind", ["withdrawn", "expired"])
def test_accept_vs_offered_terminal_race(auth_settings, clock, keys, kind):
    event = seed()
    receive(event)
    barrier = Barrier(2)

    def run(action):
        barrier.wait(timeout=10)
        return (
            decision(event, "accept")
            if action == "accept"
            else send(auth_settings, clock, keys, terminal(event, kind))
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(run, ("accept", "terminal")))
    assert sorted(r[0] for r in responses) == [200, 409]
    identity = event["payload"]["assignment_id"]
    if state(identity)["status"] == "accepted":
        assert len(rows(identity)) == 2
    else:
        assert state(identity)["status"] == kind and not rows(identity)


def test_confirm_vs_cancel_race(auth_settings, clock, keys):
    event = accepted()
    critical(event)
    barrier = Barrier(2)

    def run(action):
        barrier.wait(timeout=10)
        return (
            decision(event, "confirm-critical", version=2)
            if action == "confirm"
            else send(auth_settings, clock, keys, terminal(event))
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(run, ("confirm", "cancel")))
    assert sorted(r[0] for r in responses) == [200, 409]
    identity = event["payload"]["assignment_id"]
    current = state(identity)
    if current["status"] == "cancelled":
        assert not rows(identity) and current["active_version_number"] == 1
    else:
        assert (
            current["status"] == "accepted"
            and current["active_version_number"] == 2
            and len(rows(identity)) == 2
        )
    assert current["pending_critical_version_number"] is None


@pytest.mark.parametrize("kind", ["cancelled", "withdrawn", "expired"])
def test_lifecycle_failure_rolls_back_everything(
    auth_settings, clock, keys, monkeypatch, kind
):
    event = accepted() if kind == "cancelled" else seed()
    if kind != "cancelled":
        receive(event)
    if kind == "cancelled":

        def fail():
            raise RuntimeError("cancel rollback")

        monkeypatch.setattr(domain, "_CANCEL_FAILURE_HOOK", fail)
    else:
        run_write_with_retry(
            lambda c: c.execute(
                "CREATE TRIGGER terminal_rollback BEFORE UPDATE OF status ON guide_operator_assignments WHEN NEW.status IN ('withdrawn','expired') BEGIN SELECT RAISE(ABORT,'fixture rollback'); END"
            )
        )
    before = fingerprint()

    async def run():
        app = create_guide_operator_integration_app(
            auth_settings=auth_settings, clock=clock, integration_settings=OFF
        )
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                target(terminal_value),
                json=terminal_value,
                headers={
                    "Authorization": "Bearer "
                    + mint_token(keys[0], scope=scope(terminal_value))
                },
            )
            assert response.status == 500

    terminal_value = terminal(event, kind)
    asyncio.run(run())
    assert fingerprint() == before


@pytest.mark.parametrize(
    "income,payment", [(0, "unpaid"), (77, "paid"), (None, "paid")]
)
def test_financially_populated_own_row_is_preserved_with_refusal(
    auth_settings, clock, keys, income, payment
):
    event = accepted()
    replace_financial_day(event, income=income, payment=payment)
    before = fingerprint()
    assert send(auth_settings, clock, keys, terminal(event))[0] == 400
    assert fingerprint() == before


def test_cancel_after_legacy_to_explicit_transition(auth_settings, clock, keys):
    _, event = legacy_fixture()
    critical(event)
    assert decision(event, "confirm-critical", version=2)[0] == 200
    assert send(auth_settings, clock, keys, terminal(event, version=2))[0] == 200
    assert not rows(event["payload"]["assignment_id"])


def replace_financial_day(event, *, income, payment):
    identity = event["payload"]["assignment_id"]
    row = rows(identity)[0]

    def remove(c):
        c.execute(
            "DELETE FROM guide_operator_daily_projections WHERE projection_tour_id=?",
            (row["projection_tour_id"],),
        )
        domain._release_daily_row(c, row["projection_tour_id"], 501)

    run_write_with_retry(remove)
    f = (
        event["payload"]["guide_os_id"],
        identity,
        event["payload"]["working_package"],
        {"company_id": event["payload"]["company_id"]},
    )
    extra(
        f,
        key=row["tour_day_id"],
        date=row["calendar_date"],
        income=income,
        payment=payment,
    )


def test_cancel_preserves_other_role_financial_values(auth_settings, clock, keys):
    event = accepted()
    peer = seed(
        connection={
            "company_id": event["payload"]["company_id"],
            "connection_id": event["payload"]["guide_connection_id"],
        },
        tour=event["payload"]["working_package"]["tour"]["id"],
        role="other",
    )
    receive(peer)
    assert decision(peer, "accept")[0] == 200
    replace_financial_day(peer, income=77, payment="paid")
    before = rows(peer["payload"]["assignment_id"])
    assert send(auth_settings, clock, keys, terminal(event))[0] == 200
    assert rows(peer["payload"]["assignment_id"]) == before


@pytest.mark.parametrize("fault", ["missing_link", "link_version", "stray"])
def test_cancel_refuses_unsafe_projection_state(auth_settings, clock, keys, fault):
    event = accepted()
    identity = event["payload"]["assignment_id"]
    if fault == "missing_link":
        run_write_with_retry(
            lambda c: c.execute(
                "DELETE FROM guide_operator_daily_projections WHERE tour_day_id=?",
                (event["payload"]["working_package"]["days"][0]["tour_day_id"],),
            )
        )
    elif fault == "link_version":
        run_write_with_retry(
            lambda c: c.execute(
                "UPDATE guide_operator_daily_projections SET active_version_number=2 WHERE assignment_id=?",
                (identity,),
            )
        )
    else:
        extra(
            (
                event["payload"]["guide_os_id"],
                identity,
                event["payload"]["working_package"],
                {"company_id": event["payload"]["company_id"]},
            ),
            linked=False,
        )
    before = fingerprint()
    assert send(auth_settings, clock, keys, terminal(event))[0] == 400
    assert fingerprint() == before


@pytest.mark.parametrize("kind", ["withdrawn", "expired"])
@pytest.mark.parametrize("fault", ["stray", "active", "pending"])
def test_offered_terminal_rejects_malformed_state(
    auth_settings, clock, keys, kind, fault
):
    event = seed()
    receive(event)
    identity = event["payload"]["assignment_id"]
    if fault == "stray":
        extra(
            (
                event["payload"]["guide_os_id"],
                identity,
                event["payload"]["working_package"],
                {"company_id": event["payload"]["company_id"]},
            ),
            linked=False,
        )
    elif fault == "active":
        run_write_with_retry(
            lambda c: c.execute(
                "UPDATE guide_operator_assignments SET active_version_number=2 WHERE assignment_id=?",
                (identity,),
            )
        )
    else:
        run_write_with_retry(
            lambda c: c.execute(
                "UPDATE guide_operator_assignments SET pending_critical_version_number=2 WHERE assignment_id=?",
                (identity,),
            )
        )
    before = fingerprint()
    assert send(auth_settings, clock, keys, terminal(event, kind))[0] == 400
    assert fingerprint() == before


def test_cancellation_ack_validates_against_operator_contract(
    auth_settings, clock, keys
):
    event = accepted()
    value = terminal(event)
    assert send(auth_settings, clock, keys, value)[0] == 200
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM guide_operator_outbox WHERE event_id=?", (value["event_id"],)
        ).fetchone()
        envelope = {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "occurred_at": row["created_at"],
            "payload": json.loads(row["payload_json"]),
        }
    root = Path(__file__).resolve().parents[2] / "guide operator"
    runtime = root / ".venv/bin/python"
    if not runtime.exists():
        pytest.skip("Operator test runtime absent: ACK contract unverified")
    code = """import json, os, sys
os.environ["DATABASE_URL"]="sqlite+aiosqlite:///:memory:"
from services.inbound_events import FrozenEventEnvelope, CancellationAckPayload
event=FrozenEventEnvelope.model_validate(json.load(sys.stdin))
assert event.event_type == "assignment.cancellation.ack.v1"
CancellationAckPayload.model_validate(event.payload)
print("validated")
"""
    result = subprocess.run(
        [str(runtime), "-c", code],
        input=json.dumps(envelope),
        cwd=root,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "validated"


@pytest.mark.parametrize("kind", ["cancelled", "withdrawn", "expired"])
def test_explicit_terminal_rejects_naive_evidence_time(
    auth_settings, clock, keys, kind
):
    event = accepted() if kind == "cancelled" else seed()
    if kind != "cancelled":
        receive(event)
    value = terminal(event, kind)
    value["occurred_at"] = "2026-11-08T10:00:00"
    if kind == "cancelled":
        value["payload"]["cancelled_at"] = value["occurred_at"]
    before = fingerprint()
    assert send(auth_settings, clock, keys, value)[0] == 400
    assert fingerprint() == before
