from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.guide_shop_navigation import create_navigation_token
from services.guide_shop_ui import GuideShopAction


def build_guide_shop_keyboard(
    telegram_user_id: int,
    actions: tuple[GuideShopAction, ...],
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
    return InlineKeyboardMarkup(inline_keyboard=rows)
