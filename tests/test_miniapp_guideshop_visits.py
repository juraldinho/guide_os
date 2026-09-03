"""GSMA7B — Mini App official GuideShop visits composition API."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from aiohttp.test_utils import TestClient, TestServer

from database.queries import register_user
from services.guide_shop_client import (
    DisabledGuideShopClient,
    GuideShopAccessDeniedError,
    GuideShopAuthenticationError,
    GuideShopClientError,
    GuideShopObjectNotFoundError,
    GuideShopTemporarilyUnavailableError,
    InMemoryGuideShopClient,
)
from services.guide_shop_contracts import PointsAccrualDTO, VisitDTO
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
OFFICIAL_VISIT_FIELDS = {
    "id",
    "companyId",
    "visitAt",
    "status",
    "touristCount",
    "customerPaymentStatus",
    "customerPaidAt",
    "createdAt",
    "updatedAt",
}
OFFICIAL_VISIT_DETAIL_FIELDS = OFFICIAL_VISIT_FIELDS | {"points"}
OFFICIAL_VISIT_POINT_FIELDS = {"amount", "unit", "status"}



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


def _official_visit(
    visit_id="visit-01",
    company_id="company-1",
    *,
    status="active",
    tourist_count=3,
    paid=False,
    visit_at=UTC,
):
    payload = {
        "visit_id": visit_id,
        "company_id": company_id,
        "guide_membership_id": "gmem-0001",
        "visit_at": visit_at,
        "status": status,
        "tourist_count": tourist_count,
        "customer_payment_status": "paid" if paid else "unpaid",
        "created_at": UTC,
        "updated_at": UTC,
    }
    if paid:
        payload["customer_paid_at"] = "2026-08-15T12:00:00Z"
    return VisitDTO.model_validate(payload)


def _points(
    points_id="points-01",
    *,
    company_id="company-1",
    visit_id="visit-01",
    amount="2.00",
    status="pending",
):
    payload = {
        "points_accrual_id": points_id,
        "company_id": company_id,
        "visit_id": visit_id,
        "amount": amount,
        "unit": "PTS",
        "status": status,
        "calculated_at": UTC,
        "updated_at": UTC,
    }
    if status == "credited":
        payload["credited_at"] = UTC
        payload["payout_id"] = f"pay-{points_id}"
    return PointsAccrualDTO.model_validate(payload)


def _configure_static(service, *, reads_enabled=True):
    configure_miniapp_guideshop_provider(
        StaticGuideShopUIServiceProvider(service),
        reads_enabled=reads_enabled,
    )


def _list_visits(user_id=API_USER, query=""):
    return api_request(
        "GET",
        f"/app/v1/guideshop/visits{query}",
        headers=_auth_headers(user_id),
    )


def _get_visit(user_id, visit_id):
    return api_request(
        "GET",
        f"/app/v1/guideshop/visits/{visit_id}",
        headers=_auth_headers(user_id),
    )


class TrackingInMemoryGuideShopClient(InMemoryGuideShopClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


def test_official_visits_routes_registered_once():
    app = create_miniapp_api_app(_settings())
    routes = [
        (route.method, route.resource.canonical)
        for route in app.router.routes()
    ]
    assert routes.count(("GET", "/app/v1/guideshop/visits")) == 1
    assert routes.count(("GET", "/app/v1/guideshop/visits/{visitId}")) == 1
    assert ("POST", "/app/v1/guideshop/visits") not in routes
    assert ("PUT", "/app/v1/guideshop/visits/{visitId}") not in routes
    assert ("PATCH", "/app/v1/guideshop/visits/{visitId}") not in routes
    assert ("DELETE", "/app/v1/guideshop/visits/{visitId}") not in routes


def test_official_visits_list_success_field_mapping(seeded_user):
    visit = _official_visit(
        visit_id="visit-silk",
        company_id="cmp_silk01",
        status="completed",
        tourist_count=4,
        paid=True,
    )
    _configure_static(GuideShopUIService(InMemoryGuideShopClient(visits=(visit,))))
    response = _list_visits(seeded_user)
    body = response_json(response)
    assert response.status == 200
    assert set(body["data"].keys()) == {"visits", "page"}
    assert body["data"]["page"] == {"nextCursor": None}
    assert len(body["data"]["visits"]) == 1
    mapped = body["data"]["visits"][0]
    assert set(mapped.keys()) == OFFICIAL_VISIT_FIELDS
    assert mapped == {
        "id": "visit-silk",
        "companyId": "cmp_silk01",
        "visitAt": "2026-08-15T10:30:00Z",
        "status": "completed",
        "touristCount": 4,
        "customerPaymentStatus": "paid",
        "customerPaidAt": "2026-08-15T12:00:00Z",
        "createdAt": "2026-08-15T10:30:00Z",
        "updatedAt": "2026-08-15T10:30:00Z",
    }
    dumped = response._body_text
    assert "guide_membership_id" not in dumped
    assert "guideMembershipId" not in dumped
    assert "visit_id" not in dumped
    assert "company_id" not in dumped
    assert "gmem-0001" not in dumped


def test_official_visits_unpaid_null_paid_at(seeded_user):
    visit = _official_visit(visit_id="visit-unpd", paid=False)
    _configure_static(GuideShopUIService(InMemoryGuideShopClient(visits=(visit,))))
    mapped = response_json(_list_visits(seeded_user))["data"]["visits"][0]
    assert mapped["customerPaymentStatus"] == "unpaid"
    assert mapped["customerPaidAt"] is None


def test_official_visits_page_cursor_remains_opaque(seeded_user):
    opaque_cursor = "opaque_visits_cursor_01"

    class FakeService:
        async def list_official_visits(self, cursor=None):
            assert cursor is None
            return SimpleNamespace(
                data=[_official_visit(visit_id="visit-page")],
                page=SimpleNamespace(next_cursor=opaque_cursor, has_more=True),
            )

    _configure_static(FakeService())
    body = response_json(_list_visits(seeded_user))
    assert body["data"]["page"] == {"nextCursor": opaque_cursor}
    assert "has_more" not in body["data"]["page"]
    assert "hasMore" not in body["data"]["page"]


def test_official_visits_list_forwards_cursor_query(seeded_user):
    seen = []

    class FakeService:
        async def list_official_visits(self, cursor=None):
            seen.append(cursor)
            return SimpleNamespace(
                data=[],
                page=SimpleNamespace(next_cursor=None, has_more=False),
            )

    _configure_static(FakeService())
    response = _list_visits(seeded_user, query="?cursor=opaque_page_two")
    assert response.status == 200
    assert seen == ["opaque_page_two"]


def test_official_visit_detail_success(seeded_user):
    visits = (
        _official_visit(visit_id="visit-aaa", company_id="cmp_alpha"),
        _official_visit(visit_id="visit-bbb", company_id="cmp_beta"),
    )
    points = (
        _points(
            "points-aaa",
            company_id="cmp_alpha",
            visit_id="visit-aaa",
            amount="5.50",
            status="pending",
        ),
        _points(
            "points-bbb",
            company_id="cmp_beta",
            visit_id="visit-bbb",
            amount="1.00",
            status="credited",
        ),
    )
    _configure_static(
        GuideShopUIService(InMemoryGuideShopClient(visits=visits, points=points))
    )
    response = _get_visit(seeded_user, "visit-aaa")
    body = response_json(response)
    assert response.status == 200
    assert set(body["data"].keys()) == OFFICIAL_VISIT_DETAIL_FIELDS
    assert body["data"]["id"] == "visit-aaa"
    assert body["data"]["companyId"] == "cmp_alpha"
    assert body["data"]["points"] == [
        {"amount": "5.50", "unit": "PTS", "status": "pending"}
    ]
    assert set(body["data"]["points"][0].keys()) == OFFICIAL_VISIT_POINT_FIELDS
    assert "points_accrual_id" not in response._body_text
    assert "points-aaa" not in response._body_text
    assert "gmem-0001" not in response._body_text


def test_official_visit_detail_points_empty(seeded_user):
    visit = _official_visit(visit_id="visit-none", company_id="cmp_alpha")
    other = _points(
        "points-other",
        company_id="cmp_alpha",
        visit_id="visit-else",
        amount="9.00",
        status="credited",
    )
    _configure_static(
        GuideShopUIService(InMemoryGuideShopClient(visits=(visit,), points=(other,)))
    )
    body = response_json(_get_visit(seeded_user, "visit-none"))
    assert body["data"]["points"] == []


def test_official_visit_detail_missing_is_not_found(seeded_user):
    _configure_static(
        GuideShopUIService(
            InMemoryGuideShopClient(visits=(_official_visit(),))
        )
    )
    response = _get_visit(seeded_user, "missing1")
    body = response_json(response)
    assert response.status == 404
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Визит не найден."
    assert "missing1" not in response._body_text


def test_official_visit_detail_unsafe_id_is_safe_not_found(seeded_user):
    from services.guide_shop_contracts import _opaque_id

    calls = []

    class CountingService:
        async def get_official_visit(self, visit_id):
            calls.append(visit_id)
            return None

    _configure_static(CountingService())
    unsafe_ids = ["short", "12345678", "visit!", "bad id", "xx"]
    for visit_id in unsafe_ids:
        with pytest.raises(ValueError):
            _opaque_id(visit_id)
        response = api_request(
            "GET",
            f"/app/v1/guideshop/visits/{quote(visit_id, safe='')}",
            headers=_auth_headers(seeded_user),
        )
        body = response_json(response)
        assert response.status == 404
        assert body["error"]["code"] == "not_found"
        assert body["error"]["message"] == "Визит не найден."
        assert visit_id not in body["error"]["message"]
        assert visit_id not in response._body_text
        assert response.status != 500
    assert calls == []


def test_official_visits_mutations_unavailable(seeded_user):
    calls = []

    class CountingService:
        async def list_official_visits(self, cursor=None):
            calls.append("list")
            return SimpleNamespace(data=[], page=SimpleNamespace(next_cursor=None))

        async def get_official_visit(self, visit_id):
            calls.append(("get", visit_id))
            return None

    _configure_static(CountingService())
    visit_id = "visit-mut"
    mutations = [
        ("POST", "/app/v1/guideshop/visits", {"json": {"touristCount": 1}}),
        ("PUT", f"/app/v1/guideshop/visits/{visit_id}", {"json": {}}),
        ("PATCH", f"/app/v1/guideshop/visits/{visit_id}", {"json": {}}),
        ("DELETE", f"/app/v1/guideshop/visits/{visit_id}", {}),
    ]
    for method, path, kwargs in mutations:
        response = api_request(method, path, headers=_auth_headers(seeded_user), **kwargs)
        assert response.status in {404, 405}
        assert response.status != 500
    assert calls == []


def test_official_visits_auth_required():
    response = api_request("GET", "/app/v1/guideshop/visits")
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_required"


def test_official_visits_provider_absent_is_integration_disabled(seeded_user):
    response = _list_visits(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "integration_disabled"
    assert body["error"]["message"] == "Раздел GuideShop временно отключён."


def test_official_visits_disabled_client_is_integration_disabled(seeded_user):
    _configure_static(GuideShopUIService(DisabledGuideShopClient()))
    response = _list_visits(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "integration_disabled"


def test_official_visits_reads_disabled_flag(seeded_user):
    _configure_static(
        GuideShopUIService(InMemoryGuideShopClient(visits=(_official_visit(),))),
        reads_enabled=False,
    )
    response = _list_visits(seeded_user)
    assert response.status == 503
    assert response_json(response)["error"]["code"] == "integration_disabled"


def test_official_visits_missing_identity_is_access_denied(seeded_user):
    provider = RequestScopedGuideShopUIServiceProvider(
        lambda _user_id: None,
        lambda _guide_os_id: TrackingInMemoryGuideShopClient(),
    )
    configure_miniapp_guideshop_provider(provider, reads_enabled=True)
    response = _list_visits(seeded_user)
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
def test_official_visits_auth_and_access_denied(seeded_user, error):
    class FakeService:
        async def list_official_visits(self, cursor=None):
            raise error

    _configure_static(FakeService())
    response = _list_visits(seeded_user)
    body = response_json(response)
    assert response.status == 403
    assert body["error"]["code"] == "access_denied"
    assert "secret" not in response._body_text


def test_official_visits_temporary_outage(seeded_user):
    class FakeService:
        async def list_official_visits(self, cursor=None):
            raise GuideShopTemporarilyUnavailableError("timeout upstream")

    _configure_static(FakeService())
    response = _list_visits(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "temporarily_unavailable"
    assert body["error"]["message"] == (
        "GuideShop временно недоступен. Попробуйте позже."
    )
    assert "timeout" not in response._body_text


def test_official_visits_generic_client_not_http_500(seeded_user):
    class FakeService:
        async def list_official_visits(self, cursor=None):
            raise GuideShopClientError("generic failure detail")

    _configure_static(FakeService())
    response = _list_visits(seeded_user)
    assert response.status == 503
    assert response_json(response)["error"]["code"] == "temporarily_unavailable"
    assert response.status != 500
    assert "generic failure" not in response._body_text


def test_official_visits_closes_client_after_success(seeded_user):
    client = TrackingInMemoryGuideShopClient(visits=(_official_visit(),))
    provider = RequestScopedGuideShopUIServiceProvider(
        lambda _user_id: GUIDE_OS_A,
        lambda _guide_os_id: client,
    )
    configure_miniapp_guideshop_provider(provider, reads_enabled=True)
    response = _list_visits(seeded_user)
    assert response.status == 200
    assert client.close_calls >= 1


def test_official_visit_detail_closes_client_on_not_found(seeded_user):
    client = TrackingInMemoryGuideShopClient(visits=())
    provider = RequestScopedGuideShopUIServiceProvider(
        lambda _user_id: GUIDE_OS_A,
        lambda _guide_os_id: client,
    )
    configure_miniapp_guideshop_provider(provider, reads_enabled=True)
    response = _get_visit(seeded_user, "visit-gone")
    assert response.status == 404
    assert client.close_calls >= 1


def test_official_visits_upstream_not_found_on_list(seeded_user):
    class FakeService:
        async def list_official_visits(self, cursor=None):
            raise GuideShopObjectNotFoundError("missing upstream object xyz")

    _configure_static(FakeService())
    response = _list_visits(seeded_user)
    body = response_json(response)
    assert response.status == 404
    assert body["error"]["code"] == "not_found"
    assert "xyz" not in response._body_text
