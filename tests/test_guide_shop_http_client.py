import asyncio
import inspect
import json
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
from dataclasses import FrozenInstanceError

import services.guide_shop_client as client_module
from services.guide_shop_client import (
    GuideShopAccessDeniedError,
    GuideShopAccessTokenProvider,
    GuideShopAuthenticationError,
    GuideShopClient,
    GuideShopClientError,
    GuideShopObjectNotFoundError,
    GuideShopTemporarilyUnavailableError,
    HTTPGuideShopClient,
)
from services.guide_shop_contracts import (
    APIDetailResponseDTO,
    APIListResponseDTO,
    CompanyDTO,
    PointsAccrualDTO,
    PointsPayoutDTO,
    PointsStatus,
    SaleDTO,
    VisitDTO,
)
from services.guide_shop_settings import (
    GuideShopHTTPSettings,
    GuideShopSettingsError,
)


UTC = "2026-08-07T12:00:00Z"


def run(awaitable):
    return asyncio.run(awaitable)


def settings(**overrides):
    values = {
        "APP_ENV": "test",
        "GUIDESHOP_API_BASE_URL": "https://api.guideshop.example",
        "GUIDESHOP_API_TIMEOUT_SECONDS": "5",
        "GUIDESHOP_API_MAX_RETRIES": "1",
        "GUIDESHOP_API_MAX_RETRY_AFTER_SECONDS": "3",
    }
    values.update(overrides)
    return GuideShopHTTPSettings.from_env(values)


def company_payload():
    return {"company_id": "company-1", "display_name": "Company", "status": "active"}


def visit_payload():
    return {
        "visit_id": "visit-01",
        "company_id": "company-1",
        "guide_membership_id": "gmem-0001",
        "visit_at": UTC,
        "status": "active",
        "tourist_count": 2,
        "customer_payment_status": "unpaid",
        "created_at": UTC,
        "updated_at": UTC,
    }


def sale_payload():
    return {
        "sale_id": "sale-001",
        "visit_id": "visit-01",
        "company_id": "company-1",
        "amount": "10.00",
        "currency": "USD",
        "status": "active",
        "payment_method": "cash",
        "category_id": "category1",
        "category_name": "Textiles",
        "created_at": UTC,
        "updated_at": UTC,
    }


def points_payload():
    return {
        "points_accrual_id": "points-01",
        "company_id": "company-1",
        "visit_id": "visit-01",
        "amount": "2.00",
        "unit": "PTS",
        "status": "pending",
        "calculated_at": UTC,
        "updated_at": UTC,
    }


def payout_payload():
    return {
        "payout_id": "payout-01",
        "points_accrual_id": "points-01",
        "company_id": "company-1",
        "visit_id": "visit-01",
        "amount": "2.00",
        "unit": "PTS",
        "paid_at": UTC,
        "created_at": UTC,
    }


def list_envelope(item):
    return {
        "schema_version": "1.0.0",
        "request_id": "request-1",
        "data": [item],
        "page": {"next_cursor": None, "has_more": False},
    }


def detail_envelope(item):
    return {
        "schema_version": "1.0.0",
        "request_id": "request-1",
        "data": item,
    }


class FakeContent:
    def __init__(self, body):
        self._body = body
        self._position = 0
        self.read_calls = []
        self.total_returned = 0

    async def read(self, size):
        self.read_calls.append(size)
        chunk = self._body[self._position : self._position + size]
        self._position += len(chunk)
        self.total_returned += len(chunk)
        return chunk


_DECLARED_LENGTH = object()


