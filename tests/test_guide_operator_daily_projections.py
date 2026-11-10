"""2A local domain/storage fixtures, deliberately no v2 receiver or HTTP path."""

import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from database.db import get_db_connection as get_connection
from database.db import init_db, run_write_with_retry
from database.queries import (
    claim_guide_operator_outbox_for_delivery,
    get_guide_operator_assignment,
    get_guide_os_id,
    register_user,
)
from services import guide_operator_assignment_service as service
from services.guide_operator_connection_service import (
    ensure_confirmed_connection_for_tests,
)
from services.guide_operator_reconcile_repair_service import repair_local_projection
from services.guide_operator_reconcile_service import (
    GuideOperatorReconcileValidationError,
    list_local_assignments,
)
from services.tour_service import delete_tour, get_conflicting_dates, save_tour
from tests.test_guide_operator_assignments import _offer

NOW = "2026-11-04T10:00:00+00:00"


def seed(
    *,
    guide=None,
    connection=None,
    tour_id=None,
    dates=("2026-11-10", "2026-11-12"),
    role="main_guide",
):
    if guide is None:
        register_user(501)
        guide = get_guide_os_id(501)
    connection = connection or ensure_confirmed_connection_for_tests(guide)
    assignment_id = str(uuid4())
    tour_id = tour_id or str(uuid4())
    package = {
        "schema_version": "assignment.working_package.v2",
        "company_id": connection["company_id"],
        "tour": {"id": tour_id, "title": "Same title", "city_or_route": "Samarkand"},
        "assignment": {
            "id": assignment_id,
            "guide_os_id": guide,
            "role": role,
            "start_date": min(dates),
            "end_date": max(dates),
        },
        "days": [{"tour_day_id": str(uuid4()), "date": value} for value in dates],
        "remuneration": None,
    }

    # Storage prerequisite only: no production explicit offer intake is implemented.
    def operation(conn):
        conn.execute(
            "INSERT INTO guide_operator_assignments(assignment_id,guide_os_id,company_id,"
            "company_name,guide_connection_id,role,start_date,end_date,status,offer_event_id,"
            "offered_at,projection_mode,operator_tour_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                assignment_id,
                guide,
                connection["company_id"],
                "Same title",
                connection["connection_id"],
                role,
                min(dates),
                max(dates),
                "offered",
                str(uuid4()),
                NOW,
                "explicit_days",
                tour_id,
            ),
        )
        conn.execute(
            "INSERT INTO guide_operator_assignment_versions(assignment_id,version_number,severity,"
            "working_package_json,published_at) VALUES (?,1,'initial',?,?)",
            (assignment_id, json.dumps(package), NOW),
        )

    run_write_with_retry(operation)
    return guide, assignment_id, package, connection


def apply(fixture, action="accept", version=1, event_id=None):
    guide, assignment_id, _, _ = fixture
    return service._apply_explicit_projection_decision_local(
        guide,
        assignment_id,
        action=action,
        version_number=version,
        event_id=event_id or str(uuid4()),
        occurred_at=NOW,
    )


def rows(assignment_id):
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT d.*,t.income,t.payment_status,t.start_date,t.end_date,t.tour_group_id "
                "FROM guide_operator_daily_projections d JOIN tours t ON t.id=d.projection_tour_id "
                "WHERE d.assignment_id=? ORDER BY calendar_date",
                (assignment_id,),
            )
        ]


def state(assignment_id):
    with get_connection() as conn:
        return dict(
            conn.execute(
                "SELECT * FROM guide_operator_assignments WHERE assignment_id=?",
                (assignment_id,),
            ).fetchone()
        )


def pending(fixture, package, number=2):
    _, assignment_id, _, _ = fixture

    def operation(conn):
        conn.execute(
            "INSERT INTO guide_operator_assignment_versions(assignment_id,version_number,severity,"
            "working_package_json,published_at) VALUES (?,?,'critical',?,?)",
            (assignment_id, number, json.dumps(package), NOW),
        )
        conn.execute(
            "UPDATE guide_operator_assignments SET pending_critical_version_number=? "
            "WHERE assignment_id=?",
            (number, assignment_id),
        )

    run_write_with_retry(operation)


