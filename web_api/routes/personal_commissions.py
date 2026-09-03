from __future__ import annotations

import json

from aiohttp import web

from services.external_sales_service import (
    ExternalSaleConflictError,
    ExternalSalePlaceNotFoundError,
    ExternalSalesService,
    ExternalSaleValidationError,
)
from services.personal_places_service import PersonalPlacesService
from web_api.auth import idempotency_lookup, idempotency_store
from web_api.dto import (
    parse_personal_commission_body,
    parse_personal_commission_id,
    parse_personal_place_id,
    personal_commission_to_api,
)
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error

_places_service = PersonalPlacesService()
_sales_service = ExternalSalesService()


def _place_not_found_response(rid: str) -> web.Response:
    return error_response("not_found", "Личная компания не найдена.", rid, 404)


def _commission_not_found_response(rid: str) -> web.Response:
    return error_response("not_found", "Запись комиссии не найдена.", rid, 404)


def _resolve_place_id(request: web.Request, rid: str) -> tuple[str | None, web.Response | None]:
    parsed = parse_personal_place_id(request.match_info["placeId"])
    if parsed is None:
        return None, _place_not_found_response(rid)
    return parsed, None


def _resolve_commission_id(
    request: web.Request,
    rid: str,
) -> tuple[str | None, web.Response | None]:
    parsed = parse_personal_commission_id(request.match_info["commissionId"])
    if parsed is None:
        return None, _commission_not_found_response(rid)
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


def _commission_validation_message(exc: ExternalSaleValidationError) -> str:
    message = str(exc)
    mapping = {
        "Invalid external sale timestamp": "Некорректная дата операции.",
        "External sale is not completed": "Дата операции не может быть в будущем.",
        "External sale outcome is required": "Укажите комиссию, баллы или сумму покупки.",
        "Invalid received points": "Некорректные баллы.",
        "Invalid external sale value": "Некорректная денежная сумма.",
        "Unexpected external sale currency": "Валюта не требуется для этой записи.",
        "External sale currency is required": "Укажите валюту.",
        "Invalid external sale currency": "Некорректная валюта.",
        "Invalid external sale note": "Некорректная заметка.",
        "Invalid personal place identifier": "Некорректный идентификатор личной компании.",
        "Invalid external sale identifier": "Некорректный идентификатор комиссии.",
        "Invalid external sale owner": "Некорректный владелец.",
        "Invalid external sale filter": "Некорректный параметр includeInactive.",
    }
    return mapping.get(message, "Некорректные данные комиссии.")


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


