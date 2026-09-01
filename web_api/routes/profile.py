from __future__ import annotations

import json

from aiohttp import web

from database.queries import (
    apply_user_profile_patch,
    get_user_notification_settings,
    get_user_profile,
    register_user,
)
from web_api.auth import idempotency_lookup, idempotency_store
from web_api.dto import (
    decode_guide_languages_json,
    decode_guide_types_json,
    parse_profile_patch_body,
    profile_to_api,
)
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error


def _profile_response_data(user_id: int) -> dict:
    profile = get_user_profile(user_id)
    notifications = get_user_notification_settings(user_id)
    display_name = profile.get("display_name") if profile else None
    types = decode_guide_types_json(profile.get("guide_types_json") if profile else None)
    languages = decode_guide_languages_json(
        profile.get("guide_languages_json") if profile else None
    )
    return profile_to_api(user_id, display_name, notifications, types, languages)


def _profile_validation_message(exc: ValueError) -> str:
    code = str(exc)
    if code == "invalid telegramId":
        return "Некорректный telegramId."
    if code == "invalid name":
        return "Некорректное имя."
    if code == "invalid types":
        return "Некорректные типы гида."
    if code == "invalid languages":
        return "Некорректные языки."
    if code == "invalid notifications":
        return "Некорректные настройки напоминаний."
    return "Некорректный запрос."


def register_profile_routes(app: web.Application) -> None:
    async def get_profile_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        register_user(user_id)
        return success_response(_profile_response_data(user_id), rid)

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

        try:
            patch = parse_profile_patch_body(data)
        except ValueError as exc:
            return error_response(
                "validation_error",
                _profile_validation_message(exc),
                rid,
                400,
            )

        apply_user_profile_patch(
            user_id,
            display_name=patch.display_name,
            guide_types=patch.guide_types,
            guide_languages=patch.guide_languages,
            notifications_enabled=patch.notifications_enabled,
            notification_time=patch.notification_time,
        )

        response = success_response(_profile_response_data(user_id), rid)
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
