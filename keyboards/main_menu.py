from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Calendar"), KeyboardButton(text="Free Dates")],
            [KeyboardButton(text="➕ Add Tour"), KeyboardButton(text="💰 Income")],
            [KeyboardButton(text="📊 Stats")], KeyboardButton(text="My Tours")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )
