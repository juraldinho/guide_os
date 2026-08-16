import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import signal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp.test_utils import make_mocked_request
from multidict import CIMultiDict
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import services.guide_shop_link_provider as provider_module
from database.queries import create_guide_shop_link_request, get_guide_os_id, register_user
from services.guide_shop_inbound_auth import GuideShopInboundJWTVerifier
from services.guide_shop_link_exchange_service import (
    GuideShopLinkExchangeService,
    LinkExchangeError,
)
from services.guide_shop_link_provider import (
    MAX_REQUEST_BODY_BYTES,
    create_guide_shop_link_provider_app,
    start_guide_shop_link_provider,
)
from services.guide_shop_settings import GuideShopInboundJWTSettings
from services.guide_shop_settings import GuideShopLinkProviderSettings
from services.guide_shop_settings import GuideShopProductionLifecycleSettings
from services.guide_shop_settings import GuideShopProductionLifecycleSettingsError


NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
RAW_TOKEN = "synthetic-http-link-token-1234567890"
MEMBERSHIP = "cgm_b20af940"
KID = "link-key-2026"
PRODUCTION_KID = "synthetic-production-link-key"
PRODUCTION_KID_ALT = "synthetic-production-link-key-alt"


def run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture
def signing_key():
    return Ed25519PrivateKey.generate()


@pytest.fixture
def components(signing_key):
    pem = signing_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    settings = GuideShopInboundJWTSettings("test", {KID: pem})
    clock = lambda: NOW
    return (
        GuideShopInboundJWTVerifier(settings, clock=clock),
        GuideShopLinkExchangeService(clock=clock),
    )


def issue_link_request():
    register_user(101)
    create_guide_shop_link_request(
        guide_os_id=get_guide_os_id(101),
        token_hash=hashlib.sha256(RAW_TOKEN.encode()).hexdigest(),
        audience="guideshop-link",
        created_at=NOW.isoformat(),
        expires_at=(NOW + timedelta(minutes=10)).isoformat(),
    )


def bearer(signing_key, scope, jti, **changes):
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
    claims.update(changes)
    token = jwt.encode(
        claims,
        signing_key,
        algorithm="EdDSA",
        headers={"kid": KID, "typ": "guideshop-link-service+jwt"},
    )
    return {"Authorization": f"Bearer {token}"}


async def with_client(components, action):
    app = create_guide_shop_link_provider_app(*components)
    return await action(DirectClient(app))


class DirectResponse:
    def __init__(self, response):
        self.status = response.status
        self._body = response.body

    async def json(self):
        return json.loads(self._body)


class DirectClient:
    def __init__(self, app):
        self._app = app

    async def _request(self, method, path, *, json_body=None, data=None, headers=None):
        body = data
        request_headers = CIMultiDict(headers or {})
        if json_body is not None:
            body = json.dumps(json_body).encode()
            if "Content-Type" not in request_headers:
                request_headers["Content-Type"] = "application/json"
        if isinstance(body, str):
            body = body.encode()
        body = body or b""
        payload = AsyncMock()
        payload.readany = AsyncMock(side_effect=[body, b""])
        request = make_mocked_request(
            method,
            path,
            headers=request_headers,
            payload=payload,
            app=self._app,
            client_max_size=MAX_REQUEST_BODY_BYTES + 1,
        )
        match_info = await self._app.router.resolve(request)
        request._match_info = match_info
        return DirectResponse(await match_info.handler(request))

    async def post(self, path, *, json=None, data=None, headers=None):
        return await self._request(
            "POST", path, json_body=json, data=data, headers=headers
        )

    async def get(self, path, *, headers=None):
        return await self._request("GET", path, headers=headers)


def post_body(**changes):
    body = {
        "schema_version": "1.0.0",
        "raw_link_token": RAW_TOKEN,
        "audience": "guideshop-link",
        "guide_membership_ref": MEMBERSHIP,
    }
    body.update(changes)
    return body


def test_exact_routes_and_methods_only(components):
    app = create_guide_shop_link_provider_app(*components)
    routes = {(route.method, route.resource.canonical) for route in app.router.routes()}
    assert routes == {
        ("GET", "/health"),
        ("POST", "/integration/v1/link-exchanges"),
        ("GET", "/integration/v1/link-exchanges/{link_exchange_id}"),
        ("GET", "/integration/v1/link-exchanges/{link_exchange_id}/evidence"),
        ("POST", "/integration/v1/staging/link-tokens"),
        ("POST", "/integration/v1/staging/link-exchanges/{link_exchange_id}/confirm"),
        ("POST", "/integration/v1/staging/link-exchanges/{link_exchange_id}/revoke"),
    }


def test_valid_post_and_status_contract_mapping(signing_key, components):
    issue_link_request()

    async def exercise(client):
        response = await client.post(
            "/integration/v1/link-exchanges",
            json=post_body(),
            headers={
                **bearer(signing_key, "guideshop:link:exchange", "http-post-jti-000001"),
                "X-Correlation-ID": "req_http_post_0001",
            },
        )
        created = await response.json()
        assert response.status == 201
        assert set(created) == {
            "schema_version", "request_id", "link_exchange_id", "guide_os_id",
            "status", "token_expires_at", "exchange_expires_at", "created_at",
            "updated_at",
        }
        assert created["request_id"] == "req_http_post_0001"
        assert created["status"] == "awaiting_guide_confirmation"
        assert "raw_link_token" not in created and "evidence_ref" not in created
        assert all(created[name].endswith("Z") for name in (
            "token_expires_at", "exchange_expires_at", "created_at", "updated_at"
        ))
        response = await client.get(
            f"/integration/v1/link-exchanges/{created['link_exchange_id']}",
            headers=bearer(signing_key, "guideshop:link:status", "http-get-jti-0000001"),
        )
        status = await response.json()
        assert response.status == 200
        assert status["link_exchange_id"] == created["link_exchange_id"]
        assert "guide_membership_ref" not in status
        return created

    run(with_client(components, exercise))


