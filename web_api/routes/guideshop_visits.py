from __future__ import annotations

from datetime import datetime, timezone

from aiohttp import web

from services.guide_shop_client import (
    GuideShopAccessDeniedError,
    GuideShopAuthenticationError,
    GuideShopClientError,
    GuideShopIntegrationDisabledError,
    GuideShopObjectNotFoundError,
    GuideShopTemporarilyUnavailableError,
)
from services.guide_shop_contracts import _opaque_id
from services.guide_shop_runtime import (
    GuideShopClientLifecycleError,
    GuideShopIdentityUnavailableError,
    GuideShopRuntimeError,
)
from web_api.errors import error_response, success_response
from web_api.routes.guideshop_companies import get_miniapp_guideshop_provider
from web_api.routes.guideshop_observe import (
    MiniAppGuideShopSpan,
    outcome_from_guideshop_exc,
)
from web_api.routes.session import _auth_or_error

_MSG_INTEGRATION_DISABLED = "Раздел GuideShop временно отключён."
_MSG_ACCESS_DENIED = "Нет доступа к данным GuideShop."
_MSG_NOT_FOUND = "Визит не найден."
_MSG_TEMPORARILY_UNAVAILABLE = "GuideShop временно недоступен. Попробуйте позже."

_GUIDESHOP_ROUTE_ERRORS = (
    GuideShopIdentityUnavailableError,
    GuideShopAccessDeniedError,
    GuideShopAuthenticationError,
    GuideShopObjectNotFoundError,
    GuideShopIntegrationDisabledError,
    GuideShopTemporarilyUnavailableError,
    GuideShopClientLifecycleError,
    GuideShopClientError,
    GuideShopRuntimeError,
)


def _safe_opaque_id(raw: str) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return _opaque_id(raw)
    except ValueError:
        return None


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be datetime")
    utc_value = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    utc_value = utc_value.astimezone(timezone.utc)
    return utc_value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _visit_to_api(visit) -> dict:
    status = getattr(visit.status, "value", visit.status)
    payment = getattr(
        visit.customer_payment_status, "value", visit.customer_payment_status
    )
    return {
        "id": visit.visit_id,
        "companyId": visit.company_id,
        "visitAt": _utc_iso(visit.visit_at),
        "status": status,
        "touristCount": visit.tourist_count,
        "customerPaymentStatus": payment,
        "customerPaidAt": _utc_iso(visit.customer_paid_at),
        "createdAt": _utc_iso(visit.created_at),
        "updatedAt": _utc_iso(visit.updated_at),
    }


def _visit_point_to_api(item) -> dict:
    status = getattr(item.status, "value", item.status)
    return {
        "amount": item.amount,
        "unit": item.unit,
        "status": status,
    }


def _page_to_api(response) -> dict:
    page = getattr(response, "page", None)
    next_cursor = getattr(page, "next_cursor", None) if page is not None else None
    if next_cursor is not None:
        next_cursor = str(next_cursor)
    return {"nextCursor": next_cursor}


def _guideshop_error_response(exc: Exception, rid: str) -> web.Response:
    if isinstance(exc, GuideShopIdentityUnavailableError):
        return error_response("access_denied", _MSG_ACCESS_DENIED, rid, 403)
    if isinstance(exc, (GuideShopAccessDeniedError, GuideShopAuthenticationError)):
        return error_response("access_denied", _MSG_ACCESS_DENIED, rid, 403)
    if isinstance(exc, GuideShopObjectNotFoundError):
        return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
    if isinstance(exc, GuideShopIntegrationDisabledError):
        return error_response(
            "integration_disabled",
            _MSG_INTEGRATION_DISABLED,
            rid,
            503,
        )
    return error_response(
        "temporarily_unavailable",
        _MSG_TEMPORARILY_UNAVAILABLE,
        rid,
        503,
    )


def _not_found_response(rid: str) -> web.Response:
    return error_response("not_found", _MSG_NOT_FOUND, rid, 404)


def _integration_disabled_response(rid: str) -> web.Response:
    return error_response(
        "integration_disabled",
        _MSG_INTEGRATION_DISABLED,
        rid,
        503,
    )


def register_guideshop_visits_routes(app: web.Application) -> None:
    async def list_visits_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        span = MiniAppGuideShopSpan("visits.list")
        try:
            provider, reads_enabled = get_miniapp_guideshop_provider()
            if provider is None or not reads_enabled:
                span.set_outcome("integration_disabled")
                return _integration_disabled_response(rid)
            raw_cursor = request.rel_url.query.get("cursor")
            cursor = raw_cursor if isinstance(raw_cursor, str) and raw_cursor else None
            try:
                async with provider.service_for(user_id) as service:
                    response = await service.list_official_visits(cursor)
            except _GUIDESHOP_ROUTE_ERRORS as exc:
                span.set_outcome(outcome_from_guideshop_exc(exc))
                return _guideshop_error_response(exc, rid)
            span.set_outcome("ok")
            return success_response(
                {
                    "visits": [_visit_to_api(item) for item in response.data],
                    "page": _page_to_api(response),
                },
                rid,
            )
        finally:
            span.finish()

    async def get_visit_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        visit_id = _safe_opaque_id(request.match_info["visitId"])
        if visit_id is None:
            return _not_found_response(rid)
        span = MiniAppGuideShopSpan("visits.detail")
        try:
            provider, reads_enabled = get_miniapp_guideshop_provider()
            if provider is None or not reads_enabled:
                span.set_outcome("integration_disabled")
                return _integration_disabled_response(rid)
            try:
                async with provider.service_for(user_id) as service:
                    visit = await service.get_official_visit(visit_id)
                    if visit is None:
                        span.set_outcome("not_found")
                        return _not_found_response(rid)
                    points = await service.list_official_visit_points(visit_id)
            except _GUIDESHOP_ROUTE_ERRORS as exc:
                span.set_outcome(outcome_from_guideshop_exc(exc))
                return _guideshop_error_response(exc, rid)
            payload = _visit_to_api(visit)
            payload["points"] = [_visit_point_to_api(item) for item in points]
            span.set_outcome("ok")
            return success_response(payload, rid)
        finally:
            span.finish()

    app.router.add_get("/app/v1/guideshop/visits", list_visits_handler)
    app.router.add_get(
        "/app/v1/guideshop/visits/{visitId}",
        get_visit_handler,
    )
