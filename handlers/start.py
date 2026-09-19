import logging

from database.queries import (
    register_user,
    set_user_acquisition_source_if_unset,
    track_event,
)

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from keyboards.main_menu import get_main_menu

router = Router()
logger = logging.getLogger(__name__)

ACQUISITION_PAYLOADS = {
    "src_ig_guideos": (
        "instagram_guide_os",
        "start_source_instagram_guide_os",
    ),
    "src_ig_personal": (
        "instagram_personal",
        "start_source_instagram_personal",
    ),
    "src_threads": ("threads", "start_source_threads"),
    "src_tg_personal": (
        "telegram_personal_channel",
        "start_source_telegram_personal_channel",
    ),
    "src_web_guideos": (
        "guide_os_website",
        "start_source_guide_os_website",
    ),
    "src_articles": ("articles", "start_source_articles"),
}



@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject | None = None,
) -> None:

    user_id = message.from_user.id
    raw_payload = command.args if command is not None else None
    acquisition = (
        ("organic", "start_source_organic")
        if raw_payload is None or raw_payload == ""
        else ACQUISITION_PAYLOADS.get(raw_payload)
    )

    logger.info("event=start_used")
    register_user(user_id)
    if acquisition is not None:
        source, source_event = acquisition
        set_user_acquisition_source_if_unset(user_id, source)
    track_event(user_id, "start_used")
    if acquisition is not None:
        track_event(user_id, source_event)
    
    text = (
        "👋 <b>Добро пожаловать в Guide OS</b>\n\n"
        "Guide OS помогает гиду вести свою работу в одном месте:\n\n"
        "📅 добавлять туры и выходные\n"
        "🗓 видеть занятые и свободные даты\n"
        "💰 учитывать доход и комиссии\n"
        "📊 смотреть итоги работы\n"
        "🔔 получать напоминания о предстоящих турах\n\n"
        "📱 <b>Все основные возможности доступны в Mini App.</b>\n"
        "Чтобы открыть приложение, нажмите синюю кнопку "
        "<b>Guide OS Mini App</b> рядом с полем сообщения.\n\n"
        "Если вы используете бот впервые — просто добавьте свой первый тур.\n\n"
        "⚠️ Бот находится в ранней версии.\n"
        "Если есть идеи или ошибки — напишите мне:\n"
        "@juraldinho\n\n"
        "Для помощи — /help"
    )

    await message.answer(
        text,
        reply_markup=get_main_menu(),
        parse_mode="HTML",
    )
