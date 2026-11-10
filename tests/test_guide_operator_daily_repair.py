"""Explicit repair domain only. Fault injection and all writes use temporary DBs."""

import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from database.db import get_db_connection, run_write_with_retry
from services import guide_operator_reconcile_repair_service as repair
from services.guide_operator_reconcile_service import get_local_assignment_v2
from services.tour_service import save_tour
from tests.test_guide_operator_daily_projections import (
    apply,
    pending,
    rows,
    seed,
)
from tests.test_guide_operator_reconcile_v2 import dump, remove_projection


def snapshot(f):
    return get_local_assignment_v2(f[0], f[1])


def request(f, *, evidence=None, request_id=None, **overrides):
    evidence = snapshot(f) if evidence is None else evidence
    values = {
        "repair_request_id": request_id or str(uuid4()),
        "expected_status": evidence["status"],
        "expected_active_version_number": evidence["active_version_number"],
        "expected_fingerprint": evidence["fingerprint"],
    }
    values.update(overrides)
    return repair.repair_local_projection_set(f[0], f[1], **values)


def history():
    with get_db_connection() as conn:
        return {
            name: [tuple(row) for row in conn.execute("SELECT * FROM " + name)]
            for name in (
                "guide_operator_assignments",
                "guide_operator_assignment_versions",
                "guide_operator_assignment_decisions",
                "guide_operator_critical_version_decisions",
                "guide_operator_cancellation_inbox",
                "guide_operator_daily_operation_inbox",
                "guide_operator_outbox",
                "guide_operator_guide_notifications",
            )
        }


def extra(
    f,
    *,
    key=None,
    date="2026-11-11",
    linked=True,
    income=None,
    payment="unpaid",
    group=None,
):
    key = key or str(uuid4())

    def operation(conn):
        cursor = conn.execute(
            "INSERT INTO tours(user_id,company,city,start_date,end_date,status,income,"
            "payment_status,note,entry_type,tour_group_id,title,source) "
            "VALUES (501,'Company','City',?,?,'confirmed',?,?,?,'tour',?,'Stray','guide_operator')",
            (
                date,
                date,
                income,
                payment,
                "go_assignment:" + f[1],
                group or f"{f[1]}:{key}",
            ),
        )
        row_id = cursor.lastrowid
        if linked:
            conn.execute(
                "INSERT INTO guide_operator_daily_projections(source_service,company_id,assignment_id,"
                "guide_os_id,operator_tour_id,tour_day_id,calendar_date,active_version_number,projection_tour_id) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "guide_operator",
                    f[3]["company_id"],
                    f[1],
                    f[0],
                    f[2]["tour"]["id"],
                    key,
                    date,
                    1,
                    row_id,
                ),
            )
        return row_id

    return run_write_with_retry(operation)


def corrupt_dates(f, *, swap=False):
    current = rows(f[1])

    def operation(conn):
        for i, row in enumerate(current):
            value = current[1 - i]["calendar_date"] if swap else "2026-11-11"
            conn.execute(
                "INSERT INTO go_operator_projection_occupancy_update(tour_id) VALUES (?)",
                (row["projection_tour_id"],),
            )
            conn.execute(
                "UPDATE tours SET start_date=?,end_date=? WHERE id=?",
                (value, value, row["projection_tour_id"]),
            )
            conn.execute(
                "DELETE FROM go_operator_projection_occupancy_update WHERE tour_id=?",
                (row["projection_tour_id"],),
            )
        conn.execute(
            "UPDATE guide_operator_daily_projections SET active_version_number=99 WHERE assignment_id=?",
            (f[1],),
        )

    run_write_with_retry(operation)


