from calendar import monthrange
from datetime import datetime, timedelta

from utils.constants import ENTRY_TYPE_DAY_OFF


def build_month_day_map(rows: list[dict], year: int, month: int) -> dict[str, list[dict]]:
    days_in_month = monthrange(year, month)[1]

    day_map: dict[str, list[dict]] = {}

    for day in range(1, days_in_month + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        day_map[date_str] = []

    for row in rows:
        start_date = datetime.strptime(row["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(row["end_date"], "%Y-%m-%d").date()

        current_date = start_date
        while current_date <= end_date:
            if current_date.year == year and current_date.month == month:
                current_date_str = current_date.strftime("%Y-%m-%d")
                day_map[current_date_str].append(dict(row))

            current_date += timedelta(days=1)

    return day_map


def get_day_status(rows: list[dict]) -> str:
    if not rows:
        return "free"

    if len(rows) > 1:
        return "multiple"

    row = rows[0]

    if row["entry_type"] == ENTRY_TYPE_DAY_OFF:
        return "day_off"

    return "tour"
