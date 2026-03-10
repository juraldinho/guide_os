from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu():

    keyboard = [
        [KeyboardButton(text="Add Tour")],
        [KeyboardButton(text="Calendar")],
        [KeyboardButton(text="My Tours")],
        [KeyboardButton(text="Income")],
        [KeyboardButton(text="Stats")]
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )
