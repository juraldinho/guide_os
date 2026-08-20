import asyncio
from datetime import datetime, timedelta, timezone
import logging
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import database.db as db_module
from database.db import get_connection
import services.guide_shop_event_worker as worker_module
from services.guide_shop_event_observability import (
    GuideShopEventInboxSnapshot,
    GuideShopEventObservabilityService,
)
from services.guide_shop_event_worker import (
    MAX_CYCLE_DURATION_MS,
    GuideShopEventCycleMetrics,
    GuideShopEventWorker,
)
from tests.test_guide_shop_event_worker import (
    GUIDE_A,
    GUIDE_B,
    FakeClient,
    http_settings,
    signing_settings,
)


NOW = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)


def run(value):
    return asyncio.run(value)


def snapshot(**changes):
    values = {
        "inbox_pending_count": 0,
        "inbox_processing_count": 0,
        "inbox_delivered_count": 0,
        "inbox_stale_count": 0,
        "inbox_dead_letter_count": 0,
        "due_pending_count": 0,
        "abandoned_processing_count": 0,
        "checkpoint_count": 0,
        "oldest_due_pending_age_seconds": None,
    }
    values.update(changes)
    return GuideShopEventInboxSnapshot(**values)


class SnapshotFactory:
    def __init__(self, value=None, error=None):
        self.value = value or snapshot()
        self.error = error
        self.calls = 0

    def __call__(self, *, clock):
        outer = self

        class Service:
            def snapshot(self):
                outer.calls += 1
                if outer.error is not None:
                    raise outer.error
                return outer.value

        return Service()


def make_worker(
    identities=(),
    client_factory=FakeClient,
    *,
    notifications=False,
    monotonic=None,
    observability_factory=None,
):
    kwargs = {}
    if monotonic is not None:
        kwargs["monotonic"] = monotonic
    return GuideShopEventWorker(
        http_settings=http_settings(),
        signing_settings=signing_settings(),
        notifications_enabled=notifications,
        sender=AsyncMock() if notifications else None,
        bot_username="GuideOSBot" if notifications else None,
        clock=lambda: NOW,
        identity_loader=lambda: list(identities),
        client_factory=client_factory,
        observability_factory=observability_factory or SnapshotFactory(),
        **kwargs,
    )


def pull_result(fetched, inserted, duplicate, stale):
    return SimpleNamespace(
        fetched_count=fetched,
        inserted_count=inserted,
        duplicate_count=duplicate,
        stale_count=stale,
    )


def test_exact_cycle_success_duplicate_and_stale_counts(monkeypatch):
    results = iter((pull_result(3, 2, 1, 0), pull_result(2, 1, 0, 1)))

    class Puller:
        def __init__(self, **kwargs):
            pass

        async def pull_once(self, *, limit):
            return next(results)

    monkeypatch.setattr(worker_module, "GuideShopEventPullService", Puller)
    times = iter((10.0, 10.25))
    metrics = run(
        make_worker(
            (GUIDE_A, GUIDE_B),
            lambda settings, identity, provider: FakeClient(identity),
            monotonic=lambda: next(times),
        ).run_cycle()
    )
    assert metrics == GuideShopEventCycleMetrics(
        active_identity_count=2,
        successful_pull_count=2,
        pull_failure_count=0,
        client_cleanup_failure_count=0,
        fetched_event_count=5,
        inserted_event_count=3,
        duplicate_event_count=1,
        stale_event_count=1,
        recovered_pending_count=0,
        recovered_dead_letter_count=0,
        notification_delivered_count=0,
        notification_pending_count=0,
        notification_dead_letter_count=0,
        notification_superseded_count=0,
        notification_processing_failure_count=0,
        cycle_duration_ms=250,
    )


def test_pull_and_cleanup_failure_counters_are_sanitized(monkeypatch, caplog):
    secret = "private-identity-token-cursor-payload"

    class Puller:
        def __init__(self, **kwargs):
            pass

        async def pull_once(self, *, limit):
            raise RuntimeError(secret)

    class Client(FakeClient):
        async def close(self):
            raise RuntimeError(secret)

    monkeypatch.setattr(worker_module, "GuideShopEventPullService", Puller)
    with caplog.at_level(logging.INFO):
        metrics = run(
            make_worker(
                (GUIDE_A,),
                lambda settings, identity, provider: Client(identity),
            ).run_cycle()
        )
    assert metrics.pull_failure_count == 1
    assert metrics.client_cleanup_failure_count == 1
    assert metrics.successful_pull_count == 0
    assert secret not in caplog.text
    assert GUIDE_A not in caplog.text


