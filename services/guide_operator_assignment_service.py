"""Guide Operator assignment intake, decision, projection, cancellation, and ordinary versions.

Local Guide OS foundation only: no cross-service networking, UI, or production auth.
"""

from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

from database.db import ensure_db_ready, get_db_connection, run_write_with_retry
from database.queries import (
    get_guide_operator_assignment,
    get_guide_operator_assignment_lifecycle_inbox,
    get_guide_operator_assignment_for_guide,
    read_guide_operator_assignment_for_guide,
    get_guide_operator_assignment_version,
    get_guide_operator_cancellation_inbox,
    get_guide_operator_critical_version_decision,
    get_guide_operator_critical_version_decision_by_event,
    get_guide_operator_decision,
    get_guide_operator_offer_inbox,
    get_guide_operator_version_acknowledgement,
    get_guide_operator_version_inbox,
    get_user_id_by_guide_os_id,
    list_guide_operator_assignment_versions,
    list_guide_operator_lifecycle_assignments,
    list_guide_operator_outbox_events,
    list_guide_operator_pending_offers,
)
from services.tour_service import days_in_range, get_conflicting_dates
from services.guide_operator_connection_service import (
    ConnectionValidationError as _ConnectionValidationError,
    require_confirmed_connection_for_offer,
)
from services.guide_operator_notification_outbox import (
    insert_guide_operator_guide_notification,
)
from utils.constants import (
    ENTRY_TYPE_TOUR,
    PAYMENT_UNPAID,
    SOURCE_GUIDE_OPERATOR,
    STATUS_CONFIRMED,
)
from utils.date_utils import today_tz
from utils.guide_os_identity import validate_guide_os_id

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CANCELLATION_ACK_EVENT_TYPE = "assignment.cancellation.ack.v1"
ORDINARY_VERSION_ACK_EVENT_TYPE = "assignment.version.applied.ack.v1"
CRITICAL_VERSION_RECEIVED_ACK_EVENT_TYPE = "assignment.version.received.ack.v1"
CRITICAL_VERSION_DECISION_EVENT_TYPE = "assignment.critical_version.decided.v1"
VERSION_ACKNOWLEDGED_EVENT_TYPE = "assignment.version.acknowledged.v1"

# Test-only hook raised inside the accept transaction before commit.
_ACCEPT_FAILURE_HOOK: Callable[[], None] | None = None

# Test-only hook raised inside the offer intake transaction before commit.
_OFFER_INTAKE_FAILURE_HOOK: Callable[[], None] | None = None

# Test-only hook raised inside the cancellation transaction before commit.
_CANCEL_FAILURE_HOOK: Callable[[], None] | None = None

# Test-only hook raised inside the ordinary-version transaction before commit.
_ORDINARY_VERSION_FAILURE_HOOK: Callable[[], None] | None = None

# Test-only hook raised inside the critical-version intake transaction before commit.
_CRITICAL_VERSION_INTAKE_FAILURE_HOOK: Callable[[], None] | None = None

# Test-only hook raised inside the critical-version decision transaction before commit.
_CRITICAL_VERSION_DECISION_FAILURE_HOOK: Callable[[], None] | None = None

# Test-only hook raised inside the version-acknowledgement transaction before commit.
_VERSION_ACK_FAILURE_HOOK: Callable[[], None] | None = None


class GuideOperatorAssignmentError(Exception):
    """Base fail-closed domain error for Guide Operator assignments."""

    code = "guide_operator_assignment_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AssignmentValidationError(GuideOperatorAssignmentError):
    code = "validation_error"


class AssignmentNotFoundError(GuideOperatorAssignmentError):
    code = "not_found"


class AssignmentForbiddenError(GuideOperatorAssignmentError):
    code = "forbidden"


class AssignmentConflictError(GuideOperatorAssignmentError):
    code = "idempotency_conflict"


class AssignmentNotActionableError(GuideOperatorAssignmentError):
    code = "assignment_not_actionable"


class CalendarConflictError(GuideOperatorAssignmentError):
    code = "calendar_conflict"


@dataclass(frozen=True)
class AssignmentOfferIntake:
    event_id: str
    assignment_id: str
    guide_os_id: str
    company_id: str
    company_name: str
    guide_connection_id: str
    role: str
    start_date: str
    end_date: str
    working_package: dict[str, Any]
    version_number: int = 1
    response_deadline: str | None = None
    operator_message: str | None = None
    offered_at: str | None = None


@dataclass(frozen=True)
class AssignmentDecisionResult:
    assignment_id: str
    guide_os_id: str
    status: str
    decision: str
    decision_event_id: str
    projection_tour_id: int | None
    replayed: bool = False


@dataclass(frozen=True)
class AssignmentCancellationIntake:
    """Canonical assignment.cancelled.v1 payload bound to one guide assignment."""

    event_id: str
    assignment_id: str
    guide_os_id: str
    version_number: int
    cancelled_at: str


@dataclass(frozen=True)
class AssignmentCancellationResult:
    assignment_id: str
    guide_os_id: str
    status: str
    version_number: int
    cancelled_at: str
    cancellation_event_id: str
    projection_released: bool
    replayed: bool = False


@dataclass(frozen=True)
class AssignmentLifecycleIntake:
    """Canonical withdrawn/expired event bound to one offered assignment."""

    event_id: str
    event_type: str
    assignment_id: str
    guide_os_id: str
    transitioned_at: str


@dataclass(frozen=True)
class AssignmentLifecycleResult:
    assignment_id: str
    guide_os_id: str
    status: str
    event_type: str
    replayed: bool = False


@dataclass(frozen=True)
class AssignmentVersionPublishedIntake:
    """Canonical assignment.version.published.v1 payload bound to one guide."""

    event_id: str
    assignment_id: str
    guide_os_id: str
    version_number: int
    previous_active_version_number: int
    severity: str
    working_package: dict[str, Any]
    change_summary: list[Any]
    published_at: str


@dataclass(frozen=True)
class AssignmentOrdinaryVersionResult:
    assignment_id: str
    guide_os_id: str
    status: str
    version_number: int
    previous_active_version_number: int
    source_event_id: str
    unread: bool
    projection_tour_id: int | None
    replayed: bool = False


@dataclass(frozen=True)
class AssignmentCriticalVersionIntakeResult:
    assignment_id: str
    guide_os_id: str
    status: str
    version_number: int
    previous_active_version_number: int
    pending_critical_version_number: int | None
    active_version_number: int
    source_event_id: str
    unread: bool
    projection_tour_id: int | None
    replayed: bool = False


@dataclass(frozen=True)
class AssignmentCriticalVersionDecisionResult:
    assignment_id: str
    guide_os_id: str
    status: str
    decision: str
    version_number: int
    decision_event_id: str
    pending_critical_version_number: int | None
    active_version_number: int
    projection_tour_id: int | None
    replayed: bool = False


@dataclass(frozen=True)
class AssignmentVersionAcknowledgeResult:
    assignment_id: str
    guide_os_id: str
    version_number: int
    decision_event_id: str
    unread: bool
    replayed: bool = False


