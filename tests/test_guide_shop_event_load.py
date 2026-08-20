import asyncio
import sqlite3
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import jwt
import pytest

import database.db as db_module
from database.db import get_connection
import services.guide_shop_event_worker as worker_module
from services.guide_shop_auth import GuideShopJWTEventAccessTokenProvider
from services.guide_shop_contracts import EventEnvelopeDTO, EventListResponseDTO
from services.guide_shop_event_client import HTTPGuideShopEventFeedClient
from services.guide_shop_event_inbox import GuideShopEventInboxService
from services.guide_shop_event_notifications import GuideShopEventNotificationService
from services.guide_shop_event_observability import GuideShopEventObservabilityService
from services.guide_shop_event_pull import (
    EventCheckpoint,
    EventCheckpointRepository,
    GuideShopEventPullService,
)
from services.guide_shop_event_reconciliation import (
    GuideShopEventReconciliationService,
)
from services.guide_shop_settings import GuideShopHTTPSettings
from tests.test_guide_shop_auth import key_pair, signing_settings
from tests.test_guide_shop_event_notifications import Clock, Sender
from tests.test_guide_shop_event_pull import (
    GUIDE_ID,
    OTHER_ID,
    NOW,
    Response,
    error,
    page,
)
from tests.test_guide_shop_event_worker import FakeClient, worker


PAGE_LIMIT = worker_module.EVENT_PAGE_LIMIT
NOTIFICATION_LIMIT = worker_module.NOTIFICATION_BATCH_LIMIT
LOAD_SIZE = 40
BACKLOG_SIZE = 200
RUNAWAY_CEILING_SECONDS = 15.0


def run(value):
    return asyncio.run(value)


def envelope(
    number: int,
    *,
    guide_id: str = GUIDE_ID,
    aggregate_version: int = 1,
    subject_number: int | None = None,
) -> EventEnvelopeDTO:
    subject = number if subject_number is None else subject_number
    return EventEnvelopeDTO.model_validate(
        {
            "event_id": f"evt_load_{number:08d}",
            "event_type": "visit.created",
            "event_version": "v1",
            "schema_version": "1.0.0",
            "occurred_at": "2026-08-20T08:00:00Z",
            "producer": "guideshop",
            "subject": {
                "type": "visit",
                "id": f"vis_load_{subject:08d}",
            },
            "guide_os_id": guide_id,
            "aggregate_version": aggregate_version,
            "data": {},
        }
    )


def event_page(events, cursor, has_more=False):
    return EventListResponseDTO.model_validate(
        page(
            [item.model_dump(mode="json") for item in events],
            cursor,
            has_more,
        )
    )


class Feed:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    async def fetch_events(self, *, cursor=None, limit=20):
        self.calls.append((cursor, limit))
        return self.pages.pop(0)


def puller(feed, *, inbox=None, identity=GUIDE_ID):
    return GuideShopEventPullService(
        client=feed,
        inbox=inbox or GuideShopEventInboxService(clock=lambda: NOW),
        checkpoint=EventCheckpointRepository(),
        expected_guide_os_id=identity,
        clock=lambda: NOW,
    )


def table_count(table, where="", parameters=()):
    conn = get_connection()
    try:
        return conn.execute(
            f"SELECT COUNT(*) FROM {table} {where}", parameters
        ).fetchone()[0]
    finally:
        conn.close()


def map_user(user_id=7001, guide_id=GUIDE_ID):
    conn = get_connection()
    conn.execute(
        "INSERT INTO users (user_id, guide_os_id) VALUES (?, ?)",
        (user_id, guide_id),
    )
    conn.commit()
    conn.close()


def checkpoint(identity=GUIDE_ID, cursor="cursor_load_final"):
    repository = EventCheckpointRepository()
    assert repository.advance(
        identity,
        expected=repository.load(identity),
        next_cursor=cursor,
        updated_at=NOW,
    )