class FakeResponse:
    def __init__(
        self,
        status=200,
        payload=None,
        *,
        body=None,
        headers=None,
        content_length=_DECLARED_LENGTH,
    ):
        self.status = status
        self.headers = headers or {}
        self._body = (
            json.dumps(payload).encode("utf-8") if body is None else body
        )
        self.content_length = (
            len(self._body)
            if content_length is _DECLARED_LENGTH
            else content_length
        )
        self.content = FakeContent(self._body)
        self.release = Mock()


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.close = AsyncMock()

    async def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class TokenProvider:
    def __init__(self, token="service-token"):
        self.token = token
        self.identities = []

    async def get_access_token(self, guide_os_id):
        self.identities.append(guide_os_id)
        return self.token


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_settings_require_https_in_staging_and_production(app_env):
    with pytest.raises(GuideShopSettingsError):
        GuideShopHTTPSettings.from_env(
            {
                "APP_ENV": app_env,
                "GUIDESHOP_API_BASE_URL": "http://api.example.com",
            }
        )
    assert GuideShopHTTPSettings.from_env(
        {
            "APP_ENV": app_env,
            "GUIDESHOP_API_BASE_URL": "https://api.example.com/",
        }
    ).base_url == "https://api.example.com"


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_settings_allow_http_only_in_development_and_test(app_env):
    parsed = GuideShopHTTPSettings.from_env(
        {
            "APP_ENV": app_env,
            "GUIDESHOP_API_BASE_URL": "http://localhost:8080",
        }
    )
    assert parsed.base_url == "http://localhost:8080"


@pytest.mark.parametrize(
    "base_url",
    [
        None,
        "",
        " https://api.example.com",
        "ftp://api.example.com",
        "https://user:pass@api.example.com",
        "https://api.example.com/path",
        "https://api.example.com?secret=value",
        "https://api.example.com#fragment",
        "https://api example.com",
        "https://пример.рф",
    ],
)
def test_settings_reject_missing_empty_and_unsafe_base_urls(base_url):
    values = {"APP_ENV": "test"}
    if base_url is not None:
        values["GUIDESHOP_API_BASE_URL"] = base_url
    with pytest.raises(GuideShopSettingsError):
        GuideShopHTTPSettings.from_env(values)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GUIDESHOP_API_TIMEOUT_SECONDS", "0"),
        ("GUIDESHOP_API_TIMEOUT_SECONDS", "-1"),
        ("GUIDESHOP_API_TIMEOUT_SECONDS", "nan"),
        ("GUIDESHOP_API_TIMEOUT_SECONDS", "inf"),
        ("GUIDESHOP_API_TIMEOUT_SECONDS", "61"),
        ("GUIDESHOP_API_MAX_RETRIES", "0"),
        ("GUIDESHOP_API_MAX_RETRIES", "1.5"),
        ("GUIDESHOP_API_MAX_RETRIES", "6"),
        ("GUIDESHOP_API_MAX_RETRY_AFTER_SECONDS", "0"),
        ("GUIDESHOP_API_MAX_RETRY_AFTER_SECONDS", "61"),
    ],
)
def test_settings_reject_malformed_nonfinite_and_out_of_bounds_numbers(name, value):
    values = {
        "APP_ENV": "test",
        "GUIDESHOP_API_BASE_URL": "https://api.example.com",
        name: value,
    }
    with pytest.raises(GuideShopSettingsError):
        GuideShopHTTPSettings.from_env(values)


def test_settings_are_immutable_bounded_and_store_no_secret():
    parsed = settings(SERVICE_TOKEN="private-token")
    assert parsed.request_timeout_seconds == 5
    assert parsed.max_retries == 1
    assert parsed.max_retry_after_seconds == 3
    assert "private-token" not in repr(parsed)
    with pytest.raises(Exception):
        parsed.base_url = "https://changed.example"


@pytest.mark.parametrize("app_env", ["", "unknown", "qa", None, 123])
def test_direct_settings_reject_invalid_environment(app_env):
    with pytest.raises(GuideShopSettingsError):
        GuideShopHTTPSettings(
            base_url="https://api.example.com",
            app_env=app_env,
        )


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_direct_settings_cannot_bypass_https_enforcement(app_env):
    with pytest.raises(GuideShopSettingsError):
        GuideShopHTTPSettings(
            base_url="http://api.example.com",
            app_env=app_env,
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        " https://api.example.com",
        "https://user:pass@api.example.com",
        "https://api.example.com/path",
        "https://api.example.com?query=value",
        "https://api.example.com#fragment",
        "https://api.example.com:bad",
    ],
)
def test_direct_settings_cannot_bypass_url_validation(base_url):
    with pytest.raises(GuideShopSettingsError):
        GuideShopHTTPSettings(base_url=base_url, app_env="test")


