"""Guide Operator connection-consent domain (GO8C2).

Local Guide OS foundation only: invitation intake, guide confirm/decline,
disconnect intake, and offer-gate helpers. No HTTP routes or networking.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from database.db import ensure_db_ready, run_write_with_retry
from database.queries import (
    get_guide_operator_connection,
    get_guide_operator_connection_decision,
    get_guide_operator_connection_for_guide,
    get_guide_operator_connection_inbox,
    get_user_id_by_guide_os_id,
    list_guide_operator_connections_for_guide,
    list_guide_operator_outbox_events,
)
from services.guide_operator_notification_outbox import (
    insert_guide_operator_guide_notification,
)
from utils.guide_os_identity import validate_guide_os_id

CONNECTION_INVITED_EVENT_TYPE = "guide_connection.invited.v1"
CONNECTION_DISCONNECTED_EVENT_TYPE = "guide_connection.disconnected.v1"
CONNECTION_DECIDED_EVENT_TYPE = "guide_connection.decided.v1"

# Test-only hook raised inside the decide transaction before commit.
_CONNECTION_DECIDE_FAILURE_HOOK: Callable[[], None] | None = None

# Test-only hook raised inside invitation/disconnect intake before commit.
_CONNECTION_INTAKE_FAILURE_HOOK: Callable[[], None] | None = None


class GuideOperatorConnectionError(Exception):
    """Base fail-closed domain error for Guide Operator connections."""

    code = "guide_operator_connection_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConnectionValidationError(GuideOperatorConnectionError):
    code = "validation_error"


class ConnectionNotFoundError(GuideOperatorConnectionError):
    code = "not_found"


class ConnectionForbiddenError(GuideOperatorConnectionError):
    code = "forbidden"


class ConnectionConflictError(GuideOperatorConnectionError):
    code = "idempotency_conflict"


class ConnectionNotActionableError(GuideOperatorConnectionError):
    code = "connection_not_actionable"


@dataclass(frozen=True)
class ConnectionInvitationIntake:
    event_id: str
    connection_id: str
    company_id: str
    company_name: str
    guide_os_id: str
    invitation_expires_at: str
    invited_at: str


@dataclass(frozen=True)
class ConnectionDisconnectIntake:
    event_id: str
    connection_id: str
    company_id: str
    company_name: str
    guide_os_id: str
    disconnected_at: str


@dataclass(frozen=True)
class ConnectionDecisionResult:
    connection_id: str
    guide_os_id: str
    status: str
    decision: str
    decision_event_id: str
    replayed: bool = False


def receive_connection_invitation(event: ConnectionInvitationIntake) -> dict[str, Any]:
    """Idempotently persist a guide_connection.invited.v1 invitation."""
    ensure_db_ready()
    normalized = _normalize_invitation(event)
    payload_hash = _canonical_hash(normalized)

    existing_inbox = get_guide_operator_connection_inbox(normalized["event_id"])
    if existing_inbox is not None:
        if existing_inbox["payload_hash"] != payload_hash:
            raise ConnectionConflictError(
                "Connection invitation event ID was already used with another payload."
            )
        stored = get_guide_operator_connection(normalized["connection_id"])
        if stored is None:
            raise ConnectionValidationError(
                "Connection invitation inbox exists without connection."
            )
        return stored

    existing = get_guide_operator_connection(normalized["connection_id"])
    if existing is not None:
        prior_inbox = get_guide_operator_connection_inbox(existing["invite_event_id"])
        if prior_inbox is not None and prior_inbox["payload_hash"] == payload_hash:
            return existing
        raise ConnectionConflictError(
            "Connection invitation already exists with a different payload."
        )

    guide_os_id = validate_guide_os_id(normalized["guide_os_id"])
    if get_user_id_by_guide_os_id(guide_os_id) is None:
        raise ConnectionValidationError(
            "Unknown guide_os_id; integration boundary fail-closed.",
            details={"code": "integration_unavailable"},
        )

    received_at = normalized["invited_at"]

    def operation(conn):
        inbox = conn.execute(
            "SELECT * FROM guide_operator_connection_inbox WHERE event_id = ? LIMIT 1",
            (normalized["event_id"],),
        ).fetchone()
        if inbox is not None:
            if inbox["payload_hash"] != payload_hash:
                raise ConnectionConflictError(
                    "Connection invitation event ID was already used with another payload."
                )
            row = conn.execute(
                "SELECT * FROM guide_operator_connections WHERE connection_id = ?",
                (normalized["connection_id"],),
            ).fetchone()
            return dict(row) if row else None

        existing_row = conn.execute(
            "SELECT * FROM guide_operator_connections WHERE connection_id = ?",
            (normalized["connection_id"],),
        ).fetchone()
        if existing_row is not None:
            raise ConnectionConflictError(
                "Connection invitation already exists with a different payload."
            )

        conn.execute(
            """
            INSERT INTO guide_operator_connections (
                connection_id, guide_os_id, company_id, company_name, status,
                invitation_expires_at, invited_at, decided_at, disconnected_at,
                invite_event_id, disconnect_event_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'invited', ?, ?, NULL, NULL, ?, NULL, ?, ?)
            """,
            (
                normalized["connection_id"],
                guide_os_id,
                normalized["company_id"],
                normalized["company_name"],
                normalized["invitation_expires_at"],
                normalized["invited_at"],
                normalized["event_id"],
                received_at,
                received_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO guide_operator_connection_inbox (
                event_id, connection_id, guide_os_id, event_type,
                payload_hash, received_at, result_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'applied')
            """,
            (
                normalized["event_id"],
                normalized["connection_id"],
                guide_os_id,
                CONNECTION_INVITED_EVENT_TYPE,
                payload_hash,
                received_at,
            ),
        )
        insert_guide_operator_guide_notification(
            conn,
            source_event_id=normalized["event_id"],
            guide_os_id=guide_os_id,
            notification_type="connection_invitation",
            company_name=normalized["company_name"],
            connection_id=normalized["connection_id"],
            created_at=received_at,
        )
        if _CONNECTION_INTAKE_FAILURE_HOOK is not None:
            _CONNECTION_INTAKE_FAILURE_HOOK()
        row = conn.execute(
            "SELECT * FROM guide_operator_connections WHERE connection_id = ?",
            (normalized["connection_id"],),
        ).fetchone()
        return dict(row)

    result = run_write_with_retry(operation)
    if result is None:
        raise ConnectionValidationError("Failed to persist connection invitation.")
    return result


