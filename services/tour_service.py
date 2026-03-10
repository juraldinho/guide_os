from database.queries import create_tour
from services.date_parser import parse_single_date


def save_tour(
    user_id: int,
    company: str,
    city: str,
    date_text: str,
    status: str,
    income: int | None = None,
) -> None:
    normalized_date = parse_single_date(date_text)

    create_tour(
        user_id=user_id,
        company=company.strip(),
        city=city.strip(),
        start_date=normalized_date,
        end_date=normalized_date,
        status=status.strip(),
        income=income,
    )
