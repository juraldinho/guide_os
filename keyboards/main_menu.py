from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu():

    keyboard = [
        [KeyboardButton(text="➕ Добавить тур")],
        [KeyboardButton(text="📅 Календарь")],
        [KeyboardButton(text="📋 Туры")],
        [KeyboardButton(text="💰 Оплата")],
        [KeyboardButton(text="📊Статистика")]
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )
