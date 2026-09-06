"""GSMA9 regression matrix for GuideShop Mini App boundaries."""

from __future__ import annotations

from urllib.parse import quote

import pytest

from database.db import get_connection
from database.queries import register_user
from services.guide_shop_client import (
    GuideShopTemporarilyUnavailableError,
    InMemoryGuideShopClient,
)
from services.guide_shop_contracts import CompanyDTO
from services.guide_shop_runtime import (
    RequestScopedGuideShopUIServiceProvider,
    StaticGuideShopUIServiceProvider,
)
from web_api.app import create_miniapp_api_app
from web_api.routes.guideshop_companies import configure_miniapp_guideshop_provider

from tests.test_miniapp_api import (
    API_USER,
    PROFILE_USER_B,
    _auth_headers,
    _commission_payload,
    _commission_reports,
    _create_commission_for_user,
    _create_place_for_user,
    _deactivate_place,
    _get_commission,
    _get_place,
    _list_commissions,
    _list_places,
    _place_payload,
    _post_commission,
    _post_place,
    _put_commission,
    _put_place,
    _settings,
    api_request,
    response_json,
)


GUIDE_ID_A = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee1"
GUIDE_ID_B = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee2"


@pytest.fixture(autouse=True)
def _reset_provider():
    configure_miniapp_guideshop_provider(None, reads_enabled=False)
    yield
    configure_miniapp_guideshop_provider(None, reads_enabled=False)


@pytest.fixture
def seeded_user(test_database):
    register_user(API_USER)
    return API_USER


def _assert_not_found(response, *forbidden: str) -> None:
    assert response.status == 404
    body = response_json(response)
    assert body["error"]["code"] == "not_found"
    assert response.status != 500
    for value in forbidden:
        assert value not in response._body_text


def test_personal_company_bola_matrix_and_owner_only_lists(seeded_user):
    register_user(PROFILE_USER_B)
    owner_place = _create_place_for_user(seeded_user)
    attacker_place = _create_place_for_user(PROFILE_USER_B)

    owner_list = response_json(_list_places(seeded_user))["data"]["places"]
    attacker_list = response_json(_list_places(PROFILE_USER_B))["data"]["places"]
    assert [item["id"] for item in owner_list] == [owner_place]
    assert [item["id"] for item in attacker_list] == [attacker_place]
    assert all("user_id" not in item and "userId" not in item for item in owner_list)

    _assert_not_found(_get_place(seeded_user, attacker_place), attacker_place)
    _assert_not_found(
        _put_place(seeded_user, attacker_place, _place_payload(name="forbidden")),
        attacker_place,
        "forbidden",
    )
    _assert_not_found(_deactivate_place(seeded_user, attacker_place), attacker_place)
    _assert_not_found(_list_commissions(seeded_user, attacker_place), attacker_place)
    _assert_not_found(
        _post_commission(seeded_user, attacker_place, _commission_payload()),
        attacker_place,
    )

    assert _get_place(PROFILE_USER_B, attacker_place).status == 200


def test_personal_commission_idempotency_is_user_and_endpoint_scoped(seeded_user):
    register_user(PROFILE_USER_B)
    place_a = _create_place_for_user(seeded_user)
    place_b = _create_place_for_user(PROFILE_USER_B)
    payload = _commission_payload(
        purchaseAmountMinor=None,
        receivedIncomeMinor=None,
        receivedPoints=7,
        currency=None,
    )
    key = "gsma9-commission-key"

    def create(user_id: int, place_id: str, body: dict):
        return api_request(
            "POST",
            f"/app/v1/personal-places/{place_id}/commissions",
            headers=_auth_headers(user_id, **{"Idempotency-Key": key}),
            json=body,
        )

    first = create(seeded_user, place_a, payload)
    replay = create(seeded_user, place_a, payload)
    assert first.status == replay.status == 201
    assert response_json(first)["data"]["id"] == response_json(replay)["data"]["id"]

    conflict = create(seeded_user, place_a, {**payload, "receivedPoints": 8})
    assert conflict.status == 409
    assert response_json(conflict)["error"]["code"] == "idempotency_replay"

    other_user = create(PROFILE_USER_B, place_b, payload)
    assert other_user.status == 201
    assert response_json(other_user)["data"]["id"] != response_json(first)["data"]["id"]


def test_commission_cannot_be_enumerated_or_reassociated_across_owners(seeded_user):
    register_user(PROFILE_USER_B)
    owner_place, owner_commission = _create_commission_for_user(seeded_user)
    attacker_place, attacker_commission = _create_commission_for_user(PROFILE_USER_B)

    _assert_not_found(_get_commission(seeded_user, attacker_commission), attacker_commission)
    _assert_not_found(
        _put_commission(seeded_user, attacker_commission, _commission_payload()),
        attacker_commission,
    )
    _assert_not_found(_list_commissions(seeded_user, attacker_place), attacker_place)
    assert [
        item["id"]
        for item in response_json(_list_commissions(seeded_user, owner_place))["data"][
            "commissions"
        ]
    ] == [owner_commission]


