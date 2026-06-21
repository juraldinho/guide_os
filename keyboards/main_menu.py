from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu():
    keyboard = [
        [KeyboardButton(text="➕ Добавить тур")],
        [KeyboardButton(text="🗓 Календарь")],
        [KeyboardButton(text="🔎 Проверить дату")],
        [KeyboardButton(text="🔔 Уведомления")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="👤 Профиль")],
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )
