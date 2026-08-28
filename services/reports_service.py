from typing import Any

from utils.constants import ENTRY_TYPE_DAY_OFF, PAYMENT_PAID

from services.tour_service import days_in_range, list_entries


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
        if payment != "all" and entry.get("payment") != payment:
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
