"""GO11A read-only Guide OS local projection snapshots for reconciliation.

Guide OS reports only local connection/assignment/calendar-projection state.
Never mutates state, enqueues events, or returns private calendar detail.
"""

from __future__ import annotations

from typing import Any

from database.db import ensure_db_ready, get_connection
from database.queries import (
    get_guide_operator_assignment_for_guide,
    get_guide_operator_connection_for_guide,
)
from utils.constants import SOURCE_GUIDE_OPERATOR
from utils.guide_os_identity import validate_guide_os_id


RECONCILE_SCHEMA_VERSION = "reconcile.snapshot.v1"
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 50
MAX_ID_FILTER = 50

CONNECTION_LOCAL_FIELDS = (
    "connection_id",
    "guide_os_id",
    "company_id",
    "status",
    "invitation_expires_at",
    "decided_at",
    "disconnected_at",
)
ASSIGNMENT_LOCAL_FIELDS = (
    "assignment_id",
    "guide_os_id",
    "guide_connection_id",
    "company_id",
    "status",
    "active_version_number",
    "pending_critical_version_number",
    "start_date",
    "end_date",
    "cancelled_at",
    "calendar_projection",
)


class GuideOperatorReconcileValidationError(Exception):
    """Invalid reconcile query."""


class GuideOperatorReconcileNotFoundError(Exception):
    """Opaque missing reconcile resource."""


def parse_page_limit(raw: object) -> int:
    if raw is None or raw == "":
        return DEFAULT_PAGE_LIMIT
    try:
        value = int(str(raw))
    except (TypeError, ValueError) as exc:
        raise GuideOperatorReconcileValidationError("limit") from exc
    if value < 1 or value > MAX_PAGE_LIMIT:
        raise GuideOperatorReconcileValidationError("limit")
    return value


def parse_id_filter(raw_values: list[str] | None) -> list[str] | None:
    if raw_values is None:
        return None
    if len(raw_values) == 0 or len(raw_values) > MAX_ID_FILTER:
        raise GuideOperatorReconcileValidationError("ids")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        if not isinstance(item, str) or not item or item != item.strip() or len(item) > 128:
            raise GuideOperatorReconcileValidationError("ids")
        if item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned


def _require_guide(guide_os_id: object) -> str:
    try:
        return validate_guide_os_id(guide_os_id)
    except Exception as exc:
        raise GuideOperatorReconcileValidationError("guide_os_id") from exc


def _connection_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": RECONCILE_SCHEMA_VERSION,
        "connection_id": row["connection_id"],
        "guide_os_id": row["guide_os_id"],
        "company_id": row["company_id"],
        "status": row["status"],
        "invitation_expires_at": row.get("invitation_expires_at"),
        "decided_at": row.get("decided_at"),
        "disconnected_at": row.get("disconnected_at"),
    }


