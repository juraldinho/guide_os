from datetime import date


WEEKDAY_NAMES = {
    0: "Mo",
    1: "Tu",
    2: "We",
    3: "Th",
    4: "Fr",
    5: "Sa",
    6: "Su",
}


def format_month_calendar(calendar_data: dict) -> str:
    year = calendar_data["year"]
    month = calendar_data["month"]
    month_name = calendar_data["month_name"]
    days_map = calendar_data["days_map"]

    lines = [f"{month_name} {year}", ""]

    for day, value in days_map.items():
        weekday = WEEKDAY_NAMES[date(year, month, day).weekday()]
        lines.append(f"{weekday} {day:<2}  {value}")

    return "\n".join(lines)


def format_free_days(free_days_data: dict) -> str:
    month_name = free_days_data["month_name"]
    year = free_days_data["year"]
    free_days = free_days_data["free_days"]

    if not free_days:
        return f"Free dates — {month_name} {year}\n\nNo free days"

    days_text = ", ".join(str(day) for day in free_days)
    return f"Free dates — {month_name} {year}\n\n{days_text}"
