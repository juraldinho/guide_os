"""Stage 5A.1 local-only agreed history; isolated SQLite, no money transport."""

import copy
import json
import sqlite3
from uuid import uuid4

import pytest

from database.db import get_db_connection, init_db, run_write_with_retry
from database.queries import get_guide_os_id, register_user
from services import guide_operator_assignment_service as domain
from services.guide_operator_assignment_v2_contract import validate_package
from tests.test_guide_operator_daily_projections import NOW, pending, rows, seed, state

TABLES = (
    "guide_operator_remuneration_versions",
    "guide_operator_remuneration_days",
    "guide_operator_remuneration_effective",
    "guide_operator_assignments",
    "guide_operator_daily_projections",
    "tours",
    "guide_operator_daily_operation_inbox",
    "guide_operator_outbox",
    "guide_operator_assignment_decisions",
    "guide_operator_critical_version_decisions",
    "guide_operator_cancellation_inbox",
    "go_operator_projection_release",
    "go_operator_projection_occupancy_update",
)


def money(package, amounts=(None, 0), default=None):
    result = copy.deepcopy(package)
    result["remuneration"] = {
        "schema_version": "assignment.remuneration.v1",
        "currency": "USD",
        "scale": 0,
        "default_daily_usd": default,
        "days": [
            {
                "tour_day_id": day["tour_day_id"],
                "amount_usd": amount,
                "source": "manual",
            }
            for day, amount in zip(result["days"], amounts, strict=True)
        ],
    }
    return result


def prepared(**kwargs):
    fixture = seed(**kwargs)
    package = money(fixture[2])
    store_initial(fixture, package)
    return fixture[0], fixture[1], package, fixture[3]


def store_initial(fixture, package):
    run_write_with_retry(
        lambda conn: conn.execute(
            "UPDATE guide_operator_assignment_versions SET working_package_json=? WHERE assignment_id=? AND version_number=1",
            (json.dumps(package), fixture[1]),
        )
    )


def apply(fixture, action="accept", version=1, event_id=None, **kwargs):
    return domain._apply_explicit_projection_decision_local(
        fixture[0],
        fixture[1],
        action=action,
        version_number=version,
        event_id=event_id or str(uuid4()),
        occurred_at=NOW,
        local_money_enabled=True,
        **kwargs,
    )


def records(table, assignment_id=None):
    with get_db_connection() as conn:
        return [
            dict(r)
            for r in conn.execute(
                f"SELECT * FROM {table}"
                + (" WHERE assignment_id=?" if assignment_id else "")
                + " ORDER BY rowid",
                (assignment_id,) if assignment_id else (),
            )
        ]


def snapshot():
    return {t: records(t) for t in TABLES}


@pytest.mark.parametrize("amount", [True, False, 1.0, 1.5, "5", -1, 9007199254740992])
def test_strict_integer_validation_is_atomic(amount):
    fixture = prepared()
    package = money(fixture[2], (amount, 0))
    store_initial(fixture, package)
    before = snapshot()
    with pytest.raises(domain.AssignmentValidationError):
        apply(fixture)
    assert snapshot() == before


@pytest.mark.parametrize(
    "change",
    [
        "currency",
        "scale",
        "bool_scale",
        "default_float",
        "schema",
        "extra",
        "duplicate",
        "missing",
        "foreign",
        "default_mismatch",
        "total_overflow",
    ],
)
def test_exact_contract_and_checked_total(change):
    fixture = prepared()
    package = copy.deepcopy(fixture[2])
    value = package["remuneration"]
    if change == "currency":
        value["currency"] = "EUR"
    if change == "scale":
        value["scale"] = 2
    if change == "bool_scale":
        value["scale"] = False
    if change == "default_float":
        value["default_daily_usd"] = 1.0
    if change == "schema":
        value["schema_version"] = "other"
    if change == "extra":
        value["paid"] = True
    if change == "duplicate":
        value["days"][1] = copy.deepcopy(value["days"][0])
    if change == "missing":
        value["days"].pop()
    if change == "foreign":
        value["days"][0]["tour_day_id"] = str(uuid4())
    if change == "default_mismatch":
        value["days"][1]["source"] = "default"
    if change == "total_overflow":
        value["days"][0]["amount_usd"] = 9007199254740991
        value["days"][1]["amount_usd"] = 1
    store_initial(fixture, package)
    before = snapshot()
    with pytest.raises(domain.AssignmentValidationError):
        apply(fixture)
    assert snapshot() == before


