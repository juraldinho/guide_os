from __future__ import annotations

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


def _company_summary_to_api(item) -> dict:
    return {
        "companyId": item.company_id,
        "displayName": item.display_name,
        "pendingTotal": item.pending_total,
        "creditedTotal": item.credited_total,
    }


def _points_summary_to_api(summary) -> dict:
    return {
        "unit": summary.unit,
        "pendingTotal": summary.pending_total,
        "creditedTotal": summary.credited_total,
        "companies": [_company_summary_to_api(item) for item in summary.companies],
    }


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


def register_guideshop_points_routes(app: web.Application) -> None:
    async def points_summary_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        provider, reads_enabled = get_miniapp_guideshop_provider()
        if provider is None or not reads_enabled:
            return _integration_disabled_response(rid)
        try:
            async with provider.service_for(user_id) as service:
                summary = await service.get_official_points_summary()
        except _GUIDESHOP_ROUTE_ERRORS as exc:
            return _guideshop_error_response(exc, rid)
        return success_response(_points_summary_to_api(summary), rid)

    app.router.add_get(
        "/app/v1/guideshop/points/summary",
        points_summary_handler,
    )