def test_terminal_evidence_and_not_ready_mapping(signing_key, components):
    issue_link_request()
    service = components[1]

    async def exercise(client):
        created = await (await client.post(
            "/integration/v1/link-exchanges", json=post_body(),
            headers=bearer(signing_key, "guideshop:link:exchange", "evidence-post-jti-01")
        )).json()
        path = f"/integration/v1/link-exchanges/{created['link_exchange_id']}/evidence"
        response = await client.get(
            path, headers=bearer(signing_key, "guideshop:link:status", "evidence-get-jti-001")
        )
        assert response.status == 422
        assert await response.json() == {
            "schema_version": "1.0.0",
            "request_id": (await response.json())["request_id"],
            "code": "invalid_transition",
            "message": "Lifecycle evidence is not available for the current exchange status.",
        }
        service.transition(created["link_exchange_id"], MEMBERSHIP, "active")
        response = await client.get(
            path, headers=bearer(signing_key, "guideshop:link:status", "evidence-get-jti-002")
        )
        evidence = await response.json()
        assert response.status == 200
        assert set(evidence) == {
            "schema_version", "request_id", "link_exchange_id", "guide_os_id",
            "status", "evidence_ref", "occurred_at",
        }
        assert evidence["schema_version"] == "1.1.0"
        assert evidence["status"] == "active"
        assert evidence["occurred_at"].endswith("Z")

    run(with_client(components, exercise))


@pytest.mark.parametrize("terminal_status", ["active", "revoked", "conflict", "expired"])
def test_persisted_lifecycle_status_is_observed_over_http(
    signing_key, components, terminal_status
):
    issue_link_request()
    service = components[1]

    async def exercise(client):
        created = await (await client.post(
            "/integration/v1/link-exchanges",
            json=post_body(),
            headers=bearer(
                signing_key, "guideshop:link:exchange", f"observe-post-{terminal_status}"
            ),
        )).json()
        if terminal_status == "revoked":
            service.transition(created["link_exchange_id"], MEMBERSHIP, "active")
            service.transition(created["link_exchange_id"], MEMBERSHIP, "revoked")
        elif terminal_status == "expired":
            service._clock = lambda: NOW + timedelta(minutes=11)
        else:
            service.transition(
                created["link_exchange_id"], MEMBERSHIP, terminal_status
            )
        response = await client.get(
            f"/integration/v1/link-exchanges/{created['link_exchange_id']}",
            headers=bearer(
                signing_key, "guideshop:link:status", f"observe-get-{terminal_status}"
            ),
        )
        assert response.status == 200
        assert (await response.json())["status"] == terminal_status

    run(with_client(components, exercise))


@pytest.mark.parametrize("authorization", [None, "", "Basic value", "Bearer", "Bearer  value", "bearer value"])
def test_strict_authorization_does_not_parse_or_consume_body(components, authorization):
    issue_link_request()
    headers = {} if authorization is None else {"Authorization": authorization}

    async def exercise(client):
        response = await client.post(
            "/integration/v1/link-exchanges", data=b"not-json", headers=headers
        )
        assert response.status == 401

    run(with_client(components, exercise))
    from database.db import get_connection
    db = get_connection()
    row = db.execute("SELECT status FROM guide_shop_link_requests").fetchone()
    db.close()
    assert row["status"] == "issued"


def test_scope_and_replay_fail_before_raw_token_consumption(signing_key, components):
    issue_link_request()
    wrong = bearer(signing_key, "guideshop:link:status", "wrong-scope-jti-0001")

    async def exercise(client):
        first = await client.post("/integration/v1/link-exchanges", json=post_body(), headers=wrong)
        second = await client.post("/integration/v1/link-exchanges", json=post_body(), headers=wrong)
        assert first.status == second.status == 401

    run(with_client(components, exercise))
    from database.db import get_connection
    db = get_connection()
    assert db.execute("SELECT status FROM guide_shop_link_requests").fetchone()["status"] == "issued"
    db.close()


@pytest.mark.parametrize(
    "raw_body",
    [
        b"not-json",
        b'{"schema_version":"1.0.0","schema_version":"1.0.0"}',
        json.dumps(post_body(extra="value")).encode(),
        json.dumps(post_body(schema_version=1)).encode(),
        json.dumps(post_body(guide_membership_ref=123)).encode(),
    ],
)
def test_malformed_duplicate_unknown_and_coercible_requests_fail(signing_key, components, raw_body):
    issue_link_request()

    async def exercise(client):
        response = await client.post(
            "/integration/v1/link-exchanges", data=raw_body,
            headers={
                **bearer(signing_key, "guideshop:link:exchange", "invalid-body-jti-" + hashlib.sha256(raw_body).hexdigest()[:16]),
                "Content-Type": "application/json",
            },
        )
        assert response.status == 400

    run(with_client(components, exercise))