def test_accept_null_zero_sparse_replay_and_no_personal_finance():
    fixture = prepared()
    event = str(uuid4())
    assert apply(fixture, event_id=event)["status"] == "accepted"
    header = records(TABLES[0], fixture[1])[0]
    assert (header["currency"], header["scale"], header["default_daily_usd"]) == (
        "USD",
        0,
        None,
    )
    assert (header["known_total_usd"], header["unknown_day_count"]) == (0, 1)
    history = records(TABLES[1], fixture[1])
    assert [r["amount_usd"] for r in history] == [None, 0]
    assert [r["calendar_date"] for r in history] == ["2026-11-10", "2026-11-12"]
    assert all(
        r["effective_version_number"] == 1 and r["state"] == "active"
        for r in records(TABLES[2])
    )
    assert all(
        r["income"] is None and r["payment_status"] == "unpaid"
        for r in rows(fixture[1])
    )
    before = snapshot()
    assert apply(fixture, event_id=event)["replayed"] is True
    assert snapshot() == before
    # A new decision identity is not a second agreement.
    with pytest.raises(domain.AssignmentNotActionableError):
        apply(fixture)
    assert snapshot() == before


def test_max_integer_and_default_materialization():
    fixture = prepared()
    package = money(fixture[2], (9007199254740991, 0), default=9007199254740991)
    package["remuneration"]["days"][0]["source"] = "default"
    store_initial(fixture, package)
    apply(fixture)
    assert records(TABLES[0])[0]["known_total_usd"] == 9007199254740991
    assert records(TABLES[1])[0]["source"] == "default"


def test_pending_reject_and_later_confirm_preserve_effective_history():
    fixture = prepared()
    apply(fixture)
    package = money(fixture[2], (70, 90), default=80)
    before = [records(t) for t in TABLES[:3]]
    pending(fixture, package)
    assert [records(t) for t in TABLES[:3]] == before
    event = str(uuid4())
    apply(fixture, "reject_critical", 2, event)
    assert [records(t) for t in TABLES[:3]] == before
    assert state(fixture[1])["active_version_number"] == 1
    assert apply(fixture, "reject_critical", 2, event)["replayed"]
    pending(fixture, package, 3)
    apply(fixture, "confirm_critical", 3)
    assert [r["version_number"] for r in records(TABLES[0])] == [1, 3]
    assert [r["amount_usd"] for r in records(TABLES[1])] == [None, 0, 70, 90]
    assert all(r["effective_version_number"] == 3 for r in records(TABLES[2]))
    assert state(fixture[1])["active_version_number"] == 3


