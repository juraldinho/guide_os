from datetime import datetime

from database.queries import get_tours_by_group_id


def format_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d-%m-%y")


def format_tour_status(status: str) -> str:
    status_map = {
        "reserved": "Бронь",
        "confirmed": "Занято",
        "cancelled": "Отменено",
    }
    return status_map.get(status, status)


def format_payment_status(payment_status: str) -> str:
    payment_map = {
        "paid": "Оплачено",
        "unpaid": "Нет оплаты",
    }
    return payment_map.get(payment_status, payment_status)


def _format_range_for_title(start_date: str, end_date: str) -> str:
    start_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_obj = datetime.strptime(end_date, "%Y-%m-%d")

    if start_date == end_date:
        return end_obj.strftime("%d.%m.%y")

    if start_obj.year == end_obj.year and start_obj.month == end_obj.month:
        return f"{start_obj.strftime('%d')}-{end_obj.strftime('%d.%m.%y')}"

    return f"{start_obj.strftime('%d.%m.%y')}-{end_obj.strftime('%d.%m.%y')}"


def build_tour_title_from_group_rows(group_rows: list[dict]) -> str:
    if not group_rows:
        return "—"

    sorted_rows = sorted(
        group_rows,
        key=lambda row: (row["start_date"], row["end_date"], row["id"]),
    )

    company = sorted_rows[0]["company"].strip()
    ranges = [
        _format_range_for_title(row["start_date"], row["end_date"])
        for row in sorted_rows
    ]
    return f"{','.join(ranges)}-{company}"


def format_tour_card(tour: dict) -> str:
    income = tour["income"] if tour["income"] is not None else "—"
    note = tour["note"] if tour["note"] else "—"

    start_date = format_date(tour["start_date"])
    end_date = format_date(tour["end_date"])
    tour_status = format_tour_status(tour["status"])

    if tour.get("entry_type") == "day_off":
        payment_status = "Нет оплаты"
    else:
        payment_status = format_payment_status(tour["payment_status"])

    return (
        f"🏢 Компания: {tour['company']}\n"
        f"📍 Маршрут: {tour['city']}\n\n"
        f"📅 Даты: {start_date} — {end_date}\n"
        f"📊 Статус: {tour_status}\n"
        f"💳 Оплата: {payment_status}\n"
        f"💰 Доход в день: {income}\n"
        f"📝 Заметка: {note}"
    )


def build_selected_day_entry_text(selected_date: str, row: dict) -> str:
    tour_group_id = row.get("tour_group_id")

    if tour_group_id:
        group_rows = [dict(item) for item in get_tours_by_group_id(row["user_id"], tour_group_id)]
    else:
        group_rows = [row]

    tour_title = build_tour_title_from_group_rows(group_rows)

    income = row["income"] if row["income"] is not None else "—"
    note = row["note"] if row["note"] else "—"

    if row.get("entry_type") == "day_off":
        payment_status = "Нет оплаты"
    else:
        payment_status = format_payment_status(row["payment_status"])

    return (
        f"📅 Дата: {format_date(selected_date)}\n"
        f"🏷 Тур: {tour_title}\n\n"
        f"🏢 Компания: {row['company']}\n"
        f"📍 Маршрут: {row['city']}\n"
        f"📊 Статус: {format_tour_status(row['status'])}\n"
        f"💳 Оплата: {payment_status}\n"
        f"💰 Доход в день: {income}\n"
        f"📝 Заметка: {note}"
    )
