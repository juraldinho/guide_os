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
    PointsTransactionDTO,
    SaleDTO,
    VisitDTO,
)


UTC_Z = "2026-08-07T12:30:45Z"
UTC_OFFSET = "2026-08-07T12:30:45+00:00"


def company_payload() -> dict:
    return {"company_id": "company-1", "display_name": "Silk Road", "status": "active"}


def visit_payload() -> dict:
    return {
        "visit_id": "visit-1",
        "company_id": "company-1",
        "guide_os_id": "guide-1",
        "visit_at": UTC_Z,
        "status": "active",
        "tourist_count": 3,
        "created_at": UTC_OFFSET,
        "updated_at": UTC_Z,
    }


def sale_payload() -> dict:
    return {
        "sale_id": "sale-1",
        "visit_id": "visit-1",
        "amount_usd": "125.40",
        "currency": "USD",
        "status": "active",
        "category_id": "category-1",
        "category_name": "Textiles",
        "created_at": UTC_Z,
        "updated_at": UTC_OFFSET,
    }


def points_payload() -> dict:
    return {
        "points_transaction_id": "points-1",
        "sale_id": "sale-1",
        "visit_id": None,
        "amount": "16.00",
        "status": "credited",
        "reason": "Sale reward",
        "calculated_at": UTC_Z,
        "credited_at": UTC_OFFSET,
        "updated_at": UTC_Z,
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
        "schema_version": "1.0",
    }


def test_valid_core_dtos_and_envelopes_accept_z_and_zero_offset():
    assert CompanyDTO.model_validate(company_payload()).company_id == "company-1"
    assert VisitDTO.model_validate(visit_payload()).tourist_count == 3
    assert SaleDTO.model_validate(sale_payload()).amount_usd == "125.40"
    assert PointsTransactionDTO.model_validate(points_payload()).amount == "16.00"

    list_payload = {
        "schema_version": "1.0",
        "request_id": "request-1",
        "data": [company_payload()],
        "page": {"next_cursor": "cursor-2"},
    }
    detail_payload = {
        "schema_version": "1.0",
        "request_id": "request-2",
        "data": visit_payload(),
    }
    assert APIListResponseDTO[CompanyDTO].model_validate(list_payload).data[0].display_name == "Silk Road"
    assert APIDetailResponseDTO[VisitDTO].model_validate(detail_payload).data.visit_id == "visit-1"


@pytest.mark.parametrize("timestamp", ["2026-08-07T12:30:45", "2026-08-07T12:30:45+05:00"])
def test_naive_and_non_utc_timestamps_are_rejected(timestamp):
    payload = visit_payload()
    payload["visit_at"] = timestamp
    with pytest.raises(ValidationError):
        VisitDTO.model_validate(payload)


@pytest.mark.parametrize("value", [125.4, 125, "125", "125.4", "125.400", "1.25e2", "NaN", "Infinity", "1,25", " 1.25"])
def test_money_rejects_numbers_and_malformed_decimal_strings(value):
    payload = sale_payload()
    payload["amount_usd"] = value
    with pytest.raises(ValidationError):
        SaleDTO.model_validate(payload)


@pytest.mark.parametrize("value", [16.0, 16, "16", "16.0", "1.60e1", "+16.00"])
def test_points_reject_numbers_and_malformed_decimal_strings(value):
    payload = points_payload()
    payload["amount"] = value
    with pytest.raises(ValidationError):
        PointsTransactionDTO.model_validate(payload)


@pytest.mark.parametrize("value", ["", "   ", 123, 1.5])
def test_ids_must_be_non_empty_strings(value):
    payload = company_payload()
    payload["company_id"] = value
    with pytest.raises(ValidationError):
        CompanyDTO.model_validate(payload)


def test_unknown_fields_versions_statuses_currency_and_boolean_count_are_rejected():
    payload = company_payload()
    payload["phone"] = "+998000000000"
    with pytest.raises(ValidationError):
        CompanyDTO.model_validate(payload)

    envelope = {"schema_version": "2.0", "request_id": "r1", "data": company_payload()}
    with pytest.raises(ValidationError):
        APIDetailResponseDTO[CompanyDTO].model_validate(envelope)

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


def test_sale_voided_at_invariants():
    active = sale_payload()
    active["voided_at"] = UTC_Z
    with pytest.raises(ValidationError):
        SaleDTO.model_validate(active)

    voided = sale_payload()
    voided["status"] = "voided"
    voided["voided_at"] = None
    with pytest.raises(ValidationError):
        SaleDTO.model_validate(voided)

    voided["voided_at"] = UTC_Z
    assert SaleDTO.model_validate(voided).status.value == "voided"


def test_points_reference_and_credited_at_invariants():
    payload = points_payload()
    payload["sale_id"] = None
    with pytest.raises(ValidationError):
        PointsTransactionDTO.model_validate(payload)

    payload = points_payload()
    payload["credited_at"] = None
    with pytest.raises(ValidationError):
        PointsTransactionDTO.model_validate(payload)

    pending = points_payload()
    pending["status"] = "pending"
    with pytest.raises(ValidationError):
        PointsTransactionDTO.model_validate(pending)

    pending["credited_at"] = None
    with pytest.raises(ValidationError):
        PointsTransactionDTO.model_validate(pending)

    reversed_payload = points_payload()
    reversed_payload["status"] = "reversed"
    assert PointsTransactionDTO.model_validate(reversed_payload).credited_at is not None


@pytest.mark.parametrize("cursor", ["", "   ", 123])
def test_pagination_cursor_must_be_optional_non_empty_string(cursor):
    with pytest.raises(ValidationError):
        PageDTO.model_validate({"next_cursor": cursor})
    assert PageDTO.model_validate({"next_cursor": None}).next_cursor is None


def test_api_error_code_and_retry_after_invariants():
    base = {
        "schema_version": "1.0",
        "request_id": "request-1",
        "code": "rate_limited",
        "message": "Try later",
        "retry_after_seconds": 30,
    }
    assert APIErrorDTO.model_validate(base).retry_after_seconds == 30

    for mutation in (
        {"retry_after_seconds": None},
        {"retry_after_seconds": 0},
        {"retry_after_seconds": True},
        {"code": "not_found", "retry_after_seconds": 30},
        {"code": "not_found", "retry_after_seconds": None},
        {"code": "unsupported", "retry_after_seconds": None},
    ):
        payload = {**base, **mutation}
        with pytest.raises(ValidationError):
            APIErrorDTO.model_validate(payload)


@pytest.mark.parametrize("event_type", ["visit.created.v1", "sale.created.v1", "points.recalculated.v1", "points.credited.v1"])
def test_each_required_event_has_typed_valid_data(event_type):
    parsed = EventEnvelopeDTO.model_validate(event_payload(event_type))
    assert parsed.event_type == event_type
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

    assert CompanyDTO.model_validate(copy.deepcopy(company_payload())).company_id == "company-1"
    assert EventEnvelopeDTO.model_validate(event_payload("sale.created.v1")).producer == "guideshop"
