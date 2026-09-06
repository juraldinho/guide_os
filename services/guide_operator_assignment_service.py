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

from database.db import ensure_db_ready, run_write_with_retry
from database.queries import (
    get_guide_operator_assignment,
    get_guide_operator_assignment_for_guide,
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
    assignment = get_assignment_for_guide(guide_os_id, assignment_id)
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
    if assignment["status"] == "accepted":
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

    assignment = get_assignment_for_guide(identity, assignment_id)
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
