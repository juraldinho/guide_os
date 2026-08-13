import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from unittest.mock import AsyncMock, Mock

from aiohttp.test_utils import make_mocked_request
from multidict import CIMultiDict
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
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


NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
RAW_TOKEN = "synthetic-http-link-token-1234567890"
MEMBERSHIP = "cgm_b20af940"
KID = "link-key-2026"


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
        ("POST", "/integration/v1/link-exchanges"),
        ("GET", "/integration/v1/link-exchanges/{link_exchange_id}"),
        ("GET", "/integration/v1/link-exchanges/{link_exchange_id}/evidence"),
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
