import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import bot as bot_module


def run(awaitable):
    return asyncio.run(awaitable)


def _bot_runtime(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "runtime-test-token")
    runtime = SimpleNamespace(
        order=[],
        miniapp_runner=Mock(),
        provider_runner=Mock(),
        miniapp_start=AsyncMock(),
        provider_start=AsyncMock(),
        polling=AsyncMock(),
        bot=Mock(),
        created_tasks=[],
    )
    runtime.miniapp_runner.cleanup = AsyncMock()
    runtime.provider_runner.cleanup = AsyncMock()
    runtime.miniapp_start.return_value = runtime.miniapp_runner
    runtime.provider_start.return_value = runtime.provider_runner

    async def start_miniapp_api(*args, **kwargs):
        runtime.order.append("start_miniapp_api")
        return await runtime.miniapp_start(*args, **kwargs)

    async def start_provider(*args, **kwargs):
        runtime.order.append("start_provider")
        return await runtime.provider_start(*args, **kwargs)

    async def start_polling(*args, **kwargs):
        runtime.order.append("start_polling")
        return await runtime.polling(*args, **kwargs)

    def create_task(coro, *args, **kwargs):
        coro.close()
        task = Mock()
        runtime.created_tasks.append(task)
        return task

    dispatcher = Mock()
    dispatcher.start_polling = start_polling

    monkeypatch.setattr(bot_module, "setup_logging", Mock())
    monkeypatch.setattr(bot_module, "configure_guide_shop_runtime", Mock())
    monkeypatch.setattr(bot_module, "configure_miniapp_runtime", Mock())
    monkeypatch.setattr(bot_module, "validate_guide_shop_event_flags", Mock())
    monkeypatch.setattr(bot_module, "Bot", Mock(return_value=runtime.bot))
    monkeypatch.setattr(bot_module, "setup_bot_commands", AsyncMock())
    monkeypatch.setattr(
        bot_module, "init_db", Mock(side_effect=lambda: runtime.order.append("init_db"))
    )
    monkeypatch.setattr(bot_module, "send_daily_admin_report", AsyncMock())
    monkeypatch.setattr(bot_module, "send_tour_reminders", AsyncMock())
    monkeypatch.setattr(bot_module.asyncio, "create_task", create_task)
    monkeypatch.setattr(
        bot_module, "start_guide_shop_event_worker", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(bot_module, "stop_guide_shop_event_worker", AsyncMock())
    monkeypatch.setattr(bot_module, "start_guide_shop_link_provider", start_provider)
    monkeypatch.setattr(bot_module, "start_miniapp_api", start_miniapp_api)
    monkeypatch.setattr(bot_module, "Dispatcher", Mock(return_value=dispatcher))
    return runtime


def test_miniapp_api_disabled_skips_runner(monkeypatch):
    runtime = _bot_runtime(monkeypatch)
    runtime.miniapp_start.return_value = None

    run(bot_module.main())

    assert "start_miniapp_api" in runtime.order
    runtime.miniapp_runner.cleanup.assert_not_awaited()
    runtime.provider_runner.cleanup.assert_awaited_once_with()


def test_miniapp_api_enabled_starts_and_cleans_runner(monkeypatch):
    runtime = _bot_runtime(monkeypatch)

    run(bot_module.main())

    assert runtime.order == [
        "init_db",
        "start_provider",
        "start_miniapp_api",
        "start_polling",
    ]
    runtime.miniapp_start.assert_awaited_once_with()
    runtime.miniapp_runner.cleanup.assert_awaited_once_with()
    runtime.provider_runner.cleanup.assert_awaited_once_with()


def test_miniapp_cleanup_runs_when_event_worker_shutdown_fails(monkeypatch):
    runtime = _bot_runtime(monkeypatch)
    monkeypatch.setattr(
        bot_module,
        "stop_guide_shop_event_worker",
        AsyncMock(side_effect=RuntimeError("worker shutdown failed")),
    )

    with pytest.raises(RuntimeError, match="worker shutdown failed"):
        run(bot_module.main())

    runtime.miniapp_runner.cleanup.assert_awaited_once_with()
    runtime.provider_runner.cleanup.assert_awaited_once_with()


def test_miniapp_cleanup_runs_when_polling_fails(monkeypatch):
    runtime = _bot_runtime(monkeypatch)
    runtime.polling.side_effect = RuntimeError("polling failed")

    with pytest.raises(RuntimeError, match="polling failed"):
        run(bot_module.main())

    runtime.miniapp_runner.cleanup.assert_awaited_once_with()
    runtime.provider_runner.cleanup.assert_awaited_once_with()


def test_miniapp_cleanup_runs_when_provider_cleanup_fails(monkeypatch):
    runtime = _bot_runtime(monkeypatch)
    runtime.provider_runner.cleanup.side_effect = RuntimeError("provider cleanup failed")

    with pytest.raises(RuntimeError, match="provider cleanup failed"):
        run(bot_module.main())

    runtime.provider_runner.cleanup.assert_awaited_once_with()
    runtime.miniapp_runner.cleanup.assert_awaited_once_with()