def list_protected_projection_tours(conn, assignment_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, start_date, end_date, source, note, title, city,
               day_locations_json, user_id, status, entry_type, income,
               payment_status, tour_group_id
        FROM tours
        WHERE source = ? AND note = ?
        ORDER BY id ASC
        """,
        (SOURCE_GUIDE_OPERATOR, f"go_assignment:{assignment_id}"),
    ).fetchall()
    return [dict(row) for row in rows]


def projection_fingerprint(
    row: dict[str, Any], tours: list[dict[str, Any]]
) -> dict[str, Any]:
    if row.get("projection_mode", "legacy_range") != "legacy_range":
        # Also used by legacy repair before it can mutate anything.
        raise GuideOperatorReconcileValidationError("unsupported_projection_mode")
    chosen: dict[str, Any] | None = None
    projection_tour_id = row.get("projection_tour_id")
    if projection_tour_id is not None:
        for tour in tours:
            if tour.get("id") == projection_tour_id:
                chosen = tour
                break
    if chosen is None and len(tours) == 1:
        chosen = tours[0]
    if chosen is None:
        return {
            "exists": False,
            "start_date": None,
            "end_date": None,
            "version_number": None,
        }
    return {
        "exists": True,
        "start_date": chosen.get("start_date"),
        "end_date": chosen.get("end_date"),
        "version_number": row.get("active_version_number"),
    }


def _projection_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    ensure_db_ready()
    conn = get_connection()
    try:
        tours = list_protected_projection_tours(conn, row["assignment_id"])
        return projection_fingerprint(row, tours)
    finally:
        conn.close()


def _assignment_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": RECONCILE_SCHEMA_VERSION,
        "assignment_id": row["assignment_id"],
        "guide_os_id": row["guide_os_id"],
        "guide_connection_id": row["guide_connection_id"],
        "company_id": row["company_id"],
        "status": row["status"],
        "active_version_number": row.get("active_version_number"),
        "pending_critical_version_number": row.get("pending_critical_version_number"),
        "start_date": row.get("start_date"),
        "end_date": row.get("end_date"),
        "cancelled_at": row.get("cancelled_at"),
        "calendar_projection": _projection_snapshot(row),
    }


def list_local_connections(
    guide_os_id: object,
    *,
    limit: object = None,
    cursor: str | None = None,
    ids: list[str] | None = None,
) -> dict[str, Any]:
    identity = _require_guide(guide_os_id)
    page_limit = parse_page_limit(limit)
    id_filter = parse_id_filter(ids)
    ensure_db_ready()
    conn = get_connection()
    try:
        params: list[Any] = [identity]
        where = ["guide_os_id = ?"]
        if id_filter is not None:
            placeholders = ",".join("?" for _ in id_filter)
            where.append(f"connection_id IN ({placeholders})")
            params.extend(id_filter)
        if cursor:
            where.append("connection_id > ?")
            params.append(cursor)
        sql = f"""
            SELECT *
            FROM guide_operator_connections
            WHERE {" AND ".join(where)}
            ORDER BY connection_id ASC
            LIMIT ?
        """
        params.append(page_limit + 1)
        rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
    page = rows[:page_limit]
    next_cursor = page[-1]["connection_id"] if len(rows) > page_limit else None
    return {
        "schema_version": RECONCILE_SCHEMA_VERSION,
        "guide_os_id": identity,
        "resource": "connections",
        "items": [_connection_snapshot(row) for row in page],
        "next_cursor": next_cursor,
        "local_fields": list(CONNECTION_LOCAL_FIELDS),
        "authoritative_side": "guide_os_local_projection",
    }


def get_local_connection(guide_os_id: object, connection_id: str) -> dict[str, Any]:
    identity = _require_guide(guide_os_id)
    row = get_guide_operator_connection_for_guide(identity, connection_id)
    if row is None:
        raise GuideOperatorReconcileNotFoundError("missing")
    return _connection_snapshot(row)


def list_local_assignments(
    guide_os_id: object,
    *,
    limit: object = None,
    cursor: str | None = None,
    ids: list[str] | None = None,
) -> dict[str, Any]:
    identity = _require_guide(guide_os_id)
    page_limit = parse_page_limit(limit)
    id_filter = parse_id_filter(ids)
    ensure_db_ready()
    conn = get_connection()
    try:
        params: list[Any] = [identity]
        where = ["guide_os_id = ?"]
        if id_filter is not None:
            placeholders = ",".join("?" for _ in id_filter)
            where.append(f"assignment_id IN ({placeholders})")
            params.extend(id_filter)
        if cursor:
            where.append("assignment_id > ?")
            params.append(cursor)
        sql = f"""
            SELECT *
            FROM guide_operator_assignments
            WHERE {" AND ".join(where)}
            ORDER BY assignment_id ASC
            LIMIT ?
        """
        params.append(page_limit + 1)
        rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
    page = rows[:page_limit]
    next_cursor = page[-1]["assignment_id"] if len(rows) > page_limit else None
    return {
        "schema_version": RECONCILE_SCHEMA_VERSION,
        "guide_os_id": identity,
        "resource": "assignments",
        "items": [_assignment_snapshot(row) for row in page],
        "next_cursor": next_cursor,
        "local_fields": list(ASSIGNMENT_LOCAL_FIELDS),
        "authoritative_side": "guide_os_local_projection",
    }


def get_local_assignment(guide_os_id: object, assignment_id: str) -> dict[str, Any]:
    identity = _require_guide(guide_os_id)
    row = get_guide_operator_assignment_for_guide(identity, assignment_id)
    if row is None:
        raise GuideOperatorReconcileNotFoundError("missing")
    snapshot = _assignment_snapshot(row)
    conn = get_connection()
    try:
        notifications = conn.execute(
            """SELECT source_event_id, notification_type, version_number, delivery_status,
                      attempt_count, last_error_code
               FROM guide_operator_guide_notifications
               WHERE guide_os_id = ? AND assignment_id = ?
               ORDER BY id DESC LIMIT 50""", (identity, assignment_id),
        ).fetchall()
        snapshot["telegram_notifications"] = [dict(item) for item in notifications]
    finally:
        conn.close()
    return snapshot


def _assignment_snapshot_v2(conn, row: dict[str, Any]) -> dict[str, Any]:
    import json
    from services.reconciliation_v2_contract import IDENTITY, seal, snapshot_base

    versions = []
    for version in conn.execute(
        "SELECT version_number, working_package_json FROM guide_operator_assignment_versions "
        "WHERE assignment_id=? ORDER BY version_number",
        (row["assignment_id"],),
    ):
        try:
            package = json.loads(version["working_package_json"])
        except (ValueError, TypeError):
            package = None
        versions.append({"version_number": version["version_number"], "package": package})
    state = {**row, "source_service": SOURCE_GUIDE_OPERATOR}
    result = snapshot_base(state, versions, row["projection_mode"])
    links = [
        dict(link)
        for link in conn.execute(
            "SELECT * FROM guide_operator_daily_projections WHERE assignment_id=?",
            (row["assignment_id"],),
        )
    ]
    owner = conn.execute(
        "SELECT user_id FROM users WHERE guide_os_id=?", (row["guide_os_id"],)
    ).fetchone()
    owner_id = owner["user_id"] if owner else None
    ids = [link["projection_tour_id"] for link in links]
    if row["projection_tour_id"] is not None:
        ids.append(row["projection_tour_id"])
    placeholders = ",".join("?" for _ in ids) or "NULL"
    tours = {
        tour["id"]: dict(tour)
        for tour in conn.execute(
            f"SELECT id,user_id,start_date,end_date,source,note,entry_type,tour_group_id "
            f"FROM tours WHERE (user_id=? AND source=? AND note=?) OR id IN ({placeholders}) LIMIT 1001",
            (owner_id, SOURCE_GUIDE_OPERATOR, f"go_assignment:{row['assignment_id']}", *ids),
        )
    }
    link_by_id: dict[int, list[dict[str, Any]]] = {}
    for link in links:
        link_by_id.setdefault(link["projection_tour_id"], []).append(link)
    # Preserve duplicate link evidence even if an unsafe legacy database lost uniqueness.
    evidence = [(key, link) for key in sorted(set(tours) | set(ids))
                for link in link_by_id.get(key, [None])]
    for projection_id, link in evidence:
        tour = tours.get(projection_id)
        binding = {key: (link[key] if link else state.get(key)) for key in IDENTITY}
        issues = []
        visible = tour is not None and tour["user_id"] == owner_id
        if tour is None:
            issues.append("missing_tour")
        elif not visible:
            issues.append("owner_mismatch")
        if visible:
            binding["source_service"] = tour["source"]
            note = tour["note"] or ""
            binding["assignment_id"] = (
                note.removeprefix("go_assignment:") if note.startswith("go_assignment:") else None
            )
            if tour["source"] != SOURCE_GUIDE_OPERATOR or tour["entry_type"] != "tour":
                issues.append("not_protected")
        if any(binding[key] != state.get(key) for key in IDENTITY):
            issues.append("binding_mismatch")
        if row["projection_mode"] == "explicit_days":
            if link is None:
                issues.append("unlinked")
            elif visible:
                if tour["tour_group_id"] != f"{row['assignment_id']}:{link['tour_day_id']}":
                    issues.append("group_mismatch")
                if link["calendar_date"] != tour["start_date"]:
                    issues.append("date_mismatch")
            if visible and tour["start_date"] != tour["end_date"]:
                issues.append("not_daily")
        result["projections"].append(
            {
                "tour_day_id": link["tour_day_id"] if link else None,
                "date": tour["start_date"] if visible else None,
                "end_date": tour["end_date"] if visible else None,
                "projection_tour_id": projection_id,
                "active_version_number": link["active_version_number"]
                if link
                else (
                    row["active_version_number"]
                    if row["projection_mode"] == "legacy_range"
                    else None
                ),
                "binding": binding,
                "issues": issues,
            }
        )
    return seal(result)


def list_local_assignments_v2(
    guide_os_id: object,
    *,
    limit: object = None,
    cursor: str | None = None,
    ids: list[str] | None = None,
) -> dict[str, Any]:
    from services.reconciliation_v2_contract import SCHEMA, SnapshotContractError

    identity = _require_guide(guide_os_id)
    page_limit = parse_page_limit(limit)
    id_filter = parse_id_filter(ids)
    if cursor is not None and (not cursor or len(cursor) > 128 or cursor != cursor.strip()):
        raise GuideOperatorReconcileValidationError("cursor")
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        params: list[Any] = [identity]
        where = ["guide_os_id=?"]
        if id_filter is not None:
            where.append("assignment_id IN (" + ",".join("?" for _ in id_filter) + ")")
            params.extend(id_filter)
        if cursor is not None:
            where.append("assignment_id>?")
            params.append(cursor)
        rows = conn.execute(
            "SELECT * FROM guide_operator_assignments WHERE "
            + " AND ".join(where)
            + " ORDER BY assignment_id LIMIT ?",
            (*params, page_limit + 1),
        ).fetchall()
        items = [_assignment_snapshot_v2(conn, dict(row)) for row in rows[:page_limit]]
        return {
            "schema_version": SCHEMA,
            "guide_os_id": identity,
            "resource": "assignments",
            "items": items,
            "next_cursor": rows[page_limit - 1]["assignment_id"]
            if len(rows) > page_limit
            else None,
            "authoritative_side": "guide_os_local_projection",
        }
    except SnapshotContractError as exc:
        raise GuideOperatorReconcileValidationError(str(exc)) from exc
    finally:
        conn.close()


def get_local_assignment_v2(guide_os_id: object, assignment_id: str) -> dict[str, Any]:
    page = list_local_assignments_v2(guide_os_id, ids=[assignment_id], limit=1)
    if not page["items"]:
        raise GuideOperatorReconcileNotFoundError("missing")
    return page["items"][0]
