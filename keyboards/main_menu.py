from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from services.guide_shop_settings import GuideShopFeatureFlags


_guide_shop_reads_enabled: bool | None = None


def configure_guide_shop_menu(reads_enabled: bool | None) -> None:
    global _guide_shop_reads_enabled
    _guide_shop_reads_enabled = reads_enabled


def get_main_menu(reads_enabled: bool | None = None):
    if reads_enabled is None:
        reads_enabled = (
            _guide_shop_reads_enabled
            if _guide_shop_reads_enabled is not None
            else GuideShopFeatureFlags.from_env().reads_enabled
        )

    keyboard = [
        [KeyboardButton(text="➕ Добавить тур")],
        [KeyboardButton(text="🗓 Календарь")],
        [KeyboardButton(text="🔎 Проверить дату")],
        [KeyboardButton(text="🔔 Уведомления")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="👤 Профиль")],
    ]

    if reads_enabled:
        keyboard.append([KeyboardButton(text="🛍 GuideShop")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )
