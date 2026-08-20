from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Callable

from database.db import ensure_db_ready, get_db_connection, run_write_with_retry
from services.guide_shop_event_client import GuideShopEventFeedClient
from services.guide_shop_event_inbox import (
    GuideShopEventInboxService,
    IngestionOutcome,
)
from utils.guide_os_identity import validate_guide_os_id


_CURSOR_PATTERN = re.compile(r"^[A-Za-z0-9._~=-]+$")


class EventCheckpointConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class EventCheckpoint:
    cursor: str | None
    generation: int


@dataclass(frozen=True)
class PullOnceResult:
    fetched_count: int
    inserted_count: int
    duplicate_count: int
    stale_count: int
    has_more: bool
    checkpoint_advanced: bool


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("clock must return an aware UTC datetime")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _cursor(value: str) -> str:
    if (
        not isinstance(value, str)
        or not 8 <= len(value) <= 256
        or _CURSOR_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("invalid event checkpoint")
    return value


class EventCheckpointRepository:
    def load(self, guide_os_id: str) -> EventCheckpoint:
        identity = validate_guide_os_id(guide_os_id)
        ensure_db_ready()
        with get_db_connection() as conn:
            row = conn.execute(
                """
                SELECT cursor, generation FROM guide_shop_event_checkpoints
                WHERE guide_os_id = ?
                """,
                (identity,),
            ).fetchone()
        if row is None:
            return EventCheckpoint(cursor=None, generation=0)
        return EventCheckpoint(cursor=row["cursor"], generation=row["generation"])

    def advance(
        self,
        guide_os_id: str,
        *,
        expected: EventCheckpoint,
        next_cursor: str,
        updated_at: datetime,
    ) -> bool:
        identity = validate_guide_os_id(guide_os_id)
        next_value = _cursor(next_cursor)
        timestamp = _utc_iso(updated_at)
        if next_value == expected.cursor:
            return False

        def operation(conn):
            if expected.generation == 0 and expected.cursor is None:
                inserted = conn.execute(
                    """
                    INSERT OR IGNORE INTO guide_shop_event_checkpoints (
                        guide_os_id, cursor, generation, updated_at
                    ) VALUES (?, ?, 1, ?)
                    """,
                    (identity, next_value, timestamp),
                )
                return inserted.rowcount == 1
            updated = conn.execute(
                """
                UPDATE guide_shop_event_checkpoints
                SET cursor = ?, generation = generation + 1, updated_at = ?
                WHERE guide_os_id = ? AND cursor = ? AND generation = ?
                """,
                (
                    next_value,
                    timestamp,
                    identity,
                    expected.cursor,
                    expected.generation,
                ),
            )
            return updated.rowcount == 1

        ensure_db_ready()
        return run_write_with_retry(operation)


class GuideShopEventPullService:
    def __init__(
        self,
        *,
        client: GuideShopEventFeedClient,
        inbox: GuideShopEventInboxService,
        checkpoint: EventCheckpointRepository,
        expected_guide_os_id: str,
        clock: Callable[[], datetime],
    ) -> None:
        if not isinstance(client, GuideShopEventFeedClient):
            raise TypeError("GuideShopEventFeedClient required")
        if not isinstance(inbox, GuideShopEventInboxService):
            raise TypeError("GuideShopEventInboxService required")
        if not isinstance(checkpoint, EventCheckpointRepository):
            raise TypeError("EventCheckpointRepository required")
        if not callable(clock):
            raise TypeError("UTC clock required")
        self._client = client
        self._inbox = inbox
        self._checkpoint = checkpoint
        self._identity = validate_guide_os_id(expected_guide_os_id)
        self._clock = clock

    async def pull_once(self, *, limit: int = 20) -> PullOnceResult:
        current = self._checkpoint.load(self._identity)
        page = await self._client.fetch_events(cursor=current.cursor, limit=limit)

        for event in page.data:
            if event.guide_os_id != self._identity:
                raise ValueError("event identity mismatch")

        inserted = 0
        duplicates = 0
        stale = 0
        for event in page.data:
            result = self._inbox.ingest(
                event, expected_guide_os_id=self._identity
            )
            if result.outcome == IngestionOutcome.INSERTED:
                inserted += 1
            else:
                duplicates += 1
            if result.state == "stale":
                stale += 1

        advanced = False
        if page.data:
            advanced = self._checkpoint.advance(
                self._identity,
                expected=current,
                next_cursor=page.page.next_cursor,
                updated_at=self._clock(),
            )
        return PullOnceResult(
            fetched_count=len(page.data),
            inserted_count=inserted,
            duplicate_count=duplicates,
            stale_count=stale,
            has_more=page.page.has_more,
            checkpoint_advanced=advanced,
        )
