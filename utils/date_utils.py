from calendar import monthrange
from datetime import date


def get_month_bounds(year: int, month: int) -> tuple[str, str]:
    last_day = monthrange(year, month)[1]
    month_start = date(year, month, 1).isoformat()
    month_end = date(year, month, last_day).isoformat()
    return month_start, month_end


def shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + offset
    new_year = total // 12
    new_month = total % 12 + 1
    return new_year, new_month
