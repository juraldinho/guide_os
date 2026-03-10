from datetime import date, datetime


def resolve_year(day: int, month: int) -> int:
    today = date.today()
    candidate = date(today.year, month, day)

    if candidate >= today:
        return today.year
    return today.year + 1


def parse_single_date(date_text: str) -> str:
    raw = date_text.strip()

    # already YYYY-MM-DD
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
        return parsed.isoformat()
    except ValueError:
        pass

    # DD/MM
    try:
        parsed = datetime.strptime(raw, "%d/%m")
        year = resolve_year(parsed.day, parsed.month)
        return date(year, parsed.month, parsed.day).isoformat()
    except ValueError:
        pass

    # DD.MM
    try:
        parsed = datetime.strptime(raw, "%d.%m")
        year = resolve_year(parsed.day, parsed.month)
        return date(year, parsed.month, parsed.day).isoformat()
    except ValueError:
        pass

    raise ValueError("Не удалось распознать дату")