def test_sparse_roles_cancel_one_and_replay():
    first = seed()
    event_id = str(uuid4())
    assert apply(first, event_id=event_id)["status"] == "accepted"
    stored = rows(first[1])
    assert [r["calendar_date"] for r in stored] == ["2026-11-10", "2026-11-12"]
    assert all(r["start_date"] == r["end_date"] == r["calendar_date"] for r in stored)
    assert all(r["income"] is None and r["payment_status"] == "unpaid" for r in stored)
    assert get_conflicting_dates(501, "2026-11-11") == []
    assert len({r["tour_group_id"] for r in stored}) == 2
    assert apply(first, event_id=event_id)["replayed"] is True
    assert rows(first[1]) == stored
    with pytest.raises(service.AssignmentConflictError):
        apply(first, action="cancel", event_id=event_id)
    second = seed(
        guide=first[0],
        connection=first[3],
        tour_id=first[2]["tour"]["id"],
        role="accompanying_guide",
    )
    apply(second)
    cancel_id = str(uuid4())
    assert apply(first, action="cancel", event_id=cancel_id)["status"] == "cancelled"
    assert rows(first[1]) == []
    assert len(rows(second[1])) == 2
    assert apply(first, action="cancel", event_id=cancel_id)["replayed"] is True
    with pytest.raises(service.AssignmentNotActionableError):
        apply(first)


@pytest.mark.parametrize(
    "occupancy", ["personal", "day_off", "other_tour", "other_company"]
)
def test_unrelated_occupancy_blocks_entire_accept(occupancy):
    fixture = seed()
    if occupancy in {"personal", "day_off"}:
        save_tour(
            501,
            "Personal",
            "City",
            "2026-11-12",
            "confirmed",
            income=55,
            entry_type="day_off" if occupancy == "day_off" else "tour",
        )
    else:
        peer = seed(
            guide=fixture[0],
            connection=fixture[3] if occupancy == "other_tour" else None,
            tour_id=fixture[2]["tour"]["id"] if occupancy == "other_company" else None,
        )
        apply(peer)
    with pytest.raises(service.CalendarConflictError):
        apply(fixture)
    assert rows(fixture[1]) == []
    assert state(fixture[1])["status"] == "offered"
    with get_connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM guide_operator_assignment_decisions WHERE assignment_id=?",
                (fixture[1],),
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM guide_operator_outbox WHERE aggregate_id=?",
                (fixture[1],),
            ).fetchone()[0]
            == 0
        )


def test_pending_reject_confirm_swap_and_conflict():
    fixture = seed()
    apply(fixture)
    before = rows(fixture[1])
    package = copy.deepcopy(fixture[2])
    package["days"][1]["date"] = "2026-11-13"
    package["assignment"]["end_date"] = "2026-11-13"
    pending(fixture, package)
    assert rows(fixture[1]) == before
    personal_id = save_tour(501, "Personal", "City", "2026-11-13", "confirmed")
    with pytest.raises(service.CalendarConflictError):
        apply(fixture, action="confirm_critical", version=2)
    assert rows(fixture[1]) == before
    assert state(fixture[1])["pending_critical_version_number"] == 2
    apply(fixture, action="reject_critical", version=2)
    assert rows(fixture[1]) == before
    assert state(fixture[1])["active_version_number"] == 1
    delete_tour(501, personal_id)
    swapped = copy.deepcopy(fixture[2])
    swapped["days"][0]["date"], swapped["days"][1]["date"] = (
        swapped["days"][1]["date"],
        swapped["days"][0]["date"],
    )
    pending(fixture, swapped, number=3)
    event_id = str(uuid4())
    apply(fixture, action="confirm_critical", version=3, event_id=event_id)
    after = rows(fixture[1])
    assert {r["tour_day_id"]: r["projection_tour_id"] for r in after} == {
        r["tour_day_id"]: r["projection_tour_id"] for r in before
    }
    assert all(r["active_version_number"] == 3 for r in after)
    assert apply(fixture, action="confirm_critical", version=3, event_id=event_id)[
        "replayed"
    ]
    assert rows(fixture[1]) == after


