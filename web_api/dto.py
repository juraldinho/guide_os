from __future__ import annotations

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

_DATE_RE = r"^\d{4}-\d{2}-\d{2}$"
_TIME_RE = r"^\d{2}:\d{2}$"


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
    start_time = data.get("startTime") if use_time else None
    end_time = data.get("endTime") if use_time else None
    start_date = data.get("startDate")
    end_date = data.get("endDate") or start_date
    if not isinstance(start_date, str):
        raise ValueError("startDate required")
    if not isinstance(end_date, str):
        raise ValueError("endDate invalid")

    status = data.get("status", STATUS_RESERVED)
    payment = data.get("payment", PAYMENT_UNPAID)
    if status not in (STATUS_RESERVED, STATUS_CONFIRMED):
        raise ValueError("invalid status")
    if payment not in (PAYMENT_PAID, PAYMENT_UNPAID):
        raise ValueError("invalid payment")

    income_raw = data.get("income", 0)
    try:
        income = int(income_raw)
    except (TypeError, ValueError):
        raise ValueError("invalid income")
    if income < 0:
        raise ValueError("invalid income")

    title = data.get("title", "")
    if not isinstance(title, str):
        raise ValueError("invalid title")

    return TourEntryDraft(
        title=title,
        company=str(data.get("company", "")),
        location=str(data.get("location", "")),
        start_date=start_date,
        end_date=end_date,
        start_time=start_time if isinstance(start_time, str) else None,
        end_time=end_time if isinstance(end_time, str) else None,
        status=status,
        payment=payment,
        income=income,
        note=str(data.get("note", "")),
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