def test_load_two_pages_ingest_40_and_identical_replay_converges():
    events = [envelope(number, subject_number=1, aggregate_version=number) for number in range(1, LOAD_SIZE + 1)]
    first_page = event_page(events[:PAGE_LIMIT], "cursor_load_page_1", True)
    second_page = event_page(events[PAGE_LIMIT:], "cursor_load_page_2")
    feed = Feed([first_page, second_page, second_page])
    service = puller(feed)
    started = time.monotonic()

    first = run(service.pull_once())
    second = run(service.pull_once())
    replay = run(service.pull_once())
    elapsed = time.monotonic() - started

    assert (first.fetched_count, second.fetched_count) == (PAGE_LIMIT, PAGE_LIMIT)
    assert (first.inserted_count, second.inserted_count) == (PAGE_LIMIT, PAGE_LIMIT)
    assert replay.duplicate_count == PAGE_LIMIT
    assert replay.inserted_count == 0
    assert table_count("guide_shop_event_inbox") == LOAD_SIZE
    assert table_count("guide_shop_event_watermarks") == 1
    assert EventCheckpointRepository().load(GUIDE_ID) == EventCheckpoint(
        "cursor_load_page_2", 2
    )
    assert feed.calls == [
        (None, PAGE_LIMIT),
        ("cursor_load_page_1", PAGE_LIMIT),
        ("cursor_load_page_2", PAGE_LIMIT),
    ]
    assert elapsed < RUNAWAY_CEILING_SECONDS


def test_load_multiple_principals_remain_isolated():
    inbox = GuideShopEventInboxService(clock=lambda: NOW)
    started = time.monotonic()
    for number in range(1, 21):
        inbox.ingest(envelope(number), expected_guide_os_id=GUIDE_ID)
        inbox.ingest(
            envelope(100 + number, guide_id=OTHER_ID),
            expected_guide_os_id=OTHER_ID,
        )
    checkpoint(GUIDE_ID, "cursor_load_guide_a")
    checkpoint(OTHER_ID, "cursor_load_guide_b")
    elapsed = time.monotonic() - started

    conn = get_connection()
    try:
        counts = dict(
            conn.execute(
                "SELECT guide_os_id, COUNT(*) FROM guide_shop_event_inbox GROUP BY guide_os_id"
            ).fetchall()
        )
    finally:
        conn.close()
    assert counts == {GUIDE_ID: 20, OTHER_ID: 20}
    assert EventCheckpointRepository().load(GUIDE_ID).cursor == "cursor_load_guide_a"
    assert EventCheckpointRepository().load(OTHER_ID).cursor == "cursor_load_guide_b"
    assert elapsed < RUNAWAY_CEILING_SECONDS


def test_load_concurrent_identical_and_distinct_ingestion_is_lossless():
    identical_barrier = threading.Barrier(8)
    identical_outcomes = []

    def ingest_identical():
        identical_barrier.wait()
        result = GuideShopEventInboxService(clock=lambda: NOW).ingest(
            envelope(1), expected_guide_os_id=GUIDE_ID
        )
        identical_outcomes.append(result.outcome.value)

    threads = [threading.Thread(target=ingest_identical) for _ in range(8)]
    started = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(RUNAWAY_CEILING_SECONDS)
        assert not thread.is_alive()
    assert identical_outcomes.count("inserted") == 1
    assert identical_outcomes.count("duplicate") == 7

    distinct_barrier = threading.Barrier(LOAD_SIZE)
    errors = []

    def ingest_distinct(number):
        try:
            distinct_barrier.wait()
            GuideShopEventInboxService(clock=lambda: NOW).ingest(
                envelope(number + 1), expected_guide_os_id=GUIDE_ID
            )
        except BaseException as exc:
            errors.append(exc)

    distinct = [
        threading.Thread(target=ingest_distinct, args=(number,))
        for number in range(1, LOAD_SIZE + 1)
    ]
    for thread in distinct:
        thread.start()
    for thread in distinct:
        thread.join(RUNAWAY_CEILING_SECONDS)
        assert not thread.is_alive()
    elapsed = time.monotonic() - started
    assert errors == []
    assert table_count("guide_shop_event_inbox") == LOAD_SIZE + 1
    assert elapsed < RUNAWAY_CEILING_SECONDS