def receive_assignment_offer(offer: AssignmentOfferIntake) -> dict[str, Any]:
    """Idempotently persist an offered assignment and immutable version 1."""
    ensure_db_ready()
    normalized = _normalize_offer(offer)
    payload_hash = _canonical_hash(normalized)

    existing_inbox = get_guide_operator_offer_inbox(normalized["event_id"])
    if existing_inbox is not None:
        if existing_inbox["payload_hash"] != payload_hash:
            raise AssignmentConflictError(
                "Offer event ID was already used with another payload."
            )
        stored = get_guide_operator_assignment(normalized["assignment_id"])
        if stored is None:
            raise AssignmentValidationError("Offer inbox exists without assignment.")
        return stored

    existing = get_guide_operator_assignment(normalized["assignment_id"])
    if existing is not None:
        prior_inbox = get_guide_operator_offer_inbox(existing["offer_event_id"])
        if prior_inbox is not None and prior_inbox["payload_hash"] == payload_hash:
            return existing
        raise AssignmentConflictError(
            "Assignment offer already exists with a different payload."
        )

    guide_os_id = validate_guide_os_id(normalized["guide_os_id"])
    if get_user_id_by_guide_os_id(guide_os_id) is None:
        raise AssignmentValidationError(
            "Unknown guide_os_id; integration boundary fail-closed.",
            details={"code": "integration_unavailable"},
        )

    try:
        require_confirmed_connection_for_offer(
            guide_connection_id=normalized["guide_connection_id"],
            guide_os_id=guide_os_id,
            company_id=normalized["company_id"],
            now=normalized["offered_at"],
        )
    except _ConnectionValidationError as exc:
        raise AssignmentValidationError(
            exc.message,
            details=exc.details or {"code": "connection_rejected"},
        ) from exc

    offered_at = normalized["offered_at"] or _utc_now()

    def operation(conn):
        inbox = conn.execute(
            "SELECT * FROM guide_operator_offer_inbox WHERE event_id = ? LIMIT 1",
            (normalized["event_id"],),
        ).fetchone()
        if inbox is not None:
            if inbox["payload_hash"] != payload_hash:
                raise AssignmentConflictError(
                    "Offer event ID was already used with another payload."
                )
            row = conn.execute(
                "SELECT * FROM guide_operator_assignments WHERE assignment_id = ?",
                (normalized["assignment_id"],),
            ).fetchone()
            return dict(row) if row else None

        existing_row = conn.execute(
            "SELECT * FROM guide_operator_assignments WHERE assignment_id = ?",
            (normalized["assignment_id"],),
        ).fetchone()
        if existing_row is not None:
            raise AssignmentConflictError(
                "Assignment offer already exists with a different payload."
            )

        # Re-check connection inside the write transaction (no partial offer rows).
        connection_row = conn.execute(
            """
            SELECT * FROM guide_operator_connections
            WHERE connection_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (normalized["guide_connection_id"], guide_os_id),
        ).fetchone()
        if (
            connection_row is None
            or connection_row["company_id"] != normalized["company_id"]
            or connection_row["status"] != "confirmed"
        ):
            raise AssignmentValidationError(
                "Guide connection is not confirmed for this offer.",
                details={"code": "connection_not_confirmed"},
            )

        conn.execute(
            """
            INSERT INTO guide_operator_assignments (
                assignment_id, guide_os_id, company_id, company_name,
                guide_connection_id, role,
                start_date, end_date, response_deadline, operator_message,
                status, active_version_number, projection_tour_id,
                offer_event_id, offered_at, decided_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'offered', 1, NULL, ?, ?, NULL, ?, ?)
            """,
            (
                normalized["assignment_id"],
                guide_os_id,
                normalized["company_id"],
                normalized["company_name"],
                normalized["guide_connection_id"],
                normalized["role"],
                normalized["start_date"],
                normalized["end_date"],
                normalized["response_deadline"],
                normalized["operator_message"],
                normalized["event_id"],
                offered_at,
                offered_at,
                offered_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO guide_operator_assignment_versions (
                assignment_id, version_number, severity,
                working_package_json, published_at
            ) VALUES (?, 1, 'initial', ?, ?)
            """,
            (
                normalized["assignment_id"],
                json.dumps(normalized["working_package"], ensure_ascii=False, sort_keys=True),
                offered_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO guide_operator_offer_inbox (
                event_id, assignment_id, guide_os_id, payload_hash,
                received_at, result_status
            ) VALUES (?, ?, ?, ?, ?, 'applied')
            """,
            (
                normalized["event_id"],
                normalized["assignment_id"],
                guide_os_id,
                payload_hash,
                offered_at,
            ),
        )
        insert_guide_operator_guide_notification(
            conn,
            source_event_id=normalized["event_id"],
            guide_os_id=guide_os_id,
            notification_type="assignment_offer",
            company_name=normalized["company_name"],
            assignment_id=normalized["assignment_id"],
            version_number=1,
            created_at=offered_at,
        )
        if _OFFER_INTAKE_FAILURE_HOOK is not None:
            _OFFER_INTAKE_FAILURE_HOOK()
        row = conn.execute(
            "SELECT * FROM guide_operator_assignments WHERE assignment_id = ?",
            (normalized["assignment_id"],),
        ).fetchone()
        return dict(row)

    result = run_write_with_retry(operation)
    if result is None:
        raise AssignmentValidationError("Failed to persist assignment offer.")
    return result


def list_pending_offers(guide_os_id: str) -> list[dict[str, Any]]:
    identity = validate_guide_os_id(guide_os_id)
    return list_guide_operator_pending_offers(identity)


def list_assignment_lifecycle(
    guide_os_id: str,
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Partition guide assignments into lifecycle sections using business timezone.

    - awaiting: status offered
    - upcoming: accepted and start_date > today
    - in_progress: accepted and start_date <= today <= end_date
    - completed: accepted and end_date < today
    - cancelled: status cancelled (newest cancelled_at first)

    Declined assignments are omitted. Sorting is server-side.
    """
    identity = validate_guide_os_id(guide_os_id)
    today = as_of or today_tz()
    today_s = today.isoformat()

    awaiting: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []
    in_progress: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    cancelled: list[dict[str, Any]] = []

    for row in list_guide_operator_lifecycle_assignments(identity):
        status = row.get("status")
        if status == "offered":
            awaiting.append(row)
            continue
        if status == "cancelled":
            cancelled.append(row)
            continue
        if status != "accepted":
            continue
        start_date = row["start_date"]
        end_date = row["end_date"]
        if start_date > today_s:
            upcoming.append(row)
        elif end_date < today_s:
            completed.append(row)
        else:
            in_progress.append(row)

    awaiting.sort(key=lambda r: (r["start_date"], r["assignment_id"]))
    upcoming.sort(key=lambda r: (r["start_date"], r["assignment_id"]))
    in_progress.sort(key=lambda r: (r["start_date"], r["assignment_id"]))
    completed.sort(
        key=lambda r: (r["end_date"], r["start_date"], r["assignment_id"]),
        reverse=True,
    )
    cancelled.sort(
        key=lambda r: (
            r.get("cancelled_at") or "",
            r["assignment_id"],
        ),
        reverse=True,
    )

    return {
        "as_of_date": today_s,
        "awaiting": awaiting,
        "upcoming": upcoming,
        "in_progress": in_progress,
        "completed": completed,
        "cancelled": cancelled,
    }


def get_assignment_for_guide(guide_os_id: str, assignment_id: str) -> dict[str, Any]:
    identity = validate_guide_os_id(guide_os_id)
    assignment_id = _require_nonempty(assignment_id, "assignment_id")
    row = get_guide_operator_assignment_for_guide(identity, assignment_id)
    if row is None:
        # Fail closed: do not reveal whether the assignment exists for another guide.
        raise AssignmentNotFoundError("Assignment was not found.")
    return row


def get_assignment_version_for_guide(
    guide_os_id: str, assignment_id: str, version_number: int = 1
) -> dict[str, Any]:
    get_assignment_for_guide(guide_os_id, assignment_id)
    version = get_guide_operator_assignment_version(assignment_id, version_number)
    if version is None:
        raise AssignmentNotFoundError("Assignment version was not found.")
    return version


def find_assignment_conflicts(guide_os_id: str, assignment_id: str) -> list[str]:
    assignment = get_assignment_for_guide(guide_os_id, assignment_id)
    user_id = _require_user_id(guide_os_id)
    return _calendar_conflicts(
        user_id, assignment["start_date"], assignment["end_date"]
    )


def accept_assignment(
    guide_os_id: str,
    assignment_id: str,
    *,
    decision_event_id: str,
    decided_at: str | None = None,
) -> AssignmentDecisionResult:
    return _decide_assignment(
        guide_os_id,
        assignment_id,
        decision="accept",
        decision_event_id=decision_event_id,
        decided_at=decided_at,
    )


def decline_assignment(
    guide_os_id: str,
    assignment_id: str,
    *,
    decision_event_id: str,
    decided_at: str | None = None,
) -> AssignmentDecisionResult:
    return _decide_assignment(
        guide_os_id,
        assignment_id,
        decision="decline",
        decision_event_id=decision_event_id,
        decided_at=decided_at,
    )


def apply_assignment_cancellation(
    event: AssignmentCancellationIntake,
) -> AssignmentCancellationResult:
    """Idempotently apply assignment.cancelled.v1 and release protected projection.

    Cancellation does not require guide approval. Identical event delivery is safe.
    Reused event IDs with a different payload fail closed without calendar changes.
    """
    ensure_db_ready()
    normalized = _normalize_cancellation(event)
    payload_hash = _canonical_hash(normalized)
    identity = normalized["guide_os_id"]
    assignment_id = normalized["assignment_id"]
    event_id = normalized["event_id"]
    version_number = normalized["version_number"]
    cancelled_at = normalized["cancelled_at"]

    owned = read_guide_operator_assignment_for_guide(identity, assignment_id)
    if owned is not None and owned["projection_mode"] == "explicit_days":
        result = _apply_explicit_projection_decision_local(
            identity, assignment_id, action="cancel", version_number=version_number,
            event_id=event_id, occurred_at=cancelled_at, wire_cancellation=True,
        )
        return AssignmentCancellationResult(
            assignment_id=assignment_id, guide_os_id=identity, status="cancelled",
            version_number=version_number, cancelled_at=cancelled_at,
            cancellation_event_id=event_id, projection_released=True,
            replayed=result["replayed"],
        )

    existing_inbox = get_guide_operator_cancellation_inbox(event_id)
    if existing_inbox is not None:
        if existing_inbox["payload_hash"] != payload_hash:
            raise AssignmentConflictError(
                "Cancellation event ID was already used with another payload."
            )
        stored = get_guide_operator_assignment_for_guide(identity, assignment_id)
        if stored is None:
            raise AssignmentNotFoundError("Assignment was not found.")
        if stored["status"] != "cancelled":
            raise AssignmentValidationError(
                "Cancellation inbox exists without cancelled assignment."
            )
        return AssignmentCancellationResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            status="cancelled",
            version_number=int(stored["active_version_number"]),
            cancelled_at=stored["cancelled_at"] or cancelled_at,
            cancellation_event_id=stored.get("cancellation_event_id") or event_id,
            projection_released=stored.get("projection_tour_id") is None,
            replayed=True,
        )

    # Fail closed before write: bind guide without disclosing cross-guide existence.
    assignment = get_assignment_for_guide(identity, assignment_id)
    if int(assignment["active_version_number"]) != version_number:
        raise AssignmentConflictError(
            "Cancellation version does not match the active assignment version."
        )
    if assignment["status"] != "accepted":
        raise AssignmentNotActionableError(
            "Only an accepted assignment can be cancelled."
        )

    def operation(conn):
        inbox = conn.execute(
            """
            SELECT * FROM guide_operator_cancellation_inbox
            WHERE event_id = ? LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        if inbox is not None:
            if inbox["payload_hash"] != payload_hash:
                raise AssignmentConflictError(
                    "Cancellation event ID was already used with another payload."
                )
            locked = conn.execute(
                """
                SELECT *
                FROM guide_operator_assignments
                WHERE assignment_id = ? AND guide_os_id = ?
                LIMIT 1
                """,
                (assignment_id, identity),
            ).fetchone()
            if locked is None or locked["status"] != "cancelled":
                raise AssignmentValidationError(
                    "Cancellation inbox exists without cancelled assignment."
                )
            return AssignmentCancellationResult(
                assignment_id=assignment_id,
                guide_os_id=identity,
                status="cancelled",
                version_number=int(locked["active_version_number"]),
                cancelled_at=locked["cancelled_at"] or cancelled_at,
                cancellation_event_id=locked["cancellation_event_id"] or event_id,
                projection_released=locked["projection_tour_id"] is None,
                replayed=True,
            )

        locked = conn.execute(
            """
            SELECT *
            FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (assignment_id, identity),
        ).fetchone()
        if locked is None:
            raise AssignmentNotFoundError("Assignment was not found.")
        if int(locked["active_version_number"]) != version_number:
            raise AssignmentConflictError(
                "Cancellation version does not match the active assignment version."
            )
        if locked["status"] != "accepted":
            raise AssignmentNotActionableError(
                "Only an accepted assignment can be cancelled."
            )

        projection_tour_id = locked["projection_tour_id"]
        received_at = _utc_now()

        conn.execute(
            """
            INSERT INTO guide_operator_cancellation_inbox (
                event_id, assignment_id, guide_os_id, version_number,
                payload_hash, received_at, result_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'applied')
            """,
            (
                event_id,
                assignment_id,
                identity,
                version_number,
                payload_hash,
                received_at,
            ),
        )
        conn.execute(
            """
            UPDATE guide_operator_assignments
            SET status = 'cancelled',
                projection_tour_id = NULL,
                cancelled_at = ?,
                cancellation_event_id = ?,
                pending_critical_version_number = NULL,
                updated_at = ?
            WHERE assignment_id = ? AND guide_os_id = ? AND status = 'accepted'
            """,
            (cancelled_at, event_id, received_at, assignment_id, identity),
        )
        updated = conn.execute(
            """
            SELECT status, projection_tour_id, cancelled_at, cancellation_event_id,
                   active_version_number
            FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (assignment_id, identity),
        ).fetchone()
        if updated is None or updated["status"] != "cancelled":
            raise AssignmentNotActionableError(
                "Only an accepted assignment can be cancelled."
            )

        projection_released = False
        if projection_tour_id is not None:
            conn.execute(
                """
                INSERT INTO go_operator_projection_release (tour_id)
                VALUES (?)
                """,
                (int(projection_tour_id),),
            )
            cursor = conn.execute(
                """
                DELETE FROM tours
                WHERE id = ? AND source = ?
                """,
                (int(projection_tour_id), SOURCE_GUIDE_OPERATOR),
            )
            if cursor.rowcount != 1:
                raise AssignmentValidationError(
                    "Cancellation must release exactly one protected projection."
                )
            conn.execute(
                "DELETE FROM go_operator_projection_release WHERE tour_id = ?",
                (int(projection_tour_id),),
            )
            projection_released = True
        else:
            projection_released = True

        payload = {
            "assignment_id": assignment_id,
            "guide_os_id": identity,
            "version_number": version_number,
            "cancelled_at": cancelled_at,
            "source_event_id": event_id,
        }
        conn.execute(
            """
            INSERT INTO guide_operator_outbox (
                event_id, event_type, aggregate_type, aggregate_id,
                guide_os_id, payload_json, created_at, delivered_at, attempt_count
            ) VALUES (?, ?, 'guide_assignment', ?, ?, ?, ?, NULL, 0)
            """,
            (
                event_id,
                CANCELLATION_ACK_EVENT_TYPE,
                assignment_id,
                identity,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                received_at,
            ),
        )
        insert_guide_operator_guide_notification(
            conn,
            source_event_id=event_id,
            guide_os_id=identity,
            notification_type="assignment_cancellation",
            company_name=str(locked["company_name"]),
            assignment_id=assignment_id,
            version_number=version_number,
            created_at=received_at,
        )

        if _CANCEL_FAILURE_HOOK is not None:
            _CANCEL_FAILURE_HOOK()

        return AssignmentCancellationResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            status="cancelled",
            version_number=version_number,
            cancelled_at=cancelled_at,
            cancellation_event_id=event_id,
            projection_released=projection_released,
            replayed=False,
        )

    return run_write_with_retry(operation)


def apply_assignment_lifecycle_transition(
    event: AssignmentLifecycleIntake,
) -> AssignmentLifecycleResult:
    """Apply an authoritative offered -> withdrawn/expired transition."""
    ensure_db_ready()
    normalized = _normalize_assignment_lifecycle(event)
    payload_hash = _canonical_hash(normalized)
    event_id = normalized["event_id"]
    assignment_id = normalized["assignment_id"]
    identity = normalized["guide_os_id"]
    target_status = normalized["status"]

    existing_inbox = get_guide_operator_assignment_lifecycle_inbox(event_id)
    if existing_inbox is not None:
        if existing_inbox["payload_hash"] != payload_hash:
            raise AssignmentConflictError(
                "Lifecycle event ID was already used with another payload."
            )
        stored = read_guide_operator_assignment_for_guide(identity, assignment_id)
        if stored is None:
            raise AssignmentNotFoundError("Assignment was not found.")
        if stored["status"] != target_status:
            raise AssignmentValidationError(
                "Lifecycle inbox exists without matching assignment state."
            )
        return AssignmentLifecycleResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            status=target_status,
            event_type=normalized["event_type"],
            replayed=True,
        )

    assignment = _guide_lifecycle_assignment(identity, assignment_id)
    if assignment["status"] != "offered":
        raise AssignmentNotActionableError(
            "Only an offered assignment can be withdrawn or expired."
        )
    if assignment.get("projection_tour_id") is not None:
        raise AssignmentConflictError(
            "An offered assignment must not have a protected projection."
        )

    def operation(conn):
        inbox = conn.execute(
            """
            SELECT * FROM guide_operator_assignment_lifecycle_inbox
            WHERE event_id = ? LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        if inbox is not None:
            if inbox["payload_hash"] != payload_hash:
                raise AssignmentConflictError(
                    "Lifecycle event ID was already used with another payload."
                )
            locked = conn.execute(
                """
                SELECT * FROM guide_operator_assignments
                WHERE assignment_id = ? AND guide_os_id = ? LIMIT 1
                """,
                (assignment_id, identity),
            ).fetchone()
            if locked is None or locked["status"] != target_status:
                raise AssignmentValidationError(
                    "Lifecycle inbox exists without matching assignment state."
                )
            return True

        locked = conn.execute(
            """
            SELECT * FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ? LIMIT 1
            """,
            (assignment_id, identity),
        ).fetchone()
        if locked is None:
            raise AssignmentNotFoundError("Assignment was not found.")
        if locked["status"] != "offered":
            raise AssignmentNotActionableError(
                "Only an offered assignment can be withdrawn or expired."
            )
        if locked["projection_tour_id"] is not None:
            raise AssignmentConflictError(
                "An offered assignment must not have a protected projection."
            )

        if locked["projection_mode"] == "explicit_days":
            _require_terminal_aware_time(normalized["transitioned_at"])
            _assert_daily_event_available(conn, event_id)
            _guard_explicit_offered_terminal(conn, dict(locked))
        elif locked["projection_mode"] != "legacy_range":
            raise AssignmentValidationError("Unsupported assignment projection mode.")

        received_at = _utc_now()
        conn.execute(
            """
            INSERT INTO guide_operator_assignment_lifecycle_inbox (
                event_id, event_type, assignment_id, guide_os_id,
                payload_hash, received_at, result_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'applied')
            """,
            (
                event_id,
                normalized["event_type"],
                assignment_id,
                identity,
                payload_hash,
                received_at,
            ),
        )
        cursor = conn.execute(
            """
            UPDATE guide_operator_assignments
            SET status = ?, updated_at = ?
            WHERE assignment_id = ? AND guide_os_id = ? AND status = 'offered'
              AND projection_tour_id IS NULL
            """,
            (target_status, normalized["transitioned_at"], assignment_id, identity),
        )
        if cursor.rowcount != 1:
            raise AssignmentNotActionableError(
                "Only an offered assignment can be withdrawn or expired."
            )
        return False

    replayed = run_write_with_retry(operation)
    return AssignmentLifecycleResult(
        assignment_id=assignment_id,
        guide_os_id=identity,
        status=target_status,
        event_type=normalized["event_type"],
        replayed=bool(replayed),
    )


def list_cancellation_ack_outbox(assignment_id: str) -> list[dict[str, Any]]:
    return list_guide_operator_outbox_events(
        assignment_id=assignment_id, event_type=CANCELLATION_ACK_EVENT_TYPE
    )


def apply_ordinary_assignment_version(
    event: AssignmentVersionPublishedIntake,
) -> AssignmentOrdinaryVersionResult:
    """Idempotently apply assignment.version.published.v1 when severity is ordinary.

    Occupancy-critical fields are checked locally and independently of operator
    classification. Identical event delivery is safe. Reused event IDs with a
    different payload fail closed without assignment or calendar changes.
    """
    ensure_db_ready()
    normalized = _normalize_ordinary_version(event)
    payload_hash = _canonical_hash(normalized)
    identity = normalized["guide_os_id"]
    assignment_id = normalized["assignment_id"]
    event_id = normalized["event_id"]
    version_number = normalized["version_number"]
    previous_active = normalized["previous_active_version_number"]
    working_package = normalized["working_package"]
    change_summary = normalized["change_summary"]
    published_at = normalized["published_at"]

    existing_inbox = get_guide_operator_version_inbox(event_id)
    if existing_inbox is not None:
        if existing_inbox["payload_hash"] != payload_hash:
            raise AssignmentConflictError(
                "Version event ID was already used with another payload."
            )
        stored = get_guide_operator_assignment_for_guide(identity, assignment_id)
        if stored is None:
            raise AssignmentNotFoundError("Assignment was not found.")
        if int(stored["active_version_number"]) != version_number:
            raise AssignmentValidationError(
                "Version inbox exists without the matching active version."
            )
        return AssignmentOrdinaryVersionResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            status=stored["status"],
            version_number=version_number,
            previous_active_version_number=previous_active,
            source_event_id=event_id,
            unread=int(stored.get("active_version_unread") or 0) == 1,
            projection_tour_id=stored.get("projection_tour_id"),
            replayed=True,
        )

    assignment = get_assignment_for_guide(identity, assignment_id)
    _assert_ordinary_version_chain(assignment, version_number, previous_active)
    previous_version = get_guide_operator_assignment_version(
        assignment_id, previous_active
    )
    if previous_version is None:
        raise AssignmentValidationError("Previous active version snapshot is required.")
    previous_package = _load_working_package_json(
        previous_version["working_package_json"]
    )
    occupancy_codes = _ordinary_occupancy_violations(
        assignment=assignment,
        previous_package=previous_package,
        next_package=working_package,
    )
    if occupancy_codes:
        raise AssignmentValidationError(
            "Ordinary version must not change assignment dates, role, "
            "day set, or occupancy envelope.",
            details={"codes": occupancy_codes},
        )

    def operation(conn):
        inbox = conn.execute(
            """
            SELECT * FROM guide_operator_version_inbox
            WHERE event_id = ? LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        if inbox is not None:
            if inbox["payload_hash"] != payload_hash:
                raise AssignmentConflictError(
                    "Version event ID was already used with another payload."
                )
            locked = conn.execute(
                """
                SELECT *
                FROM guide_operator_assignments
                WHERE assignment_id = ? AND guide_os_id = ?
                LIMIT 1
                """,
                (assignment_id, identity),
            ).fetchone()
            if locked is None or int(locked["active_version_number"]) != version_number:
                raise AssignmentValidationError(
                    "Version inbox exists without the matching active version."
                )
            return AssignmentOrdinaryVersionResult(
                assignment_id=assignment_id,
                guide_os_id=identity,
                status=locked["status"],
                version_number=version_number,
                previous_active_version_number=previous_active,
                source_event_id=event_id,
                unread=int(locked["active_version_unread"] or 0) == 1,
                projection_tour_id=locked["projection_tour_id"],
                replayed=True,
            )

        locked = conn.execute(
            """
            SELECT *
            FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (assignment_id, identity),
        ).fetchone()
        if locked is None:
            raise AssignmentNotFoundError("Assignment was not found.")
        _assert_ordinary_version_chain(dict(locked), version_number, previous_active)

        existing_version = conn.execute(
            """
            SELECT version_number, source_event_id
            FROM guide_operator_assignment_versions
            WHERE assignment_id = ? AND version_number = ?
            LIMIT 1
            """,
            (assignment_id, version_number),
        ).fetchone()
        if existing_version is not None:
            raise AssignmentConflictError(
                "Assignment version already exists with a different event."
            )

        previous_row = conn.execute(
            """
            SELECT working_package_json
            FROM guide_operator_assignment_versions
            WHERE assignment_id = ? AND version_number = ?
            LIMIT 1
            """,
            (assignment_id, previous_active),
        ).fetchone()
        if previous_row is None:
            raise AssignmentValidationError(
                "Previous active version snapshot is required."
            )
        locked_previous_package = _load_working_package_json(
            previous_row["working_package_json"]
        )
        locked_occupancy = _ordinary_occupancy_violations(
            assignment=dict(locked),
            previous_package=locked_previous_package,
            next_package=working_package,
        )
        if locked_occupancy:
            raise AssignmentValidationError(
                "Ordinary version must not change assignment dates, role, "
                "day set, or occupancy envelope.",
                details={"codes": locked_occupancy},
            )

        projection_tour_id = locked["projection_tour_id"]
        if projection_tour_id is None:
            raise AssignmentValidationError(
                "Accepted assignment must have a calendar projection."
            )
        received_at = _utc_now()
        title, city = _projection_labels(dict(locked), working_package)
        day_locations_json = _day_locations_json_from_package(working_package)

        conn.execute(
            """
            INSERT INTO guide_operator_version_inbox (
                event_id, assignment_id, guide_os_id, version_number,
                payload_hash, received_at, result_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'applied')
            """,
            (
                event_id,
                assignment_id,
                identity,
                version_number,
                payload_hash,
                received_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO guide_operator_assignment_versions (
                assignment_id, version_number, severity,
                working_package_json, published_at,
                change_summary_json, source_event_id
            ) VALUES (?, ?, 'ordinary', ?, ?, ?, ?)
            """,
            (
                assignment_id,
                version_number,
                json.dumps(working_package, ensure_ascii=False, sort_keys=True),
                published_at,
                json.dumps(change_summary, ensure_ascii=False, sort_keys=True),
                event_id,
            ),
        )
        conn.execute(
            """
            UPDATE guide_operator_assignments
            SET active_version_number = ?,
                active_version_unread = 1,
                updated_at = ?
            WHERE assignment_id = ? AND guide_os_id = ? AND status = 'accepted'
              AND active_version_number = ?
            """,
            (
                version_number,
                received_at,
                assignment_id,
                identity,
                previous_active,
            ),
        )
        updated = conn.execute(
            """
            SELECT status, active_version_number, active_version_unread,
                   projection_tour_id, start_date, end_date
            FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (assignment_id, identity),
        ).fetchone()
        if (
            updated is None
            or updated["status"] != "accepted"
            or int(updated["active_version_number"]) != version_number
        ):
            raise AssignmentNotActionableError(
                "Only an accepted assignment can receive an ordinary version."
            )

        conn.execute(
            """
            INSERT INTO go_operator_projection_metadata_update (tour_id)
            VALUES (?)
            """,
            (int(projection_tour_id),),
        )
        cursor = conn.execute(
            """
            UPDATE tours
            SET title = ?, city = ?, day_locations_json = ?
            WHERE id = ? AND source = ?
            """,
            (
                title,
                city,
                day_locations_json,
                int(projection_tour_id),
                SOURCE_GUIDE_OPERATOR,
            ),
        )
        if cursor.rowcount != 1:
            raise AssignmentValidationError(
                "Ordinary version must update exactly one protected projection."
            )
        projection = conn.execute(
            """
            SELECT start_date, end_date, user_id, status, source
            FROM tours
            WHERE id = ?
            LIMIT 1
            """,
            (int(projection_tour_id),),
        ).fetchone()
        if (
            projection is None
            or projection["start_date"] != locked["start_date"]
            or projection["end_date"] != locked["end_date"]
            or projection["source"] != SOURCE_GUIDE_OPERATOR
        ):
            raise AssignmentValidationError(
                "Ordinary version must keep calendar occupancy dates."
            )
        conn.execute(
            "DELETE FROM go_operator_projection_metadata_update WHERE tour_id = ?",
            (int(projection_tour_id),),
        )

        payload = {
            "assignment_id": assignment_id,
            "guide_os_id": identity,
            "version_number": version_number,
            "previous_active_version_number": previous_active,
            "severity": "ordinary",
            "source_event_id": event_id,
            "published_at": published_at,
            "applied_at": received_at,
        }
        conn.execute(
            """
            INSERT INTO guide_operator_outbox (
                event_id, event_type, aggregate_type, aggregate_id,
                guide_os_id, payload_json, created_at, delivered_at, attempt_count
            ) VALUES (?, ?, 'guide_assignment', ?, ?, ?, ?, NULL, 0)
            """,
            (
                event_id,
                ORDINARY_VERSION_ACK_EVENT_TYPE,
                assignment_id,
                identity,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                received_at,
            ),
        )
        insert_guide_operator_guide_notification(
            conn,
            source_event_id=event_id,
            guide_os_id=identity,
            notification_type="ordinary_version_change",
            company_name=str(locked["company_name"]),
            assignment_id=assignment_id,
            version_number=version_number,
            created_at=received_at,
        )

        if _ORDINARY_VERSION_FAILURE_HOOK is not None:
            _ORDINARY_VERSION_FAILURE_HOOK()

        return AssignmentOrdinaryVersionResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            status="accepted",
            version_number=version_number,
            previous_active_version_number=previous_active,
            source_event_id=event_id,
            unread=True,
            projection_tour_id=int(projection_tour_id),
            replayed=False,
        )

    return run_write_with_retry(operation)


def list_ordinary_version_ack_outbox(assignment_id: str) -> list[dict[str, Any]]:
    return list_guide_operator_outbox_events(
        assignment_id=assignment_id, event_type=ORDINARY_VERSION_ACK_EVENT_TYPE
    )


def intake_critical_assignment_version(
    event: AssignmentVersionPublishedIntake,
) -> AssignmentCriticalVersionIntakeResult:
    """Idempotently receive critical assignment.version.published.v1 without applying.

    Stores an immutable pending snapshot, sets pending_critical_version_number, and
    emits exactly one receipt acknowledgement. Does not change the active version,
    working package, calendar projection, dates, or unread state.
    """
    ensure_db_ready()
    normalized = _normalize_critical_version(event)
    payload_hash = _canonical_hash(normalized)
    identity = normalized["guide_os_id"]
    assignment_id = normalized["assignment_id"]
    event_id = normalized["event_id"]
    version_number = normalized["version_number"]
    previous_active = normalized["previous_active_version_number"]
    working_package = normalized["working_package"]
    change_summary = normalized["change_summary"]
    published_at = normalized["published_at"]

    existing_inbox = get_guide_operator_version_inbox(event_id)
    if existing_inbox is not None:
        if existing_inbox["payload_hash"] != payload_hash:
            raise AssignmentConflictError(
                "Version event ID was already used with another payload."
            )
        stored = get_guide_operator_assignment_for_guide(identity, assignment_id)
        if stored is None:
            raise AssignmentNotFoundError("Assignment was not found.")
        version_row = get_guide_operator_assignment_version(
            assignment_id, version_number
        )
        if version_row is None or version_row.get("source_event_id") != event_id:
            raise AssignmentValidationError(
                "Version inbox exists without the matching critical snapshot."
            )
        pending = stored.get("pending_critical_version_number")
        return AssignmentCriticalVersionIntakeResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            status=stored["status"],
            version_number=version_number,
            previous_active_version_number=previous_active,
            pending_critical_version_number=(
                int(pending) if pending is not None else None
            ),
            active_version_number=int(stored["active_version_number"]),
            source_event_id=event_id,
            unread=int(stored.get("active_version_unread") or 0) == 1,
            projection_tour_id=stored.get("projection_tour_id"),
            replayed=True,
        )

    assignment = get_assignment_for_guide(identity, assignment_id)
    _assert_critical_version_intake_chain(assignment, version_number, previous_active)
    previous_version = get_guide_operator_assignment_version(
        assignment_id, previous_active
    )
    if previous_version is None:
        raise AssignmentValidationError("Previous active version snapshot is required.")
    previous_package = _load_working_package_json(
        previous_version["working_package_json"]
    )
    _assert_critical_version_not_noop(previous_package, working_package, change_summary)

    def operation(conn):
        inbox = conn.execute(
            """
            SELECT * FROM guide_operator_version_inbox
            WHERE event_id = ? LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        if inbox is not None:
            if inbox["payload_hash"] != payload_hash:
                raise AssignmentConflictError(
                    "Version event ID was already used with another payload."
                )
            locked = conn.execute(
                """
                SELECT *
                FROM guide_operator_assignments
                WHERE assignment_id = ? AND guide_os_id = ?
                LIMIT 1
                """,
                (assignment_id, identity),
            ).fetchone()
            if locked is None:
                raise AssignmentNotFoundError("Assignment was not found.")
            version_row = conn.execute(
                """
                SELECT source_event_id
                FROM guide_operator_assignment_versions
                WHERE assignment_id = ? AND version_number = ?
                LIMIT 1
                """,
                (assignment_id, version_number),
            ).fetchone()
            if version_row is None or version_row["source_event_id"] != event_id:
                raise AssignmentValidationError(
                    "Version inbox exists without the matching critical snapshot."
                )
            pending = locked["pending_critical_version_number"]
            return AssignmentCriticalVersionIntakeResult(
                assignment_id=assignment_id,
                guide_os_id=identity,
                status=locked["status"],
                version_number=version_number,
                previous_active_version_number=previous_active,
                pending_critical_version_number=(
                    int(pending) if pending is not None else None
                ),
                active_version_number=int(locked["active_version_number"]),
                source_event_id=event_id,
                unread=int(locked["active_version_unread"] or 0) == 1,
                projection_tour_id=locked["projection_tour_id"],
                replayed=True,
            )

        locked = conn.execute(
            """
            SELECT *
            FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (assignment_id, identity),
        ).fetchone()
        if locked is None:
            raise AssignmentNotFoundError("Assignment was not found.")
        _assert_critical_version_intake_chain(
            dict(locked), version_number, previous_active
        )

        existing_version = conn.execute(
            """
            SELECT version_number, source_event_id
            FROM guide_operator_assignment_versions
            WHERE assignment_id = ? AND version_number = ?
            LIMIT 1
            """,
            (assignment_id, version_number),
        ).fetchone()
        if existing_version is not None:
            raise AssignmentConflictError(
                "Assignment version already exists with a different event."
            )

        previous_row = conn.execute(
            """
            SELECT working_package_json
            FROM guide_operator_assignment_versions
            WHERE assignment_id = ? AND version_number = ?
            LIMIT 1
            """,
            (assignment_id, previous_active),
        ).fetchone()
        if previous_row is None:
            raise AssignmentValidationError(
                "Previous active version snapshot is required."
            )
        locked_previous_package = _load_working_package_json(
            previous_row["working_package_json"]
        )
        _assert_critical_version_not_noop(
            locked_previous_package, working_package, change_summary
        )

        active_before = int(locked["active_version_number"])
        unread_before = int(locked["active_version_unread"] or 0)
        projection_before = locked["projection_tour_id"]
        start_before = locked["start_date"]
        end_before = locked["end_date"]
        role_before = locked["role"]
        received_at = _utc_now()

        conn.execute(
            """
            INSERT INTO guide_operator_version_inbox (
                event_id, assignment_id, guide_os_id, version_number,
                payload_hash, received_at, result_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'applied')
            """,
            (
                event_id,
                assignment_id,
                identity,
                version_number,
                payload_hash,
                received_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO guide_operator_assignment_versions (
                assignment_id, version_number, severity,
                working_package_json, published_at,
                change_summary_json, source_event_id
            ) VALUES (?, ?, 'critical', ?, ?, ?, ?)
            """,
            (
                assignment_id,
                version_number,
                json.dumps(working_package, ensure_ascii=False, sort_keys=True),
                published_at,
                json.dumps(change_summary, ensure_ascii=False, sort_keys=True),
                event_id,
            ),
        )
        conn.execute(
            """
            UPDATE guide_operator_assignments
            SET pending_critical_version_number = ?,
                updated_at = ?
            WHERE assignment_id = ? AND guide_os_id = ? AND status = 'accepted'
              AND active_version_number = ?
              AND pending_critical_version_number IS NULL
            """,
            (
                version_number,
                received_at,
                assignment_id,
                identity,
                previous_active,
            ),
        )
        updated = conn.execute(
            """
            SELECT status, active_version_number, active_version_unread,
                   pending_critical_version_number, projection_tour_id,
                   start_date, end_date, role
            FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (assignment_id, identity),
        ).fetchone()
        if (
            updated is None
            or updated["status"] != "accepted"
            or int(updated["active_version_number"]) != active_before
            or int(updated["active_version_unread"] or 0) != unread_before
            or updated["pending_critical_version_number"] is None
            or int(updated["pending_critical_version_number"]) != version_number
            or updated["projection_tour_id"] != projection_before
            or updated["start_date"] != start_before
            or updated["end_date"] != end_before
            or updated["role"] != role_before
        ):
            raise AssignmentNotActionableError(
                "Critical version intake could not be recorded without mutating "
                "the active assignment."
            )

        payload = {
            "assignment_id": assignment_id,
            "guide_os_id": identity,
            "version_number": version_number,
            "previous_active_version_number": previous_active,
            "severity": "critical",
            "source_event_id": event_id,
            "published_at": published_at,
            "received_at": received_at,
        }
        conn.execute(
            """
            INSERT INTO guide_operator_outbox (
                event_id, event_type, aggregate_type, aggregate_id,
                guide_os_id, payload_json, created_at, delivered_at, attempt_count
            ) VALUES (?, ?, 'guide_assignment', ?, ?, ?, ?, NULL, 0)
            """,
            (
                event_id,
                CRITICAL_VERSION_RECEIVED_ACK_EVENT_TYPE,
                assignment_id,
                identity,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                received_at,
            ),
        )
        insert_guide_operator_guide_notification(
            conn,
            source_event_id=event_id,
            guide_os_id=identity,
            notification_type="critical_confirmation_required",
            company_name=str(locked["company_name"]),
            assignment_id=assignment_id,
            version_number=version_number,
            created_at=received_at,
        )

        if _CRITICAL_VERSION_INTAKE_FAILURE_HOOK is not None:
            _CRITICAL_VERSION_INTAKE_FAILURE_HOOK()

        return AssignmentCriticalVersionIntakeResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            status="accepted",
            version_number=version_number,
            previous_active_version_number=previous_active,
            pending_critical_version_number=version_number,
            active_version_number=active_before,
            source_event_id=event_id,
            unread=unread_before == 1,
            projection_tour_id=projection_before,
            replayed=False,
        )

    return run_write_with_retry(operation)