def assert_clean(f):
    value = snapshot(f)
    desired = {
        (d["tour_day_id"], d["date"], d["date"], value["active_version_number"])
        for d in value["active_days"]
    }
    assert {
        (p["tour_day_id"], p["date"], p["end_date"], p["active_version_number"])
        for p in value["projections"]
    } == desired
    assert all(not p["issues"] for p in value["projections"])
    with get_db_connection() as conn:
        for table in (
            "go_operator_projection_release",
            "go_operator_projection_occupancy_update",
            "go_operator_projection_metadata_update",
        ):
            assert conn.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_missing_extra_repair_preserves_another_role_history_and_records():
    a = seed()
    apply(a)
    b = seed(
        guide=a[0], connection=a[3], tour_id=a[2]["tour"]["id"], role="local_guide"
    )
    apply(b)
    peer = rows(b[1])
    retained = rows(a[1])[0]["projection_tour_id"]
    remove_projection(a[1], rows(a[1])[1]["projection_tour_id"])
    extra_id = extra(a)
    before = history()
    evidence = snapshot(a)
    key = str(uuid4())
    result = request(a, evidence=evidence, request_id=key)
    assert result.status == "applied"
    assert_clean(a)
    assert rows(a[1])[0]["projection_tour_id"] == retained
    assert rows(b[1]) == peer and history() == before
    with get_db_connection() as conn:
        assert (
            conn.execute("SELECT 1 FROM tours WHERE id=?", (extra_id,)).fetchone()
            is None
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM guide_operator_projection_repair_audits"
            ).fetchone()[0]
            == 1
        )
    replay = request(a, evidence=evidence, request_id=key)
    assert (
        replay.status == result.status
        and replay.action == result.action
        and replay.replayed
    )
    assert request(a, request_id=key).status == "conflict"


@pytest.mark.parametrize("swap", [False, True])
def test_wrong_dates_and_link_versions_update_atomically_retaining_ids(swap):
    f = seed()
    apply(f)
    ids = {r["tour_day_id"]: r["projection_tour_id"] for r in rows(f[1])}
    corrupt_dates(f, swap=swap)
    before = history()
    assert request(f).status == "applied"
    assert_clean(f)
    assert {r["tour_day_id"]: r["projection_tour_id"] for r in rows(f[1])} == ids
    assert history() == before


def test_financial_fields_retained_even_if_link_was_lost_but_extra_finances_refused():
    f = seed()
    apply(f)
    key = f[2]["days"][0]["tour_day_id"]
    remove_projection(f[1], rows(f[1])[0]["projection_tour_id"])
    paid = extra(f, key=key, linked=False, income=77, payment="paid")
    assert request(f).status == "applied"
    assert_clean(f)
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM tours WHERE id=?", (paid,)).fetchone()
        assert row["income"] == 77 and row["payment_status"] == "paid"
    extra(f, income=55)
    before = snapshot(f)
    assert request(f).status == "no-op"
    assert snapshot(f) == before


def test_conflict_and_stale_fingerprint_never_partially_write():
    f = seed()
    apply(f)
    evidence = snapshot(f)
    remove_projection(f[1], rows(f[1])[1]["projection_tour_id"])
    before = history()
    assert request(f, evidence=evidence).status == "no-op"
    save_tour(501, "Personal", "City", "2026-11-12", "confirmed", income=10)
    current = snapshot(f)
    assert request(f).status == "conflict"
    assert snapshot(f) == current and history() == before


@pytest.mark.parametrize(
    "fault",
    [
        "pending",
        "gap",
        "no_accept",
        "no_confirm",
        "wrong_group",
        "duplicate",
        "no_cancel",
        "orphan",
    ],
)
def test_unsafe_states_refuse_without_calendar_or_history_changes(fault):
    f = seed()
    apply(f)
    if fault == "pending":
        pending(f, copy.deepcopy(f[2]))
    elif fault == "gap":
        pending(f, copy.deepcopy(f[2]), 3)
        run_write_with_retry(
            lambda conn: conn.execute(
                "UPDATE guide_operator_assignments SET pending_critical_version_number=NULL WHERE assignment_id=?",
                (f[1],),
            )
        )
    elif fault == "no_accept":
        run_write_with_retry(
            lambda conn: conn.execute(
                "DELETE FROM guide_operator_assignment_decisions WHERE assignment_id=?",
                (f[1],),
            )
        )
    elif fault == "no_confirm":
        pending(f, copy.deepcopy(f[2]))
        apply(f, "confirm_critical", 2)
        run_write_with_retry(
            lambda conn: conn.execute(
                "DELETE FROM guide_operator_critical_version_decisions WHERE assignment_id=?",
                (f[1],),
            )
        )
    elif fault == "wrong_group":
        # A foreign calendar reference must not be claimed through repair.
        b = seed(
            guide=f[0], connection=f[3], tour_id=f[2]["tour"]["id"], role="local_guide"
        )
        apply(b)
        peer_id = rows(b[1])[0]["projection_tour_id"]

        def corrupt(conn):
            conn.execute(
                "DELETE FROM guide_operator_daily_projections WHERE projection_tour_id=?",
                (peer_id,),
            )
            conn.execute(
                "UPDATE guide_operator_daily_projections SET projection_tour_id=? WHERE tour_day_id=?",
                (peer_id, f[2]["days"][0]["tour_day_id"]),
            )

        run_write_with_retry(corrupt)
    elif fault == "duplicate":
        extra(f, key=f[2]["days"][0]["tour_day_id"], linked=False)
    elif fault == "orphan":
        extra(f, linked=False, group=str(uuid4()))
    elif fault == "no_cancel":
        apply(f, "cancel")
        extra(f, linked=False)
        run_write_with_retry(
            lambda conn: conn.execute(
                "DELETE FROM guide_operator_cancellation_inbox WHERE assignment_id=?",
                (f[1],),
            )
        )
    before, immutable = snapshot(f), history()
    assert request(f).status == "no-op"
    assert snapshot(f) == before and history() == immutable


