
from datetime import datetime, timedelta
from uuid import uuid4
import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Optional, TypedDict

from utils.constants import (
    ENTRY_TYPE_TOUR,
    ENTRY_TYPE_DAY_OFF,
    STATUS_RESERVED,
    STATUS_CONFIRMED,
    PAYMENT_PAID,
    PAYMENT_UNPAID,
    DAY_OFF_LABEL,
    DAY_OFF_TITLE,
    SOURCE_GUIDE_OS_BOT,
    SOURCE_MINI_APP,
    SOURCE_GUIDE_OPERATOR,
    SOURCE_DISPLAY,
)

from database.queries import (
    create_tour,
    get_guide_operator_assignment,
    get_tours_for_month,
    get_tour_by_id,
    delete_tour_by_id,
    delete_tours_by_group_id,
    update_tour_company,
    update_tour_company_by_group,
    update_tour_city,
    update_tour_city_by_group,
    update_tour_income,
    update_tour_income_by_group,
    update_tour_note,
    update_tour_note_by_group,
    update_tour_status,
    update_tour_status_by_group,
    update_tour_payment_status,
    update_tour_payment_status_by_group,
    update_tour_dates,
    get_tours_in_range,
    get_tours_by_group_id,
    update_tour_extended,
    update_tour_extended_by_group,
)

from services.date_parser import parse_date_input


def get_conflicting_dates(
    user_id: int,
    date_text: str,
    exclude_tour_id: int | None = None,
    exclude_tour_group_id: str | None = None,
) -> list[str]:
    intervals = _parse_single_iso_date(date_text)

    if intervals is None:
        intervals = parse_date_input(date_text)

    conflict_dates: set[str] = set()

    for interval in intervals:
        start_date = interval["start_date"]
        end_date = interval["end_date"]

        rows = get_tours_in_range(user_id, start_date, end_date)

        if not rows:
            continue

        requested_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        requested_end = datetime.strptime(end_date, "%Y-%m-%d").date()

        for row in rows:
            if exclude_tour_id is not None and row["id"] == exclude_tour_id:
                continue
            if exclude_tour_group_id is not None and row["tour_group_id"] == exclude_tour_group_id:
                continue

            row_start = datetime.strptime(row["start_date"], "%Y-%m-%d").date()
            row_end = datetime.strptime(row["end_date"], "%Y-%m-%d").date()

            overlap_start = max(requested_start, row_start)
            overlap_end = min(requested_end, row_end)

            current = overlap_start
            while current <= overlap_end:
                conflict_dates.add(current.strftime("%Y-%m-%d"))
                current = current.fromordinal(current.toordinal() + 1)

    return sorted(conflict_dates)

def _parse_single_iso_date(date_text: str) -> list[dict] | None:
    date_text = date_text.strip()

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        return None

    try:
        datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        return None

    return [
        {
            "start_date": date_text,
            "end_date": date_text,
        }
    ]

def save_tour(
    user_id: int,
    company: str,
    city: str,
    date_text: str,
    status: str,
    income: int | None = None,
    entry_type: str = ENTRY_TYPE_TOUR,
) -> None:
    intervals = _parse_single_iso_date(date_text)

    if intervals is None:
        intervals = parse_date_input(date_text)

    tour_group_id = str(uuid4())

    for interval in intervals:
        create_tour(
            user_id=user_id,
            company=company.strip(),
            city=city.strip(),
            start_date=interval["start_date"],
            end_date=interval["end_date"],
            status=status.strip(),
            income=income,
            entry_type=entry_type,
            tour_group_id=tour_group_id,
        )

def save_day_off(user_id: int, date_text: str) -> None:
    save_tour(
        user_id=user_id,
        company=DAY_OFF_LABEL,
        city="—",
        date_text=date_text,
        status=STATUS_CONFIRMED,
        income=0,
        entry_type=ENTRY_TYPE_DAY_OFF,
    )

def get_current_month_tours(user_id: int) -> list[dict]:
    now = datetime.now()
    month_start = now.replace(day=1).strftime("%Y-%m-%d")

    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month + 1, day=1)

    month_end = next_month.strftime("%Y-%m-%d")

    return get_tours_for_month(user_id, month_start, month_end)


def get_tour(user_id: int, tour_id: int) -> dict | None:
    return get_tour_by_id(user_id, tour_id)


def is_operator_managed_tour(tour: dict | None) -> bool:
    if not tour:
        return False
    return (tour.get("source") or SOURCE_GUIDE_OS_BOT) == SOURCE_GUIDE_OPERATOR


