from __future__ import annotations

import logging

from aiohttp import web

from services.miniapp_api_settings import MiniAppApiSettings
from web_api.routes.availability import register_availability_routes
from web_api.routes.entries import register_entries_routes
from web_api.routes.profile import register_profile_routes
from web_api.routes.reports import register_reports_routes
from web_api.routes.session import register_session_routes

logger = logging.getLogger(__name__)

MAX_REQUEST_BODY_BYTES = 65536


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_miniapp_api_app(settings: MiniAppApiSettings) -> web.Application:
    app = web.Application(client_max_size=MAX_REQUEST_BODY_BYTES)
    app.router.add_get("/health", health)
    register_miniapp_api_on_app(app, settings)
    return app


def register_miniapp_api_on_app(app: web.Application, settings: MiniAppApiSettings) -> None:
    app["miniapp_settings"] = settings
    app["max_body_bytes"] = MAX_REQUEST_BODY_BYTES

    register_session_routes(app)
    register_entries_routes(app)
    register_profile_routes(app)
    register_reports_routes(app)
    register_availability_routes(app)


async def start_miniapp_api(values=None, *, clock=None):
    settings = MiniAppApiSettings.from_env(values)
    if not settings.enabled:
        return None

    runner = web.AppRunner(create_miniapp_api_app(settings))
    try:
        await runner.setup()
        site = web.TCPSite(runner, settings.host, settings.port)
        await site.start()
        logger.info(
            "Mini App API listening on %s:%s (dev_auth=%s)",
            settings.host,
            settings.port,
            settings.dev_auth,
        )
        return runner
    except BaseException:
        await runner.cleanup()
        raise
