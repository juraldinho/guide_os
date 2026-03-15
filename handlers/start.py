import logging

from database.queries import register_user, track_event

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from keyboards.main_menu import get_main_menu

router = Router()
logger = logging.getLogger(__name__)



@router.message(CommandStart())
async def cmd_start(message: Message) -> None:

    user_id = message.from_user.id
    logger.info("event=start_used user_id=%s", user_id)
    register_user(user_id)
    track_event(user_id, "start_used")
    
    text = (
        "👋 <b>Добро пожаловать в Guide OS</b>\n\n"
        "Этот бот помогает гидам управлять своей работой:\n\n"
        "📅 планировать туры и занятые дни\n"
        "🗓 смотреть календарь занятости\n"
        "📋 открывать карточки туров\n"
        "📊 анализировать статистику\n\n"
        "Если вы используете бот впервые — просто добавьте свой первый тур.\n\n"
        "⚠️ Бот находится в ранней версии.\n"
        "Если вы заметили ошибку или у вас есть предложения по улучшению — пожалуйста напишите мне.\n\n"
        "Все сообщения можно отправлять сюда:\n"
        "@juraldinho\n\n"
        "Если нет времени писать — можно отправить голосовое сообщение.\n\n"
        "ℹ️ Чтобы снова открыть это меню — нажмите /start"
    )

    await message.answer(
        text,
        reply_markup=get_main_menu(),
        parse_mode="HTML",
    )