def register_personal_commissions_routes(app: web.Application) -> None:
    async def list_commissions_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        place_id, place_failure = _resolve_place_id(request, rid)
        if place_failure is not None:
            return place_failure
        include_inactive, invalid = _parse_include_inactive(request)
        if invalid:
            return error_response(
                "validation_error",
                "Некорректный параметр includeInactive.",
                rid,
                400,
            )
        place = _places_service.get(user_id=user_id, public_id=place_id)
        if place is None:
            return _place_not_found_response(rid)
        try:
            commissions = _sales_service.list(
                user_id=user_id,
                personal_place_id=place_id,
                include_inactive=include_inactive,
            )
        except ExternalSaleValidationError as exc:
            return error_response(
                "validation_error",
                _commission_validation_message(exc),
                rid,
                400,
            )
        return success_response(
            {"commissions": [personal_commission_to_api(item) for item in commissions]},
            rid,
        )

    async def create_commission_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        place_id, place_failure = _resolve_place_id(request, rid)
        if place_failure is not None:
            return place_failure
        body_bytes = await request.read()
        endpoint = f"POST /app/v1/personal-places/{place_id}/commissions"

        async def build():
            try:
                data = json.loads(body_bytes or b"{}")
                if not isinstance(data, dict):
                    raise ValueError
                body = parse_personal_commission_body(data)
            except (ValueError, TypeError, json.JSONDecodeError):
                return error_response(
                    "validation_error",
                    "Некорректные данные комиссии.",
                    rid,
                    400,
                )
            try:
                created = _sales_service.create(
                    user_id=user_id,
                    personal_place_id=place_id,
                    occurred_at=body.occurred_at,
                    purchase_amount_minor=body.purchase_amount_minor,
                    received_income_minor=body.received_income_minor,
                    received_points=body.received_points,
                    currency=body.currency,
                    note=body.note,
                )
            except ExternalSalePlaceNotFoundError:
                return _place_not_found_response(rid)
            except ExternalSaleValidationError as exc:
                return error_response(
                    "validation_error",
                    _commission_validation_message(exc),
                    rid,
                    400,
                )
            except ExternalSaleConflictError:
                return error_response(
                    "conflict",
                    "Запись комиссии не может быть создана.",
                    rid,
                    409,
                )
            return success_response(personal_commission_to_api(created), rid, status=201)

        return await _idempotent(request, user_id, endpoint, body_bytes, build)

    async def get_commission_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        commission_id, commission_failure = _resolve_commission_id(request, rid)
        if commission_failure is not None:
            return commission_failure
        sale = _sales_service.get(user_id=user_id, public_id=commission_id)
        if sale is None:
            return _commission_not_found_response(rid)
        return success_response(personal_commission_to_api(sale), rid)

    async def update_commission_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        commission_id, commission_failure = _resolve_commission_id(request, rid)
        if commission_failure is not None:
            return commission_failure
        body_bytes = await request.read()
        endpoint = f"PUT /app/v1/personal-commissions/{commission_id}"

        async def build():
            try:
                data = json.loads(body_bytes or b"{}")
                if not isinstance(data, dict):
                    raise ValueError
                body = parse_personal_commission_body(data)
            except (ValueError, TypeError, json.JSONDecodeError):
                return error_response(
                    "validation_error",
                    "Некорректные данные комиссии.",
                    rid,
                    400,
                )
            try:
                updated = _sales_service.update(
                    user_id=user_id,
                    public_id=commission_id,
                    occurred_at=body.occurred_at,
                    purchase_amount_minor=body.purchase_amount_minor,
                    received_income_minor=body.received_income_minor,
                    received_points=body.received_points,
                    currency=body.currency,
                    note=body.note,
                )
            except ExternalSaleValidationError as exc:
                return error_response(
                    "validation_error",
                    _commission_validation_message(exc),
                    rid,
                    400,
                )
            except ExternalSaleConflictError:
                return error_response(
                    "conflict",
                    "Запись комиссии не может быть обновлена.",
                    rid,
                    409,
                )
            if updated is None:
                return _commission_not_found_response(rid)
            return success_response(personal_commission_to_api(updated), rid)

        return await _idempotent(request, user_id, endpoint, body_bytes, build)

    async def deactivate_commission_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        commission_id, commission_failure = _resolve_commission_id(request, rid)
        if commission_failure is not None:
            return commission_failure
        body_bytes = await request.read()
        if body_bytes.strip():
            return error_response(
                "validation_error",
                "Некорректный запрос.",
                rid,
                400,
            )
        endpoint = f"POST /app/v1/personal-commissions/{commission_id}/deactivate"

        async def build():
            try:
                changed = _sales_service.deactivate(
                    user_id=user_id,
                    public_id=commission_id,
                )
            except ExternalSaleValidationError as exc:
                return error_response(
                    "validation_error",
                    _commission_validation_message(exc),
                    rid,
                    400,
                )
            if not changed:
                return _commission_not_found_response(rid)
            return success_response({}, rid)

        return await _idempotent(request, user_id, endpoint, body_bytes, build)

    app.router.add_get(
        "/app/v1/personal-places/{placeId}/commissions",
        list_commissions_handler,
    )
    app.router.add_post(
        "/app/v1/personal-places/{placeId}/commissions",
        create_commission_handler,
    )
    app.router.add_get(
        "/app/v1/personal-commissions/{commissionId}",
        get_commission_handler,
    )
    app.router.add_put(
        "/app/v1/personal-commissions/{commissionId}",
        update_commission_handler,
    )
    app.router.add_post(
        "/app/v1/personal-commissions/{commissionId}/deactivate",
        deactivate_commission_handler,
    )
