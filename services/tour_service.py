from database.queries import create_tour

from datetime import datetime

from database.queries import create_tour, get_tours_for_month
from services.date_parser import parse_date_input


def save_tour(
    user_id: int,
    company: str,
    city: str,
    date_text: str,
    status: str,
    income: int | None = None,
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
        )


def get_current_month_tours(user_id: int):
    now = datetime.now()
    month_start = now.replace(day=1).strftime("%Y-%m-%d")

    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month + 1, day=1)

    month_end = next_month.strftime("%Y-%m-%d")
    return get_tours_for_month(user_id, month_start, month_end)
