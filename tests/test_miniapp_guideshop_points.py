"""GSMA7C — Mini App official GuideShop points summary composition API."""

from __future__ import annotations

import asyncio
import json

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
from services.guide_shop_contracts import (
    CompanyDTO,
    PointsAccrualDTO,
    PointsSummaryDTO,
)
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
POINTS_SUMMARY_FIELDS = {
    "unit",
    "pendingTotal",
    "creditedTotal",
    "companies",
}
COMPANY_SUMMARY_FIELDS = {
    "companyId",
    "displayName",
    "pendingTotal",
    "creditedTotal",
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


def _company(company_id="company-1", name="Silk Road"):
    return CompanyDTO.model_validate(
        {
            "company_id": company_id,
            "display_name": name,
            "status": "active",
        }
    )


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


def _summary_dto(
    *,
    pending="3.50",
    credited="1.25",
    companies=None,
):
    if companies is None:
        companies = [
            {
                "company_id": "cmp_silk01",
                "display_name": "Silk Road",
                "pending_total": pending,
                "credited_total": credited,
            }
        ]
    return PointsSummaryDTO.model_validate(
        {
            "schema_version": "1.0.0",
            "request_id": "req_points01",
            "unit": "PTS",
            "pending_total": pending,
            "credited_total": credited,
            "companies": companies,
        }
    )


def _configure_static(service, *, reads_enabled=True):
    configure_miniapp_guideshop_provider(
        StaticGuideShopUIServiceProvider(service),
        reads_enabled=reads_enabled,
    )


def _get_summary(user_id=API_USER):
    return api_request(
        "GET",
        "/app/v1/guideshop/points/summary",
        headers=_auth_headers(user_id),
    )


class TrackingInMemoryGuideShopClient(InMemoryGuideShopClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


def test_official_points_summary_route_registered_once():
    app = create_miniapp_api_app(_settings())
    routes = [
        (route.method, route.resource.canonical)
        for route in app.router.routes()
    ]
    assert routes.count(("GET", "/app/v1/guideshop/points/summary")) == 1
    assert ("POST", "/app/v1/guideshop/points/summary") not in routes
    assert ("PUT", "/app/v1/guideshop/points/summary") not in routes
    assert ("PATCH", "/app/v1/guideshop/points/summary") not in routes
    assert ("DELETE", "/app/v1/guideshop/points/summary") not in routes
    assert ("GET", "/app/v1/guideshop/history") not in routes
    assert ("GET", "/app/v1/guideshop/sales") not in routes


def test_official_points_summary_success_field_mapping(seeded_user):
    company = _company(company_id="cmp_silk01", name="Silk Road")
    points = (
        _points("points-pend", company_id="cmp_silk01", amount="3.50", status="pending"),
        _points(
            "points-cred",
            company_id="cmp_silk01",
            visit_id="visit-02",
            amount="1.25",
            status="credited",
        ),
    )
    _configure_static(
        GuideShopUIService(
            InMemoryGuideShopClient(companies=(company,), points=points)
        )
    )
    response = _get_summary(seeded_user)
    body = response_json(response)
    assert response.status == 200
    mapped = body["data"]
    assert set(mapped.keys()) == POINTS_SUMMARY_FIELDS
    assert mapped["unit"] == "PTS"
    assert mapped["pendingTotal"] == "3.50"
    assert mapped["creditedTotal"] == "1.25"
    assert len(mapped["companies"]) == 1
    row = mapped["companies"][0]
    assert set(row.keys()) == COMPANY_SUMMARY_FIELDS
    assert row == {
        "companyId": "cmp_silk01",
        "displayName": "Silk Road",
        "pendingTotal": "3.50",
        "creditedTotal": "1.25",
    }
    dumped = response._body_text
    assert "schema_version" not in dumped
    assert "pending_total" not in dumped
    assert "company_id" not in dumped
    assert "display_name" not in dumped
    assert "credited_total" not in dumped


def test_official_points_summary_empty_companies(seeded_user):
    class FakeService:
        async def get_official_points_summary(self):
            return _summary_dto(pending="0.00", credited="0.00", companies=[])

    _configure_static(FakeService())
    response = _get_summary(seeded_user)
    body = response_json(response)
    assert response.status == 200
    assert body["data"] == {
        "unit": "PTS",
        "pendingTotal": "0.00",
        "creditedTotal": "0.00",
        "companies": [],
    }


def test_official_points_summary_mutations_unavailable(seeded_user):
    calls = []

    class CountingService:
        async def get_official_points_summary(self):
            calls.append("summary")
            return _summary_dto(pending="0.00", credited="0.00", companies=[])

    _configure_static(CountingService())
    mutations = [
        ("POST", "/app/v1/guideshop/points/summary", {"json": {}}),
        ("PUT", "/app/v1/guideshop/points/summary", {"json": {}}),
        ("PATCH", "/app/v1/guideshop/points/summary", {"json": {}}),
        ("DELETE", "/app/v1/guideshop/points/summary", {}),
    ]
    for method, path, kwargs in mutations:
        response = api_request(method, path, headers=_auth_headers(seeded_user), **kwargs)
        assert response.status in {404, 405}
        assert response.status != 500
    assert calls == []


def test_official_points_summary_auth_required():
    response = api_request("GET", "/app/v1/guideshop/points/summary")
    body = response_json(response)
    assert response.status == 401
    assert body["error"]["code"] == "auth_required"


def test_official_points_summary_provider_absent_is_integration_disabled(seeded_user):
    response = _get_summary(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "integration_disabled"
    assert body["error"]["message"] == "Раздел GuideShop временно отключён."


def test_official_points_summary_disabled_client(seeded_user):
    _configure_static(GuideShopUIService(DisabledGuideShopClient()))
    response = _get_summary(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "integration_disabled"


def test_official_points_summary_reads_disabled_flag(seeded_user):
    _configure_static(
        GuideShopUIService(InMemoryGuideShopClient()),
        reads_enabled=False,
    )
    response = _get_summary(seeded_user)
    assert response.status == 503
    assert response_json(response)["error"]["code"] == "integration_disabled"


def test_official_points_summary_missing_identity_is_access_denied(seeded_user):
    provider = RequestScopedGuideShopUIServiceProvider(
        lambda _user_id: None,
        lambda _guide_os_id: TrackingInMemoryGuideShopClient(),
    )
    configure_miniapp_guideshop_provider(provider, reads_enabled=True)
    response = _get_summary(seeded_user)
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
def test_official_points_summary_auth_and_access_denied(seeded_user, error):
    class FakeService:
        async def get_official_points_summary(self):
            raise error

    _configure_static(FakeService())
    response = _get_summary(seeded_user)
    body = response_json(response)
    assert response.status == 403
    assert body["error"]["code"] == "access_denied"
    assert "secret" not in response._body_text


def test_official_points_summary_temporary_outage(seeded_user):
    class FakeService:
        async def get_official_points_summary(self):
            raise GuideShopTemporarilyUnavailableError("timeout upstream")

    _configure_static(FakeService())
    response = _get_summary(seeded_user)
    body = response_json(response)
    assert response.status == 503
    assert body["error"]["code"] == "temporarily_unavailable"
    assert body["error"]["message"] == (
        "GuideShop временно недоступен. Попробуйте позже."
    )
    assert "timeout" not in response._body_text


def test_official_points_summary_generic_client_not_http_500(seeded_user):
    class FakeService:
        async def get_official_points_summary(self):
            raise GuideShopClientError("generic failure detail")

    _configure_static(FakeService())
    response = _get_summary(seeded_user)
    assert response.status == 503
    assert response_json(response)["error"]["code"] == "temporarily_unavailable"
    assert response.status != 500
    assert "generic failure" not in response._body_text


def test_official_points_summary_closes_client_after_success(seeded_user):
    client = TrackingInMemoryGuideShopClient()
    provider = RequestScopedGuideShopUIServiceProvider(
        lambda _user_id: GUIDE_OS_A,
        lambda _guide_os_id: client,
    )
    configure_miniapp_guideshop_provider(provider, reads_enabled=True)
    response = _get_summary(seeded_user)
    assert response.status == 200
    assert client.close_calls >= 1
