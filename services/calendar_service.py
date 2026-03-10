from calendar import monthrange
from datetime import date, datetime

from database.queries import get_tours_for_month


MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


def get_current_month_period() -> tuple[int, int, str, str]:
    today = date.today()
    year = today.year
    month = today.month

    last_day = monthrange(year, month)[1]
    month_start = date(year, month, 1).isoformat()
    month_end = date(year, month, last_day).isoformat()

    return year, month, month_start, month_end


def build_month_calendar(user_id: int) -> dict:
    year, month, month_start, month_end = get_current_month_period()
    tours = get_tours_for_month(user_id, month_start, month_end)

    days_in_month = monthrange(year, month)[1]
    days_map: dict[int, str] = {}

    for day in range(1, days_in_month + 1):
        days_map[day] = "free"

    for tour in tours:
        start = datetime.strptime(tour["start_date"], "%Y-%m-%d").date()
        end = datetime.strptime(tour["end_date"], "%Y-%m-%d").date()

        for day in range(1, days_in_month + 1):
            current_day = date(year, month, day)
            if start <= current_day <= end:
                if days_map[day] == "free":
                    days_map[day] = tour["company"]

    return {
        "year": year,
        "month": month,
        "month_name": MONTH_NAMES[month],
        "days_map": days_map,
    }


def get_free_days(user_id: int) -> dict:
    calendar_data = build_month_calendar(user_id)
    free_days = []

    for day, value in calendar_data["days_map"].items():
        if value == "free":
            free_days.append(day)

    return {
        "year": calendar_data["year"],
        "month": calendar_data["month"],
        "month_name": calendar_data["month_name"],
        "free_days": free_days,
    }
