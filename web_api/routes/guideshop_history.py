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
from services.guide_shop_runtime import (
    GuideShopClientLifecycleError,
    GuideShopIdentityUnavailableError,
    GuideShopRuntimeError,
)
from web_api.errors import error_response, success_response
from web_api.routes.guideshop_companies import get_miniapp_guideshop_provider
from web_api.routes.session import _auth_or_error

_MSG_INTEGRATION_DISABLED = "Раздел GuideShop временно отключён."
_MSG_ACCESS_DENIED = "Нет доступа к данным GuideShop."
_MSG_NOT_FOUND = "Данные GuideShop не найдены."
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


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be datetime")
    utc_value = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    utc_value = utc_value.astimezone(timezone.utc)
    return utc_value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _payout_to_api(item) -> dict:
    return {
        "id": item.payout_id,
        "pointsAccrualId": item.points_accrual_id,
        "companyId": item.company_id,
        "visitId": item.visit_id,
        "amount": item.amount,
        "unit": item.unit,
        "paidAt": _utc_iso(item.paid_at),
        "createdAt": _utc_iso(item.created_at),
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


def _integration_disabled_response(rid: str) -> web.Response:
    return error_response(
        "integration_disabled",
        _MSG_INTEGRATION_DISABLED,
        rid,
        503,
    )


def register_guideshop_history_routes(app: web.Application) -> None:
    async def list_history_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        provider, reads_enabled = get_miniapp_guideshop_provider()
        if provider is None or not reads_enabled:
            return _integration_disabled_response(rid)
        raw_cursor = request.rel_url.query.get("cursor")
        cursor = raw_cursor if isinstance(raw_cursor, str) and raw_cursor else None
        try:
            async with provider.service_for(user_id) as service:
                response = await service.list_official_history(cursor)
        except _GUIDESHOP_ROUTE_ERRORS as exc:
            return _guideshop_error_response(exc, rid)
        return success_response(
            {
                "history": [_payout_to_api(item) for item in response.data],
                "page": _page_to_api(response),
            },
            rid,
        )

    app.router.add_get("/app/v1/guideshop/history", list_history_handler)