def test_cancelled_only_releases_own_strays_with_retained_cancellation_evidence():
    f = seed()
    apply(f)
    b = seed(
        guide=f[0], connection=f[3], tour_id=f[2]["tour"]["id"], role="local_guide"
    )
    apply(b)
    apply(f, "cancel")
    extra(f, linked=False)
    peer, immutable = rows(b[1]), history()
    result = request(f)
    assert result.status == "applied" and result.action == "release_stray"
    assert snapshot(f)["projections"] == []
    assert rows(b[1]) == peer and history() == immutable


def test_rollback_covers_projections_links_inbox_audit_and_allowlists(monkeypatch):
    f = seed()
    apply(f)
    remove_projection(f[1], rows(f[1])[1]["projection_tour_id"])
    extra(f, linked=False)
    before = dump()

    def fail():
        raise RuntimeError("injected rollback")

    monkeypatch.setattr(repair, "_REPAIR_FAILURE_HOOK", fail)
    with pytest.raises(RuntimeError, match="injected rollback"):
        request(f)
    assert dump() == before


def test_concurrent_replays_have_one_audit_and_one_projection_set():
    f = seed()
    apply(f)
    remove_projection(f[1], rows(f[1])[1]["projection_tour_id"])
    evidence, key, barrier = snapshot(f), str(uuid4()), Barrier(2)

    def run():
        barrier.wait()
        return request(f, evidence=evidence, request_id=key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = [future.result() for future in (pool.submit(run), pool.submit(run))]
    assert a.status == b.status == "applied" and a.replayed != b.replayed
    assert_clean(f)
    with get_db_connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM guide_operator_projection_repair_audits"
            ).fetchone()[0]
            == 1
        )


def test_repair_cancel_race_is_terminal_and_replay_never_resurrects():
    f = seed()
    apply(f)

    def drift(conn):
        row_id = rows(f[1])[0]["projection_tour_id"]
        conn.execute(
            "INSERT INTO go_operator_projection_metadata_update(tour_id) VALUES (?)",
            (row_id,),
        )
        conn.execute("UPDATE tours SET title='Drift' WHERE id=?", (row_id,))
        conn.execute(
            "DELETE FROM go_operator_projection_metadata_update WHERE tour_id=?",
            (row_id,),
        )

    run_write_with_retry(drift)
    evidence, key, barrier = snapshot(f), str(uuid4()), Barrier(2)

    def run_repair():
        barrier.wait()
        return request(f, evidence=evidence, request_id=key)

    def cancel():
        barrier.wait()
        return apply(f, "cancel")

    with ThreadPoolExecutor(max_workers=2) as pool:
        repaired, cancelled = [
            future.result() for future in (pool.submit(run_repair), pool.submit(cancel))
        ]
    assert (
        repaired.status in ("applied", "no-op") and cancelled["status"] == "cancelled"
    )
    assert snapshot(f)["projections"] == []
    assert request(f, evidence=evidence, request_id=key).replayed
    assert snapshot(f)["projections"] == []


