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
from database.queries import get_guide_os_id
from handlers import stats
from handlers import errors
from handlers.check_date import router as check_date_router
from handlers.tour_cards import router as tour_cards_router
from handlers.tour_edits import router as tour_edits_router
from handlers.profile import router as profile_router
from handlers.guide_shop import (
    configure_guide_shop_provider,
    configure_guide_shop_ui,
    router as guide_shop_router,
)
from handlers.personal_places import router as personal_places_router
from handlers.personal_place_entries import router as personal_place_entries_router
from keyboards.main_menu import configure_guide_shop_menu, configure_miniapp_menu
from services.miniapp_api_settings import MiniAppMenuSettings
from web_api.app import start_miniapp_api
from services.guide_shop_client import (
    HTTPGuideShopClient,
    InMemoryGuideShopClient,
)
from services.guide_shop_auth import GuideShopJWTAccessTokenProvider
from services.guide_shop_runtime import RequestScopedGuideShopUIServiceProvider
from services.guide_shop_settings import (
    GuideShopFeatureFlags,
    GuideShopHTTPSettings,
    GuideShopJWTSigningSettings,
    GuideShopRuntimeSettings,
)
from services.guide_shop_ui import GuideShopUIService
from services.guide_shop_link_provider import start_guide_shop_link_provider
from services.guide_shop_event_worker import (
    build_guide_shop_event_worker,
    validate_guide_shop_event_flags,
)

from utils.logger import setup_logging

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


async def start_guide_shop_event_worker(bot, values=None):
    worker = await build_guide_shop_event_worker(bot, values)
    return asyncio.create_task(worker.run()) if worker is not None else None


async def stop_guide_shop_event_worker(task) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def configure_guide_shop_runtime(values=None) -> None:
    configure_guide_shop_provider(None, reads_enabled=False)
    flags = GuideShopFeatureFlags.from_env(values)
    configure_guide_shop_menu(flags.reads_enabled)

    if not flags.reads_enabled:
        return

    runtime = GuideShopRuntimeSettings.from_env(values)
    if runtime.use_fake:
        client = InMemoryGuideShopClient(
            companies=(),
            visits=(),
            sales=(),
            points=(),
            points_history=(),
        )
        configure_guide_shop_ui(
            GuideShopUIService(client),
            reads_enabled=True,
        )
        return

    http_settings = GuideShopHTTPSettings.from_env(values)
    signing_settings = GuideShopJWTSigningSettings.from_env(values)
    token_provider = GuideShopJWTAccessTokenProvider(signing_settings)
    provider = RequestScopedGuideShopUIServiceProvider(
        get_guide_os_id,
        lambda guide_os_id: HTTPGuideShopClient(
            http_settings,
            guide_os_id,
            token_provider,
        ),
    )
    configure_guide_shop_provider(
        provider,
        reads_enabled=True,
    )


def configure_miniapp_runtime(values=None) -> None:
    menu_settings = MiniAppMenuSettings.from_env(values)
    if menu_settings.enabled and menu_settings.public_url:
        configure_miniapp_menu(menu_settings.public_url)
    else:
        configure_miniapp_menu(None)
        if menu_settings.enabled:
            logging.getLogger(__name__).warning(
                "Mini App menu entry disabled: MINI_APP_PUBLIC_URL missing or invalid"
            )


async def setup_bot_commands(bot: Bot) -> None:
    user_commands = [
        BotCommand(command="start", description="Открыть главное меню"),
        BotCommand(command="help", description="Помощь и инструкция"),
        BotCommand(command="profile", description="Мой профиль"),
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

    configure_guide_shop_runtime()
    configure_miniapp_runtime()
    validate_guide_shop_event_flags()

    bot = Bot(token=BOT_TOKEN)
    await setup_bot_commands(bot)
    
    init_db()
    link_provider_runner = None
    miniapp_runner = None
    event_worker_task = None
    try:
        event_worker_task = await start_guide_shop_event_worker(bot)
        link_provider_runner = await start_guide_shop_link_provider(attach_miniapp_api=True)
        if link_provider_runner is None:
            miniapp_runner = await start_miniapp_api()
        logger.info("Bot started")
        logger.info("BUILD_MARKER: reminder-fix-2026-03-17-v2")

        asyncio.create_task(send_daily_admin_report(bot))
        asyncio.create_task(send_tour_reminders(bot))

        dp = Dispatcher()
        dp.include_router(personal_place_entries_router)
        dp.include_router(personal_places_router)
        dp.include_router(guide_shop_router)
        dp.include_router(start_router)
        dp.include_router(add_tour_router)
        dp.include_router(calendar_router)
        dp.include_router(income_router)
        dp.include_router(check_date_router)
        dp.include_router(tour_cards_router)
        dp.include_router(tour_edits_router)
        dp.include_router(profile_router)
        dp.include_router(stats.router)
        dp.include_router(errors.router)
        dp.include_router(admin_report_router)
        dp.include_router(help_router)
        dp.include_router(notifications_router)
        dp.include_router(broadcast_router)

        await dp.start_polling(bot, skip_updates=True)
    finally:
        try:
            await stop_guide_shop_event_worker(event_worker_task)
        finally:
            try:
                if link_provider_runner is not None:
                    await link_provider_runner.cleanup()
            finally:
                if miniapp_runner is not None:
                    await miniapp_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
