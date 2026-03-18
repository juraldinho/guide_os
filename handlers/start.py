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
        "📅 планировать туры\n"
        "🗓 смотреть календарь занятости\n"
        "📋 открывать карточки туров и редактировать данные\n"
        "📊 анализировать статистику по загруженности и доходу\n\n"

        "🔔 <b>Новая функция — уведомления</b>\n"
        "Бот может сам напоминать тебе о турах на завтра:\n"
        "• во сколько экскурсия\n"
        "• какая компания\n"
        "• маршрут и детали\n\n"

        "📌 Это помогает:\n"
        "— не забыть про тур\n"
        "— подготовиться заранее\n"
        "— держать всё под контролем\n\n"

        "👉 Включи уведомления в меню бота\n\n"

        "Если вы используете бот впервые — просто добавьте свой первый тур.\n\n"

        "⚠️ Бот находится в ранней версии.\n"
        "Если есть идеи или ошибки — напишите мне:\n"
        "@juraldinho\n\n"

        "ℹ️ Чтобы открыть это меню — /start\n"
        "Для помощи — /help"
    )

    await message.answer(
        text,
        reply_markup=get_main_menu(),
        parse_mode="HTML",
    )