def test_load_reverse_aggregate_versions_are_deterministic():
    inbox = GuideShopEventInboxService(clock=lambda: NOW)
    started = time.monotonic()
    results = [
        inbox.ingest(
            envelope(number, aggregate_version=number, subject_number=1),
            expected_guide_os_id=GUIDE_ID,
        )
        for number in range(LOAD_SIZE, 0, -1)
    ]
    elapsed = time.monotonic() - started
    assert [result.state for result in results].count("pending") == 1
    assert [result.state for result in results].count("stale") == LOAD_SIZE - 1
    watermark = inbox.get_watermark(
        guide_os_id=GUIDE_ID,
        subject_type="visit",
        subject_id="vis_load_00000001",
    )
    assert watermark.highest_aggregate_version == LOAD_SIZE
    assert elapsed < RUNAWAY_CEILING_SECONDS


def test_load_checkpoint_cas_contention_has_one_winner_and_no_regression():
    repository = EventCheckpointRepository()
    initial = repository.load(GUIDE_ID)
    barrier = threading.Barrier(10)
    outcomes = []

    def advance(number):
        barrier.wait()
        outcomes.append(
            repository.advance(
                GUIDE_ID,
                expected=initial,
                next_cursor=f"cursor_contention_{number:02d}",
                updated_at=NOW,
            )
        )

    threads = [threading.Thread(target=advance, args=(number,)) for number in range(10)]
    started = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(RUNAWAY_CEILING_SECONDS)
        assert not thread.is_alive()
    winner = repository.load(GUIDE_ID)
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 9
    assert repository.advance(
        GUIDE_ID,
        expected=initial,
        next_cursor="cursor_regression_00",
        updated_at=NOW,
    ) is False
    assert repository.load(GUIDE_ID) == winner
    assert time.monotonic() - started < RUNAWAY_CEILING_SECONDS


def test_load_two_worker_cycles_obey_page_and_notification_limits(monkeypatch):
    class Puller:
        calls = 0

        def __init__(self, **kwargs):
            pass

        async def pull_once(self, *, limit):
            assert limit == PAGE_LIMIT
            Puller.calls += 1
            return SimpleNamespace(
                fetched_count=PAGE_LIMIT,
                inserted_count=PAGE_LIMIT,
                duplicate_count=0,
                stale_count=0,
            )

    processor = SimpleNamespace(
        process_one=AsyncMock(
            return_value=SimpleNamespace(outcome="delivered")
        )
    )
    inbox = SimpleNamespace(
        recover_abandoned=Mock(
            return_value=SimpleNamespace(pending_count=0, dead_letter_count=0)
        )
    )
    monkeypatch.setattr(worker_module, "GuideShopEventPullService", Puller)
    monkeypatch.setattr(
        worker_module, "GuideShopEventInboxService", Mock(return_value=inbox)
    )
    monkeypatch.setattr(
        worker_module,
        "GuideShopEventNotificationService",
        Mock(return_value=processor),
    )
    runtime = worker(
        [GUIDE_ID],
        lambda *args: FakeClient(GUIDE_ID),
        notifications=True,
        sender=AsyncMock(),
    )
    results = [run(runtime.run_cycle()), run(runtime.run_cycle())]
    assert Puller.calls == 2
    assert [result.fetched_event_count for result in results] == [PAGE_LIMIT] * 2
    assert [result.notification_delivered_count for result in results] == [NOTIFICATION_LIMIT] * 2
    assert processor.process_one.await_count == LOAD_SIZE


def test_load_40_notification_jobs_deliver_in_two_bounded_batches():
    clock = Clock()
    inbox = GuideShopEventInboxService(clock=clock)
    sender = Sender()
    map_user()
    for number in range(1, LOAD_SIZE + 1):
        inbox.ingest(envelope(number), expected_guide_os_id=GUIDE_ID)
    service = GuideShopEventNotificationService(
        inbox=inbox,
        sender=sender,
        bot_username="GuideOSBot",
        clock=clock,
    )
    started = time.monotonic()
    outcomes = []
    for _ in range(2):
        outcomes.extend(
            run(service.process_one()).outcome for _ in range(NOTIFICATION_LIMIT)
        )
    elapsed = time.monotonic() - started
    assert outcomes == ["delivered"] * LOAD_SIZE
    assert len(sender.calls) == LOAD_SIZE
    assert table_count("guide_shop_event_inbox", "WHERE state = 'delivered'") == LOAD_SIZE
    assert run(service.process_one()).outcome == "idle"
    assert elapsed < RUNAWAY_CEILING_SECONDS


