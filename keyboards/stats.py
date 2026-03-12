from datetime import date
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from services.calendar_service import shift_month


MONTH_NAMES_RU = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


def get_stats_picker_keyboard(
    months: list[tuple[int, int]],
    window_year: int,
    window_month: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=MONTH_NAMES_RU[months[0][1]],
                    callback_data=f"stats_month:{months[0][0]}:{months[0][1]}",
                ),
                InlineKeyboardButton(
                    text=MONTH_NAMES_RU[months[1][1]],
                    callback_data=f"stats_month:{months[1][0]}:{months[1][1]}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=MONTH_NAMES_RU[months[2][1]],
                    callback_data=f"stats_month:{months[2][0]}:{months[2][1]}",
                ),
                InlineKeyboardButton(
                    text=MONTH_NAMES_RU[months[3][1]],
                    callback_data=f"stats_month:{months[3][0]}:{months[3][1]}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=f"stats_shift:{window_year}:{window_month}:-4",
                ),
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=f"stats_shift:{window_year}:{window_month}:4",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="За весь период",
                    callback_data="stats_all",
                )
            ],
        ]
    )


def get_stats_actions_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    prev_year, prev_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=f"stats_month:{prev_year}:{prev_month}",
                ),
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=f"stats_month:{next_year}:{next_month}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="За весь период",
                    callback_data="stats_all",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"stats_picker:{year}:{month}",
                )
            ],
        ]
    )


def get_stats_all_time_keyboard() -> InlineKeyboardMarkup:
    today = date.today()

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"stats_picker:{today.year}:{today.month}",
                )
            ]
        ]
    )
