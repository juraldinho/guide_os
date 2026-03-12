from datetime import datetime

from database.queries import get_tours_by_group_id, get_tours_for_date


STATUS_LABELS = {
    "reserved": "Бронь",
    "confirmed": "Подтверждено",
    "cancelled": "Отменено",
}

PAYMENT_STATUS_LABELS = {
    "paid": "Оплачено",
    "unpaid": "Не оплачено",
}


def _format_card_date(date_str: str) -> str:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return date_obj.strftime("%d-%m-%y")


def _format_range_for_title(start_date: str, end_date: str) -> str:
    start_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_obj = datetime.strptime(end_date, "%Y-%m-%d")

    if start_date == end_date:
        return end_obj.strftime("%d.%m.%y")

    if start_obj.year == end_obj.year and start_obj.month == end_obj.month:
        return f"{start_obj.strftime('%d')}-{end_obj.strftime('%d.%m.%y')}"

    return f"{start_obj.strftime('%d.%m.%y')}-{end_obj.strftime('%d.%m.%y')}"


def _build_tour_title(group_rows: list[dict]) -> str:
    if not group_rows:
        return "—"

    sorted_rows = sorted(group_rows, key=lambda row: (row["start_date"], row["end_date"], row["id"]))
    company = sorted_rows[0]["company"].strip()

    ranges = [
        _format_range_for_title(row["start_date"], row["end_date"])
        for row in sorted_rows
    ]

    joined_ranges = ",".join(ranges)
    return f"{joined_ranges}-{company}"


def _format_status(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def _format_payment_status(entry_type: str, payment_status: str | None) -> str:
    if entry_type == "day_off":
        return "Нет оплаты"

    if not payment_status:
        return "Не оплачено"

    return PAYMENT_STATUS_LABELS.get(payment_status, payment_status)


def _format_income(income: int | None) -> str:
    if income is None:
        return "—"
    return str(income)


def _format_note(note: str | None) -> str:
    if not note:
        return "—"
    return note.strip()


def build_free_day_card(date_str: str) -> dict:
    text = (
        f"Дата: {_format_card_date(date_str)}\n"
        f"Статус: Свободно"
    )

    return {
        "kind": "free",
        "date": date_str,
        "text": text,
        "entries": [],
    }


def build_day_card_from_row(selected_date: str, row: dict) -> dict:
    tour_group_id = row.get("tour_group_id")

    if tour_group_id:
        group_rows = [dict(item) for item in get_tours_by_group_id(row["user_id"], tour_group_id)]
    else:
        group_rows = [row]

    tour_title = _build_tour_title(group_rows)

    text = (
        f"Тур: {tour_title}\n"
        f"Дата: {_format_card_date(selected_date)}\n"
        f"Компания: {row['company']}\n"
        f"Город: {row['city']}\n"
        f"Статус: {_format_status(row['status'])}\n"
        f"Оплата: {_format_payment_status(row['entry_type'], row['payment_status'])}\n"
        f"Стоимость в день: {_format_income(row['income'])}\n"
        f"Заметка: {_format_note(row['note'])}"
    )

    return {
        "kind": "entry",
        "date": selected_date,
        "text": text,
        "entry": row,
        "group_entries": group_rows,
        "tour_group_id": tour_group_id,
        "entry_type": row["entry_type"],
    }


def get_day_card_data(user_id: int, date_str: str) -> dict:
    rows = [dict(row) for row in get_tours_for_date(user_id, date_str)]

    if not rows:
        return build_free_day_card(date_str)

    if len(rows) > 1:
        return {
            "kind": "multiple",
            "date": date_str,
            "entries": rows,
        }

    return build_day_card_from_row(date_str, rows[0])
