from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.guide_shop_navigation import create_navigation_token
from services.guide_shop_ui import GuideShopAction


def build_guide_shop_keyboard(
    telegram_user_id: int,
    actions: tuple[GuideShopAction, ...],
    *,
    include_personal_places: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    for action in actions:
        token = create_navigation_token(telegram_user_id, action.route)
        rows.append(
            [
                InlineKeyboardButton(
                    text=action.label,
                    callback_data=token.raw_token,
                )
            ]
        )
    if include_personal_places:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📍 Мои места",
                    callback_data="pp:list",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
