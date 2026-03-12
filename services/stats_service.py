from datetime import date, datetime, timedelta

from database.queries import get_tours_for_month, get_all_tours_for_stats


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
    return [tour for tour in tours if tour.get("entry_type", "tour") == "tour"]


def get_stats_summary(user_id: int, year: int, month: int) -> dict:
    month_start_date, next_month_start_date = _get_month_range(year, month)

    month_start = month_start_date.isoformat()
    month_end = (next_month_start_date - timedelta(days=1)).isoformat()

    tours = get_tours_for_month(user_id, month_start, month_end)
    tours = _filter_work_tours(tours)

    total_tours = 0
    working_days = 0
    total_income = 0
    paid_tours = 0
    unpaid_tours = 0

    for tour in tours:
        total_tours += 1

        tour_start = _parse_date(tour["start_date"])
        tour_end = _parse_date(tour["end_date"])

        days_in_month = _calculate_overlap_days(
            tour_start,
            tour_end,
            month_start_date,
            next_month_start_date,
        )

        working_days += days_in_month

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
        "working_days": working_days,
        "total_income": total_income,
        "paid_tours": paid_tours,
        "unpaid_tours": unpaid_tours,
    }


def get_all_time_stats_summary(user_id: int) -> dict:
    tours = get_all_tours_for_stats(user_id)
    tours = _filter_work_tours(tours)

    total_tours = 0
    working_days = 0
    total_income = 0
    paid_tours = 0
    unpaid_tours = 0

    for tour in tours:
        total_tours += 1

        tour_start = _parse_date(tour["start_date"])
        tour_end = _parse_date(tour["end_date"])

        days_count = (tour_end - tour_start).days + 1
        working_days += days_count

        daily_income = tour["income"] or 0
        total_income += daily_income * days_count

        if tour["payment_status"] == "paid":
            paid_tours += 1
        else:
            unpaid_tours += 1

    return {
        "mode": "all_time",
        "total_tours": total_tours,
        "working_days": working_days,
        "total_income": total_income,
        "paid_tours": paid_tours,
        "unpaid_tours": unpaid_tours,
    }