def list_critical_version_received_ack_outbox(
    assignment_id: str,
) -> list[dict[str, Any]]:
    return list_guide_operator_outbox_events(
        assignment_id=assignment_id,
        event_type=CRITICAL_VERSION_RECEIVED_ACK_EVENT_TYPE,
    )


def decide_critical_assignment_version(
    guide_os_id: str,
    assignment_id: str,
    *,
    version_number: int,
    decision: str,
    decision_event_id: str,
    decided_at: str | None = None,
) -> AssignmentCriticalVersionDecisionResult:
    """Idempotently confirm or reject one pending critical assignment version.

    Reject keeps the previous active version/package/projection. Confirm validates
    proposed occupancy (excluding the current projection) and, when clear,
    activates the pending version and updates exactly one protected projection.
    Confirmed critical versions are treated as seen (no ordinary unread ack).
    """
    ensure_db_ready()
    identity = validate_guide_os_id(guide_os_id)
    assignment_id = _require_nonempty(assignment_id, "assignment_id")
    decision_event_id = _require_nonempty(decision_event_id, "decision_event_id")
    version_number = _require_int(version_number, "version_number", minimum=2)
    if decision not in {"confirm_critical", "reject_critical"}:
        raise AssignmentValidationError(
            "decision must be confirm_critical or reject_critical."
        )
    decided_at_value = decided_at or _utc_now()
    if decided_at is not None:
        decided_at_value = _require_iso_datetime(decided_at, "decided_at")

    owned = _guide_lifecycle_assignment(identity, assignment_id)
    target = get_guide_operator_assignment_version(assignment_id, version_number)
    explicit_target = (
        target is not None
        and _load_working_package_json(target["working_package_json"]).get("schema_version")
        == "assignment.working_package.v2"
    )
    if owned["projection_mode"] == "explicit_days" or explicit_target:
        result = _apply_explicit_projection_decision_local(
            identity, assignment_id, action=decision, version_number=version_number,
            event_id=decision_event_id, occurred_at=decided_at, public_replay=True,
        )
        return AssignmentCriticalVersionDecisionResult(
            assignment_id=assignment_id, guide_os_id=identity, status=result["status"],
            decision=decision, version_number=version_number,
            decision_event_id=result["decision_event_id"],
            pending_critical_version_number=result["pending_critical_version_number"],
            active_version_number=result["active_version_number"],
            projection_tour_id=result["projection_tour_id"], replayed=result["replayed"],
        )

    existing_by_event = get_guide_operator_critical_version_decision_by_event(
        decision_event_id
    )
    if existing_by_event is not None:
        return _replay_critical_version_decision(
            identity=identity,
            assignment_id=assignment_id,
            version_number=version_number,
            decision=decision,
            decision_event_id=decision_event_id,
            existing=existing_by_event,
        )

    existing_by_version = get_guide_operator_critical_version_decision(
        assignment_id=assignment_id, version_number=version_number
    )
    if existing_by_version is not None:
        if existing_by_version["guide_os_id"] != identity:
            raise AssignmentNotFoundError("Assignment was not found.")
        if existing_by_version["decision_type"] == decision:
            assignment = get_assignment_for_guide(identity, assignment_id)
            return AssignmentCriticalVersionDecisionResult(
                assignment_id=assignment_id,
                guide_os_id=identity,
                status=assignment["status"],
                decision=decision,
                version_number=version_number,
                decision_event_id=existing_by_version["decision_event_id"],
                pending_critical_version_number=_optional_int(
                    assignment.get("pending_critical_version_number")
                ),
                active_version_number=int(assignment["active_version_number"]),
                projection_tour_id=assignment.get("projection_tour_id"),
                replayed=True,
            )
        raise AssignmentConflictError(
            "Critical version already has a different decision."
        )

    assignment = get_assignment_for_guide(identity, assignment_id)
    if assignment["status"] == "cancelled":
        raise AssignmentNotActionableError(
            "Cancelled assignments cannot decide a critical version."
        )
    if assignment["status"] != "accepted":
        raise AssignmentNotActionableError(
            "Only an accepted assignment can decide a critical version."
        )
    pending = assignment.get("pending_critical_version_number")
    if pending is None or int(pending) != version_number:
        raise AssignmentConflictError(
            "Critical version is not the current pending version."
        )

    version = get_guide_operator_assignment_version(assignment_id, version_number)
    if version is None or version.get("severity") != "critical":
        raise AssignmentValidationError(
            "Pending critical version snapshot is required."
        )
    working_package = _load_working_package_json(version["working_package_json"])
    proposed = _critical_proposed_occupancy(
        working_package,
        assignment_id=assignment_id,
        guide_os_id=identity,
    )

    user_id = _require_user_id(identity)
    projection_tour_id = assignment.get("projection_tour_id")
    if projection_tour_id is None:
        raise AssignmentValidationError(
            "Accepted assignment must have a calendar projection."
        )

    if decision == "confirm_critical":
        conflicts = _calendar_conflicts(
            user_id,
            proposed["start_date"],
            proposed["end_date"],
            exclude_tour_id=int(projection_tour_id),
        )
        if conflicts:
            raise CalendarConflictError(
                "The critical version overlaps an existing calendar commitment.",
                details={"dates": conflicts},
            )

    def operation(conn):
        locked = conn.execute(
            """
            SELECT *
            FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (assignment_id, identity),
        ).fetchone()
        if locked is None:
            raise AssignmentNotFoundError("Assignment was not found.")
        if locked["status"] == "cancelled":
            raise AssignmentNotActionableError(
                "Cancelled assignments cannot decide a critical version."
            )
        if locked["status"] != "accepted":
            raise AssignmentNotActionableError(
                "Only an accepted assignment can decide a critical version."
            )

        prior_event = conn.execute(
            """
            SELECT *
            FROM guide_operator_critical_version_decisions
            WHERE decision_event_id = ?
            LIMIT 1
            """,
            (decision_event_id,),
        ).fetchone()
        if prior_event is not None:
            return _replay_critical_version_decision(
                identity=identity,
                assignment_id=assignment_id,
                version_number=version_number,
                decision=decision,
                decision_event_id=decision_event_id,
                existing=dict(prior_event),
                assignment_row=dict(locked),
            )

        prior_version = conn.execute(
            """
            SELECT *
            FROM guide_operator_critical_version_decisions
            WHERE assignment_id = ? AND version_number = ?
            LIMIT 1
            """,
            (assignment_id, version_number),
        ).fetchone()
        if prior_version is not None:
            if prior_version["decision_type"] == decision:
                return AssignmentCriticalVersionDecisionResult(
                    assignment_id=assignment_id,
                    guide_os_id=identity,
                    status=locked["status"],
                    decision=decision,
                    version_number=version_number,
                    decision_event_id=prior_version["decision_event_id"],
                    pending_critical_version_number=_optional_int(
                        locked["pending_critical_version_number"]
                    ),
                    active_version_number=int(locked["active_version_number"]),
                    projection_tour_id=locked["projection_tour_id"],
                    replayed=True,
                )
            raise AssignmentConflictError(
                "Critical version already has a different decision."
            )

        if (
            locked["pending_critical_version_number"] is None
            or int(locked["pending_critical_version_number"]) != version_number
        ):
            raise AssignmentConflictError(
                "Critical version is not the current pending version."
            )

        version_row = conn.execute(
            """
            SELECT severity, working_package_json
            FROM guide_operator_assignment_versions
            WHERE assignment_id = ? AND version_number = ?
            LIMIT 1
            """,
            (assignment_id, version_number),
        ).fetchone()
        if version_row is None or version_row["severity"] != "critical":
            raise AssignmentValidationError(
                "Pending critical version snapshot is required."
            )
        locked_package = _load_working_package_json(
            version_row["working_package_json"]
        )
        locked_proposed = _critical_proposed_occupancy(
            locked_package,
            assignment_id=assignment_id,
            guide_os_id=identity,
        )

        locked_projection_id = locked["projection_tour_id"]
        if locked_projection_id is None:
            raise AssignmentValidationError(
                "Accepted assignment must have a calendar projection."
            )

        if decision == "confirm_critical":
            conflicts = _calendar_conflicts(
                user_id,
                locked_proposed["start_date"],
                locked_proposed["end_date"],
                exclude_tour_id=int(locked_projection_id),
            )
            if conflicts:
                raise CalendarConflictError(
                    "The critical version overlaps an existing calendar commitment.",
                    details={"dates": conflicts},
                )

        conn.execute(
            """
            INSERT INTO guide_operator_critical_version_decisions (
                decision_event_id, assignment_id, guide_os_id,
                version_number, decision_type, decided_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_event_id,
                assignment_id,
                identity,
                version_number,
                decision,
                decided_at_value,
                decided_at_value,
            ),
        )

        active_before = int(locked["active_version_number"])
        if decision == "reject_critical":
            conn.execute(
                """
                UPDATE guide_operator_assignments
                SET pending_critical_version_number = NULL,
                    updated_at = ?
                WHERE assignment_id = ? AND guide_os_id = ? AND status = 'accepted'
                  AND pending_critical_version_number = ?
                """,
                (
                    decided_at_value,
                    assignment_id,
                    identity,
                    version_number,
                ),
            )
            updated = conn.execute(
                """
                SELECT status, active_version_number, pending_critical_version_number,
                       projection_tour_id, start_date, end_date, role,
                       active_version_unread
                FROM guide_operator_assignments
                WHERE assignment_id = ? AND guide_os_id = ?
                LIMIT 1
                """,
                (assignment_id, identity),
            ).fetchone()
            if (
                updated is None
                or updated["status"] != "accepted"
                or int(updated["active_version_number"]) != active_before
                or updated["pending_critical_version_number"] is not None
                or updated["projection_tour_id"] != locked_projection_id
                or updated["start_date"] != locked["start_date"]
                or updated["end_date"] != locked["end_date"]
                or updated["role"] != locked["role"]
            ):
                raise AssignmentNotActionableError(
                    "Critical version reject could not clear pending state."
                )
            active_after = active_before
            projection_after = int(locked_projection_id)
        else:
            title, city = _projection_labels(dict(locked), locked_package)
            day_locations_json = _day_locations_json_from_package(locked_package)
            conn.execute(
                """
                INSERT INTO go_operator_projection_occupancy_update (tour_id)
                VALUES (?)
                """,
                (int(locked_projection_id),),
            )
            cursor = conn.execute(
                """
                UPDATE tours
                SET title = ?, city = ?, start_date = ?, end_date = ?,
                    day_locations_json = ?
                WHERE id = ? AND source = ?
                """,
                (
                    title,
                    city,
                    locked_proposed["start_date"],
                    locked_proposed["end_date"],
                    day_locations_json,
                    int(locked_projection_id),
                    SOURCE_GUIDE_OPERATOR,
                ),
            )
            if cursor.rowcount != 1:
                raise AssignmentValidationError(
                    "Critical confirm must update exactly one protected projection."
                )
            projection = conn.execute(
                """
                SELECT start_date, end_date, user_id, status, source, note,
                       tour_group_id, income, payment_status
                FROM tours
                WHERE id = ?
                LIMIT 1
                """,
                (int(locked_projection_id),),
            ).fetchone()
            if (
                projection is None
                or projection["start_date"] != locked_proposed["start_date"]
                or projection["end_date"] != locked_proposed["end_date"]
                or projection["source"] != SOURCE_GUIDE_OPERATOR
                or projection["note"] != f"go_assignment:{assignment_id}"
                or projection["tour_group_id"] != assignment_id
                or projection["income"] is not None
            ):
                raise AssignmentValidationError(
                    "Critical confirm must keep protected projection identity."
                )
            conn.execute(
                "DELETE FROM go_operator_projection_occupancy_update WHERE tour_id = ?",
                (int(locked_projection_id),),
            )

            conn.execute(
                """
                UPDATE guide_operator_assignments
                SET active_version_number = ?,
                    role = ?,
                    start_date = ?,
                    end_date = ?,
                    pending_critical_version_number = NULL,
                    active_version_unread = 0,
                    updated_at = ?
                WHERE assignment_id = ? AND guide_os_id = ? AND status = 'accepted'
                  AND pending_critical_version_number = ?
                  AND active_version_number = ?
                """,
                (
                    version_number,
                    locked_proposed["role"],
                    locked_proposed["start_date"],
                    locked_proposed["end_date"],
                    decided_at_value,
                    assignment_id,
                    identity,
                    version_number,
                    active_before,
                ),
            )
            updated = conn.execute(
                """
                SELECT status, active_version_number, pending_critical_version_number,
                       projection_tour_id, start_date, end_date, role,
                       active_version_unread
                FROM guide_operator_assignments
                WHERE assignment_id = ? AND guide_os_id = ?
                LIMIT 1
                """,
                (assignment_id, identity),
            ).fetchone()
            if (
                updated is None
                or updated["status"] != "accepted"
                or int(updated["active_version_number"]) != version_number
                or updated["pending_critical_version_number"] is not None
                or updated["projection_tour_id"] != locked_projection_id
                or updated["start_date"] != locked_proposed["start_date"]
                or updated["end_date"] != locked_proposed["end_date"]
                or updated["role"] != locked_proposed["role"]
                or int(updated["active_version_unread"] or 0) != 0
            ):
                raise AssignmentNotActionableError(
                    "Critical version confirm could not activate pending state."
                )
            active_after = version_number
            projection_after = int(locked_projection_id)

        payload = {
            "assignment_id": assignment_id,
            "guide_os_id": identity,
            "decision": decision,
            "version_number": version_number,
            "decided_at": decided_at_value,
            "projection_tour_id": projection_after,
            "active_version_number": active_after,
        }
        conn.execute(
            """
            INSERT INTO guide_operator_outbox (
                event_id, event_type, aggregate_type, aggregate_id,
                guide_os_id, payload_json, created_at, delivered_at, attempt_count
            ) VALUES (?, ?, 'guide_assignment', ?, ?, ?, ?, NULL, 0)
            """,
            (
                decision_event_id,
                CRITICAL_VERSION_DECISION_EVENT_TYPE,
                assignment_id,
                identity,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                decided_at_value,
            ),
        )

        if _CRITICAL_VERSION_DECISION_FAILURE_HOOK is not None:
            _CRITICAL_VERSION_DECISION_FAILURE_HOOK()

        return AssignmentCriticalVersionDecisionResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            status="accepted",
            decision=decision,
            version_number=version_number,
            decision_event_id=decision_event_id,
            pending_critical_version_number=None,
            active_version_number=active_after,
            projection_tour_id=projection_after,
            replayed=False,
        )

    return run_write_with_retry(operation)