def test_content_type_body_limit_and_correlation_validation(signing_key, components):
    issue_link_request()

    async def exercise(client):
        response = await client.post(
            "/integration/v1/link-exchanges", data=json.dumps(post_body()),
            headers=bearer(signing_key, "guideshop:link:exchange", "content-type-jti-001")
        )
        assert response.status == 400
        response = await client.post(
            "/integration/v1/link-exchanges", data=b"x" * (MAX_REQUEST_BODY_BYTES + 1),
            headers={
                **bearer(signing_key, "guideshop:link:exchange", "oversize-body-jti-01"),
                "Content-Type": "application/json",
            },
        )
        assert response.status == 400
        response = await client.post(
            "/integration/v1/link-exchanges", json=post_body(),
            headers={
                **bearer(signing_key, "guideshop:link:exchange", "bad-correlation-jti"),
                "X-Correlation-ID": "bad",
            },
        )
        assert response.status == 400
        assert (await response.json())["request_id"] == "req_invalid_request"

    run(with_client(components, exercise))


def test_unknown_and_foreign_opaque_ids_are_indistinguishable(signing_key, components):
    async def exercise(client):
        results = []
        for index, value in enumerate(("lex_00000000000000000000000000000000", "foreign-value")):
            response = await client.get(
                f"/integration/v1/link-exchanges/{value}",
                headers=bearer(signing_key, "guideshop:link:status", f"unknown-get-jti-{index:04d}"),
            )
            results.append((response.status, (await response.json())["code"]))
        assert results == [(404, "not_found"), (404, "not_found")]

    run(with_client(components, exercise))


def test_unavailable_response_and_logs_do_not_expose_private_values(
    signing_key, components, monkeypatch, caplog
):
    sensitive_values = (
        RAW_TOKEN,
        MEMBERSHIP,
        "private-factory-detail",
        "lex_sensitive_object_01",
    )
    monkeypatch.setattr(
        components[1],
        "get_status_for_service",
        Mock(side_effect=LinkExchangeError("private-factory-detail")),
    )

    async def exercise(client):
        response = await client.get(
            "/integration/v1/link-exchanges/lex_sensitive_object_01",
            headers=bearer(
                signing_key, "guideshop:link:status", "redaction-get-jti-0001"
            ),
        )
        assert response.status == 503
        text = response._body.decode() + caplog.text
        assert all(value not in text for value in sensitive_values)

    run(with_client(components, exercise))


def test_raw_token_and_jwt_are_single_use_under_concurrency(signing_key, components):
    issue_link_request()

    async def exercise(client):
        shared_headers = bearer(signing_key, "guideshop:link:exchange", "shared-http-jti-0001")
        responses = await asyncio.gather(*[
            client.post("/integration/v1/link-exchanges", json=post_body(), headers=shared_headers)
            for _ in range(2)
        ])
        assert sorted(response.status for response in responses) == [201, 401]

    run(with_client(components, exercise))


def test_raw_token_is_single_use_with_distinct_jwts(signing_key, components):
    issue_link_request()

    async def exercise(client):
        responses = await asyncio.gather(
            client.post(
                "/integration/v1/link-exchanges",
                json=post_body(),
                headers=bearer(
                    signing_key, "guideshop:link:exchange", "raw-race-jti-000001"
                ),
            ),
            client.post(
                "/integration/v1/link-exchanges",
                json=post_body(),
                headers=bearer(
                    signing_key, "guideshop:link:exchange", "raw-race-jti-000002"
                ),
            ),
        )
        assert sorted(response.status for response in responses) == [201, 422]

    run(with_client(components, exercise))


def test_provider_settings_are_default_off_and_local_only():
    assert GuideShopLinkProviderSettings.from_env({}) == GuideShopLinkProviderSettings()
    assert GuideShopLinkProviderSettings.from_env({
        "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
        "GUIDESHOP_LINK_PROVIDER_HOST": "127.0.0.1",
        "GUIDESHOP_LINK_PROVIDER_PORT": "8082",
        "APP_ENV": "test",
    }) == GuideShopLinkProviderSettings(True, "127.0.0.1", 8082, "test")
    assert GuideShopLinkProviderSettings.from_env({
        "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
        "GUIDESHOP_LINK_PROVIDER_HOST": "::1",
        "GUIDESHOP_LINK_PROVIDER_PORT": "8081",
        "APP_ENV": "development",
    }) == GuideShopLinkProviderSettings(True, "::1", 8081, "development")
    for values in (
        {"GUIDESHOP_LINK_PROVIDER_ENABLED": "true", "APP_ENV": "production"},
        {"GUIDESHOP_LINK_PROVIDER_ENABLED": "true", "APP_ENV": "staging"},
        {
            "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
            "GUIDESHOP_LINK_PROVIDER_HOST": "0.0.0.0",
            "APP_ENV": "test",
        },
        {
            "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
            "APP_ENV": "unknown",
        },
    ):
        with pytest.raises(Exception):
            GuideShopLinkProviderSettings.from_env(values)


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


