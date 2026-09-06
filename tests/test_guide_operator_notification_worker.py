"""GO10A2B: bounded guide-notification drain inside the bot process."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest

import bot as bot_module
from database.db import init_db, run_write_with_retry
from database.queries import (
    get_guide_operator_guide_notification_by_source_event_id,
    get_guide_os_id,
    register_user,
)
from services.guide_operator_notification_delivery import (
    CLAIM_LEASE,
    ERROR_AUTHENTICATION,
    ERROR_RETRY_EXHAUSTED,
    ERROR_TIMEOUT,
    ERROR_UNAVAILABLE,
    MAX_DELIVERY_ATTEMPTS,
    NotificationDeliveryResult,
    RETRY_JITTER_FRACTION,
    TelegramHttpResult,
    deliver_one_notification,
    retry_delay,
)
from services.guide_operator_notification_delivery_settings import (
    GuideOperatorNotificationDeliverySettings,
)
from services.guide_operator_notification_outbox import (
    insert_guide_operator_guide_notification,
)
from services.guide_operator_notification_worker import (
    GuideOperatorNotificationWorker,
    GuideOperatorNotificationWorkerConfigurationError,
    GuideOperatorNotificationWorkerSettings,
    _log_result,
    build_guide_operator_notification_worker,
)
from services.guide_operator_notification_worker import logger as worker_logger

FIXED_NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
BOT_TOKEN = "7000000000:TEST_guide_operator_notify_worker_01"
MINI_APP_URL = "https://miniapp.example.com"


def run(awaitable):
    return asyncio.run(awaitable)


class FrozenClock:
    def __init__(self, now: datetime = FIXED_NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeTelegram:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[TelegramHttpResult] = []

    def queue(self, result: TelegramHttpResult) -> None:
        self.responses.append(result)

    def send_webapp_message(self, **kwargs: Any) -> TelegramHttpResult:
        self.calls.append(kwargs)
        if not self.responses:
            return TelegramHttpResult(
                status_code=200, ok=True, telegram_error_code=None, transport_error=None
            )
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def _reset_db() -> Iterator[None]:
    init_db()
    yield


def _delivery_settings() -> GuideOperatorNotificationDeliverySettings:
    return GuideOperatorNotificationDeliverySettings.enabled_with(
        app_env="test",
        bot_token=BOT_TOKEN,
        mini_app_public_url=MINI_APP_URL,
    )


def _seed_guide(user_id: int = 1301) -> str:
    register_user(user_id)
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    return guide_os_id


def _insert_offer_notification(
    guide_os_id: str,
    *,
    source_event_id: str | None = None,
    attempt_count: int = 0,
    next_attempt_at: str | None = None,
    last_error_code: str | None = None,
) -> str:
    eid = source_event_id or str(uuid4())
    assignment_id = str(uuid4())

    def operation(conn):
        insert_guide_operator_guide_notification(
            conn,
            source_event_id=eid,
            guide_os_id=guide_os_id,
            notification_type="assignment_offer",
            company_name="Operator Co",
            assignment_id=assignment_id,
            version_number=1,
            created_at="2026-09-06T10:00:00+00:00",
        )
        if attempt_count or next_attempt_at or last_error_code:
            conn.execute(
                """
                UPDATE guide_operator_guide_notifications
                SET attempt_count = ?, next_attempt_at = ?, last_error_code = ?
                WHERE source_event_id = ?
                """,
                (attempt_count, next_attempt_at, last_error_code, eid),
            )

    run_write_with_retry(operation)
    return eid


def _make_worker(
    http: FakeTelegram,
    *,
    batch_size: int = 10,
    clock: FrozenClock | None = None,
    jitter_unit: float = 0.0,
    sleep: Any = None,
    enabled: bool = True,
    deliver_one: Any = None,
) -> GuideOperatorNotificationWorker:
    delivery = _delivery_settings()
    if enabled:
        settings = GuideOperatorNotificationWorkerSettings.enabled_with(
            poll_interval_seconds=5.0,
            batch_size=batch_size,
            delivery=delivery,
        )
    else:
        settings = GuideOperatorNotificationWorkerSettings.disabled()
    return GuideOperatorNotificationWorker(
        settings=settings,
        delivery_settings=delivery
        if enabled
        else GuideOperatorNotificationDeliverySettings.disabled("test"),
        http_client=http,
        clock=clock or FrozenClock(),
        jitter_unit=lambda: jitter_unit,
        sleep=sleep,
        deliver_one=deliver_one,
    )


def test_worker_defaults_disabled() -> None:
    settings = GuideOperatorNotificationWorkerSettings.from_env({})
    assert settings.enabled is False
    assert settings.batch_size == 10
    assert settings.poll_interval_seconds == 5.0


def test_worker_enabled_without_delivery_fails_closed() -> None:
    with pytest.raises(GuideOperatorNotificationWorkerConfigurationError):
        GuideOperatorNotificationWorkerSettings.from_env(
            {"GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_WORKER_ENABLED": "true"}
        )


def test_worker_enabled_with_incomplete_delivery_fails_closed() -> None:
    with pytest.raises(GuideOperatorNotificationWorkerConfigurationError):
        GuideOperatorNotificationWorkerSettings.from_env(
            {
                "GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_WORKER_ENABLED": "true",
                "GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_DELIVERY_ENABLED": "true",
                "BOT_TOKEN": BOT_TOKEN,
                "MINI_APP_PUBLIC_URL": "",
            }
        )


def test_retry_delay_uses_capped_jitter() -> None:
    assert retry_delay(1, jitter_unit=0.0) == timedelta(seconds=15)
    assert retry_delay(1, jitter_unit=1.0) == timedelta(
        seconds=15 * (1 + RETRY_JITTER_FRACTION)
    )
    assert retry_delay(20, jitter_unit=1.0) == timedelta(minutes=15)


def test_bot_starts_notification_worker_helper_only() -> None:
    source = inspect.getsource(bot_module.main)
    assert "start_guide_operator_notification_worker" in source
    assert "stop_guide_operator_notification_worker" in source
    assert "getUpdates" not in source
    assert "start_polling" in source


def test_empty_queue() -> None:
    http = FakeTelegram()
    worker = _make_worker(http)
    assert run(worker.run_once()) == []
    assert http.calls == []


def test_successful_batch() -> None:
    guide_os_id = _seed_guide(1302)
    first = _insert_offer_notification(guide_os_id)
    second = _insert_offer_notification(guide_os_id)
    third = _insert_offer_notification(guide_os_id)
    http = FakeTelegram()
    worker = _make_worker(http, batch_size=2)
    first_cycle = run(worker.run_once())
    second_cycle = run(worker.run_once())
    assert [item.outcome for item in first_cycle] == ["delivered", "delivered"]
    assert [item.outcome for item in second_cycle] == ["delivered"]
    assert len(http.calls) == 3
    for event_id in (first, second, third):
        row = get_guide_operator_guide_notification_by_source_event_id(event_id)
        assert row is not None
        assert row["delivery_status"] == "delivered"


def test_retry_scheduling_and_backoff() -> None:
    guide_os_id = _seed_guide(1303)
    event_id = _insert_offer_notification(guide_os_id)
    clock = FrozenClock(FIXED_NOW)
    http = FakeTelegram()
    http.queue(
        TelegramHttpResult(
            status_code=503, ok=False, telegram_error_code=None, transport_error=None
        )
    )
    http.queue(
        TelegramHttpResult(
            status_code=503, ok=False, telegram_error_code=None, transport_error=None
        )
    )
    worker = _make_worker(http, clock=clock, jitter_unit=0.0)
    first = run(worker.run_once())
    assert first[0].outcome == "retrying"
    assert first[0].error_code == ERROR_UNAVAILABLE
    row = get_guide_operator_guide_notification_by_source_event_id(event_id)
    assert row is not None
    assert row["next_attempt_at"] == (FIXED_NOW + timedelta(seconds=15)).isoformat()
    assert run(worker.run_once()) == []
    clock.now = FIXED_NOW + timedelta(seconds=15)
    second = run(worker.run_once())
    assert second[0].outcome == "retrying"
    assert len(http.calls) == 2


def test_maximum_attempt_exhaustion() -> None:
    guide_os_id = _seed_guide(1304)
    event_id = _insert_offer_notification(
        guide_os_id,
        attempt_count=MAX_DELIVERY_ATTEMPTS,
        next_attempt_at=FIXED_NOW.isoformat(),
        last_error_code=ERROR_TIMEOUT,
    )
    http = FakeTelegram()
    results = run(_make_worker(http).run_once())
    assert results[0].outcome == "failed"
    assert results[0].error_code == ERROR_RETRY_EXHAUSTED
    assert http.calls == []
    row = get_guide_operator_guide_notification_by_source_event_id(event_id)
    assert row is not None
    assert row["delivery_status"] == "failed"
    assert int(row["attempt_count"]) == MAX_DELIVERY_ATTEMPTS + 1


def test_permanent_failure_remains_inspectable() -> None:
    guide_os_id = _seed_guide(1305)
    event_id = _insert_offer_notification(guide_os_id)
    http = FakeTelegram()
    http.queue(
        TelegramHttpResult(
            status_code=401, ok=False, telegram_error_code=401, transport_error=None
        )
    )
    worker = _make_worker(http)
    first = run(worker.run_once())
    assert first[0].error_code == ERROR_AUTHENTICATION
    assert run(worker.run_once()) == []
    row = get_guide_operator_guide_notification_by_source_event_id(event_id)
    assert row is not None
    assert row["delivery_status"] == "failed"
    assert row["failed_at"] is not None


def test_expired_claim_recovery() -> None:
    guide_os_id = _seed_guide(1306)
    event_id = _insert_offer_notification(
        guide_os_id,
        attempt_count=1,
        next_attempt_at=(FIXED_NOW + CLAIM_LEASE).isoformat(),
    )
    clock = FrozenClock(FIXED_NOW)
    http = FakeTelegram()
    worker = _make_worker(http, clock=clock)
    assert run(worker.run_once()) == []
    assert http.calls == []
    clock.now = FIXED_NOW + CLAIM_LEASE
    recovered = run(worker.run_once())
    assert recovered[0].outcome == "delivered"
    assert recovered[0].source_event_id == event_id
    assert len(http.calls) == 1


def test_in_process_cycles_do_not_overlap() -> None:
    guide_os_id = _seed_guide(1307)
    event_id = _insert_offer_notification(guide_os_id)
    http = FakeTelegram()
    started = threading.Event()
    release = threading.Event()

    def slow_deliver(**kwargs: Any) -> NotificationDeliveryResult | None:
        started.set()
        assert release.wait(timeout=5)
        return deliver_one_notification(**kwargs)

    async def _run() -> list:
        worker = _make_worker(http, deliver_one=slow_deliver)
        first = asyncio.create_task(worker.run_once())
        assert await asyncio.to_thread(started.wait, 2)
        second = asyncio.create_task(worker.run_once())
        await asyncio.sleep(0.05)
        assert not second.done()
        release.set()
        return list(await asyncio.gather(first, second))

    batches = run(_run())
    delivered = [
        item
        for batch in batches
        for item in batch
        if item.outcome == "delivered"
    ]
    assert len(delivered) == 1
    assert delivered[0].source_event_id == event_id
    assert len(http.calls) == 1


def test_graceful_stop_finishes_current_event() -> None:
    guide_os_id = _seed_guide(1308)
    first_id = _insert_offer_notification(guide_os_id)
    second_id = _insert_offer_notification(guide_os_id)
    third_id = _insert_offer_notification(guide_os_id)
    ids = {first_id, second_id, third_id}
    holder: list[GuideOperatorNotificationWorker] = []
    http = FakeTelegram()

    def deliver_and_stop(**kwargs: Any):
        result = deliver_one_notification(**kwargs)
        holder[0].request_stop()
        return result

    worker = _make_worker(http, batch_size=10, deliver_one=deliver_and_stop)
    holder.append(worker)
    results = run(worker.run_once())
    assert len(results) == 1
    assert results[0].source_event_id in ids
    pending = 0
    for event_id in ids:
        row = get_guide_operator_guide_notification_by_source_event_id(event_id)
        assert row is not None
        if row["delivery_status"] == "pending":
            pending += 1
    assert pending == 2


def test_graceful_stop_exits_polling_loop() -> None:
    sleeps = {"count": 0}

    async def sleep(_seconds: float) -> None:
        sleeps["count"] += 1
        worker.request_stop()

    http = FakeTelegram()
    worker = _make_worker(http, sleep=sleep)
    run(worker.run_forever())
    assert sleeps["count"] == 1


def test_one_cycle_does_not_poll() -> None:
    async def sleep(_seconds: float) -> None:
        raise AssertionError("must not poll")

    http = FakeTelegram()
    worker = _make_worker(http, sleep=sleep)
    assert run(worker.run_once()) == []


def test_disabled_configuration_does_not_claim() -> None:
    guide_os_id = _seed_guide(1309)
    event_id = _insert_offer_notification(guide_os_id)
    http = FakeTelegram()
    worker = _make_worker(http, enabled=False)
    assert run(worker.run_once()) == []
    assert http.calls == []
    row = get_guide_operator_guide_notification_by_source_event_id(event_id)
    assert row is not None
    assert int(row["attempt_count"]) == 0


def test_delivery_failure_does_not_stop_forever_loop() -> None:
    cycles = {"count": 0}

    def boom(**_kwargs: Any):
        cycles["count"] += 1
        raise RuntimeError("forced delivery failure")

    async def sleep(_seconds: float) -> None:
        if cycles["count"] >= 2:
            worker.request_stop()

    http = FakeTelegram()
    worker = _make_worker(http, sleep=sleep, deliver_one=boom)
    run(worker.run_forever())
    assert cycles["count"] >= 2


def test_build_disabled_returns_none() -> None:
    assert build_guide_operator_notification_worker({}) is None


def test_bot_main_does_not_create_second_poller() -> None:
    source = inspect.getsource(bot_module)
    assert source.count("start_polling") == 1
    assert "Webhook" not in source
    assert "getUpdates" not in source


def test_operational_log_contains_only_safe_fields() -> None:
    records: list[str] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _ListHandler()
    previous_level = worker_logger.level
    worker_logger.setLevel(logging.INFO)
    worker_logger.addHandler(handler)
    try:
        _log_result(
            NotificationDeliveryResult(
                source_event_id="evt-1",
                notification_type="assignment_offer",
                outcome="retrying",
                error_code=ERROR_UNAVAILABLE,
                attempt_count=2,
                notification_id=42,
            ),
            7,
        )
    finally:
        worker_logger.removeHandler(handler)
        worker_logger.setLevel(previous_level)
    assert records == [
        "notification delivery notification_id=42 event_type=assignment_offer "
        "attempt=2 outcome=retrying error_code=unavailable elapsed_ms=7"
    ]
    assert BOT_TOKEN not in records[0]
    assert "Operator Co" not in records[0]
    assert "chat_id" not in records[0]
