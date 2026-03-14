import re
from datetime import date, datetime


def resolve_year(day: int, month: int) -> int:
    today = date.today()
    candidate = date(today.year, month, day)

    if candidate >= today:
        return today.year

    return today.year + 1


def build_iso_date(day: int, month: int) -> str:
    year = resolve_year(day, month)
    return date(year, month, day).isoformat()


def parse_day_token(raw: str) -> str:
    raw = raw.strip()

    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
        return parsed.isoformat()
    except ValueError:
        pass

    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})", raw)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        return build_iso_date(day, month)

    match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})", raw)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        return build_iso_date(day, month)

    raise ValueError("Не удалось распознать дату")


def parse_short_same_month_range(raw: str) -> dict[str, str]:
    """
    Поддерживает:
    1-2/06
    1-15/06
    1-2.06
    1-15.06
    """
    text = raw.strip().replace(" ", "")

    match = re.fullmatch(r"(\d{1,2})-(\d{1,2})[/.](\d{1,2})", text)
    if not match:
        raise ValueError("Не удалось распознать диапазон дат")

    start_day = int(match.group(1))
    end_day = int(match.group(2))
    month = int(match.group(3))

    if start_day > end_day:
        raise ValueError("Диапазон дат указан в обратном порядке")

    start_date = build_iso_date(start_day, month)
    end_date = build_iso_date(end_day, month)

    return {
        "start_date": start_date,
        "end_date": end_date,
    }


def parse_full_same_month_range(raw: str) -> dict[str, str]:
    """
    Поддерживает:
    1/06-2/06
    1.06-2.06
    7.03-9.03
    7/03-9/03
    """
    text = raw.strip().replace(" ", "")

    match = re.fullmatch(
        r"(\d{1,2})[/.](\d{1,2})-(\d{1,2})[/.](\d{1,2})",
        text
    )
    if not match:
        raise ValueError("Не удалось распознать диапазон дат")

    start_day = int(match.group(1))
    start_month = int(match.group(2))
    end_day = int(match.group(3))
    end_month = int(match.group(4))

    if start_month != end_month:
        raise ValueError("Пока поддерживаются только диапазоны внутри одного месяца")

    if start_day > end_day:
        raise ValueError("Диапазон дат указан в обратном порядке")

    start_date = build_iso_date(start_day, start_month)
    end_date = build_iso_date(end_day, end_month)

    return {
        "start_date": start_date,
        "end_date": end_date,
    }


def parse_range_token(raw: str) -> dict[str, str]:
    text = raw.strip()

    parsers = (
        parse_full_same_month_range,
        parse_short_same_month_range,
    )

    for parser in parsers:
        try:
            return parser(text)
        except ValueError:
            continue

    raise ValueError("Не удалось распознать диапазон дат")


def parse_date_input(date_text: str) -> list[dict[str, str]]:
    raw = date_text.strip()

    if not raw:
        raise ValueError("Дата не должна быть пустой")

    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not parts:
        raise ValueError("Дата не должна быть пустой")

    intervals: list[dict[str, str]] = []

    for part in parts:
        compact = part.replace(" ", "")

        try:
            single_date = parse_day_token(compact)
            intervals.append(
                {
                    "start_date": single_date,
                    "end_date": single_date,
                }
            )
            continue
        except ValueError:
            pass

        intervals.append(parse_range_token(compact))

    return intervals


def parse_single_date(date_text: str) -> str:
    intervals = parse_date_input(date_text)

    if len(intervals) != 1:
        raise ValueError("Ожидалась одна дата")

    interval = intervals[0]

    if interval["start_date"] != interval["end_date"]:
        raise ValueError("Ожидалась одна дата, а получен диапазон")

    return interval["start_date"]
