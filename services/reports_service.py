from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from config import TIMEZONE
from services.external_sales_service import (
    ExternalSale,
    ExternalSalesService,
    ExternalSaleValidationError,
)
from services.personal_places_service import (
    PersonalPlacesService,
    PersonalPlaceValidationError,
)
from services.tour_service import (
    days_in_range,
    is_guide_operator_managed_entry,
    list_entries,
)
from utils.constants import ENTRY_TYPE_DAY_OFF, PAYMENT_PAID

_BUSINESS_TZ = ZoneInfo(TIMEZONE)
_UNRESOLVED_COMPANY_NAME = "Компания не найдена"


def get_reports_summary(
    user_id: int,
    from_date: str,
    to_date: str,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    filters = filters or {}
    status = filters.get("status", "all")
    payment = filters.get("payment", "all")
    company_filter = filters.get("company", "")
    location_filter = filters.get("location", "")

    entries = list_entries(user_id, from_date, to_date)

    tour_count = 0
    income = 0
    paid_tours = 0
    unpaid_tours = 0
    work_days_set: set[str] = set()

    for entry in entries:
        if entry["type"] == ENTRY_TYPE_DAY_OFF:
            continue
        if status != "all" and entry.get("status") != status:
            continue
        operator_managed = is_guide_operator_managed_entry(entry)
        # Guide Operator has no paid/unpaid fee state — exclude from payment filters.
        if payment != "all":
            if operator_managed or entry.get("payment") != payment:
                continue
        if company_filter and company_filter not in (entry.get("company") or ""):
            continue
        if location_filter and location_filter not in (entry.get("location") or ""):
            continue

        overlap = [
            day
            for day in days_in_range(entry["start_date"], entry["end_date"])
            if from_date <= day <= to_date
        ]
        if not overlap:
            continue

        tour_count += 1
        work_days_set.update(overlap)
        if not operator_managed:
            income += (entry.get("income") or 0) * len(overlap)
            if entry.get("payment") == PAYMENT_PAID:
                paid_tours += 1
            else:
                unpaid_tours += 1

    return {
        "tour_count": tour_count,
        "work_days": len(work_days_set),
        "income": income,
        "paid_tours": paid_tours,
        "unpaid_tours": unpaid_tours,
        "period": {"from": from_date, "to": to_date},
    }


def _parse_iso_calendar_date(value: str) -> date:
    if not isinstance(value, str):
        raise ValueError("invalid date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid date") from exc


def _local_business_date(occurred_at: str) -> date | None:
    if not isinstance(occurred_at, str) or not occurred_at:
        return None
    try:
        parsed = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(_BUSINESS_TZ).date()


def _is_user_facing_commission(sale: ExternalSale) -> bool:
    if sale.status != "active":
        return False
    points = sale.received_points
    if isinstance(points, bool) or not isinstance(points, int) or points <= 0:
        return False
    return True


def get_commission_reports_summary(
    user_id: int,
    from_date: str,
    to_date: str,
) -> dict[str, object]:
    start = _parse_iso_calendar_date(from_date)
    end = _parse_iso_calendar_date(to_date)
    if end < start:
        raise ValueError("invalid date range")

    sales_service = ExternalSalesService()
    places_service = PersonalPlacesService()
    try:
        sales = sales_service.list(user_id=user_id, include_inactive=False)
        places = places_service.list(user_id=user_id, include_inactive=True)
    except (ExternalSaleValidationError, PersonalPlaceValidationError) as exc:
        raise ValueError("invalid commission reports owner") from exc

    place_names = {place.public_id: place.name for place in places}
    grouped: dict[str, dict[str, object]] = {}
    total_commission = 0
    record_count = 0

    for sale in sales:
        if not _is_user_facing_commission(sale):
            continue
        local_day = _local_business_date(sale.occurred_at)
        if local_day is None or local_day < start or local_day > end:
            continue

        amount = int(sale.received_points)
        place_id = sale.personal_place_id
        row = grouped.get(place_id)
        if row is None:
            row = {
                "place_id": place_id,
                "company_name": place_names.get(place_id, _UNRESOLVED_COMPANY_NAME),
                "total_commission": 0,
                "record_count": 0,
            }
            grouped[place_id] = row
        row["total_commission"] = int(row["total_commission"]) + amount
        row["record_count"] = int(row["record_count"]) + 1
        total_commission += amount
        record_count += 1

    by_company = sorted(
        grouped.values(),
        key=lambda item: (
            -int(item["total_commission"]),
            str(item["company_name"]).casefold(),
            str(item["place_id"]),
        ),
    )

    return {
        "total_commission": total_commission,
        "record_count": record_count,
        "by_company": by_company,
        "period": {"from": from_date, "to": to_date},
    }
