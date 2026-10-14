"""GO13J1 production-safe single-process Guide OS runtime."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from guide_os_staging_runtime import (
    RuntimeDependencies,
    _flag,
    _port,
    build_runtime_dependencies,
    run_consolidated_runtime,
)
from services.guide_operator_integration_settings import (
    GuideOperatorIntegrationSettings,
)
from services.guide_operator_outbound_settings import GuideOperatorOutboundSettings
from services.guide_operator_outbound_worker import GuideOperatorOutboundWorkerSettings
from services.guide_operator_service_auth_settings import (
    GuideOperatorServiceAuthSettings,
)

logger = logging.getLogger("guide_os.production_runtime")


class ConsolidatedProductionRuntimeConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ConsolidatedProductionRuntimeSettings:
    database_path: str
    shutdown_timeout_seconds: float
    integration_enabled: bool
    outbound_enabled: bool

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> ConsolidatedProductionRuntimeSettings:
        source = os.environ if values is None else values
        try:
            if source.get("APP_ENV") != "production" or not _flag(
                source, "GUIDE_OS_CONSOLIDATED_PRODUCTION_RUNTIME_ENABLED"
            ):
                raise ConsolidatedProductionRuntimeConfigurationError(
                    "consolidated runtime is not enabled for production"
                )
            if source.get("GUIDE_OS_CONSOLIDATED_PRODUCTION_REPLICA_COUNT") != "1":
                raise ConsolidatedProductionRuntimeConfigurationError(
                    "consolidated production runtime requires one replica"
                )
            database_path = source.get("DATABASE_PATH", "")
            path = Path(database_path)
            if not path.is_absolute() or path.parent != Path("/data"):
                raise ConsolidatedProductionRuntimeConfigurationError(
                    "consolidated production runtime requires the shared volume"
                )
            if not _flag(source, "MINI_APP_API_ENABLED"):
                raise ConsolidatedProductionRuntimeConfigurationError(
                    "production Mini App API must remain enabled"
                )
            integration_enabled = _flag(
                source, "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED"
            )
            outbound_enabled = _flag(
                source, "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ENABLED"
            )
            outbound_delivery_enabled = _flag(
                source, "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_ENABLED"
            )
            if outbound_enabled and not integration_enabled:
                raise ConsolidatedProductionRuntimeConfigurationError(
                    "outbound requires the integration API"
                )
            if outbound_enabled != outbound_delivery_enabled:
                raise ConsolidatedProductionRuntimeConfigurationError(
                    "outbound flags must be enabled together"
                )
            if _flag(source, "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ONCE"):
                raise ConsolidatedProductionRuntimeConfigurationError(
                    "outbound worker once mode is not allowed"
                )
            miniapp_port = _port(source, "MINI_APP_API_PORT", 8083)
            integration_port = _port(
                source, "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_PORT", 8084
            )
            if integration_enabled and miniapp_port == integration_port:
                raise ConsolidatedProductionRuntimeConfigurationError(
                    "enabled HTTP components require separate ports"
                )
            timeout = float(
                source.get(
                    "GUIDE_OS_CONSOLIDATED_PRODUCTION_SHUTDOWN_TIMEOUT_SECONDS", "30"
                )
            )
            if not 1 <= timeout <= 120:
                raise ValueError
            auth: GuideOperatorServiceAuthSettings | None = None
            if integration_enabled:
                integration = GuideOperatorIntegrationSettings.from_env(source)
                auth = GuideOperatorServiceAuthSettings.from_env(source)
                if not integration.enabled or not auth.enabled:
                    raise ConsolidatedProductionRuntimeConfigurationError(
                        "enabled integration requires service authentication"
                    )
            if outbound_enabled:
                outbound = GuideOperatorOutboundSettings.from_env(
                    source, auth_settings=auth
                )
                worker = GuideOperatorOutboundWorkerSettings.from_env(
                    source, outbound=outbound
                )
                if not outbound.enabled or not worker.enabled:
                    raise ConsolidatedProductionRuntimeConfigurationError(
                        "enabled outbound worker configuration is incomplete"
                    )
        except ConsolidatedProductionRuntimeConfigurationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ConsolidatedProductionRuntimeConfigurationError(
                "invalid consolidated production runtime configuration"
            ) from exc
        return cls(database_path, timeout, integration_enabled, outbound_enabled)


async def run_consolidated_production_runtime(
    values: Mapping[str, str] | None = None,
    *,
    dependencies: RuntimeDependencies | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    settings = ConsolidatedProductionRuntimeSettings.from_env(values)
    deps = dependencies or build_runtime_dependencies(
        values,
        integration_enabled=settings.integration_enabled,
        outbound_enabled=settings.outbound_enabled,
    )
    await run_consolidated_runtime(
        database_path=settings.database_path,
        shutdown_timeout_seconds=settings.shutdown_timeout_seconds,
        dependencies=deps,
        stop_event=stop_event,
        runtime_name="production",
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        asyncio.run(run_consolidated_production_runtime())
    except ConsolidatedProductionRuntimeConfigurationError:
        logger.error("Consolidated production runtime configuration is invalid")
        raise SystemExit(1) from None
    except RuntimeError:
        logger.error("Consolidated production runtime failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