def receive_connection_disconnect(event: ConnectionDisconnectIntake) -> dict[str, Any]:
    """Idempotently apply guide_connection.disconnected.v1 as a terminal state."""
    ensure_db_ready()
    normalized = _normalize_disconnect(event)
    payload_hash = _canonical_hash(normalized)

    existing_inbox = get_guide_operator_connection_inbox(normalized["event_id"])
    if existing_inbox is not None:
        if existing_inbox["payload_hash"] != payload_hash:
            raise ConnectionConflictError(
                "Connection disconnect event ID was already used with another payload."
            )
        stored = get_guide_operator_connection(normalized["connection_id"])
        if stored is None:
            raise ConnectionValidationError(
                "Connection disconnect inbox exists without connection."
            )
        return stored

    guide_os_id = validate_guide_os_id(normalized["guide_os_id"])
    connection = get_guide_operator_connection(normalized["connection_id"])
    if connection is None:
        raise ConnectionNotFoundError("Connection was not found.")
    if connection["guide_os_id"] != guide_os_id:
        raise ConnectionNotFoundError("Connection was not found.")
    if (
        connection["company_id"] != normalized["company_id"]
        or connection["company_name"] != normalized["company_name"]
    ):
        raise ConnectionConflictError(
            "Disconnect payload does not match stored connection identity."
        )
    if connection["status"] == "disconnected":
        if connection.get("disconnect_event_id") == normalized["event_id"]:
            return connection
        raise ConnectionConflictError(
            "Connection is already disconnected with a different event."
        )
    if connection["status"] != "confirmed":
        raise ConnectionNotActionableError(
            "Only a confirmed guide connection can be disconnected.",
            details={"status": connection["status"]},
        )

    disconnected_at = normalized["disconnected_at"]

    def operation(conn):
        inbox = conn.execute(
            "SELECT * FROM guide_operator_connection_inbox WHERE event_id = ? LIMIT 1",
            (normalized["event_id"],),
        ).fetchone()
        if inbox is not None:
            if inbox["payload_hash"] != payload_hash:
                raise ConnectionConflictError(
                    "Connection disconnect event ID was already used with another payload."
                )
            row = conn.execute(
                "SELECT * FROM guide_operator_connections WHERE connection_id = ?",
                (normalized["connection_id"],),
            ).fetchone()
            return dict(row) if row else None

        locked = conn.execute(
            """
            SELECT * FROM guide_operator_connections
            WHERE connection_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (normalized["connection_id"], guide_os_id),
        ).fetchone()
        if locked is None:
            raise ConnectionNotFoundError("Connection was not found.")
        if (
            locked["company_id"] != normalized["company_id"]
            or locked["company_name"] != normalized["company_name"]
        ):
            raise ConnectionConflictError(
                "Disconnect payload does not match stored connection identity."
            )
        if locked["status"] == "disconnected":
            if locked["disconnect_event_id"] == normalized["event_id"]:
                return dict(locked)
            raise ConnectionConflictError(
                "Connection is already disconnected with a different event."
            )
        if locked["status"] != "confirmed":
            raise ConnectionNotActionableError(
                "Only a confirmed guide connection can be disconnected.",
                details={"status": locked["status"]},
            )

        conn.execute(
            """
            UPDATE guide_operator_connections
            SET status = 'disconnected',
                disconnected_at = ?,
                disconnect_event_id = ?,
                updated_at = ?
            WHERE connection_id = ? AND guide_os_id = ? AND status = 'confirmed'
            """,
            (
                disconnected_at,
                normalized["event_id"],
                disconnected_at,
                normalized["connection_id"],
                guide_os_id,
            ),
        )
        updated = conn.execute(
            """
            SELECT * FROM guide_operator_connections
            WHERE connection_id = ? AND status = 'disconnected'
            LIMIT 1
            """,
            (normalized["connection_id"],),
        ).fetchone()
        if updated is None:
            raise ConnectionNotActionableError(
                "Only a confirmed guide connection can be disconnected."
            )
        conn.execute(
            """
            INSERT INTO guide_operator_connection_inbox (
                event_id, connection_id, guide_os_id, event_type,
                payload_hash, received_at, result_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'applied')
            """,
            (
                normalized["event_id"],
                normalized["connection_id"],
                guide_os_id,
                CONNECTION_DISCONNECTED_EVENT_TYPE,
                payload_hash,
                disconnected_at,
            ),
        )
        insert_guide_operator_guide_notification(
            conn,
            source_event_id=normalized["event_id"],
            guide_os_id=guide_os_id,
            notification_type="connection_disconnection",
            company_name=normalized["company_name"],
            connection_id=normalized["connection_id"],
            created_at=disconnected_at,
        )
        if _CONNECTION_INTAKE_FAILURE_HOOK is not None:
            _CONNECTION_INTAKE_FAILURE_HOOK()
        return dict(updated)

    result = run_write_with_retry(operation)
    if result is None:
        raise ConnectionValidationError("Failed to apply connection disconnect.")
    return result


def confirm_connection(
    guide_os_id: str,
    connection_id: str,
    *,
    decision_event_id: str,
    decided_at: str | None = None,
) -> ConnectionDecisionResult:
    return _decide_connection(
        guide_os_id,
        connection_id,
        decision="confirm",
        decision_event_id=decision_event_id,
        decided_at=decided_at,
    )


def decline_connection(
    guide_os_id: str,
    connection_id: str,
    *,
    decision_event_id: str,
    decided_at: str | None = None,
) -> ConnectionDecisionResult:
    return _decide_connection(
        guide_os_id,
        connection_id,
        decision="decline",
        decision_event_id=decision_event_id,
        decided_at=decided_at,
    )


def get_connection_for_guide(guide_os_id: str, connection_id: str) -> dict[str, Any]:
    identity = validate_guide_os_id(guide_os_id)
    connection_id = _require_nonempty(connection_id, "connection_id")
    row = get_guide_operator_connection_for_guide(identity, connection_id)
    if row is None:
        raise ConnectionNotFoundError("Connection was not found.")
    return row


def list_connections_for_guide(
    guide_os_id: str, *, now: str | None = None
) -> list[dict[str, Any]]:
    """Return guide-scoped connection summaries for Mini App (safe fields only)."""
    identity = validate_guide_os_id(guide_os_id)
    rows = list_guide_operator_connections_for_guide(identity)
    summaries = [_connection_summary(row, now=now) for row in rows]

    def _group_rank(item: dict[str, Any]) -> int:
        if item["actionable"]:
            return 0
        if item["status"] == "confirmed":
            return 1
        if item["status"] == "invited" and item["expired"]:
            return 2
        if item["status"] == "declined":
            return 3
        return 4

    summaries.sort(key=lambda item: item["invitedAt"], reverse=True)
    summaries.sort(key=_group_rank)
    return summaries


def _connection_summary(
    row: dict[str, Any], *, now: str | None = None
) -> dict[str, Any]:
    expired = _is_expired(row, now=now)
    status = row["status"]
    actionable = status == "invited" and not expired
    return {
        "id": row["connection_id"],
        "companyName": row["company_name"],
        "status": status,
        "invitedAt": row["invited_at"],
        "invitationExpiresAt": row["invitation_expires_at"],
        "decidedAt": row.get("decided_at"),
        "disconnectedAt": row.get("disconnected_at"),
        "expired": expired,
        "actionable": actionable,
    }


def require_confirmed_connection_for_offer(
    *,
    guide_connection_id: str,
    guide_os_id: str,
    company_id: str,
    now: str | None = None,
) -> dict[str, Any]:
    """Fail closed unless the local connection is confirmed and identity matches."""
    identity = validate_guide_os_id(guide_os_id)
    connection_id = _require_nonempty(guide_connection_id, "guide_connection_id")
    company_id = _require_nonempty(company_id, "company_id")
    connection = get_guide_operator_connection(connection_id)
    if connection is None or connection["guide_os_id"] != identity:
        raise ConnectionValidationError(
            "Guide connection is missing or not available for this offer.",
            details={"code": "connection_missing"},
        )
    if connection["company_id"] != company_id:
        raise ConnectionValidationError(
            "Offer company does not match the guide connection.",
            details={"code": "connection_company_mismatch"},
        )
    status = connection["status"]
    if status == "disconnected":
        raise ConnectionValidationError(
            "Guide connection is disconnected; new offers are rejected.",
            details={"code": "connection_disconnected"},
        )
    if status == "declined":
        raise ConnectionValidationError(
            "Guide connection was declined; new offers are rejected.",
            details={"code": "connection_declined"},
        )
    if status == "invited":
        if _is_expired(connection, now=now):
            raise ConnectionValidationError(
                "Guide connection invitation has expired.",
                details={"code": "connection_expired"},
            )
        raise ConnectionValidationError(
            "Guide connection is not confirmed.",
            details={"code": "connection_not_confirmed"},
        )
    if status != "confirmed":
        raise ConnectionValidationError(
            "Guide connection is not confirmed.",
            details={"code": "connection_not_confirmed"},
        )
    return connection


def ensure_confirmed_connection_for_tests(
    guide_os_id: str,
    *,
    connection_id: str | None = None,
    company_id: str | None = None,
    company_name: str = "Operator Co",
    invitation_expires_at: str = "2099-12-31T23:59:59+00:00",
    invited_at: str = "2026-01-01T00:00:00+00:00",
) -> dict[str, Any]:
    """Test helper: invite + confirm a connection for assignment fixtures."""
    from uuid import uuid4

    connection_id = connection_id or str(uuid4())
    company_id = company_id or str(uuid4())
    invite_event_id = str(uuid4())
    receive_connection_invitation(
        ConnectionInvitationIntake(
            event_id=invite_event_id,
            connection_id=connection_id,
            company_id=company_id,
            company_name=company_name,
            guide_os_id=guide_os_id,
            invitation_expires_at=invitation_expires_at,
            invited_at=invited_at,
        )
    )
    confirm_connection(
        guide_os_id,
        connection_id,
        decision_event_id=str(uuid4()),
        decided_at=invited_at,
    )
    return get_connection_for_guide(guide_os_id, connection_id)


def list_connection_decision_outbox(connection_id: str) -> list[dict[str, Any]]:
    return list_guide_operator_outbox_events(
        assignment_id=connection_id, event_type=CONNECTION_DECIDED_EVENT_TYPE
    )


def _decide_connection(
    guide_os_id: str,
    connection_id: str,
    *,
    decision: str,
    decision_event_id: str,
    decided_at: str | None,
) -> ConnectionDecisionResult:
    ensure_db_ready()
    identity = validate_guide_os_id(guide_os_id)
    connection_id = _require_nonempty(connection_id, "connection_id")
    decision_event_id = _require_nonempty(decision_event_id, "decision_event_id")
    if decision not in {"confirm", "decline"}:
        raise ConnectionValidationError("decision must be confirm or decline.")

    existing_decision = get_guide_operator_connection_decision(connection_id)
    if existing_decision is not None:
        if existing_decision["guide_os_id"] != identity:
            raise ConnectionNotFoundError("Connection was not found.")
        if existing_decision["decision_event_id"] != decision_event_id:
            if existing_decision["decision_type"] == decision:
                connection = get_connection_for_guide(identity, connection_id)
                return ConnectionDecisionResult(
                    connection_id=connection_id,
                    guide_os_id=identity,
                    status=connection["status"],
                    decision=existing_decision["decision_type"],
                    decision_event_id=existing_decision["decision_event_id"],
                    replayed=True,
                )
            raise ConnectionNotActionableError(
                "Connection invitation is not actionable."
            )
        if existing_decision["decision_type"] != decision:
            raise ConnectionConflictError(
                "Decision event ID was already used with another decision."
            )
        connection = get_connection_for_guide(identity, connection_id)
        return ConnectionDecisionResult(
            connection_id=connection_id,
            guide_os_id=identity,
            status=connection["status"],
            decision=decision,
            decision_event_id=decision_event_id,
            replayed=True,
        )

    connection = get_connection_for_guide(identity, connection_id)
    if connection["status"] != "invited":
        raise ConnectionNotActionableError("Connection invitation is not actionable.")
    if _is_expired(connection):
        raise ConnectionNotActionableError(
            "Connection invitation has expired.",
            details={"code": "connection_expired"},
        )

    decided_at_value = decided_at or _utc_now()
    if decided_at is not None:
        decided_at_value = _require_iso_datetime(decided_at, "decided_at")
    status = "confirmed" if decision == "confirm" else "declined"

    def operation(conn):
        locked = conn.execute(
            """
            SELECT * FROM guide_operator_connections
            WHERE connection_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (connection_id, identity),
        ).fetchone()
        if locked is None:
            raise ConnectionNotFoundError("Connection was not found.")
        if locked["status"] != "invited":
            prior = conn.execute(
                """
                SELECT * FROM guide_operator_connection_decisions
                WHERE connection_id = ? LIMIT 1
                """,
                (connection_id,),
            ).fetchone()
            if prior is not None and prior["decision_type"] == decision:
                return ConnectionDecisionResult(
                    connection_id=connection_id,
                    guide_os_id=identity,
                    status=locked["status"],
                    decision=decision,
                    decision_event_id=prior["decision_event_id"],
                    replayed=True,
                )
            raise ConnectionNotActionableError(
                "Connection invitation is not actionable."
            )
        if _is_expired(dict(locked)):
            raise ConnectionNotActionableError(
                "Connection invitation has expired.",
                details={"code": "connection_expired"},
            )

        event_row = conn.execute(
            """
            SELECT * FROM guide_operator_connection_decisions
            WHERE decision_event_id = ? LIMIT 1
            """,
            (decision_event_id,),
        ).fetchone()
        if event_row is not None:
            if event_row["connection_id"] != connection_id:
                raise ConnectionConflictError(
                    "Decision event ID was already used for another connection."
                )
            return ConnectionDecisionResult(
                connection_id=connection_id,
                guide_os_id=identity,
                status=locked["status"],
                decision=event_row["decision_type"],
                decision_event_id=decision_event_id,
                replayed=True,
            )

        conn.execute(
            """
            INSERT INTO guide_operator_connection_decisions (
                decision_event_id, connection_id, guide_os_id,
                decision_type, decided_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                decision_event_id,
                connection_id,
                identity,
                decision,
                decided_at_value,
                decided_at_value,
            ),
        )
        conn.execute(
            """
            UPDATE guide_operator_connections
            SET status = ?,
                decided_at = ?,
                updated_at = ?
            WHERE connection_id = ? AND guide_os_id = ? AND status = 'invited'
            """,
            (
                status,
                decided_at_value,
                decided_at_value,
                connection_id,
                identity,
            ),
        )
        updated = conn.execute(
            """
            SELECT status FROM guide_operator_connections
            WHERE connection_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (connection_id, identity),
        ).fetchone()
        if updated is None or updated["status"] != status:
            raise ConnectionNotActionableError(
                "Connection invitation is not actionable."
            )

        payload = {
            "connection_id": connection_id,
            "guide_os_id": identity,
            "company_id": locked["company_id"],
            "company_name": locked["company_name"],
            "decision": decision,
            "decided_at": decided_at_value,
        }
        conn.execute(
            """
            INSERT INTO guide_operator_outbox (
                event_id, event_type, aggregate_type, aggregate_id,
                guide_os_id, payload_json, created_at, delivered_at, attempt_count
            ) VALUES (?, ?, 'guide_connection', ?, ?, ?, ?, NULL, 0)
            """,
            (
                decision_event_id,
                CONNECTION_DECIDED_EVENT_TYPE,
                connection_id,
                identity,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                decided_at_value,
            ),
        )

        if _CONNECTION_DECIDE_FAILURE_HOOK is not None:
            _CONNECTION_DECIDE_FAILURE_HOOK()

        return ConnectionDecisionResult(
            connection_id=connection_id,
            guide_os_id=identity,
            status=status,
            decision=decision,
            decision_event_id=decision_event_id,
            replayed=False,
        )

    return run_write_with_retry(operation)