@pytest.mark.parametrize(
    "action,hook",
    [
        ("accept", "_ACCEPT_FAILURE_HOOK"),
        ("confirm_critical", "_CRITICAL_VERSION_DECISION_FAILURE_HOOK"),
        ("cancel", "_CANCEL_FAILURE_HOOK"),
    ],
)
def test_projection_set_and_decision_rollback(action, hook, monkeypatch):
    fixture = seed()
    if action != "accept":
        apply(fixture)
    if action == "confirm_critical":
        package = copy.deepcopy(fixture[2])
        package["days"][1]["date"] = "2026-11-13"
        package["assignment"]["end_date"] = "2026-11-13"
        pending(fixture, package)
    before, before_state = rows(fixture[1]), state(fixture[1])
    with get_connection() as conn:
        outbox_before = conn.execute(
            "SELECT count(*) FROM guide_operator_outbox"
        ).fetchone()[0]

    def fail():
        raise RuntimeError("injected daily transaction failure")

    monkeypatch.setattr(service, hook, fail)
    with pytest.raises(RuntimeError, match="injected"):
        apply(fixture, action=action, version=2 if action == "confirm_critical" else 1)
    assert rows(fixture[1]) == before
    assert state(fixture[1]) == before_state
    with get_connection() as conn:
        assert (
            conn.execute("SELECT count(*) FROM guide_operator_outbox").fetchone()[0]
            == outbox_before
        )
        for table in [
            "go_operator_projection_release",
            "go_operator_projection_occupancy_update",
        ]:
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_legacy_repair_intake_and_outbound_stay_gated_after_guide_wiring():
    fixture = seed()
    apply(fixture)
    assert get_guide_operator_assignment(fixture[1]) is None
    assert get_conflicting_dates(501, "2026-11-10") == ["2026-11-10"]
    assert service.list_pending_offers(fixture[0]) == []
    lifecycle = service.list_assignment_lifecycle(fixture[0])
    visible = [row["assignment_id"] for key, value in lifecycle.items()
               if key != "as_of_date" for row in value]
    assert visible == [fixture[1]]
    replay = service.accept_assignment(
        fixture[0], fixture[1], decision_event_id=str(uuid4())
    )
    assert replay.replayed and replay.projection_tour_id is None
    assert len(rows(fixture[1])) == 2
    with pytest.raises(GuideOperatorReconcileValidationError):
        list_local_assignments(fixture[0])
    with pytest.raises(GuideOperatorReconcileValidationError):
        repair_local_projection(
            fixture[0],
            fixture[1],
            repair_request_id=str(uuid4()),
            expected_status="accepted",
            expected_active_version_number=1,
            expected_projection={
                "exists": False,
                "start_date": None,
                "end_date": None,
                "version_number": None,
            },
        )
    with get_connection() as conn:
        event_id = conn.execute(
            "SELECT event_id FROM guide_operator_outbox WHERE aggregate_id=?",
            (fixture[1],),
        ).fetchone()[0]
    assert (
        claim_guide_operator_outbox_for_delivery(
            now_iso=NOW,
            lease_until_iso="2026-11-04T11:00:00+00:00",
            deliverable_event_types=("assignment.decision.v1",),
            permanent_error_codes=(),
            event_id=event_id,
        )
        is None
    )
    offer = _offer(fixture[0])
    with pytest.raises(service.AssignmentValidationError, match="intake is disabled"):
        service.receive_assignment_offer(
            service.AssignmentOfferIntake(
                **{
                    **offer.__dict__,
                    "working_package": fixture[2],
                }
            )
        )


