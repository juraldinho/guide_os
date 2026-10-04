from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from collections import Counter

import pytest

import bot
import database.db as db_module
import guide_os_staging_runtime as runtime_module
from guide_os_staging_runtime import (
    ConsolidatedStagingRuntimeConfigurationError,
    ConsolidatedStagingRuntimeSettings,
    RuntimeDependencies,
    run_consolidated_staging_runtime,
)
from web_api.app import create_miniapp_api_app
from web_api.guide_operator_integration import create_guide_operator_integration_app
from services.miniapp_api_settings import MiniAppApiSettings
from services.guide_operator_service_auth_settings import GuideOperatorServiceAuthSettings


def run(awaitable):
    return asyncio.run(awaitable)


def _env(**overrides):
    values = {
        "APP_ENV": "staging",
        "GUIDE_OS_CONSOLIDATED_STAGING_RUNTIME_ENABLED": "true",
        "GUIDE_OS_CONSOLIDATED_STAGING_REPLICA_COUNT": "1",
        "GUIDE_OS_CONSOLIDATED_STAGING_SHUTDOWN_TIMEOUT_SECONDS": "2",
        "DATABASE_PATH": "/data/guide_os.db",
        "MINI_APP_API_ENABLED": "true",
        "MINI_APP_API_HOST": "0.0.0.0",
        "MINI_APP_API_PORT": "8083",
        "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED": "true",
        "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_HOST": "0.0.0.0",
        "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_PORT": "8084",
        "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_ENABLED": "true",
        "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ENABLED": "true",
        "GUIDESHOP_LINK_PROVIDER_ENABLED": "false",
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    "overrides",
    [
        {"APP_ENV": "production"},
        {"APP_ENV": "development"},
        {"GUIDE_OS_CONSOLIDATED_STAGING_RUNTIME_ENABLED": "false"},
        {"GUIDE_OS_CONSOLIDATED_STAGING_REPLICA_COUNT": "2"},
        {"DATABASE_PATH": "guide_os.db"},
        {"DATABASE_PATH": "/tmp/guide_os.db"},
        {"MINI_APP_API_ENABLED": "false"},
        {"GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED": "false"},
        {"GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ENABLED": "false"},
        {"GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ONCE": "true"},
        {"GUIDESHOP_LINK_PROVIDER_ENABLED": "true"},
        {"MINI_APP_API_PORT": "8084"},
    ],
)
def test_staging_runtime_guards_fail_closed(overrides):
    with pytest.raises(ConsolidatedStagingRuntimeConfigurationError):
        ConsolidatedStagingRuntimeSettings.from_env(_env(**overrides))


def test_settings_pin_separate_http_ports_and_shared_volume():
    settings = ConsolidatedStagingRuntimeSettings.from_env(_env())
    assert settings.database_path == "/data/guide_os.db"
    assert settings.miniapp_port == 8083
    assert settings.integration_port == 8084


def test_database_binding_must_match_imported_sqlite_path(monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", "/data/other.db")
    with pytest.raises(
        ConsolidatedStagingRuntimeConfigurationError,
        match="one database",
    ):
        runtime_module._validate_database_binding("/data/guide_os.db")


def test_runtime_starts_each_required_component_once_and_shuts_down(monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", "/data/guide_os.db")
    calls = Counter()
    outbound_stop = threading.Event()
    integration_stopped = asyncio.Event()

    async def bot_runner():
        calls["poller"] += 1
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            calls["bot_cancelled"] += 1
            raise

    async def integration_runner(stop):
        calls["integration"] += 1
        await stop.wait()
        integration_stopped.set()

    def outbound_runner():
        calls["outbound"] += 1
        outbound_stop.wait()

    def stop_outbound():
        calls["outbound_stop"] += 1
        outbound_stop.set()

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(
            run_consolidated_staging_runtime(
                _env(),
                dependencies=RuntimeDependencies(
                    bot_runner,
                    integration_runner,
                    outbound_runner,
                    stop_outbound,
                ),
                stop_event=stop,
            )
        )
        await asyncio.sleep(0.05)
        stop.set()
        await task

    run(scenario())
    assert calls == Counter(
        poller=1,
        integration=1,
        outbound=1,
        outbound_stop=1,
        bot_cancelled=1,
    )
    assert integration_stopped.is_set()


def test_required_component_exit_stops_complete_runtime(monkeypatch, caplog):
    monkeypatch.setattr(db_module, "DB_PATH", "/data/guide_os.db")
    outbound_stop = threading.Event()
    integration_stopped = asyncio.Event()
    sensitive = "sensitive-component-detail"

    async def failed_bot():
        raise RuntimeError(sensitive)

    async def integration_runner(stop):
        await stop.wait()
        integration_stopped.set()

    def outbound_runner():
        outbound_stop.wait()

    with caplog.at_level(logging.INFO), pytest.raises(
        RuntimeError, match="required runtime component stopped"
    ):
        run(
            run_consolidated_staging_runtime(
                _env(),
                dependencies=RuntimeDependencies(
                    failed_bot,
                    integration_runner,
                    outbound_runner,
                    outbound_stop.set,
                ),
                stop_event=asyncio.Event(),
            )
        )
    assert integration_stopped.is_set()
    assert outbound_stop.is_set()
    assert sensitive not in caplog.text
    assert "Required runtime component stopped" in caplog.text


def test_http_apps_remain_separate_route_surfaces():
    miniapp = create_miniapp_api_app(
        MiniAppApiSettings(enabled=True, bot_token="test-token")
    )
    integration = create_guide_operator_integration_app(
        auth_settings=GuideOperatorServiceAuthSettings.disabled()
    )
    miniapp_paths = {resource.canonical for resource in miniapp.router.resources()}
    integration_paths = {
        resource.canonical for resource in integration.router.resources()
    }
    assert any(path.startswith("/app/v1/") for path in miniapp_paths)
    assert not any(path.startswith("/integration/v1/") for path in miniapp_paths)
    assert any(path.startswith("/integration/v1/") for path in integration_paths)
    assert not any(path.startswith("/app/v1/") for path in integration_paths)


def test_production_bot_entrypoint_and_notification_ownership_are_unchanged():
    bot_source = inspect.getsource(bot)
    runtime_source = inspect.getsource(runtime_module)
    assert 'if __name__ == "__main__":\n    asyncio.run(main())' in bot_source
    assert bot_source.count("dp.start_polling") == 1
    assert "start_guide_operator_notification_worker" in bot_source
    assert "real_background_tasks" in bot_source
    assert "start_guide_operator_notification_worker" not in runtime_source
    assert "create_subprocess" not in runtime_source
    assert "shell=True" not in runtime_source
