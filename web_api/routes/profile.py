from __future__ import annotations

import json
import re

from aiohttp import web

from database.queries import (
    get_user_notification_settings,
    get_user_profile,
    register_user,
    set_notification_time,
    set_notifications_enabled,
    update_user_display_name,
)
from web_api.auth import idempotency_lookup, idempotency_store
from web_api.dto import profile_to_api
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def register_profile_routes(app: web.Application) -> None:
    async def get_profile_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        register_user(user_id)
        profile = get_user_profile(user_id)
        notifications = get_user_notification_settings(user_id)
        display_name = profile.get("display_name") if profile else None
        return success_response(
            profile_to_api(user_id, display_name, notifications),
            rid,
        )

    async def patch_profile_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        body_bytes = await request.read()

        key = request.headers.get("Idempotency-Key")
        if key:
            stored = idempotency_lookup(user_id, "PATCH /app/v1/profile", key.strip(), body_bytes)
            if stored and stored.get("replay_conflict"):
                return error_response(
                    "idempotency_replay",
                    "Idempotency-Key уже использован с другим телом запроса.",
                    rid,
                    409,
                )
            if stored:
                return web.Response(
                    body=stored["response_body"],
                    status=stored["status_code"],
                    content_type="application/json",
                )

        try:
            data = json.loads(body_bytes.decode("utf-8") if body_bytes else "{}")
            if not isinstance(data, dict):
                raise ValueError
        except (ValueError, TypeError, json.JSONDecodeError):
            return error_response("validation_error", "Некорректный запрос.", rid, 400)

        register_user(user_id)
        name = data.get("name")
        if name is not None:
            if not isinstance(name, str):
                return error_response("validation_error", "Некорректное имя.", rid, 400)
            update_user_display_name(user_id, name.strip())

        notifications = data.get("notifications")
        if isinstance(notifications, dict):
            enabled = notifications.get("enabled")
            if enabled is not None:
                set_notifications_enabled(user_id, bool(enabled))
            time_value = notifications.get("time")
            if isinstance(time_value, str) and _TIME_RE.fullmatch(time_value):
                set_notification_time(user_id, time_value)
            elif time_value is not None:
                return error_response(
                    "validation_error",
                    "Некорректное время напоминания.",
                    rid,
                    400,
                )

        profile = get_user_profile(user_id)
        notif = get_user_notification_settings(user_id)
        response = success_response(
            profile_to_api(user_id, profile.get("display_name") if profile else None, notif),
            rid,
        )
        if key and response.body:
            idempotency_store(
                user_id,
                "PATCH /app/v1/profile",
                key.strip(),
                body_bytes,
                response.status,
                response.body.decode("utf-8"),
            )
        return response

    app.router.add_get("/app/v1/profile", get_profile_handler)
    app.router.add_patch("/app/v1/profile", patch_profile_handler)
