"""GSMA7D — Mini App official GuideShop sales composition API."""

from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

import pytest
from aiohttp.test_utils import TestClient, TestServer

from database.queries import register_user
from services.guide_shop_client import (
    DisabledGuideShopClient,
    GuideShopAccessDeniedError,
    GuideShopAuthenticationError,
    GuideShopClientError,
    GuideShopTemporarilyUnavailableError,
    InMemoryGuideShopClient,
)
from services.guide_shop_contracts import SaleDTO
from services.guide_shop_runtime import (
    RequestScopedGuideShopUIServiceProvider,
    StaticGuideShopUIServiceProvider,
)
from services.guide_shop_ui import GuideShopUIService
from services.miniapp_api_settings import MiniAppApiSettings
from types import SimpleNamespace
from web_api.app import create_miniapp_api_app
from web_api.auth import dev_session_token
from web_api.routes.guideshop_companies import configure_miniapp_guideshop_provider

API_USER = 887001
TEST_BOT_TOKEN = "7000000000:TEST_miniapp_synthetic_bot_token"
GUIDE_OS_A = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee1"
UTC = "2026-08-15T10:30:00Z"
OFFICIAL_SALE_FIELDS = {
    "id",
    "visitId",
    "companyId",
    "amount",
    "currency",
    "status",
    "paymentMethod",
    "comment",
    "categoryId",
    "categoryName",
    "createdAt",
    "updatedAt",
}


def run(awaitable):
    return asyncio.run(awaitable)


def _settings():
    return MiniAppApiSettings(
        enabled=True,
        host="127.0.0.1",
        port=8083,
        dev_auth=True,
        bot_token=TEST_BOT_TOKEN,
        session_ttl_seconds=3600,
        initdata_max_age_seconds=86400,
        allowlist=frozenset(),
    )


def _auth_headers(user_id=API_USER, **extra):
    headers = {
        "Authorization": f"Bearer {dev_session_token(user_id)}",
        "Content-Type": "application/json",
    }
    headers.update(extra)
    return headers


async def _with_client(coro):
    app = create_miniapp_api_app(_settings())
    client = TestClient(TestServer(app))
    async with client:
        response = await coro(client)
        response._body_text = await response.text()
        return response


def response_json(response):
    return json.loads(response._body_text)


def api_request(method, path, **kwargs):
    async def _call(client):
        return await client.request(method, path, **kwargs)

    return run(_with_client(_call))


@pytest.fixture(autouse=True)
def _reset_miniapp_guideshop_provider():
    configure_miniapp_guideshop_provider(None, reads_enabled=False)
    yield
    configure_miniapp_guideshop_provider(None, reads_enabled=False)


@pytest.fixture
def seeded_user():
    register_user(API_USER)
    return API_USER


def _official_sale(
    sale_id="sale-0001",
    *,
    visit_id="visit-01",
    company_id="company-1",
    amount="125.40",
    payment_method="card",
    comment=None,
    category_id="category1",
    category_name="Textiles",
):
    payload = {
        "sale_id": sale_id,
        "visit_id": visit_id,
        "company_id": company_id,
        "amount": amount,
        "currency": "USD",
        "status": "active",
        "payment_method": payment_method,
        "category_id": category_id,
        "category_name": category_name,
        "created_at": UTC,
        "updated_at": UTC,
    }
    if comment is not None:
        payload["comment"] = comment
    return SaleDTO.model_validate(payload)


def _configure_static(service, *, reads_enabled=True):
    configure_miniapp_guideshop_provider(
        StaticGuideShopUIServiceProvider(service),
        reads_enabled=reads_enabled,
    )


def _list_sales(user_id=API_USER, query=""):
    return api_request(
        "GET",
        f"/app/v1/guideshop/sales{query}",
        headers=_auth_headers(user_id),
    )


def _get_sale(user_id, sale_id):
    return api_request(
        "GET",
        f"/app/v1/guideshop/sales/{sale_id}",
        headers=_auth_headers(user_id),
    )


