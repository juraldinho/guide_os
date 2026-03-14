from calendar import monthrange
from datetime import date
from services.month_day_map import build_month_day_map, get_day_status
from utils.constants import (
    MONTH_NAMES_RU,
    FREE_LABEL,
    DAY_OFF_LABEL,
    MULTIPLE_TOURS_LABEL,
)
from utils.date_utils import get_month_bounds, shift_month
from database.queries import get_tours_for_month, get_tours_for_month_raw

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
    raw_rows = get_tours_for_month_raw(user_id, month_start, month_end)

    days_in_month = monthrange(year, month)[1]
    day_map = build_month_day_map(raw_rows, year, month)

    days_map: dict[int, str] = {}

    for day in range(1, days_in_month + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        rows = day_map[date_str]
        status = get_day_status(rows)

        if status == "free":
            days_map[day] = FREE_LABEL
        elif status == "multiple":
            days_map[day] = MULTIPLE_TOURS_LABEL
        elif status == "day_off":
            days_map[day] = DAY_OFF_LABEL
        else:
            days_map[day] = rows[0]["company"]

    return {
        "year": year,
        "month": month,
        "month_name": MONTH_NAMES_RU[month],
        "days_map": days_map,
        "tours": raw_rows,
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