@pytest.mark.parametrize("timeout", [True, False, 0, -1, 61, float("nan"), "5"])
def test_direct_settings_cannot_bypass_timeout_bounds(timeout):
    with pytest.raises(GuideShopSettingsError):
        GuideShopHTTPSettings(
            base_url="https://api.example.com",
            app_env="test",
            request_timeout_seconds=timeout,
        )


@pytest.mark.parametrize("retries", [True, False, 0, -1, 6, 1.5, "2"])
def test_direct_settings_cannot_bypass_retry_bounds(retries):
    with pytest.raises(GuideShopSettingsError):
        GuideShopHTTPSettings(
            base_url="https://api.example.com",
            app_env="test",
            max_retries=retries,
        )


@pytest.mark.parametrize(
    "retry_after", [True, False, 0, -1, 61, float("inf"), "5"]
)
def test_direct_settings_cannot_bypass_retry_after_bounds(retry_after):
    with pytest.raises(GuideShopSettingsError):
        GuideShopHTTPSettings(
            base_url="https://api.example.com",
            app_env="test",
            max_retry_after_seconds=retry_after,
        )


def test_direct_settings_normalize_consistently_and_remain_immutable():
    parsed = GuideShopHTTPSettings(
        base_url="https://api.example.com/",
        app_env="TEST",
        request_timeout_seconds=5,
        max_retries=2,
        max_retry_after_seconds=3,
    )
    assert parsed.base_url == "https://api.example.com"
    assert parsed.app_env == "test"
    assert parsed.request_timeout_seconds == 5.0
    assert parsed.max_retry_after_seconds == 3.0
    with pytest.raises(FrozenInstanceError):
        parsed.app_env = "production"


def test_client_construction_binds_identity_and_performs_no_http():
    provider = TokenProvider()
    session = FakeSession([])
    client = HTTPGuideShopClient(settings(), "bound-guide", provider, session=session)
    assert isinstance(client, GuideShopClient)
    assert isinstance(provider, GuideShopAccessTokenProvider)
    assert session.requests == []
    assert provider.identities == []

    for name in (
        "list_companies",
        "list_visits",
        "get_visit",
        "list_sales",
        "get_sale",
        "list_points",
        "get_points_transaction",
        "list_history",
    ):
        parameters = inspect.signature(getattr(HTTPGuideShopClient, name)).parameters
        assert "guide_os_id" not in parameters
        assert "telegram_user_id" not in parameters


@pytest.mark.parametrize("identity", [None, "", "   ", 123, True])
def test_client_rejects_invalid_bound_identity(identity):
    with pytest.raises(GuideShopClientError):
        HTTPGuideShopClient(settings(), identity, TokenProvider(), session=FakeSession([]))


@pytest.mark.parametrize("token", [None, "", "   ", "bad token", "bad\r\ntoken", 123])
def test_invalid_access_token_fails_before_http(token):
    session = FakeSession([])
    client = HTTPGuideShopClient(
        settings(), "bound-guide", TokenProvider(token), session=session
    )
    with pytest.raises(GuideShopAuthenticationError):
        run(client.list_companies())
    assert session.requests == []