def delete_tour(user_id: int, tour_id: int) -> bool:
    tour = get_tour_by_id(user_id, tour_id)
    if not tour:
        return False
    if is_operator_managed_tour(tour):
        return False

    tour_group_id = tour.get("tour_group_id")
    if tour_group_id:
        return delete_tours_by_group_id(user_id, tour_group_id) > 0

    return delete_tour_by_id(user_id, tour_id)

def edit_tour_company(user_id: int, tour_id: int, company: str) -> bool:
    company = company.strip()

    if not company:
        return False

    tour = get_tour_by_id(user_id, tour_id)
    if not tour or is_operator_managed_tour(tour):
        return False

    tour_group_id = tour.get("tour_group_id")
    if tour_group_id:
        return update_tour_company_by_group(user_id, tour_group_id, company)

    return update_tour_company(user_id, tour_id, company)

def edit_tour_city(user_id: int, tour_id: int, city: str) -> bool:
    city = city.strip()

    if not city:
        return False

    tour = get_tour_by_id(user_id, tour_id)
    if not tour or is_operator_managed_tour(tour):
        return False

    tour_group_id = tour.get("tour_group_id")
    if tour_group_id:
        return update_tour_city_by_group(user_id, tour_group_id, city)

    return update_tour_city(user_id, tour_id, city)

def edit_tour_income(user_id: int, tour_id: int, income: int) -> bool:
    if income < 0:
        return False

    tour = get_tour_by_id(user_id, tour_id)
    if not tour or is_operator_managed_tour(tour):
        return False

    tour_group_id = tour.get("tour_group_id")
    if tour_group_id:
        return update_tour_income_by_group(user_id, tour_group_id, income)

    return update_tour_income(user_id, tour_id, income)

def edit_tour_note(user_id: int, tour_id: int, note: str) -> bool:
    note = note.strip()

    if not note:
        note = None

    tour = get_tour_by_id(user_id, tour_id)
    if not tour or is_operator_managed_tour(tour):
        return False

    tour_group_id = tour.get("tour_group_id")
    if tour_group_id:
        return update_tour_note_by_group(user_id, tour_group_id, note)

    return update_tour_note(user_id, tour_id, note)

def edit_tour_status(user_id: int, tour_id: int, status: str) -> bool:
    if status not in (STATUS_RESERVED, STATUS_CONFIRMED):
        return False

    tour = get_tour_by_id(user_id, tour_id)
    if not tour or is_operator_managed_tour(tour):
        return False

    tour_group_id = tour.get("tour_group_id")
    if tour_group_id:
        return update_tour_status_by_group(user_id, tour_group_id, status)

    return update_tour_status(user_id, tour_id, status)


def edit_tour_payment_status(user_id: int, tour_id: int, payment_status: str) -> bool:
    if payment_status not in (PAYMENT_PAID, PAYMENT_UNPAID):
        return False

    tour = get_tour_by_id(user_id, tour_id)
    if not tour or is_operator_managed_tour(tour):
        return False

    tour_group_id = tour.get("tour_group_id")
    if tour_group_id:
        return update_tour_payment_status_by_group(user_id, tour_group_id, payment_status)

    return update_tour_payment_status(user_id, tour_id, payment_status)

def edit_tour_dates(user_id: int, tour_id: int, date_text: str) -> bool:
    tour = get_tour_by_id(user_id, tour_id)
    if not tour or is_operator_managed_tour(tour):
        return False

    intervals = parse_date_input(date_text)

    if len(intervals) != 1:
        return False

    interval = intervals[0]

    return update_tour_dates(
        user_id=user_id,
        tour_id=tour_id,
        start_date=interval["start_date"],
        end_date=interval["end_date"],
    )


class ConflictWarn(TypedDict):
    warn: Literal[True]
    date: str
    existing: dict[str, Any]


class ConflictBlock(TypedDict):
    block: Literal[True]
    date: str
    existing: dict[str, Any]
    reason: str


ConflictResult = Optional[ConflictWarn | ConflictBlock]


@dataclass
class TourEntryDraft:
    title: str
    company: str
    location: str
    start_date: str
    end_date: str
    start_time: str | None = None
    end_time: str | None = None
    status: str = STATUS_RESERVED
    payment: str = PAYMENT_UNPAID
    income: int = 0
    note: str = ""
    source: str = SOURCE_MINI_APP
    entry_type: str = ENTRY_TYPE_TOUR


def days_in_range(start: str, end: str) -> list[str]:
    start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end, "%Y-%m-%d").date()
    out: list[str] = []
    current = start_dt
    while current <= end_dt:
        out.append(current.isoformat())
        current += timedelta(days=1)
    return out


