"""GO11B2B safe local Guide Operator calendar projection repair.

Derives the desired projection only from Guide OS local active version and
retained guide-authored accept decision. Never accepts replacement calendar
content from Guide Operator. Does not change assignment/version/decision
state machines, consent, or personal tours.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from database.db import ensure_db_ready, get_connection, run_write_with_retry
from database.queries import get_user_id_by_guide_os_id
from services.guide_operator_assignment_service import (
    _calendar_conflicts,
    _canonical_hash,
    _day_locations_json_from_package,
    _load_working_package_json,
    _projection_labels,
    _utc_now,
)
from services.guide_operator_reconcile_service import (
    list_protected_projection_tours,
    projection_fingerprint,
)
from utils.constants import (
    ENTRY_TYPE_TOUR,
    PAYMENT_UNPAID,
    SOURCE_GUIDE_OPERATOR,
    STATUS_CONFIRMED,
)
from utils.guide_os_identity import validate_guide_os_id

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REPAIR_PROJECTION_KEYS = frozenset(
    {"exists", "start_date", "end_date", "version_number"}
)
ALLOWED_EXPECTED_STATUSES = frozenset({"accepted", "cancelled"})

# Test-only hook executed after writes, before commit.
_REPAIR_FAILURE_HOOK: Callable[[], None] | None = None


class GuideOperatorProjectionRepairError(Exception):
    """Base fail-closed repair error."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProjectionRepairValidationError(GuideOperatorProjectionRepairError):
    pass


class ProjectionRepairNotFoundError(GuideOperatorProjectionRepairError):
    pass


@dataclass(frozen=True)
class ProjectionRepairResult:
    status: str
    repair_request_id: str
    replayed: bool
    action: str = "none"


