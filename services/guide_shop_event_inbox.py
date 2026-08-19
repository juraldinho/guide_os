from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from database.db import ensure_db_ready, get_db_connection, run_write_with_retry
from services.guide_shop_contracts import EventEnvelopeDTO
from utils.guide_os_identity import validate_guide_os_id


class EventInboxConflictError(RuntimeError):
    pass


class EventInboxIdentityMismatchError(RuntimeError):
    pass


class IngestionOutcome(str, Enum):
    INSERTED = "inserted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class IngestionResult:
    outcome: IngestionOutcome
    state: str


@dataclass(frozen=True)
class InboxEvent:
    event_id: str
    event_type: str
    event_version: str
    schema_version: str
    occurred_at: str
    producer: str
    guide_os_id: str
    subject_type: str
    subject_id: str
    aggregate_version: int
    state: str
    received_at: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: str | None
    last_attempt_at: str | None
    terminal_at: str | None


@dataclass(frozen=True)
class AggregateWatermark:
    guide_os_id: str
    subject_type: str
    subject_id: str
    highest_aggregate_version: int
    event_id: str
    updated_at: str


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("clock must return an aware UTC datetime")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _event_values(event: EventEnvelopeDTO) -> tuple[object, ...]:
    return (
        event.event_id,
        event.event_type,
        event.event_version,
        event.schema_version,
        _utc_iso(event.occurred_at),
        event.producer,
        event.guide_os_id,
        event.subject.type,
        event.subject.id,
        event.aggregate_version,
    )


def _same_immutable_content(row, event: EventEnvelopeDTO) -> bool:
    names = (
        "event_id",
        "event_type",
        "event_version",
        "schema_version",
        "occurred_at",
        "producer",
        "guide_os_id",
        "subject_type",
        "subject_id",
        "aggregate_version",
    )
    return tuple(row[name] for name in names) == _event_values(event)


class GuideShopEventInboxService:
    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        after_inbox_insert: Callable[[], None] | None = None,
    ) -> None:
        self._clock = clock
        self._after_inbox_insert = after_inbox_insert

    def ingest(
        self, event: EventEnvelopeDTO, *, expected_guide_os_id: str
    ) -> IngestionResult:
        expected_identity = validate_guide_os_id(expected_guide_os_id)
        if event.guide_os_id != expected_identity:
            raise EventInboxIdentityMismatchError("event identity mismatch")
        received_at = _utc_iso(self._clock())

        def operation(conn):
            existing = conn.execute(
                "SELECT * FROM guide_shop_event_inbox WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
            if existing is not None:
                if _same_immutable_content(existing, event):
                    return IngestionResult(
                        IngestionOutcome.DUPLICATE, existing["state"]
                    )
                raise EventInboxConflictError("event identity conflict")

            watermark = conn.execute(
                """
                SELECT highest_aggregate_version
                FROM guide_shop_event_watermarks
                WHERE guide_os_id = ? AND subject_type = ? AND subject_id = ?
                """,
                (event.guide_os_id, event.subject.type, event.subject.id),
            ).fetchone()
            state = (
                "stale"
                if watermark is not None
                and event.aggregate_version <= watermark["highest_aggregate_version"]
                else "pending"
            )
            conn.execute(
                """
                INSERT INTO guide_shop_event_inbox (
                    event_id, event_type, event_version, schema_version,
                    occurred_at, producer, guide_os_id, subject_type, subject_id,
                    aggregate_version, state, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*_event_values(event), state, received_at),
            )
            if self._after_inbox_insert is not None:
                self._after_inbox_insert()
            if state == "pending":
                conn.execute(
                    """
                    UPDATE guide_shop_event_inbox
                    SET state = 'stale'
                    WHERE guide_os_id = ?
                      AND subject_type = ?
                      AND subject_id = ?
                      AND event_id != ?
                      AND state = 'pending'
                      AND aggregate_version < ?
                    """,
                    (
                        event.guide_os_id,
                        event.subject.type,
                        event.subject.id,
                        event.event_id,
                        event.aggregate_version,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO guide_shop_event_watermarks (
                        guide_os_id, subject_type, subject_id,
                        highest_aggregate_version, event_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guide_os_id, subject_type, subject_id) DO UPDATE SET
                        highest_aggregate_version = excluded.highest_aggregate_version,
                        event_id = excluded.event_id,
                        updated_at = excluded.updated_at
                    WHERE excluded.highest_aggregate_version >
                          guide_shop_event_watermarks.highest_aggregate_version
                    """,
                    (
                        event.guide_os_id,
                        event.subject.type,
                        event.subject.id,
                        event.aggregate_version,
                        event.event_id,
                        received_at,
                    ),
                )
            return IngestionResult(IngestionOutcome.INSERTED, state)

        ensure_db_ready()
        return run_write_with_retry(operation)

    def get_event(self, event_id: str) -> InboxEvent | None:
        ensure_db_ready()
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT * FROM guide_shop_event_inbox WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return InboxEvent(**dict(row)) if row is not None else None

    def list_pending(self, *, limit: int = 100) -> list[InboxEvent]:
        if isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("pending limit is invalid")
        ensure_db_ready()
        with get_db_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM guide_shop_event_inbox
                WHERE state = 'pending'
                ORDER BY received_at, occurred_at, event_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [InboxEvent(**dict(row)) for row in rows]

    def get_watermark(
        self, *, guide_os_id: str, subject_type: str, subject_id: str
    ) -> AggregateWatermark | None:
        identity = validate_guide_os_id(guide_os_id)
        ensure_db_ready()
        with get_db_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM guide_shop_event_watermarks
                WHERE guide_os_id = ? AND subject_type = ? AND subject_id = ?
                """,
                (identity, subject_type, subject_id),
            ).fetchone()
        return AggregateWatermark(**dict(row)) if row is not None else None
