from datetime import date, datetime, timedelta

from database.queries import get_tours_for_month, get_all_tours_for_stats
from services.tour_service import is_guide_operator_managed_entry
from utils.constants import SOURCE_GUIDE_OPERATOR


def _get_month_range(year: int, month: int) -> tuple[date, date]:
    month_start = date(year, month, 1)

    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)

    return month_start, next_month_start


def _parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _calculate_overlap_days(
    tour_start: date,
    tour_end: date,
    period_start: date,
    next_period_start: date,
) -> int:
    overlap_start = max(tour_start, period_start)
    overlap_end = min(tour_end + timedelta(days=1), next_period_start)

    days = (overlap_end - overlap_start).days
    return max(days, 0)


def _filter_work_tours(tours: list[dict]) -> list[dict]:
    return [tour for tour in tours if tour.get("entry_type") == "tour"]


def _iter_overlap_dates(
    tour_start: date,
    tour_end: date,
    period_start: date | None = None,
    period_end_inclusive: date | None = None,
) -> list[date]:
    start = tour_start
    end = tour_end
    if period_start is not None:
        start = max(start, period_start)
    if period_end_inclusive is not None:
        end = min(end, period_end_inclusive)
    if end < start:
        return []
    out: list[date] = []
    current = start
    while current <= end:
        out.append(current)
        current += timedelta(days=1)
    return out


def get_stats_summary(user_id: int, year: int, month: int) -> dict:
    month_start_date, next_month_start_date = _get_month_range(year, month)

    month_start = month_start_date.isoformat()
    month_end = (next_month_start_date - timedelta(days=1)).isoformat()
    month_end_date = next_month_start_date - timedelta(days=1)

    tours = get_tours_for_month(user_id, month_start, month_end)
    tours = _filter_work_tours(tours)

    total_tours = 0
    work_days_set: set[date] = set()
    total_income = 0
    paid_tours = 0
    unpaid_tours = 0

    for tour in tours:
        total_tours += 1

        tour_start = _parse_date(tour["start_date"])
        tour_end = _parse_date(tour["end_date"])
        work_days_set.update(
            _iter_overlap_dates(
                tour_start,
                tour_end,
                month_start_date,
                month_end_date,
            )
        )

        operator_managed = is_guide_operator_managed_entry(tour) or (
            tour.get("source") == SOURCE_GUIDE_OPERATOR
        )
        if operator_managed:
            continue

        days_in_month = _calculate_overlap_days(
            tour_start,
            tour_end,
            month_start_date,
            next_month_start_date,
        )
        daily_income = tour["income"] or 0
        total_income += daily_income * days_in_month

        if tour["payment_status"] == "paid":
            paid_tours += 1
        else:
            unpaid_tours += 1

    return {
        "mode": "month",
        "year": year,
        "month": month,
        "total_tours": total_tours,
        "working_days": len(work_days_set),
        "total_income": total_income,
        "paid_tours": paid_tours,
        "unpaid_tours": unpaid_tours,
    }


def get_all_time_stats_summary(user_id: int) -> dict:
    tours = get_all_tours_for_stats(user_id)
    tours = _filter_work_tours(tours)

    total_tours = 0
    work_days_set: set[date] = set()
    total_income = 0
    paid_tours = 0
    unpaid_tours = 0

    for tour in tours:
        total_tours += 1

        tour_start = _parse_date(tour["start_date"])
        tour_end = _parse_date(tour["end_date"])
        work_days_set.update(_iter_overlap_dates(tour_start, tour_end))

        operator_managed = is_guide_operator_managed_entry(tour) or (
            tour.get("source") == SOURCE_GUIDE_OPERATOR
        )
        if operator_managed:
            continue

        days_count = (tour_end - tour_start).days + 1
        daily_income = tour["income"] or 0
        total_income += daily_income * days_count

        if tour["payment_status"] == "paid":
            paid_tours += 1
        else:
            unpaid_tours += 1

    return {
        "mode": "all_time",
        "total_tours": total_tours,
        "working_days": len(work_days_set),
        "total_income": total_income,
        "paid_tours": paid_tours,
        "unpaid_tours": unpaid_tours,
    }