def test_authentication_header_and_identity_are_isolated_from_url_and_query():
    provider = TokenProvider("private-service-token")
    session = FakeSession([FakeResponse(payload=list_envelope(company_payload()))])
    client = HTTPGuideShopClient(settings(), "private-guide-id", provider, session=session)
    result = run(client.list_companies())

    assert isinstance(result, APIListResponseDTO)
    assert isinstance(result.data[0], CompanyDTO)
    assert provider.identities == ["private-guide-id"]
    method, url, kwargs = session.requests[0]
    assert method == "GET"
    assert kwargs["headers"] == {
        "Authorization": "Bearer private-service-token",
        "Accept": "application/json",
    }
    assert kwargs["params"] is None
    assert kwargs["allow_redirects"] is False
    assert "private-guide-id" not in url
    assert "private-service-token" not in url


def test_all_eight_methods_use_exact_paths_get_and_typed_envelopes():
    outcomes = [
        FakeResponse(payload=list_envelope(company_payload())),
        FakeResponse(payload=list_envelope(visit_payload())),
        FakeResponse(payload=detail_envelope(visit_payload())),
        FakeResponse(payload=list_envelope(sale_payload())),
        FakeResponse(payload=detail_envelope(sale_payload())),
        FakeResponse(payload=list_envelope(points_payload())),
        FakeResponse(payload=detail_envelope(points_payload())),
        FakeResponse(payload=list_envelope(payout_payload())),
    ]
    session = FakeSession(outcomes)
    client = HTTPGuideShopClient(settings(), "guide", TokenProvider(), session=session)

    results = [
        run(client.list_companies()),
        run(client.list_visits()),
        run(client.get_visit("visit/one")),
        run(client.list_sales()),
        run(client.get_sale("sale one")),
        run(client.list_points()),
        run(client.get_points_transaction("points?one")),
        run(client.list_history()),
    ]
    assert [request[0] for request in session.requests] == ["GET"] * 8
    assert [request[1] for request in session.requests] == [
        "https://api.guideshop.example/integration/v1/me/companies",
        "https://api.guideshop.example/integration/v1/me/visits",
        "https://api.guideshop.example/integration/v1/me/visits/visit%2Fone",
        "https://api.guideshop.example/integration/v1/me/sales",
        "https://api.guideshop.example/integration/v1/me/sales/sale%20one",
        "https://api.guideshop.example/integration/v1/me/points",
        "https://api.guideshop.example/integration/v1/me/points/points%3Fone",
        "https://api.guideshop.example/integration/v1/me/history",
    ]
    assert isinstance(results[2], APIDetailResponseDTO)
    assert isinstance(results[2].data, VisitDTO)
    assert isinstance(results[4].data, SaleDTO)
    assert isinstance(results[6].data, PointsAccrualDTO)
    assert isinstance(results[7].data[0], PointsPayoutDTO)


def test_cursor_and_points_status_queries_are_optional_and_strict():
    session = FakeSession(
        [
            FakeResponse(payload=list_envelope(visit_payload())),
            FakeResponse(payload=list_envelope(points_payload())),
        ]
    )
    client = HTTPGuideShopClient(settings(), "guide", TokenProvider(), session=session)
    run(client.list_visits("opaque-cursor"))
    run(client.list_points(PointsStatus.PENDING, "points-cursor"))
    assert session.requests[0][2]["params"] == {"cursor": "opaque-cursor"}
    assert session.requests[1][2]["params"] == {"cursor": "points-cursor"}

    before = len(session.requests)
    with pytest.raises(GuideShopClientError):
        run(client.list_visits(""))
    with pytest.raises(GuideShopClientError):
        run(client.list_points("pending"))
    with pytest.raises(GuideShopClientError):
        run(client.get_sale(123))
    assert len(session.requests) == before


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (400, GuideShopClientError),
        (401, GuideShopAuthenticationError),
        (403, GuideShopAccessDeniedError),
        (404, GuideShopObjectNotFoundError),
        (409, GuideShopAccessDeniedError),
        (418, GuideShopClientError),
        (500, GuideShopTemporarilyUnavailableError),
    ],
)
def test_non_retry_status_mapping_is_safe(status, error_type):
    private_body = b"private body object-id guide-id token-value"
    session = FakeSession([FakeResponse(status=status, body=private_body)])
    client = HTTPGuideShopClient(settings(), "private-guide-id", TokenProvider("token-value"), session=session)
    with pytest.raises(error_type) as error:
        run(client.get_visit("private-object-id"))
    assert len(session.requests) == 1
    for private_value in (
        "private body",
        "private-object-id",
        "private-guide-id",
        "token-value",
    ):
        assert private_value not in str(error.value)


