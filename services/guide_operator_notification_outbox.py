"""GO10A1: durable guide-facing notification outbox for Guide Operator intake.

Records are written inside the same SQLite transaction as successful domain
intake. Delivery (Telegram) is intentionally out of scope for this stage.
"""

from __future__ import annotations

from typing import Any, Literal

NotificationType = Literal[
    "connection_invitation",
    "assignment_offer",
    "ordinary_version_change",
    "critical_confirmation_required",
    "assignment_cancellation",
    "connection_disconnection",
]

NOTIFICATION_TYPES: frozenset[str] = frozenset(
    {
        "connection_invitation",
        "assignment_offer",
        "ordinary_version_change",
        "critical_confirmation_required",
        "assignment_cancellation",
        "connection_disconnection",
    }
)

DELIVERY_STATUS_PENDING = "pending"
DELIVERY_STATUS_DELIVERED = "delivered"
DELIVERY_STATUS_FAILED = "failed"


def deep_link_target_for_connection(connection_id: str) -> str:
    return f"guide_operator:connection:{connection_id}"


def deep_link_target_for_assignment(assignment_id: str) -> str:
    return f"guide_operator:assignment:{assignment_id}"


def insert_guide_operator_guide_notification(
    conn: Any,
    *,
    source_event_id: str,
    guide_os_id: str,
    notification_type: NotificationType,
    company_name: str,
    created_at: str,
    connection_id: str | None = None,
    assignment_id: str | None = None,
    version_number: int | None = None,
) -> None:
    """Insert one guide notification row on the caller's open write connection.

    Callers must invoke this only on the first successful apply path. Duplicate
    `source_event_id` values are rejected by UNIQUE constraint (fail closed).
    """
    if notification_type not in NOTIFICATION_TYPES:
        raise ValueError("unsupported guide notification type")
    if not isinstance(company_name, str) or not company_name.strip():
        raise ValueError("company_name is required for guide notifications")
    if notification_type in {"connection_invitation", "connection_disconnection"}:
        if not connection_id or assignment_id is not None:
            raise ValueError("connection notifications require connection_id only")
        if version_number is not None:
            raise ValueError("version_number is not allowed for connection notifications")
        deep_link_target = deep_link_target_for_connection(connection_id)
    else:
        if not assignment_id:
            raise ValueError("assignment notifications require assignment_id")
        if connection_id is not None:
            raise ValueError("assignment notifications must not set connection_id")
        deep_link_target = deep_link_target_for_assignment(assignment_id)
        if notification_type in {
            "ordinary_version_change",
            "critical_confirmation_required",
            "assignment_cancellation",
            "assignment_offer",
        } and (version_number is None or int(version_number) < 1):
            raise ValueError("version_number is required for this notification type")

    conn.execute(
        """
        INSERT INTO guide_operator_guide_notifications (
            source_event_id, guide_os_id, notification_type, company_name,
            connection_id, assignment_id, version_number, deep_link_target,
            created_at, delivery_status, delivered_at, failed_at,
            attempt_count, last_error_code, next_attempt_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, 0, NULL, NULL)
        """,
        (
            source_event_id,
            guide_os_id,
            notification_type,
            company_name.strip(),
            connection_id,
            assignment_id,
            version_number,
            deep_link_target,
            created_at,
        ),
    )