def test_staging_provider_settings_require_explicit_authorization_and_railway_port():
    assert GuideShopLinkProviderSettings.from_env(
        _staging_provider_env()
    ) == GuideShopLinkProviderSettings(True, "0.0.0.0", 8080, "staging")
    # Local provider port must not substitute for Railway PORT.
    local_port_only = _staging_provider_env(GUIDESHOP_LINK_PROVIDER_PORT="8081")
    del local_port_only["PORT"]
    with pytest.raises(Exception):
        GuideShopLinkProviderSettings.from_env(local_port_only)
    for values in (
        _staging_provider_env(GUIDESHOP_LINK_PROVIDER_STAGING_ENABLED="false"),
        {
            key: value
            for key, value in _staging_provider_env().items()
            if key != "GUIDESHOP_LINK_PROVIDER_STAGING_ENABLED"
        },
        _staging_provider_env(GUIDESHOP_LINK_PROVIDER_HOST="127.0.0.1"),
        _staging_provider_env(GUIDESHOP_LINK_PROVIDER_HOST="::1"),
        _staging_provider_env(GUIDESHOP_LINK_PROVIDER_HOST="10.0.0.1"),
        {
            key: value
            for key, value in _staging_provider_env().items()
            if key != "GUIDESHOP_LINK_PROVIDER_HOST"
        },
        {
            key: value
            for key, value in _staging_provider_env().items()
            if key != "PORT"
        },
        _staging_provider_env(PORT=""),
        _staging_provider_env(PORT="0"),
        _staging_provider_env(PORT="-1"),
        _staging_provider_env(PORT="8080.5"),
        _staging_provider_env(PORT="65536"),
        _staging_provider_env(PORT="not-a-port"),
        _staging_provider_env(APP_ENV="production"),
        _staging_provider_env(APP_ENV="development"),
    ):
        with pytest.raises(Exception):
            GuideShopLinkProviderSettings.from_env(values)


def test_production_provider_activation_always_fails_closed():
    for values in (
        {
            "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
            "APP_ENV": "production",
        },
        {
            "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
            "GUIDESHOP_LINK_PROVIDER_STAGING_ENABLED": "true",
            "GUIDESHOP_LINK_PROVIDER_HOST": "0.0.0.0",
            "PORT": "8080",
            "APP_ENV": "production",
        },
        {
            "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
            "GUIDESHOP_LINK_PROVIDER_HOST": "127.0.0.1",
            "GUIDESHOP_LINK_PROVIDER_PORT": "8081",
            "APP_ENV": "production",
        },
    ):
        with pytest.raises(Exception):
            GuideShopLinkProviderSettings.from_env(values)


def test_staging_composition_succeeds_only_with_complete_explicit_config(
    monkeypatch, signing_key
):
    pem = signing_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    runner = Mock()
    runner.setup = AsyncMock()
    runner.cleanup = AsyncMock()
    site = Mock()
    site.start = AsyncMock()
    monkeypatch.setattr(provider_module.web, "AppRunner", Mock(return_value=runner))
    monkeypatch.setattr(provider_module.web, "TCPSite", Mock(return_value=site))
    started = run(
        start_guide_shop_link_provider(
            {
                **_staging_provider_env(),
                "GUIDESHOP_LINK_JWT_PUBLIC_KEYS": json.dumps({KID: pem}),
            }
        )
    )
    assert started is runner
    site.start.assert_awaited_once_with()
    runner.cleanup.assert_not_called()


def test_staging_empty_public_key_allowlist_fails_before_runner(monkeypatch):
    runner = Mock(side_effect=AssertionError("runner created"))
    monkeypatch.setattr(provider_module.web, "AppRunner", runner)
    with pytest.raises(Exception):
        run(
            start_guide_shop_link_provider(
                {
                    **_staging_provider_env(),
                    "GUIDESHOP_LINK_JWT_PUBLIC_KEYS": "{}",
                }
            )
        )
    runner.assert_not_called()


def test_disabled_start_has_no_settings_verifier_or_runner(monkeypatch):
    inbound = Mock(side_effect=AssertionError("keys parsed"))
    runner = Mock(side_effect=AssertionError("runner created"))
    monkeypatch.setattr(provider_module.GuideShopInboundJWTSettings, "from_env", inbound)
    monkeypatch.setattr(provider_module.web, "AppRunner", runner)
    assert run(start_guide_shop_link_provider({})) is None
    assert run(
        start_guide_shop_link_provider(
            {
                "GUIDESHOP_LINK_PROVIDER_HOST": "0.0.0.0",
                "PORT": "bad",
                "GUIDESHOP_LINK_JWT_PUBLIC_KEYS": "{",
                "APP_ENV": "staging",
            }
        )
    ) is None
    inbound.assert_not_called()
    runner.assert_not_called()


def test_enabled_invalid_configuration_fails_before_runner(monkeypatch):
    runner = Mock(side_effect=AssertionError("runner created"))
    monkeypatch.setattr(provider_module.web, "AppRunner", runner)
    with pytest.raises(Exception):
        run(start_guide_shop_link_provider({"GUIDESHOP_LINK_PROVIDER_ENABLED": "true", "APP_ENV": "test"}))
    runner.assert_not_called()


def test_startup_failure_cleans_runner_once(monkeypatch, components):
    runner = Mock()
    runner.setup = AsyncMock(side_effect=RuntimeError("startup"))
    runner.cleanup = AsyncMock()
    monkeypatch.setattr(provider_module.web, "AppRunner", Mock(return_value=runner))
    monkeypatch.setattr(provider_module.GuideShopInboundJWTSettings, "from_env", Mock())
    monkeypatch.setattr(provider_module, "GuideShopInboundJWTVerifier", Mock(return_value=components[0]))
    with pytest.raises(RuntimeError):
        run(start_guide_shop_link_provider({
            "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
            "APP_ENV": "test",
        }))
    runner.cleanup.assert_awaited_once_with()


def test_successful_start_supports_exactly_once_shutdown(monkeypatch, components):
    runner = Mock()
    runner.setup = AsyncMock()
    runner.cleanup = AsyncMock()
    site = Mock()
    site.start = AsyncMock()
    monkeypatch.setattr(provider_module.web, "AppRunner", Mock(return_value=runner))
    monkeypatch.setattr(provider_module.web, "TCPSite", Mock(return_value=site))
    monkeypatch.setattr(provider_module.GuideShopInboundJWTSettings, "from_env", Mock())
    monkeypatch.setattr(
        provider_module, "GuideShopInboundJWTVerifier", Mock(return_value=components[0])
    )

    async def exercise():
        started = await start_guide_shop_link_provider({
            "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
            "APP_ENV": "test",
        })
        await started.cleanup()

    run(exercise())
    runner.cleanup.assert_awaited_once_with()