def test_registered_official_surface_is_get_only_and_sales_are_withdrawn(seeded_user):
    app = create_miniapp_api_app(_settings())
    routes = {(route.method, route.resource.canonical) for route in app.router.routes()}
    expected = {
        ("GET", "/app/v1/guideshop/companies"),
        ("GET", "/app/v1/guideshop/companies/{companyId}"),
        ("GET", "/app/v1/guideshop/visits"),
        ("GET", "/app/v1/guideshop/visits/{visitId}"),
        ("GET", "/app/v1/guideshop/points/summary"),
        ("GET", "/app/v1/guideshop/history"),
    }
    official_routes = {
        route
        for route in routes
        if route[0] != "HEAD" and route[1].startswith("/app/v1/guideshop/")
    }
    assert official_routes == expected
    assert not any("sales" in path for _, path in routes)

    calls: list[str] = []

    class NoCallService:
        def __getattr__(self, name):
            calls.append(name)
            raise AssertionError("official provider must not be called")

    configure_miniapp_guideshop_provider(
        StaticGuideShopUIServiceProvider(NoCallService()),
        reads_enabled=True,
    )

    with get_connection() as connection:
        before = tuple(connection.iterdump())

    attempts = [
        ("POST", "/app/v1/guideshop/companies", 405),
        ("PUT", "/app/v1/guideshop/companies/company_safe", 405),
        ("PATCH", "/app/v1/guideshop/visits/visit_safe1", 405),
        ("DELETE", "/app/v1/guideshop/points/summary", 405),
        ("POST", "/app/v1/guideshop/history", 405),
        ("GET", "/app/v1/guideshop/sales", 404),
        ("GET", "/app/v1/guideshop/sales/sale_safe1", 404),
    ]
    for method, path, expected_status in attempts:
        response = api_request(method, path, headers=_auth_headers(seeded_user), json={})
        assert response.status == expected_status
        assert response.status != 500
    assert calls == []
    with get_connection() as connection:
        assert tuple(connection.iterdump()) == before


