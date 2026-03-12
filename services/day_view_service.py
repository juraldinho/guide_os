from calendar import monthrange
from datetime import datetime, timedelta

from database.queries import get_tours_for_month_raw


MONTH_NAMES_RU = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def _get_month_bounds(year: int, month: int) -> tuple[str, str]:
    last_day = monthrange(year, month)[1]
    month_start = f"{year:04d}-{month:02d}-01"
    month_end = f"{year:04d}-{month:02d}-{last_day:02d}"
    return month_start, month_end


def _format_day_label(date_obj: datetime, status: str, rows: list[dict]) -> str:
    day_number = date_obj.day
    month_name = MONTH_NAMES_RU[date_obj.month]

    if status == "free":
        return f"{day_number} {month_name} — свободно"

    if status == "multiple":
        return f"{day_number} {month_name} — несколько записей"

    row = rows[0]

    if status == "day_off":
        return f"{day_number} {month_name} — У меня выходной"

    return f"{day_number} {month_name} — {row['company']}"


def build_day_entries_for_month(user_id: int, year: int, month: int) -> list[dict]:
    month_start, month_end = _get_month_bounds(year, month)
    raw_rows = get_tours_for_month_raw(user_id, month_start, month_end)

    days_in_month = monthrange(year, month)[1]

    day_map: dict[str, list[dict]] = {}

    for day in range(1, days_in_month + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        day_map[date_str] = []

    for row in raw_rows:
        start_date = datetime.strptime(row["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(row["end_date"], "%Y-%m-%d").date()

        current_date = start_date
        while current_date <= end_date:
            current_date_str = current_date.strftime("%Y-%m-%d")

            if month_start <= current_date_str <= month_end:
                day_map[current_date_str].append(dict(row))

            current_date += timedelta(days=1)

    result: list[dict] = []

    for day in range(1, days_in_month + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        rows = day_map[date_str]
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")

        if not rows:
            status = "free"
            label = _format_day_label(date_obj, status, rows)
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

        if len(rows) > 1:
            status = "multiple"
            label = _format_day_label(date_obj, status, rows)
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

        if row["entry_type"] == "day_off":
            status = "day_off"
        else:
            status = "tour"

        label = _format_day_label(date_obj, status, rows)

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
