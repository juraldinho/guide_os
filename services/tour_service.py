from datetime import datetime

from database.queries import (
    create_tour,
    get_tours_for_month,
    get_tour_by_id,
    delete_tour_by_id,
    update_tour_company,
    update_tour_city,
    update_tour_income,
    update_tour_note,
    update_tour_status,
    update_tour_payment_status,
    update_tour_dates,
)

from services.date_parser import parse_date_input


def save_tour(
    user_id: int,
    company: str,
    city: str,
    date_text: str,
    status: str,
    income: int | None = None,
    entry_type: str = "tour",
) -> None:
    intervals = parse_date_input(date_text)

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
        )

def save_day_off(user_id: int, date_text: str) -> None:
    save_tour(
        user_id=user_id,
        company="У меня выходной",
        city="—",
        date_text=date_text,
        status="confirmed",
        income=0,
        entry_type="day_off",
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
    return delete_tour_by_id(user_id, tour_id)

def edit_tour_company(user_id: int, tour_id: int, company: str) -> bool:
    company = company.strip()

    if not company:
        return False

    return update_tour_company(user_id, tour_id, company)

def edit_tour_city(user_id: int, tour_id: int, city: str) -> bool:
    city = city.strip()

    if not city:
        return False

    return update_tour_city(user_id, tour_id, city)

def edit_tour_income(user_id: int, tour_id: int, income: int) -> bool:
    if income < 0:
        return False

    return update_tour_income(user_id, tour_id, income)

def edit_tour_note(user_id: int, tour_id: int, note: str) -> bool:
    note = note.strip()

    if not note:
        note = None

    return update_tour_note(user_id, tour_id, note)

def edit_tour_status(user_id: int, tour_id: int, status: str) -> bool:
    if status not in ("reserved", "confirmed"):
        return False

    return update_tour_status(user_id, tour_id, status)


def edit_tour_payment_status(user_id: int, tour_id: int, payment_status: str) -> bool:
    if payment_status not in ("paid", "unpaid"):
        return False

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
