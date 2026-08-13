"""API-only GuideShop link provider process.

Starts SQLite initialization and the Stage 5D HTTP provider only.
Does not import Telegram bot configuration or start polling.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from database.db import init_db
from services.guide_shop_link_provider import start_guide_shop_link_provider
from services.guide_shop_settings import GuideShopLinkProviderSettings

logger = logging.getLogger(__name__)


async def run_guide_shop_link_api(values=None, *, clock=None, stop_event=None):
    runtime = GuideShopLinkProviderSettings.from_env(values)
    if not runtime.enabled:
        raise SystemExit(1)

    init_db()
    runner = await start_guide_shop_link_provider(values, clock=clock)
    if runner is None:
        raise SystemExit(1)

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
        asyncio.run(run_guide_shop_link_api(values))
    except SystemExit:
        raise
    except BaseException:
        logger.exception("GuideShop link API failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
