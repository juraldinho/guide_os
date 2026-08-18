import asyncio
from dataclasses import FrozenInstanceError
import inspect
import sqlite3
import socket

import pytest

from services.guide_shop_client import (
    DisabledGuideShopClient,
    GuideShopClient,
    GuideShopClientError,
    GuideShopIntegrationDisabledError,
    GuideShopObjectNotFoundError,
    InMemoryGuideShopClient,
    build_guide_shop_client,
)
from services.guide_shop_contracts import (
    APIDetailResponseDTO,
    APIListResponseDTO,
    CompanyDTO,
    PointsAccrualDTO,
    PointsPayoutDTO,
    PointsStatus,
    PointsSummaryDTO,
    SaleDTO,
    VisitDTO,
)
from services.guide_shop_settings import (
    GuideShopFeatureFlags,
    GuideShopSettingsError,
)


UTC = "2026-08-07T12:00:00Z"


def run(awaitable):
    return asyncio.run(awaitable)


def company(company_id: str) -> CompanyDTO:
    return CompanyDTO.model_validate(
        {"company_id": company_id, "display_name": company_id, "status": "active"}
    )


def visit(visit_id: str) -> VisitDTO:
    return VisitDTO.model_validate(
        {
            "visit_id": visit_id,
            "company_id": "company-1",
            "guide_membership_id": "gmem-0001",
            "visit_at": UTC,
            "status": "active",
            "tourist_count": 2,
            "customer_payment_status": "unpaid",
            "created_at": UTC,
            "updated_at": UTC,
        }
    )


def sale(sale_id: str) -> SaleDTO:
    return SaleDTO.model_validate(
        {
            "sale_id": sale_id,
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
    )


def points(points_id: str, status: str = "pending") -> PointsAccrualDTO:
    payload = {
        "points_accrual_id": points_id,
        "company_id": "company-1",
        "visit_id": "visit-01",
        "amount": "2.00",
        "unit": "PTS",
        "status": status,
        "calculated_at": UTC,
        "updated_at": UTC,
    }
    if status == "credited":
        payload["credited_at"] = UTC
        payload["payout_id"] = f"pay-{points_id}"
    return PointsAccrualDTO.model_validate(payload)


def payout(payout_id: str, accrual_id: str = "points-1") -> PointsPayoutDTO:
    return PointsPayoutDTO.model_validate(
        {
            "payout_id": payout_id,
            "points_accrual_id": accrual_id,
            "company_id": "company-1",
            "visit_id": "visit-01",
            "amount": "2.00",
            "unit": "PTS",
            "paid_at": UTC,
            "created_at": UTC,
        }
    )


def test_feature_flags_default_false_and_are_immutable():
    flags = GuideShopFeatureFlags.from_env({})
    assert flags == GuideShopFeatureFlags(False, False, False, False)
    with pytest.raises(FrozenInstanceError):
        flags.reads_enabled = True


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", "YeS"])
def test_supported_true_flag_values(value):
    assert GuideShopFeatureFlags.from_env({"GUIDESHOP_READS_ENABLED": value}).reads_enabled


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "FALSE", "OfF"])
def test_supported_false_flag_values(value):
    assert not GuideShopFeatureFlags.from_env({"GUIDESHOP_READS_ENABLED": value}).reads_enabled


@pytest.mark.parametrize("value", ["", "enabled", "2", " true "])
def test_empty_and_unknown_flag_values_are_rejected(value):
    with pytest.raises(GuideShopSettingsError):
        GuideShopFeatureFlags.from_env({"GUIDESHOP_READS_ENABLED": value})


def test_feature_flags_are_independent():
    flags = GuideShopFeatureFlags.from_env(
        {
            "GUIDESHOP_READS_ENABLED": "false",
            "GUIDESHOP_LINKING_ENABLED": "true",
            "GUIDESHOP_EVENTS_ENABLED": "false",
            "GUIDESHOP_NOTIFICATIONS_ENABLED": "true",
            "BOT_TOKEN": "must-not-be-read",
        }
    )
    assert not flags.reads_enabled
    assert flags.linking_enabled
    assert not flags.events_enabled
    assert flags.notifications_enabled


def disabled_calls(client):
    return [
        client.list_companies(),
        client.list_visits("ignored"),
        client.get_visit("ignored"),
        client.list_sales("ignored"),
        client.get_sale("ignored"),
        client.list_points(PointsStatus.PENDING, "ignored"),
        client.get_points_summary(),
        client.get_points_transaction("ignored"),
        client.list_history("ignored"),
    ]


def test_disabled_client_protocol_all_methods_and_no_external_operations(monkeypatch):
    client = DisabledGuideShopClient()
    assert isinstance(client, GuideShopClient)

    def unexpected(*args, **kwargs):
        raise AssertionError("external operation attempted")

    async def exercise():
        monkeypatch.setattr(socket, "socket", unexpected)
        monkeypatch.setattr(sqlite3, "connect", unexpected)
        for operation in disabled_calls(client):
            with pytest.raises(GuideShopIntegrationDisabledError):
                await operation

    run(exercise())


def test_factory_is_disabled_by_default_and_fails_when_reads_enabled():
    client = build_guide_shop_client(GuideShopFeatureFlags())
    assert isinstance(client, DisabledGuideShopClient)
    with pytest.raises(GuideShopClientError, match="not configured"):
        build_guide_shop_client(GuideShopFeatureFlags(reads_enabled=True))