def test_load_backlog_snapshot_and_reconciliation_match_database():
    inbox = GuideShopEventInboxService(clock=lambda: NOW)
    started = time.monotonic()
    for number in range(1, BACKLOG_SIZE + 1):
        inbox.ingest(envelope(number), expected_guide_os_id=GUIDE_ID)
    checkpoint()
    snapshot = GuideShopEventObservabilityService(
        database_path=db_module.DB_PATH, clock=lambda: NOW
    ).snapshot()
    report = GuideShopEventReconciliationService(
        database_path=db_module.DB_PATH, clock=lambda: NOW
    ).reconcile()
    elapsed = time.monotonic() - started
    assert snapshot.inbox_pending_count == BACKLOG_SIZE
    assert snapshot.due_pending_count == BACKLOG_SIZE
    assert snapshot.checkpoint_count == 1
    assert report.inbox_pending_count == BACKLOG_SIZE
    assert report.verdict == "CLEAN"
    assert table_count("guide_shop_event_inbox") == BACKLOG_SIZE
    assert elapsed < RUNAWAY_CEILING_SECONDS


def test_failure_sqlite_lock_contention_retries_without_lost_row(monkeypatch):
    real_get_connection = db_module.get_connection

    def short_timeout_connection():
        conn = real_get_connection()
        conn.execute("PRAGMA busy_timeout = 1")
        return conn

    lock = sqlite3.connect(db_module.DB_PATH, timeout=1)
    lock.execute("BEGIN IMMEDIATE")
    monkeypatch.setattr(db_module, "get_connection", short_timeout_connection)
    result = []
    errors = []

    def ingest():
        try:
            result.append(
                GuideShopEventInboxService(clock=lambda: NOW).ingest(
                    envelope(1), expected_guide_os_id=GUIDE_ID
                )
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=ingest)
    started = time.monotonic()
    thread.start()
    time.sleep(0.25)
    lock.rollback()
    lock.close()
    thread.join(RUNAWAY_CEILING_SECONDS)
    assert not thread.is_alive()
    assert errors == []
    assert len(result) == 1
    assert table_count("guide_shop_event_inbox") == 1
    assert time.monotonic() - started < RUNAWAY_CEILING_SECONDS


def test_failure_partial_page_keeps_checkpoint_and_replay_converges():
    class FailingInbox(GuideShopEventInboxService):
        def __init__(self):
            super().__init__(clock=lambda: NOW)
            self.calls = 0

        def ingest(self, value, *, expected_guide_os_id):
            self.calls += 1
            if self.calls == 11:
                raise RuntimeError("synthetic failure")
            return super().ingest(
                value, expected_guide_os_id=expected_guide_os_id
            )

    values = [envelope(number) for number in range(1, PAGE_LIMIT + 1)]
    response = event_page(values, "cursor_partial_page")
    with pytest.raises(RuntimeError, match="synthetic failure"):
        run(puller(Feed([response]), inbox=FailingInbox()).pull_once())
    assert EventCheckpointRepository().load(GUIDE_ID) == EventCheckpoint(None, 0)
    assert table_count("guide_shop_event_inbox") == 10
    replay = run(puller(Feed([response])).pull_once())
    assert (replay.duplicate_count, replay.inserted_count) == (10, 10)
    assert replay.checkpoint_advanced is True
    assert table_count("guide_shop_event_inbox") == PAGE_LIMIT


@pytest.mark.parametrize("failure", [429, 503, "timeout"])
def test_failure_http_retries_are_bounded_and_use_fresh_jwts(
    failure, signing_settings
):
    provider = GuideShopJWTEventAccessTokenProvider(signing_settings)

    class FailureSession:
        def __init__(self):
            self.calls = []
            self.number = 0

        async def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            self.number += 1
            if self.number == 1:
                if failure == "timeout":
                    raise asyncio.TimeoutError
                return Response(
                    failure,
                    error(
                        "rate_limited" if failure == 429 else "temporarily_unavailable",
                        1,
                    ),
                )
            return Response(payload=page([], None, False))

    session = FailureSession()
    client = HTTPGuideShopEventFeedClient(
        GuideShopHTTPSettings(
            "https://api.guideshop.example", "test", 5, 1, 2
        ),
        GUIDE_ID,
        provider,
        session=session,
        owns_session=False,
        sleep=AsyncMock(),
    )
    started = time.monotonic()
    run(client.fetch_events())
    elapsed = time.monotonic() - started
    tokens = [call[2]["headers"]["Authorization"].split(" ", 1)[1] for call in session.calls]
    jtis = [jwt.decode(token, options={"verify_signature": False})["jti"] for token in tokens]
    assert len(session.calls) == 2
    assert len(set(tokens)) == len(set(jtis)) == 2
    assert elapsed < RUNAWAY_CEILING_SECONDS


