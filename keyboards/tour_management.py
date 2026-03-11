from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def format_short_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d-%m-%y")

def get_tours_list_keyboard(tours: list[dict]) -> InlineKeyboardMarkup:
    buttons = []

    for tour in tours:

        start_raw = tour["start_date"]
        end_raw = tour["end_date"]

        start_dt = datetime.strptime(start_raw, "%Y-%m-%d")
        end_dt = datetime.strptime(end_raw, "%Y-%m-%d")

        days = (end_dt - start_dt).days + 1

        start_date = format_short_date(start_raw)

        company = tour["company"]
        tour_id = tour["id"]

        if days == 1:
            text = f"{start_date} | {company}"
        else:
            text = f"{start_date} | {days} дня | {company}"

        buttons.append(
            [InlineKeyboardButton(text=text, callback_data=f"tour_view:{tour_id}")]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_tour_view_keyboard(tour_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"tour_delete:{tour_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="tours_back")],
        ]
    )


def get_delete_confirmation_keyboard(tour_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"tour_delete_confirm:{tour_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"tour_view:{tour_id}")],
        ]
    )
