"""GO13C2 single-replica consolidated staging runtime.

This launcher is staging-only. Production continues to use ``python bot.py``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("guide_os.staging_runtime")

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off", ""})


class ConsolidatedStagingRuntimeConfigurationError(ValueError):
    pass


def _flag(values: Mapping[str, str], name: str) -> bool:
    value = values.get(name, "false")
    if not isinstance(value, str):
        raise ConsolidatedStagingRuntimeConfigurationError("invalid runtime configuration")
    normalized = value.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise ConsolidatedStagingRuntimeConfigurationError("invalid runtime configuration")


def _port(values: Mapping[str, str], name: str, default: int) -> int:
    try:
        value = int(values.get(name, str(default)))
    except (TypeError, ValueError):
        raise ConsolidatedStagingRuntimeConfigurationError(
            "invalid runtime configuration"
        ) from None
    if not 1 <= value <= 65535:
        raise ConsolidatedStagingRuntimeConfigurationError("invalid runtime configuration")
    return value


@dataclass(frozen=True)
class ConsolidatedStagingRuntimeSettings:
    database_path: str
    miniapp_port: int
    integration_port: int
    shutdown_timeout_seconds: float

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "ConsolidatedStagingRuntimeSettings":
        source = os.environ if values is None else values
        if source.get("APP_ENV") != "staging" or not _flag(
            source, "GUIDE_OS_CONSOLIDATED_STAGING_RUNTIME_ENABLED"
        ):
            raise ConsolidatedStagingRuntimeConfigurationError(
                "consolidated runtime is staging-only"
            )
        if source.get("GUIDE_OS_CONSOLIDATED_STAGING_REPLICA_COUNT") != "1":
            raise ConsolidatedStagingRuntimeConfigurationError(
                "consolidated runtime requires one replica"
            )
        database_path = source.get("DATABASE_PATH", "")
        path = Path(database_path)
        if not path.is_absolute() or path.parent != Path("/data"):
            raise ConsolidatedStagingRuntimeConfigurationError(
                "consolidated runtime requires the shared volume"
            )
        required_flags = (
            "MINI_APP_API_ENABLED",
            "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED",
            "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_ENABLED",
            "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ENABLED",
        )
        if not all(_flag(source, name) for name in required_flags):
            raise ConsolidatedStagingRuntimeConfigurationError(
                "required component is disabled"
            )
        if _flag(source, "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ONCE"):
            raise ConsolidatedStagingRuntimeConfigurationError(
                "outbound worker must remain active"
            )
        if _flag(source, "GUIDESHOP_LINK_PROVIDER_ENABLED"):
            raise ConsolidatedStagingRuntimeConfigurationError(
                "GuideShop link provider must use its isolated runtime"
            )
        if source.get("MINI_APP_API_HOST") != "0.0.0.0" or source.get(
            "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_HOST"
        ) != "0.0.0.0":
            raise ConsolidatedStagingRuntimeConfigurationError(
                "HTTP components require explicit staging hosts"
            )
        miniapp_port = _port(source, "MINI_APP_API_PORT", 8083)
        integration_port = _port(
            source, "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_PORT", 8084
        )
        if miniapp_port == integration_port:
            raise ConsolidatedStagingRuntimeConfigurationError(
                "HTTP component ports must differ"
            )
        try:
            timeout = float(
                source.get(
                    "GUIDE_OS_CONSOLIDATED_STAGING_SHUTDOWN_TIMEOUT_SECONDS", "30"
                )
            )
        except (TypeError, ValueError):
            raise ConsolidatedStagingRuntimeConfigurationError(
                "invalid runtime configuration"
            ) from None
        if not 1 <= timeout <= 120:
            raise ConsolidatedStagingRuntimeConfigurationError(
                "invalid runtime configuration"
            )
        return cls(database_path, miniapp_port, integration_port, timeout)


@dataclass(frozen=True)
class RuntimeDependencies:
    run_bot: Callable[[], Awaitable[None]]
    run_integration: Callable[[asyncio.Event], Awaitable[None]]
    run_outbound: Callable[[], None]
    stop_outbound: Callable[[], None]


def _default_dependencies(values: Mapping[str, str] | None) -> RuntimeDependencies:
    import bot
    from guide_operator_integration_api import run_guide_operator_integration_api
    from services.guide_operator_outbound_settings import GuideOperatorOutboundSettings
    from services.guide_operator_outbound_worker import (
        GuideOperatorOutboundDeliveryWorker,
        GuideOperatorOutboundWorkerSettings,
    )

    worker_settings = GuideOperatorOutboundWorkerSettings.from_env(values)
    outbound_settings = GuideOperatorOutboundSettings.from_env(values)
    worker = GuideOperatorOutboundDeliveryWorker(
        settings=worker_settings,
        outbound_settings=outbound_settings,
    )

    async def run_bot() -> None:
        await bot.main(polling_handle_signals=False)

    async def run_integration(stop_event: asyncio.Event) -> None:
        await run_guide_operator_integration_api(
            values,
            stop_event=stop_event,
            install_signal_handlers=False,
        )

    return RuntimeDependencies(
        run_bot=run_bot,
        run_integration=run_integration,
        run_outbound=worker.run_forever,
        stop_outbound=worker.request_stop,
    )


def _validate_database_binding(expected: str) -> None:
    from database import db

    if db.DB_PATH != expected:
        raise ConsolidatedStagingRuntimeConfigurationError(
            "components do not share one database"
        )


async def run_consolidated_staging_runtime(
    values: Mapping[str, str] | None = None,
    *,
    dependencies: RuntimeDependencies | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    settings = ConsolidatedStagingRuntimeSettings.from_env(values)
    _validate_database_binding(settings.database_path)
    deps = dependencies or _default_dependencies(values)
    stop = stop_event or asyncio.Event()
    integration_stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []
    if stop_event is None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, RuntimeError):
                continue
            installed_signals.append(sig)

    tasks = {
        asyncio.create_task(deps.run_bot(), name="telegram_and_miniapp"): "bot",
        asyncio.create_task(
            deps.run_integration(integration_stop), name="guide_operator_integration"
        ): "integration",
        asyncio.create_task(
            asyncio.to_thread(deps.run_outbound), name="guide_operator_outbound"
        ): "outbound",
    }
    stop_task = asyncio.create_task(stop.wait(), name="runtime_stop")
    logger.info("Consolidated staging runtime started")
    failed_component: str | None = None
    try:
        done, _pending = await asyncio.wait(
            [*tasks, stop_task], return_when=asyncio.FIRST_COMPLETED
        )
        if stop_task not in done:
            failed_component = tasks[next(task for task in tasks if task in done)]
            logger.error("Required runtime component stopped")
    finally:
        integration_stop.set()
        deps.stop_outbound()
        for task, component in tasks.items():
            if component == "bot" and not task.done():
                task.cancel()
        stop_task.cancel()
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=settings.shutdown_timeout_seconds,
            )
        except TimeoutError:
            logger.error("Consolidated staging runtime shutdown timed out")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise RuntimeError("consolidated staging runtime shutdown failed") from None
        finally:
            await asyncio.gather(stop_task, return_exceptions=True)
            for sig in installed_signals:
                try:
                    loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError):
                    pass
        logger.info("Consolidated staging runtime stopped")
    if failed_component is not None:
        raise RuntimeError("required runtime component stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        asyncio.run(run_consolidated_staging_runtime())
    except ConsolidatedStagingRuntimeConfigurationError:
        logger.error("Consolidated staging runtime configuration is invalid")
        raise SystemExit(1) from None
    except BaseException:
        logger.error("Consolidated staging runtime failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