@pytest.mark.parametrize("status", [429, 503])
def test_approved_transient_statuses_retry_then_succeed(status):
    sleep = AsyncMock()
    session = FakeSession(
        [
            FakeResponse(status=status),
            FakeResponse(payload=list_envelope(company_payload())),
        ]
    )
    client = HTTPGuideShopClient(
        settings(), "guide", TokenProvider(), session=session, sleep=sleep
    )
    assert run(client.list_companies()).data[0].company_id == "company-1"
    assert len(session.requests) == 2
    sleep.assert_awaited_once()


def test_retry_after_is_numeric_and_bounded():
    sleep = AsyncMock()
    session = FakeSession(
        [
            FakeResponse(status=429, headers={"Retry-After": "999"}),
            FakeResponse(status=429),
        ]
    )
    client = HTTPGuideShopClient(
        settings(), "guide", TokenProvider(), session=session, sleep=sleep
    )
    with pytest.raises(GuideShopTemporarilyUnavailableError):
        run(client.list_companies())
    sleep.assert_awaited_once_with(3.0)


@pytest.mark.parametrize("retry_after", ["-1", "Wed, 21 Oct 2026 07:28:00 GMT", "bad"])
def test_malformed_retry_after_uses_safe_bounded_delay(retry_after):
    sleep = AsyncMock()
    session = FakeSession(
        [
            FakeResponse(status=503, headers={"Retry-After": retry_after}),
            FakeResponse(payload=list_envelope(company_payload())),
        ]
    )
    client = HTTPGuideShopClient(
        settings(), "guide", TokenProvider(), session=session, sleep=sleep
    )
    run(client.list_companies())
    delay = sleep.await_args.args[0]
    assert 0 <= delay <= 3


@pytest.mark.parametrize("failure", [asyncio.TimeoutError(), aiohttp.ClientConnectionError()])
def test_timeout_and_connection_failures_retry_with_bound(failure):
    sleep = AsyncMock()
    session = FakeSession(
        [failure, FakeResponse(payload=list_envelope(company_payload()))]
    )
    client = HTTPGuideShopClient(
        settings(), "guide", TokenProvider(), session=session, sleep=sleep
    )
    assert run(client.list_companies()).data
    assert len(session.requests) == 2
    assert sleep.await_args.args[0] <= 3


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(body=b"not-json"),
        FakeResponse(payload={"wrong": "shape"}),
    ],
)
def test_invalid_json_and_contract_responses_are_rejected(response):
    session = FakeSession([response])
    client = HTTPGuideShopClient(settings(), "guide", TokenProvider(), session=session)
    with pytest.raises(GuideShopClientError, match="Invalid GuideShop response"):
        run(client.list_companies())
    assert len(session.requests) == 1


def test_oversized_declared_content_length_is_rejected_before_body_read():
    response = FakeResponse(
        body=b"private-body",
        content_length=1_000_001,
    )
    session = FakeSession([response, FakeResponse(payload=list_envelope(company_payload()))])
    client = HTTPGuideShopClient(settings(), "guide", TokenProvider(), session=session)
    with pytest.raises(GuideShopClientError, match="Invalid GuideShop response"):
        run(client.list_companies())
    assert response.content.read_calls == []
    response.release.assert_called_once_with()
    assert len(session.requests) == 1


