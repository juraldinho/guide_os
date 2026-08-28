from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any

from utils.constants import (
    ENTRY_TYPE_DAY_OFF,
    MONTH_NAMES_IN_RU,
    MONTH_NAMES_RU_GENITIVE,
    STATUS_CONFIRMED,
    STATUS_RESERVED,
)

from services.tour_service import days_in_range, list_entries


def _parse_date(date_text: str) -> datetime:
    return datetime.strptime(date_text, "%Y-%m-%d")


def _fmt_date(date_text: str) -> str:
    dt = _parse_date(date_text)
    return f"{dt.day} {MONTH_NAMES_RU_GENITIVE[dt.month]}"


def _fmt_date_short(date_text: str) -> str:
    dt = _parse_date(date_text)
    return f"{dt.day}.{dt.month:02d}"


def _is_full_calendar_month(from_date: str, to_date: str) -> bool:
    start = _parse_date(from_date)
    end = _parse_date(to_date)
    last_day = monthrange(end.year, end.month)[1]
    return (
        start.day == 1
        and end.day == last_day
        and start.month == end.month
        and start.year == end.year
    )


def build_free_dates_heading(from_date: str, to_date: str) -> str:
    if _is_full_calendar_month(from_date, to_date):
        month = _parse_date(from_date).month
        return f"Свободные даты в {MONTH_NAMES_IN_RU[month]}:"
    return f"Свободные даты с {_fmt_date(from_date)} по {_fmt_date(to_date)}:"


def _compress_ranges(dates: list[str]) -> list[dict[str, str]]:
    if not dates:
        return []

    sorted_dates = sorted(dates)
    out: list[dict[str, str]] = []
    start = sorted_dates[0]
    end = sorted_dates[0]

    for i in range(1, len(sorted_dates)):
        prev = _parse_date(end)
        next_day = (prev + timedelta(days=1)).strftime("%Y-%m-%d")
        if next_day == sorted_dates[i]:
            end = sorted_dates[i]
        else:
            out.append({"start": start, "end": end})
            start = sorted_dates[i]
            end = sorted_dates[i]

    out.append({"start": start, "end": end})
    return out


def day_status(date_text: str, entries: list[dict[str, Any]]) -> str:
    day_entries = [e for e in entries if e["start_date"] <= date_text <= e["end_date"]]
    if not day_entries:
        return "free"
    if any(e["type"] == ENTRY_TYPE_DAY_OFF for e in day_entries):
        return "dayoff"
    tours_only = [e for e in day_entries if e["type"] != ENTRY_TYPE_DAY_OFF]
    if any(e.get("status") == STATUS_CONFIRMED for e in tours_only):
        return "confirmed"
    if any(e.get("status") == STATUS_RESERVED for e in tours_only):
        return "reserved"
    return "free"


def build_availability_preview(
    user_id: int,
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    entries = list_entries(user_id, from_date, to_date)
    free_dates = [
        day
        for day in days_in_range(from_date, to_date)
        if day_status(day, entries) == "free"
    ]

    heading = build_free_dates_heading(from_date, to_date)
    if not free_dates:
        return {
            "heading": heading,
            "text": "",
            "free_dates": [],
            "ranges": [],
        }

    ranges = _compress_ranges(free_dates)
    parts: list[str] = []
    for range_item in ranges:
        start = range_item["start"]
        end = range_item["end"]
        if start == end:
            dt = _parse_date(start)
            parts.append(f"{dt.day} {MONTH_NAMES_RU_GENITIVE[dt.month]}")
        else:
            a = _parse_date(start)
            b = _parse_date(end)
            if a.month == b.month:
                parts.append(
                    f"{a.day}–{b.day} {MONTH_NAMES_RU_GENITIVE[a.month]}"
                )
            else:
                parts.append(f"{_fmt_date_short(start)}–{_fmt_date_short(end)}")

    joined = (
        f"{', '.join(parts[:-1])} и {parts[-1]}"
        if len(parts) > 1
        else parts[0]
    )
    text = f"{heading} {joined}."

    return {
        "heading": heading,
        "text": text,
        "free_dates": free_dates,
        "ranges": ranges,
    }
