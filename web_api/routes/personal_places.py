from __future__ import annotations

import json

from aiohttp import web

from services.personal_places_service import (
    PersonalPlaceConflictError,
    PersonalPlacesService,
    PersonalPlaceValidationError,
)
from web_api.auth import idempotency_lookup, idempotency_store
from web_api.dto import (
    parse_personal_place_body,
    parse_personal_place_id,
    personal_place_to_api,
)
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error

_places_service = PersonalPlacesService()


def _place_not_found_response(rid: str) -> web.Response:
    return error_response("not_found", "Личное место не найдено.", rid, 404)


def _resolve_place_id(request: web.Request, rid: str) -> tuple[str | None, web.Response | None]:
    parsed = parse_personal_place_id(request.match_info["placeId"])
    if parsed is None:
        return None, _place_not_found_response(rid)
    return parsed, None


def _parse_include_inactive(request: web.Request) -> tuple[bool | None, bool]:
    values = request.rel_url.query.getall("includeInactive", [])
    if not values:
        return False, False
    if len(values) > 1:
        return None, True
    value = values[0]
    if value == "true":
        return True, False
    if value == "false":
        return False, False
    return None, True


def _personal_place_validation_message(exc: PersonalPlaceValidationError) -> str:
    message = str(exc)
    if message == "Invalid personal place identifier":
        return "Некорректный идентификатор личного места."
    if message == "Invalid personal place owner":
        return "Некорректный владелец личного места."
    return "Некорректные данные личного места."


async def _idempotent(
    request: web.Request,
    user_id: int,
    endpoint: str,
    body_bytes: bytes,
    build_response,
) -> web.Response:
    key = request.headers.get("Idempotency-Key")
    if key:
        stored = idempotency_lookup(user_id, endpoint, key.strip(), body_bytes)
        if stored and stored.get("replay_conflict"):
            rid = request["request_id"]
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

    response = await build_response()
    if key and response.body:
        idempotency_store(
            user_id,
            endpoint,
            key.strip(),
            body_bytes,
            response.status,
            response.body.decode("utf-8"),
        )
    return response


def register_personal_places_routes(app: web.Application) -> None:
    async def list_personal_places_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        include_inactive, invalid = _parse_include_inactive(request)
        if invalid:
            return error_response(
                "validation_error",
                "Некорректный параметр includeInactive.",
                rid,
                400,
            )
        try:
            places = _places_service.list(
                user_id=user_id,
                include_inactive=include_inactive,
            )
        except PersonalPlaceValidationError as exc:
            return error_response(
                "validation_error",
                _personal_place_validation_message(exc),
                rid,
                400,
            )
        return success_response(
            {"places": [personal_place_to_api(place) for place in places]},
            rid,
        )

    async def create_personal_place_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        body_bytes = await request.read()

        async def build():
            try:
                data = json.loads(body_bytes or b"{}")
                if not isinstance(data, dict):
                    raise ValueError
                body = parse_personal_place_body(data)
            except (ValueError, TypeError, json.JSONDecodeError):
                return error_response(
                    "validation_error",
                    "Некорректные данные личного места.",
                    rid,
                    400,
                )
            try:
                created = _places_service.create(
                    user_id=user_id,
                    name=body.name,
                    category=body.category,
                    general_location=body.general_location,
                    landmark=body.landmark,
                    note=body.note,
                )
            except PersonalPlaceValidationError as exc:
                return error_response(
                    "validation_error",
                    _personal_place_validation_message(exc),
                    rid,
                    400,
                )
            except PersonalPlaceConflictError:
                return error_response(
                    "conflict",
                    "Личное место не может быть создано.",
                    rid,
                    409,
                )
            return success_response(personal_place_to_api(created), rid, status=201)

        return await _idempotent(
            request,
            user_id,
            "POST /app/v1/personal-places",
            body_bytes,
            build,
        )

    async def get_personal_place_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        place_id, place_failure = _resolve_place_id(request, rid)
        if place_failure is not None:
            return place_failure
        place = _places_service.get(user_id=user_id, public_id=place_id)
        if place is None:
            return _place_not_found_response(rid)
        return success_response(personal_place_to_api(place), rid)

    async def update_personal_place_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        place_id, place_failure = _resolve_place_id(request, rid)
        if place_failure is not None:
            return place_failure
        body_bytes = await request.read()
        endpoint = f"PUT /app/v1/personal-places/{place_id}"

        async def build():
            try:
                data = json.loads(body_bytes or b"{}")
                if not isinstance(data, dict):
                    raise ValueError
                body = parse_personal_place_body(data)
            except (ValueError, TypeError, json.JSONDecodeError):
                return error_response(
                    "validation_error",
                    "Некорректные данные личного места.",
                    rid,
                    400,
                )
            try:
                updated = _places_service.update(
                    user_id=user_id,
                    public_id=place_id,
                    name=body.name,
                    category=body.category,
                    general_location=body.general_location,
                    landmark=body.landmark,
                    note=body.note,
                )
            except PersonalPlaceValidationError as exc:
                return error_response(
                    "validation_error",
                    _personal_place_validation_message(exc),
                    rid,
                    400,
                )
            except PersonalPlaceConflictError:
                return error_response(
                    "conflict",
                    "Личное место не может быть обновлено.",
                    rid,
                    409,
                )
            if updated is None:
                return _place_not_found_response(rid)
            return success_response(personal_place_to_api(updated), rid)

        return await _idempotent(request, user_id, endpoint, body_bytes, build)

    async def deactivate_personal_place_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        place_id, place_failure = _resolve_place_id(request, rid)
        if place_failure is not None:
            return place_failure
        body_bytes = await request.read()
        if body_bytes.strip():
            return error_response(
                "validation_error",
                "Некорректный запрос.",
                rid,
                400,
            )
        endpoint = f"POST /app/v1/personal-places/{place_id}/deactivate"

        async def build():
            try:
                changed = _places_service.deactivate(user_id=user_id, public_id=place_id)
            except PersonalPlaceValidationError as exc:
                return error_response(
                    "validation_error",
                    _personal_place_validation_message(exc),
                    rid,
                    400,
                )
            if not changed:
                return _place_not_found_response(rid)
            return success_response({}, rid)

        return await _idempotent(request, user_id, endpoint, body_bytes, build)

    app.router.add_get("/app/v1/personal-places", list_personal_places_handler)
    app.router.add_post("/app/v1/personal-places", create_personal_place_handler)
    app.router.add_get("/app/v1/personal-places/{placeId}", get_personal_place_handler)
    app.router.add_put("/app/v1/personal-places/{placeId}", update_personal_place_handler)
    app.router.add_post(
        "/app/v1/personal-places/{placeId}/deactivate",
        deactivate_personal_place_handler,
    )
