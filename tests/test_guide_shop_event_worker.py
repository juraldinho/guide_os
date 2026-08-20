import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import bot as bot_module
import services.guide_shop_event_worker as worker_module
from database.db import get_connection
from database.queries import get_active_guide_shop_guide_os_ids
from services.guide_shop_contracts import EventListResponseDTO
from services.guide_shop_event_worker import (
    EVENT_PAGE_LIMIT,
    NOTIFICATION_BATCH_LIMIT,
    POLL_INTERVAL_SECONDS,
    RECOVERY_BATCH_LIMIT,
    GuideShopEventRuntimeConfigurationError,
    GuideShopEventWorker,
    AiogramGuideShopEventNotificationSender,
    build_guide_shop_event_worker,
)
from services.guide_shop_settings import (
    GuideShopHTTPSettings,
    GuideShopJWTSigningSettings,
)


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
GUIDE_A = "123e4567-e89b-42d3-a456-426614174000"
GUIDE_B = "123e4567-e89b-42d3-a456-426614174001"


def run(value):
    return asyncio.run(value)


def signing_settings():
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return GuideShopJWTSigningSettings("test", "guide-os.test-1", pem)


def http_settings():
    return GuideShopHTTPSettings("https://api.example.test", "test", 5, 1, 2)


def empty_page():
    return EventListResponseDTO.model_validate(
        {
            "schema_version": "1.0.0",
            "request_id": "req_events_empty_01",
            "data": [],
            "page": {"next_cursor": None, "has_more": False},
        }
    )


class FakeClient:
    def __init__(self, identity, *, error=None, cancel=False):
        self.identity = identity
        self.error = error
        self.cancel = cancel
        self.fetch_calls = []
        self.close_calls = 0

    async def fetch_events(self, *, cursor=None, limit=20):
        self.fetch_calls.append((cursor, limit))
        if self.cancel:
            raise asyncio.CancelledError
        if self.error:
            raise self.error
        return empty_page()

    async def close(self):
        self.close_calls += 1


def worker(
    identities,
    factory,
    *,
    notifications=False,
    sender=None,
    sleep=asyncio.sleep,
    **kwargs,
):
    return GuideShopEventWorker(
        http_settings=http_settings(),
        signing_settings=signing_settings(),
        notifications_enabled=notifications,
        sender=sender,
        bot_username="GuideOSBot" if notifications else None,
        clock=lambda: NOW,
        sleep=sleep,
        identity_loader=lambda: list(identities),
        client_factory=factory,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("events", "notifications", "expected"),
    [
        (False, False, "off"),
        (True, False, "events"),
        (True, True, "notifications"),
        (False, True, "error"),
    ],
)
def test_complete_flag_matrix(monkeypatch, events, notifications, expected):
    http = Mock(return_value=http_settings())
    signing = Mock(return_value=signing_settings())
    bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="GuideOSBot")))
    monkeypatch.setattr(worker_module.GuideShopHTTPSettings, "from_env", http)
    monkeypatch.setattr(worker_module.GuideShopJWTSigningSettings, "from_env", signing)
    values = {
        "GUIDESHOP_EVENTS_ENABLED": str(events).lower(),
        "GUIDESHOP_NOTIFICATIONS_ENABLED": str(notifications).lower(),
    }
    if expected == "error":
        with pytest.raises(GuideShopEventRuntimeConfigurationError):
            run(build_guide_shop_event_worker(bot, values))
        http.assert_not_called()
        signing.assert_not_called()
        bot.get_me.assert_not_awaited()
        return
    result = run(build_guide_shop_event_worker(bot, values))
    if expected == "off":
        assert result is None
        http.assert_not_called()
        signing.assert_not_called()
        bot.get_me.assert_not_awaited()
    else:
        assert isinstance(result, GuideShopEventWorker)
        http.assert_called_once()
        signing.assert_called_once()
        if expected == "notifications":
            bot.get_me.assert_awaited_once_with()
        else:
            bot.get_me.assert_not_awaited()


def test_aiogram_sender_uses_generic_text_and_one_url_button():
    bot = SimpleNamespace(send_message=AsyncMock())
    sender = AiogramGuideShopEventNotificationSender(bot)
    run(sender.send(7001, "Новый визит в GuideShop.", "https://t.me/GuideOSBot?start=gs_safe"))
    bot.send_message.assert_awaited_once()
    args = bot.send_message.await_args.args
    keyboard = bot.send_message.await_args.kwargs["reply_markup"]
    assert args == (7001, "Новый визит в GuideShop.")
    assert len(keyboard.inline_keyboard) == 1
    assert len(keyboard.inline_keyboard[0]) == 1
    button = keyboard.inline_keyboard[0][0]
    assert button.text == "Открыть в GuideShop"
    assert button.url == "https://t.me/GuideOSBot?start=gs_safe"


