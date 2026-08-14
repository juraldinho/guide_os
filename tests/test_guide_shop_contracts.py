import copy
import sqlite3
import socket

import pytest
from pydantic import ValidationError

from services.guide_shop_contracts import (
    APIDetailResponseDTO,
    APIErrorDTO,
    APIListResponseDTO,
    CompanyDTO,
    EventEnvelopeDTO,
    PageDTO,
    PointsAccrualDTO,
    PointsPayoutDTO,
    SaleDTO,
    VisitDTO,
)


UTC_Z = "2026-08-07T12:30:45Z"
UTC_FRACTION = "2026-08-07T12:30:45.123Z"


def company_payload() -> dict:
    return {
        "company_id": "cmp_8f32ab10",
        "display_name": "Silk Road",
        "status": "active",
    }


def visit_payload(*, paid: bool = False) -> dict:
    payload = {
        "visit_id": "vis_8f32ab10",
        "company_id": "cmp_8f32ab10",
        "guide_membership_id": "gmem_8f32ab1",
        "visit_at": UTC_Z,
        "status": "active",
        "tourist_count": 3,
        "customer_payment_status": "paid" if paid else "unpaid",
        "created_at": UTC_FRACTION,
        "updated_at": UTC_Z,
    }
    if paid:
        payload["customer_paid_at"] = UTC_Z
    return payload


def sale_payload(*, unresolved: bool = False) -> dict:
    if unresolved:
        return {
            "sale_id": "sal_8f32ab10",
            "visit_id": "vis_8f32ab10",
            "company_id": "cmp_8f32ab10",
            "amount": "125.40",
            "currency": "USD",
            "status": "active",
            "payment_method": "cash",
            "category_id": None,
            "category_name": "Category unavailable",
            "created_at": UTC_Z,
            "updated_at": UTC_Z,
        }
    return {
        "sale_id": "sal_8f32ab10",
        "visit_id": "vis_8f32ab10",
        "company_id": "cmp_8f32ab10",
        "amount": "125.40",
        "currency": "USD",
        "status": "active",
        "payment_method": "card",
        "category_id": "cat_8f32ab10",
        "category_name": "Textiles",
        "created_at": UTC_Z,
        "updated_at": UTC_Z,
    }


def accrual_payload(*, credited: bool = True) -> dict:
    payload = {
        "points_accrual_id": "pacc_8f32ab1",
        "company_id": "cmp_8f32ab10",
        "visit_id": "vis_8f32ab10",
        "amount": "16.00",
        "unit": "PTS",
        "status": "credited" if credited else "pending",
        "calculated_at": UTC_Z,
        "updated_at": UTC_Z,
    }
    if credited:
        payload["credited_at"] = UTC_FRACTION
        payload["payout_id"] = "pay_8f32ab10"
    return payload


def payout_payload() -> dict:
    return {
        "payout_id": "pay_8f32ab10",
        "points_accrual_id": "pacc_8f32ab1",
        "company_id": "cmp_8f32ab10",
        "visit_id": "vis_8f32ab10",
        "amount": "16.00",
        "unit": "PTS",
        "paid_at": UTC_Z,
        "created_at": UTC_FRACTION,
    }


def list_envelope(item) -> dict:
    return {
        "schema_version": "1.0.0",
        "request_id": "req_8f32ab10",
        "data": [item],
        "page": {"next_cursor": None, "has_more": False},
    }


def event_payload(event_type: str) -> dict:
    variants = {
        "visit.created.v1": (
            {"type": "visit", "id": "visit-1"},
            {"visit_id": "visit-1", "company_id": "company-1"},
        ),
        "sale.created.v1": (
            {"type": "sale", "id": "sale-1"},
            {
                "sale_id": "sale-1",
                "visit_id": "visit-1",
                "amount_usd": "125.40",
                "currency": "USD",
            },
        ),
        "points.recalculated.v1": (
            {"type": "points_transaction", "id": "points-1"},
            {
                "points_transaction_id": "points-1",
                "old_amount": "12.00",
                "new_amount": "16.00",
                "status": "pending",
            },
        ),
        "points.credited.v1": (
            {"type": "points_transaction", "id": "points-1"},
            {
                "points_transaction_id": "points-1",
                "amount": "16.00",
                "status": "credited",
            },
        ),
    }
    subject, data = variants[event_type]
    return {
        "event_id": "event-1",
        "event_type": event_type,
        "occurred_at": UTC_Z,
        "producer": "guideshop",
        "subject": subject,
        "guide_os_id": "guide-1",
        "data": data,
        "schema_version": "1.0.0",
    }


