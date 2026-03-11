from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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


def get_month_picker_keyboard(months: list[tuple[int, int]], window_year: int, window_month: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=MONTH_NAMES_RU[months[0][1]], callback_data=f"cal_month:{months[0][0]}:{months[0][1]}"),
                InlineKeyboardButton(text=MONTH_NAMES_RU[months[1][1]], callback_data=f"cal_month:{months[1][0]}:{months[1][1]}"),
            ],
            [
                InlineKeyboardButton(text=MONTH_NAMES_RU[months[2][1]], callback_data=f"cal_month:{months[2][0]}:{months[2][1]}"),
                InlineKeyboardButton(text=MONTH_NAMES_RU[months[3][1]], callback_data=f"cal_month:{months[3][0]}:{months[3][1]}"),
            ],
            [
                InlineKeyboardButton(text="⬅️", callback_data=f"cal_shift:{window_year}:{window_month}:-4"),
                InlineKeyboardButton(text="➡️", callback_data=f"cal_shift:{window_year}:{window_month}:4"),
            ],
        ]
    )


def get_month_actions_keyboard(year: int, month: int, picker_year: int, picker_month: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Карточка тура", callback_data=f"cal_tours:{year}:{month}")],
            [InlineKeyboardButton(text="Свободные даты", callback_data=f"cal_free:{year}:{month}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cal_picker:{picker_year}:{picker_month}")],
        ]
    )