def _normalize_invitation(event: ConnectionInvitationIntake) -> dict[str, Any]:
    if not isinstance(event, ConnectionInvitationIntake):
        raise ConnectionValidationError(
            "Invitation payload must be ConnectionInvitationIntake."
        )
    return {
        "event_id": _require_nonempty(event.event_id, "event_id"),
        "connection_id": _require_nonempty(event.connection_id, "connection_id"),
        "company_id": _require_nonempty(event.company_id, "company_id"),
        "company_name": _require_nonempty(event.company_name, "company_name"),
        "guide_os_id": validate_guide_os_id(event.guide_os_id),
        "invitation_expires_at": _require_iso_datetime(
            event.invitation_expires_at, "invitation_expires_at"
        ),
        "invited_at": _require_iso_datetime(event.invited_at, "invited_at"),
    }


def _normalize_disconnect(event: ConnectionDisconnectIntake) -> dict[str, Any]:
    if not isinstance(event, ConnectionDisconnectIntake):
        raise ConnectionValidationError(
            "Disconnect payload must be ConnectionDisconnectIntake."
        )
    return {
        "event_id": _require_nonempty(event.event_id, "event_id"),
        "connection_id": _require_nonempty(event.connection_id, "connection_id"),
        "company_id": _require_nonempty(event.company_id, "company_id"),
        "company_name": _require_nonempty(event.company_name, "company_name"),
        "guide_os_id": validate_guide_os_id(event.guide_os_id),
        "disconnected_at": _require_iso_datetime(
            event.disconnected_at, "disconnected_at"
        ),
    }


def _is_expired(connection: dict[str, Any], *, now: str | None = None) -> bool:
    if connection.get("status") != "invited":
        return False
    expiry_raw = connection["invitation_expires_at"]
    expiry = _parse_aware_utc(expiry_raw)
    current = (
        _parse_aware_utc(now) if now is not None else datetime.now(timezone.utc)
    )
    return expiry <= current


def _parse_aware_utc(value: str) -> datetime:
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _require_nonempty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConnectionValidationError(f"{field} is required.")
    return value.strip()


def _require_iso_datetime(value: str, field: str) -> str:
    text = _require_nonempty(value, field)
    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ConnectionValidationError(
            f"{field} must be a valid ISO-8601 timestamp."
        ) from exc
    return text


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
