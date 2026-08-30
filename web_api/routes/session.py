from __future__ import annotations

from aiohttp import web

from database.queries import get_user_profile, register_user, update_user_display_name
from services.miniapp_api_settings import MiniAppApiSettings
from web_api.auth import (
    MiniAppAuthError,
    MiniAppForbiddenError,
    check_allowlist,
    create_miniapp_session,
    dev_session_token,
    read_json_body,
    resolve_user_id_from_request,
    revoke_miniapp_session,
    _extract_bearer_token,
    _utc_now_timestamp,
)
from web_api.errors import error_response, request_id, success_response
from web_api.telegram_auth import InitDataValidationError, validate_telegram_init_data

_MAX_SQLITE_INTEGER = 2**63 - 1


def register_session_routes(app: web.Application) -> None:
    async def create_session(request: web.Request) -> web.Response:
        rid = request_id(request)
        settings: MiniAppApiSettings = request.app["miniapp_settings"]
        try:
            data = await read_json_body(request, app["max_body_bytes"])
        except (ValueError, TypeError):
            return error_response("validation_error", "Некорректный запрос.", rid, 400)

        dev_user_id = data.get("dev_user_id")
        init_data = data.get("init_data")

        if dev_user_id is not None:
            if not settings.dev_auth:
                return error_response(
                    "auth_invalid",
                    "Dev-авторизация отключена.",
                    rid,
                    401,
                )
            try:
                user_id = int(dev_user_id)
            except (TypeError, ValueError):
                return error_response("validation_error", "Некорректный dev_user_id.", rid, 400)
            if not 0 < user_id <= _MAX_SQLITE_INTEGER:
                return error_response("validation_error", "Некорректный dev_user_id.", rid, 400)

            try:
                check_allowlist(settings, user_id)
            except MiniAppForbiddenError:
                return error_response("forbidden", "Доступ запрещён.", rid, 403)

            register_user(user_id)
            profile = get_user_profile(user_id)
            display_name = profile.get("display_name") if profile else ""
            token = dev_session_token(user_id)
            return success_response(
                {
                    "session_token": token,
                    "session_expires_at": None,
                    "user": {
                        "telegram_id": str(user_id),
                        "display_name": display_name or "",
                    },
                },
                rid,
            )

        if not isinstance(init_data, str) or not init_data.strip():
            return error_response(
                "validation_error",
                "Укажите init_data или dev_user_id.",
                rid,
                400,
            )

        if not settings.bot_token:
            return error_response(
                "auth_invalid",
                "Авторизация Mini App не настроена.",
                rid,
                401,
            )

        now = _utc_now_timestamp()
        try:
            user_id, init_display_name = validate_telegram_init_data(
                init_data,
                settings.bot_token,
                settings.initdata_max_age_seconds,
                now,
            )
        except InitDataValidationError:
            return error_response(
                "auth_invalid",
                "Недействительные данные авторизации Telegram.",
                rid,
                401,
            )

        try:
            check_allowlist(settings, user_id)
        except MiniAppForbiddenError:
            return error_response("forbidden", "Доступ запрещён.", rid, 403)

        register_user(user_id)
        if init_display_name:
            update_user_display_name(user_id, init_display_name)

        session_token, session_expires_at = create_miniapp_session(
            user_id,
            settings.session_ttl_seconds,
            now_timestamp=now,
        )
        profile = get_user_profile(user_id)
        display_name = profile.get("display_name") if profile else init_display_name
        return success_response(
            {
                "session_token": session_token,
                "session_expires_at": session_expires_at,
                "user": {
                    "telegram_id": str(user_id),
                    "display_name": display_name or "",
                },
            },
            rid,
        )

    async def delete_session(request: web.Request) -> web.Response:
        rid = request_id(request)
        bearer = _extract_bearer_token(request)
        if bearer is None:
            return error_response("auth_required", "Требуется авторизация.", rid, 401)

        if bearer.startswith("dev:"):
            return success_response({}, rid)

        if not revoke_miniapp_session(bearer):
            return error_response("auth_required", "Требуется авторизация.", rid, 401)
        return success_response({}, rid)

    app.router.add_post("/app/v1/session", create_session)
    app.router.add_delete("/app/v1/session", delete_session)


def _auth_or_error(request: web.Request) -> tuple[str, int | None, web.Response | None]:
    rid = request_id(request)
    settings: MiniAppApiSettings = request.app["miniapp_settings"]
    try:
        user_id = resolve_user_id_from_request(request, settings)
    except MiniAppForbiddenError:
        return rid, None, error_response("forbidden", "Доступ запрещён.", rid, 403)
    except MiniAppAuthError:
        return rid, None, error_response(
            "auth_required",
            "Требуется авторизация.",
            rid,
            401,
        )
    return rid, user_id, None