def test_stale_repair_confirm_race_cannot_restore_old_scope():
    f = seed()
    apply(f)
    evidence = snapshot(f)
    proposed = copy.deepcopy(f[2])
    proposed["days"][1]["date"] = "2026-11-14"
    proposed["assignment"]["end_date"] = "2026-11-14"
    pending(f, proposed)
    barrier = Barrier(2)

    def run_repair():
        barrier.wait()
        return request(f, evidence=evidence)

    def confirm():
        barrier.wait()
        return apply(f, "confirm_critical", 2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        repaired, confirmed = [
            future.result()
            for future in (pool.submit(run_repair), pool.submit(confirm))
        ]
    assert repaired.status == "no-op" and confirmed["active_version_number"] == 2
    assert_clean(f)
    assert [r["calendar_date"] for r in rows(f[1])] == ["2026-11-10", "2026-11-14"]


def test_confirmed_active_version_repair_uses_current_agreement():
    f = seed()
    apply(f)
    proposed = copy.deepcopy(f[2])
    proposed["days"][1]["date"] = "2026-11-14"
    proposed["assignment"]["end_date"] = "2026-11-14"
    pending(f, proposed)
    apply(f, "confirm_critical", 2)
    remove_projection(f[1], rows(f[1])[1]["projection_tour_id"])
    assert request(f).status == "applied"
    assert_clean(f)
    assert [r["calendar_date"] for r in rows(f[1])] == ["2026-11-10", "2026-11-14"]


@pytest.mark.parametrize("changed", [False, True])
def test_ordinary_scope_requires_retained_guide_agreement(changed):
    f = seed()
    apply(f)
    proposed = copy.deepcopy(f[2])
    if changed:
        proposed["days"][1]["date"] = "2026-11-14"
        proposed["assignment"]["end_date"] = "2026-11-14"
    pending(f, proposed)

    # Prepared future ordinary local state, not a new intake or publication path.
    def prepare(conn):
        conn.execute(
            "UPDATE guide_operator_assignment_versions SET severity='ordinary' WHERE assignment_id=? AND version_number=2",
            (f[1],),
        )
        conn.execute(
            "UPDATE guide_operator_assignments SET active_version_number=2,pending_critical_version_number=NULL,end_date=? WHERE assignment_id=?",
            (proposed["assignment"]["end_date"], f[1]),
        )

    run_write_with_retry(prepare)
    before = snapshot(f)
    result = request(f)
    assert result.status == ("no-op" if changed else "applied")
    if changed:
        assert snapshot(f) == before
    else:
        assert_clean(f)


def test_invalid_input_isolation_and_correct_noop():
    f = seed()
    apply(f)
    before = dump()
    with pytest.raises(repair.ProjectionRepairValidationError):
        request(f, expected_fingerprint="invalid")
    with pytest.raises(TypeError):
        request(f, selected_days=[])
    with pytest.raises(repair.ProjectionRepairNotFoundError):
        repair.repair_local_projection_set(
            str(uuid4()),
            f[1],
            repair_request_id=str(uuid4()),
            expected_status="accepted",
            expected_active_version_number=1,
            expected_fingerprint=snapshot(f)["fingerprint"],
        )
    assert dump() == before
    assert request(f).status == "no-op"
    with get_db_connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM guide_operator_projection_repair_audits"
            ).fetchone()[0]
            == 0
        )


def test_unknown_historical_consent_schema_is_not_interpreted():
    import json

    f = seed()
    apply(f)
    pending(f, copy.deepcopy(f[2]))
    apply(f, "confirm_critical", 2)
    remove_projection(f[1], rows(f[1])[1]["projection_tour_id"])
    future = copy.deepcopy(f[2])
    future["schema_version"] = "assignment.working_package.future"
    run_write_with_retry(
        lambda conn: conn.execute(
            "UPDATE guide_operator_assignment_versions SET working_package_json=? "
            "WHERE assignment_id=? AND version_number=1",
            (json.dumps(future), f[1]),
        )
    )
    before, immutable = snapshot(f), history()
    assert request(f).status == "no-op"
    assert snapshot(f) == before and history() == immutable
