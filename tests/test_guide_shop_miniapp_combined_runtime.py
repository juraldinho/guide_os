"""Regression tests for GuideShop link provider + Mini App API combined runtime (MA10)."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from multidict import CIMultiDict

import services.guide_shop_link_provider as provider_module
from database.queries import create_guide_shop_link_request, get_guide_os_id, register_user
from services.guide_shop_inbound_auth import GuideShopInboundJWTVerifier
from services.guide_shop_link_exchange_service import GuideShopLinkExchangeService
from services.guide_shop_link_provider import (
    MAX_REQUEST_BODY_BYTES as GUIDESHOP_MAX_REQUEST_BODY_BYTES,
    create_guide_shop_link_provider_app,
    start_guide_shop_link_provider,
)
from services.guide_shop_settings import GuideShopInboundJWTSettings
from services.miniapp_api_settings import MiniAppApiSettings
from web_api.app import (
    MAX_REQUEST_BODY_BYTES as MINIAPP_MAX_REQUEST_BODY_BYTES,
    MINIAPP_CORS_MIDDLEWARE_REGISTERED_KEY,
    create_miniapp_api_app,
    miniapp_cors_middleware,
    register_miniapp_api_on_app,
)

ROOT = Path(__file__).resolve().parents[1]
KID = "link-key-2026"
TEST_BOT_TOKEN = "7000000000:TEST_miniapp_synthetic_bot_token"
API_USER = 887001
PRODUCTION_FRONTEND_ORIGIN = "https://guide-os-miniapp.example"
RAW_TOKEN = "synthetic-http-link-token-1234567890"
MEMBERSHIP = "cgm_b20af940"
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def run(awaitable):
    return asyncio.run(awaitable)


def _staging_provider_env(**overrides):
    values = {
        "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
        "GUIDESHOP_LINK_PROVIDER_STAGING_ENABLED": "true",
        "GUIDESHOP_LINK_PROVIDER_HOST": "0.0.0.0",
        "PORT": "8080",
        "APP_ENV": "staging",
    }
    values.update(overrides)
    return values


@pytest.fixture
def signing_key():
    return Ed25519PrivateKey.generate()


@pytest.fixture
def public_pem(signing_key):
    return signing_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def _miniapp_settings(**overrides):
    values = {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8083,
        "dev_auth": True,
        "bot_token": TEST_BOT_TOKEN,
        "session_ttl_seconds": 3600,
        "initdata_max_age_seconds": 86400,
        "allowlist": frozenset(),
    }
    values.update(overrides)
    return MiniAppApiSettings(**values)


def _link_components(public_pem):
    settings = GuideShopInboundJWTSettings("staging", {KID: public_pem})
    clock = lambda: NOW
    return (
        GuideShopInboundJWTVerifier(settings, clock=clock),
        GuideShopLinkExchangeService(clock=clock),
    )


def _miniapp_enabled_env(**overrides):
    values = {
        "MINI_APP_API_ENABLED": "true",
        "MINI_APP_API_DEV_AUTH": "true",
        "MINI_APP_PUBLIC_URL": PRODUCTION_FRONTEND_ORIGIN,
        "BOT_TOKEN": TEST_BOT_TOKEN,
    }
    values.update(overrides)
    return values


def _combined_app(public_pem, miniapp_values):
    app = create_guide_shop_link_provider_app(*_link_components(public_pem))
    miniapp_settings = MiniAppApiSettings.from_env(miniapp_values)
    if miniapp_settings.enabled:
        register_miniapp_api_on_app(app, miniapp_settings)
    return app


def _health_routes(app):
    return [
        route
        for route in app.router.routes()
        if route.method == "GET" and route.resource.canonical == "/health"
    ]


def test_combined_runtime_disabled_preserves_link_provider_only(public_pem):
    app = _combined_app(
        public_pem,
        {"MINI_APP_API_ENABLED": "false"},
    )
    routes = {(route.method, route.resource.canonical) for route in app.router.routes()}
    assert ("GET", "/app/v1/profile") not in routes
    assert ("GET", "/health") in routes
    assert len(_health_routes(app)) == 1


def test_combined_runtime_disabled_link_health_payload(public_pem, monkeypatch):
    app = _combined_app(public_pem, {"MINI_APP_API_ENABLED": "false"})
    queried = Mock(side_effect=AssertionError("database queried"))
    monkeypatch.setattr("database.db.get_connection", queried)

    async def exercise():
        request = make_mocked_request("GET", "/health", app=app)
        match_info = await app.router.resolve(request)
        request._match_info = match_info
        response = await match_info.handler(request)
        assert response.status == 200
        body = json.loads(response.body)
        assert body == {"schema_version": "1.0.0", "status": "ok"}

    run(exercise())
    queried.assert_not_called()


def test_combined_runtime_enabled_mounts_miniapp_routes(public_pem):
    app = _combined_app(
        public_pem,
        {
            "MINI_APP_API_ENABLED": "true",
            "MINI_APP_API_DEV_AUTH": "true",
            "BOT_TOKEN": TEST_BOT_TOKEN,
        },
    )
    routes = {(route.method, route.resource.canonical) for route in app.router.routes()}
    assert ("GET", "/app/v1/profile") in routes
    assert ("POST", "/app/v1/session") in routes
    assert ("GET", "/health") in routes
    assert len(_health_routes(app)) == 1


def test_combined_runtime_no_duplicate_health_on_shared_app(public_pem):
    app = _combined_app(
        public_pem,
        {
            "MINI_APP_API_ENABLED": "true",
            "MINI_APP_API_DEV_AUTH": "true",
            "BOT_TOKEN": TEST_BOT_TOKEN,
        },
    )
    assert len(_health_routes(app)) == 1


def test_standalone_miniapp_api_keeps_own_health_route():
    app = create_miniapp_api_app(_miniapp_settings())
    health_routes = _health_routes(app)
    assert len(health_routes) == 1

    async def exercise():
        request = make_mocked_request("GET", "/health", app=app)
        match_info = await app.router.resolve(request)
        request._match_info = match_info
        response = await match_info.handler(request)
        assert response.status == 200
        assert json.loads(response.body) == {"status": "ok"}

    run(exercise())


def test_combined_runtime_disabled_start_without_bot_token(public_pem, monkeypatch):
    runner = Mock()
    runner.setup = AsyncMock()
    runner.cleanup = AsyncMock()
    site = Mock()
    site.start = AsyncMock()
    monkeypatch.setattr(provider_module.web, "AppRunner", Mock(return_value=runner))
    monkeypatch.setattr(provider_module.web, "TCPSite", Mock(return_value=site))
    values = _staging_provider_env(
        GUIDESHOP_LINK_JWT_PUBLIC_KEYS=json.dumps({KID: public_pem}),
        MINI_APP_API_ENABLED="false",
    )
    started = run(
        start_guide_shop_link_provider(
            values,
            attach_miniapp_api=True,
        )
    )
    assert started is runner
    site.start.assert_awaited_once_with()


def test_combined_runtime_enabled_without_bot_token_fails_closed(public_pem, tmp_path):
    env = os.environ.copy()
    env.pop("BOT_TOKEN", None)
    env["PYTHONPATH"] = str(ROOT)
    values = _staging_provider_env(
        GUIDESHOP_LINK_JWT_PUBLIC_KEYS=json.dumps({KID: public_pem}),
        MINI_APP_API_ENABLED="true",
        MINI_APP_API_DEV_AUTH="true",
        DATABASE_PATH=str(tmp_path / "combined.db"),
    )
    script = (
        "import asyncio, json, os, sys\n"
        f"values = {repr(values)}\n"
        "from database.db import init_db\n"
        "init_db()\n"
        "from services.guide_shop_link_provider import start_guide_shop_link_provider\n"
        "asyncio.run(start_guide_shop_link_provider(values, attach_miniapp_api=True))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "BOT_TOKEN" in completed.stderr or "ValueError" in completed.stderr


def test_link_api_entrypoint_import_without_bot_token_when_miniapp_disabled():
    env = os.environ.copy()
    env.pop("BOT_TOKEN", None)
    env["PYTHONPATH"] = str(ROOT)
    script = (
        "import os, sys\n"
        "assert 'BOT_TOKEN' not in os.environ\n"
        "import guide_shop_link_api\n"
        "assert 'bot' not in sys.modules\n"
        "assert 'config' not in sys.modules\n"
        "print('ok')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_combined_runtime_enabled_start_single_listener(public_pem, monkeypatch):
    runner = Mock()
    runner.setup = AsyncMock()
    runner.cleanup = AsyncMock()
    site = Mock()
    site.start = AsyncMock()
    monkeypatch.setattr(provider_module.web, "AppRunner", Mock(return_value=runner))
    monkeypatch.setattr(provider_module.web, "TCPSite", Mock(return_value=site))
    values = _staging_provider_env(
        GUIDESHOP_LINK_JWT_PUBLIC_KEYS=json.dumps({KID: public_pem}),
        **_miniapp_enabled_env(),
    )
    started = run(
        start_guide_shop_link_provider(
            values,
            attach_miniapp_api=True,
        )
    )
    assert started is runner
    site.start.assert_awaited_once_with()


def test_combined_runtime_registers_cors_middleware_once(public_pem):
    app = _combined_app(public_pem, _miniapp_enabled_env())
    assert app.get(MINIAPP_CORS_MIDDLEWARE_REGISTERED_KEY) is True
    assert app.middlewares.count(miniapp_cors_middleware) == 1
    miniapp_settings = MiniAppApiSettings.from_env(_miniapp_enabled_env())
    register_miniapp_api_on_app(app, miniapp_settings)
    assert app.middlewares.count(miniapp_cors_middleware) == 1


def test_combined_runtime_shared_app_client_max_size_is_miniapp_limit(public_pem):
    app = _combined_app(public_pem, _miniapp_enabled_env())
    assert app._client_max_size == MINIAPP_MAX_REQUEST_BODY_BYTES
    assert app._client_max_size > GUIDESHOP_MAX_REQUEST_BODY_BYTES


async def _combined_client_request(app, method, path, **kwargs):
    client = TestClient(TestServer(app))
    async with client:
        response = await client.request(method, path, **kwargs)
        response._body_text = await response.text()
        return response


def test_combined_runtime_cors_allows_configured_frontend_origin(public_pem):
    app = _combined_app(public_pem, _miniapp_enabled_env())
    response = run(
        _combined_client_request(
            app,
            "OPTIONS",
            "/app/v1/session",
            headers={"Origin": PRODUCTION_FRONTEND_ORIGIN},
        )
    )
    assert response.status == 200
    assert response.headers.get("Access-Control-Allow-Origin") == PRODUCTION_FRONTEND_ORIGIN


def test_combined_runtime_cors_rejects_disallowed_origin(public_pem):
    app = _combined_app(public_pem, _miniapp_enabled_env())
    response = run(
        _combined_client_request(
            app,
            "OPTIONS",
            "/app/v1/session",
            headers={"Origin": "https://evil.example"},
        )
    )
    assert response.status == 403
    assert "Access-Control-Allow-Origin" not in response.headers


def test_combined_runtime_miniapp_auth_required_with_allowed_origin(public_pem):
    app = _combined_app(public_pem, _miniapp_enabled_env())
    response = run(
        _combined_client_request(
            app,
            "GET",
            "/app/v1/profile",
            headers={"Origin": PRODUCTION_FRONTEND_ORIGIN},
        )
    )
    body = json.loads(response._body_text)
    assert response.status == 401
    assert body["error"]["code"] == "auth_required"


def test_combined_runtime_miniapp_accepts_body_above_guide_shop_limit(public_pem):
    register_user(API_USER)
    app = _combined_app(public_pem, _miniapp_enabled_env())
    oversized_payload = {
        "dev_user_id": API_USER,
        "padding": "x" * 5000,
    }
    response = run(
        _combined_client_request(
            app,
            "POST",
            "/app/v1/session",
            json=oversized_payload,
            headers={"Content-Type": "application/json"},
        )
    )
    assert response.status == 200


def _guide_shop_bearer(signing_key, scope, jti):
    issued_at = int(NOW.timestamp())
    claims = {
        "iss": "guideshop-integration",
        "aud": "guide-os-integration",
        "sub": "guideshop:link-service",
        "scope": scope,
        "iat": issued_at,
        "exp": issued_at + 60,
        "jti": jti,
    }
    token = jwt.encode(
        claims,
        signing_key,
        algorithm="EdDSA",
        headers={"kid": KID, "typ": "guideshop-link-service+jwt"},
    )
    return {"Authorization": f"Bearer {token}"}


def test_combined_runtime_guide_shop_handler_rejects_oversize_body(public_pem, signing_key):
    register_user(101)
    create_guide_shop_link_request(
        guide_os_id=get_guide_os_id(101),
        token_hash=hashlib.sha256(RAW_TOKEN.encode()).hexdigest(),
        audience="guideshop-link",
        created_at=NOW.isoformat(),
        expires_at=(NOW + timedelta(minutes=10)).isoformat(),
    )
    app = _combined_app(public_pem, _miniapp_enabled_env())

    async def exercise():
        body = b"x" * (GUIDESHOP_MAX_REQUEST_BODY_BYTES + 1)
        headers = CIMultiDict(
            {
                **_guide_shop_bearer(signing_key, "guideshop:link:exchange", "oversize-body-jti-01"),
                "Content-Type": "application/json",
            }
        )
        payload = AsyncMock()
        payload.readany = AsyncMock(side_effect=[body, b""])
        request = make_mocked_request(
            "POST",
            "/integration/v1/link-exchanges",
            headers=headers,
            payload=payload,
            app=app,
            client_max_size=MINIAPP_MAX_REQUEST_BODY_BYTES,
        )
        match_info = await app.router.resolve(request)
        request._match_info = match_info
        response = await match_info.handler(request)
        assert response.status == 400

    run(exercise())
