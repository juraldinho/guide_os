"""Read-only whole-set snapshots: isolated databases, no v2 intake or repair."""

import copy
from uuid import uuid4

import pytest
from database.db import get_db_connection, run_write_with_retry
from services.guide_operator_reconcile_service import (
    GuideOperatorReconcileValidationError,
    get_local_assignment_v2,
    list_local_assignments,
)
from services.guide_operator_service_auth_settings import (
    reset_guide_operator_service_auth_for_tests,
)
from services.guide_operator_service_jwt import SCOPE_CONNECTIONS_WRITE, SCOPE_OPERATOR_RECONCILE
from tests.test_guide_operator_daily_projections import apply, pending, rows, seed
from tests.test_guide_operator_reconcile_http import (
    api_get,
    mint_token,
    response_json,
)
from tests.test_guide_operator_reconcile_http import (
    auth_settings as auth_settings,
)
from tests.test_guide_operator_reconcile_http import (
    clock as clock,
)
from tests.test_guide_operator_reconcile_http import (
    keys as keys,
)
from tests.test_guide_operator_reconcile_http import (
    outbound_private as outbound_private,
)

from services.reconciliation_v2_contract import SCHEMA, validate_snapshot


@pytest.fixture(autouse=True)
def reset_auth():
    reset_guide_operator_service_auth_for_tests()
    yield
    reset_guide_operator_service_auth_for_tests()


def dump():
    with get_db_connection() as conn:
        return tuple(conn.iterdump())


def remove_projection(assignment_id, projection):
    def operation(conn):
        conn.execute(
            "DELETE FROM guide_operator_daily_projections WHERE projection_tour_id=?", (projection,)
        )
        conn.execute(
            "INSERT INTO go_operator_projection_release(tour_id) VALUES (?)", (projection,)
        )
        conn.execute("DELETE FROM tours WHERE id=?", (projection,))
        conn.execute("DELETE FROM go_operator_projection_release WHERE tour_id=?", (projection,))

    run_write_with_retry(operation)


def stray(fixture, date="2026-11-11"):
    def operation(conn):
        conn.execute(
            "INSERT INTO tours(user_id,company,city,start_date,end_date,status,payment_status,"
            "note,entry_type,tour_group_id,source,title) "
            "VALUES (501,'Private company text','Private city',?,?,'confirmed','unpaid',"
            "?,'tour',?,'guide_operator','Stray')",
            (date, date, "go_assignment:" + fixture[1], str(uuid4())),
        )

    run_write_with_retry(operation)


def test_sparse_pending_roles_and_read_only():
    a = seed()
    apply(a)
    b = seed(guide=a[0], connection=a[3], tour_id=a[2]["tour"]["id"], role="local_guide")
    apply(b)
    package = copy.deepcopy(a[2])
    package["days"][1]["date"] = "2026-11-14"
    package["assignment"]["end_date"] = "2026-11-14"
    pending(a, package)
    before = dump()
    snapshot = get_local_assignment_v2(a[0], a[1])
    assert snapshot["schema_version"] == SCHEMA
    assert snapshot["state_issues"] == []
    assert [day["date"] for day in snapshot["active_days"]] == ["2026-11-10", "2026-11-12"]
    assert [
        row["date"] for row in sorted(snapshot["projections"], key=lambda row: row["date"])
    ] == ["2026-11-10", "2026-11-12"]
    assert snapshot["pending_critical_version_number"] == 2
    assert validate_snapshot(snapshot) == snapshot
    assert get_local_assignment_v2(b[0], b[1])["role"] == "local_guide"
    assert dump() == before
    with pytest.raises(GuideOperatorReconcileValidationError):
        list_local_assignments(a[0])  # V1 never collapses explicit days into a range.


