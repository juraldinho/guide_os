"""API-only Guide OS Mini App HTTP server.

Starts SQLite initialization and the Mini App Web API only.
Does not import Telegram bot configuration or start polling.
MA5: dev auth stub only — see web_api/auth.py (MA6 replaces initData).
"""

from __future__ import annotations

import asyncio
import logging
import signal

from database.db import init_db
from web_api.app import start_miniapp_api

logger = logging.getLogger(__name__)


async def run_guide_os_miniapp_api(values=None, *, clock=None, stop_event=None):
    init_db()
    runner = await start_miniapp_api(values, clock=clock)
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
        asyncio.run(run_guide_os_miniapp_api(values))
    except SystemExit:
        raise
    except BaseException:
        logger.exception("Guide OS Mini App API failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