def test_cancelled_startup_cleans_runner_once(monkeypatch, components):
    runner = Mock()
    runner.setup = AsyncMock()
    runner.cleanup = AsyncMock()
    site = Mock()
    site.start = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(provider_module.web, "AppRunner", Mock(return_value=runner))
    monkeypatch.setattr(provider_module.web, "TCPSite", Mock(return_value=site))
    monkeypatch.setattr(provider_module.GuideShopInboundJWTSettings, "from_env", Mock())
    monkeypatch.setattr(
        provider_module, "GuideShopInboundJWTVerifier", Mock(return_value=components[0])
    )
    with pytest.raises(asyncio.CancelledError):
        run(start_guide_shop_link_provider({
            "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
            "APP_ENV": "test",
        }))
    runner.cleanup.assert_awaited_once_with()


def _public_pem(private_key):
    return private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def _generated_pem():
    return _public_pem(Ed25519PrivateKey.generate())


@pytest.fixture
def production_pem():
    return _generated_pem()


def _production_provider_env(**overrides):
    values = {
        "GUIDESHOP_LINK_PROVIDER_ENABLED": "true",
        "GUIDESHOP_LINK_PROVIDER_PRODUCTION_ENABLED": "true",
        "GUIDESHOP_LINK_PROVIDER_HOST": "0.0.0.0",
        "PORT": "8080",
        "APP_ENV": "production",
    }
    values.update(overrides)
    return values


def _without(values, *names):
    return {key: value for key, value in values.items() if key not in names}


def _production_runtime_env(pem, *, lifecycle_keys=None, link_keys=None, **overrides):
    keys = {PRODUCTION_KID: pem}
    values = _production_provider_env(
        GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED="true",
        GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS=json.dumps(
            keys if lifecycle_keys is None else lifecycle_keys
        ),
        GUIDESHOP_LINK_JWT_PUBLIC_KEYS=json.dumps(
            keys if link_keys is None else link_keys
        ),
    )
    values.update(overrides)
    return values


def _mock_runner(monkeypatch):
    runner = Mock()
    runner.setup = AsyncMock()
    runner.cleanup = AsyncMock()
    site = Mock()
    site.start = AsyncMock()
    monkeypatch.setattr(provider_module.web, "AppRunner", Mock(return_value=runner))
    monkeypatch.setattr(provider_module.web, "TCPSite", Mock(return_value=site))
    return runner, site


def test_production_provider_settings_require_explicit_production_authorization():
    assert GuideShopLinkProviderSettings.from_env(
        _production_provider_env()
    ) == GuideShopLinkProviderSettings(True, "0.0.0.0", 8080, "production")
    for values in (
        _without(
            _production_provider_env(), "GUIDESHOP_LINK_PROVIDER_PRODUCTION_ENABLED"
        ),
        _production_provider_env(GUIDESHOP_LINK_PROVIDER_PRODUCTION_ENABLED="false"),
        _production_provider_env(GUIDESHOP_LINK_PROVIDER_PRODUCTION_ENABLED=""),
        # Staging authorization must never open the production surface.
        {
            **_without(
                _production_provider_env(),
                "GUIDESHOP_LINK_PROVIDER_PRODUCTION_ENABLED",
            ),
            "GUIDESHOP_LINK_PROVIDER_STAGING_ENABLED": "true",
        },
        _production_provider_env(GUIDESHOP_LINK_PROVIDER_STAGING_ENABLED="true"),
        _production_provider_env(GUIDESHOP_LINK_PROVIDER_HOST="127.0.0.1"),
        _production_provider_env(GUIDESHOP_LINK_PROVIDER_HOST="::1"),
        _production_provider_env(GUIDESHOP_LINK_PROVIDER_HOST="10.0.0.1"),
        _production_provider_env(GUIDESHOP_LINK_PROVIDER_HOST=""),
        _without(_production_provider_env(), "GUIDESHOP_LINK_PROVIDER_HOST"),
        _without(_production_provider_env(), "PORT"),
        _production_provider_env(PORT=""),
        _production_provider_env(PORT="0"),
        _production_provider_env(PORT="-1"),
        _production_provider_env(PORT="8080.5"),
        _production_provider_env(PORT="65536"),
        _production_provider_env(PORT=" 8080"),
        _production_provider_env(PORT="not-a-port"),
        _without(_production_provider_env(), "APP_ENV"),
        _production_provider_env(APP_ENV="unknown"),
        _production_provider_env(APP_ENV="development"),
        _production_provider_env(APP_ENV="test"),
    ):
        with pytest.raises(Exception):
            GuideShopLinkProviderSettings.from_env(values)
    # The local Railway PORT alternative must not substitute for PORT.
    with pytest.raises(Exception):
        GuideShopLinkProviderSettings.from_env(
            _without(
                _production_provider_env(GUIDESHOP_LINK_PROVIDER_PORT="8081"), "PORT"
            )
        )


def test_production_authorization_does_not_satisfy_staging():
    with pytest.raises(Exception):
        GuideShopLinkProviderSettings.from_env(
            _production_provider_env(APP_ENV="staging")
        )
    assert GuideShopLinkProviderSettings.from_env(
        _staging_provider_env()
    ) == GuideShopLinkProviderSettings(True, "0.0.0.0", 8080, "staging")


