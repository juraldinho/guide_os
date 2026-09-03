"""GSMA7E — Mini App official GuideShop payout history composition API."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

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
from services.guide_shop_contracts import PointsPayoutDTO
from services.guide_shop_runtime import (
    RequestScopedGuideShopUIServiceProvider,
    StaticGuideShopUIServiceProvider,
)
from services.guide_shop_ui import GuideShopUIService
from services.miniapp_api_settings import MiniAppApiSettings
from web_api.app import create_miniapp_api_app
from web_api.auth import dev_session_token
from web_api.routes.guideshop_companies import configure_miniapp_guideshop_provider

API_USER = 887001
TEST_BOT_TOKEN = "7000000000:TEST_miniapp_synthetic_bot_token"
GUIDE_OS_A = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee1"
UTC = "2026-08-15T10:30:00Z"
OFFICIAL_HISTORY_FIELDS = {
    "id",
    "pointsAccrualId",
    "companyId",
    "visitId",
    "amount",
    "unit",
    "paidAt",
    "createdAt",
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


def _official_payout(
    payout_id="payout-01",
    *,
    accrual_id="points-01",
    company_id="company-1",
    visit_id="visit-01",
    amount="2.00",
):
    return PointsPayoutDTO.model_validate(
        {
            "payout_id": payout_id,
            "points_accrual_id": accrual_id,
            "company_id": company_id,
            "visit_id": visit_id,
            "amount": amount,
            "unit": "PTS",
            "paid_at": UTC,
            "created_at": UTC,
        }
    )


def _configure_static(service, *, reads_enabled=True):
    configure_miniapp_guideshop_provider(
        StaticGuideShopUIServiceProvider(service),
        reads_enabled=reads_enabled,
    )


def _list_history(user_id=API_USER, query=""):
    return api_request(
        "GET",
        f"/app/v1/guideshop/history{query}",
        headers=_auth_headers(user_id),
    )


class TrackingInMemoryGuideShopClient(InMemoryGuideShopClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


def test_official_history_route_registered_once():
    app = create_miniapp_api_app(_settings())
    routes = [
        (route.method, route.resource.canonical)
        for route in app.router.routes()
    ]
    assert routes.count(("GET", "/app/v1/guideshop/history")) == 1
    assert ("POST", "/app/v1/guideshop/history") not in routes
    assert ("PUT", "/app/v1/guideshop/history") not in routes
    assert ("PATCH", "/app/v1/guideshop/history") not in routes
    assert ("DELETE", "/app/v1/guideshop/history") not in routes
    assert ("GET", "/app/v1/guideshop/history/{payoutId}") not in routes


def test_official_history_list_success_field_mapping(seeded_user):
    payout = _official_payout(
        payout_id="payout-silk",
        company_id="cmp_silk01",
        amount="4.50",
    )
    _configure_static(
        GuideShopUIService(InMemoryGuideShopClient(points_history=(payout,)))
    )
    response = _list_history(seeded_user)
    body = response_json(response)
    assert response.status == 200
    assert set(body["data"].keys()) == {"history", "page"}
    assert body["data"]["page"] == {"nextCursor": None}
    assert len(body["data"]["history"]) == 1
    mapped = body["data"]["history"][0]
    assert set(mapped.keys()) == OFFICIAL_HISTORY_FIELDS
    assert mapped == {
        "id": "payout-silk",
        "pointsAccrualId": "points-01",
        "companyId": "cmp_silk01",
        "visitId": "visit-01",
        "amount": "4.50",
        "unit": "PTS",
        "paidAt": "2026-08-15T10:30:00Z",
        "createdAt": "2026-08-15T10:30:00Z",
    }
    dumped = response._body_text
    assert "payout_id" not in dumped
    assert "points_accrual_id" not in dumped
    assert "company_id" not in dumped
    assert "paid_at" not in dumped


def test_official_history_empty_list(seeded_user):
    _configure_static(GuideShopUIService(InMemoryGuideShopClient(points_history=())))
    response = _list_history(seeded_user)
    body = response_json(response)
    assert response.status == 200
    assert body["data"] == {"history": [], "page": {"nextCursor": None}}


def test_official_history_page_cursor_remains_opaque(seeded_user):
    opaque_cursor = "opaque_history_cursor_01"

    class FakeService:
        async def list_official_history(self, cursor=None):
            assert cursor is None
            return SimpleNamespace(
                data=[_official_payout(payout_id="payout-page")],
                page=SimpleNamespace(next_cursor=opaque_cursor, has_more=True),
            )

    _configure_static(FakeService())
    body = response_json(_list_history(seeded_user))
    assert body["data"]["page"] == {"nextCursor": opaque_cursor}
    assert "has_more" not in body["data"]["page"]
    assert "hasMore" not in body["data"]["page"]


def test_official_history_list_forwards_cursor_query(seeded_user):
    seen = []

    class FakeService:
        async def list_official_history(self, cursor=None):
            seen.append(cursor)
            return SimpleNamespace(
                data=[],
                page=SimpleNamespace(next_cursor=None, has_more=False),
            )

    _configure_static(FakeService())
    response = _list_history(seeded_user, query="?cursor=opaque_page_two")
    assert response.status == 200
    assert seen == ["opaque_page_two"]


def test_official_history_mutations_unavailable(seeded_user):
    calls = []

    class CountingService:
        async def list_official_history(self, cursor=None):
            calls.append("list")
            return SimpleNamespace(data=[], page=SimpleNamespace(next_cursor=None))

    _configure_static(CountingService())
    mutations = [
        ("POST", "/app/v1/guideshop/history", {"json": {"amount": "1.00"}}),
        ("PUT", "/app/v1/guideshop/history", {"json": {}}),
        ("PATCH", "/app/v1/guideshop/history", {"json": {}}),
        ("DELETE", "/app/v1/guideshop/history", {}),
    ]
    for method, path, kwargs in mutations:
        response = api_request(method, path, headers=_auth_headers(seeded_user), **kwargs)
        assert response.status in {404, 405}
        assert response.status != 500
    assert calls == []


def test_official_history_auth_required():
    response = api_request("GET", "/app/v1/guideshop/history")
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_required"


def test_official_history_provider_absent_is_integration_disabled(seeded_user):
    response = _list_history(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "integration_disabled"
    assert body["error"]["message"] == "Раздел GuideShop временно отключён."


def test_official_history_disabled_client(seeded_user):
    _configure_static(GuideShopUIService(DisabledGuideShopClient()))
    response = _list_history(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "integration_disabled"


def test_official_history_reads_disabled_flag(seeded_user):
    _configure_static(
        GuideShopUIService(InMemoryGuideShopClient(points_history=(_official_payout(),))),
        reads_enabled=False,
    )
    response = _list_history(seeded_user)
    assert response.status == 503
    assert response_json(response)["error"]["code"] == "integration_disabled"


def test_official_history_missing_identity_is_access_denied(seeded_user):
    provider = RequestScopedGuideShopUIServiceProvider(
        lambda _user_id: None,
        lambda _guide_os_id: TrackingInMemoryGuideShopClient(),
    )
    configure_miniapp_guideshop_provider(provider, reads_enabled=True)
    response = _list_history(seeded_user)
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
def test_official_history_auth_and_access_denied(seeded_user, error):
    class FakeService:
        async def list_official_history(self, cursor=None):
            raise error

    _configure_static(FakeService())
    response = _list_history(seeded_user)
    body = response_json(response)
    assert response.status == 403
    assert body["error"]["code"] == "access_denied"
    assert "secret" not in response._body_text


def test_official_history_temporary_outage(seeded_user):
    class FakeService:
        async def list_official_history(self, cursor=None):
            raise GuideShopTemporarilyUnavailableError("timeout upstream")

    _configure_static(FakeService())
    response = _list_history(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "temporarily_unavailable"
    assert body["error"]["message"] == (
        "GuideShop временно недоступен. Попробуйте позже."
    )
    assert "timeout" not in response._body_text


def test_official_history_generic_client_not_http_500(seeded_user):
    class FakeService:
        async def list_official_history(self, cursor=None):
            raise GuideShopClientError("generic failure detail")

    _configure_static(FakeService())
    response = _list_history(seeded_user)
    assert response.status == 503
    assert response_json(response)["error"]["code"] == "temporarily_unavailable"
    assert response.status != 500
    assert "generic failure" not in response._body_text


def test_official_history_closes_client_after_success(seeded_user):
    client = TrackingInMemoryGuideShopClient(points_history=(_official_payout(),))
    provider = RequestScopedGuideShopUIServiceProvider(
        lambda _user_id: GUIDE_OS_A,
        lambda _guide_os_id: client,
    )
    configure_miniapp_guideshop_provider(provider, reads_enabled=True)
    response = _list_history(seeded_user)
    assert response.status == 200
    assert client.close_calls >= 1
