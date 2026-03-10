from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def format_short_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d-%m-%y")


def get_tours_list_keyboard(tours: list[dict]) -> InlineKeyboardMarkup:
    buttons = []

    for tour in tours:
        start_date = format_short_date(tour["start_date"])
        company = tour["company"]
        tour_id = tour["id"]

        text = f"{start_date} | {company}"
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
