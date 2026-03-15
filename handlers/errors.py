import logging

from database.queries import track_event

from aiogram import Router
from aiogram.types import ErrorEvent

router = Router()

logger = logging.getLogger(__name__)


@router.errors()
async def error_handler(event: ErrorEvent):
    user_id = None

    if event.update and event.update.message and event.update.message.from_user:
        user_id = event.update.message.from_user.id
    elif event.update and event.update.callback_query and event.update.callback_query.from_user:
        user_id = event.update.callback_query.from_user.id

    logger.exception("Unhandled error: %s", event.exception)
    track_event(user_id, "error_occurred")