_GO_ASSIGNMENT_NOTE_PREFIX = "go_assignment:"


def is_guide_operator_managed_entry(entry: dict[str, Any]) -> bool:
    """True for Guide Operator calendar projections (entry dict or raw tour row)."""
    if entry.get("guide_operator_assignment_id"):
        return True
    source = entry.get("source")
    if source == SOURCE_GUIDE_OPERATOR:
        return True
    if source == SOURCE_DISPLAY[SOURCE_GUIDE_OPERATOR]:
        return True
    return False


def _parse_guide_operator_assignment_id(
    *, source_key: str | None, group_id: Any, note: Any
) -> str | None:
    if source_key != SOURCE_GUIDE_OPERATOR:
        return None
    if isinstance(group_id, str) and group_id.strip():
        return group_id.strip()
    if isinstance(note, str) and note.startswith(_GO_ASSIGNMENT_NOTE_PREFIX):
        parsed = note[len(_GO_ASSIGNMENT_NOTE_PREFIX) :].strip()
        return parsed or None
    return None


def _attach_guide_operator_meta(entry: dict[str, Any]) -> dict[str, Any]:
    """Expose stable Guide Operator projection metadata for Mini App calendar UX."""
    if entry.get("source") != SOURCE_DISPLAY[SOURCE_GUIDE_OPERATOR]:
        return entry

    assignment_id = entry.get("guide_operator_assignment_id")
    if not assignment_id:
        assignment_id = _parse_guide_operator_assignment_id(
            source_key=SOURCE_GUIDE_OPERATOR,
            group_id=entry.get("group_id"),
            note=entry.get("note"),
        )
    if not assignment_id:
        return entry

    enriched = dict(entry)
    enriched["guide_operator_assignment_id"] = assignment_id
    assignment = get_guide_operator_assignment(assignment_id)
    if assignment is not None:
        enriched["guide_operator_version"] = int(
            assignment.get("active_version_number") or 1
        )
        enriched["guide_operator_version_unread"] = (
            int(assignment.get("active_version_unread") or 0) == 1
        )
        enriched["guide_operator_pending_critical"] = (
            assignment.get("pending_critical_version_number") is not None
        )
    else:
        enriched["guide_operator_version"] = int(
            entry.get("guide_operator_version") or 1
        )
        enriched["guide_operator_version_unread"] = bool(
            entry.get("guide_operator_version_unread")
        )
        enriched["guide_operator_pending_critical"] = bool(
            entry.get("guide_operator_pending_critical")
        )
    return enriched


def row_to_entry_dict(row: dict[str, Any]) -> dict[str, Any]:
    entry_type = row.get("entry_type", ENTRY_TYPE_TOUR)
    source_key = row.get("source") or SOURCE_GUIDE_OS_BOT
    source_display = SOURCE_DISPLAY.get(source_key, source_key)

    day_locations: dict[str, str] | None = None
    raw_locations = row.get("day_locations_json")
    if raw_locations:
        try:
            parsed = json.loads(raw_locations)
            if isinstance(parsed, dict):
                day_locations = {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            day_locations = None

    if entry_type == ENTRY_TYPE_DAY_OFF:
        title = DAY_OFF_TITLE
    else:
        title = row.get("title") or row.get("company") or ""

    is_operator = source_key == SOURCE_GUIDE_OPERATOR
    raw_income = row.get("income")
    entry: dict[str, Any] = {
        "id": str(row["id"]),
        "type": entry_type,
        "title": title,
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "start_time": row.get("start_time"),
        "end_time": row.get("end_time"),
        "status": row.get("status"),
        # Operator MVP has no guide fee / payment state — keep unknown, do not invent 0.
        "payment": None if is_operator else row.get("payment_status"),
        "income": None if is_operator else (raw_income or 0),
        "company": row.get("company"),
        "location": row.get("city"),
        "note": row.get("note"),
        "source": source_display,
        "day_locations": day_locations,
        "group_id": row.get("tour_group_id"),
    }
    assignment_id = _parse_guide_operator_assignment_id(
        source_key=source_key,
        group_id=row.get("tour_group_id"),
        note=row.get("note"),
    )
    if assignment_id:
        entry["guide_operator_assignment_id"] = assignment_id
    return _attach_guide_operator_meta(entry)


def collapse_rows_to_entries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    singles: list[dict[str, Any]] = []

    for row in rows:
        group_id = row.get("tour_group_id")
        if group_id:
            groups.setdefault(group_id, []).append(row)
        else:
            singles.append(row)

    collapsed: list[dict[str, Any]] = []
    for group_rows in groups.values():
        collapsed.append(_merge_group_rows(group_rows))
    for row in singles:
        collapsed.append(row_to_entry_dict(row))

    collapsed.sort(key=lambda e: (e["start_date"], e["id"]))
    return collapsed


def _merge_group_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda r: (r["start_date"], r["id"]))
    merged = dict(ordered[0])
    merged["start_date"] = min(r["start_date"] for r in ordered)
    merged["end_date"] = max(r["end_date"] for r in ordered)

    locations: dict[str, str] = {}
    for row in ordered:
        raw = row.get("day_locations_json")
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    locations.update({str(k): str(v) for k, v in parsed.items()})
            except json.JSONDecodeError:
                continue
    if locations:
        merged["day_locations_json"] = json.dumps(locations, ensure_ascii=False)

    return row_to_entry_dict(merged)


def list_entries(user_id: int, from_date: str, to_date: str) -> list[dict[str, Any]]:
    rows = get_tours_in_range(user_id, from_date, to_date)
    return [
        _attach_guide_operator_meta(entry)
        for entry in collapse_rows_to_entries([dict(row) for row in rows])
    ]


def get_entry(user_id: int, entry_id: str) -> dict[str, Any] | None:
    tour = get_tour_by_id(user_id, int(entry_id))
    if not tour:
        return None

    group_id = tour.get("tour_group_id")
    if group_id:
        rows = get_tours_by_group_id(user_id, group_id)
        entries = collapse_rows_to_entries([dict(row) for row in rows])
        if not entries:
            return None
        return _attach_guide_operator_meta(entries[0])

    return _attach_guide_operator_meta(row_to_entry_dict(dict(tour)))


def _validate_times(start_time: str | None, end_time: str | None) -> None:
    if start_time is None and end_time is None:
        return
    if start_time is None or end_time is None:
        raise ValueError("invalid time pair")
    if start_time >= end_time:
        raise ValueError("end time must be after start time")


def _is_full_day_entry(entry: dict[str, Any]) -> bool:
    return entry.get("type") == ENTRY_TYPE_DAY_OFF or not entry.get("start_time") or not entry.get("end_time")


def _date_in_entry(date: str, entry: dict[str, Any]) -> bool:
    return entry["start_date"] <= date <= entry["end_date"]


def _times_overlap(
    a_start: str,
    a_end: str,
    b_start: str,
    b_end: str,
    a_full: bool,
    b_full: bool,
) -> bool:
    if a_full or b_full:
        return True
    return a_start < b_end and b_start < a_end


def check_entry_conflicts(
    user_id: int,
    draft: TourEntryDraft,
    exclude_id: str | None = None,
) -> ConflictResult:
    if not draft.start_date or not draft.end_date:
        return None

    exclude_group_id: str | None = None
    if exclude_id is not None:
        existing = get_tour_by_id(user_id, int(exclude_id))
        if existing:
            exclude_group_id = existing.get("tour_group_id")

    entries = list_entries(user_id, draft.start_date, draft.end_date)
    probe: dict[str, Any] = {
        "type": draft.entry_type,
        "title": draft.title,
        "start_date": draft.start_date,
        "end_date": draft.end_date,
        "start_time": draft.start_time,
        "end_time": draft.end_time,
        "status": draft.status,
    }

    warning: ConflictResult = None
    for date in days_in_range(draft.start_date, draft.end_date):
        for ex in entries:
            if exclude_id is not None and ex["id"] == exclude_id:
                continue
            if exclude_group_id and ex.get("group_id") == exclude_group_id:
                continue
            if not _date_in_entry(date, ex):
                continue

            if ex["type"] == ENTRY_TYPE_DAY_OFF:
                return {
                    "block": True,
                    "date": date,
                    "existing": ex,
                    "reason": "На этой дате уже отмечен выходной. Измените дату.",
                }

            entry_full = _is_full_day_entry(probe)
            ex_full = _is_full_day_entry(ex)
            overlap = _times_overlap(
                probe.get("start_time") or "00:00",
                probe.get("end_time") or "24:00",
                ex.get("start_time") or "00:00",
                ex.get("end_time") or "24:00",
                entry_full,
                ex_full,
            )

            if overlap:
                time_label = "Весь день" if ex_full else f"{ex['start_time']}–{ex['end_time']}"
                title = ex.get("title") or ex.get("company") or ""
                return {
                    "block": True,
                    "date": date,
                    "existing": ex,
                    "reason": (
                        f"Время нового тура пересекается с туром «{title}» {time_label}. "
                        "Измените время или дату."
                    ),
                }

            if warning is None:
                warning = {"warn": True, "date": date, "existing": ex}

    return warning


