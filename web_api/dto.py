from __future__ import annotations

import datetime
import math
import re
from typing import Any

from utils.constants import (
    ENTRY_TYPE_DAY_OFF,
    PAYMENT_PAID,
    PAYMENT_UNPAID,
    STATUS_CONFIRMED,
    STATUS_RESERVED,
)

from services.tour_service import TourEntryDraft, SOURCE_MINI_APP


GUIDE_TYPES_STUB: list[dict[str, Any]] = [
    {"type": "local", "label": "Локальный гид", "geo": ["Самарканд"]},
    {"type": "route", "label": "Маршрутный гид", "geo": ["Самарканд", "Бухара"]},
]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_ENTRY_ID_RE = re.compile(r"^[1-9]\d{0,18}$")
_MAX_SQLITE_INTEGER = 2**63 - 1


def parse_entry_id(raw: str) -> int | None:
    if not isinstance(raw, str) or raw != raw.strip() or not raw:
        return None
    if _ENTRY_ID_RE.fullmatch(raw) is None:
        return None
    value = int(raw)
    if value > _MAX_SQLITE_INTEGER:
        return None
    return value


def validate_iso_calendar_date(value: str) -> str:
    if not isinstance(value, str) or _DATE_RE.fullmatch(value) is None:
        raise ValueError("invalid date")
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid date")
    return value


def validate_date_range(start_date: str, end_date: str) -> tuple[str, str]:
    start = validate_iso_calendar_date(start_date)
    end = validate_iso_calendar_date(end_date)
    if end < start:
        raise ValueError("invalid date range")
    return start, end


def _validate_time_value(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid time")
    if value != value.strip():
        raise ValueError("invalid time")
    if _TIME_RE.fullmatch(value) is None:
        raise ValueError("invalid time")
    hour = int(value[0:2])
    minute = int(value[3:5])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("invalid time")
    return value


def _validate_tour_times(
    use_time: bool,
    start_time: Any,
    end_time: Any,
) -> tuple[str | None, str | None]:
    if not use_time:
        return None, None
    if start_time is None or end_time is None:
        raise ValueError("invalid time")
    return _validate_time_value(start_time), _validate_time_value(end_time)


def _optional_string_field(data: dict[str, Any], key: str, default: str = "") -> str:
    if key not in data:
        return default
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"invalid {key}")
    return value


def normalize_day_locations(locations: Any) -> dict[str, str]:
    if not isinstance(locations, dict):
        raise ValueError("invalid locations")
    normalized: dict[str, str] = {}
    for key, value in locations.items():
        if not isinstance(key, str):
            raise ValueError("invalid locations")
        date_key = validate_iso_calendar_date(key)
        if not isinstance(value, str):
            raise ValueError("invalid locations")
        normalized[date_key] = value
    return normalized


def parse_income_value(raw: Any) -> int:
    if isinstance(raw, bool) or raw is None:
        raise ValueError("invalid income")
    if isinstance(raw, float):
        if not math.isfinite(raw) or not raw.is_integer():
            raise ValueError("invalid income")
        raw = int(raw)
    elif isinstance(raw, str):
        stripped = raw.strip()
        lowered = stripped.lower()
        if lowered in {"nan", "infinity", "-infinity", "inf", "-inf"}:
            raise ValueError("invalid income")
        try:
            raw = int(stripped)
        except ValueError:
            raise ValueError("invalid income")
    elif not isinstance(raw, int):
        raise ValueError("invalid income")
    if raw < 0 or raw > _MAX_SQLITE_INTEGER:
        raise ValueError("invalid income")
    return raw


