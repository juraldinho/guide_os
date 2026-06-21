
from datetime import datetime
from uuid import uuid4
import re

from utils.constants import (
    ENTRY_TYPE_TOUR,
    ENTRY_TYPE_DAY_OFF,
    STATUS_RESERVED,
    STATUS_CONFIRMED,
    PAYMENT_PAID,
    PAYMENT_UNPAID,
    DAY_OFF_LABEL,
)

from database.queries import (
    create_tour,
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

def delete_tour(user_id: int, tour_id: int) -> bool:
    tour = get_tour_by_id(user_id, tour_id)
    if not tour:
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
    if not tour:
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
    if not tour:
        return False

    tour_group_id = tour.get("tour_group_id")
    if tour_group_id:
        return update_tour_city_by_group(user_id, tour_group_id, city)

    return update_tour_city(user_id, tour_id, city)

def edit_tour_income(user_id: int, tour_id: int, income: int) -> bool:
    if income < 0:
        return False

    tour = get_tour_by_id(user_id, tour_id)
    if not tour:
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
    if not tour:
        return False

    tour_group_id = tour.get("tour_group_id")
    if tour_group_id:
        return update_tour_note_by_group(user_id, tour_group_id, note)

    return update_tour_note(user_id, tour_id, note)

def edit_tour_status(user_id: int, tour_id: int, status: str) -> bool:
    if status not in (STATUS_RESERVED, STATUS_CONFIRMED):
        return False

    tour = get_tour_by_id(user_id, tour_id)
    if not tour:
        return False

    tour_group_id = tour.get("tour_group_id")
    if tour_group_id:
        return update_tour_status_by_group(user_id, tour_group_id, status)

    return update_tour_status(user_id, tour_id, status)


def edit_tour_payment_status(user_id: int, tour_id: int, payment_status: str) -> bool:
    if payment_status not in (PAYMENT_PAID, PAYMENT_UNPAID):
        return False

    tour = get_tour_by_id(user_id, tour_id)
    if not tour:
        return False

    tour_group_id = tour.get("tour_group_id")
    if tour_group_id:
        return update_tour_payment_status_by_group(user_id, tour_group_id, payment_status)

    return update_tour_payment_status(user_id, tour_id, payment_status)

def edit_tour_dates(user_id: int, tour_id: int, date_text: str) -> bool:
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
