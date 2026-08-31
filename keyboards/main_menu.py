from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

MINI_APP_MENU_LABEL = "📱 Guide OS Mini App"

_guide_shop_reads_enabled: bool | None = None
_miniapp_public_url: str | None = None


def configure_guide_shop_menu(reads_enabled: bool | None) -> None:
    global _guide_shop_reads_enabled
    _guide_shop_reads_enabled = reads_enabled


def configure_miniapp_menu(public_url: str | None) -> None:
    global _miniapp_public_url
    _miniapp_public_url = public_url


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
    ]

    if _miniapp_public_url:
        keyboard.append(
            [
                KeyboardButton(
                    text=MINI_APP_MENU_LABEL,
                    web_app=WebAppInfo(url=_miniapp_public_url),
                )
            ]
        )

    if reads_enabled:
        keyboard.append([KeyboardButton(text="🛍 GuideShop")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )
