"""GO9A test-only Guide OS HTTP servers.

Starts the GO8D1/D2 integration API and Mini App API on loopback ports against
an isolated SQLite file. Not a production entrypoint. Flags stay off unless the
parent harness injects test-only environment for this subprocess.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

READY_PREFIX = "GO9A_READY"
DEFAULT_TELEGRAM_USER_ID = 706901


async def _serve() -> None:
    from aiohttp import web

    from database.db import init_db
    from database.queries import get_guide_os_id, register_user
    from services.guide_operator_service_auth_settings import (
        load_guide_operator_service_auth_settings,
    )
    from services.miniapp_api_settings import MiniAppApiSettings
    from web_api.app import create_miniapp_api_app
    from web_api.guide_operator_integration import create_guide_operator_integration_app

    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("go9a")

    @web.middleware
    async def log_exceptions(request: web.Request, handler):
        try:
            return await handler(request)
        except Exception:
            logger.exception("uncaught %s %s", request.method, request.path)
            raise

    telegram_user_id = int(os.environ.get("GO9A_TELEGRAM_USER_ID", str(DEFAULT_TELEGRAM_USER_ID)))
    integration_port = int(os.environ["GO9A_INTEGRATION_PORT"])
    miniapp_port = int(os.environ["GO9A_MINIAPP_PORT"])

    init_db()
    register_user(telegram_user_id)
    guide_os_id = get_guide_os_id(telegram_user_id)
    if not guide_os_id:
        raise SystemExit("GO9A Guide OS identity is missing")

    auth_settings = load_guide_operator_service_auth_settings()
    if not auth_settings.enabled:
        raise SystemExit("GO9A Guide OS service authentication is disabled")

    integration_app = create_guide_operator_integration_app(auth_settings=auth_settings)
    integration_app.middlewares.append(log_exceptions)
    miniapp_app = create_miniapp_api_app(
        MiniAppApiSettings(
            enabled=True,
            host="127.0.0.1",
            port=miniapp_port,
            dev_auth=True,
            bot_token="7000000000:GO9A_local_only_bot_token",
            session_ttl_seconds=3600,
            initdata_max_age_seconds=86400,
            allowlist=frozenset(),
        )
    )

    integration_runner = web.AppRunner(integration_app)
    miniapp_runner = web.AppRunner(miniapp_app)
    await integration_runner.setup()
    await miniapp_runner.setup()
    await web.TCPSite(integration_runner, "127.0.0.1", integration_port).start()
    await web.TCPSite(miniapp_runner, "127.0.0.1", miniapp_port).start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            continue

    print(f"{READY_PREFIX} guide_os_id={guide_os_id}", flush=True)
    try:
        await stop.wait()
    finally:
        await integration_runner.cleanup()
        await miniapp_runner.cleanup()


def main() -> int:
    asyncio.run(_serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
