"""Mini App GuideShop sales — withdrawn from Mini App by owner decision."""

from __future__ import annotations

import asyncio
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from database.queries import register_user
from services.miniapp_api_settings import MiniAppApiSettings
from web_api.app import create_miniapp_api_app
from web_api.auth import dev_session_token
from web_api.routes.guideshop_companies import configure_miniapp_guideshop_provider

API_USER = 887001
TEST_BOT_TOKEN = "7000000000:TEST_miniapp_synthetic_bot_token"


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


def test_official_sales_routes_not_registered():
    app = create_miniapp_api_app(_settings())
    routes = {(route.method, route.resource.canonical) for route in app.router.routes()}
    assert ("GET", "/app/v1/guideshop/sales") not in routes
    assert ("GET", "/app/v1/guideshop/sales/{saleId}") not in routes


def test_official_sales_endpoints_unavailable(seeded_user):
    for path in (
        "/app/v1/guideshop/sales",
        "/app/v1/guideshop/sales/sale-aaaa",
    ):
        response = api_request("GET", path, headers=_auth_headers(seeded_user))
        assert response.status in {404, 405}
        assert response.status != 500