def test_protection_identity_and_storage_repeatability():
    fixture = seed()
    apply(fixture)
    before = rows(fixture[1])
    init_db()
    init_db()
    assert rows(fixture[1]) == before
    with get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="protected"):
            conn.execute(
                "UPDATE tours SET income=5 WHERE id=?",
                (before[0]["projection_tour_id"],),
            )
        with pytest.raises(sqlite3.IntegrityError, match="protected"):
            conn.execute(
                "DELETE FROM tours WHERE id=?", (before[0]["projection_tour_id"],)
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE guide_operator_assignments SET operator_tour_id=? WHERE assignment_id=?",
                (str(uuid4()), fixture[1]),
            )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_concurrent_confirm_cancel_is_serialized():
    fixture = seed()
    apply(fixture)
    package = copy.deepcopy(fixture[2])
    package["days"][1]["date"] = "2026-11-13"
    package["assignment"]["end_date"] = "2026-11-13"
    pending(fixture, package)
    barrier = Barrier(2)

    def race(action, version):
        barrier.wait(timeout=5)
        try:
            return apply(fixture, action=action, version=version)["status"]
        except (
            service.AssignmentConflictError,
            service.AssignmentNotActionableError,
        ) as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        confirm = pool.submit(race, "confirm_critical", 2)
        cancel = pool.submit(race, "cancel", 1)
        results = [confirm.result(timeout=15), cancel.result(timeout=15)]
    final = state(fixture[1])
    if final["status"] == "cancelled":
        assert rows(fixture[1]) == []
        assert final["pending_critical_version_number"] is None
        assert "cancelled" in results
    else:
        assert final["active_version_number"] == 2
        assert [r["calendar_date"] for r in rows(fixture[1])] == [
            "2026-11-10",
            "2026-11-13",
        ]
        assert "idempotency_conflict" in results


def test_legacy_database_upgrade_preserves_ranges_snapshots_and_history():
    fixtures = []
    for index, status in enumerate(["accepted", "pending", "cancelled"]):
        register_user(901 + index)
        guide = get_guide_os_id(901 + index)
        offer = _offer(guide)
        service.receive_assignment_offer(offer)
        service.accept_assignment(
            guide, offer.assignment_id, decision_event_id=str(uuid4())
        )
        if status == "cancelled":
            service.apply_assignment_cancellation(
                service.AssignmentCancellationIntake(
                    event_id=str(uuid4()),
                    assignment_id=offer.assignment_id,
                    guide_os_id=guide,
                    version_number=1,
                    cancelled_at=NOW,
                )
            )
        if status == "pending":

            def stage(conn, offer=offer):
                package = json.loads(
                    conn.execute(
                        "SELECT working_package_json FROM "
                        "guide_operator_assignment_versions WHERE assignment_id=? AND version_number=1",
                        (offer.assignment_id,),
                    ).fetchone()[0]
                )
                conn.execute(
                    "INSERT INTO guide_operator_assignment_versions(assignment_id,version_number,"
                    "severity,working_package_json,published_at) VALUES (?,2,'critical',?,?)",
                    (offer.assignment_id, json.dumps(package), NOW),
                )
                conn.execute(
                    "UPDATE guide_operator_assignments SET pending_critical_version_number=2 "
                    "WHERE assignment_id=?",
                    (offer.assignment_id,),
                )

            run_write_with_retry(stage)
        fixtures.append(offer.assignment_id)
    with get_connection() as conn:
        old = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM guide_operator_assignments ORDER BY assignment_id"
            )
        ]
        for row in old:
            row.pop("projection_mode")
            row.pop("operator_tour_id")
        snapshots = [
            tuple(row)
            for row in conn.execute(
                "SELECT * FROM guide_operator_assignment_versions ORDER BY assignment_id,version_number"
            )
        ]
        outbox = [
            tuple(row)
            for row in conn.execute("SELECT * FROM guide_operator_outbox ORDER BY id")
        ]

    # Simulate the actual pre-2A schema, then initialize twice.
    def old_schema(conn):
        for table in [
            "guide_operator_daily_projections",
            "guide_operator_daily_operation_inbox",
        ]:
            conn.execute(f"DROP TABLE {table}")
        conn.execute("DROP TRIGGER trg_go_explicit_identity_immutable")
        conn.execute("DROP TRIGGER trg_go_explicit_insert_identity")
        conn.execute("DROP INDEX idx_go_daily_assignment_identity")
        conn.execute(
            "ALTER TABLE guide_operator_assignments DROP COLUMN operator_tour_id"
        )
        conn.execute(
            "ALTER TABLE guide_operator_assignments DROP COLUMN projection_mode"
        )

    run_write_with_retry(old_schema)
    init_db()
    init_db()
    with get_connection() as conn:
        after = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM guide_operator_assignments ORDER BY assignment_id"
            )
        ]
        for row in after:
            assert row.pop("projection_mode") == "legacy_range"
            assert row.pop("operator_tour_id") is None
        assert after == old
        assert [
            tuple(row)
            for row in conn.execute(
                "SELECT * FROM guide_operator_assignment_versions ORDER BY assignment_id,version_number"
            )
        ] == snapshots
        assert [
            tuple(row)
            for row in conn.execute("SELECT * FROM guide_operator_outbox ORDER BY id")
        ] == outbox
        assert (
            conn.execute(
                "SELECT count(*) FROM guide_operator_daily_projections"
            ).fetchone()[0]
            == 0
        )
    assert get_conflicting_dates(901, "2026-04-18") == ["2026-04-18"]