def test_failure_http_cleanup_on_success_failure_and_cancellation():
    success = FakeClient(GUIDE_ID)
    run(worker([GUIDE_ID], lambda *args: success).run_cycle())
    assert success.close_calls == 1

    failed = FakeClient(GUIDE_ID, error=RuntimeError("synthetic"))
    run(worker([GUIDE_ID], lambda *args: failed).run_cycle())
    assert failed.close_calls == 1

    cancelled = FakeClient(GUIDE_ID, cancel=True)
    with pytest.raises(asyncio.CancelledError):
        run(worker([GUIDE_ID], lambda *args: cancelled).run_cycle())
    assert cancelled.close_calls == 1


def test_failure_sender_retry_dead_letter_is_bounded_and_not_auto_replayed():
    clock = Clock()
    inbox = GuideShopEventInboxService(clock=clock)
    sender = Sender(RuntimeError("synthetic transport"))
    map_user()
    inbox.ingest(envelope(1), expected_guide_os_id=GUIDE_ID)
    conn = get_connection()
    conn.execute(
        "UPDATE guide_shop_event_inbox SET max_attempts = 2 WHERE event_id = ?",
        ("evt_load_00000001",),
    )
    conn.commit()
    conn.close()
    service = GuideShopEventNotificationService(
        inbox=inbox, sender=sender, bot_username="GuideOSBot", clock=clock
    )
    assert run(service.process_one()).outcome == "pending"
    clock.advance()
    assert run(service.process_one()).outcome == "dead_letter"
    assert len(sender.calls) == 2
    clock.advance()
    assert run(service.process_one()).outcome == "idle"
    assert inbox.get_event("evt_load_00000001").state == "dead_letter"


def test_failure_worker_cancellation_has_no_leaked_tasks_or_sessions():
    async def scenario():
        started = asyncio.Event()
        client = FakeClient(GUIDE_ID)

        async def sleep(_):
            started.set()
            await asyncio.Event().wait()

        runtime = worker([GUIDE_ID], lambda *args: client, sleep=sleep)
        task = asyncio.create_task(runtime.run())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        remaining = [item for item in asyncio.all_tasks() if item is not asyncio.current_task() and not item.done()]
        return client, remaining

    client, remaining = run(scenario())
    assert client.close_calls == 1
    assert remaining == []


def test_failure_abandoned_crash_reconciles_then_recovers_cleanly():
    clock = Clock()
    inbox = GuideShopEventInboxService(clock=clock)
    inbox.ingest(envelope(1), expected_guide_os_id=GUIDE_ID)
    checkpoint()
    claim = inbox.claim_due()
    assert claim is not None
    clock.advance(301)
    before = GuideShopEventReconciliationService(
        database_path=db_module.DB_PATH, clock=clock
    ).reconcile()
    assert before.verdict == "NEEDS_ATTENTION"
    assert before.abandoned_processing_count == 1
    recovered = inbox.recover_abandoned(limit=100, apply=True)
    after = GuideShopEventReconciliationService(
        database_path=db_module.DB_PATH, clock=clock
    ).reconcile()
    assert (recovered.pending_count, recovered.dead_letter_count) == (1, 0)
    assert inbox.get_event(claim.event.event_id).attempt_count == 1
    assert after.verdict == "CLEAN"


def test_failure_pull_once_never_traverses_unbounded_pages():
    values = [envelope(number) for number in range(1, PAGE_LIMIT + 1)]
    feed = Feed(
        [
            event_page(values, "cursor_more_pages", True),
            event_page(values, "cursor_should_not_fetch", True),
        ]
    )
    result = run(puller(feed).pull_once())
    assert result.has_more is True
    assert len(feed.calls) == 1
    assert len(feed.pages) == 1
