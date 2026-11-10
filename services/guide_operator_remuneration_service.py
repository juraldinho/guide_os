"""Local agreed USD history only. No HTTP, capability configuration or payment API."""

import sqlite3
from typing import Any, NoReturn

from services.guide_operator_assignment_service import AssignmentValidationError

MAX_USD = 9007199254740991


def _fail() -> NoReturn:
    raise AssignmentValidationError("Invalid or inconsistent agreed remuneration.")


def _money(value: object) -> None:
    if value is not None and (type(value) is not int or not 0 <= value <= MAX_USD):
        _fail()


def validate_remuneration(
    package: dict[str, Any], scope: list[tuple[str, str]]
) -> tuple[dict[str, Any], int, int] | None:
    """Use exactly the approved assignment.remuneration.v1 object, not a new DTO."""
    money = package.get("remuneration")
    if money is None:
        return None
    if (
        type(money) is not dict
        or set(money)
        != {"schema_version", "currency", "scale", "default_daily_usd", "days"}
        or money["schema_version"] != "assignment.remuneration.v1"
        or money["currency"] != "USD"
        or type(money["scale"]) is not int
        or money["scale"] != 0
        or type(money["days"]) is not list
        or not 1 <= len(money["days"]) <= 366
    ):
        _fail()
    _money(money["default_daily_usd"])
    ids = []
    total, unknown = 0, 0
    for row in money["days"]:
        if type(row) is not dict or set(row) != {"tour_day_id", "amount_usd", "source"}:
            _fail()
        if type(row["tour_day_id"]) is not str or row["source"] not in (
            "default",
            "manual",
        ):
            _fail()
        _money(row["amount_usd"])
        if (
            row["source"] == "default"
            and row["amount_usd"] != money["default_daily_usd"]
        ):
            _fail()
        ids.append(row["tour_day_id"])
        if row["amount_usd"] is None:
            unknown += 1
        else:
            total += row["amount_usd"]
        if total > MAX_USD:
            _fail()
    if len(ids) != len(set(ids)) or set(ids) != {key for key, _ in scope}:
        _fail()
    return money, total, unknown


def validate_effective(
    conn: sqlite3.Connection,
    assignment: dict[str, Any],
    package: dict[str, Any],
    scope: list[tuple[str, str]],
) -> None:
    """Existing agreement must match its active immutable snapshot before any change."""
    value = validate_remuneration(package, scope)
    assignment_id = assignment["assignment_id"]
    active = assignment["active_version_number"]
    rows = conn.execute(
        "SELECT e.*,d.calendar_date,d.amount_usd,d.source FROM guide_operator_remuneration_effective e "
        "JOIN guide_operator_remuneration_days d ON d.assignment_id=e.assignment_id "
        "AND d.tour_day_id=e.tour_day_id AND d.version_number=e.effective_version_number "
        "WHERE e.assignment_id=? AND e.state='active'",
        (assignment_id,),
    ).fetchall()
    if value is None:
        if (
            rows
            or conn.execute(
                "SELECT 1 FROM guide_operator_remuneration_versions WHERE assignment_id=?",
                (assignment_id,),
            ).fetchone()
        ):
            _fail()  # Never silently strip a previously agreed money object.
        return
    money, total, unknown = value
    header = conn.execute(
        "SELECT * FROM guide_operator_remuneration_versions WHERE assignment_id=? AND version_number=?",
        (assignment_id, active),
    ).fetchone()
    if (
        header is None
        or any(
            header[k] != assignment[k]
            for k in ("company_id", "guide_os_id", "operator_tour_id")
        )
        or (
            header["default_daily_usd"] != money["default_daily_usd"]
            or header["known_total_usd"] != total
            or header["unknown_day_count"] != unknown
        )
    ):
        _fail()
    expected = {r["tour_day_id"]: (r["amount_usd"], r["source"]) for r in money["days"]}
    if len(rows) != len(scope) or {r["tour_day_id"] for r in rows} != set(expected):
        _fail()
    dates = dict(scope)
    for row in rows:
        if (
            any(
                row[k] != assignment[k]
                for k in ("company_id", "guide_os_id", "operator_tour_id")
            )
            or row["effective_version_number"] != active
            or row["calendar_date"] != dates[row["tour_day_id"]]
            or (row["amount_usd"], row["source"]) != expected[row["tour_day_id"]]
        ):
            _fail()


def apply_agreement(
    conn: sqlite3.Connection,
    assignment: dict[str, Any],
    package: dict[str, Any],
    scope: list[tuple[str, str]],
    version: int,
    occurred_at: str,
) -> None:
    """Called only inside the assignment decision transaction, after scope validation."""
    value = validate_remuneration(package, scope)
    assignment_id = assignment["assignment_id"]
    if value is None:
        if conn.execute(
            "SELECT 1 FROM guide_operator_remuneration_versions WHERE assignment_id=?",
            (assignment_id,),
        ).fetchone():
            _fail()
        return
    money, total, unknown = value
    conn.execute(
        "INSERT INTO guide_operator_remuneration_versions(assignment_id,version_number,source_service,"
        "company_id,guide_os_id,operator_tour_id,schema_version,currency,scale,default_daily_usd,"
        "known_total_usd,unknown_day_count,agreed_at) VALUES (?,?,'guide_operator',?,?,?,?,?,?,?,?,?,?)",
        (
            assignment_id,
            version,
            assignment["company_id"],
            assignment["guide_os_id"],
            assignment["operator_tour_id"],
            money["schema_version"],
            money["currency"],
            money["scale"],
            money["default_daily_usd"],
            total,
            unknown,
            occurred_at,
        ),
    )
    conn.execute(
        "UPDATE guide_operator_remuneration_effective SET state='removed',effective_version_number=NULL,"
        "updated_at=? WHERE assignment_id=? AND state='active'",
        (occurred_at, assignment_id),
    )
    dates = dict(scope)
    for row in money["days"]:
        conn.execute(
            "INSERT INTO guide_operator_remuneration_days(assignment_id,tour_day_id,version_number,"
            "calendar_date,amount_usd,source) VALUES (?,?,?,?,?,?)",
            (
                assignment_id,
                row["tour_day_id"],
                version,
                dates[row["tour_day_id"]],
                row["amount_usd"],
                row["source"],
            ),
        )
        conn.execute(
            "INSERT INTO guide_operator_remuneration_effective(source_service,company_id,assignment_id,"
            "guide_os_id,operator_tour_id,tour_day_id,last_agreed_version_number,effective_version_number,state,updated_at) "
            "VALUES ('guide_operator',?,?,?,?,?,?,?,'active',?) "
            "ON CONFLICT(source_service,company_id,assignment_id,tour_day_id) DO UPDATE SET "
            "last_agreed_version_number=excluded.last_agreed_version_number,"
            "effective_version_number=excluded.effective_version_number,state='active',updated_at=excluded.updated_at",
            (
                assignment["company_id"],
                assignment_id,
                assignment["guide_os_id"],
                assignment["operator_tour_id"],
                row["tour_day_id"],
                version,
                version,
                occurred_at,
            ),
        )


def close_cancelled(
    conn: sqlite3.Connection, assignment_id: str, occurred_at: str
) -> None:
    # Includes previously removed days: all history remains, no debt/refund inference.
    conn.execute(
        "UPDATE guide_operator_remuneration_effective SET state='cancelled',"
        "effective_version_number=NULL,updated_at=? WHERE assignment_id=?",
        (occurred_at, assignment_id),
    )