def test_recovery_and_notification_outcome_counters(monkeypatch, caplog):
    inbox = SimpleNamespace(
        recover_abandoned=Mock(
            return_value=SimpleNamespace(pending_count=2, dead_letter_count=1)
        )
    )
    outcomes = iter(
        (
            SimpleNamespace(outcome="delivered"),
            SimpleNamespace(outcome="pending"),
            SimpleNamespace(outcome="dead_letter"),
            SimpleNamespace(outcome="superseded"),
            SimpleNamespace(outcome="private-sensitive-unexpected-outcome"),
            RuntimeError("sensitive notification failure"),
            SimpleNamespace(outcome="idle"),
        )
    )

    async def process_one():
        value = next(outcomes)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(
        worker_module, "GuideShopEventInboxService", Mock(return_value=inbox)
    )
    monkeypatch.setattr(
        worker_module,
        "GuideShopEventNotificationService",
        Mock(return_value=SimpleNamespace(process_one=process_one)),
    )
    with caplog.at_level(logging.INFO):
        metrics = run(make_worker(notifications=True).run_cycle())
    assert (
        metrics.recovered_pending_count,
        metrics.recovered_dead_letter_count,
        metrics.notification_delivered_count,
        metrics.notification_pending_count,
        metrics.notification_dead_letter_count,
        metrics.notification_superseded_count,
        metrics.notification_processing_failure_count,
    ) == (2, 1, 1, 1, 1, 1, 2)
    assert "private-sensitive-unexpected-outcome" not in caplog.text
    assert "sensitive notification failure" not in caplog.text


@pytest.mark.parametrize(
    ("times", "expected"),
    [
        ((5.0, 4.0), 0),
        ((float("nan"), 5.0), 0),
        ((0.0, 100_000.0), MAX_CYCLE_DURATION_MS),
    ],
)
def test_duration_is_finite_non_negative_and_bounded(times, expected):
    values = iter(times)
    metrics = run(make_worker(monotonic=lambda: next(values)).run_cycle())
    assert metrics.cycle_duration_ms == expected


def insert_inbox(
    event_id,
    state,
    *,
    received_at,
    next_attempt_at=None,
    last_attempt_at=None,
):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO guide_shop_event_inbox (
            event_id, event_type, event_version, schema_version, occurred_at,
            producer, guide_os_id, subject_type, subject_id,
            aggregate_version, state, received_at, next_attempt_at,
            last_attempt_at
        ) VALUES (?, 'visit.created', 'v1', '1.0.0', ?, 'guideshop',
                  ?, 'visit', ?, 1, ?, ?, ?, ?)
        """,
        (
            event_id,
            received_at,
            GUIDE_A,
            f"vis_observe_{event_id}",
            state,
            received_at,
            next_attempt_at,
            last_attempt_at,
        ),
    )
    conn.commit()
    conn.close()


def test_inbox_snapshot_counts_due_lag_and_checkpoint():
    old = (NOW - timedelta(seconds=90)).isoformat().replace("+00:00", "Z")
    future = (NOW + timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    abandoned = (NOW - timedelta(minutes=6)).isoformat().replace("+00:00", "Z")
    insert_inbox("evt_observe_pending_due", "pending", received_at=old)
    insert_inbox(
        "evt_observe_pending_future",
        "pending",
        received_at=old,
        next_attempt_at=future,
    )
    insert_inbox(
        "evt_observe_processing",
        "processing",
        received_at=old,
        last_attempt_at=abandoned,
    )
    for state in ("delivered", "stale", "dead_letter"):
        insert_inbox(f"evt_observe_{state}", state, received_at=old)
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO guide_shop_event_checkpoints (
            guide_os_id, cursor, generation, updated_at
        ) VALUES (?, 'cursor_observe_01', 1, ?)
        """,
        (GUIDE_A, old),
    )
    conn.commit()
    conn.close()
    result = GuideShopEventObservabilityService(
        database_path=db_module.DB_PATH, clock=lambda: NOW
    ).snapshot()
    assert result == snapshot(
        inbox_pending_count=2,
        inbox_processing_count=1,
        inbox_delivered_count=1,
        inbox_stale_count=1,
        inbox_dead_letter_count=1,
        due_pending_count=1,
        abandoned_processing_count=1,
        checkpoint_count=1,
        oldest_due_pending_age_seconds=90,
    )