@pytest.mark.parametrize(
    "invalid", ["duplicate_id", "duplicate_date", "wrong_tour", "wrong_guide", "empty"]
)
def test_invalid_local_scope_is_rejected_without_partial_rows(invalid):
    fixture = seed()
    package = copy.deepcopy(fixture[2])
    if invalid == "duplicate_id":
        package["days"][1]["tour_day_id"] = package["days"][0]["tour_day_id"]
    elif invalid == "duplicate_date":
        package["days"][1]["date"] = package["days"][0]["date"]
    elif invalid == "wrong_tour":
        package["tour"]["id"] = str(uuid4())
    elif invalid == "wrong_guide":
        package["assignment"]["guide_os_id"] = str(uuid4())
    else:
        package["days"] = []
    run_write_with_retry(
        lambda conn: conn.execute(
            "UPDATE guide_operator_assignment_versions SET "
            "working_package_json=? WHERE assignment_id=?",
            (json.dumps(package), fixture[1]),
        )
    )
    with pytest.raises(service.AssignmentValidationError):
        apply(fixture)
    assert rows(fixture[1]) == []
    assert state(fixture[1])["status"] == "offered"


def test_concurrent_unrelated_accepts_cannot_both_take_a_date():
    first = seed()
    second = seed(guide=first[0], connection=first[3])
    barrier = Barrier(2)

    def accept(fixture):
        barrier.wait(timeout=5)
        try:
            return apply(fixture)["status"]
        except service.CalendarConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(accept, first)
        b = pool.submit(accept, second)
        assert sorted([a.result(timeout=15), b.result(timeout=15)]) == [
            "accepted",
            "conflict",
        ]
    assert sorted([len(rows(first[1])), len(rows(second[1]))]) == [0, 2]


def test_daily_calendar_day_detail_availability_and_distinct_work_days():
    from database.queries import get_tours_for_date
    from services.calendar_service import build_month_calendar
    from services.day_card_service import get_day_card_data
    from services.day_view_service import build_day_entries_for_month
    from services.guide_operator_discovery_service import (
        guide_availability_for_operator,
    )
    from services.reports_service import get_reports_summary
    from services.stats_service import get_stats_summary
    from services.tour_service import get_entry, list_entries
    from web_api.dto import entry_to_api

    first = seed()
    second = seed(
        guide=first[0],
        connection=first[3],
        tour_id=first[2]["tour"]["id"],
        dates=("2026-11-10",),
        role="local_guide",
    )
    apply(first)
    apply(second)
    entries = list_entries(501, "2026-11-10", "2026-11-12")
    assert len(entries) == 3
    assert {e["start_date"] for e in entries} == {"2026-11-10", "2026-11-12"}
    assert {e["guide_operator_assignment_id"] for e in entries} == {first[1], second[1]}
    assert len({e["id"] for e in entries}) == 3
    for entry in entries:
        assert entry["start_date"] == entry["end_date"]
        assert get_entry(501, entry["id"]) == entry
        assert get_entry(777, entry["id"]) is None
        payload = entry_to_api(entry)
        assert (
            payload["guideOperatorAssignmentId"]
            == entry["guide_operator_assignment_id"]
        )
        assert payload["income"] is None and payload["payment"] is None
        assert payload["guideOperatorVersion"] == 1
    assert len(get_tours_for_date(501, "2026-11-10")) == 2
    assert get_day_card_data(501, "2026-11-10")["kind"] == "multiple"
    assert get_day_card_data(501, "2026-11-11")["kind"] == "free"
    day_views = {d["date"]: d for d in build_day_entries_for_month(501, 2026, 11)}
    assert day_views["2026-11-10"]["status"] == "multiple"
    assert day_views["2026-11-11"]["status"] == "free"
    assert len(build_month_calendar(501, 2026, 11)["tours"]) == 3
    assert (
        guide_availability_for_operator(first[0], "2026-11-11", "2026-11-11")["status"]
        == "free"
    )
    assert (
        guide_availability_for_operator(first[0], "2026-11-10", "2026-11-12")["status"]
        == "partial"
    )
    report = get_reports_summary(501, "2026-11-01", "2026-11-30")
    assert report["work_days"] == 2
    assert report["income"] == report["paid_tours"] == report["unpaid_tours"] == 0
    assert get_stats_summary(501, 2026, 11)["working_days"] == 2
    apply(second, "cancel")
    remaining = list_entries(501, "2026-11-10", "2026-11-10")
    assert (
        len(remaining) == 1 and remaining[0]["guide_operator_assignment_id"] == first[1]
    )
    assert (
        guide_availability_for_operator(first[0], "2026-11-10", "2026-11-10")["status"]
        == "busy"
    )