def create_tour_entry(user_id: int, draft: TourEntryDraft) -> dict[str, Any]:
    _validate_times(draft.start_time, draft.end_time)

    if draft.entry_type == ENTRY_TYPE_TOUR and not draft.title.strip():
        raise ValueError("title required")

    if draft.end_date < draft.start_date:
        raise ValueError("end date before start date")

    title = draft.title.strip() if draft.entry_type == ENTRY_TYPE_TOUR else DAY_OFF_TITLE
    company = draft.company.strip() if draft.entry_type == ENTRY_TYPE_TOUR else DAY_OFF_LABEL
    city = draft.location.strip() if draft.entry_type == ENTRY_TYPE_TOUR else "—"
    note = draft.note.strip() or None
    tour_group_id = str(uuid4())

    tour_id = create_tour(
        user_id=user_id,
        company=company,
        city=city,
        start_date=draft.start_date,
        end_date=draft.end_date,
        status=draft.status if draft.entry_type == ENTRY_TYPE_TOUR else STATUS_CONFIRMED,
        income=draft.income,
        payment_status=draft.payment,
        note=note,
        entry_type=draft.entry_type,
        tour_group_id=tour_group_id,
        title=title,
        start_time=draft.start_time,
        end_time=draft.end_time,
        source=draft.source,
    )
    return get_entry(user_id, str(tour_id))


def update_tour_entry(user_id: int, entry_id: str, draft: TourEntryDraft) -> dict[str, Any] | None:
    tour = get_tour_by_id(user_id, int(entry_id))
    if not tour or is_operator_managed_tour(tour):
        return None

    _validate_times(draft.start_time, draft.end_time)
    if draft.end_date < draft.start_date:
        raise ValueError("end date before start date")

    updates = {
        "title": draft.title.strip(),
        "company": draft.company.strip(),
        "city": draft.location.strip(),
        "start_date": draft.start_date,
        "end_date": draft.end_date,
        "status": draft.status,
        "income": draft.income,
        "payment_status": draft.payment,
        "note": draft.note.strip() or None,
        "start_time": draft.start_time,
        "end_time": draft.end_time,
        "source": draft.source,
    }

    group_id = tour.get("tour_group_id")
    if group_id:
        update_tour_extended_by_group(user_id, group_id, **updates)
    else:
        update_tour_extended(user_id, int(entry_id), **updates)

    return get_entry(user_id, entry_id)


def create_day_off_entry(user_id: int, start_date: str, end_date: str) -> dict[str, Any]:
    draft = TourEntryDraft(
        title=DAY_OFF_TITLE,
        company=DAY_OFF_LABEL,
        location="—",
        start_date=start_date,
        end_date=end_date,
        status=STATUS_CONFIRMED,
        payment=PAYMENT_UNPAID,
        income=0,
        entry_type=ENTRY_TYPE_DAY_OFF,
        source=SOURCE_MINI_APP,
    )
    return create_tour_entry(user_id, draft)


def update_day_locations(
    user_id: int,
    entry_id: str,
    locations: dict[str, str],
) -> dict[str, Any] | None:
    tour = get_tour_by_id(user_id, int(entry_id))
    if not tour or is_operator_managed_tour(tour):
        return None

    json_str = json.dumps(locations, ensure_ascii=False)
    group_id = tour.get("tour_group_id")
    if group_id:
        update_tour_extended_by_group(user_id, group_id, day_locations_json=json_str)
    else:
        update_tour_extended(user_id, int(entry_id), day_locations_json=json_str)

    return get_entry(user_id, entry_id)


def copy_tour_entry(
    user_id: int,
    entry_id: str,
    new_start: str,
    new_end: str,
) -> dict[str, Any] | None:
    source_entry = get_entry(user_id, entry_id)
    if not source_entry or source_entry["type"] == ENTRY_TYPE_DAY_OFF:
        return None

    draft = TourEntryDraft(
        title=source_entry["title"],
        company=source_entry.get("company") or "",
        location=source_entry.get("location") or "",
        start_date=new_start,
        end_date=new_end,
        start_time=source_entry.get("start_time"),
        end_time=source_entry.get("end_time"),
        status=source_entry.get("status") or STATUS_RESERVED,
        payment=source_entry.get("payment") or PAYMENT_UNPAID,
        income=source_entry.get("income") or 0,
        note=source_entry.get("note") or "",
        source=SOURCE_MINI_APP,
    )
    return create_tour_entry(user_id, draft)
