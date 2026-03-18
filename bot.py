import asyncio
import logging
import os

from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat
from handlers.broadcast import router as broadcast_router

from handlers.notifications import router as notifications_router
from services.reminder_service import send_tour_reminders

from dotenv import load_dotenv

from handlers.admin_report import (
    router as admin_report_router,
    send_daily_admin_report,
)

from aiogram import Bot, Dispatcher
from handlers.help import router as help_router

from config import BOT_TOKEN
from handlers.start import router as start_router
from handlers.add_tour import router as add_tour_router
from handlers.calendar import router as calendar_router
from handlers.income import router as income_router
from database.db import init_db
from handlers import stats
from handlers import errors
from handlers.check_date import router as check_date_router
from handlers.tour_cards import router as tour_cards_router
from handlers.tour_edits import router as tour_edits_router

from utils.logger import setup_logging

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

async def setup_bot_commands(bot: Bot) -> None:
    user_commands = [
        BotCommand(command="start", description="Открыть главное меню"),
        BotCommand(command="help", description="Помощь и инструкция"),
    ]

    admin_commands = [
        BotCommand(command="start", description="Открыть главное меню"),
        BotCommand(command="help", description="Помощь и инструкция"),
        BotCommand(command="admin_report", description="Админ-отчет"),
        BotCommand(command="broadcast", description="Рассылка"),
        BotCommand(command="backup", description="Скачать backup БД"),
    ]

    await bot.set_my_commands(
        commands=user_commands,
        scope=BotCommandScopeAllPrivateChats(),
    )

    if ADMIN_ID:
        await bot.set_my_commands(
            commands=admin_commands,
            scope=BotCommandScopeChat(chat_id=ADMIN_ID),
        )


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)


    bot = Bot(token=BOT_TOKEN)
    await setup_bot_commands(bot)
    
    init_db()
    logger.info("Bot started")
    logger.info("BUILD_MARKER: reminder-fix-2026-03-17-v2")
    
    asyncio.create_task(send_daily_admin_report(bot))
    asyncio.create_task(send_tour_reminders(bot))
    
    dp = Dispatcher()


    dp.include_router(start_router)
    dp.include_router(add_tour_router)
    dp.include_router(calendar_router)
    dp.include_router(income_router)
    dp.include_router(check_date_router)
    dp.include_router(tour_cards_router)
    dp.include_router(tour_edits_router)
    dp.include_router(stats.router)
    dp.include_router(errors.router)
    dp.include_router(admin_report_router)
    dp.include_router(help_router)
    dp.include_router(notifications_router)
    dp.include_router(broadcast_router)

    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