def test_valid_core_dtos_and_envelopes_accept_z_and_fractional_utc():
    assert CompanyDTO.model_validate(company_payload()).company_id == "cmp_8f32ab10"
    assert VisitDTO.model_validate(visit_payload()).tourist_count == 3
    assert VisitDTO.model_validate(visit_payload(paid=True)).customer_payment_status.value == "paid"
    assert SaleDTO.model_validate(sale_payload()).amount == "125.40"
    assert SaleDTO.model_validate(sale_payload(unresolved=True)).category_id is None
    assert PointsAccrualDTO.model_validate(accrual_payload()).unit == "PTS"
    assert PointsPayoutDTO.model_validate(payout_payload()).payout_id == "pay_8f32ab10"

    company_list = APIListResponseDTO[CompanyDTO].model_validate(
        list_envelope(company_payload())
    )
    assert company_list.schema_version == "1.0.0"
    assert company_list.page.has_more is False
    visit_list = APIListResponseDTO[VisitDTO].model_validate(list_envelope(visit_payload()))
    sale_list = APIListResponseDTO[SaleDTO].model_validate(list_envelope(sale_payload()))
    accrual_list = APIListResponseDTO[PointsAccrualDTO].model_validate(
        list_envelope(accrual_payload())
    )
    payout_list = APIListResponseDTO[PointsPayoutDTO].model_validate(
        list_envelope(payout_payload())
    )
    assert visit_list.data[0].visit_id == "vis_8f32ab10"
    assert sale_list.data[0].payment_method.value == "card"
    assert accrual_list.data[0].status.value == "credited"
    assert payout_list.data[0].amount == "16.00"
    detail = APIDetailResponseDTO[VisitDTO].model_validate(
        {
            "schema_version": "1.0.0",
            "request_id": "req_8f32ab10",
            "data": visit_payload(),
        }
    )
    assert detail.data.visit_id == "vis_8f32ab10"
    sale_detail = APIDetailResponseDTO[SaleDTO].model_validate(
        {
            "schema_version": "1.0.0",
            "request_id": "req_8f32ab11",
            "data": sale_payload(),
        }
    )
    assert sale_detail.data.sale_id == "sal_8f32ab10"


def test_empty_list_and_has_more_with_cursor_are_accepted():
    empty = {
        "schema_version": "1.0.0",
        "request_id": "req_8f32ab10",
        "data": [],
        "page": {"next_cursor": None, "has_more": False},
    }
    parsed = APIListResponseDTO[CompanyDTO].model_validate(empty)
    assert parsed.data == []
    more = {
        "schema_version": "1.0.0",
        "request_id": "req_8f32ab10",
        "data": [company_payload()],
        "page": {"next_cursor": "nextcurs", "has_more": True},
    }
    parsed_more = APIListResponseDTO[CompanyDTO].model_validate(more)
    assert parsed_more.page.has_more is True
    assert parsed_more.page.next_cursor == "nextcurs"


@pytest.mark.parametrize("status", ["active", "inactive", "unknown"])
def test_company_status_enum(status):
    payload = company_payload()
    payload["status"] = status
    assert CompanyDTO.model_validate(payload).status.value == status


@pytest.mark.parametrize("status", ["active", "completed", "cancelled"])
def test_visit_status_enum(status):
    payload = visit_payload()
    payload["status"] = status
    assert VisitDTO.model_validate(payload).status.value == status


@pytest.mark.parametrize("method", ["cash", "card", "transfer"])
def test_sale_payment_methods(method):
    payload = sale_payload()
    payload["payment_method"] = method
    assert SaleDTO.model_validate(payload).payment_method.value == method


@pytest.mark.parametrize("timestamp", ["2026-08-07T12:30:45", "2026-08-07T12:30:45+00:00", "2026-08-07T12:30:45+05:00"])
def test_naive_offset_and_non_utc_timestamps_are_rejected(timestamp):
    payload = visit_payload()
    payload["visit_at"] = timestamp
    with pytest.raises(ValidationError):
        VisitDTO.model_validate(payload)


@pytest.mark.parametrize("value", [125.4, 125, "125", "125.4", "125.400", "1.25e2", "NaN", "Infinity", "1,25", " 1.25", "012.00", "-1.00"])
def test_money_rejects_numbers_and_malformed_decimal_strings(value):
    payload = sale_payload()
    payload["amount"] = value
    with pytest.raises(ValidationError):
        SaleDTO.model_validate(payload)


@pytest.mark.parametrize("value", [16.0, 16, "16", "16.0", "1.60e1", "+16.00"])
def test_points_reject_numbers_and_malformed_decimal_strings(value):
    payload = accrual_payload()
    payload["amount"] = value
    with pytest.raises(ValidationError):
        PointsAccrualDTO.model_validate(payload)


@pytest.mark.parametrize("value", ["", "   ", 123, 1.5, "cmp1", "12345678", "cmp/unsafe"])
def test_ids_must_be_opaque_strings(value):
    payload = company_payload()
    payload["company_id"] = value
    with pytest.raises(ValidationError):
        CompanyDTO.model_validate(payload)


def test_unknown_fields_old_versions_and_boolean_count_are_rejected():
    payload = company_payload()
    payload["phone"] = "+998000000000"
    with pytest.raises(ValidationError):
        CompanyDTO.model_validate(payload)

    envelope = {
        "schema_version": "1.0",
        "request_id": "req_8f32ab10",
        "data": company_payload(),
        "page": {"next_cursor": None, "has_more": False},
    }
    with pytest.raises(ValidationError):
        APIListResponseDTO[CompanyDTO].model_validate(envelope)

    evidence_version = {
        "schema_version": "1.1.0",
        "request_id": "req_8f32ab10",
        "data": company_payload(),
        "page": {"next_cursor": None, "has_more": False},
    }
    with pytest.raises(ValidationError):
        APIListResponseDTO[CompanyDTO].model_validate(evidence_version)

    visit = visit_payload()
    visit["status"] = "unknown"
    with pytest.raises(ValidationError):
        VisitDTO.model_validate(visit)
    visit = visit_payload()
    visit["tourist_count"] = True
    with pytest.raises(ValidationError):
        VisitDTO.model_validate(visit)

    sale = sale_payload()
    sale["currency"] = "EUR"
    with pytest.raises(ValidationError):
        SaleDTO.model_validate(sale)


def test_page_requires_boolean_has_more_and_rejects_malformed_cursors():
    with pytest.raises(ValidationError):
        PageDTO.model_validate({"next_cursor": None})
    with pytest.raises(ValidationError):
        PageDTO.model_validate({"next_cursor": None, "has_more": "false"})
    with pytest.raises(ValidationError):
        PageDTO.model_validate({"next_cursor": None, "has_more": 0})
    with pytest.raises(ValidationError):
        PageDTO.model_validate({"next_cursor": "short", "has_more": True})
    with pytest.raises(ValidationError):
        PageDTO.model_validate({"next_cursor": "bad cursor", "has_more": True})
    assert PageDTO.model_validate({"next_cursor": None, "has_more": False}).has_more is False


def test_visit_payment_invariants():
    unpaid = visit_payload()
    unpaid["customer_paid_at"] = UTC_Z
    with pytest.raises(ValidationError):
        VisitDTO.model_validate(unpaid)

    paid = visit_payload(paid=True)
    paid.pop("customer_paid_at")
    with pytest.raises(ValidationError):
        VisitDTO.model_validate(paid)
    paid["customer_paid_at"] = None
    with pytest.raises(ValidationError):
        VisitDTO.model_validate(paid)


def test_sale_category_invariants_and_voided_rejected():
    unresolved = sale_payload(unresolved=True)
    unresolved["category_id"] = "cat_8f32ab10"
    with pytest.raises(ValidationError):
        SaleDTO.model_validate(unresolved)

    resolved = sale_payload()
    resolved["category_id"] = None
    with pytest.raises(ValidationError):
        SaleDTO.model_validate(resolved)

    voided = sale_payload()
    voided["status"] = "voided"
    with pytest.raises(ValidationError):
        SaleDTO.model_validate(voided)
    extra = sale_payload()
    extra["voided_at"] = UTC_Z
    with pytest.raises(ValidationError):
        SaleDTO.model_validate(extra)


def test_accrual_pending_credited_and_reversed_invariants():
    pending = accrual_payload(credited=False)
    assert PointsAccrualDTO.model_validate(pending).payout_id is None

    pending["credited_at"] = UTC_Z
    with pytest.raises(ValidationError):
        PointsAccrualDTO.model_validate(pending)

    credited = accrual_payload()
    credited.pop("payout_id")
    with pytest.raises(ValidationError):
        PointsAccrualDTO.model_validate(credited)

    reversed_payload = accrual_payload()
    reversed_payload["status"] = "reversed"
    with pytest.raises(ValidationError):
        PointsAccrualDTO.model_validate(reversed_payload)