def test_staging_provider_rejects_mixed_production_authorization_flag():
    with pytest.raises(Exception):
        GuideShopLinkProviderSettings.from_env(
            _staging_provider_env(GUIDESHOP_LINK_PROVIDER_PRODUCTION_ENABLED="true")
        )
    assert GuideShopLinkProviderSettings.from_env(
        _staging_provider_env()
    ) == GuideShopLinkProviderSettings(True, "0.0.0.0", 8080, "staging")
    assert GuideShopLinkProviderSettings.from_env(
        _staging_provider_env(GUIDESHOP_LINK_PROVIDER_PRODUCTION_ENABLED="false")
    ) == GuideShopLinkProviderSettings(True, "0.0.0.0", 8080, "staging")


def test_staging_runtime_rejects_enabled_production_lifecycle_before_runner(
    monkeypatch, production_pem
):
    runner = Mock(side_effect=AssertionError("runner created"))
    monkeypatch.setattr(provider_module.web, "AppRunner", runner)
    with pytest.raises(Exception):
        run(
            start_guide_shop_link_provider(
                {
                    **_staging_provider_env(),
                    "GUIDESHOP_LINK_JWT_PUBLIC_KEYS": json.dumps(
                        {PRODUCTION_KID: production_pem}
                    ),
                    "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
                    "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                        {PRODUCTION_KID: production_pem}
                    ),
                }
            )
        )
    runner.assert_not_called()


def test_production_lifecycle_settings_reject_staging_segment_kid(production_pem):
    with pytest.raises(GuideShopProductionLifecycleSettingsError):
        GuideShopProductionLifecycleSettings.from_env(
            {
                "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
                "APP_ENV": "production",
                "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                    {"guideshop-staging-link-key": production_pem}
                ),
            }
        )


def test_production_lifecycle_settings_default_off_and_read_only_their_variables(
    production_pem,
):
    assert GuideShopProductionLifecycleSettings.from_env({}) == (
        GuideShopProductionLifecycleSettings()
    )
    assert GuideShopProductionLifecycleSettings.from_env(
        {"GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "false"}
    ).enabled is False
    assert GuideShopProductionLifecycleSettings.from_env(
        {
            "GUIDESHOP_STAGING_LIFECYCLE_ENABLED": "true",
            "GUIDESHOP_STAGING_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                {PRODUCTION_KID: production_pem}
            ),
            "APP_ENV": "staging",
        }
    ).enabled is False
    settings = GuideShopProductionLifecycleSettings.from_env(
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "production",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                {PRODUCTION_KID: production_pem}
            ),
        }
    )
    assert settings.enabled is True
    assert settings.app_env == "production"
    assert dict(settings.public_keys) == {PRODUCTION_KID: production_pem}
    assert production_pem.strip().splitlines()[1] not in repr(settings)
    assert settings == GuideShopProductionLifecycleSettings(
        True, "production", {PRODUCTION_KID: _generated_pem()}
    )


def test_production_lifecycle_settings_fail_closed_on_environment_and_key_material(
    production_pem,
):
    other_pem = _generated_pem()
    non_ed25519_pem = _public_pem(ec.generate_private_key(ec.SECP256R1()))
    for values in (
        # Staging environment and staging-only variables cannot satisfy production.
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "staging",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                {PRODUCTION_KID: production_pem}
            ),
        },
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "test",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                {PRODUCTION_KID: production_pem}
            ),
        },
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                {PRODUCTION_KID: production_pem}
            ),
        },
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "production",
            "GUIDESHOP_STAGING_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                {PRODUCTION_KID: production_pem}
            ),
        },
        {"GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true", "APP_ENV": "production"},
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "production",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": "{}",
        },
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "production",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": "{",
        },
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "production",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": "[]",
        },
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "production",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": (
                '{"%s": "%s", "%s": "%s"}'
                % (
                    PRODUCTION_KID,
                    production_pem.replace("\n", "\\n"),
                    PRODUCTION_KID,
                    other_pem.replace("\n", "\\n"),
                )
            ),
        },
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "production",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                {"short": production_pem}
            ),
        },
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "production",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                {"Synthetic-Production-Link-Key": production_pem}
            ),
        },
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "production",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                {PRODUCTION_KID: "not-a-pem"}
            ),
        },
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "production",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                {PRODUCTION_KID: non_ed25519_pem}
            ),
        },
        {
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
            "APP_ENV": "production",
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                {PRODUCTION_KID: 1}
            ),
        },
    ):
        with pytest.raises(GuideShopProductionLifecycleSettingsError):
            GuideShopProductionLifecycleSettings.from_env(values)


def test_production_composition_requires_equivalent_lifecycle_and_link_key_allowlists(
    monkeypatch, production_pem
):
    runner, site = _mock_runner(monkeypatch)
    staging_verifier = Mock(side_effect=AssertionError("staging verifier created"))
    monkeypatch.setattr(
        provider_module, "GuideShopStagingLifecycleJWTVerifier", staging_verifier
    )
    captured = {}
    build_app = provider_module.create_guide_shop_link_provider_app

    def spy(*args, **kwargs):
        captured["kwargs"] = kwargs
        return build_app(*args, **kwargs)

    monkeypatch.setattr(provider_module, "create_guide_shop_link_provider_app", spy)
    started = run(
        start_guide_shop_link_provider(_production_runtime_env(production_pem))
    )
    assert started is runner
    site.start.assert_awaited_once_with()
    runner.cleanup.assert_not_called()
    assert provider_module.web.TCPSite.call_args.args[1:] == ("0.0.0.0", 8080)
    assert captured["kwargs"]["lifecycle_verifier"] is None
    staging_verifier.assert_not_called()


