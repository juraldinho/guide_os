"""Read-only reconciliation for the durable GuideShop event state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import sqlite3
from typing import Callable


_CURSOR_PATTERN = re.compile(r"^[A-Za-z0-9._~=-]+$")
_PROCESSING_LEASE_TIMEOUT = timedelta(minutes=5)
_STATES = ("pending", "processing", "delivered", "stale", "dead_letter")


class EventReconciliationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EventReconciliationReport:
    inbox_pending_count: int
    inbox_processing_count: int
    inbox_delivered_count: int
    inbox_stale_count: int
    inbox_dead_letter_count: int
    abandoned_processing_count: int
    dead_letter_count: int
    aggregate_gap_count: int
    equal_version_collision_count: int
    missing_watermark_count: int
    watermark_mismatch_count: int
    inbox_without_checkpoint_count: int
    checkpoint_without_inbox_count: int
    invalid_checkpoint_count: int

    @property
    def verdict(self) -> str:
        attention_metrics = (
            self.abandoned_processing_count,
            self.dead_letter_count,
            self.aggregate_gap_count,
            self.equal_version_collision_count,
            self.missing_watermark_count,
            self.watermark_mismatch_count,
            self.inbox_without_checkpoint_count,
            self.checkpoint_without_inbox_count,
            self.invalid_checkpoint_count,
        )
        return "NEEDS_ATTENTION" if any(attention_metrics) else "CLEAN"

    def metrics(self) -> tuple[tuple[str, int], ...]:
        return tuple(
            (name, value)
            for name, value in self.__dict__.items()
        )


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise EventReconciliationError("reconciliation failed")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _valid_cursor(value: object) -> bool:
    return (
        isinstance(value, str)
        and 8 <= len(value) <= 256
        and _CURSOR_PATTERN.fullmatch(value) is not None
    )


class GuideShopEventReconciliationService:
    def __init__(
        self,
        *,
        database_path: str | os.PathLike[str] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        after_snapshot_started: Callable[[], None] | None = None,
    ) -> None:
        self._database_path = Path(
            database_path or os.getenv("DATABASE_PATH", "guide_os.db")
        ).resolve()
        self._clock = clock
        self._after_snapshot_started = after_snapshot_started

    def reconcile(self) -> EventReconciliationReport:
        lease_cutoff = _utc_iso(self._clock() - _PROCESSING_LEASE_TIMEOUT)
        uri = f"{self._database_path.as_uri()}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON")
            conn.execute("BEGIN")

            state_rows = conn.execute(
                """
                SELECT state, COUNT(*) AS count
                FROM guide_shop_event_inbox
                GROUP BY state
                """
            ).fetchall()
            state_counts = {state: 0 for state in _STATES}
            state_counts.update({row["state"]: row["count"] for row in state_rows})

            if self._after_snapshot_started is not None:
                self._after_snapshot_started()

            abandoned = conn.execute(
                """
                SELECT COUNT(*)
                FROM guide_shop_event_inbox
                WHERE state = 'processing'
                  AND last_attempt_at IS NOT NULL
                  AND last_attempt_at < ?
                """,
                (lease_cutoff,),
            ).fetchone()[0]
            aggregate_gaps = conn.execute(
                """
                WITH versions AS (
                    SELECT DISTINCT guide_os_id, subject_type, subject_id,
                                    aggregate_version
                    FROM guide_shop_event_inbox
                ), ordered AS (
                    SELECT aggregate_version,
                           LAG(aggregate_version) OVER (
                               PARTITION BY guide_os_id, subject_type, subject_id
                               ORDER BY aggregate_version
                           ) AS previous_version
                    FROM versions
                )
                SELECT COUNT(*) FROM ordered
                WHERE previous_version IS NOT NULL
                  AND aggregate_version > previous_version + 1
                """
            ).fetchone()[0]
            collisions = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT guide_os_id, subject_type, subject_id,
                           aggregate_version
                    FROM guide_shop_event_inbox
                    GROUP BY guide_os_id, subject_type, subject_id,
                             aggregate_version
                    HAVING COUNT(DISTINCT event_id) > 1
                )
                """
            ).fetchone()[0]
            missing_watermarks = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT i.guide_os_id, i.subject_type, i.subject_id
                    FROM guide_shop_event_inbox AS i
                    WHERE i.state != 'stale'
                      AND NOT EXISTS (
                          SELECT 1 FROM guide_shop_event_watermarks AS w
                          WHERE w.guide_os_id = i.guide_os_id
                            AND w.subject_type = i.subject_type
                            AND w.subject_id = i.subject_id
                      )
                )
                """
            ).fetchone()[0]
            watermark_mismatches = conn.execute(
                """
                SELECT COUNT(*)
                FROM guide_shop_event_watermarks AS w
                WHERE NOT EXISTS (
                    SELECT 1 FROM guide_shop_event_inbox AS i
                    WHERE i.event_id = w.event_id
                      AND i.guide_os_id = w.guide_os_id
                      AND i.subject_type = w.subject_type
                      AND i.subject_id = w.subject_id
                      AND i.aggregate_version = w.highest_aggregate_version
                )
                OR w.highest_aggregate_version != COALESCE((
                    SELECT MAX(i.aggregate_version)
                    FROM guide_shop_event_inbox AS i
                    WHERE i.guide_os_id = w.guide_os_id
                      AND i.subject_type = w.subject_type
                      AND i.subject_id = w.subject_id
                      AND i.state != 'stale'
                ), 0)
                """
            ).fetchone()[0]
            inbox_without_checkpoint = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT i.guide_os_id
                    FROM guide_shop_event_inbox AS i
                    WHERE NOT EXISTS (
                        SELECT 1 FROM guide_shop_event_checkpoints AS c
                        WHERE c.guide_os_id = i.guide_os_id
                    )
                )
                """
            ).fetchone()[0]
            checkpoint_without_inbox = conn.execute(
                """
                SELECT COUNT(*)
                FROM guide_shop_event_checkpoints AS c
                WHERE NOT EXISTS (
                    SELECT 1 FROM guide_shop_event_inbox AS i
                    WHERE i.guide_os_id = c.guide_os_id
                )
                """
            ).fetchone()[0]
            checkpoint_rows = conn.execute(
                """
                SELECT cursor, generation, typeof(generation) AS generation_type
                FROM guide_shop_event_checkpoints
                """
            ).fetchall()
            invalid_checkpoints = sum(
                not _valid_cursor(row["cursor"])
                or row["generation_type"] != "integer"
                or isinstance(row["generation"], bool)
                or row["generation"] < 1
                for row in checkpoint_rows
            )
            conn.commit()
        except Exception:
            raise EventReconciliationError("reconciliation failed") from None
        finally:
            if "conn" in locals():
                conn.close()

        return EventReconciliationReport(
            inbox_pending_count=state_counts["pending"],
            inbox_processing_count=state_counts["processing"],
            inbox_delivered_count=state_counts["delivered"],
            inbox_stale_count=state_counts["stale"],
            inbox_dead_letter_count=state_counts["dead_letter"],
            abandoned_processing_count=abandoned,
            dead_letter_count=state_counts["dead_letter"],
            aggregate_gap_count=aggregate_gaps,
            equal_version_collision_count=collisions,
            missing_watermark_count=missing_watermarks,
            watermark_mismatch_count=watermark_mismatches,
            inbox_without_checkpoint_count=inbox_without_checkpoint,
            checkpoint_without_inbox_count=checkpoint_without_inbox,
            invalid_checkpoint_count=invalid_checkpoints,
        )
