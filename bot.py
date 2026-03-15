import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from handlers.start import router as start_router
from handlers.add_tour import router as add_tour_router
from handlers.calendar import router as calendar_router
from handlers.income import router as income_router
from database.db import init_db
from handlers import stats
from handlers.check_date import router as check_date_router
from handlers.tour_cards import router as tour_cards_router
from handlers.tour_edits import router as tour_edits_router

from utils.logger import setup_logging

async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    init_db()
    logger.info("Bot started")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start_router)
    dp.include_router(add_tour_router)
    dp.include_router(calendar_router)
    dp.include_router(income_router)
    dp.include_router(check_date_router)
    dp.include_router(tour_cards_router)
    dp.include_router(tour_edits_router)
    dp.include_router(stats.router)


    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