class TrackingInMemoryGuideShopClient(InMemoryGuideShopClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


def test_official_sales_routes_registered_once():
    app = create_miniapp_api_app(_settings())
    routes = [
        (route.method, route.resource.canonical)
        for route in app.router.routes()
    ]
    assert routes.count(("GET", "/app/v1/guideshop/sales")) == 1
    assert routes.count(("GET", "/app/v1/guideshop/sales/{saleId}")) == 1
    assert ("POST", "/app/v1/guideshop/sales") not in routes
    assert ("PUT", "/app/v1/guideshop/sales/{saleId}") not in routes
    assert ("PATCH", "/app/v1/guideshop/sales/{saleId}") not in routes
    assert ("DELETE", "/app/v1/guideshop/sales/{saleId}") not in routes
    assert ("GET", "/app/v1/guideshop/history") not in routes


def test_official_sales_list_success_field_mapping(seeded_user):
    sale = _official_sale(
        sale_id="sale-silk1",
        company_id="cmp_silk01",
        amount="99.50",
        payment_method="cash",
        comment="Group souvenirs",
    )
    _configure_static(GuideShopUIService(InMemoryGuideShopClient(sales=(sale,))))
    response = _list_sales(seeded_user)
    body = response_json(response)
    assert response.status == 200
    assert set(body["data"].keys()) == {"sales", "page"}
    assert body["data"]["page"] == {"nextCursor": None}
    assert len(body["data"]["sales"]) == 1
    mapped = body["data"]["sales"][0]
    assert set(mapped.keys()) == OFFICIAL_SALE_FIELDS
    assert mapped == {
        "id": "sale-silk1",
        "visitId": "visit-01",
        "companyId": "cmp_silk01",
        "amount": "99.50",
        "currency": "USD",
        "status": "active",
        "paymentMethod": "cash",
        "comment": "Group souvenirs",
        "categoryId": "category1",
        "categoryName": "Textiles",
        "createdAt": "2026-08-15T10:30:00Z",
        "updatedAt": "2026-08-15T10:30:00Z",
    }
    dumped = response._body_text
    assert "sale_id" not in dumped
    assert "payment_method" not in dumped
    assert "category_name" not in dumped
    assert "company_id" not in dumped


def test_official_sales_null_comment_and_unresolved_category(seeded_user):
    sale = _official_sale(
        sale_id="sale-unres",
        category_id=None,
        category_name="Category unavailable",
    )
    _configure_static(GuideShopUIService(InMemoryGuideShopClient(sales=(sale,))))
    mapped = response_json(_list_sales(seeded_user))["data"]["sales"][0]
    assert mapped["comment"] is None
    assert mapped["categoryId"] is None
    assert mapped["categoryName"] == "Category unavailable"


def test_official_sales_page_cursor_remains_opaque(seeded_user):
    opaque_cursor = "opaque_sales_cursor_01"

    class FakeService:
        async def list_official_sales(self, cursor=None):
            assert cursor is None
            return SimpleNamespace(
                data=[_official_sale(sale_id="sale-page1")],
                page=SimpleNamespace(next_cursor=opaque_cursor, has_more=True),
            )

    _configure_static(FakeService())
    body = response_json(_list_sales(seeded_user))
    assert body["data"]["page"] == {"nextCursor": opaque_cursor}
    assert "has_more" not in body["data"]["page"]
    assert "hasMore" not in body["data"]["page"]


def test_official_sales_list_forwards_cursor_query(seeded_user):
    seen = []

    class FakeService:
        async def list_official_sales(self, cursor=None):
            seen.append(cursor)
            return SimpleNamespace(
                data=[],
                page=SimpleNamespace(next_cursor=None, has_more=False),
            )

    _configure_static(FakeService())
    response = _list_sales(seeded_user, query="?cursor=opaque_page_two")
    assert response.status == 200
    assert seen == ["opaque_page_two"]


def test_official_sale_detail_success(seeded_user):
    sales = (
        _official_sale(sale_id="sale-aaaa", company_id="cmp_alpha"),
        _official_sale(sale_id="sale-bbbb", company_id="cmp_beta"),
    )
    _configure_static(GuideShopUIService(InMemoryGuideShopClient(sales=sales)))
    response = _get_sale(seeded_user, "sale-aaaa")
    body = response_json(response)
    assert response.status == 200
    assert set(body["data"].keys()) == OFFICIAL_SALE_FIELDS
    assert body["data"]["id"] == "sale-aaaa"
    assert body["data"]["companyId"] == "cmp_alpha"
    assert body["data"]["amount"] == "125.40"
    assert body["data"]["currency"] == "USD"


def test_official_sale_detail_missing_is_not_found(seeded_user):
    _configure_static(
        GuideShopUIService(InMemoryGuideShopClient(sales=(_official_sale(),)))
    )
    response = _get_sale(seeded_user, "missing1")
    body = response_json(response)
    assert response.status == 404
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Продажа не найдена."
    assert "missing1" not in response._body_text


def test_official_sale_detail_unsafe_id_is_safe_not_found(seeded_user):
    from services.guide_shop_contracts import _opaque_id

    calls = []

    class CountingService:
        async def get_official_sale(self, sale_id):
            calls.append(sale_id)
            return None

    _configure_static(CountingService())
    unsafe_ids = ["short", "12345678", "sale!", "bad id", "xx"]
    for sale_id in unsafe_ids:
        with pytest.raises(ValueError):
            _opaque_id(sale_id)
        response = api_request(
            "GET",
            f"/app/v1/guideshop/sales/{quote(sale_id, safe='')}",
            headers=_auth_headers(seeded_user),
        )
        body = response_json(response)
        assert response.status == 404
        assert body["error"]["code"] == "not_found"
        assert body["error"]["message"] == "Продажа не найдена."
        assert sale_id not in body["error"]["message"]
        assert sale_id not in response._body_text
        assert response.status != 500
    assert calls == []


def test_official_sales_mutations_unavailable(seeded_user):
    calls = []

    class CountingService:
        async def list_official_sales(self, cursor=None):
            calls.append("list")
            return SimpleNamespace(data=[], page=SimpleNamespace(next_cursor=None))

        async def get_official_sale(self, sale_id):
            calls.append(("get", sale_id))
            return None

    _configure_static(CountingService())
    sale_id = "sale-mut1"
    mutations = [
        ("POST", "/app/v1/guideshop/sales", {"json": {"amount": "1.00"}}),
        ("PUT", f"/app/v1/guideshop/sales/{sale_id}", {"json": {}}),
        ("PATCH", f"/app/v1/guideshop/sales/{sale_id}", {"json": {}}),
        ("DELETE", f"/app/v1/guideshop/sales/{sale_id}", {}),
    ]
    for method, path, kwargs in mutations:
        response = api_request(method, path, headers=_auth_headers(seeded_user), **kwargs)
        assert response.status in {404, 405}
        assert response.status != 500
    assert calls == []


def test_official_sales_auth_required():
    response = api_request("GET", "/app/v1/guideshop/sales")
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_required"


def test_official_sales_provider_absent_is_integration_disabled(seeded_user):
    response = _list_sales(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "integration_disabled"
    assert body["error"]["message"] == "Раздел GuideShop временно отключён."


def test_official_sales_disabled_client(seeded_user):
    _configure_static(GuideShopUIService(DisabledGuideShopClient()))
    response = _list_sales(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "integration_disabled"


def test_official_sales_reads_disabled_flag(seeded_user):
    _configure_static(
        GuideShopUIService(InMemoryGuideShopClient(sales=(_official_sale(),))),
        reads_enabled=False,
    )
    response = _list_sales(seeded_user)
    assert response.status == 503
    assert response_json(response)["error"]["code"] == "integration_disabled"


def test_official_sales_missing_identity_is_access_denied(seeded_user):
    provider = RequestScopedGuideShopUIServiceProvider(
        lambda _user_id: None,
        lambda _guide_os_id: TrackingInMemoryGuideShopClient(),
    )
    configure_miniapp_guideshop_provider(provider, reads_enabled=True)
    response = _list_sales(seeded_user)
    body = response_json(response)
    assert response.status == 403
    assert body["error"]["code"] == "access_denied"
    assert body["error"]["message"] == "Нет доступа к данным GuideShop."


@pytest.mark.parametrize(
    "error",
    [
        GuideShopAuthenticationError("secret-token"),
        GuideShopAccessDeniedError("secret-deny"),
    ],
)
def test_official_sales_auth_and_access_denied(seeded_user, error):
    class FakeService:
        async def list_official_sales(self, cursor=None):
            raise error

    _configure_static(FakeService())
    response = _list_sales(seeded_user)
    body = response_json(response)
    assert response.status == 403
    assert body["error"]["code"] == "access_denied"
    assert "secret" not in response._body_text


def test_official_sales_temporary_outage(seeded_user):
    class FakeService:
        async def list_official_sales(self, cursor=None):
            raise GuideShopTemporarilyUnavailableError("timeout upstream")

    _configure_static(FakeService())
    response = _list_sales(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "temporarily_unavailable"
    assert body["error"]["message"] == (
        "GuideShop временно недоступен. Попробуйте позже."
    )
    assert "timeout" not in response._body_text


def test_official_sales_generic_client_not_http_500(seeded_user):
    class FakeService:
        async def list_official_sales(self, cursor=None):
            raise GuideShopClientError("generic failure detail")

    _configure_static(FakeService())
    response = _list_sales(seeded_user)
    assert response.status == 503
    assert response_json(response)["error"]["code"] == "temporarily_unavailable"
    assert response.status != 500
    assert "generic failure" not in response._body_text


def test_official_sales_closes_client_after_success(seeded_user):
    client = TrackingInMemoryGuideShopClient(sales=(_official_sale(),))
    provider = RequestScopedGuideShopUIServiceProvider(
        lambda _user_id: GUIDE_OS_A,
        lambda _guide_os_id: client,
    )
    configure_miniapp_guideshop_provider(provider, reads_enabled=True)
    response = _list_sales(seeded_user)
    assert response.status == 200
    assert client.close_calls >= 1


def test_official_sale_detail_closes_client_on_not_found(seeded_user):
    client = TrackingInMemoryGuideShopClient(sales=())
    provider = RequestScopedGuideShopUIServiceProvider(
        lambda _user_id: GUIDE_OS_A,
        lambda _guide_os_id: client,
    )
    configure_miniapp_guideshop_provider(provider, reads_enabled=True)
    response = _get_sale(seeded_user, "sale-gone")
    assert response.status == 404
    assert client.close_calls >= 1