def test_payout_rejects_missing_required_fields():
    payload = payout_payload()
    payload.pop("paid_at")
    with pytest.raises(ValidationError):
        PointsPayoutDTO.model_validate(payload)


def test_api_error_code_and_retry_after_invariants():
    base = {
        "schema_version": "1.0.0",
        "request_id": "req_8f32ab10",
        "code": "rate_limited",
        "message": "Try later",
        "retry_after_seconds": 30,
    }
    assert APIErrorDTO.model_validate(base).retry_after_seconds == 30
    unavailable = {
        "schema_version": "1.0.0",
        "request_id": "req_8f32ab10",
        "code": "temporarily_unavailable",
        "message": "Unavailable",
        "retry_after_seconds": 12,
    }
    assert APIErrorDTO.model_validate(unavailable).code.value == "temporarily_unavailable"
    assert APIErrorDTO.model_validate(
        {
            "schema_version": "1.0.0",
            "request_id": "req_8f32ab10",
            "code": "invalid_transition",
            "message": "Conflict",
        }
    ).code.value == "invalid_transition"

    for mutation in (
        {"retry_after_seconds": None},
        {"retry_after_seconds": 0},
        {"retry_after_seconds": 121},
        {"retry_after_seconds": True},
        {"code": "not_found", "retry_after_seconds": 30},
        {"code": "not_found", "retry_after_seconds": None},
        {"code": "unsupported", "retry_after_seconds": None},
        {"schema_version": "1.0"},
    ):
        payload = {**base, **mutation}
        with pytest.raises(ValidationError):
            APIErrorDTO.model_validate(payload)


@pytest.mark.parametrize("event_type", ["visit.created.v1", "sale.created.v1", "points.recalculated.v1", "points.credited.v1"])
def test_each_required_event_has_typed_valid_data(event_type):
    parsed = EventEnvelopeDTO.model_validate(event_payload(event_type))
    assert parsed.event_type == event_type
    assert parsed.schema_version == "1.0.0"
    assert not isinstance(parsed.data, dict)
    id_field = {
        "visit.created.v1": "visit_id",
        "sale.created.v1": "sale_id",
        "points.recalculated.v1": "points_transaction_id",
        "points.credited.v1": "points_transaction_id",
    }[event_type]
    expected_id = getattr(parsed.data, id_field)
    assert parsed.subject.id == expected_id


@pytest.mark.parametrize(
    "event_type",
    [
        "visit.created.v1",
        "sale.created.v1",
        "points.recalculated.v1",
        "points.credited.v1",
    ],
)
def test_event_subject_id_must_match_typed_data_id(event_type):
    payload = event_payload(event_type)
    payload["subject"]["id"] = "different-id"

    with pytest.raises(
        ValidationError,
        match="event subject id does not match event data id",
    ):
        EventEnvelopeDTO.model_validate(payload)


def test_event_type_subject_data_and_version_mismatches_are_rejected():
    wrong_subject = event_payload("visit.created.v1")
    wrong_subject["subject"]["type"] = "sale"
    with pytest.raises(ValidationError):
        EventEnvelopeDTO.model_validate(wrong_subject)

    wrong_data = event_payload("visit.created.v1")
    wrong_data["data"] = event_payload("sale.created.v1")["data"]
    with pytest.raises(ValidationError):
        EventEnvelopeDTO.model_validate(wrong_data)

    wrong_version = event_payload("visit.created.v1")
    wrong_version["event_type"] = "visit.created.v2"
    with pytest.raises(ValidationError):
        EventEnvelopeDTO.model_validate(wrong_version)

    unknown_data_field = event_payload("sale.created.v1")
    unknown_data_field["data"]["payment_method"] = "cash"
    with pytest.raises(ValidationError):
        EventEnvelopeDTO.model_validate(unknown_data_field)


def test_parsing_performs_no_network_or_database_operations(monkeypatch):
    def unexpected_operation(*args, **kwargs):
        raise AssertionError("external operation attempted")

    monkeypatch.setattr(socket, "socket", unexpected_operation)
    monkeypatch.setattr(sqlite3, "connect", unexpected_operation)

    assert CompanyDTO.model_validate(copy.deepcopy(company_payload())).company_id == "cmp_8f32ab10"
    assert EventEnvelopeDTO.model_validate(event_payload("sale.created.v1")).producer == "guideshop"
