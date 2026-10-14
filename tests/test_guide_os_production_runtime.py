from __future__ import annotations

import asyncio
import inspect
import json
import sqlite3
import threading
from collections import Counter

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import bot
import database.db as db_module
import guide_os_production_runtime as production_runtime
from guide_os_production_runtime import (
    ConsolidatedProductionRuntimeConfigurationError,
    ConsolidatedProductionRuntimeSettings,
    run_consolidated_production_runtime,
)
from guide_os_staging_runtime import RuntimeDependencies


def run(awaitable):
    return asyncio.run(awaitable)


def _key_material():
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        private.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return private_pem, public_pem


def _env(**overrides):
    values = {
        "APP_ENV": "production",
        "GUIDE_OS_CONSOLIDATED_PRODUCTION_RUNTIME_ENABLED": "true",
        "GUIDE_OS_CONSOLIDATED_PRODUCTION_REPLICA_COUNT": "1",
        "GUIDE_OS_CONSOLIDATED_PRODUCTION_SHUTDOWN_TIMEOUT_SECONDS": "2",
        "DATABASE_PATH": "/data/guide_os.db",
        "MINI_APP_API_ENABLED": "true",
        "MINI_APP_API_PORT": "8083",
        "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED": "false",
        "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_HOST": "0.0.0.0",
        "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_PORT": "8084",
        "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_ENABLED": "false",
        "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ENABLED": "false",
        "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ONCE": "false",
        "GUIDE_OS_SERVICE_AUTH_ENABLED": "false",
    }
    values.update(overrides)
    return values


def _integration_env(*, outbound=False, **overrides):
    private_pem, public_pem = _key_material()
    values = _env(
        GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED="true",
        GUIDE_OS_SERVICE_AUTH_ENABLED="true",
        GUIDE_OS_GUIDE_OPERATOR_JWT_PUBLIC_KEYS=json.dumps(
            {"go-production-20261014": public_pem}
        ),
        GUIDE_OS_SIGNING_KID="guide-os-production-20261014",
        GUIDE_OS_SIGNING_PRIVATE_KEY_PEM=private_pem,
    )
    if outbound:
        values.update(
            {
                "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_ENABLED": "true",
                "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ENABLED": "true",
                "GUIDE_OS_GUIDE_OPERATOR_BASE_URL": "https://operator.example",
            }
        )
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    "overrides",
    [
        {"APP_ENV": "staging"},
        {"APP_ENV": "development"},
        {"APP_ENV": "test"},
        {"GUIDE_OS_CONSOLIDATED_PRODUCTION_RUNTIME_ENABLED": "false"},
        {"GUIDE_OS_CONSOLIDATED_PRODUCTION_REPLICA_COUNT": "0"},
        {"GUIDE_OS_CONSOLIDATED_PRODUCTION_REPLICA_COUNT": "2"},
        {"DATABASE_PATH": "guide_os.db"},
        {"DATABASE_PATH": "/tmp/guide_os.db"},
        {"MINI_APP_API_ENABLED": "false"},
        {"GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_ENABLED": "true"},
        {"GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ENABLED": "true"},
        {"GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ONCE": "true"},
    ],
)
def test_production_guards_reject_invalid_base_configuration(overrides):
    with pytest.raises(ConsolidatedProductionRuntimeConfigurationError):
        ConsolidatedProductionRuntimeSettings.from_env(_env(**overrides))


def test_production_guards_reject_conflicting_enabled_ports():
    with pytest.raises(ConsolidatedProductionRuntimeConfigurationError):
        ConsolidatedProductionRuntimeSettings.from_env(
            _integration_env(GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_PORT="8083")
        )


def test_production_guards_reject_incomplete_enabled_auth():
    with pytest.raises(ConsolidatedProductionRuntimeConfigurationError):
        ConsolidatedProductionRuntimeSettings.from_env(
            _env(GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED="true")
        )


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (_env(), Counter(poller=1, bot_cancelled=1)),
        (
            _integration_env(),
            Counter(poller=1, integration=1, integration_stopped=1, bot_cancelled=1),
        ),
        (
            _integration_env(outbound=True),
            Counter(
                poller=1,
                integration=1,
                integration_stopped=1,
                outbound=1,
                outbound_stop=1,
                bot_cancelled=1,
            ),
        ),
    ],
)
def test_production_phased_runtime_composition(monkeypatch, values, expected):
    monkeypatch.setattr(db_module, "DB_PATH", "/data/guide_os.db")
    calls = Counter()
    outbound_stop = threading.Event()

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
        calls["integration_stopped"] += 1

    def outbound_runner():
        calls["outbound"] += 1
        outbound_stop.wait()

    def stop_outbound():
        calls["outbound_stop"] += 1
        outbound_stop.set()

    settings = ConsolidatedProductionRuntimeSettings.from_env(values)
    dependencies = RuntimeDependencies(
        bot_runner,
        integration_runner if settings.integration_enabled else None,
        outbound_runner if settings.outbound_enabled else None,
        stop_outbound if settings.outbound_enabled else None,
    )

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(
            run_consolidated_production_runtime(
                values, dependencies=dependencies, stop_event=stop
            )
        )
        await asyncio.sleep(0.05)
        stop.set()
        await task

    run(scenario())
    assert calls == expected


def test_invalid_configuration_fails_before_poller(monkeypatch):
    calls = Counter()

    async def bot_runner():
        calls["poller"] += 1

    with pytest.raises(ConsolidatedProductionRuntimeConfigurationError):
        run(
            run_consolidated_production_runtime(
                _env(GUIDE_OS_CONSOLIDATED_PRODUCTION_REPLICA_COUNT="2"),
                dependencies=RuntimeDependencies(bot_runner),
                stop_event=asyncio.Event(),
            )
        )
    assert calls == Counter()


def test_unexpected_integration_exit_stops_the_single_poller(monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", "/data/guide_os.db")
    calls = Counter()

    async def bot_runner():
        calls["poller"] += 1
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            calls["bot_cancelled"] += 1
            raise

    async def integration_runner(_stop):
        calls["integration"] += 1

    with pytest.raises(RuntimeError, match="required runtime component stopped"):
        run(
            run_consolidated_production_runtime(
                _integration_env(),
                dependencies=RuntimeDependencies(bot_runner, integration_runner),
                stop_event=asyncio.Event(),
            )
        )
    assert calls == Counter(poller=1, integration=1, bot_cancelled=1)


def test_production_entrypoint_does_not_duplicate_notification_or_polling():
    production_source = inspect.getsource(production_runtime)
    bot_source = inspect.getsource(bot)
    assert "start_guide_operator_notification_worker" not in production_source
    assert "start_polling" not in production_source
    assert bot_source.count("dp.start_polling") == 1
    assert bot_source.count("start_guide_operator_notification_worker()") == 1


def test_sqlite_restart_preserves_data_and_integrity(tmp_path, monkeypatch):
    database_path = tmp_path / "guide_os.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(database_path))
    db_module.init_db()
    with sqlite3.connect(database_path) as connection:
        connection.execute("INSERT INTO users(user_id) VALUES (?)", (1,))
        connection.commit()
    db_module.init_db()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM users WHERE user_id = 1"
            ).fetchone()[0]
            == 1
        )