def test_move_remove_reintroduce_retains_natural_identity_and_versions():
    fixture = prepared()
    apply(fixture)
    original = copy.deepcopy(fixture[2])
    first_id, removed_id = [d["tour_day_id"] for d in original["days"]]
    package = copy.deepcopy(original)
    package["days"][0]["date"] = "2026-11-11"
    package["days"][1] = {"tour_day_id": str(uuid4()), "date": "2026-11-13"}
    package["assignment"].update(start_date="2026-11-11", end_date="2026-11-13")
    package = money(package, (30, 40))
    pending(fixture, package)
    event = str(uuid4())
    old_projection = rows(fixture[1])[0]["projection_tour_id"]
    apply(fixture, "confirm_critical", 2, event)
    effective = {r["tour_day_id"]: r for r in records(TABLES[2])}
    assert effective[removed_id]["state"] == "removed"
    assert effective[removed_id]["effective_version_number"] is None
    assert effective[removed_id]["last_agreed_version_number"] == 1
    assert rows(fixture[1])[0]["projection_tour_id"] == old_projection
    assert [
        r["calendar_date"] for r in records(TABLES[1]) if r["tour_day_id"] == first_id
    ] == ["2026-11-10", "2026-11-11"]
    before = snapshot()
    assert apply(fixture, "confirm_critical", 2, event)["replayed"]
    assert snapshot() == before
    # Reintroduced stable day is the same entitlement with a new agreed version.
    next_package = money(original, (50, 60))
    pending(fixture, next_package, 3)
    apply(fixture, "confirm_critical", 3)
    effective = {r["tour_day_id"]: r for r in records(TABLES[2])}
    assert len(effective) == 3
    assert effective[removed_id]["effective_version_number"] == 3
    assert len(records(TABLES[1])) == 6


def test_cancellation_keeps_history_and_other_role_finances():
    fixture = prepared()
    apply(fixture)
    peer = prepared(
        guide=fixture[0],
        connection=fixture[3],
        tour_id=fixture[2]["tour"]["id"],
        role="local_guide",
    )
    package = money({**peer[2], "days": copy.deepcopy(fixture[2]["days"])}, (25, 50))
    store_initial(peer, package)
    apply(peer)
    peer_before = [records(t, peer[1]) for t in TABLES[:3]]
    pending(fixture, money(fixture[2], (100, 200)))
    apply(fixture, "confirm_critical", 2)
    assert [records(t, peer[1]) for t in TABLES[:3]] == peer_before
    run_write_with_retry(
        lambda conn: conn.execute(
            "INSERT INTO tours(user_id,company,city,start_date,end_date,status,income,payment_status,entry_type,source) "
            "VALUES (501,'Personal','City','2026-11-11','2026-11-11','confirmed',250,'paid','tour','manual')"
        )
    )
    run_write_with_retry(
        lambda conn: conn.execute(
            "INSERT INTO daily_tips(user_id,tip_date,amount) VALUES (501,'2026-11-11',35)"
        )
    )
    init_db()  # Existing schema normalization is independent of cancellation.
    personal_before = [r for r in records("tours") if r["source"] != "guide_operator"]
    tips_before = records("daily_tips")
    pending(fixture, money(fixture[2], (500, 600)), 3)
    unpublished = records("guide_operator_assignment_versions", fixture[1])
    history = records(TABLES[1], fixture[1])
    event = str(uuid4())
    apply(fixture, "cancel", 2, event_id=event)
    assert records("guide_operator_assignment_versions", fixture[1]) == unpublished
    assert state(fixture[1])["pending_critical_version_number"] is None
    assert [r["version_number"] for r in records(TABLES[0], fixture[1])] == [1, 2]
    assert records(TABLES[1], fixture[1]) == history
    assert all(
        r["state"] == "cancelled" and r["effective_version_number"] is None
        for r in records(TABLES[2], fixture[1])
    )
    assert [records(t, peer[1]) for t in TABLES[:3]] == peer_before
    assert len(rows(peer[1])) == 2 and rows(fixture[1]) == []
    before = snapshot()
    assert apply(fixture, "cancel", 2, event_id=event)["replayed"]
    assert snapshot() == before
    assert [
        r for r in records("tours") if r["source"] != "guide_operator"
    ] == personal_before
    assert records("daily_tips") == tips_before
    with pytest.raises(domain.AssignmentNotActionableError):
        apply(fixture, "confirm_critical", 3)