def test_production_composition_rejects_missing_mismatched_or_staging_key_material(
    monkeypatch, production_pem
):
    other_pem = _generated_pem()
    runner = Mock(side_effect=AssertionError("runner created"))
    monkeypatch.setattr(provider_module.web, "AppRunner", runner)
    for values in (
        _production_runtime_env(
            production_pem, GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED="false"
        ),
        _without(
            _production_runtime_env(production_pem),
            "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED",
        ),
        _production_runtime_env(
            production_pem, GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS="{}"
        ),
        _without(
            _production_runtime_env(production_pem),
            "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS",
        ),
        _production_runtime_env(production_pem, GUIDESHOP_LINK_JWT_PUBLIC_KEYS="{}"),
        _without(
            _production_runtime_env(production_pem), "GUIDESHOP_LINK_JWT_PUBLIC_KEYS"
        ),
        _production_runtime_env(production_pem, link_keys={PRODUCTION_KID: other_pem}),
        _production_runtime_env(
            production_pem, link_keys={PRODUCTION_KID_ALT: production_pem}
        ),
        _production_runtime_env(
            production_pem,
            link_keys={
                PRODUCTION_KID: production_pem,
                PRODUCTION_KID_ALT: other_pem,
            },
        ),
        _production_runtime_env(
            production_pem,
            lifecycle_keys={
                PRODUCTION_KID: production_pem,
                PRODUCTION_KID_ALT: other_pem,
            },
        ),
        # Staging lifecycle material must never authorize the production runtime.
        {
            **_without(
                _production_runtime_env(production_pem),
                "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED",
                "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS",
            ),
            "GUIDESHOP_STAGING_LIFECYCLE_ENABLED": "true",
            "GUIDESHOP_STAGING_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                {PRODUCTION_KID: production_pem}
            ),
        },
        _production_runtime_env(
            production_pem,
            GUIDESHOP_STAGING_LIFECYCLE_ENABLED="true",
            GUIDESHOP_STAGING_LIFECYCLE_JWT_PUBLIC_KEYS=json.dumps(
                {PRODUCTION_KID: production_pem}
            ),
        ),
        _production_runtime_env(
            production_pem, GUIDESHOP_LINK_PROVIDER_STAGING_ENABLED="true"
        ),
    ):
        with pytest.raises(Exception):
            run(start_guide_shop_link_provider(values))
    runner.assert_not_called()


def test_production_runtime_keeps_staging_lifecycle_routes_not_found(
    monkeypatch, production_pem
):
    _mock_runner(monkeypatch)
    bootstrap = Mock(side_effect=AssertionError("staging bootstrap called"))
    monkeypatch.setattr(provider_module, "ensure_staging_guide_user", bootstrap)
    captured = {}
    build_app = provider_module.create_guide_shop_link_provider_app

    def spy(*args, **kwargs):
        captured["app"] = build_app(*args, **kwargs)
        return captured["app"]

    monkeypatch.setattr(provider_module, "create_guide_shop_link_provider_app", spy)
    run(start_guide_shop_link_provider(_production_runtime_env(production_pem)))

    async def exercise(client):
        for path in (
            "/integration/v1/staging/link-tokens",
            "/integration/v1/staging/link-exchanges/lex_0000000000000001/confirm",
            "/integration/v1/staging/link-exchanges/lex_0000000000000001/revoke",
        ):
            response = await client.post(path)
            assert response.status == 404
            assert (await response.json())["code"] == "not_found"
        health = await client.get("/health")
        assert health.status == 200
        assert await health.json() == {"schema_version": "1.0.0", "status": "ok"}

    run(exercise(DirectClient(captured["app"])))
    bootstrap.assert_not_called()


def test_disabled_provider_ignores_production_settings_and_key_values(monkeypatch):
    lifecycle = Mock(side_effect=AssertionError("production lifecycle parsed"))
    inbound = Mock(side_effect=AssertionError("keys parsed"))
    runner = Mock(side_effect=AssertionError("runner created"))
    monkeypatch.setattr(
        provider_module.GuideShopProductionLifecycleSettings, "from_env", lifecycle
    )
    monkeypatch.setattr(provider_module.GuideShopInboundJWTSettings, "from_env", inbound)
    monkeypatch.setattr(provider_module.web, "AppRunner", runner)
    assert run(
        start_guide_shop_link_provider(
            {
                "GUIDESHOP_LINK_PROVIDER_PRODUCTION_ENABLED": "true",
                "GUIDESHOP_PRODUCTION_LIFECYCLE_ENABLED": "true",
                "GUIDESHOP_PRODUCTION_LIFECYCLE_JWT_PUBLIC_KEYS": "{",
                "GUIDESHOP_LINK_JWT_PUBLIC_KEYS": "{",
                "GUIDESHOP_LINK_PROVIDER_HOST": "0.0.0.0",
                "PORT": "bad",
                "APP_ENV": "production",
            }
        )
    ) is None
    lifecycle.assert_not_called()
    inbound.assert_not_called()
    runner.assert_not_called()


