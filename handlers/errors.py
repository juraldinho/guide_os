import logging

from database.queries import track_event

from aiogram import Router
from aiogram.types import ErrorEvent

from keyboards.main_menu import get_main_menu

router = Router()

logger = logging.getLogger(__name__)

ERROR_TEXT = "Что-то пошло не так. Попробуйте ещё раз."


@router.errors()
async def error_handler(event: ErrorEvent):
    user_id = None

    if event.update and event.update.message and event.update.message.from_user:
        user_id = event.update.message.from_user.id
    elif event.update and event.update.callback_query and event.update.callback_query.from_user:
        user_id = event.update.callback_query.from_user.id

    logger.exception("Unhandled error: %s", event.exception)
    track_event(user_id, "error_occurred")

    if event.update and event.update.message:
        try:
            await event.update.message.answer(ERROR_TEXT, reply_markup=get_main_menu())
        except Exception:
            logger.warning("Failed to send error message to user")
    elif event.update and event.update.callback_query:
        try:
            await event.update.callback_query.answer()
            if event.update.callback_query.message:
                await event.update.callback_query.message.answer(
                    ERROR_TEXT, reply_markup=get_main_menu()
                )
        except Exception:
            logger.warning("Failed to send error message to user")
