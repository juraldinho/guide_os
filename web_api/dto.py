from __future__ import annotations

import datetime
import json
import math
import re
from dataclasses import dataclass
from typing import Any

from utils.constants import (
    ENTRY_TYPE_DAY_OFF,
    PAYMENT_PAID,
    PAYMENT_UNPAID,
    STATUS_CONFIRMED,
    STATUS_RESERVED,
)

from services.tour_service import TourEntryDraft, SOURCE_MINI_APP


GUIDE_TYPE_CODES = frozenset({"local", "route", "accompanying"})
GUIDE_TYPE_LABELS: dict[str, str] = {
    "local": "Локальный гид",
    "route": "Маршрутный гид",
    "accompanying": "Сопровождающий гид",
}
CANONICAL_GEOGRAPHY = frozenset(
    {
        "Самарканд",
        "Ташкент",
        "Бухара",
        "Хива",
        "Каракалпакстан",
        "Сурхандарья",
        "Шахрисабз",
        "Ферганская долина",
    }
)
MAX_GUIDE_LANGUAGES = 20
MAX_GUIDE_LANGUAGE_LENGTH = 50

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


def _normalize_guide_type_entry(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("invalid types")
    if "label" in item:
        raise ValueError("invalid types")
    type_code = item.get("type")
    if not isinstance(type_code, str) or type_code not in GUIDE_TYPE_CODES:
        raise ValueError("invalid types")
    all_uzbekistan = item.get("allUzbekistan", False)
    if not isinstance(all_uzbekistan, bool):
        raise ValueError("invalid types")
    geo_raw = item.get("geo")
    if not isinstance(geo_raw, list):
        raise ValueError("invalid types")
    geo: list[str] = []
    for value in geo_raw:
        if not isinstance(value, str):
            raise ValueError("invalid types")
        if value not in CANONICAL_GEOGRAPHY:
            raise ValueError("invalid types")
        geo.append(value)
    if len(geo) != len(set(geo)):
        raise ValueError("invalid types")
    if type_code == "local":
        if all_uzbekistan:
            raise ValueError("invalid types")
        if len(geo) != 1:
            raise ValueError("invalid types")
    else:
        if all_uzbekistan and geo:
            raise ValueError("invalid types")
        if not all_uzbekistan and not geo:
            raise ValueError("invalid types")
    return {
        "type": type_code,
        "label": GUIDE_TYPE_LABELS[type_code],
        "geo": geo,
        "allUzbekistan": all_uzbekistan,
    }


def normalize_guide_types(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("invalid types")
    seen_types: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for item in value:
        entry = _normalize_guide_type_entry(item)
        if entry["type"] in seen_types:
            raise ValueError("invalid types")
        seen_types.add(entry["type"])
        normalized.append(entry)
    return normalized


def normalize_guide_languages(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("invalid languages")
    if len(value) > MAX_GUIDE_LANGUAGES:
        raise ValueError("invalid languages")
    seen_lower: set[str] = set()
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("invalid languages")
        cleaned = item.strip()
        if not cleaned:
            raise ValueError("invalid languages")
        if len(cleaned) > MAX_GUIDE_LANGUAGE_LENGTH:
            raise ValueError("invalid languages")
        key = cleaned.casefold()
        if key in seen_lower:
            raise ValueError("invalid languages")
        seen_lower.add(key)
        normalized.append(cleaned)
    return normalized


def guide_types_for_storage(normalized: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": item["type"],
            "geo": list(item["geo"]),
            "allUzbekistan": item["allUzbekistan"],
        }
        for item in normalized
    ]


def _guide_types_storage_to_api_input(data: list[Any]) -> list[dict[str, Any]]:
    api_input: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("invalid types")
        api_input.append(
            {
                "type": item.get("type"),
                "geo": item.get("geo", []),
                "allUzbekistan": item.get("allUzbekistan", False),
            }
        )
    return api_input


def decode_guide_types_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    try:
        return normalize_guide_types(_guide_types_storage_to_api_input(data))
    except ValueError:
        return []


def decode_guide_languages_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    try:
        return normalize_guide_languages(data)
    except ValueError:
        return []


@dataclass(frozen=True)
class ProfilePatchUpdate:
    display_name: str | None = None
    guide_types: list[dict[str, Any]] | None = None
    guide_languages: list[str] | None = None
    notifications_enabled: bool | None = None
    notification_time: str | None = None


def _validate_notification_time(value: Any) -> str:
    try:
        return _validate_time_value(value)
    except ValueError:
        raise ValueError("invalid notifications")


def normalize_profile_notifications(value: Any) -> tuple[bool | None, str | None]:
    if value is None:
        raise ValueError("invalid notifications")
    if not isinstance(value, dict):
        raise ValueError("invalid notifications")
    enabled: bool | None = None
    time_value: str | None = None
    if "enabled" in value:
        enabled_raw = value["enabled"]
        if not isinstance(enabled_raw, bool):
            raise ValueError("invalid notifications")
        enabled = enabled_raw
    if "time" in value:
        time_value = _validate_notification_time(value["time"])
    return enabled, time_value


def parse_profile_patch_body(data: dict[str, Any]) -> ProfilePatchUpdate:
    if "telegramId" in data:
        raise ValueError("invalid telegramId")

    display_name: str | None = None
    guide_types: list[dict[str, Any]] | None = None
    guide_languages: list[str] | None = None
    notifications_enabled: bool | None = None
    notification_time: str | None = None

    if "name" in data:
        name = data["name"]
        if name is None or not isinstance(name, str):
            raise ValueError("invalid name")
        display_name = name.strip()

    if "types" in data:
        types_value = data["types"]
        if types_value is None:
            raise ValueError("invalid types")
        guide_types = guide_types_for_storage(normalize_guide_types(types_value))

    if "languages" in data:
        languages_value = data["languages"]
        if languages_value is None:
            raise ValueError("invalid languages")
        guide_languages = normalize_guide_languages(languages_value)

    if "notifications" in data:
        enabled, time_value = normalize_profile_notifications(data["notifications"])
        notifications_enabled = enabled
        notification_time = time_value

    return ProfilePatchUpdate(
        display_name=display_name,
        guide_types=guide_types,
        guide_languages=guide_languages,
        notifications_enabled=notifications_enabled,
        notification_time=notification_time,
    )


def profile_to_api(
    user_id: int,
    display_name: str | None,
    notifications: dict[str, Any],
    types: list[dict[str, Any]],
    languages: list[str],
) -> dict[str, Any]:
    return {
        "name": display_name or "",
        "telegramId": str(user_id),
        "types": [dict(item) for item in types],
        "languages": list(languages),
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
