from database.queries import get_tours_for_date
from services.tour_card_formatter import build_selected_day_entry_text, format_date


def build_free_day_card(date_str: str) -> dict:
    text = (
        f"📅 Дата: {format_date(date_str)}\n"
        f"📊 Статус: Свободно"
    )

    return {
        "kind": "free",
        "date": date_str,
        "text": text,
        "entries": [],
    }


def build_day_card_from_row(selected_date: str, row: dict) -> dict:
    return {
        "kind": "entry",
        "date": selected_date,
        "text": build_selected_day_entry_text(selected_date, row),
        "entry": row,
        "group_entries": [],
        "tour_group_id": row.get("tour_group_id"),
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
