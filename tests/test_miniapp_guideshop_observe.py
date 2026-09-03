"""GSMA8 — sanitized Mini App GuideShop observability."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from aiohttp.test_utils import TestClient, TestServer

from database.queries import register_user
from services.guide_shop_client import GuideShopTemporarilyUnavailableError
from services.guide_shop_runtime import StaticGuideShopUIServiceProvider
from services.miniapp_api_settings import MiniAppApiSettings
from web_api.app import create_miniapp_api_app
from web_api.auth import dev_session_token
from web_api.routes.guideshop_companies import configure_miniapp_guideshop_provider
from web_api.routes.guideshop_observe import (
    MiniAppGuideShopSpan,
    outcome_from_guideshop_exc,
)

API_USER = 887801
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


def _auth_headers(user_id=API_USER):
    return {
        "Authorization": f"Bearer {dev_session_token(user_id)}",
        "Content-Type": "application/json",
    }


async def _with_client(coro):
    app = create_miniapp_api_app(_settings())
    client = TestClient(TestServer(app))
    async with client:
        response = await coro(client)
        response._body_text = await response.text()
        return response


def api_request(method, path, **kwargs):
    async def _call(client):
        return await client.request(method, path, **kwargs)

    return run(_with_client(_call))


@pytest.fixture(autouse=True)
def _reset_provider():
    configure_miniapp_guideshop_provider(None, reads_enabled=False)
    yield
    configure_miniapp_guideshop_provider(None, reads_enabled=False)


@pytest.fixture
def seeded_user():
    register_user(API_USER)
    return API_USER


def test_outcome_mapping_is_allowlisted_only():
    assert (
        outcome_from_guideshop_exc(GuideShopTemporarilyUnavailableError("x"))
        == "unavailable"
    )
    span = MiniAppGuideShopSpan("companies.list")
    span.set_outcome("not_a_real_outcome")
    assert span.outcome == "unavailable"


def test_companies_list_logs_sanitized_outcome(seeded_user, caplog):
    class FakeService:
        async def list_official_companies(self):
            raise GuideShopTemporarilyUnavailableError("upstream detail must not log")

    configure_miniapp_guideshop_provider(
        StaticGuideShopUIServiceProvider(FakeService()),
        reads_enabled=True,
    )
    with caplog.at_level(logging.INFO, logger="web_api.guideshop"):
        response = api_request(
            "GET",
            "/app/v1/guideshop/companies",
            headers=_auth_headers(seeded_user),
        )
    assert response.status == 503
    body = json.loads(response._body_text)
    assert body["error"]["code"] == "temporarily_unavailable"
    records = [r.getMessage() for r in caplog.records if "miniapp_guideshop" in r.getMessage()]
    assert len(records) == 1
    message = records[0]
    assert "route=companies.list" in message
    assert "outcome=unavailable" in message
    assert "latency_ms=" in message
    assert "upstream detail" not in message
    assert str(seeded_user) not in message
    assert "Bearer" not in message
    assert "opaque" not in message.lower()
