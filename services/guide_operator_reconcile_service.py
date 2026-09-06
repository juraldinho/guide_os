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


def _projection_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    ensure_db_ready()
    conn = get_connection()
    try:
        projection_tour_id = row.get("projection_tour_id")
        exists = False
        start_date = None
        end_date = None
        version_number = None
        if projection_tour_id is not None:
            tour = conn.execute(
                """
                SELECT id, start_date, end_date, source, note
                FROM tours
                WHERE id = ?
                LIMIT 1
                """,
                (projection_tour_id,),
            ).fetchone()
            if tour is not None and dict(tour).get("source") == SOURCE_GUIDE_OPERATOR:
                note = dict(tour).get("note") or ""
                if note == f"go_assignment:{row['assignment_id']}":
                    exists = True
                    start_date = dict(tour).get("start_date")
                    end_date = dict(tour).get("end_date")
                    version_number = row.get("active_version_number")
        return {
            "exists": exists,
            "start_date": start_date,
            "end_date": end_date,
            "version_number": version_number,
        }
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
    return _assignment_snapshot(row)
