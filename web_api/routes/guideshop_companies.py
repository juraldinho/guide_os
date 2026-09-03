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
from services.guide_shop_contracts import _opaque_id
from services.guide_shop_runtime import (
    GuideShopClientLifecycleError,
    GuideShopIdentityUnavailableError,
    GuideShopRuntimeConfigurationError,
    GuideShopRuntimeError,
    GuideShopUIServiceProvider,
)
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error

_provider: GuideShopUIServiceProvider | None = None
_reads_enabled = False

_MSG_INTEGRATION_DISABLED = "Раздел GuideShop временно отключён."
_MSG_ACCESS_DENIED = "Нет доступа к данным GuideShop."
_MSG_NOT_FOUND = "Компания не найдена."
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


def configure_miniapp_guideshop_provider(
    provider: GuideShopUIServiceProvider | None,
    *,
    reads_enabled: bool,
) -> None:
    global _provider, _reads_enabled
    _provider = None
    _reads_enabled = False
    if provider is not None:
        try:
            valid_provider = isinstance(provider, GuideShopUIServiceProvider)
        except Exception as exc:
            raise GuideShopRuntimeConfigurationError(
                "GuideShop runtime is not configured"
            ) from exc
        if not valid_provider:
            raise GuideShopRuntimeConfigurationError(
                "GuideShop runtime is not configured"
            )
    _provider = provider
    _reads_enabled = reads_enabled


def get_miniapp_guideshop_provider() -> tuple[
    GuideShopUIServiceProvider | None, bool
]:
    """Shared Mini App GuideShop provider state (companies + submodules)."""
    return _provider, _reads_enabled


def _safe_company_id(raw: str) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return _opaque_id(raw)
    except ValueError:
        return None


def _company_to_api(company) -> dict:
    status = getattr(company.status, "value", company.status)
    return {
        "id": company.company_id,
        "displayName": company.display_name,
        "status": status,
        "phone": company.phone,
        "address": company.address,
        "description": company.description,
        "type": company.type,
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


def register_guideshop_companies_routes(app: web.Application) -> None:
    async def list_companies_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        if _provider is None or not _reads_enabled:
            return _integration_disabled_response(rid)
        try:
            async with _provider.service_for(user_id) as service:
                response = await service.list_official_companies()
        except _GUIDESHOP_ROUTE_ERRORS as exc:
            return _guideshop_error_response(exc, rid)
        return success_response(
            {
                "companies": [_company_to_api(item) for item in response.data],
                "page": _page_to_api(response),
            },
            rid,
        )

    async def get_company_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        company_id = _safe_company_id(request.match_info["companyId"])
        if company_id is None:
            return _not_found_response(rid)
        if _provider is None or not _reads_enabled:
            return _integration_disabled_response(rid)
        try:
            async with _provider.service_for(user_id) as service:
                company = await service.get_official_company(company_id)
        except _GUIDESHOP_ROUTE_ERRORS as exc:
            return _guideshop_error_response(exc, rid)
        if company is None:
            return _not_found_response(rid)
        return success_response(_company_to_api(company), rid)

    app.router.add_get("/app/v1/guideshop/companies", list_companies_handler)
    app.router.add_get(
        "/app/v1/guideshop/companies/{companyId}",
        get_company_handler,
    )