def list_critical_version_decision_outbox(assignment_id: str) -> list[dict[str, Any]]:
    return list_guide_operator_outbox_events(
        assignment_id=assignment_id,
        event_type=CRITICAL_VERSION_DECISION_EVENT_TYPE,
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _replay_critical_version_decision(
    *,
    identity: str,
    assignment_id: str,
    version_number: int,
    decision: str,
    decision_event_id: str,
    existing: dict[str, Any],
    assignment_row: dict[str, Any] | None = None,
) -> AssignmentCriticalVersionDecisionResult:
    if existing["guide_os_id"] != identity:
        raise AssignmentNotFoundError("Assignment was not found.")
    if existing["assignment_id"] != assignment_id:
        raise AssignmentConflictError(
            "Decision event ID was already used for another assignment."
        )
    if int(existing["version_number"]) != version_number:
        raise AssignmentConflictError(
            "Decision event ID was already used for another version."
        )
    if existing["decision_type"] != decision:
        raise AssignmentConflictError(
            "Decision event ID was already used with another decision."
        )
    if assignment_row is None:
        assignment_row = get_assignment_for_guide(identity, assignment_id)
    return AssignmentCriticalVersionDecisionResult(
        assignment_id=assignment_id,
        guide_os_id=identity,
        status=assignment_row["status"],
        decision=decision,
        version_number=version_number,
        decision_event_id=decision_event_id,
        pending_critical_version_number=_optional_int(
            assignment_row.get("pending_critical_version_number")
        ),
        active_version_number=int(assignment_row["active_version_number"]),
        projection_tour_id=assignment_row.get("projection_tour_id"),
        replayed=True,
    )


def _critical_proposed_occupancy(
    working_package: dict[str, Any],
    *,
    assignment_id: str,
    guide_os_id: str,
) -> dict[str, str]:
    validated = _validate_working_package_snapshot(
        working_package,
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
    )
    assignment = validated["assignment"]
    return {
        "role": str(assignment["role"]).strip(),
        "start_date": assignment["start_date"],
        "end_date": assignment["end_date"],
    }


def list_version_acknowledged_outbox(assignment_id: str) -> list[dict[str, Any]]:
    return list_guide_operator_outbox_events(
        assignment_id=assignment_id, event_type=VERSION_ACKNOWLEDGED_EVENT_TYPE
    )


def build_assignment_detail_for_guide(
    guide_os_id: str, assignment_id: str
) -> dict[str, Any]:
    """Assemble guide-facing assignment detail with active package and history."""
    assignment = read_guide_operator_assignment_for_guide(guide_os_id, assignment_id)
    if assignment is None:
        raise AssignmentNotFoundError("Assignment was not found.")
    active_number = int(assignment["active_version_number"])
    versions = list_guide_operator_assignment_versions(assignment_id)
    if not versions:
        raise AssignmentValidationError("Assignment versions are required.")

    version_payloads: list[dict[str, Any]] = []
    active_payload: dict[str, Any] | None = None
    for row in versions:
        change_summary = _parse_change_summary(row.get("change_summary_json"))
        package = _load_working_package_json(row["working_package_json"])
        payload = {
            "version_number": int(row["version_number"]),
            "severity": row["severity"],
            "published_at": row["published_at"],
            "change_summary": change_summary,
            "working_package": package,
            "source_event_id": row.get("source_event_id"),
        }
        version_payloads.append(payload)
        if int(row["version_number"]) == active_number:
            active_payload = payload

    if active_payload is None:
        raise AssignmentValidationError("Active assignment version snapshot is required.")

    unread = int(assignment.get("active_version_unread") or 0) == 1
    if assignment["status"] == "cancelled":
        conflicts: list[str] = []
    elif assignment["projection_mode"] == "explicit_days":
        with get_db_connection() as conn:
            conflicts = _daily_conflicts(
                conn, assignment, _explicit_scope(assignment, active_payload["working_package"]),
                _require_user_id(guide_os_id),
            )
    else:
        conflicts = find_assignment_conflicts(guide_os_id, assignment_id)

    pending_critical = _pending_critical_version_for_detail(
        assignment=assignment,
        guide_os_id=guide_os_id,
        versions=version_payloads,
    )

    return {
        "assignment": assignment,
        "working_package": active_payload["working_package"],
        "conflict_dates": conflicts,
        "active_version": {
            "version_number": active_payload["version_number"],
            "severity": active_payload["severity"],
            "published_at": active_payload["published_at"],
            "change_summary": active_payload["change_summary"],
            "unread": unread and active_payload["severity"] == "ordinary",
            "source_event_id": active_payload["source_event_id"],
        },
        "pending_critical_version": pending_critical,
        "versions": version_payloads,
    }


def _pending_critical_version_for_detail(
    *,
    assignment: dict[str, Any],
    guide_os_id: str,
    versions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    pending_raw = assignment.get("pending_critical_version_number")
    if pending_raw is None:
        return None
    pending_number = int(pending_raw)
    pending_payload = next(
        (row for row in versions if int(row["version_number"]) == pending_number),
        None,
    )
    if pending_payload is None or pending_payload.get("severity") != "critical":
        raise AssignmentValidationError(
            "Pending critical version snapshot is required."
        )

    conflict_dates: list[str] = []
    if assignment["status"] == "accepted" and assignment["projection_mode"] == "explicit_days":
        with get_db_connection() as conn:
            conflict_dates = _daily_conflicts(
                conn, assignment, _explicit_scope(assignment, pending_payload["working_package"]),
                _require_user_id(guide_os_id),
            )
    elif (
        assignment["status"] == "accepted"
        and pending_payload["working_package"].get("schema_version") == "assignment.working_package.v2"
    ):
        with get_db_connection() as conn:
            user_id = _require_user_id(guide_os_id)
            legacy_id = _validated_legacy_transition(conn, assignment, pending_number, user_id)
            explicit = {
                **assignment, "projection_mode": "explicit_days",
                "operator_tour_id": pending_payload["working_package"]["tour"]["id"],
            }
            conflict_dates = _daily_conflicts(
                conn, explicit, _explicit_scope(explicit, pending_payload["working_package"]),
                user_id, exclude_projection_ids={legacy_id},
            )
    elif assignment["status"] == "accepted":
        projection_tour_id = assignment.get("projection_tour_id")
        if projection_tour_id is None:
            raise AssignmentValidationError(
                "Accepted assignment must have a calendar projection."
            )
        proposed = _critical_proposed_occupancy(
            pending_payload["working_package"],
            assignment_id=assignment["assignment_id"],
            guide_os_id=guide_os_id,
        )
        user_id = _require_user_id(guide_os_id)
        conflict_dates = _calendar_conflicts(
            user_id,
            proposed["start_date"],
            proposed["end_date"],
            exclude_tour_id=int(projection_tour_id),
        )

    return {
        "version_number": pending_payload["version_number"],
        "severity": pending_payload["severity"],
        "published_at": pending_payload["published_at"],
        "change_summary": pending_payload["change_summary"],
        "working_package": pending_payload["working_package"],
        "source_event_id": pending_payload.get("source_event_id"),
        "conflict_dates": conflict_dates,
    }


def acknowledge_ordinary_version(
    guide_os_id: str,
    assignment_id: str,
    *,
    version_number: int,
    decision_event_id: str,
    acknowledged_at: str | None = None,
) -> AssignmentVersionAcknowledgeResult:
    """Idempotently acknowledge reading the active ordinary version.

    Clears unread and writes exactly one assignment.version.acknowledged.v1 outbox
    event. Does not change calendar occupancy or working-package contents.
    """
    ensure_db_ready()
    identity = validate_guide_os_id(guide_os_id)
    assignment_id = _require_nonempty(assignment_id, "assignment_id")
    decision_event_id = _require_nonempty(decision_event_id, "decision_event_id")
    if not isinstance(version_number, int) or isinstance(version_number, bool):
        raise AssignmentValidationError("version_number must be an integer.")
    if version_number < 1:
        raise AssignmentValidationError("version_number must be >= 1.")

    existing_by_event = get_guide_operator_version_acknowledgement(
        decision_event_id=decision_event_id
    )
    if existing_by_event is not None:
        if existing_by_event["guide_os_id"] != identity:
            raise AssignmentNotFoundError("Assignment was not found.")
        if existing_by_event["assignment_id"] != assignment_id:
            raise AssignmentConflictError(
                "Acknowledgement event ID was already used for another assignment."
            )
        if int(existing_by_event["version_number"]) != version_number:
            raise AssignmentConflictError(
                "Acknowledgement event ID was already used for another version."
            )
        return AssignmentVersionAcknowledgeResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            version_number=version_number,
            decision_event_id=decision_event_id,
            unread=False,
            replayed=True,
        )

    existing_by_version = get_guide_operator_version_acknowledgement(
        assignment_id=assignment_id, version_number=version_number
    )
    if existing_by_version is not None:
        if existing_by_version["guide_os_id"] != identity:
            raise AssignmentNotFoundError("Assignment was not found.")
        return AssignmentVersionAcknowledgeResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            version_number=version_number,
            decision_event_id=existing_by_version["decision_event_id"],
            unread=False,
            replayed=True,
        )

    assignment = _guide_lifecycle_assignment(identity, assignment_id)
    if assignment["status"] == "cancelled":
        raise AssignmentNotActionableError(
            "Cancelled assignments cannot be acknowledged."
        )
    if assignment["status"] != "accepted":
        raise AssignmentNotActionableError(
            "Only an accepted assignment version can be acknowledged."
        )
    if int(assignment["active_version_number"]) != version_number:
        raise AssignmentConflictError(
            "Acknowledgement version does not match the active assignment version."
        )
    version = get_guide_operator_assignment_version(assignment_id, version_number)
    if version is None:
        raise AssignmentNotFoundError("Assignment version was not found.")
    if version["severity"] == "critical":
        raise AssignmentNotActionableError(
            "Critical versions cannot be acknowledged as ordinary reads."
        )
    if version["severity"] != "ordinary":
        raise AssignmentNotActionableError(
            "Only an ordinary active version can be acknowledged."
        )
    if int(assignment.get("active_version_unread") or 0) != 1:
        raise AssignmentNotActionableError(
            "Active version has no unread ordinary change to acknowledge."
        )

    acknowledged_at_value = acknowledged_at or _utc_now()

    def operation(conn):
        prior_event = conn.execute(
            """
            SELECT *
            FROM guide_operator_version_acknowledgements
            WHERE decision_event_id = ?
            LIMIT 1
            """,
            (decision_event_id,),
        ).fetchone()
        if prior_event is not None:
            if prior_event["guide_os_id"] != identity:
                raise AssignmentNotFoundError("Assignment was not found.")
            if prior_event["assignment_id"] != assignment_id:
                raise AssignmentConflictError(
                    "Acknowledgement event ID was already used for another assignment."
                )
            if int(prior_event["version_number"]) != version_number:
                raise AssignmentConflictError(
                    "Acknowledgement event ID was already used for another version."
                )
            return AssignmentVersionAcknowledgeResult(
                assignment_id=assignment_id,
                guide_os_id=identity,
                version_number=version_number,
                decision_event_id=decision_event_id,
                unread=False,
                replayed=True,
            )

        prior_version = conn.execute(
            """
            SELECT *
            FROM guide_operator_version_acknowledgements
            WHERE assignment_id = ? AND version_number = ?
            LIMIT 1
            """,
            (assignment_id, version_number),
        ).fetchone()
        if prior_version is not None:
            if prior_version["guide_os_id"] != identity:
                raise AssignmentNotFoundError("Assignment was not found.")
            return AssignmentVersionAcknowledgeResult(
                assignment_id=assignment_id,
                guide_os_id=identity,
                version_number=version_number,
                decision_event_id=prior_version["decision_event_id"],
                unread=False,
                replayed=True,
            )

        locked = conn.execute(
            """
            SELECT *
            FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (assignment_id, identity),
        ).fetchone()
        if locked is None:
            raise AssignmentNotFoundError("Assignment was not found.")
        if locked["status"] != "accepted":
            raise AssignmentNotActionableError(
                "Only an accepted assignment version can be acknowledged."
            )
        if int(locked["active_version_number"]) != version_number:
            raise AssignmentConflictError(
                "Acknowledgement version does not match the active assignment version."
            )
        if int(locked["active_version_unread"] or 0) != 1:
            raise AssignmentNotActionableError(
                "Active version has no unread ordinary change to acknowledge."
            )

        locked_version = conn.execute(
            """
            SELECT severity
            FROM guide_operator_assignment_versions
            WHERE assignment_id = ? AND version_number = ?
            LIMIT 1
            """,
            (assignment_id, version_number),
        ).fetchone()
        if locked_version is None:
            raise AssignmentNotFoundError("Assignment version was not found.")
        if locked_version["severity"] == "critical":
            raise AssignmentNotActionableError(
                "Critical versions cannot be acknowledged as ordinary reads."
            )
        if locked_version["severity"] != "ordinary":
            raise AssignmentNotActionableError(
                "Only an ordinary active version can be acknowledged."
            )

        if locked["projection_mode"] == "explicit_days":
            _require_daily_decision_event_id(decision_event_id)
            _assert_daily_event_available(conn, decision_event_id)
        received_at = _utc_now()
        conn.execute(
            """
            INSERT INTO guide_operator_version_acknowledgements (
                decision_event_id, assignment_id, guide_os_id,
                version_number, acknowledged_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                decision_event_id,
                assignment_id,
                identity,
                version_number,
                acknowledged_at_value,
                received_at,
            ),
        )
        conn.execute(
            """
            UPDATE guide_operator_assignments
            SET active_version_unread = 0,
                updated_at = ?
            WHERE assignment_id = ? AND guide_os_id = ?
              AND status = 'accepted'
              AND active_version_number = ?
              AND active_version_unread = 1
            """,
            (received_at, assignment_id, identity, version_number),
        )
        updated = conn.execute(
            """
            SELECT active_version_unread
            FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (assignment_id, identity),
        ).fetchone()
        if updated is None or int(updated["active_version_unread"] or 0) != 0:
            raise AssignmentNotActionableError(
                "Active version has no unread ordinary change to acknowledge."
            )

        payload = {
            "assignment_id": assignment_id,
            "guide_os_id": identity,
            "version_number": version_number,
            "acknowledged_at": acknowledged_at_value,
            "decision_event_id": decision_event_id,
        }
        conn.execute(
            """
            INSERT INTO guide_operator_outbox (
                event_id, event_type, aggregate_type, aggregate_id,
                guide_os_id, payload_json, created_at, delivered_at, attempt_count
            ) VALUES (?, ?, 'guide_assignment', ?, ?, ?, ?, NULL, 0)
            """,
            (
                decision_event_id,
                VERSION_ACKNOWLEDGED_EVENT_TYPE,
                assignment_id,
                identity,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                received_at,
            ),
        )

        if _VERSION_ACK_FAILURE_HOOK is not None:
            _VERSION_ACK_FAILURE_HOOK()

        return AssignmentVersionAcknowledgeResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            version_number=version_number,
            decision_event_id=decision_event_id,
            unread=False,
            replayed=False,
        )

    return run_write_with_retry(operation)


def _parse_change_summary(raw: Any) -> list[Any]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _decide_assignment(
    guide_os_id: str,
    assignment_id: str,
    *,
    decision: str,
    decision_event_id: str,
    decided_at: str | None,
) -> AssignmentDecisionResult:
    ensure_db_ready()
    identity = validate_guide_os_id(guide_os_id)
    assignment_id = _require_nonempty(assignment_id, "assignment_id")
    decision_event_id = _require_nonempty(decision_event_id, "decision_event_id")
    if decision not in {"accept", "decline"}:
        raise AssignmentValidationError("decision must be accept or decline.")

    owned = _guide_lifecycle_assignment(identity, assignment_id)
    if owned["projection_mode"] == "explicit_days":
        result = _apply_explicit_projection_decision_local(
            identity, assignment_id, action=decision, version_number=1,
            event_id=decision_event_id, occurred_at=decided_at, public_replay=True,
        )
        return AssignmentDecisionResult(
            assignment_id=assignment_id, guide_os_id=identity, status=result["status"],
            decision=decision, decision_event_id=result["decision_event_id"],
            projection_tour_id=None, replayed=result["replayed"],
        )

    existing_decision = get_guide_operator_decision(assignment_id)
    if existing_decision is not None:
        if existing_decision["guide_os_id"] != identity:
            raise AssignmentNotFoundError("Assignment was not found.")
        if existing_decision["decision_event_id"] != decision_event_id:
            if existing_decision["decision_type"] == decision:
                assignment = get_assignment_for_guide(identity, assignment_id)
                return AssignmentDecisionResult(
                    assignment_id=assignment_id,
                    guide_os_id=identity,
                    status=assignment["status"],
                    decision=existing_decision["decision_type"],
                    decision_event_id=existing_decision["decision_event_id"],
                    projection_tour_id=assignment.get("projection_tour_id"),
                    replayed=True,
                )
            raise AssignmentConflictError(
                "Assignment already has a different decision."
            )
        if existing_decision["decision_type"] != decision:
            raise AssignmentConflictError(
                "Decision event ID was already used with another decision."
            )
        assignment = get_assignment_for_guide(identity, assignment_id)
        return AssignmentDecisionResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            status=assignment["status"],
            decision=decision,
            decision_event_id=decision_event_id,
            projection_tour_id=assignment.get("projection_tour_id"),
            replayed=True,
        )

    assignment = get_assignment_for_guide(identity, assignment_id)
    if assignment["status"] != "offered":
        raise AssignmentNotActionableError("Assignment offer is not actionable.")

    user_id = _require_user_id(identity)
    decided_at_value = decided_at or _utc_now()
    version = get_guide_operator_assignment_version(assignment_id, 1)
    if version is None:
        raise AssignmentValidationError("Immutable version 1 is required.")

    if decision == "accept":
        conflicts = _calendar_conflicts(
            user_id, assignment["start_date"], assignment["end_date"]
        )
        if conflicts:
            raise CalendarConflictError(
                "The assignment overlaps an existing calendar commitment.",
                details={"dates": conflicts},
            )

    working_package = json.loads(version["working_package_json"])
    title, city = _projection_labels(assignment, working_package)

    def operation(conn):
        locked = conn.execute(
            """
            SELECT *
            FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (assignment_id, identity),
        ).fetchone()
        if locked is None:
            raise AssignmentNotFoundError("Assignment was not found.")
        if locked["status"] != "offered":
            prior = conn.execute(
                """
                SELECT * FROM guide_operator_assignment_decisions
                WHERE assignment_id = ? LIMIT 1
                """,
                (assignment_id,),
            ).fetchone()
            if prior is not None and prior["decision_type"] == decision:
                return AssignmentDecisionResult(
                    assignment_id=assignment_id,
                    guide_os_id=identity,
                    status=locked["status"],
                    decision=decision,
                    decision_event_id=prior["decision_event_id"],
                    projection_tour_id=locked["projection_tour_id"],
                    replayed=True,
                )
            raise AssignmentNotActionableError("Assignment offer is not actionable.")

        event_row = conn.execute(
            """
            SELECT * FROM guide_operator_assignment_decisions
            WHERE decision_event_id = ? LIMIT 1
            """,
            (decision_event_id,),
        ).fetchone()
        if event_row is not None:
            if event_row["assignment_id"] != assignment_id:
                raise AssignmentConflictError(
                    "Decision event ID was already used for another assignment."
                )
            return AssignmentDecisionResult(
                assignment_id=assignment_id,
                guide_os_id=identity,
                status=locked["status"],
                decision=event_row["decision_type"],
                decision_event_id=decision_event_id,
                projection_tour_id=locked["projection_tour_id"],
                replayed=True,
            )

        projection_tour_id = None
        if decision == "accept":
            conflicts = _calendar_conflicts(
                user_id, locked["start_date"], locked["end_date"]
            )
            if conflicts:
                raise CalendarConflictError(
                    "The assignment overlaps an existing calendar commitment.",
                    details={"dates": conflicts},
                )
            day_locations_json = _day_locations_json_from_package(working_package)
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
                    locked["company_name"],
                    city,
                    locked["start_date"],
                    locked["end_date"],
                    STATUS_CONFIRMED,
                    PAYMENT_UNPAID,
                    f"go_assignment:{assignment_id}",
                    ENTRY_TYPE_TOUR,
                    assignment_id,
                    title,
                    SOURCE_GUIDE_OPERATOR,
                    day_locations_json,
                ),
            )
            projection_tour_id = int(cursor.lastrowid)
            projection_count = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM tours
                WHERE source = ? AND note = ?
                """,
                (SOURCE_GUIDE_OPERATOR, f"go_assignment:{assignment_id}"),
            ).fetchone()["cnt"]
            if int(projection_count) != 1:
                raise AssignmentValidationError(
                    "Acceptance must create exactly one calendar projection."
                )

        status = "accepted" if decision == "accept" else "declined"
        conn.execute(
            """
            INSERT INTO guide_operator_assignment_decisions (
                decision_event_id, assignment_id, guide_os_id,
                decision_type, version_number, decided_at, created_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                decision_event_id,
                assignment_id,
                identity,
                decision,
                decided_at_value,
                decided_at_value,
            ),
        )
        conn.execute(
            """
            UPDATE guide_operator_assignments
            SET status = ?,
                projection_tour_id = ?,
                decided_at = ?,
                updated_at = ?
            WHERE assignment_id = ? AND guide_os_id = ? AND status = 'offered'
            """,
            (
                status,
                projection_tour_id,
                decided_at_value,
                decided_at_value,
                assignment_id,
                identity,
            ),
        )
        updated = conn.execute(
            """
            SELECT status, projection_tour_id
            FROM guide_operator_assignments
            WHERE assignment_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (assignment_id, identity),
        ).fetchone()
        if updated is None or updated["status"] != status:
            raise AssignmentNotActionableError("Assignment offer is not actionable.")
        if decision == "accept" and updated["projection_tour_id"] != projection_tour_id:
            raise AssignmentValidationError(
                "Acceptance must create exactly one calendar projection."
            )

        payload = {
            "assignment_id": assignment_id,
            "guide_os_id": identity,
            "decision": decision,
            "version_number": 1,
            "decided_at": decided_at_value,
            "projection_tour_id": projection_tour_id,
        }
        conn.execute(
            """
            INSERT INTO guide_operator_outbox (
                event_id, event_type, aggregate_type, aggregate_id,
                guide_os_id, payload_json, created_at, delivered_at, attempt_count
            ) VALUES (?, 'assignment.decision.v1', 'guide_assignment', ?, ?, ?, ?, NULL, 0)
            """,
            (
                decision_event_id,
                assignment_id,
                identity,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                decided_at_value,
            ),
        )

        if _ACCEPT_FAILURE_HOOK is not None and decision == "accept":
            _ACCEPT_FAILURE_HOOK()

        return AssignmentDecisionResult(
            assignment_id=assignment_id,
            guide_os_id=identity,
            status=status,
            decision=decision,
            decision_event_id=decision_event_id,
            projection_tour_id=projection_tour_id,
            replayed=False,
        )

    return run_write_with_retry(operation)


def list_decision_outbox(assignment_id: str) -> list[dict[str, Any]]:
    return list_guide_operator_outbox_events(
        assignment_id=assignment_id, event_type="assignment.decision.v1"
    )


def _normalize_offer(offer: AssignmentOfferIntake) -> dict[str, Any]:
    _require_legacy_package(offer.working_package)
    if not isinstance(offer, AssignmentOfferIntake):
        raise AssignmentValidationError("Offer payload must be AssignmentOfferIntake.")
    event_id = _require_nonempty(offer.event_id, "event_id")
    assignment_id = _require_nonempty(offer.assignment_id, "assignment_id")
    guide_os_id = validate_guide_os_id(offer.guide_os_id)
    company_id = _require_nonempty(offer.company_id, "company_id")
    company_name = _require_nonempty(offer.company_name, "company_name")
    guide_connection_id = _require_nonempty(
        offer.guide_connection_id, "guide_connection_id"
    )
    role = _require_nonempty(offer.role, "role")
    start_date = _require_iso_date(offer.start_date, "start_date")
    end_date = _require_iso_date(offer.end_date, "end_date")
    if end_date < start_date:
        raise AssignmentValidationError("end_date must not precede start_date.")
    if offer.version_number != 1:
        raise AssignmentValidationError("GO6A accepts only immutable version 1.")
    if not isinstance(offer.working_package, dict) or not offer.working_package:
        raise AssignmentValidationError("working_package is required.")
    response_deadline = offer.response_deadline
    if response_deadline is not None:
        response_deadline = _require_nonempty(response_deadline, "response_deadline")
    operator_message = offer.operator_message
    if operator_message is not None:
        operator_message = operator_message.strip() or None
    offered_at = offer.offered_at
    if offered_at is not None:
        offered_at = _require_iso_datetime(offered_at, "offered_at")
    return {
        "event_id": event_id,
        "assignment_id": assignment_id,
        "guide_os_id": guide_os_id,
        "company_id": company_id,
        "company_name": company_name,
        "guide_connection_id": guide_connection_id,
        "role": role,
        "start_date": start_date,
        "end_date": end_date,
        "response_deadline": response_deadline,
        "operator_message": operator_message,
        "version_number": 1,
        "working_package": offer.working_package,
        "offered_at": offered_at,
    }


def _projection_labels(
    assignment: dict[str, Any], working_package: dict[str, Any]
) -> tuple[str, str]:
    tour = working_package.get("tour")
    title = assignment["company_name"]
    city = "—"
    if isinstance(tour, dict):
        raw_title = tour.get("title") or tour.get("reference")
        if isinstance(raw_title, str) and raw_title.strip():
            title = raw_title.strip()
        raw_city = tour.get("city_or_route")
        if isinstance(raw_city, str) and raw_city.strip():
            city = raw_city.strip()
    return title, city


def _day_locations_json_from_package(working_package: dict[str, Any]) -> str | None:
    """Map working-package day cities into tours.day_locations_json for calendar UX."""
    days = working_package.get("days")
    if not isinstance(days, list):
        return None
    locations: dict[str, str] = {}
    for raw in days:
        if not isinstance(raw, dict):
            continue
        date = raw.get("date")
        city = raw.get("city_or_route") or raw.get("cityOrRoute")
        if not isinstance(date, str) or not date.strip():
            continue
        if not isinstance(city, str) or not city.strip():
            continue
        locations[date.strip()] = city.strip()
    if not locations:
        return None
    return json.dumps(locations, ensure_ascii=False)


def _require_user_id(guide_os_id: str) -> int:
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    if user_id is None:
        raise AssignmentValidationError(
            "Unknown guide_os_id; integration boundary fail-closed.",
            details={"code": "integration_unavailable"},
        )
    return user_id


def _require_nonempty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssignmentValidationError(f"{field} is required.")
    return value.strip()


def _require_iso_date(value: str, field: str) -> str:
    text = _require_nonempty(value, field)
    if _ISO_DATE.fullmatch(text) is None:
        raise AssignmentValidationError(f"{field} must be YYYY-MM-DD.")
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise AssignmentValidationError(f"{field} must be a valid date.") from exc
    return text


def _require_iso_datetime(value: str, field: str) -> str:
    text = _require_nonempty(value, field)
    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AssignmentValidationError(
            f"{field} must be a valid ISO-8601 timestamp."
        ) from exc
    return text


def _normalize_cancellation(
    event: AssignmentCancellationIntake,
) -> dict[str, Any]:
    if not isinstance(event, AssignmentCancellationIntake):
        raise AssignmentValidationError(
            "Cancellation payload must be AssignmentCancellationIntake."
        )
    event_id = _require_nonempty(event.event_id, "event_id")
    assignment_id = _require_nonempty(event.assignment_id, "assignment_id")
    guide_os_id = validate_guide_os_id(event.guide_os_id)
    if not isinstance(event.version_number, int) or isinstance(
        event.version_number, bool
    ):
        raise AssignmentValidationError("version_number must be an integer.")
    if event.version_number < 1:
        raise AssignmentValidationError("version_number must be >= 1.")
    cancelled_at = _require_iso_datetime(event.cancelled_at, "cancelled_at")
    return {
        "event_id": event_id,
        "assignment_id": assignment_id,
        "guide_os_id": guide_os_id,
        "version_number": event.version_number,
        "cancelled_at": cancelled_at,
    }


def _normalize_assignment_lifecycle(
    event: AssignmentLifecycleIntake,
) -> dict[str, Any]:
    if not isinstance(event, AssignmentLifecycleIntake):
        raise AssignmentValidationError(
            "Lifecycle payload must be AssignmentLifecycleIntake."
        )
    statuses = {
        "assignment.withdrawn.v1": "withdrawn",
        "assignment.expired.v1": "expired",
    }
    event_type = _require_nonempty(event.event_type, "event_type")
    status = statuses.get(event_type)
    if status is None:
        raise AssignmentValidationError("Unsupported assignment lifecycle event.")
    return {
        "event_id": _require_nonempty(event.event_id, "event_id"),
        "event_type": event_type,
        "assignment_id": _require_nonempty(event.assignment_id, "assignment_id"),
        "guide_os_id": validate_guide_os_id(event.guide_os_id),
        "transitioned_at": _require_iso_datetime(
            event.transitioned_at, "transitioned_at"
        ),
        "status": status,
    }


def _normalize_ordinary_version(
    event: AssignmentVersionPublishedIntake,
) -> dict[str, Any]:
    if not isinstance(event, AssignmentVersionPublishedIntake):
        raise AssignmentValidationError(
            "Version payload must be AssignmentVersionPublishedIntake."
        )
    event_id = _require_nonempty(event.event_id, "event_id")
    assignment_id = _require_nonempty(event.assignment_id, "assignment_id")
    guide_os_id = validate_guide_os_id(event.guide_os_id)
    version_number = _require_int(event.version_number, "version_number", minimum=2)
    previous_active = _require_int(
        event.previous_active_version_number,
        "previous_active_version_number",
        minimum=1,
    )
    if event.severity != "ordinary":
        raise AssignmentValidationError(
            "GO7D1 accepts only ordinary assignment versions."
        )
    if not isinstance(event.working_package, dict) or not event.working_package:
        raise AssignmentValidationError("working_package is required.")
    if not isinstance(event.change_summary, list):
        raise AssignmentValidationError("change_summary must be a list.")
    published_at = _require_iso_datetime(event.published_at, "published_at")
    working_package = _validate_working_package_snapshot(
        event.working_package,
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
    )
    return {
        "event_id": event_id,
        "assignment_id": assignment_id,
        "guide_os_id": guide_os_id,
        "version_number": version_number,
        "previous_active_version_number": previous_active,
        "severity": "ordinary",
        "working_package": working_package,
        "change_summary": event.change_summary,
        "published_at": published_at,
    }


def _normalize_critical_version(
    event: AssignmentVersionPublishedIntake,
) -> dict[str, Any]:
    if not isinstance(event, AssignmentVersionPublishedIntake):
        raise AssignmentValidationError(
            "Version payload must be AssignmentVersionPublishedIntake."
        )
    event_id = _require_nonempty(event.event_id, "event_id")
    assignment_id = _require_nonempty(event.assignment_id, "assignment_id")
    guide_os_id = validate_guide_os_id(event.guide_os_id)
    version_number = _require_int(event.version_number, "version_number", minimum=2)
    previous_active = _require_int(
        event.previous_active_version_number,
        "previous_active_version_number",
        minimum=1,
    )
    if event.severity != "critical":
        raise AssignmentValidationError(
            "GO7E1 accepts only critical assignment versions."
        )
    if not isinstance(event.working_package, dict) or not event.working_package:
        raise AssignmentValidationError("working_package is required.")
    published_at = _require_iso_datetime(event.published_at, "published_at")
    working_package = _validate_working_package_snapshot(
        event.working_package,
        assignment_id=assignment_id,
        guide_os_id=guide_os_id,
    )
    change_summary = _validate_critical_change_summary(event.change_summary)
    return {
        "event_id": event_id,
        "assignment_id": assignment_id,
        "guide_os_id": guide_os_id,
        "version_number": version_number,
        "previous_active_version_number": previous_active,
        "severity": "critical",
        "working_package": working_package,
        "change_summary": change_summary,
        "published_at": published_at,
    }


def _validate_critical_change_summary(change_summary: Any) -> list[dict[str, Any]]:
    if not isinstance(change_summary, list):
        raise AssignmentValidationError("change_summary must be a list.")
    if not change_summary:
        raise AssignmentValidationError(
            "Critical version change_summary must not be empty."
        )
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(change_summary):
        if not isinstance(item, dict) or not item:
            raise AssignmentValidationError(
                f"change_summary[{index}] must be a structured object."
            )
        code = item.get("code")
        path = item.get("path")
        if not isinstance(code, str) or not code.strip():
            raise AssignmentValidationError(
                f"change_summary[{index}].code is required."
            )
        if not isinstance(path, str) or not path.strip():
            raise AssignmentValidationError(
                f"change_summary[{index}].path is required."
            )
        severity = item.get("severity")
        if severity is not None and severity not in {
            "critical",
            "ordinary",
            "uncertain",
        }:
            raise AssignmentValidationError(
                f"change_summary[{index}].severity is invalid."
            )
        normalized.append(item)
    return normalized


def _assert_critical_version_intake_chain(
    assignment: dict[str, Any],
    version_number: int,
    previous_active: int,
) -> None:
    if assignment["status"] == "cancelled":
        raise AssignmentNotActionableError(
            "Cancelled assignments cannot receive a critical version."
        )
    if assignment["status"] != "accepted":
        raise AssignmentNotActionableError(
            "Only an accepted assignment can receive a critical version."
        )
    pending = assignment.get("pending_critical_version_number")
    if pending is not None:
        raise AssignmentConflictError(
            "Another critical version is already pending for this assignment."
        )
    active_version = int(assignment["active_version_number"])
    if previous_active != active_version:
        raise AssignmentConflictError(
            "Previous active version does not match the current assignment version."
        )
    if version_number != active_version + 1:
        raise AssignmentConflictError(
            "Assignment version number is not the next monotonic version."
        )


def _assert_critical_version_not_noop(
    previous_package: dict[str, Any],
    next_package: dict[str, Any],
    change_summary: list[dict[str, Any]],
) -> None:
    if not change_summary:
        raise AssignmentValidationError(
            "Critical version change_summary must not be empty."
        )
    if _canonical_hash(previous_package) == _canonical_hash(next_package):
        raise AssignmentValidationError(
            "Critical version must change the working package snapshot."
        )


def _validate_working_package_snapshot(
    working_package: dict[str, Any],
    *,
    assignment_id: str,
    guide_os_id: str,
) -> dict[str, Any]:
    _require_legacy_package(working_package)
    assignment = working_package.get("assignment")
    if not isinstance(assignment, dict) or not assignment:
        raise AssignmentValidationError("working_package.assignment is required.")
    package_assignment_id = _require_nonempty(
        assignment.get("id") if isinstance(assignment.get("id"), str) else "",
        "working_package.assignment.id",
    )
    if package_assignment_id != assignment_id:
        raise AssignmentValidationError(
            "working_package.assignment.id must match assignment_id."
        )
    raw_guide_os_id = assignment.get("guide_os_id")
    if not isinstance(raw_guide_os_id, str) or not raw_guide_os_id.strip():
        raise AssignmentValidationError(
            "working_package.assignment.guide_os_id is required."
        )
    if validate_guide_os_id(raw_guide_os_id) != guide_os_id:
        raise AssignmentValidationError(
            "working_package.assignment.guide_os_id must match guide_os_id."
        )
    _require_nonempty(
        assignment.get("role") if isinstance(assignment.get("role"), str) else "",
        "working_package.assignment.role",
    )
    start_date = _require_iso_date(
        assignment.get("start_date")
        if isinstance(assignment.get("start_date"), str)
        else "",
        "working_package.assignment.start_date",
    )
    end_date = _require_iso_date(
        assignment.get("end_date") if isinstance(assignment.get("end_date"), str) else "",
        "working_package.assignment.end_date",
    )
    if end_date < start_date:
        raise AssignmentValidationError(
            "working_package assignment end_date must not precede start_date."
        )
    _working_package_day_map(working_package)
    return working_package


def _assert_ordinary_version_chain(
    assignment: dict[str, Any],
    version_number: int,
    previous_active: int,
) -> None:
    if assignment["status"] != "accepted":
        raise AssignmentNotActionableError(
            "Only an accepted assignment can receive an ordinary version."
        )
    active_version = int(assignment["active_version_number"])
    if previous_active != active_version:
        raise AssignmentConflictError(
            "Previous active version does not match the current assignment version."
        )
    if version_number != active_version + 1:
        raise AssignmentConflictError(
            "Assignment version number is not the next monotonic version."
        )


def _load_working_package_json(raw: str) -> dict[str, Any]:
    try:
        loaded = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AssignmentValidationError(
            "Stored working package snapshot is malformed."
        ) from exc
    if not isinstance(loaded, dict) or not loaded:
        raise AssignmentValidationError("Stored working package snapshot is malformed.")
    return loaded


def _ordinary_occupancy_violations(
    *,
    assignment: dict[str, Any],
    previous_package: dict[str, Any],
    next_package: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    previous_assignment = _as_mapping(previous_package.get("assignment"))
    next_assignment = _as_mapping(next_package.get("assignment"))
    if (
        assignment.get("role") != next_assignment.get("role")
        or previous_assignment.get("role") != next_assignment.get("role")
    ):
        violations.append("assignment_role")
    next_dates = (
        next_assignment.get("start_date"),
        next_assignment.get("end_date"),
    )
    if (assignment.get("start_date"), assignment.get("end_date")) != next_dates:
        violations.append("assignment_dates")
    elif (
        previous_assignment.get("start_date"),
        previous_assignment.get("end_date"),
    ) != next_dates:
        violations.append("assignment_dates")

    previous_days = _working_package_day_map(previous_package)
    next_days = _working_package_day_map(next_package)
    if set(previous_days) != set(next_days):
        violations.append("day_set")
    for day_date in sorted(set(previous_days) & set(next_days)):
        if _occupancy_envelope(
            _day_events(previous_days[day_date])
        ) != _occupancy_envelope(_day_events(next_days[day_date])):
            violations.append("occupancy_envelope")
            break
    return violations


def _working_package_day_map(working_package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    days = working_package.get("days")
    if not isinstance(days, list):
        raise AssignmentValidationError("working_package.days must be a list.")
    mapped: dict[str, dict[str, Any]] = {}
    for raw in days:
        if not isinstance(raw, dict):
            raise AssignmentValidationError(
                "working_package.days entries must be objects."
            )
        raw_date = raw.get("date")
        if not isinstance(raw_date, str):
            raise AssignmentValidationError("working_package.days date is required.")
        day_date = _require_iso_date(raw_date, "working_package.days.date")
        if day_date in mapped:
            raise AssignmentValidationError(
                "working_package.days must not contain duplicate dates."
            )
        mapped[day_date] = raw
    return mapped


def _day_events(day: dict[str, Any]) -> list[dict[str, Any]]:
    events = day.get("events")
    if events is None:
        return []
    if not isinstance(events, list):
        raise AssignmentValidationError("working_package day events must be a list.")
    normalized: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            raise AssignmentValidationError("working_package events must be objects.")
        normalized.append(event)
    return normalized


def _occupancy_envelope(
    events: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    starts = [str(event["start_time"]) for event in events if event.get("start_time")]
    ends = [str(event["end_time"]) for event in events if event.get("end_time")]
    min_start = min(starts) if starts else None
    if ends:
        max_end = max(ends)
    elif starts:
        max_end = max(starts)
    else:
        max_end = None
    return min_start, max_end


def _as_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _require_int(value: object, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssignmentValidationError(f"{field} must be an integer.")
    if value < minimum:
        raise AssignmentValidationError(f"{field} must be >= {minimum}.")
    return value


def _calendar_conflicts(
    user_id: int,
    start_date: str,
    end_date: str,
    *,
    exclude_tour_id: int | None = None,
) -> list[str]:
    conflict_dates: set[str] = set()
    for day in days_in_range(start_date, end_date):
        conflict_dates.update(
            get_conflicting_dates(
                user_id,
                day,
                exclude_tour_id=exclude_tour_id,
            )
        )
    return sorted(conflict_dates)


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require_legacy_package(package: object) -> None:
    """V1 intake must never interpret an explicit scope as its range envelope."""
    if isinstance(package, dict) and (
        package.get("schema_version") is not None
        or any(
            isinstance(day, dict) and "tour_day_id" in day
            for day in (package.get("days") if isinstance(package.get("days"), list) else [])
        )
    ):
        raise AssignmentValidationError("Explicit-day intake is disabled in stage 2A.")


def _explicit_scope(assignment: dict, package: dict, *, local_money_enabled: bool = False) -> list[tuple[str, str]]:
    """Validate only the local projection scope, not the future wire DTO."""
    from uuid import UUID

    detail = package.get("assignment", {})
    if (
        assignment["projection_mode"] != "explicit_days"
        or not assignment.get("operator_tour_id")
        or package.get("tour", {}).get("id") != assignment["operator_tour_id"]
        or package.get("company_id") != assignment["company_id"]
        or detail.get("id") != assignment["assignment_id"]
        or detail.get("guide_os_id") != assignment["guide_os_id"]
        or (package.get("remuneration") is not None and local_money_enabled is not True)
    ):
        raise AssignmentValidationError("Invalid local explicit identity or unsupported money.")
    if detail.get("role") not in {
        "main_guide",
        "accompanying_guide",
        "local_guide",
        "meet_and_greet",
        "other",
    }:
        raise AssignmentValidationError("Invalid explicit role.")
    scope = []
    for day in package.get("days", []):
        key = day.get("tour_day_id")
        try:
            parsed = UUID(key)
        except (ValueError, TypeError, AttributeError) as exc:
            raise AssignmentValidationError("Invalid stable day identity.") from exc
        if parsed.version != 4 or str(parsed) != key:
            raise AssignmentValidationError("Invalid stable day identity.")
        scope.append((key, _require_iso_date(day.get("date"), "date")))
    if (
        not scope
        or len({key for key, _ in scope}) != len(scope)
        or (len({value for _, value in scope}) != len(scope))
    ):
        raise AssignmentValidationError("Explicit scope must have unique days and dates.")
    dates = [value for _, value in scope]
    if detail.get("start_date") != min(dates) or detail.get("end_date") != max(dates):
        raise AssignmentValidationError("Explicit envelope must match selected dates.")
    if local_money_enabled is True:
        from services.guide_operator_remuneration_service import validate_remuneration

        validate_remuneration(package, scope)
    return sorted(scope, key=lambda item: (item[1], item[0]))


def _daily_links(conn, assignment_id: str) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM guide_operator_daily_projections WHERE assignment_id=? "
            "ORDER BY calendar_date,tour_day_id",
            (assignment_id,),
        )
    ]


def _daily_conflicts(
    conn,
    assignment: dict,
    scope: list[tuple[str, str]],
    user_id: int,
    *,
    exclude_projection_ids: set[int] | None = None,
) -> list[str]:
    conflicts = []
    for _, value in scope:
        rows = conn.execute(
            "SELECT * FROM tours WHERE user_id=? AND start_date<=? AND end_date>=?",
            (user_id, value, value),
        ).fetchall()
        for row in rows:
            if exclude_projection_ids and row["id"] in exclude_projection_ids:
                continue
            peer = conn.execute(
                "SELECT d.*, a.status FROM guide_operator_daily_projections d "
                "JOIN guide_operator_assignments a ON a.assignment_id=d.assignment_id "
                "WHERE d.projection_tour_id=?",
                (row["id"],),
            ).fetchone()
            if (
                peer is not None
                and row["source"] == SOURCE_GUIDE_OPERATOR
                and row["entry_type"] == ENTRY_TYPE_TOUR
                and peer["status"] == "accepted"
                and peer["source_service"] == SOURCE_GUIDE_OPERATOR
                and peer["guide_os_id"] == assignment["guide_os_id"]
                and peer["company_id"] == assignment["company_id"]
                and peer["operator_tour_id"] == assignment["operator_tour_id"]
            ):
                continue
            conflicts.append(value)
            break
    return sorted(set(conflicts))


def _release_daily_row(conn, projection_id: int, user_id: int) -> None:
    conn.execute("INSERT INTO go_operator_projection_release(tour_id) VALUES (?)", (projection_id,))
    removed = conn.execute(
        "DELETE FROM tours WHERE id=? AND user_id=? AND source=?",
        (projection_id, user_id, SOURCE_GUIDE_OPERATOR),
    )
    if removed.rowcount != 1:
        raise AssignmentValidationError("Daily projection identity is inconsistent.")
    conn.execute("DELETE FROM go_operator_projection_release WHERE tour_id=?", (projection_id,))


def _replace_daily_projections(
    conn, assignment: dict, package: dict, version: int, user_id: int, scope: list[tuple[str, str]]
) -> None:
    old = {row["tour_day_id"]: row for row in _daily_links(conn, assignment["assignment_id"])}
    desired = {key for key, _ in scope}
    # Remove only mutable links first: permits date swaps under immediate UNIQUE
    # constraints while retaining the protected calendar ID of a retained day.
    conn.execute(
        "DELETE FROM guide_operator_daily_projections WHERE assignment_id=?",
        (assignment["assignment_id"],),
    )
    for key, row in old.items():
        if key not in desired:
            _release_daily_row(conn, row["projection_tour_id"], user_id)
    title, city = _projection_labels(assignment, package)
    for key, value in scope:
        if key in old:
            projection_id = old[key]["projection_tour_id"]
            conn.execute(
                "INSERT INTO go_operator_projection_occupancy_update(tour_id) VALUES (?)",
                (projection_id,),
            )
            updated = conn.execute(
                "UPDATE tours SET title=?,city=?,start_date=?,end_date=? "
                "WHERE id=? AND user_id=? AND source=?",
                (title, city, value, value, projection_id, user_id, SOURCE_GUIDE_OPERATOR),
            )
            if updated.rowcount != 1:
                raise AssignmentValidationError("Daily projection is missing.")
            conn.execute(
                "DELETE FROM go_operator_projection_occupancy_update WHERE tour_id=?",
                (projection_id,),
            )
        else:
            result = conn.execute(
                "INSERT INTO tours(user_id,company,city,start_date,end_date,status,income,"
                "payment_status,note,entry_type,tour_group_id,title,source) "
                "VALUES (?,?,?,?,?,?,NULL,?,?,?,?,?,?)",
                (
                    user_id,
                    assignment["company_name"],
                    city,
                    value,
                    value,
                    STATUS_CONFIRMED,
                    PAYMENT_UNPAID,
                    f"go_assignment:{assignment['assignment_id']}",
                    ENTRY_TYPE_TOUR,
                    f"{assignment['assignment_id']}:{key}",
                    title,
                    SOURCE_GUIDE_OPERATOR,
                ),
            )
            projection_id = result.lastrowid
        conn.execute(
            "INSERT INTO guide_operator_daily_projections(source_service,company_id,assignment_id,"
            "guide_os_id,operator_tour_id,tour_day_id,calendar_date,active_version_number,"
            "projection_tour_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                SOURCE_GUIDE_OPERATOR,
                assignment["company_id"],
                assignment["assignment_id"],
                assignment["guide_os_id"],
                assignment["operator_tour_id"],
                key,
                value,
                version,
                projection_id,
            ),
        )


def _apply_explicit_projection_decision_local(
    guide_os_id: str,
    assignment_id: str,
    *,
    action: str,
    version_number: int,
    event_id: str,
    occurred_at: str | None,
    public_replay: bool = False,
    wire_cancellation: bool = False,
    local_money_enabled: bool = False,
) -> dict:
    """Atomic daily decisions shared by local and session-bound lifecycle calls.

    Prepared immutable offer/pending snapshots must already exist locally.
    Legacy-to-explicit confirmation requires independently validated v2 intake.
    Decisions, projection set and held outbox share BEGIN IMMEDIATE and rollback.
    Stage 5A.1 money opt-in is local only: no public/wire caller may enable it.
    """
    if local_money_enabled is not False and (
        local_money_enabled is not True or public_replay or wire_cancellation
    ):
        raise AssignmentValidationError("Money application is local-only and default-off.")
    ensure_db_ready()
    identity = validate_guide_os_id(guide_os_id)
    event_id = _require_nonempty(event_id, "event_id")
    version_number = _require_int(version_number, "version_number", minimum=1)
    if occurred_at is not None:
        occurred_at = _require_iso_datetime(occurred_at, "occurred_at")
    if public_replay:
        _require_daily_decision_event_id(event_id)
    if action not in {"accept", "decline", "confirm_critical", "reject_critical", "cancel"}:
        raise AssignmentValidationError("Unsupported local action.")
    request_hash = _canonical_hash(
        dict(
            guide_os_id=identity,
            assignment_id=assignment_id,
            action=action,
            version_number=version_number,
            event_id=event_id,
            occurred_at=occurred_at,
        )
    )

    if wire_cancellation:
        if action != "cancel" or public_replay or occurred_at is None:
            raise AssignmentValidationError("Invalid wire cancellation dispatch.")
        _require_terminal_aware_time(occurred_at)
        # Exactly the existing v1 normalizer/hash, recorded in this transaction.
        request_hash = _canonical_hash(_normalize_cancellation(AssignmentCancellationIntake(
            event_id=event_id, assignment_id=assignment_id, guide_os_id=identity,
            version_number=version_number, cancelled_at=occurred_at,
        )))

    # Generated evidence time is excluded from retry identity when no time was supplied.
    occurred_at = occurred_at or _utc_now()

    def operation(conn):
        raw = conn.execute(
            "SELECT * FROM guide_operator_assignments WHERE assignment_id=? AND guide_os_id=?",
            (assignment_id, identity),
        ).fetchone()
        if raw is None:
            raise AssignmentNotFoundError("Assignment was not found.")
        assignment = dict(raw)
        transitioning = (
            assignment["projection_mode"] == "legacy_range"
            and action in {"confirm_critical", "reject_critical"}
        )
        if not transitioning and (
            assignment["projection_mode"] != "explicit_days"
            or assignment["projection_tour_id"] is not None
        ):
            raise AssignmentValidationError(
                "Local daily operation requires an explicit assignment."
            )
        # Public/wire entry points never opt into local money, including replay.
        if local_money_enabled is not True:
            if conn.execute(
                "SELECT 1 FROM guide_operator_remuneration_versions WHERE assignment_id=?",
                (assignment_id,),
            ).fetchone():
                raise AssignmentValidationError("Agreed remuneration capability is disabled.")
            targets = {version_number, assignment["active_version_number"]}
            for target in targets:
                snapshot = conn.execute(
                    "SELECT working_package_json FROM guide_operator_assignment_versions "
                    "WHERE assignment_id=? AND version_number=?", (assignment_id, target),
                ).fetchone()
                if snapshot and _load_working_package_json(snapshot["working_package_json"]).get("remuneration") is not None:
                    raise AssignmentValidationError("Agreed remuneration capability is disabled.")
        prior = conn.execute(
            "SELECT * FROM guide_operator_daily_operation_inbox WHERE event_id=?", (event_id,)
        ).fetchone()
        if prior:
            if prior["payload_hash"] != request_hash:
                raise AssignmentConflictError("Local decision event ID was reused.")
            if wire_cancellation:
                inbox = conn.execute(
                    "SELECT * FROM guide_operator_cancellation_inbox WHERE event_id=?", (event_id,)
                ).fetchone()
                if (
                    assignment["status"] != "cancelled"
                    or assignment["cancellation_event_id"] != event_id
                    or assignment["active_version_number"] != version_number
                    or assignment["cancelled_at"] != occurred_at
                    or inbox is None or inbox["payload_hash"] != request_hash
                    or inbox["assignment_id"] != assignment_id or inbox["guide_os_id"] != identity
                ):
                    raise AssignmentValidationError("Inconsistent retained cancellation evidence.")
            result = json.loads(prior["result_json"])
            return {
                **result,
                "status": assignment["status"],
                "active_version_number": assignment["active_version_number"],
                "replayed": True,
                **(_public_daily_state(assignment, result.get("decision_event_id", event_id)) if public_replay else {}),
            }
        if public_replay:
            table = (
                "guide_operator_assignment_decisions" if action in {"accept", "decline"}
                else "guide_operator_critical_version_decisions"
            )
            record = conn.execute(
                f"SELECT * FROM {table} WHERE assignment_id=? AND version_number=?",
                (assignment_id, version_number),
            ).fetchone()
            if record is not None:
                if record["guide_os_id"] != identity or record["decision_type"] != action:
                    raise AssignmentConflictError("Assignment version already has a different decision.")
                if event_id != record["decision_event_id"]:
                    _assert_daily_event_available(conn, event_id)
                return {
                    "assignment_id": assignment_id, "replayed": True,
                    **_public_daily_state(assignment, record["decision_event_id"]),
                }
        if conn.execute(
            "SELECT 1 FROM guide_operator_outbox WHERE event_id=?", (event_id,)
        ).fetchone():
            raise AssignmentConflictError("Event identity is already reserved.")
        for inbox in (
            "guide_operator_offer_inbox", "guide_operator_version_inbox",
            "guide_operator_cancellation_inbox", "guide_operator_assignment_lifecycle_inbox",
        ):
            if conn.execute(f"SELECT 1 FROM {inbox} WHERE event_id=?", (event_id,)).fetchone():
                raise AssignmentConflictError("Decision event identity is already reserved.")
        if assignment["status"] == "cancelled":
            raise AssignmentNotActionableError("Cancellation is terminal.")
        accepting = action in {"accept", "decline"}
        if accepting:
            if assignment["status"] != "offered" or version_number != 1:
                raise AssignmentNotActionableError("Explicit offer is not actionable.")
            if (
                assignment["active_version_number"] != 1
                or assignment["pending_critical_version_number"] is not None
            ):
                raise AssignmentValidationError("Invalid offered version state.")
            connection = conn.execute(
                "SELECT * FROM guide_operator_connections WHERE connection_id=?",
                (assignment["guide_connection_id"],),
            ).fetchone()
            if (
                connection is None
                or connection["status"] != "confirmed"
                or connection["guide_os_id"] != identity
                or connection["company_id"] != assignment["company_id"]
            ):
                raise AssignmentValidationError("Confirmed connection required.")
        elif assignment["status"] != "accepted":
            raise AssignmentNotActionableError("An accepted explicit assignment is required.")
        critical = action in {"confirm_critical", "reject_critical"}
        if critical and (assignment["pending_critical_version_number"] != version_number):
            raise AssignmentNotActionableError("Exact pending critical version required.")
        if critical:
            numbers = [
                row[0]
                for row in conn.execute(
                    "SELECT version_number FROM guide_operator_assignment_versions "
                    "WHERE assignment_id=? ORDER BY version_number",
                    (assignment_id,),
                )
            ]
            if version_number <= assignment["active_version_number"] or numbers != list(
                range(1, version_number + 1)
            ):
                raise AssignmentValidationError("Explicit version chain has a gap or stale target.")
        if action == "cancel" and assignment["active_version_number"] != version_number:
            raise AssignmentConflictError("Cancellation version mismatch.")
        user = conn.execute("SELECT user_id FROM users WHERE guide_os_id=?", (identity,)).fetchone()
        if user is None:
            raise AssignmentValidationError("Unknown guide identity.")
        user_id = user["user_id"]
        actual_ids = {
            row[0]
            for row in conn.execute(
                "SELECT id FROM tours WHERE source=? AND note=?",
                (SOURCE_GUIDE_OPERATOR, f"go_assignment:{assignment_id}"),
            )
        }
        legacy_id = None
        if transitioning:
            legacy_id = _validated_legacy_transition(conn, assignment, version_number, user_id)
        linked_ids = (
            {legacy_id} if transitioning
            else {row["projection_tour_id"] for row in _daily_links(conn, assignment_id)}
        )
        if actual_ids != linked_ids or (accepting and actual_ids):
            raise AssignmentValidationError("Unexpected protected rows; repair is gated.")
        if not accepting and not transitioning:
            active = conn.execute(
                "SELECT working_package_json FROM guide_operator_assignment_versions "
                "WHERE assignment_id=? AND version_number=?",
                (assignment_id, assignment["active_version_number"]),
            ).fetchone()
            if active is None:
                raise AssignmentValidationError("Active snapshot is missing.")
            active_package = _load_working_package_json(active["working_package_json"])
            expected = _explicit_scope(assignment, active_package, local_money_enabled=local_money_enabled)
            if local_money_enabled is True:
                from services.guide_operator_remuneration_service import (
                    validate_effective,
                )

                validate_effective(conn, assignment, active_package, expected)
            actual = _daily_links(conn, assignment_id)
            if {(r["tour_day_id"], r["calendar_date"]) for r in actual} != set(expected):
                raise AssignmentValidationError(
                    "Effective daily set is inconsistent; repair is gated."
                )
            for link in actual:
                row = conn.execute(
                    "SELECT * FROM tours WHERE id=?", (link["projection_tour_id"],)
                ).fetchone()
                if (
                    row is None
                    or row["source"] != SOURCE_GUIDE_OPERATOR
                    or row["user_id"] != user_id
                    or row["start_date"] != link["calendar_date"]
                    or row["end_date"] != link["calendar_date"]
                    or row["note"] != f"go_assignment:{assignment_id}"
                    or link["active_version_number"] != assignment["active_version_number"]
                ):
                    raise AssignmentValidationError("Effective daily row is inconsistent.")
                if row["income"] is not None or row["payment_status"] != PAYMENT_UNPAID:
                    raise AssignmentValidationError("Financially populated projection requires a compatible history flow.")
        recorded_at = _utc_now() if wire_cancellation else occurred_at
        if action == "cancel":
            links = _daily_links(conn, assignment_id)
            if wire_cancellation:
                _guard_explicit_terminal_identity(conn, assignment)
                for link in links:
                    row = conn.execute("SELECT * FROM tours WHERE id=?", (link["projection_tour_id"],)).fetchone()
                    if (
                        row is None or row["entry_type"] != ENTRY_TYPE_TOUR
                        or row["status"] != STATUS_CONFIRMED
                        or row["start_time"] is not None or row["end_time"] is not None
                        or row["tour_group_id"] != f"{assignment_id}:{link['tour_day_id']}"
                        or link["company_id"] != assignment["company_id"]
                        or link["guide_os_id"] != identity
                        or link["operator_tour_id"] != assignment["operator_tour_id"]
                    ):
                        raise AssignmentValidationError("Unsafe protected projection identity.")
                    if row["income"] is not None or row["payment_status"] != PAYMENT_UNPAID:
                        raise AssignmentValidationError(
                            "Financially populated projection requires a compatible history flow."
                        )
            conn.execute(
                "DELETE FROM guide_operator_daily_projections WHERE assignment_id=?",
                (assignment_id,),
            )
            for link in links:
                _release_daily_row(conn, link["projection_tour_id"], user_id)
            conn.execute(
                "UPDATE guide_operator_assignments SET status='cancelled',cancelled_at=?,"
                "cancellation_event_id=?,pending_critical_version_number=NULL,updated_at=? "
                "WHERE assignment_id=?",
                (occurred_at, event_id, recorded_at, assignment_id),
            )
            conn.execute(
                "INSERT INTO guide_operator_cancellation_inbox(event_id,assignment_id,guide_os_id,"
                "version_number,payload_hash,received_at,result_status) VALUES (?,?,?,?,?,?,'applied')",
                (event_id, assignment_id, identity, version_number, request_hash, recorded_at),
            )
            if local_money_enabled is True:
                from services.guide_operator_remuneration_service import close_cancelled

                close_cancelled(conn, assignment_id, occurred_at)
            payload = dict(
                assignment_id=assignment_id,
                guide_os_id=identity,
                version_number=version_number,
                cancelled_at=occurred_at,
                source_event_id=event_id,
            )
            event_type = CANCELLATION_ACK_EVENT_TYPE
            hook = _CANCEL_FAILURE_HOOK
        else:
            if action == "decline":
                conn.execute(
                    "UPDATE guide_operator_assignments SET status='declined',decided_at=?,updated_at=? "
                    "WHERE assignment_id=?", (occurred_at, occurred_at, assignment_id)
                )
            elif action != "reject_critical":
                version = conn.execute(
                    "SELECT * FROM guide_operator_assignment_versions "
                    "WHERE assignment_id=? AND version_number=?",
                    (assignment_id, version_number),
                ).fetchone()
                if version is None or version["severity"] != (
                    "initial" if accepting else "critical"
                ):
                    raise AssignmentValidationError("Immutable target snapshot is missing.")
                package = json.loads(version["working_package_json"])
                if transitioning:
                    assignment = {
                        **assignment, "projection_mode": "explicit_days",
                        "projection_tour_id": None, "operator_tour_id": package["tour"]["id"],
                    }
                scope = _explicit_scope(assignment, package, local_money_enabled=local_money_enabled)
                conflicts = _daily_conflicts(
                    conn, assignment, scope, user_id,
                    exclude_projection_ids={legacy_id} if transitioning else None,
                )
                if conflicts:
                    raise CalendarConflictError(
                        "Explicit days overlap calendar commitments.", details={"dates": conflicts}
                    )
                if transitioning:
                    conn.execute(
                        "UPDATE guide_operator_assignments SET projection_mode='explicit_days',"
                        "projection_tour_id=NULL,operator_tour_id=? WHERE assignment_id=?",
                        (package["tour"]["id"], assignment_id),
                    )
                    _release_daily_row(conn, legacy_id, user_id)
                _replace_daily_projections(
                    conn, assignment, package, version_number, user_id, scope
                )
                if local_money_enabled is True:
                    from services.guide_operator_remuneration_service import (
                        apply_agreement,
                    )

                    apply_agreement(conn, assignment, package, scope, version_number, occurred_at)
                conn.execute(
                    "UPDATE guide_operator_assignments SET status='accepted',active_version_number=?,"
                    "start_date=?,end_date=?,role=?,pending_critical_version_number=NULL,"
                    "active_version_unread=0,decided_at=COALESCE(decided_at,?),updated_at=? WHERE assignment_id=?",
                    (
                        version_number,
                        scope[0][1],
                        scope[-1][1],
                        package["assignment"]["role"],
                        occurred_at,
                        occurred_at,
                        assignment_id,
                    ),
                )
            else:
                conn.execute(
                    "UPDATE guide_operator_assignments SET pending_critical_version_number=NULL,"
                    "updated_at=? WHERE assignment_id=?",
                    (occurred_at, assignment_id),
                )
            table = (
                "guide_operator_assignment_decisions"
                if accepting
                else "guide_operator_critical_version_decisions"
            )
            conn.execute(
                f"INSERT INTO {table}(decision_event_id,assignment_id,guide_os_id,version_number,"
                "decision_type,decided_at,created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    event_id,
                    assignment_id,
                    identity,
                    version_number,
                    action,
                    occurred_at,
                    occurred_at,
                ),
            )
            payload = dict(
                assignment_id=assignment_id,
                guide_os_id=identity,
                version_number=version_number,
                decision=action,
                decided_at=occurred_at,
                projection_tour_id=None,
            )
            if critical:
                payload["active_version_number"] = (
                    assignment["active_version_number"]
                    if action == "reject_critical"
                    else version_number
                )
            event_type = (
                "assignment.decision.v1" if accepting else CRITICAL_VERSION_DECISION_EVENT_TYPE
            )
            hook = _ACCEPT_FAILURE_HOOK if accepting else _CRITICAL_VERSION_DECISION_FAILURE_HOOK
        conn.execute(
            "INSERT INTO guide_operator_outbox(event_id,event_type,aggregate_type,aggregate_id,"
            "guide_os_id,payload_json,created_at,attempt_count) VALUES (?,?,'guide_assignment',?,?,?,?,0)",
            (
                event_id,
                event_type,
                assignment_id,
                identity,
                json.dumps(payload, sort_keys=True),
                recorded_at,
            ),
        )
        if wire_cancellation:
            insert_guide_operator_guide_notification(
                conn, source_event_id=event_id, guide_os_id=identity,
                notification_type="assignment_cancellation",
                company_name=assignment["company_name"], assignment_id=assignment_id,
                version_number=version_number, created_at=recorded_at,
            )
        current = conn.execute(
            "SELECT status,active_version_number FROM guide_operator_assignments "
            "WHERE assignment_id=?",
            (assignment_id,),
        ).fetchone()
        result = dict(
            assignment_id=assignment_id,
            status=current["status"],
            active_version_number=current["active_version_number"],
            replayed=False,
        )
        if public_replay:
            current_assignment = dict(conn.execute(
                "SELECT * FROM guide_operator_assignments WHERE assignment_id=?", (assignment_id,)
            ).fetchone())
            result.update(_public_daily_state(current_assignment, event_id))
        conn.execute(
            "INSERT INTO guide_operator_daily_operation_inbox VALUES (?,?,?,?)",
            (event_id, assignment_id, request_hash, json.dumps(result, sort_keys=True)),
        )
        if hook is not None:
            hook()
        return result

    return run_write_with_retry(operation)


def _validated_legacy_transition(conn, assignment, target_version, user_id):
    """Prove the old obligation before a confirmed transition; never infer day IDs."""
    from services.guide_operator_assignment_v2_contract import uuid, validate_package

    target = conn.execute(
        "SELECT severity,working_package_json FROM guide_operator_assignment_versions "
        "WHERE assignment_id=? AND version_number=?",
        (assignment["assignment_id"], target_version),
    ).fetchone()
    active = conn.execute(
        "SELECT working_package_json FROM guide_operator_assignment_versions "
        "WHERE assignment_id=? AND version_number=?",
        (assignment["assignment_id"], assignment["active_version_number"]),
    ).fetchone()
    consent = conn.execute(
        "SELECT 1 FROM guide_operator_assignment_decisions WHERE assignment_id=? "
        "AND guide_os_id=? AND version_number=1 AND decision_type='accept'",
        (assignment["assignment_id"], assignment["guide_os_id"]),
    ).fetchone()
    if target is None or active is None or consent is None or target["severity"] != "critical":
        raise AssignmentValidationError("Retained legacy agreement and v2 target required.")
    package = validate_package(_load_working_package_json(target["working_package_json"]))
    old = _load_working_package_json(active["working_package_json"])
    _require_legacy_package(old)
    tour_id = old.get("tour", {}).get("id")
    uuid(tour_id, "legacy immutable tour identity")
    explicit = {**assignment, "projection_mode": "explicit_days", "operator_tour_id": tour_id}
    _explicit_scope(explicit, package)
    old_scope = old.get("assignment", {})
    if (
        old_scope.get("id") != assignment["assignment_id"]
        or old_scope.get("role") != assignment["role"]
        or old_scope.get("start_date") != assignment["start_date"]
        or old_scope.get("end_date") != assignment["end_date"]
        or old_scope.get("guide_os_id", assignment["guide_os_id"]) != assignment["guide_os_id"]
        or old.get("company_id", assignment["company_id"]) != assignment["company_id"]
    ):
        raise AssignmentValidationError("Legacy agreed identity/scope is inconsistent.")
    projection_id = assignment["projection_tour_id"]
    row = conn.execute("SELECT * FROM tours WHERE id=?", (projection_id,)).fetchone()
    if (
        row is None or row["user_id"] != user_id or row["source"] != SOURCE_GUIDE_OPERATOR
        or row["note"] != f"go_assignment:{assignment['assignment_id']}"
        or row["tour_group_id"] != assignment["assignment_id"]
        or row["entry_type"] != ENTRY_TYPE_TOUR or row["status"] != STATUS_CONFIRMED
        or row["start_date"] != assignment["start_date"]
        or row["end_date"] != assignment["end_date"]
        or row["income"] is not None or row["payment_status"] != PAYMENT_UNPAID
        or row["start_time"] is not None or row["end_time"] is not None
        or _daily_links(conn, assignment["assignment_id"])
    ):
        raise AssignmentValidationError("Unsafe legacy projection; transition is refused.")
    return projection_id


def _guide_lifecycle_assignment(guide_os_id, assignment_id):
    identity = validate_guide_os_id(guide_os_id)
    assignment_id = _require_nonempty(assignment_id, "assignment_id")
    row = read_guide_operator_assignment_for_guide(identity, assignment_id)
    if row is None:
        raise AssignmentNotFoundError("Assignment was not found.")
    return row


def _public_daily_state(assignment, event_id):
    return {
        "decision_event_id": event_id,
        "status": assignment["status"],
        "active_version_number": assignment["active_version_number"],
        "pending_critical_version_number": assignment["pending_critical_version_number"],
        "projection_tour_id": assignment["projection_tour_id"],
    }


def _assert_daily_event_available(conn, event_id):
    for table in (
        "guide_operator_outbox", "guide_operator_offer_inbox", "guide_operator_version_inbox",
        "guide_operator_cancellation_inbox", "guide_operator_assignment_lifecycle_inbox",
        "guide_operator_daily_operation_inbox",
    ):
        if conn.execute(f"SELECT 1 FROM {table} WHERE event_id=?", (event_id,)).fetchone():
            raise AssignmentConflictError("Event identity is already reserved.")


def _require_daily_decision_event_id(value):
    # Explicit decisions still use the frozen v1 envelope: its event ID is UUIDv4.
    from services.guide_operator_assignment_v2_contract import uuid

    uuid(value, "decision_event_id")


def _guard_explicit_terminal_identity(conn, assignment):
    connection = conn.execute(
        "SELECT company_id,guide_os_id FROM guide_operator_connections WHERE connection_id=?",
        (assignment["guide_connection_id"],),
    ).fetchone()
    if (
        connection is None or connection["company_id"] != assignment["company_id"]
        or connection["guide_os_id"] != assignment["guide_os_id"]
    ):
        raise AssignmentValidationError("Stored company/guide connection binding is inconsistent.")
    # Disconnect blocks new work, never a valid terminal event for retained work.


def _guard_explicit_offered_terminal(conn, assignment):
    _guard_explicit_terminal_identity(conn, assignment)
    if assignment["active_version_number"] != 1 or assignment["pending_critical_version_number"] is not None:
        raise AssignmentValidationError("Invalid explicit offered state.")
    active = conn.execute(
        "SELECT working_package_json FROM guide_operator_assignment_versions "
        "WHERE assignment_id=? AND version_number=1", (assignment["assignment_id"],)
    ).fetchone()
    if active is None:
        raise AssignmentValidationError("Missing explicit offer snapshot.")
    _explicit_scope(assignment, _load_working_package_json(active["working_package_json"]))
    if _daily_links(conn, assignment["assignment_id"]) or conn.execute(
        "SELECT 1 FROM tours WHERE source=? AND note=?",
        (SOURCE_GUIDE_OPERATOR, f"go_assignment:{assignment['assignment_id']}"),
    ).fetchone():
        raise AssignmentValidationError("Offered assignment unexpectedly owns occupancy.")


def _require_terminal_aware_time(value):
    # Frozen v1 evidence is timezone-aware; retain its original normalized string/hash.
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise AssignmentValidationError("Terminal event time must be timezone-aware.")
