from datetime import date


WEEKDAY_NAMES_RU = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}


def format_month_calendar(calendar_data: dict) -> str:
    year = calendar_data["year"]
    month = calendar_data["month"]
    month_name = calendar_data["month_name"]
    days_map = calendar_data["days_map"]

    lines = [f"🗓 {month_name} {year}", ""]

    for day, value in days_map.items():
        weekday = WEEKDAY_NAMES_RU[date(year, month, day).weekday()]
        day_str = f"{day:02d}"

        if value == "свободно":
            label = "🟢 свободно"

        elif value.lower() == "у меня выходной":
            label = "🌴 У меня выходной"

        else:
            label = f"🔵 <b>{value}</b>"

        lines.append(f"{weekday} {day_str} — {label}")

    return "\n".join(lines)


def format_free_days(free_days_data: dict) -> str:
    month_name = free_days_data["month_name"]
    year = free_days_data["year"]
    free_days = free_days_data["free_days"]

    if not free_days:
        return f"🟢 Свободные даты — {month_name} {year}\n\nНет свободных дней"

    # форматируем 01 02 03
    days = [f"{day:02d}" for day in free_days]

    # делим по 8 чисел в строке
    rows = [", ".join(days[i:i+8]) for i in range(0, len(days), 8)]

    return f"🟢 Свободные даты — {month_name} {year}\n\n" + "\n".join(rows)