def test_invalid_production_configuration_stays_generic_in_errors_and_logs(
    monkeypatch, caplog, production_pem
):
    caplog.set_level(logging.DEBUG)
    other_pem = _generated_pem()
    runner = Mock(side_effect=AssertionError("runner created"))
    monkeypatch.setattr(provider_module.web, "AppRunner", runner)
    with pytest.raises(Exception) as raised:
        run(
            start_guide_shop_link_provider(
                _production_runtime_env(
                    production_pem, link_keys={PRODUCTION_KID: other_pem}
                )
            )
        )
    text = f"{raised.value}{raised.value!r}{caplog.text}"
    forbidden = [
        PRODUCTION_KID,
        "BEGIN PUBLIC KEY",
        "PRIVATE",
        "0.0.0.0",
        *production_pem.strip().splitlines()[1:-1],
        *other_pem.strip().splitlines()[1:-1],
    ]
    assert all(value not in text for value in forbidden)
    runner.assert_not_called()


def _bot_runtime(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "runtime-test-token")
    import bot as bot_module

    runtime = SimpleNamespace(
        module=bot_module,
        order=[],
        loops={},
        bot=Mock(),
        runner=Mock(),
        provider_start=AsyncMock(),
        polling=AsyncMock(),
        setup_commands=AsyncMock(),
        created_tasks=[],
    )
    runtime.runner.cleanup = AsyncMock()
    runtime.provider_start.return_value = runtime.runner

    async def start_provider(*args, **kwargs):
        runtime.order.append("start_provider")
        runtime.loops["provider"] = asyncio.get_running_loop()
        return await runtime.provider_start(*args, **kwargs)

    async def start_polling(*args, **kwargs):
        runtime.order.append("start_polling")
        runtime.loops["polling"] = asyncio.get_running_loop()
        return await runtime.polling(*args, **kwargs)

    def create_task(coro, *args, **kwargs):
        coro.close()
        task = Mock()
        runtime.created_tasks.append(task)
        return task

    dispatcher = Mock()
    dispatcher.start_polling = start_polling
    runtime.dispatcher = dispatcher

    monkeypatch.setattr(bot_module, "setup_logging", Mock())
    monkeypatch.setattr(bot_module, "configure_guide_shop_runtime", Mock())
    monkeypatch.setattr(bot_module, "Bot", Mock(return_value=runtime.bot))
    monkeypatch.setattr(bot_module, "setup_bot_commands", runtime.setup_commands)
    monkeypatch.setattr(
        bot_module, "init_db", Mock(side_effect=lambda: runtime.order.append("init_db"))
    )
    monkeypatch.setattr(bot_module, "send_daily_admin_report", AsyncMock())
    monkeypatch.setattr(bot_module, "send_tour_reminders", AsyncMock())
    monkeypatch.setattr(bot_module.asyncio, "create_task", create_task)
    monkeypatch.setattr(bot_module, "start_guide_shop_link_provider", start_provider)
    monkeypatch.setattr(bot_module, "Dispatcher", Mock(return_value=dispatcher))
    return runtime


def test_bot_runtime_disabled_provider_starts_polling_without_cleanup(monkeypatch):
    runtime = _bot_runtime(monkeypatch)
    runtime.provider_start.return_value = None

    run(runtime.module.main())

    assert runtime.order == ["init_db", "start_provider", "start_polling"]
    runtime.setup_commands.assert_awaited_once_with(runtime.bot)
    runtime.polling.assert_awaited_once_with(runtime.bot, skip_updates=True)
    runtime.runner.cleanup.assert_not_called()
    assert len(runtime.created_tasks) == 2


def test_bot_runtime_starts_provider_after_init_db_on_the_polling_loop(monkeypatch):
    runtime = _bot_runtime(monkeypatch)

    run(runtime.module.main())

    assert runtime.order == ["init_db", "start_provider", "start_polling"]
    assert runtime.loops["provider"] is runtime.loops["polling"]
    runtime.provider_start.assert_awaited_once_with()
    runtime.runner.cleanup.assert_awaited_once_with()


def test_bot_runtime_cleans_provider_once_on_polling_failure(monkeypatch):
    runtime = _bot_runtime(monkeypatch)
    runtime.polling.side_effect = RuntimeError("polling failed")

    with pytest.raises(RuntimeError, match="polling failed"):
        run(runtime.module.main())

    runtime.runner.cleanup.assert_awaited_once_with()


def test_bot_runtime_cleans_provider_once_on_polling_cancellation(monkeypatch):
    runtime = _bot_runtime(monkeypatch)
    runtime.polling.side_effect = asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        run(runtime.module.main())

    runtime.runner.cleanup.assert_awaited_once_with()


def test_bot_runtime_cleans_provider_once_when_polling_returns_after_signal(monkeypatch):
    runtime = _bot_runtime(monkeypatch)
    received = []
    previous = signal.getsignal(signal.SIGTERM)

    async def stopped_by_signal(*args, **kwargs):
        signal.raise_signal(signal.SIGTERM)
        await asyncio.sleep(0)
        return None

    runtime.polling.side_effect = stopped_by_signal
    signal.signal(signal.SIGTERM, lambda signum, frame: received.append(signum))
    try:
        run(runtime.module.main())
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert received == [signal.SIGTERM]
    assert runtime.order == ["init_db", "start_provider", "start_polling"]
    runtime.runner.cleanup.assert_awaited_once_with()


def test_bot_runtime_provider_startup_failure_prevents_polling_and_double_cleanup(
    monkeypatch,
):
    runtime = _bot_runtime(monkeypatch)
    runtime.provider_start.side_effect = RuntimeError("provider failed")

    with pytest.raises(RuntimeError, match="provider failed"):
        run(runtime.module.main())

    assert runtime.order == ["init_db", "start_provider"]
    runtime.polling.assert_not_awaited()
    runtime.runner.cleanup.assert_not_called()
    runtime.dispatcher.include_router.assert_not_called()
