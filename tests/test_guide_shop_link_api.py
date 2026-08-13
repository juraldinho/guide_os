import asyncio
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp.test_utils import make_mocked_request
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import guide_shop_link_api as api_module
from services.guide_shop_inbound_auth import GuideShopInboundJWTVerifier
from services.guide_shop_link_exchange_service import GuideShopLinkExchangeService
from services.guide_shop_link_provider import create_guide_shop_link_provider_app
from services.guide_shop_settings import GuideShopInboundJWTSettings


ROOT = Path(__file__).resolve().parents[1]
KID = "link-key-2026"


def run(awaitable):
    return asyncio.run(awaitable)


def _staging_env(public_pem: str, **overrides):
    values = {
        "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
        "GUIDESHOP_LINK_PROVIDER_STAGING_ENABLED": "true",
        "GUIDESHOP_LINK_PROVIDER_HOST": "0.0.0.0",
        "PORT": "8080",
        "APP_ENV": "staging",
        "GUIDESHOP_LINK_JWT_PUBLIC_KEYS": json.dumps({KID: public_pem}),
    }
    values.update(overrides)
    return values


def _local_env(public_pem: str, **overrides):
    values = {
        "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
        "GUIDESHOP_LINK_PROVIDER_HOST": "127.0.0.1",
        "GUIDESHOP_LINK_PROVIDER_PORT": "8082",
        "APP_ENV": "test",
        "GUIDESHOP_LINK_JWT_PUBLIC_KEYS": json.dumps({KID: public_pem}),
    }
    values.update(overrides)
    return values


