from __future__ import annotations

import re

from aiohttp import web

from database.queries import register_user
from web_api.auth import dev_session_token, read_json_body, resolve_user_id_from_request
from web_api.auth import MiniAppAuthError
from web_api.errors import error_response, request_id, success_response

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_SQLITE_INTEGER = 2**63 - 1


def register_session_routes(app: web.Application) -> None:
    async def create_session(request: web.Request) -> web.Response:
        rid = request_id(request)
        settings = request.app["miniapp_settings"]
        if not settings.dev_auth:
            return error_response(
                "auth_invalid",
                "Авторизация Mini App ещё не настроена (MA6).",
                rid,
                401,
            )
        try:
            data = await read_json_body(request, app["max_body_bytes"])
        except (ValueError, TypeError):
            return error_response("validation_error", "Некорректный запрос.", rid, 400)

        dev_user_id = data.get("dev_user_id")
        if dev_user_id is None and isinstance(data.get("init_data"), str):
            return error_response(
                "auth_invalid",
                "initData не поддерживается в MA5. Используйте dev_user_id (MA6).",
                rid,
                401,
            )
        try:
            user_id = int(dev_user_id)
        except (TypeError, ValueError):
            return error_response("validation_error", "Некорректный dev_user_id.", rid, 400)
        if not 0 < user_id <= _MAX_SQLITE_INTEGER:
            return error_response("validation_error", "Некорректный dev_user_id.", rid, 400)

        register_user(user_id)
        token = dev_session_token(user_id)
        return success_response(
            {
                "session_expires_at": None,
                "user": {
                    "telegram_id": str(user_id),
                    "display_name": "",
                },
                "token": token,
            },
            rid,
        )

    async def delete_session(request: web.Request) -> web.Response:
        rid = request_id(request)
        return success_response({}, rid)

    app.router.add_post("/app/v1/session", create_session)
    app.router.add_delete("/app/v1/session", delete_session)


def _auth_or_error(request: web.Request) -> tuple[str, int | None, web.Response | None]:
    rid = request_id(request)
    settings = request.app["miniapp_settings"]
    try:
        user_id = resolve_user_id_from_request(request, settings.dev_auth)
    except MiniAppAuthError:
        return rid, None, error_response(
            "auth_required",
            "Требуется авторизация.",
            rid,
            401,
        )
    return rid, user_id, None