@pytest.mark.parametrize(
    "route_prefix,personal_id",
    [
        ("/app/v1/guideshop/companies", "place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        ("/app/v1/guideshop/visits", "entry_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
    ],
)
def test_forged_official_ids_fail_closed_without_namespace_reinterpretation(
    seeded_user, route_prefix, personal_id
):
    calls: list[str] = []

    class CountingClient(InMemoryGuideShopClient):
        async def close(self):
            return None

        async def list_companies(self):
            calls.append("companies.list")
            return await super().list_companies()

        async def get_company(self, company_id):
            calls.append(company_id)
            return await super().get_company(company_id)

        async def get_visit(self, visit_id):
            calls.append(visit_id)
            return await super().get_visit(visit_id)

    configure_miniapp_guideshop_provider(
        RequestScopedGuideShopUIServiceProvider(
            lambda _user_id: GUIDE_ID_A,
            lambda _guide_id: CountingClient(),
        ),
        reads_enabled=True,
    )
    forged = [
        personal_id,
        "<script>alert(1)</script>",
        "../traversal",
        "encoded/slash",
        "control\x00value",
        "unicode_компания",
        "x" * 129,
    ]
    for raw_id in forged:
        response = api_request(
            "GET",
            f"{route_prefix}/{quote(raw_id, safe='')}",
            headers=_auth_headers(seeded_user),
        )
        assert response.status == 404
        assert response.status != 500
        assert raw_id not in response._body_text
    # A syntactically valid opaque personal ID may reach the current principal's
    # read-only provider, but it can never resolve as a personal resource.
    assert len(calls) <= 1


def test_official_detail_uses_request_scoped_identity(seeded_user):
    register_user(PROFILE_USER_B)

    def company(company_id: str, name: str):
        return CompanyDTO.model_validate(
            {"company_id": company_id, "display_name": name, "status": "active"}
        )

    class ClosableClient(InMemoryGuideShopClient):
        async def close(self):
            return None

    def client_for(guide_id: str):
        if guide_id == GUIDE_ID_A:
            return ClosableClient(companies=(company("company_user_a", "Company A"),))
        return ClosableClient(companies=(company("company_user_b", "Company B"),))

    configure_miniapp_guideshop_provider(
        RequestScopedGuideShopUIServiceProvider(
            lambda user_id: GUIDE_ID_A if user_id == seeded_user else GUIDE_ID_B,
            client_for,
        ),
        reads_enabled=True,
    )

    own = api_request(
        "GET",
        "/app/v1/guideshop/companies/company_user_a",
        headers=_auth_headers(seeded_user),
    )
    foreign = api_request(
        "GET",
        "/app/v1/guideshop/companies/company_user_a",
        headers=_auth_headers(PROFILE_USER_B),
    )
    assert own.status == 200, own._body_text
    _assert_not_found(foreign, "company_user_a", GUIDE_ID_A, GUIDE_ID_B)


def test_commission_reports_session_scoped_period_only(seeded_user):
    register_user(PROFILE_USER_B)
    owner_place = _create_place_for_user(seeded_user)
    attacker_place = _create_place_for_user(PROFILE_USER_B)
    _create_commission_for_user(
        seeded_user,
        owner_place,
        occurredAt="2026-08-10T12:00:00+05:00",
        receivedPoints=11,
        purchaseAmountMinor=None,
        receivedIncomeMinor=None,
        currency=None,
    )
    _create_commission_for_user(
        PROFILE_USER_B,
        attacker_place,
        occurredAt="2026-08-10T12:00:00+05:00",
        receivedPoints=99,
        purchaseAmountMinor=None,
        receivedIncomeMinor=None,
        currency=None,
    )

    own = _commission_reports(seeded_user, "?from=2026-08-01&to=2026-08-31")
    body = response_json(own)
    assert own.status == 200
    assert own.status != 500
    data = body["data"]
    assert data["totalCommission"] == 11
    assert data["recordCount"] == 1
    assert [row["placeId"] for row in data["byCompany"]] == [owner_place]
    assert attacker_place not in {row["placeId"] for row in data["byCompany"]}
    commission_values = [
        data["totalCommission"],
        *(row["totalCommission"] for row in data["byCompany"]),
    ]
    assert 99 not in commission_values
    assert all(row["recordCount"] != 99 for row in data["byCompany"])
    assert "userId" not in data
    assert "user_id" not in own._body_text

    spoof = _commission_reports(
        seeded_user,
        f"?from=2026-08-01&to=2026-08-31&userId={PROFILE_USER_B}",
    )
    assert spoof.status == 400
    assert spoof.status != 500
    assert response_json(spoof)["error"]["code"] == "validation_error"

    missing = api_request(
        "GET",
        "/app/v1/reports/commissions?from=2026-08-01&to=2026-08-31",
    )
    assert missing.status == 401
    assert missing.status != 500
    assert response_json(missing)["error"]["code"] == "auth_required"


def test_personal_place_and_commission_html_roundtrip_is_inert(seeded_user):
    scriptish = "<script>alert(1)</script>"
    created = _post_place(
        seeded_user,
        _place_payload(name=scriptish, note=scriptish),
    )
    assert created.status == 201
    assert created.status != 500
    place_body = response_json(created)["data"]
    assert place_body["name"] == scriptish
    assert place_body["note"] == scriptish
    assert scriptish in created._body_text

    place_id = place_body["id"]
    commission = _post_commission(
        seeded_user,
        place_id,
        _commission_payload(
            occurredAt="2026-08-10T12:00:00+05:00",
            receivedPoints=3,
            purchaseAmountMinor=None,
            receivedIncomeMinor=None,
            currency=None,
            note=scriptish,
        ),
    )
    assert commission.status == 201
    assert response_json(commission)["data"]["note"] == scriptish
    parsed = response_json(commission)
    assert parsed["data"]["note"] == scriptish


def test_official_outage_does_not_block_personal_or_commission_reports(seeded_user):
    place_id = _create_place_for_user(seeded_user)
    _create_commission_for_user(
        seeded_user,
        place_id,
        occurredAt="2026-08-10T12:00:00+05:00",
        receivedPoints=4,
        purchaseAmountMinor=None,
        receivedIncomeMinor=None,
        currency=None,
    )

    class FakeService:
        async def list_official_companies(self):
            raise GuideShopTemporarilyUnavailableError("outage")

        async def list_visits(self, cursor=None):
            raise GuideShopTemporarilyUnavailableError("outage")

    configure_miniapp_guideshop_provider(
        StaticGuideShopUIServiceProvider(FakeService()),
        reads_enabled=True,
    )
    official = api_request(
        "GET",
        "/app/v1/guideshop/companies",
        headers=_auth_headers(seeded_user),
    )
    assert official.status == 503
    assert official.status != 500
    assert response_json(official)["error"]["code"] == "temporarily_unavailable"

    places = _list_places(seeded_user)
    assert places.status == 200
    assert any(item["id"] == place_id for item in response_json(places)["data"]["places"])

    reports = _commission_reports(seeded_user, "?from=2026-08-01&to=2026-08-31")
    assert reports.status == 200
    assert response_json(reports)["data"]["totalCommission"] == 4


def test_unregistered_official_history_detail_and_sales_never_500(seeded_user):
    cases = (
        ("GET", "/app/v1/guideshop/history/gspay_forged_01", 404),
        ("GET", "/app/v1/guideshop/sales", 404),
        ("POST", "/app/v1/guideshop/points/summary", 405),
    )
    for method, path, expected_status in cases:
        response = api_request(method, path, headers=_auth_headers(seeded_user))
        assert response.status == expected_status
        assert response.status != 500