@pytest.fixture
def public_pem():
    key = Ed25519PrivateKey.generate()
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def test_entrypoint_import_succeeds_without_bot_token_and_without_bot_modules():
    env = os.environ.copy()
    env.pop("BOT_TOKEN", None)
    env["PYTHONPATH"] = str(ROOT)
    script = (
        "import os, sys\n"
        "assert 'BOT_TOKEN' not in os.environ\n"
        "import guide_shop_link_api\n"
        "assert 'bot' not in sys.modules\n"
        "assert 'config' not in sys.modules\n"
        "assert 'aiogram' not in sys.modules\n"
        "print('ok')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_entrypoint_module_does_not_reference_telegram_runtime():
    source = (ROOT / "guide_shop_link_api.py").read_text(encoding="utf-8")
    assert "BOT_TOKEN" not in source
    assert "aiogram" not in source
    assert "Dispatcher" not in source
    assert "start_polling" not in source
    assert "import bot" not in source
    assert "import config" not in source
    assert "from bot" not in source
    assert "from config" not in source


def test_health_returns_fixed_non_sensitive_payload(public_pem, monkeypatch):
    settings = GuideShopInboundJWTSettings("test", {KID: public_pem})
    app = create_guide_shop_link_provider_app(
        GuideShopInboundJWTVerifier(settings),
        GuideShopLinkExchangeService(),
    )
    queried = Mock(side_effect=AssertionError("database queried"))
    monkeypatch.setattr("database.db.get_connection", queried)

    async def exercise():
        request = make_mocked_request("GET", "/health", app=app)
        match_info = await app.router.resolve(request)
        request._match_info = match_info
        response = await match_info.handler(request)
        assert response.status == 200
        body = json.loads(response.body)
        assert body == {"schema_version": "1.0.0", "status": "ok"}
        text = response.body.decode()
        for forbidden in (
            "BOT_TOKEN",
            "DATABASE_PATH",
            "staging",
            "production",
            "GUIDESHOP",
            "fingerprint",
            "BEGIN ",
            "jti",
            public_pem.strip().splitlines()[1],
        ):
            assert forbidden not in text

    run(exercise())
    queried.assert_not_called()


def test_successful_startup_initializes_db_before_provider(monkeypatch, public_pem):
    order = []
    init = Mock(side_effect=lambda: order.append("init_db"))
    runner = Mock()
    runner.cleanup = AsyncMock()

    async def start(*args, **kwargs):
        order.append("start_provider")
        return runner

    stop = asyncio.Event()
    stop.set()
    monkeypatch.setattr(api_module, "init_db", init)
    monkeypatch.setattr(api_module, "start_guide_shop_link_provider", start)

    run(api_module.run_guide_shop_link_api(_local_env(public_pem), stop_event=stop))
    assert order == ["init_db", "start_provider"]
    runner.cleanup.assert_awaited_once_with()


def test_disabled_provider_exits_fail_closed_without_waiting(monkeypatch):
    init = Mock()
    start = AsyncMock(return_value=None)
    monkeypatch.setattr(api_module, "init_db", init)
    monkeypatch.setattr(api_module, "start_guide_shop_link_provider", start)
    with pytest.raises(SystemExit) as raised:
        run(api_module.run_guide_shop_link_api({}))
    assert raised.value.code == 1
    init.assert_not_called()
    start.assert_not_called()


def test_invalid_configuration_exits_fail_closed(monkeypatch):
    init = Mock()
    start = AsyncMock()
    monkeypatch.setattr(api_module, "init_db", init)
    monkeypatch.setattr(api_module, "start_guide_shop_link_provider", start)
    with pytest.raises(Exception):
        run(
            api_module.run_guide_shop_link_api(
                {
                    "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
                    "APP_ENV": "production",
                }
            )
        )
    init.assert_not_called()
    start.assert_not_called()


def test_database_initialization_failure_prevents_provider_startup(
    monkeypatch, public_pem
):
    init = Mock(side_effect=RuntimeError("db failed"))
    start = AsyncMock()
    monkeypatch.setattr(api_module, "init_db", init)
    monkeypatch.setattr(api_module, "start_guide_shop_link_provider", start)
    with pytest.raises(RuntimeError, match="db failed"):
        run(api_module.run_guide_shop_link_api(_local_env(public_pem)))
    start.assert_not_called()


def test_provider_startup_failure_propagates(monkeypatch, public_pem):
    init = Mock()
    start = AsyncMock(side_effect=RuntimeError("provider failed"))
    monkeypatch.setattr(api_module, "init_db", init)
    monkeypatch.setattr(api_module, "start_guide_shop_link_provider", start)
    with pytest.raises(RuntimeError, match="provider failed"):
        run(api_module.run_guide_shop_link_api(_local_env(public_pem)))
    init.assert_called_once_with()


def test_cancellation_cleans_runner_exactly_once(monkeypatch, public_pem):
    init = Mock()
    runner = Mock()
    runner.cleanup = AsyncMock()
    start = AsyncMock(return_value=runner)
    monkeypatch.setattr(api_module, "init_db", init)
    monkeypatch.setattr(api_module, "start_guide_shop_link_provider", start)

    async def exercise():
        task = asyncio.create_task(
            api_module.run_guide_shop_link_api(_local_env(public_pem))
        )
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(exercise())
    runner.cleanup.assert_awaited_once_with()


def test_stop_event_cleans_runner_exactly_once(monkeypatch, public_pem):
    init = Mock()
    runner = Mock()
    runner.cleanup = AsyncMock()
    start = AsyncMock(return_value=runner)
    monkeypatch.setattr(api_module, "init_db", init)
    monkeypatch.setattr(api_module, "start_guide_shop_link_provider", start)
    stop = asyncio.Event()

    async def exercise():
        task = asyncio.create_task(
            api_module.run_guide_shop_link_api(
                _local_env(public_pem), stop_event=stop
            )
        )
        await asyncio.sleep(0)
        stop.set()
        await task

    run(exercise())
    runner.cleanup.assert_awaited_once_with()


def test_entrypoint_removes_only_installed_signal_handlers(monkeypatch, public_pem):
    init = Mock()
    runner = Mock()
    runner.cleanup = AsyncMock()
    start = AsyncMock(return_value=runner)
    monkeypatch.setattr(api_module, "init_db", init)
    monkeypatch.setattr(api_module, "start_guide_shop_link_provider", start)
    stop = asyncio.Event()
    added = []
    removed = []

    async def exercise():
        loop = asyncio.get_running_loop()

        def add_signal_handler(sig, callback, *args):
            if sig == signal.SIGINT:
                raise RuntimeError("unsupported")
            added.append(sig)

        def remove_signal_handler(sig):
            removed.append(sig)

        monkeypatch.setattr(loop, "add_signal_handler", add_signal_handler)
        monkeypatch.setattr(loop, "remove_signal_handler", remove_signal_handler)
        task = asyncio.create_task(
            api_module.run_guide_shop_link_api(
                _local_env(public_pem), stop_event=stop
            )
        )
        await asyncio.sleep(0)
        stop.set()
        await task

    run(exercise())
    assert added == [signal.SIGTERM]
    assert removed == [signal.SIGTERM]
    runner.cleanup.assert_awaited_once_with()


def test_main_maps_failures_to_nonzero_exit(monkeypatch, public_pem):
    monkeypatch.setattr(
        api_module,
        "run_guide_shop_link_api",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    with pytest.raises(SystemExit) as raised:
        api_module.main(_local_env(public_pem))
    assert raised.value.code == 1


def test_staging_settings_path_accepted_at_composition(monkeypatch, public_pem):
    order = []
    init = Mock(side_effect=lambda: order.append("init_db"))
    runner = Mock()
    runner.cleanup = AsyncMock()

    async def start(values=None, *, clock=None):
        order.append("start_provider")
        assert values["APP_ENV"] == "staging"
        assert values["PORT"] == "8080"
        return runner

    stop = asyncio.Event()
    stop.set()
    monkeypatch.setattr(api_module, "init_db", init)
    monkeypatch.setattr(api_module, "start_guide_shop_link_provider", start)
    run(api_module.run_guide_shop_link_api(_staging_env(public_pem), stop_event=stop))
    assert order == ["init_db", "start_provider"]
    runner.cleanup.assert_awaited_once_with()
