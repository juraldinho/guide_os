from __future__ import annotations

import json

from aiohttp import web

from services.miniapp_analytics import (
    is_valid_client_miniapp_event,
    track_miniapp_event_safely,
)
from web_api.auth import idempotency_lookup, idempotency_store
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error

_ENDPOINT = "POST /app/v1/analytics/events"
_VALIDATION_MESSAGE = "Некорректное событие аналитики."


def register_analytics_routes(app: web.Application) -> None:
    async def create_analytics_event(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure

        idempotency_key = request.headers.get("Idempotency-Key")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            return error_response(
                "validation_error",
                _VALIDATION_MESSAGE,
                rid,
                400,
            )
        idempotency_key = idempotency_key.strip()

        body_bytes = await request.read()
        try:
            if request.content_type != "application/json":
                raise ValueError
            data = json.loads(body_bytes)
            if not isinstance(data, dict) or set(data) != {"name"}:
                raise ValueError
            event_name = data["name"]
            if not is_valid_client_miniapp_event(event_name):
                raise ValueError
        except (ValueError, TypeError, json.JSONDecodeError):
            return error_response(
                "validation_error",
                _VALIDATION_MESSAGE,
                rid,
                400,
            )

        stored = idempotency_lookup(
            user_id,
            _ENDPOINT,
            idempotency_key,
            body_bytes,
        )
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

        track_miniapp_event_safely(user_id, event_name)
        response = success_response({}, rid)
        idempotency_store(
            user_id,
            _ENDPOINT,
            idempotency_key,
            body_bytes,
            response.status,
            response.body.decode("utf-8"),
        )
        return response

    app.router.add_post("/app/v1/analytics/events", create_analytics_event)
