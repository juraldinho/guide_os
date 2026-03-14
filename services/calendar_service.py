from calendar import monthrange
from datetime import date, datetime

from database.queries import get_tours_for_month
from utils.constants import MONTH_NAMES_RU, FREE_LABEL
from utils.date_utils import get_month_bounds, shift_month


def get_current_month_period() -> tuple[int, int, str, str]:
    today = date.today()
    year = today.year
    month = today.month

    last_day = monthrange(year, month)[1]
    month_start = date(year, month, 1).isoformat()
    month_end = date(year, month, last_day).isoformat()

    return year, month, month_start, month_end


def build_month_calendar(user_id: int, year: int, month: int) -> dict:
    month_start, month_end = get_month_bounds(year, month)
    tours = get_tours_for_month(user_id, month_start, month_end)

    days_in_month = monthrange(year, month)[1]
    days_map: dict[int, str] = {day: FREE_LABEL for day in range(1, days_in_month + 1)}

    for tour in tours:
        start = datetime.strptime(tour["start_date"], "%Y-%m-%d").date()
        end = datetime.strptime(tour["end_date"], "%Y-%m-%d").date()

        for day in range(1, days_in_month + 1):
            current_day = date(year, month, day)
            if start <= current_day <= end:
                if days_map[day] == FREE_LABEL:
                    days_map[day] = tour["company"]

    return {
        "year": year,
        "month": month,
        "month_name": MONTH_NAMES_RU[month],
        "days_map": days_map,
        "tours": tours,
    }   


def get_month_window(start_year: int, start_month: int) -> list[tuple[int, int]]:
    months = []
    year, month = start_year, start_month

    for i in range(4):
        y, m = shift_month(year, month, i)
        months.append((y, m))

    return months

def get_free_days(user_id: int, year: int, month: int) -> dict:
    calendar_data = build_month_calendar(user_id, year, month)

    free_days = [day for day, value in calendar_data["days_map"].items() if value == FREE_LABEL]

    return {
        "year": year,
        "month": month,
        "month_name": calendar_data["month_name"],
        "free_days": free_days,
    }
def get_month_tours(user_id: int, year: int, month: int) -> list[dict]:
    month_start, month_end = get_month_bounds(year, month)
    return get_tours_for_month(user_id, month_start, month_end)
