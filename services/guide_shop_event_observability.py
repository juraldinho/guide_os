"""Low-cardinality read-only metrics for the GuideShop event inbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Callable

from services.guide_shop_event_inbox import PROCESSING_LEASE_TIMEOUT


class EventObservabilityError(RuntimeError):
    pass


@dataclass(frozen=True)
class GuideShopEventInboxSnapshot:
    inbox_pending_count: int
    inbox_processing_count: int
    inbox_delivered_count: int
    inbox_stale_count: int
    inbox_dead_letter_count: int
    due_pending_count: int
    abandoned_processing_count: int
    checkpoint_count: int
    oldest_due_pending_age_seconds: int | None

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if name == "oldest_due_pending_age_seconds" and value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("invalid event inbox snapshot")

    def values(self) -> tuple[int | None, ...]:
        return tuple(self.__dict__.values())


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise EventObservabilityError("event inbox snapshot failed")
    return value.astimezone(timezone.utc)


def _utc_iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _stored_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        raise EventObservabilityError("event inbox snapshot failed") from None
    return _utc(parsed)


class GuideShopEventObservabilityService:
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

    def snapshot(self) -> GuideShopEventInboxSnapshot:
        now = _utc(self._clock())
        now_iso = _utc_iso(now)
        lease_cutoff = _utc_iso(now - PROCESSING_LEASE_TIMEOUT)
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
            state_counts = {
                "pending": 0,
                "processing": 0,
                "delivered": 0,
                "stale": 0,
                "dead_letter": 0,
            }
            state_counts.update(
                {row["state"]: row["count"] for row in state_rows}
            )
            if self._after_snapshot_started is not None:
                self._after_snapshot_started()
            due = conn.execute(
                """
                SELECT COUNT(*) AS count,
                       MIN(COALESCE(next_attempt_at, received_at)) AS oldest_due
                FROM guide_shop_event_inbox
                WHERE state = 'pending'
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                """,
                (now_iso,),
            ).fetchone()
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
            checkpoints = conn.execute(
                "SELECT COUNT(*) FROM guide_shop_event_checkpoints"
            ).fetchone()[0]
            conn.commit()
        except Exception:
            raise EventObservabilityError("event inbox snapshot failed") from None
        finally:
            if "conn" in locals():
                conn.close()

        oldest_age = None
        if due["oldest_due"] is not None:
            oldest_age = max(
                0, int((now - _stored_utc(due["oldest_due"])).total_seconds())
            )
        return GuideShopEventInboxSnapshot(
            inbox_pending_count=state_counts["pending"],
            inbox_processing_count=state_counts["processing"],
            inbox_delivered_count=state_counts["delivered"],
            inbox_stale_count=state_counts["stale"],
            inbox_dead_letter_count=state_counts["dead_letter"],
            due_pending_count=due["count"],
            abandoned_processing_count=abandoned,
            checkpoint_count=checkpoints,
            oldest_due_pending_age_seconds=oldest_age,
        )
