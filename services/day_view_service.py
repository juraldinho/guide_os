from calendar import monthrange
from datetime import datetime

from database.queries import get_tours_for_month_raw
from services.month_day_map import build_month_day_map, get_day_status
from utils.constants import (
    MONTH_SHORT_RU,
    ENTRY_TYPE_DAY_OFF,
)
from utils.date_utils import get_month_bounds


def _format_day_label(date_obj: datetime, status: str, rows: list[dict]) -> str:
    day_number = f"{date_obj.day:02d}"

    month_name = MONTH_SHORT_RU[date_obj.month]

    if status == "free":
        return f"🟢 {day_number} {month_name} — свободно"

    if status == "multiple":
        return f"🟡 {day_number} {month_name} — несколько туров"

    row = rows[0]

    if status == "day_off":
        return f"🌴 {day_number} {month_name} — выходной"

    return f"🔵 {day_number} {month_name} — {row['company']}"


def build_day_entries_for_month(user_id: int, year: int, month: int) -> list[dict]:
    month_start, month_end = get_month_bounds(year, month)
    raw_rows = get_tours_for_month_raw(user_id, month_start, month_end)

    days_in_month = monthrange(year, month)[1]
    day_map = build_month_day_map(raw_rows, year, month)

    result: list[dict] = []

    for day in range(1, days_in_month + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        rows = day_map[date_str]
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")

        status = get_day_status(rows)
        label = _format_day_label(date_obj, status, rows)

        if status == "free":
            result.append(
                {
                    "date": date_str,
                    "status": status,
                    "label": label,
                    "entries": [],
                    "tour_group_id": None,
                    "entry_type": None,
                }
            )
            continue

        if status == "multiple":
            result.append(
                {
                    "date": date_str,
                    "status": status,
                    "label": label,
                    "entries": rows,
                    "tour_group_id": None,
                    "entry_type": None,
                }
            )
            continue

        row = rows[0]

        result.append(
            {
                "date": date_str,
                "status": status,
                "label": label,
                "entries": rows,
                "tour_group_id": row["tour_group_id"],
                "entry_type": row["entry_type"],
            }
        )

    return result