def test_empty_inbox_has_null_due_lag():
    result = GuideShopEventObservabilityService(
        database_path=db_module.DB_PATH, clock=lambda: NOW
    ).snapshot()
    assert result.oldest_due_pending_age_seconds is None
    assert all(value == 0 for value in result.values()[:-1])


def test_snapshot_is_consistent_during_concurrent_writer():
    def writer():
        received = (NOW - timedelta(seconds=60)).isoformat().replace(
            "+00:00", "Z"
        )
        insert_inbox("evt_observe_late", "pending", received_at=received)

    result = GuideShopEventObservabilityService(
        database_path=db_module.DB_PATH,
        clock=lambda: NOW,
        after_snapshot_started=writer,
    ).snapshot()
    assert result.inbox_pending_count == 0
    assert result.due_pending_count == 0
    later = GuideShopEventObservabilityService(
        database_path=db_module.DB_PATH, clock=lambda: NOW
    ).snapshot()
    assert later.inbox_pending_count == 1
    assert later.due_pending_count == 1


def test_snapshot_failure_is_nonfatal_and_summary_is_still_once(caplog):
    factory = SnapshotFactory(error=RuntimeError("private database path and SQL"))
    with caplog.at_level(logging.INFO):
        metrics = run(make_worker(observability_factory=factory).run_cycle())
    assert isinstance(metrics, GuideShopEventCycleMetrics)
    summaries = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("GuideShop event cycle metrics ")
    ]
    assert len(summaries) == 1
    assert "GuideShop event inbox metrics failed" in caplog.text
    assert "private database path and SQL" not in caplog.text


def test_summary_has_one_stable_approved_field_set_and_no_sensitive_values(
    monkeypatch, caplog
):
    secret = "private-token-cursor-identity-payload-message"

    class Puller:
        def __init__(self, **kwargs):
            pass

        async def pull_once(self, *, limit):
            raise RuntimeError(secret)

    monkeypatch.setattr(worker_module, "GuideShopEventPullService", Puller)
    observed = snapshot(inbox_pending_count=2, oldest_due_pending_age_seconds=7)
    with caplog.at_level(logging.INFO):
        run(
            make_worker(
                (GUIDE_A,),
                lambda settings, identity, provider: FakeClient(identity),
                observability_factory=SnapshotFactory(observed),
            ).run_cycle()
        )
    summaries = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("GuideShop event cycle metrics ")
    ]
    assert len(summaries) == 1
    fields = [item.split("=", 1)[0] for item in summaries[0].split()[4:]]
    assert fields == [
        *worker_module._CYCLE_METRIC_NAMES,
        *worker_module._SNAPSHOT_METRIC_NAMES,
    ]
    assert "notification_superseded_count" in fields
    assert secret not in caplog.text
    assert GUIDE_A not in caplog.text


def test_default_off_builds_no_worker_and_emits_no_metrics(caplog):
    bot = SimpleNamespace(get_me=AsyncMock())
    with caplog.at_level(logging.INFO):
        result = run(
            worker_module.build_guide_shop_event_worker(
                bot,
                {
                    "GUIDESHOP_EVENTS_ENABLED": "false",
                    "GUIDESHOP_NOTIFICATIONS_ENABLED": "false",
                },
            )
        )
    assert result is None
    assert "GuideShop event cycle metrics" not in caplog.text


def test_wal_backup_restore_and_quick_check(tmp_path):
    received = (NOW - timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    insert_inbox("evt_observe_backup", "pending", received_at=received)
    assert GuideShopEventObservabilityService(
        database_path=db_module.DB_PATH, clock=lambda: NOW
    ).snapshot().due_pending_count == 1
    source = get_connection()
    assert source.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    backup_path = tmp_path / "event-observability-backup.db"
    destination = sqlite3.connect(backup_path)
    source.backup(destination)
    source.close()
    assert destination.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    destination.close()
    restored = GuideShopEventObservabilityService(
        database_path=backup_path, clock=lambda: NOW
    ).snapshot()
    assert restored.due_pending_count == 1