@pytest.mark.parametrize(
    "action,hook",
    [
        ("accept", "_ACCEPT_FAILURE_HOOK"),
        ("confirm_critical", "_CRITICAL_VERSION_DECISION_FAILURE_HOOK"),
        ("cancel", "_CANCEL_FAILURE_HOOK"),
    ],
)
def test_atomic_rollback_after_all_domain_writes(monkeypatch, action, hook):
    fixture = prepared()
    version = 1
    if action != "accept":
        apply(fixture)
    if action == "confirm_critical":
        pending(fixture, money(fixture[2], (75, 80)))
        version = 2
    before = snapshot()

    def fail():
        raise RuntimeError("injected rollback")

    monkeypatch.setattr(domain, hook, fail)
    with pytest.raises(RuntimeError, match="injected rollback"):
        apply(fixture, action, version)
    assert snapshot() == before


@pytest.mark.parametrize(
    "field,value",
    [("company_id", str(uuid4())), ("guide", str(uuid4())), ("tour", str(uuid4()))],
)
def test_company_guide_tour_binding(field, value):
    fixture = prepared()
    package = copy.deepcopy(fixture[2])
    if field == "company_id":
        package["company_id"] = value
    if field == "guide":
        package["assignment"]["guide_os_id"] = value
    if field == "tour":
        package["tour"]["id"] = value
    store_initial(fixture, package)
    before = snapshot()
    with pytest.raises(domain.AssignmentValidationError):
        apply(fixture)
    assert snapshot() == before


def test_wrong_session_guide_and_production_gates():
    fixture = prepared()
    register_user(502)
    before = snapshot()
    with pytest.raises(domain.AssignmentNotFoundError):
        domain._apply_explicit_projection_decision_local(
            get_guide_os_id(502),
            fixture[1],
            action="accept",
            version_number=1,
            event_id=str(uuid4()),
            occurred_at=NOW,
            local_money_enabled=True,
        )
    with pytest.raises(domain.AssignmentValidationError):
        domain.accept_assignment(
            guide_os_id=fixture[0],
            assignment_id=fixture[1],
            decision_event_id=str(uuid4()),
        )
    for flags in (
        {},
        {"local_money_enabled": "true"},
        {"local_money_enabled": True, "public_replay": True},
        {"local_money_enabled": True, "wire_cancellation": True},
    ):
        with pytest.raises(domain.AssignmentValidationError):
            domain._apply_explicit_projection_decision_local(
                fixture[0],
                fixture[1],
                action="accept",
                version_number=1,
                event_id=str(uuid4()),
                occurred_at=NOW,
                **flags,
            )
    with pytest.raises(domain.AssignmentValidationError):
        validate_package(fixture[2])
    assert snapshot() == before


@pytest.mark.parametrize("action", ["cancel", "confirm_critical"])
@pytest.mark.parametrize(
    "income,payment", [(0, "unpaid"), (100, "unpaid"), (None, "paid")]
)
def test_financially_nonempty_projections_remain_protected(action, income, payment):
    fixture = prepared()
    apply(fixture)
    projection_id = rows(fixture[1])[0]["projection_tour_id"]

    def inject(conn):
        # Simulate existing historical financial data; production has no such write path.
        conn.execute("DROP TRIGGER trg_tours_operator_managed_no_update")
        conn.execute(
            "UPDATE tours SET income=?,payment_status=? WHERE id=?",
            (income, payment, projection_id),
        )

    run_write_with_retry(inject)
    init_db()
    version = 1
    if action == "confirm_critical":
        pending(fixture, money(fixture[2], (60, 70)))
        version = 2
    before = snapshot()
    with pytest.raises(domain.AssignmentValidationError, match="Financially"):
        apply(fixture, action, version)
    assert snapshot() == before