def fake_client(page_size: int = 2) -> InMemoryGuideShopClient:
    return InMemoryGuideShopClient(
        companies=[company("company-1")],
        visits=[visit("visit-01"), visit("visit-02"), visit("visit-03")],
        sales=[sale("sale-001"), sale("sale-002")],
        points=[points("points-1"), points("points-2", "credited")],
        points_history=[payout("history-2", "points-2"), payout("history-1", "points-1")],
        page_size=page_size,
    )


def test_fake_satisfies_protocol_accepts_only_validated_dtos():
    assert isinstance(fake_client(), GuideShopClient)
    with pytest.raises(TypeError):
        InMemoryGuideShopClient(companies=[{"company_id": "unchecked"}])


def test_fake_returns_typed_lists_details_filter_and_history_in_input_order():
    client = fake_client()
    companies = run(client.list_companies())
    visits = run(client.list_visits())
    sales = run(client.list_sales())
    point_list = run(client.list_points(PointsStatus.CREDITED))
    history = run(client.list_history())

    assert isinstance(companies, APIListResponseDTO)
    assert isinstance(companies.data[0], CompanyDTO)
    assert [item.visit_id for item in visits.data] == ["visit-01", "visit-02"]
    assert isinstance(sales.data[0], SaleDTO)
    assert [item.points_accrual_id for item in point_list.data] == ["points-2"]
    assert [item.payout_id for item in history.data] == ["history-2", "history-1"]
    assert isinstance(run(client.get_visit("visit-01")), APIDetailResponseDTO)
    assert run(client.get_sale("sale-001")).data.sale_id == "sale-001"
    assert run(client.get_points_transaction("points-1")).data.points_accrual_id == "points-1"
    summary = run(client.get_points_summary())
    assert isinstance(summary, PointsSummaryDTO)
    assert summary.pending_total == "2.00"
    assert summary.credited_total == "2.00"
    assert summary.unit == "PTS"
    assert summary.companies[0].pending_total == "2.00"
    assert summary.companies[0].credited_total == "2.00"


def test_unknown_detail_ids_raise_safe_not_found_error():
    client = fake_client()
    for operation in (
        client.get_visit("missing"),
        client.get_sale("missing"),
        client.get_points_transaction("missing"),
    ):
        with pytest.raises(GuideShopObjectNotFoundError, match="not found"):
            run(operation)


def test_fake_pagination_uses_opaque_scoped_cursors_and_preserves_order():
    client = fake_client(page_size=2)
    first = run(client.list_visits())
    cursor = first.page.next_cursor
    assert cursor and cursor not in {"2", "visit-01", "visit-02", "visit-03"}
    second = run(client.list_visits(cursor))
    assert [item.visit_id for item in second.data] == ["visit-03"]
    assert second.page.next_cursor is None

    with pytest.raises(GuideShopClientError, match="cursor"):
        run(client.list_visits("unknown"))
    with pytest.raises(GuideShopClientError, match="cursor"):
        run(client.list_sales(cursor))


def test_fake_points_summary_is_complete_scope_and_preserves_decimal_strings():
    client = fake_client(page_size=1)
    listed = run(client.list_points())
    summary = run(client.get_points_summary())
    empty = run(InMemoryGuideShopClient().get_points_summary())

    assert len(listed.data) == 1
    assert summary.pending_total == "2.00"
    assert summary.credited_total == "2.00"
    assert isinstance(summary.pending_total, str)
    assert isinstance(summary.credited_total, str)
    assert summary.companies[0].pending_total == "2.00"
    assert summary.companies[0].credited_total == "2.00"
    assert empty.pending_total == "0.00"
    assert empty.credited_total == "0.00"
    assert empty.companies == []
    assert isinstance(empty, PointsSummaryDTO)


def test_returned_lists_and_models_cannot_mutate_internal_state():
    client = fake_client()
    response = run(client.list_visits())
    response.data.clear()
    response = run(client.list_visits())
    response.data[0].visit_id = "changed"

    fresh = run(client.list_visits())
    assert [item.visit_id for item in fresh.data] == ["visit-01", "visit-02"]


def test_fake_operations_perform_no_network_or_sqlite(monkeypatch):
    client = fake_client()

    def unexpected(*args, **kwargs):
        raise AssertionError("external operation attempted")

    async def exercise():
        monkeypatch.setattr(socket, "socket", unexpected)
        monkeypatch.setattr(sqlite3, "connect", unexpected)
        assert (await client.list_companies()).data[0].company_id == "company-1"
        assert (await client.get_visit("visit-01")).data.visit_id == "visit-01"
        summary = await client.get_points_summary()
        assert summary.pending_total == "2.00"

    run(exercise())


def test_protocol_methods_do_not_accept_guide_identity_arguments():
    for name in (
        "list_companies",
        "list_visits",
        "get_visit",
        "list_sales",
        "get_sale",
        "list_points",
        "get_points_summary",
        "get_points_transaction",
        "list_history",
    ):
        parameters = inspect.signature(getattr(GuideShopClient, name)).parameters
        assert "guide_os_id" not in parameters
        assert "guideshop_guide_id" not in parameters