def test_read_only_explicit_detail_pending_rejected_and_confirmed_scope():
    from services.tour_service import list_entries

    fixture = seed()
    apply(fixture)
    proposed = copy.deepcopy(fixture[2])
    proposed["days"][1]["date"] = "2026-11-14"
    proposed["assignment"]["end_date"] = "2026-11-14"
    pending(fixture, proposed)
    detail = service.build_assignment_detail_for_guide(fixture[0], fixture[1])
    assert detail["assignment"]["projection_tour_id"] is None
    assert detail["working_package"] == fixture[2]
    assert detail["pending_critical_version"]["working_package"] == proposed
    assert detail["pending_critical_version"]["conflict_dates"] == []
    entries = list_entries(501, "2026-11-10", "2026-11-14")
    assert {e["start_date"] for e in entries} == {"2026-11-10", "2026-11-12"}
    assert all(e["guide_operator_pending_critical"] for e in entries)
    register_user(777)
    with pytest.raises(service.AssignmentNotFoundError):
        service.build_assignment_detail_for_guide(get_guide_os_id(777), fixture[1])
    apply(fixture, "reject_critical", 2)
    assert not any(
        e["guide_operator_pending_critical"]
        for e in list_entries(501, "2026-11-10", "2026-11-14")
    )
    pending(fixture, proposed, 3)
    apply(fixture, "confirm_critical", 3)
    final = list_entries(501, "2026-11-10", "2026-11-14")
    assert {e["start_date"] for e in final} == {"2026-11-10", "2026-11-14"}
    assert all(e["guide_operator_version"] == 3 for e in final)


def test_explicit_reader_api_is_owner_scoped_and_projections_stay_protected():
    from tests.test_miniapp_guide_operator_assignments import (
        _auth_headers,
        api_request,
        response_json,
    )

    fixture = seed()
    apply(fixture)
    calendar = api_request(
        "GET",
        "/app/v1/entries?from=2026-11-10&to=2026-11-12",
        headers=_auth_headers(501),
    )
    assert calendar.status == 200
    calendar_entries = response_json(calendar)["data"]["entries"]
    assert len(calendar_entries) == 2
    for entry in calendar_entries:
        assert entry["guideOperatorAssignmentId"] == fixture[1]
        entry_path = f"/app/v1/entries/{entry['id']}"
        assert api_request("GET", entry_path, headers=_auth_headers(777)).status == 404
        assert api_request("GET", entry_path, headers=_auth_headers(501)).status == 200
        assert (
            api_request("DELETE", entry_path, headers=_auth_headers(501)).status == 404
        )
        assert api_request("GET", entry_path, headers=_auth_headers(501)).status == 200
    path = f"/app/v1/guide-operator/assignments/{fixture[1]}"
    response = api_request("GET", path, headers=_auth_headers(501))
    assert response.status == 200
    data = response_json(response)["data"]
    assert data["assignment"]["projectionTourId"] is None
    assert data["workingPackage"]["days"] == fixture[2]["days"]
    register_user(777)
    assert api_request("GET", path, headers=_auth_headers(777)).status == 404
    assert (
        api_request(
            "POST",
            path + "/accept",
            headers=_auth_headers(501),
            json={"decisionEventId": str(uuid4())},
        ).status
        == 200  # Existing acceptance is replayed; no second projection set.
    )