def test_no_money_legacy_migration_repeat_and_immutable_constraints():
    fixture = seed()

    # Simulate the additive upgrade from the immediately preceding schema.
    def old_schema(conn):
        for table in reversed(TABLES[:3]):
            conn.execute(f"DROP TABLE {table}")

    run_write_with_retry(old_schema)
    before = state(fixture[1])
    init_db()
    init_db()
    assert state(fixture[1]) == before
    assert all(records(t) == [] for t in TABLES[:3])
    apply(fixture)  # Explicit no-money still creates no invented accruals.
    assert all(records(t) == [] for t in TABLES[:3])
    priced = money(fixture[2])
    pending(fixture, priced)
    apply(fixture, "confirm_critical", 2)
    agreed = [records(t) for t in TABLES[:3]]
    init_db()
    assert [records(t) for t in TABLES[:3]] == agreed
    with get_db_connection() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in TABLES[:2]:
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                conn.execute(f"DELETE FROM {table}")
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                conn.execute(f"UPDATE {table} SET version_number=99")
        for value in (-1, 1.5, 9007199254740992, "bad"):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO guide_operator_remuneration_days VALUES (?,?,?,?,?,?)",
                    (fixture[1], str(uuid4()), 2, "2026-11-14", value, "manual"),
                )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE guide_operator_remuneration_effective SET company_id=?",
                (str(uuid4()),),
            )


def test_money_cannot_be_silently_stripped_on_confirm():
    fixture = prepared()
    apply(fixture)
    package = copy.deepcopy(fixture[2])
    package["remuneration"] = None
    pending(fixture, package)
    before = snapshot()
    with pytest.raises(domain.AssignmentValidationError):
        apply(fixture, "confirm_critical", 2)
    assert snapshot() == before
    # Even corrupt/stripped snapshot metadata cannot bypass the public capability gate.
    store_initial(fixture, package)
    before = snapshot()
    with pytest.raises(
        domain.AssignmentValidationError, match="capability is disabled"
    ):
        domain._apply_explicit_projection_decision_local(
            fixture[0],
            fixture[1],
            action="cancel",
            version_number=1,
            event_id=str(uuid4()),
            occurred_at=NOW,
        )
    assert snapshot() == before


def test_all_null_default_is_an_explicit_agreement_not_free():
    fixture = prepared()
    package = money(fixture[2], (None, None))
    for row in package["remuneration"]["days"]:
        row["source"] = "default"
    store_initial(fixture, package)
    apply(fixture)
    assert records(TABLES[0])[0]["unknown_day_count"] == 2
    assert records(TABLES[0])[0]["known_total_usd"] == 0
    assert [r["amount_usd"] for r in records(TABLES[1])] == [None, None]
    assert len(records(TABLES[2])) == 2


def test_concurrent_identical_accept_has_one_agreement():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    fixture = prepared()
    event = str(uuid4())
    barrier = Barrier(2)

    def accept():
        barrier.wait(timeout=10)
        return apply(fixture, event_id=event)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(accept)
        second = pool.submit(accept)
        results = [first.result(timeout=15), second.result(timeout=15)]
    assert sorted(r["replayed"] for r in results) == [False, True]
    assert len(records(TABLES[0])) == 1 and len(records(TABLES[1])) == 2
    assert len(rows(fixture[1])) == 2


def test_conflicting_moved_day_rolls_back_money_and_keeps_pending():
    fixture = prepared()
    apply(fixture)
    run_write_with_retry(
        lambda conn: conn.execute(
            "INSERT INTO tours(user_id,company,city,start_date,end_date,status,income,payment_status,entry_type,source) "
            "VALUES (501,'Other','City','2026-11-11','2026-11-11','confirmed',NULL,'unpaid','tour','manual')"
        )
    )
    package = money(fixture[2], (70, 90))
    package["days"][0]["date"] = "2026-11-11"
    package["assignment"]["start_date"] = "2026-11-11"
    pending(fixture, package)
    init_db()
    before = snapshot()
    with pytest.raises(domain.CalendarConflictError):
        apply(fixture, "confirm_critical", 2)
    assert snapshot() == before
    assert state(fixture[1])["pending_critical_version_number"] == 2