def add_exchange(identity, request_id, exchange_id, status):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO guide_shop_link_requests (
            id, guide_os_id, token_hash, audience, status, created_at, expires_at
        ) VALUES (?, ?, ?, 'guideshop-link', 'consumed', ?, ?)
        """,
        (request_id, identity, f"hash-{request_id}", NOW.isoformat(), (NOW.replace(year=2027)).isoformat()),
    )
    conn.execute(
        """
        INSERT INTO guide_shop_link_exchanges (
            link_exchange_id, link_request_id, guide_os_id, service_subject,
            guide_membership_ref, status, token_expires_at,
            exchange_expires_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            exchange_id,
            request_id,
            identity,
            f"subject-{request_id}",
            f"membership-{request_id}",
            status,
            NOW.replace(year=2027).isoformat(),
            NOW.replace(year=2027).isoformat(),
            NOW.isoformat(),
            NOW.isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def test_active_identity_query_is_unique_active_and_stable():
    add_exchange(GUIDE_B, 1, "lex_active_b_01", "active")
    add_exchange(GUIDE_A, 2, "lex_active_a_01", "active")
    add_exchange(GUIDE_A, 3, "lex_active_a_02", "active")
    add_exchange("123e4567-e89b-42d3-a456-426614174002", 4, "lex_revoked_01", "revoked")
    assert get_active_guide_shop_guide_os_ids() == [GUIDE_A, GUIDE_B]


def test_empty_identity_set_creates_no_http_client():
    factory = Mock(side_effect=AssertionError("HTTP client created"))
    run(worker([], factory).run_cycle())
    factory.assert_not_called()


def test_one_pull_per_identity_and_every_client_closes():
    clients = []

    def factory(settings, identity, provider):
        client = FakeClient(identity)
        clients.append(client)
        return client

    run(worker([GUIDE_A, GUIDE_B], factory).run_cycle())
    assert [client.identity for client in clients] == [GUIDE_A, GUIDE_B]
    assert [client.fetch_calls for client in clients] == [[(None, EVENT_PAGE_LIMIT)]] * 2
    assert [client.close_calls for client in clients] == [1, 1]


def test_identity_failure_does_not_block_next_and_logs_safely(caplog):
    secret = "private-identity-token-cursor-body"
    clients = []

    def factory(settings, identity, provider):
        client = FakeClient(identity, error=RuntimeError(secret) if identity == GUIDE_A else None)
        clients.append(client)
        return client

    with caplog.at_level(logging.WARNING):
        run(worker([GUIDE_A, GUIDE_B], factory).run_cycle())
    assert len(clients[1].fetch_calls) == 1
    assert [client.close_calls for client in clients] == [1, 1]
    assert secret not in caplog.text
    assert GUIDE_A not in caplog.text


def test_client_closes_on_cancellation():
    client = FakeClient(GUIDE_A, cancel=True)
    with pytest.raises(asyncio.CancelledError):
        run(worker([GUIDE_A], lambda *args: client).run_cycle())
    assert client.close_calls == 1


def test_event_only_mode_never_builds_notification_service(monkeypatch):
    notifications = Mock(side_effect=AssertionError("notification service"))
    monkeypatch.setattr(worker_module, "GuideShopEventNotificationService", notifications)
    run(worker([], Mock(), notifications=False).run_cycle())
    notifications.assert_not_called()


def test_abandoned_recovery_runs_only_with_notifications_enabled(monkeypatch):
    inbox = SimpleNamespace(
        recover_abandoned=Mock(
            return_value=SimpleNamespace(pending_count=0, dead_letter_count=0)
        ),
        claim_due=Mock(return_value=None),
    )
    inbox_factory = Mock(return_value=inbox)
    monkeypatch.setattr(worker_module, "GuideShopEventInboxService", inbox_factory)
    monkeypatch.setattr(
        worker_module,
        "GuideShopEventNotificationService",
        Mock(
            return_value=SimpleNamespace(
                process_one=AsyncMock(
                    return_value=SimpleNamespace(outcome="idle")
                )
            )
        ),
    )

    run(worker([], Mock(), notifications=False).run_cycle())
    inbox_factory.assert_not_called()

    run(worker([], Mock(), notifications=True, sender=AsyncMock()).run_cycle())
    inbox.recover_abandoned.assert_called_once_with(
        limit=RECOVERY_BATCH_LIMIT, apply=True
    )


def test_notification_mode_processes_at_most_twenty(monkeypatch):
    processor = SimpleNamespace(process_one=AsyncMock(return_value=SimpleNamespace(outcome="delivered")))
    monkeypatch.setattr(worker_module, "GuideShopEventNotificationService", Mock(return_value=processor))
    run(worker([], Mock(), notifications=True, sender=AsyncMock()).run_cycle())
    assert processor.process_one.await_count == NOTIFICATION_BATCH_LIMIT == 20


def test_loop_uses_bounded_sleep_and_stops_cleanly():
    sleeps = []

    async def sleep(value):
        sleeps.append(value)
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        run(worker([], Mock(), sleep=sleep).run())
    assert sleeps == [POLL_INTERVAL_SECONDS]


def test_loop_contains_sensitive_cycle_failure_then_preserves_cancellation(caplog):
    secret = "private-database-identity-cursor-token-payload"
    runtime = worker([], Mock())
    runtime.run_cycle = AsyncMock(
        side_effect=[RuntimeError(secret), asyncio.CancelledError]
    )
    sleeps = []

    async def sleep(value):
        sleeps.append(value)

    runtime._sleep = sleep
    with caplog.at_level(logging.WARNING):
        with pytest.raises(asyncio.CancelledError):
            run(runtime.run())
    assert runtime.run_cycle.await_count == 2
    assert sleeps == [POLL_INTERVAL_SECONDS]
    assert "GuideShop event cycle failed" in caplog.text
    assert secret not in caplog.text


def test_bot_starts_at_most_one_task_and_shutdown_cancels_it(monkeypatch):
    started = asyncio.Event()

    class Runtime:
        async def run(self):
            started.set()
            await asyncio.Event().wait()

    build = AsyncMock(return_value=Runtime())
    monkeypatch.setattr(bot_module, "build_guide_shop_event_worker", build)

    async def scenario():
        task = await bot_module.start_guide_shop_event_worker(object(), {})
        await started.wait()
        await bot_module.stop_guide_shop_event_worker(task)
        return task

    task = run(scenario())
    build.assert_awaited_once()
    assert task.cancelled()


def test_bot_provider_cleanup_runs_once_when_worker_shutdown_raises(monkeypatch):
    runner = SimpleNamespace(cleanup=AsyncMock())
    telegram_bot = object()
    dispatcher = SimpleNamespace(
        include_router=Mock(),
        start_polling=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(bot_module, "configure_guide_shop_runtime", Mock())
    monkeypatch.setattr(bot_module, "validate_guide_shop_event_flags", Mock())
    monkeypatch.setattr(bot_module, "Bot", Mock(return_value=telegram_bot))
    monkeypatch.setattr(bot_module, "setup_bot_commands", AsyncMock())
    monkeypatch.setattr(bot_module, "init_db", Mock())
    monkeypatch.setattr(
        bot_module, "start_guide_shop_event_worker", AsyncMock(return_value=object())
    )
    monkeypatch.setattr(
        bot_module,
        "stop_guide_shop_event_worker",
        AsyncMock(side_effect=RuntimeError("worker shutdown failed")),
    )
    monkeypatch.setattr(
        bot_module, "start_guide_shop_link_provider", AsyncMock(return_value=runner)
    )
    monkeypatch.setattr(bot_module, "Dispatcher", Mock(return_value=dispatcher))
    def close_test_coroutine(coroutine):
        coroutine.close()
        return Mock()

    monkeypatch.setattr(
        bot_module.asyncio, "create_task", Mock(side_effect=close_test_coroutine)
    )

    with pytest.raises(RuntimeError, match="worker shutdown failed"):
        run(bot_module.main())
    runner.cleanup.assert_awaited_once_with()


def test_api_entrypoint_and_env_defaults_remain_event_worker_free():
    root = Path(__file__).resolve().parents[1]
    api_source = (root / "guide_shop_link_api.py").read_text(encoding="utf-8")
    assert "guide_shop_event_worker" not in api_source
    assert "GUIDESHOP_EVENTS_ENABLED=false" in (root / ".env.example").read_text()
    assert "GUIDESHOP_NOTIFICATIONS_ENABLED=false" in (root / ".env.example").read_text()