def get_projection_repair_inbox(repair_request_id: str) -> dict[str, Any] | None:
    ensure_db_ready()
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT *
            FROM guide_operator_projection_repair_inbox
            WHERE repair_request_id = ?
            LIMIT 1
            """,
            (repair_request_id,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row is not None else None


def list_projection_repair_audits(assignment_id: str) -> list[dict[str, Any]]:
    ensure_db_ready()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM guide_operator_projection_repair_audits
            WHERE assignment_id = ?
            ORDER BY id ASC
            """,
            (assignment_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def repair_local_projection(
    guide_os_id: object,
    assignment_id: object,
    *,
    repair_request_id: object,
    expected_status: object,
    expected_active_version_number: object,
    expected_projection: object,
) -> ProjectionRepairResult:
    identity = _require_guide(guide_os_id)
    assignment_key = _require_assignment_id(assignment_id)
    request_id = _require_uuid4(repair_request_id, "repair_request_id")
    status_expected = _require_expected_status(expected_status)
    version_expected = _require_version_number(expected_active_version_number)
    observed = _require_projection_fingerprint(expected_projection)
    payload_hash = _canonical_hash(
        {
            "assignment_id": assignment_key,
            "guide_os_id": identity,
            "expected_status": status_expected,
            "expected_active_version_number": version_expected,
            "expected_projection": observed,
        }
    )

    def operation(conn):
        prior = conn.execute(
            """
            SELECT *
            FROM guide_operator_projection_repair_inbox
            WHERE repair_request_id = ?
            LIMIT 1
            """,
            (request_id,),
        ).fetchone()
        if prior is not None:
            prior_row = dict(prior)
            if prior_row["payload_hash"] != payload_hash:
                return ProjectionRepairResult(
                    status="conflict",
                    repair_request_id=request_id,
                    replayed=False,
                    action="none",
                )
            stored_status = prior_row["result_status"]
            replay_status = "replayed" if stored_status == "applied" else stored_status
            return ProjectionRepairResult(
                status=replay_status,
                repair_request_id=request_id,
                replayed=True,
                action=prior_row["action"],
            )

        locked = conn.execute(
            """
            SELECT *
            FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (assignment_key, identity),
        ).fetchone()
        if locked is None:
            raise ProjectionRepairNotFoundError("missing")
        assignment = dict(locked)
        tours = list_protected_projection_tours(conn, assignment_key)
        current_projection = projection_fingerprint(assignment, tours)
        current_status = assignment["status"]
        current_version = int(assignment["active_version_number"])

        if (
            current_status != status_expected
            or current_version != version_expected
            or current_projection != observed
        ):
            return _persist_terminal(
                conn,
                request_id=request_id,
                assignment_id=assignment_key,
                guide_os_id=identity,
                payload_hash=payload_hash,
                result_status="no-op",
                action="none",
                audit=False,
            )

        if current_status == "accepted":
            result = _repair_accepted(
                conn,
                assignment=assignment,
                tours=tours,
                request_id=request_id,
                payload_hash=payload_hash,
            )
        elif current_status == "cancelled":
            result = _repair_cancelled(
                conn,
                assignment=assignment,
                tours=tours,
                request_id=request_id,
                payload_hash=payload_hash,
            )
        else:
            result = _persist_terminal(
                conn,
                request_id=request_id,
                assignment_id=assignment_key,
                guide_os_id=identity,
                payload_hash=payload_hash,
                result_status="no-op",
                action="none",
                audit=False,
            )

        if _REPAIR_FAILURE_HOOK is not None:
            _REPAIR_FAILURE_HOOK()
        return result

    return run_write_with_retry(operation)


def _repair_accepted(
    conn,
    *,
    assignment: dict[str, Any],
    tours: list[dict[str, Any]],
    request_id: str,
    payload_hash: str,
) -> ProjectionRepairResult:
    assignment_id = assignment["assignment_id"]
    identity = assignment["guide_os_id"]
    if assignment.get("pending_critical_version_number") is not None:
        return _persist_terminal(
            conn,
            request_id=request_id,
            assignment_id=assignment_id,
            guide_os_id=identity,
            payload_hash=payload_hash,
            result_status="no-op",
            action="none",
            audit=False,
        )
    decision = conn.execute(
        """
        SELECT decision_type
        FROM guide_operator_assignment_decisions
        WHERE assignment_id = ? AND guide_os_id = ?
        LIMIT 1
        """,
        (assignment_id, identity),
    ).fetchone()
    if decision is None or dict(decision).get("decision_type") != "accept":
        return _persist_terminal(
            conn,
            request_id=request_id,
            assignment_id=assignment_id,
            guide_os_id=identity,
            payload_hash=payload_hash,
            result_status="no-op",
            action="none",
            audit=False,
        )
    desired = _desired_projection_from_local(conn, assignment)
    if desired is None:
        return _persist_terminal(
            conn,
            request_id=request_id,
            assignment_id=assignment_id,
            guide_os_id=identity,
            payload_hash=payload_hash,
            result_status="no-op",
            action="none",
            audit=False,
        )
    if len(tours) > 1:
        return _persist_terminal(
            conn,
            request_id=request_id,
            assignment_id=assignment_id,
            guide_os_id=identity,
            payload_hash=payload_hash,
            result_status="no-op",
            action="none",
            audit=False,
        )

    user_id = get_user_id_by_guide_os_id(identity)
    if user_id is None:
        raise ProjectionRepairValidationError("Unknown guide_os_id.")

    if not tours:
        conflicts = _calendar_conflicts(
            user_id, desired["start_date"], desired["end_date"]
        )
        if conflicts:
            return _persist_terminal(
                conn,
                request_id=request_id,
                assignment_id=assignment_id,
                guide_os_id=identity,
                payload_hash=payload_hash,
                result_status="conflict",
                action="none",
                audit=False,
            )
        _insert_protected_projection(conn, assignment, desired, user_id)
        return _persist_terminal(
            conn,
            request_id=request_id,
            assignment_id=assignment_id,
            guide_os_id=identity,
            payload_hash=payload_hash,
            result_status="applied",
            action="recreate",
            audit=True,
        )

    current = tours[0]
    if (
        current.get("start_date") == desired["start_date"]
        and current.get("end_date") == desired["end_date"]
        and current.get("title") == desired["title"]
        and current.get("city") == desired["city"]
        and current.get("day_locations_json") == desired["day_locations_json"]
        and assignment.get("projection_tour_id") == current["id"]
    ):
        return _persist_terminal(
            conn,
            request_id=request_id,
            assignment_id=assignment_id,
            guide_os_id=identity,
            payload_hash=payload_hash,
            result_status="no-op",
            action="none",
            audit=False,
        )

    conflicts = _calendar_conflicts(
        user_id,
        desired["start_date"],
        desired["end_date"],
        exclude_tour_id=int(current["id"]),
    )
    if conflicts:
        return _persist_terminal(
            conn,
            request_id=request_id,
            assignment_id=assignment_id,
            guide_os_id=identity,
            payload_hash=payload_hash,
            result_status="conflict",
            action="none",
            audit=False,
        )
    _update_protected_projection(conn, assignment, current, desired)
    return _persist_terminal(
        conn,
        request_id=request_id,
        assignment_id=assignment_id,
        guide_os_id=identity,
        payload_hash=payload_hash,
        result_status="applied",
        action="repair_mismatch",
        audit=True,
    )


def _repair_cancelled(
    conn,
    *,
    assignment: dict[str, Any],
    tours: list[dict[str, Any]],
    request_id: str,
    payload_hash: str,
) -> ProjectionRepairResult:
    assignment_id = assignment["assignment_id"]
    identity = assignment["guide_os_id"]
    if not tours:
        return _persist_terminal(
            conn,
            request_id=request_id,
            assignment_id=assignment_id,
            guide_os_id=identity,
            payload_hash=payload_hash,
            result_status="no-op",
            action="none",
            audit=False,
        )
    conn.execute(
        """
        UPDATE guide_operator_assignments
        SET projection_tour_id = NULL
        WHERE assignment_id = ? AND guide_os_id = ? AND status = 'cancelled'
        """,
        (assignment_id, identity),
    )
    for tour in tours:
        _release_protected_projection(conn, int(tour["id"]))
    remaining = list_protected_projection_tours(conn, assignment_id)
    if remaining:
        raise ProjectionRepairValidationError(
            "Cancelled repair must release protected projections."
        )
    return _persist_terminal(
        conn,
        request_id=request_id,
        assignment_id=assignment_id,
        guide_os_id=identity,
        payload_hash=payload_hash,
        result_status="applied",
        action="release_stray",
        audit=True,
    )


def _desired_projection_from_local(
    conn, assignment: dict[str, Any]
) -> dict[str, Any] | None:
    version_number = int(assignment["active_version_number"])
    version = conn.execute(
        """
        SELECT working_package_json
        FROM guide_operator_assignment_versions
        WHERE assignment_id = ? AND version_number = ?
        LIMIT 1
        """,
        (assignment["assignment_id"], version_number),
    ).fetchone()
    if version is None:
        return None
    try:
        working_package = _load_working_package_json(version["working_package_json"])
    except Exception:
        return None
    package_assignment = working_package.get("assignment")
    if not isinstance(package_assignment, dict):
        return None
    if (
        package_assignment.get("start_date") != assignment["start_date"]
        or package_assignment.get("end_date") != assignment["end_date"]
    ):
        return None
    title, city = _projection_labels(assignment, working_package)
    return {
        "start_date": assignment["start_date"],
        "end_date": assignment["end_date"],
        "title": title,
        "city": city,
        "day_locations_json": _day_locations_json_from_package(working_package),
    }


def _insert_protected_projection(
    conn,
    assignment: dict[str, Any],
    desired: dict[str, Any],
    user_id: int,
) -> None:
    assignment_id = assignment["assignment_id"]
    cursor = conn.execute(
        """
        INSERT INTO tours (
            user_id, company, city, start_date, end_date, status,
            income, payment_status, note, entry_type, tour_group_id,
            title, start_time, end_time, source, day_locations_json
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
        """,
        (
            user_id,
            assignment["company_name"],
            desired["city"],
            desired["start_date"],
            desired["end_date"],
            STATUS_CONFIRMED,
            PAYMENT_UNPAID,
            f"go_assignment:{assignment_id}",
            ENTRY_TYPE_TOUR,
            assignment_id,
            desired["title"],
            SOURCE_GUIDE_OPERATOR,
            desired["day_locations_json"],
        ),
    )
    projection_tour_id = int(cursor.lastrowid)
    count = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM tours
        WHERE source = ? AND note = ?
        """,
        (SOURCE_GUIDE_OPERATOR, f"go_assignment:{assignment_id}"),
    ).fetchone()["cnt"]
    if int(count) != 1:
        raise ProjectionRepairValidationError(
            "Repair must create exactly one calendar projection."
        )
    conn.execute(
        """
        UPDATE guide_operator_assignments
        SET projection_tour_id = ?
        WHERE assignment_id = ? AND guide_os_id = ? AND status = 'accepted'
        """,
        (projection_tour_id, assignment_id, assignment["guide_os_id"]),
    )
    updated = conn.execute(
        """
        SELECT projection_tour_id, status, active_version_number,
               pending_critical_version_number
        FROM guide_operator_assignments
        WHERE assignment_id = ?
        LIMIT 1
        """,
        (assignment_id,),
    ).fetchone()
    if (
        updated is None
        or updated["status"] != "accepted"
        or updated["projection_tour_id"] != projection_tour_id
        or int(updated["active_version_number"]) != int(assignment["active_version_number"])
        or updated["pending_critical_version_number"]
        != assignment.get("pending_critical_version_number")
    ):
        raise ProjectionRepairValidationError(
            "Repair must not change assignment status or version."
        )


def _update_protected_projection(
    conn,
    assignment: dict[str, Any],
    current: dict[str, Any],
    desired: dict[str, Any],
) -> None:
    tour_id = int(current["id"])
    assignment_id = assignment["assignment_id"]
    conn.execute(
        "INSERT INTO go_operator_projection_occupancy_update (tour_id) VALUES (?)",
        (tour_id,),
    )
    cursor = conn.execute(
        """
        UPDATE tours
        SET title = ?, city = ?, start_date = ?, end_date = ?,
            day_locations_json = ?
        WHERE id = ? AND source = ?
        """,
        (
            desired["title"],
            desired["city"],
            desired["start_date"],
            desired["end_date"],
            desired["day_locations_json"],
            tour_id,
            SOURCE_GUIDE_OPERATOR,
        ),
    )
    if cursor.rowcount != 1:
        raise ProjectionRepairValidationError(
            "Repair must update exactly one protected projection."
        )
    projection = conn.execute(
        """
        SELECT start_date, end_date, source, note, tour_group_id, income,
               user_id, status, payment_status
        FROM tours
        WHERE id = ?
        LIMIT 1
        """,
        (tour_id,),
    ).fetchone()
    if (
        projection is None
        or projection["start_date"] != desired["start_date"]
        or projection["end_date"] != desired["end_date"]
        or projection["source"] != SOURCE_GUIDE_OPERATOR
        or projection["note"] != f"go_assignment:{assignment_id}"
        or projection["tour_group_id"] != assignment_id
        or projection["income"] is not None
        or projection["user_id"] != current["user_id"]
        or projection["status"] != current["status"]
        or projection["payment_status"] != current["payment_status"]
    ):
        raise ProjectionRepairValidationError(
            "Repair must keep protected projection identity."
        )
    conn.execute(
        "DELETE FROM go_operator_projection_occupancy_update WHERE tour_id = ?",
        (tour_id,),
    )
    if assignment.get("projection_tour_id") != tour_id:
        conn.execute(
            """
            UPDATE guide_operator_assignments
            SET projection_tour_id = ?
            WHERE assignment_id = ? AND guide_os_id = ? AND status = 'accepted'
            """,
            (tour_id, assignment_id, assignment["guide_os_id"]),
        )


def _release_protected_projection(conn, tour_id: int) -> None:
    conn.execute(
        "INSERT INTO go_operator_projection_release (tour_id) VALUES (?)",
        (tour_id,),
    )
    cursor = conn.execute(
        "DELETE FROM tours WHERE id = ? AND source = ?",
        (tour_id, SOURCE_GUIDE_OPERATOR),
    )
    if cursor.rowcount != 1:
        raise ProjectionRepairValidationError(
            "Repair must release exactly one protected projection."
        )
    conn.execute(
        "DELETE FROM go_operator_projection_release WHERE tour_id = ?",
        (tour_id,),
    )


def _persist_terminal(
    conn,
    *,
    request_id: str,
    assignment_id: str,
    guide_os_id: str,
    payload_hash: str,
    result_status: str,
    action: str,
    audit: bool,
) -> ProjectionRepairResult:
    created_at = _utc_now()
    conn.execute(
        """
        INSERT INTO guide_operator_projection_repair_inbox (
            repair_request_id, assignment_id, guide_os_id, payload_hash,
            result_status, action, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            assignment_id,
            guide_os_id,
            payload_hash,
            result_status,
            action,
            created_at,
        ),
    )
    if audit:
        conn.execute(
            """
            INSERT INTO guide_operator_projection_repair_audits (
                repair_request_id, assignment_id, guide_os_id,
                action, result_status, created_at
            ) VALUES (?, ?, ?, ?, 'applied', ?)
            """,
            (request_id, assignment_id, guide_os_id, action, created_at),
        )
    return ProjectionRepairResult(
        status=result_status,
        repair_request_id=request_id,
        replayed=False,
        action=action,
    )


def _require_guide(guide_os_id: object) -> str:
    try:
        return validate_guide_os_id(guide_os_id)
    except Exception as exc:
        raise ProjectionRepairValidationError("guide_os_id") from exc


def _require_assignment_id(assignment_id: object) -> str:
    if not isinstance(assignment_id, str) or not assignment_id.strip():
        raise ProjectionRepairValidationError("assignment_id")
    if assignment_id != assignment_id.strip() or len(assignment_id) > 128:
        raise ProjectionRepairValidationError("assignment_id")
    return assignment_id


def _require_uuid4(value: object, field: str) -> str:
    if not isinstance(value, str) or value != value.lower():
        raise ProjectionRepairValidationError(field)
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ProjectionRepairValidationError(field) from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ProjectionRepairValidationError(field)
    return value


def _require_expected_status(value: object) -> str:
    if not isinstance(value, str) or value not in ALLOWED_EXPECTED_STATUSES:
        raise ProjectionRepairValidationError("expected_status")
    return value


def _require_version_number(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ProjectionRepairValidationError("expected_active_version_number")
    return value


def _require_projection_fingerprint(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _REPAIR_PROJECTION_KEYS:
        raise ProjectionRepairValidationError("expected_projection")
    exists = value.get("exists")
    if not isinstance(exists, bool):
        raise ProjectionRepairValidationError("expected_projection")
    start_date = value.get("start_date")
    end_date = value.get("end_date")
    version_number = value.get("version_number")
    if not exists:
        if start_date is not None or end_date is not None or version_number is not None:
            raise ProjectionRepairValidationError("expected_projection")
        return {
            "exists": False,
            "start_date": None,
            "end_date": None,
            "version_number": None,
        }
    if (
        not isinstance(start_date, str)
        or not isinstance(end_date, str)
        or _ISO_DATE_RE.fullmatch(start_date) is None
        or _ISO_DATE_RE.fullmatch(end_date) is None
        or isinstance(version_number, bool)
        or not isinstance(version_number, int)
        or version_number < 1
    ):
        raise ProjectionRepairValidationError("expected_projection")
    return {
        "exists": True,
        "start_date": start_date,
        "end_date": end_date,
        "version_number": version_number,
    }


def repair_local_projection_set(
    guide_os_id: object,
    assignment_id: object,
    *,
    repair_request_id: object,
    expected_status: object,
    expected_active_version_number: object,
    expected_fingerprint: object,
) -> ProjectionRepairResult:
    """Local explicit-day repair only. No HTTP/UI caller or replacement content.

    All evidence checks, conflict detection, projection writes and repair records
    share BEGIN IMMEDIATE with confirm/cancel. Legacy repair remains separate.
    """
    from services.guide_operator_assignment_service import (
        _daily_conflicts,
        _release_daily_row,
        _replace_daily_projections,
    )
    from services.guide_operator_reconcile_service import _assignment_snapshot_v2
    from services.reconciliation_v2_contract import SnapshotContractError

    identity = _require_guide(guide_os_id)
    assignment_key = _require_assignment_id(assignment_id)
    request_id = _require_uuid4(repair_request_id, "repair_request_id")
    status_expected = _require_expected_status(expected_status)
    version_expected = _require_version_number(expected_active_version_number)
    if (
        not isinstance(expected_fingerprint, str)
        or re.fullmatch("[0-9a-f]{64}", expected_fingerprint) is None
    ):
        raise ProjectionRepairValidationError("expected_fingerprint")
    payload_hash = _canonical_hash(
        {
            "schema_version": "projection_set.repair.v2",
            "assignment_id": assignment_key,
            "guide_os_id": identity,
            "expected_status": status_expected,
            "expected_active_version_number": version_expected,
            "expected_fingerprint": expected_fingerprint,
        }
    )

    def operation(conn):
        prior = conn.execute(
            "SELECT * FROM guide_operator_projection_repair_inbox WHERE repair_request_id=?",
            (request_id,),
        ).fetchone()
        if prior is not None:
            if prior["payload_hash"] != payload_hash:
                return ProjectionRepairResult("conflict", request_id, False, "none")
            # Return the recorded terminal result, even after a later confirmation/cancellation.
            return ProjectionRepairResult(
                prior["result_status"], request_id, True, prior["action"]
            )
        raw = conn.execute(
            "SELECT * FROM guide_operator_assignments WHERE assignment_id=? AND guide_os_id=?",
            (assignment_key, identity),
        ).fetchone()
        if raw is None:
            raise ProjectionRepairNotFoundError("missing")
        assignment = dict(raw)

        def finish(status="no-op", action="none"):
            return _persist_terminal(
                conn,
                request_id=request_id,
                assignment_id=assignment_key,
                guide_os_id=identity,
                payload_hash=payload_hash,
                result_status=status,
                action=action,
                audit=status == "applied",
            )

        if (
            assignment["projection_mode"] != "explicit_days"
            or assignment["projection_tour_id"] is not None
            or assignment["status"] != status_expected
            or assignment["active_version_number"] != version_expected
            or assignment["pending_critical_version_number"] is not None
        ):
            return finish()
        try:
            snapshot = _assignment_snapshot_v2(conn, assignment)
        except (SnapshotContractError, ValueError, TypeError, KeyError):
            return finish()
        if snapshot["fingerprint"] != expected_fingerprint or snapshot["state_issues"]:
            return finish()
        desired = _agreed_explicit_repair_scope(conn, assignment)
        if desired is None:
            return finish()
        package, scope = desired
        if status_expected == "cancelled":
            cancellation = conn.execute(
                "SELECT 1 FROM guide_operator_cancellation_inbox WHERE event_id=? AND assignment_id=? "
                "AND guide_os_id=? AND version_number=? AND result_status='applied'",
                (
                    assignment["cancellation_event_id"],
                    assignment_key,
                    identity,
                    version_expected,
                ),
            ).fetchone()
            if cancellation is None or not assignment["cancelled_at"]:
                return finish()
        connection = conn.execute(
            "SELECT company_id,guide_os_id FROM guide_operator_connections "
            "WHERE connection_id=?",
            (assignment["guide_connection_id"],),
        ).fetchone()
        if (
            connection is None
            or connection["company_id"] != assignment["company_id"]
            or connection["guide_os_id"] != identity
        ):
            return finish()
        user = conn.execute(
            "SELECT user_id FROM users WHERE guide_os_id=?", (identity,)
        ).fetchone()
        if user is None:
            return finish()
        user_id = user["user_id"]
        owned = _safe_explicit_repair_rows(conn, assignment, snapshot, user_id)
        if owned is None:
            return finish()
        desired_keys = (
            {key for key, _ in scope} if status_expected == "accepted" else set()
        )
        # Never delete a row containing financial values, even if it is an otherwise valid stray.
        if any(
            key not in desired_keys
            and (row["income"] is not None or row["payment_status"] != PAYMENT_UNPAID)
            for key, row in owned.items()
        ):
            return finish()
        if status_expected == "accepted" and _daily_conflicts(
            conn,
            assignment,
            scope,
            user_id,
            exclude_projection_ids={row["id"] for row in owned.values()},
        ):
            return finish("conflict")
        if _explicit_repair_matches(assignment, snapshot, owned, package, scope):
            return finish()

        conn.execute(
            "DELETE FROM guide_operator_daily_projections WHERE assignment_id=?",
            (assignment_key,),
        )
        for key, row in owned.items():
            if key not in desired_keys:
                _release_daily_row(conn, row["id"], user_id)
        if status_expected == "accepted":
            # Reattach only unique, validated stable identities. This also retains a
            # financially nonempty row if its link was lost; no copying of amounts.
            for key, value in scope:
                if key in owned:
                    conn.execute(
                        "INSERT INTO guide_operator_daily_projections(source_service,company_id,assignment_id,"
                        "guide_os_id,operator_tour_id,tour_day_id,calendar_date,active_version_number,projection_tour_id) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            SOURCE_GUIDE_OPERATOR,
                            assignment["company_id"],
                            assignment_key,
                            identity,
                            assignment["operator_tour_id"],
                            key,
                            value,
                            version_expected,
                            owned[key]["id"],
                        ),
                    )
            _replace_daily_projections(
                conn, assignment, package, version_expected, user_id, scope
            )
        after_row = dict(
            conn.execute(
                "SELECT * FROM guide_operator_assignments WHERE assignment_id=?",
                (assignment_key,),
            ).fetchone()
        )
        if after_row != assignment:
            raise ProjectionRepairValidationError("Repair changed assignment state.")
        after = _assignment_snapshot_v2(conn, after_row)
        if not _explicit_repair_matches(
            assignment, after, {}, package, scope, check_labels=False
        ):
            raise ProjectionRepairValidationError(
                "Repair did not restore the entire projection set."
            )
        action = (
            "release_stray"
            if status_expected == "cancelled"
            else ("recreate" if not owned else "repair_mismatch")
        )
        result = finish("applied", action)
        if _REPAIR_FAILURE_HOOK is not None:
            _REPAIR_FAILURE_HOOK()
        return result

    return run_write_with_retry(operation)


def _agreed_explicit_repair_scope(conn, assignment):
    """Version reference + retained guide decision, never caller calendar content."""
    from services.guide_operator_assignment_service import (
        AssignmentValidationError,
        _explicit_scope,
    )

    initial_accept = conn.execute(
        "SELECT 1 FROM guide_operator_assignment_decisions WHERE assignment_id=? AND guide_os_id=? "
        "AND decision_type='accept' AND version_number=1",
        (assignment["assignment_id"], assignment["guide_os_id"]),
    ).fetchone()
    if initial_accept is None:
        return None
    versions = {
        row["version_number"]: dict(row)
        for row in conn.execute(
            "SELECT * FROM guide_operator_assignment_versions WHERE assignment_id=?",
            (assignment["assignment_id"],),
        )
    }
    active = versions.get(assignment["active_version_number"])
    if active is None or versions.get(1, {}).get("severity") != "initial":
        return None
    confirmed = {
        row["version_number"]
        for row in conn.execute(
            "SELECT version_number FROM guide_operator_critical_version_decisions WHERE assignment_id=? "
            "AND guide_os_id=? AND decision_type='confirm_critical'",
            (assignment["assignment_id"], assignment["guide_os_id"]),
        )
    }
    version = assignment["active_version_number"]
    if version == 1:
        proof_version = 1
    elif active["severity"] == "critical" and version in confirmed:
        proof_version = version
    elif active["severity"] == "ordinary":
        proof_version = max([1] + [n for n in confirmed if n < version])
        if (
            proof_version != 1
            and versions.get(proof_version, {}).get("severity") != "critical"
        ):
            return None
    else:
        return None
    try:
        initial = _load_working_package_json(versions[1]["working_package_json"])
        package = _load_working_package_json(active["working_package_json"])
        proof = _load_working_package_json(
            versions[proof_version]["working_package_json"]
        )
        if any(
            candidate.get("schema_version") != "assignment.working_package.v2"
            or not isinstance(candidate.get("days"), list)
            or len(candidate["days"]) > 366
            for candidate in (initial, package, proof)
        ):
            return None
        _explicit_scope(assignment, initial)
        scope = _explicit_scope(assignment, package)
        if (
            _explicit_scope(assignment, proof) != scope
            or proof["assignment"]["role"] != package["assignment"]["role"]
        ):
            return None
        return package, scope
    except (AssignmentValidationError, ValueError, TypeError, KeyError):
        return None


def _safe_explicit_repair_rows(conn, assignment, snapshot, user_id):
    """Do not guess ownership or select between duplicate stable identities."""
    owned = {}
    allowed = {"missing_tour", "unlinked", "date_mismatch", "not_daily"}
    for item in snapshot["projections"]:
        if set(item["issues"]) - allowed:
            return None
        row = conn.execute(
            "SELECT * FROM tours WHERE id=?", (item["projection_tour_id"],)
        ).fetchone()
        if row is None:
            continue
        row = dict(row)
        if conn.execute(
            "SELECT 1 FROM guide_operator_daily_projections WHERE projection_tour_id=? "
            "AND assignment_id<>?",
            (row["id"], assignment["assignment_id"]),
        ).fetchone():
            return None
        if (
            row["user_id"] != user_id
            or row["source"] != SOURCE_GUIDE_OPERATOR
            or row["note"] != "go_assignment:" + assignment["assignment_id"]
            or row["entry_type"] != ENTRY_TYPE_TOUR
            or row["status"] != STATUS_CONFIRMED
            or row["start_time"] is not None
            or row["end_time"] is not None
        ):
            return None
        prefix = assignment["assignment_id"] + ":"
        group = row["tour_group_id"]
        if not isinstance(group, str) or not group.startswith(prefix):
            return None
        try:
            key = _require_uuid4(group[len(prefix) :], "tour_day_id")
        except ProjectionRepairValidationError:
            return None
        if (
            item["tour_day_id"] is not None and item["tour_day_id"] != key
        ) or key in owned:
            return None
        owned[key] = row
    return owned


def _explicit_repair_matches(
    assignment, snapshot, owned, package, scope, *, check_labels=True
):
    if assignment["status"] == "cancelled":
        return not snapshot["projections"]
    title, city = _projection_labels(assignment, package)
    desired = {
        (key, value, value, assignment["active_version_number"]) for key, value in scope
    }
    actual = {
        (p["tour_day_id"], p["date"], p["end_date"], p["active_version_number"])
        for p in snapshot["projections"]
        if not p["issues"]
    }
    if actual != desired or len(snapshot["projections"]) != len(desired):
        return False
    return not check_labels or (
        len(owned) == len(desired)
        and all(row["title"] == title and row["city"] == city for row in owned.values())
    )
