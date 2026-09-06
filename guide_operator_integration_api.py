"""API-only Guide Operator inbound event process (GO8D1).

Starts SQLite initialization and the Guide Operator integration HTTP surface only.
Does not import Telegram bot configuration or start polling / Mini App user routes.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from aiohttp import web

from database.db import init_db
from services.guide_operator_integration_settings import (
    GuideOperatorIntegrationConfigurationError,
    GuideOperatorIntegrationSettings,
)
from services.guide_operator_service_auth_settings import (
    GuideOperatorServiceAuthConfigurationError,
    load_guide_operator_service_auth_settings,
)
from web_api.guide_operator_integration import create_guide_operator_integration_app

logger = logging.getLogger(__name__)


async def run_guide_operator_integration_api(values=None, *, clock=None, stop_event=None):
    try:
        runtime = GuideOperatorIntegrationSettings.from_env(values)
    except GuideOperatorIntegrationConfigurationError:
        logger.error("Guide Operator integration configuration is invalid")
        raise SystemExit(1) from None
    if not runtime.enabled:
        raise SystemExit(1)

    try:
        auth_settings = load_guide_operator_service_auth_settings()
    except GuideOperatorServiceAuthConfigurationError:
        logger.error("Guide Operator service authentication configuration is invalid")
        raise SystemExit(1) from None
    if not auth_settings.enabled:
        logger.error("Guide Operator service authentication is disabled")
        raise SystemExit(1)

    init_db()
    app = create_guide_operator_integration_app(
        auth_settings=auth_settings,
        clock=clock,
    )
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=runtime.host, port=runtime.port)
    await site.start()
    logger.info(
        "Guide Operator integration API listening on %s:%s",
        runtime.host,
        runtime.port,
    )

    stop = stop_event if stop_event is not None else asyncio.Event()
    loop = asyncio.get_running_loop()
    installed_signals = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            continue
        installed_signals.append(sig)

    try:
        await stop.wait()
    finally:
        for sig in installed_signals:
            try:
                loop.remove_signal_handler(sig)
            except (NotImplementedError, RuntimeError):
                pass
        await runner.cleanup()


def main(values=None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        asyncio.run(run_guide_operator_integration_api(values))
    except SystemExit:
        raise
    except BaseException:
        logger.exception("Guide Operator integration API failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