def entry_to_api(entry: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": entry["id"],
        "type": entry["type"],
        "title": entry["title"],
        "startDate": entry["start_date"],
        "endDate": entry["end_date"],
        "startTime": entry.get("start_time"),
        "endTime": entry.get("end_time"),
        "income": entry.get("income") or 0,
        "company": entry.get("company"),
        "location": entry.get("location"),
        "note": entry.get("note"),
        "source": entry.get("source"),
    }
    if entry["type"] != ENTRY_TYPE_DAY_OFF:
        payload["status"] = entry.get("status")
        payload["payment"] = entry.get("payment")
    if entry.get("day_locations"):
        payload["dayLocations"] = entry["day_locations"]
    if entry.get("group_id"):
        payload["groupId"] = entry["group_id"]
    return payload


def reports_summary_to_api(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "tourCount": summary["tour_count"],
        "workDays": summary["work_days"],
        "income": summary["income"],
        "paidTours": summary["paid_tours"],
        "unpaidTours": summary["unpaid_tours"],
        "period": {
            "from": summary["period"]["from"],
            "to": summary["period"]["to"],
        },
    }


def availability_preview_to_api(preview: dict[str, Any]) -> dict[str, Any]:
    return {
        "heading": preview["heading"],
        "text": preview["text"],
        "freeDates": preview["free_dates"],
        "ranges": [
            {"start": item["start"], "end": item["end"]}
            for item in preview.get("ranges", [])
        ],
    }


def profile_to_api(user_id: int, display_name: str | None, notifications: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": display_name or "",
        "telegramId": str(user_id),
        "types": [dict(item) for item in GUIDE_TYPES_STUB],
        "notifications": {
            "enabled": bool(notifications.get("notifications_enabled")),
            "time": notifications.get("notification_time") or "21:00",
        },
    }


def tour_draft_from_body(data: dict[str, Any]) -> TourEntryDraft:
    use_time = bool(data.get("useTime"))
    start_time, end_time = _validate_tour_times(
        use_time,
        data.get("startTime"),
        data.get("endTime"),
    )
    start_date = data.get("startDate")
    end_date = data.get("endDate") or start_date
    if not isinstance(start_date, str):
        raise ValueError("startDate required")
    if not isinstance(end_date, str):
        raise ValueError("endDate invalid")
    start_date, end_date = validate_date_range(start_date, end_date)

    status = data.get("status", STATUS_RESERVED)
    payment = data.get("payment", PAYMENT_UNPAID)
    if status not in (STATUS_RESERVED, STATUS_CONFIRMED):
        raise ValueError("invalid status")
    if payment not in (PAYMENT_PAID, PAYMENT_UNPAID):
        raise ValueError("invalid payment")

    income = parse_income_value(data.get("income", 0))

    if "title" in data and not isinstance(data.get("title"), str):
        raise ValueError("invalid title")
    title = data.get("title", "")
    company = _optional_string_field(data, "company")
    location = _optional_string_field(data, "location")
    note = _optional_string_field(data, "note")

    return TourEntryDraft(
        title=title,
        company=company,
        location=location,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        status=status,
        payment=payment,
        income=income,
        note=note,
        source=SOURCE_MINI_APP,
    )


def conflict_to_error(conflict: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    existing = entry_to_api(conflict["existing"])
    if conflict.get("block"):
        if conflict["existing"].get("type") == ENTRY_TYPE_DAY_OFF:
            return (
                "day_off_conflict",
                conflict.get("reason", "На этой дате уже отмечен выходной. Измените дату."),
                {
                    "conflict_kind": "day_off_conflict",
                    "date": conflict["date"],
                    "existing_entry": existing,
                    "reason_code": "day_off",
                },
            )
        return (
            "time_conflict",
            conflict.get("reason", "Время тура пересекается с существующей записью."),
            {
                "conflict_kind": "time_conflict",
                "date": conflict["date"],
                "existing_entry": existing,
                "reason_code": "time_overlap",
            },
        )
    return (
        "date_warning",
        "На этой дате уже есть тур. Время не пересекается — сохранение возможно.",
        {
            "conflict_kind": "date_warning",
            "date": conflict["date"],
            "existing_entry": existing,
            "ack_field": "ack_date_warning",
        },
    )