@pytest.mark.parametrize("declared_length", [None, "malformed", 1])
def test_oversized_undeclared_or_dishonest_response_stops_at_detection_byte(
    declared_length,
):
    private_body = b"private-object-id-guide-id-token" + b"x" * 1_000_100
    response = FakeResponse(
        body=private_body,
        content_length=declared_length,
    )
    session = FakeSession([response, FakeResponse(payload=list_envelope(company_payload()))])
    client = HTTPGuideShopClient(
        settings(), "private-guide-id", TokenProvider("private-token"), session=session
    )
    with pytest.raises(GuideShopClientError) as error:
        run(client.get_visit("private-object-id"))
    assert response.content.total_returned == 1_000_001
    assert max(response.content.read_calls) <= 65_536
    response.release.assert_called_once_with()
    assert len(session.requests) == 1
    for private_value in (
        "private-object-id",
        "private-guide-id",
        "private-token",
    ):
        assert private_value not in str(error.value)


def test_exactly_at_limit_contract_valid_response_is_accepted():
    encoded = json.dumps(list_envelope(company_payload())).encode("utf-8")
    body = encoded + b" " * (1_000_000 - len(encoded))
    response = FakeResponse(body=body, content_length=None)
    session = FakeSession([response])
    client = HTTPGuideShopClient(settings(), "guide", TokenProvider(), session=session)
    result = run(client.list_companies())
    assert result.data[0].company_id == "company-1"
    assert response.content.total_returned == 1_000_000
    response.release.assert_called_once_with()


def test_injected_session_is_not_closed_unless_ownership_is_explicit():
    unowned = FakeSession([])
    client = HTTPGuideShopClient(settings(), "guide", TokenProvider(), session=unowned)
    run(client.close())
    run(client.close())
    unowned.close.assert_not_awaited()

    owned = FakeSession([])
    client = HTTPGuideShopClient(
        settings(), "guide", TokenProvider(), session=owned, owns_session=True
    )
    run(client.close())
    run(client.close())
    owned.close.assert_awaited_once_with()


@pytest.mark.parametrize("status", [502, 504])
def test_non_contract_gateway_statuses_do_not_retry(status):
    sleep = AsyncMock()
    session = FakeSession(
        [
            FakeResponse(status=status),
            FakeResponse(payload=list_envelope(company_payload())),
        ]
    )
    client = HTTPGuideShopClient(
        settings(), "guide", TokenProvider(), session=session, sleep=sleep
    )
    with pytest.raises(GuideShopTemporarilyUnavailableError):
        run(client.list_companies())
    assert len(session.requests) == 1
    sleep.assert_not_awaited()


class SequenceTokenProvider:
    def __init__(self):
        self.tokens = []

    async def get_access_token(self, guide_os_id):
        token = f"service-token-{len(self.tokens) + 1}"
        self.tokens.append(token)
        return token


def test_retry_mints_fresh_access_token_and_does_not_retain_it():
    provider = SequenceTokenProvider()
    session = FakeSession(
        [
            FakeResponse(status=503),
            FakeResponse(payload=list_envelope(company_payload())),
        ]
    )
    client = HTTPGuideShopClient(
        settings(), "guide", provider, session=session, sleep=AsyncMock()
    )
    run(client.list_companies())
    assert provider.tokens == ["service-token-1", "service-token-2"]
    first_auth = session.requests[0][2]["headers"]["Authorization"]
    second_auth = session.requests[1][2]["headers"]["Authorization"]
    assert first_auth != second_auth
    assert "service-token-1" not in repr(client)
    assert "service-token-2" not in repr(client)
    assert not hasattr(client, "_last_token")


def test_owned_lazy_session_closes_once_and_context_manager_cleans_up(monkeypatch):
    session = FakeSession([FakeResponse(payload=list_envelope(company_payload()))])
    constructor = Mock(return_value=session)
    monkeypatch.setattr(client_module.aiohttp, "ClientSession", constructor)

    async def exercise():
        async with HTTPGuideShopClient(
            settings(), "guide", TokenProvider()
        ) as client:
            await client.list_companies()
        await client.close()

    run(exercise())
    constructor.assert_called_once()
    session.close.assert_awaited_once_with()
