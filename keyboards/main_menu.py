from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

COMMANDS_MENU_LABEL = "⚙️ Команды"

_guide_shop_reads_enabled: bool | None = None


def configure_guide_shop_menu(reads_enabled: bool | None) -> None:
    global _guide_shop_reads_enabled
    _guide_shop_reads_enabled = reads_enabled


def get_main_menu(reads_enabled: bool | None = None):
    # The section also contains local personal places and is always available.
    reads_enabled = True

    keyboard = [
        [KeyboardButton(text="➕ Добавить тур")],
        [KeyboardButton(text="🗓 Календарь")],
        [KeyboardButton(text="🔎 Проверить дату")],
        [KeyboardButton(text="🔔 Уведомления")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text=COMMANDS_MENU_LABEL)],
    ]

    if reads_enabled:
        keyboard.append([KeyboardButton(text="🛍 GuideShop")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )
