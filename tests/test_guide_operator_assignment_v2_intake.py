"""Isolated v2 domain intake/decisions. HTTP/service-auth wiring is a later gate."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from database.db import get_db_connection, run_write_with_retry
from database.queries import get_guide_os_id, register_user
from services import guide_operator_assignment_service as domain
from services.guide_operator_assignment_v2_service import (
    AssignmentV2ReceiveDisabled,
    receive_assignment_event_v2,
)
from services.guide_operator_connection_service import (
    ensure_confirmed_connection_for_tests,
)
from tests.test_guide_operator_assignment_v2_contract import NOW, offered, published
from tests.test_guide_operator_assignments import _offer
from tests.test_guide_operator_daily_projections import rows, state


def seed(*, connection=None, **kwargs):
    register_user(501)
    guide = get_guide_os_id(501)
    connection = connection or ensure_confirmed_connection_for_tests(guide)
    return offered(
        guide=guide,
        company=connection["company_id"],
        connection=connection["connection_id"],
        **kwargs,
    )


def receive(event, **kwargs):
    return receive_assignment_event_v2(
        event,
        assignment_id=event["payload"]["assignment_id"],
        receive_enabled=True,
        **kwargs,
    )


def decide(event, action="accept", version=1, event_id=None):
    return domain._apply_explicit_projection_decision_local(
        event["payload"]["guide_os_id"],
        event["payload"]["assignment_id"],
        action=action,
        version_number=version,
        event_id=event_id or str(uuid4()),
        occurred_at=NOW,
    )


def count(table):
    with get_db_connection() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def fingerprint():
    with get_db_connection() as conn:
        tables = (
            "guide_operator_assignments",
            "guide_operator_assignment_versions",
            "guide_operator_offer_inbox",
            "guide_operator_version_inbox",
            "guide_operator_outbox",
            "guide_operator_guide_notifications",
            "guide_operator_daily_projections",
            "tours",
        )
        return {
            t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
            for t in tables
        }


def test_disabled_before_any_write():
    event = seed()
    before = fingerprint()
    for enabled in (False, None, 1, "true"):
        with pytest.raises(AssignmentV2ReceiveDisabled):
            receive_assignment_event_v2(
                event,
                assignment_id=event["payload"]["assignment_id"],
                receive_enabled=enabled,
            )
    assert fingerprint() == before


def test_sparse_roles_independent_accept_decline_cancel_and_acks():
    first = seed()
    connection = {
        "company_id": first["payload"]["company_id"],
        "connection_id": first["payload"]["guide_connection_id"],
    }
    second = seed(
        connection=connection,
        tour=first["payload"]["working_package"]["tour"]["id"],
        role="local_guide",
    )
    third = seed(
        connection=connection,
        tour=first["payload"]["working_package"]["tour"]["id"],
        role="other",
    )
    for event in (first, second, third):
        receive(event)
    assert not rows(first["payload"]["assignment_id"])
    decide(first)
    decide(second)
    decide(third, "decline")
    assert [r["calendar_date"] for r in rows(first["payload"]["assignment_id"])] == [
        "2026-11-10",
        "2026-11-12",
    ]
    assert not rows(third["payload"]["assignment_id"])
    decide(first, "cancel")
    assert len(rows(second["payload"]["assignment_id"])) == 2
    with get_db_connection() as conn:
        acks = [
            json.loads(r[0])
            for r in conn.execute(
                "SELECT payload_json FROM guide_operator_outbox WHERE event_type='assignment.decision.v1'"
            )
        ]
    assert len(acks) == 3
    assert all(
        a["projection_tour_id"] is None
        and set(a)
        == {
            "assignment_id",
            "guide_os_id",
            "version_number",
            "decision",
            "decided_at",
            "projection_tour_id",
        }
        for a in acks
    )


def test_ordinary_pending_rejection_history_and_latest_sequence():
    event = seed()
    receive(event)
    decide(event)
    identity = event["payload"]["assignment_id"]
    first_ids = [r["projection_tour_id"] for r in rows(identity)]
    ordinary = published(event)
    receive(ordinary)
    assert state(identity)["active_version_number"] == 2
    assert [r["projection_tour_id"] for r in rows(identity)] == first_ids
    critical = published(event, number=3, previous=2, severity="critical")
    critical["payload"]["working_package"]["days"][1]["date"] = "2026-11-13"
    critical["payload"]["working_package"]["assignment"]["end_date"] = "2026-11-13"
    receive(critical)
    assert state(identity)["active_version_number"] == 2
    assert [r["calendar_date"] for r in rows(identity)] == ["2026-11-10", "2026-11-12"]
    with pytest.raises(domain.AssignmentNotActionableError):
        receive(published(event, number=4, previous=2))
    decide(event, "reject_critical", 3)
    assert state(identity)["active_version_number"] == 2
    later = copy.deepcopy(critical)
    later["event_id"] = str(uuid4())
    later["payload"]["version_number"] = 4
    receive(later)
    decide(event, "confirm_critical", 4)
    assert [r["calendar_date"] for r in rows(identity)] == ["2026-11-10", "2026-11-13"]
    assert count("guide_operator_assignment_versions") == 4
    with get_db_connection() as conn:
        rejected = conn.execute(
            "SELECT working_package_json FROM guide_operator_assignment_versions WHERE assignment_id=? AND version_number=3",
            (identity,),
        ).fetchone()[0]
    assert json.loads(rejected) == critical["payload"]["working_package"]


@pytest.mark.parametrize(
    "case",
    [
        "days",
        "ids",
        "role",
        "route",
        "timezone",
        "times",
        "company",
        "tour",
        "guide",
        "gap",
        "active",
        "cancelled",
        "foreign_connection",
    ],
)
def test_invalid_changes_do_not_write(case):
    event = seed()
    receive(event)
    decide(event)
    update = published(event)
    p = update["payload"]
    package = p["working_package"]
    if case == "days":
        package["days"][1]["date"] = package["assignment"]["end_date"] = "2026-11-13"
    elif case == "ids":
        package["days"][0]["tour_day_id"] = str(uuid4())
    elif case == "role":
        package["assignment"]["role"] = "other"
    elif case == "route":
        package["days"][0]["city_or_route"] = "Bukhara"
    elif case == "timezone":
        package["tour"]["timezone"] = "UTC"
    elif case == "times":
        package["days"][0]["events"] = [
            {
                "start_time": "10:00",
                "end_time": "11:00",
                "event_type": "visit",
                "title": "Place",
                "place": None,
                "description": None,
                "important_instruction": None,
            }
        ]
    elif case == "company":
        package["company_id"] = str(uuid4())
    elif case == "tour":
        package["tour"]["id"] = str(uuid4())
    elif case == "guide":
        package["assignment"]["guide_os_id"] = p["guide_os_id"] = str(uuid4())
    elif case == "gap":
        p["version_number"] = 3
    elif case == "active":
        p["previous_active_version_number"] = 2
    elif case == "cancelled":
        decide(event, "cancel")
    else:
        run_write_with_retry(
            lambda c: c.execute(
                "UPDATE guide_operator_connections SET status='disconnected' WHERE connection_id=?",
                (event["payload"]["guide_connection_id"],),
            )
        )
    before = fingerprint()
    with pytest.raises(domain.GuideOperatorAssignmentError):
        receive(update)
    assert fingerprint() == before


def test_replay_conflicting_reuse_and_terminal_state():
    event = seed()
    receive(event)
    before = fingerprint()
    assert receive(event)["replayed"]
    assert fingerprint() == before
    changed = copy.deepcopy(event)
    changed["payload"]["company_name"] = "Changed"
    with pytest.raises(domain.AssignmentConflictError):
        receive(changed)
    decide(event)
    update = published(event)
    receive(update)
    before = fingerprint()
    assert receive(update)["replayed"]
    assert fingerprint() == before
    changed = copy.deepcopy(update)
    changed["payload"]["working_package"]["tour"]["title"] = "Reused"
    with pytest.raises(domain.AssignmentConflictError):
        receive(changed)
    decide(event, "cancel", 2)
    assert receive(update)["status"] == "cancelled"
    assert not rows(event["payload"]["assignment_id"])


@pytest.mark.parametrize("kind", ["offer", "ordinary", "critical"])
def test_intake_atomic_rollback(monkeypatch, kind):
    event = seed()
    if kind != "offer":
        receive(event)
        decide(event)
    target = event if kind == "offer" else published(event, severity=kind)
    hook = {
        "offer": "_OFFER_INTAKE_FAILURE_HOOK",
        "ordinary": "_ORDINARY_VERSION_FAILURE_HOOK",
        "critical": "_CRITICAL_VERSION_INTAKE_FAILURE_HOOK",
    }[kind]

    def fail():
        raise RuntimeError("injected")

    monkeypatch.setattr(domain, hook, fail)
    before = fingerprint()
    with pytest.raises(RuntimeError, match="injected"):
        receive(target)
    assert fingerprint() == before


def test_unrelated_tour_conflict_and_concurrent_replay():
    event = seed()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(receive, (event, copy.deepcopy(event))))
    assert sorted(r["replayed"] for r in results) == [False, True]
    decide(event)
    other = seed()
    receive(other)
    before = fingerprint()
    with pytest.raises(domain.CalendarConflictError):
        decide(other)
    assert fingerprint() == before


def legacy_fixture(*, known_tour=True):
    register_user(501)
    guide = get_guide_os_id(501)
    legacy = _offer(guide, start_date="2026-11-10", end_date="2026-11-12")
    tour = str(uuid4())
    if known_tour:
        legacy.working_package["tour"]["id"] = tour
    domain.receive_assignment_offer(legacy)
    domain.accept_assignment(
        guide, legacy.assignment_id, decision_event_id=str(uuid4()), decided_at=NOW
    )
    event = offered(
        guide=guide,
        company=legacy.company_id,
        connection=legacy.guide_connection_id,
        tour=tour,
    )
    event["payload"]["assignment_id"] = legacy.assignment_id
    event["payload"]["working_package"]["assignment"]["id"] = legacy.assignment_id
    return legacy, event


@pytest.mark.parametrize("decision", ["confirm_critical", "reject_critical"])
def test_legacy_to_v2_requires_critical_and_keeps_old_scope_until_confirm(decision):
    legacy, event = legacy_fixture()
    with pytest.raises(domain.AssignmentValidationError):
        receive(published(event))
    critical = published(event, severity="critical")
    receive(critical)
    assert state(legacy.assignment_id)["projection_mode"] == "legacy_range"
    decide(event, decision, 2)
    current = state(legacy.assignment_id)
    if decision == "reject_critical":
        assert (
            current["projection_mode"] == "legacy_range"
            and current["projection_tour_id"] is not None
        )
        assert not rows(legacy.assignment_id)
    else:
        assert (
            current["projection_mode"] == "explicit_days"
            and current["projection_tour_id"] is None
        )
        assert [r["calendar_date"] for r in rows(legacy.assignment_id)] == [
            "2026-11-10",
            "2026-11-12",
        ]


def test_legacy_missing_immutable_tour_identity_refuses_without_writes():
    _, event = legacy_fixture(known_tour=False)
    before = fingerprint()
    with pytest.raises(domain.AssignmentValidationError):
        receive(published(event, severity="critical"))
    assert fingerprint() == before


def test_decline_idempotency_conflicting_reuse_and_event_namespace():
    event = seed()
    receive(event)
    before = fingerprint()
    with pytest.raises(domain.AssignmentConflictError):
        decide(event, "accept", event_id=event["event_id"])
    assert fingerprint() == before
    decision_id = str(uuid4())
    decide(event, "decline", event_id=decision_id)
    before = fingerprint()
    assert decide(event, "decline", event_id=decision_id)["replayed"]
    with pytest.raises(domain.AssignmentConflictError):
        decide(event, "accept", event_id=decision_id)
    assert fingerprint() == before
    second = seed()
    second["event_id"] = decision_id
    with pytest.raises(domain.AssignmentConflictError):
        receive(second)


@pytest.mark.parametrize("action", ["confirm_critical", "reject_critical"])
def test_confirmation_and_cancellation_race(action):
    from threading import Barrier

    event = seed()
    receive(event)
    decide(event)
    critical = published(event, severity="critical")
    critical["payload"]["working_package"]["days"][1]["date"] = "2026-11-13"
    critical["payload"]["working_package"]["assignment"]["end_date"] = "2026-11-13"
    receive(critical)
    barrier = Barrier(2)

    def run(which):
        barrier.wait()
        try:
            return decide(event, which, 2 if which != "cancel" else 1)
        except (domain.AssignmentNotActionableError, domain.AssignmentConflictError):
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, (action, "cancel")))
    identity = event["payload"]["assignment_id"]
    current = state(identity)
    assert current["pending_critical_version_number"] is None
    if current["status"] == "cancelled":
        assert not rows(identity)
    else:
        assert action == "confirm_critical" and current["active_version_number"] == 2
        assert [r["calendar_date"] for r in rows(identity)] == [
            "2026-11-10",
            "2026-11-13",
        ]


@pytest.mark.parametrize(
    "fault",
    [
        "row_missing",
        "link_version",
        "malformed_active",
        "version_gap",
        "unknown_mode",
        "ordinary_unknown_title",
        "revision_only",
    ],
)
def test_unsafe_effective_state_or_unconfirmed_content_fails_closed(fault):
    event = seed()
    receive(event)
    decide(event)
    identity = event["payload"]["assignment_id"]
    target = published(event)
    if fault == "row_missing":
        run_write_with_retry(
            lambda c: c.execute(
                "DELETE FROM guide_operator_daily_projections WHERE tour_day_id=?",
                (event["payload"]["working_package"]["days"][1]["tour_day_id"],),
            )
        )
    elif fault == "link_version":
        run_write_with_retry(
            lambda c: c.execute(
                "UPDATE guide_operator_daily_projections SET active_version_number=2 WHERE assignment_id=?",
                (identity,),
            )
        )
    elif fault == "malformed_active":
        run_write_with_retry(
            lambda c: c.execute(
                "UPDATE guide_operator_assignment_versions SET working_package_json='[]' WHERE assignment_id=?",
                (identity,),
            )
        )
    elif fault == "version_gap":
        receive(target)
        run_write_with_retry(
            lambda c: c.execute(
                "DELETE FROM guide_operator_assignment_versions WHERE assignment_id=? AND version_number=1",
                (identity,),
            )
        )
        target = published(event, number=3, previous=2)
    elif fault == "unknown_mode":
        target["payload"]["working_package"]["schema_version"] = "unknown"
    elif fault == "ordinary_unknown_title":
        target["payload"]["working_package"]["tour"]["title"] = (
            "Unknown meaningful change"
        )
    else:
        target["payload"]["working_package"] = copy.deepcopy(
            event["payload"]["working_package"]
        )
        target["payload"]["working_package"]["source_tour_revision"] = 2
    before = fingerprint()
    with pytest.raises(domain.AssignmentValidationError):
        receive(target)
    assert fingerprint() == before


@pytest.mark.parametrize(
    "fault", ["identity", "consent", "projection", "rollback", "conflict"]
)
def test_legacy_transition_proof_and_atomicity(monkeypatch, fault):
    legacy, event = legacy_fixture()
    critical = published(event, severity="critical")
    receive(critical)
    if fault == "identity":

        def corrupt(c):
            raw = c.execute(
                "SELECT working_package_json FROM guide_operator_assignment_versions WHERE assignment_id=? AND version_number=1",
                (legacy.assignment_id,),
            ).fetchone()[0]
            p = json.loads(raw)
            p["tour"]["id"] = str(uuid4())
            c.execute(
                "UPDATE guide_operator_assignment_versions SET working_package_json=? WHERE assignment_id=? AND version_number=1",
                (json.dumps(p), legacy.assignment_id),
            )

        run_write_with_retry(corrupt)
    elif fault == "consent":
        run_write_with_retry(
            lambda c: c.execute(
                "DELETE FROM guide_operator_assignment_decisions WHERE assignment_id=?",
                (legacy.assignment_id,),
            )
        )
    elif fault == "projection":
        run_write_with_retry(
            lambda c: c.execute(
                "UPDATE guide_operator_assignments SET projection_tour_id=NULL WHERE assignment_id=?",
                (legacy.assignment_id,),
            )
        )
    elif fault == "rollback":

        def fail():
            raise RuntimeError("transition rollback")

        monkeypatch.setattr(domain, "_CRITICAL_VERSION_DECISION_FAILURE_HOOK", fail)
    else:
        # A newly selected date outside the old range conflicts with a personal row.
        from services.tour_service import save_tour

        save_tour(
            user_id=501,
            company="Personal",
            city="Bukhara",
            date_text="2026-11-13",
            status="confirmed",
        )

        # The existing initialization normalizes NULL personal titles. Prepare a
        # complete personal fixture so this assertion isolates transaction writes.
        run_write_with_retry(
            lambda c: c.execute(
                "UPDATE tours SET title='Personal' WHERE user_id=501 AND company='Personal'"
            )
        )

        # Alter only the isolated fixture's pending authority to cover that date.
        def extend(c):
            p = copy.deepcopy(critical["payload"]["working_package"])
            p["days"][1]["date"] = p["assignment"]["end_date"] = "2026-11-13"
            c.execute(
                "UPDATE guide_operator_assignment_versions SET working_package_json=? WHERE assignment_id=? AND version_number=2",
                (json.dumps(p), legacy.assignment_id),
            )

        run_write_with_retry(extend)
    before = fingerprint()
    with pytest.raises(
        (domain.AssignmentValidationError, domain.CalendarConflictError, RuntimeError)
    ):
        decide(event, "confirm_critical", 2)
    assert fingerprint() == before


@pytest.mark.parametrize(
    "fault",
    [
        "money",
        "day_id",
        "connection_company",
        "connection_guide",
        "path",
        "unknown_key",
    ],
)
def test_malformed_or_unconsented_offer_has_no_partial_writes(fault):
    event = seed()
    payload = event["payload"]
    path = payload["assignment_id"]
    if fault == "money":
        payload["working_package"]["remuneration"] = 0
    elif fault == "day_id":
        payload["working_package"]["days"][1]["tour_day_id"] = payload[
            "working_package"
        ]["days"][0]["tour_day_id"]
    elif fault == "connection_company":
        payload["company_id"] = payload["working_package"]["company_id"] = str(uuid4())
    elif fault == "connection_guide":
        register_user(502)
        payload["guide_os_id"] = payload["working_package"]["assignment"][
            "guide_os_id"
        ] = get_guide_os_id(502)
    elif fault == "path":
        path = str(uuid4())
    else:
        payload["working_package"]["private_comment"] = "hidden"
    before = fingerprint()
    with pytest.raises(domain.GuideOperatorAssignmentError):
        receive_assignment_event_v2(event, assignment_id=path, receive_enabled=True)
    assert fingerprint() == before