def test_missing_stray_cancel_and_fingerprint():
    f = seed()
    apply(f)
    before = get_local_assignment_v2(f[0], f[1])
    remove_projection(f[1], rows(f[1])[1]["projection_tour_id"])
    stray(f)
    after = get_local_assignment_v2(f[0], f[1])
    assert before["active_days"] == after["active_days"]
    assert before["fingerprint"] != after["fingerprint"]
    assert {p["date"] for p in after["projections"]} == {"2026-11-10", "2026-11-11"}
    assert any("unlinked" in p["issues"] for p in after["projections"])
    # Cancellation fixture prepared through the existing private writer on a clean assignment.
    g = seed(guide=f[0], connection=f[3], dates=("2026-11-20",))
    apply(g)
    apply(g, "cancel")
    stray(g, "2026-11-20")
    cancelled = get_local_assignment_v2(g[0], g[1])
    assert cancelled["cancelled"]
    assert len(cancelled["projections"]) == 1
    assert (
        cancelled["active_days"][0]["date"] == "2026-11-20"
    )  # retained agreement, no active occupancy


def test_gaps_are_reported_and_pending_is_not_substituted():
    f = seed()
    apply(f)
    package = copy.deepcopy(f[2])
    pending(f, package, 3)  # Deliberately corrupt isolated fixture: missing immutable version 2.
    value = get_local_assignment_v2(f[0], f[1])
    assert "version_gap" in value["state_issues"]
    assert value["active_days"] == sorted(
        f[2]["days"], key=lambda day: (day["date"], day["tour_day_id"])
    )


def test_http_auth_isolation_pagination_and_v1_repair_gate(auth_settings, clock, keys):
    f = seed()
    apply(f)
    seed(guide=f[0], connection=f[3], role="local_guide")
    path = f"/integration/v2/reconcile/guides/{f[0]}/assignments"

    def request(suffix="", scope=SCOPE_OPERATOR_RECONCILE, authenticated=True):
        token = mint_token(keys[0], scope=scope) if authenticated else None
        return api_get(auth_settings, clock, path + suffix, token=token)

    assert request(authenticated=False).status == 401
    assert request(scope=SCOPE_CONNECTIONS_WRITE).status == 401
    assert request("?limit=51").status == 400
    first = request("?limit=1")
    assert first.status == 200
    page = response_json(first)["data"]
    assert page["schema_version"] == SCHEMA and len(page["items"]) == 1
    next_page = response_json(request("?limit=1&cursor=" + page["next_cursor"]))["data"]
    assert next_page["items"][0]["assignment_id"] != page["items"][0]["assignment_id"]
    assert next_page["next_cursor"] is None
    other = str(uuid4())
    token = mint_token(keys[0], scope=SCOPE_OPERATOR_RECONCILE)
    other_response = api_get(
        auth_settings,
        clock,
        f"/integration/v2/reconcile/guides/{other}/assignments/{f[1]}",
        token=token,
    )
    assert other_response.status == 404
    snapshot = request("/" + f[1])
    assert snapshot.status == 200
    encoded = snapshot._body_text
    for forbidden in ("Private company text", "working_package", "income", "phone", "payment"):
        assert forbidden not in encoded


def test_misbound_foreign_calendar_row_is_redacted_and_legacy_repair_stays_closed():
    from database.queries import register_user
    from services.guide_operator_reconcile_repair_service import repair_local_projection
    from services.tour_service import save_tour

    f = seed()
    apply(f)
    register_user(777)
    save_tour(
        777, "Foreign private title", "Foreign private city", "2027-01-10", "confirmed", income=999
    )

    def corrupt(conn):
        foreign = conn.execute("SELECT id FROM tours WHERE user_id=777").fetchone()[0]
        conn.execute(
            "UPDATE guide_operator_daily_projections SET projection_tour_id=? WHERE tour_day_id=?",
            (foreign, f[2]["days"][1]["tour_day_id"]),
        )

    run_write_with_retry(corrupt)
    value = get_local_assignment_v2(f[0], f[1])
    foreign = next(p for p in value["projections"] if "owner_mismatch" in p["issues"])
    assert foreign["date"] is None and foreign["end_date"] is None
    import json

    encoded = json.dumps(value)
    for private in ("2027-01-10", "Foreign private", "999"):
        assert private not in encoded
    before = dump()
    with pytest.raises(GuideOperatorReconcileValidationError):
        repair_local_projection(
            f[0],
            f[1],
            repair_request_id=str(uuid4()),
            expected_status="accepted",
            expected_active_version_number=1,
            expected_projection=dict(
                exists=False, start_date=None, end_date=None, version_number=None
            ),
        )
    assert dump() == before
