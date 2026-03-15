import os

import shutil
import datetime
from aiogram.types import FSInputFile
from database.db import DB_PATH

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.queries import (
    get_total_users_count,
    get_new_users_today_count,
    get_active_users_last_days,
    get_event_count_today,
    get_unique_event_users_today,
    get_repeat_active_users_last_days,
)

router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


def percent(part: int, whole: int) -> int:
    if whole <= 0:
        return 0
    return round((part / whole) * 100)

@router.message(Command("admin_report"))
async def admin_report(message: Message) -> None:
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет доступа")
        return

    total_users = get_total_users_count()
    new_users_today = get_new_users_today_count()
    active_7d = get_active_users_last_days(7)
    active_30d = get_active_users_last_days(30)

    starts_today = get_event_count_today("start_used")
    calendar_today = get_event_count_today("calendar_opened")
    month_open_today = get_event_count_today("calendar_month_opened")
    add_tour_started_today = get_event_count_today("add_tour_started")
    tours_saved_today = get_event_count_today("tour_saved")
    day_off_today = get_event_count_today("day_off_saved")
    stats_today = get_event_count_today("stats_opened")
    errors_today = get_event_count_today("error_occurred")

    unique_start_users_today = get_unique_event_users_today("start_used")
    unique_calendar_users_today = get_unique_event_users_today("calendar_opened")
    unique_month_open_users_today = get_unique_event_users_today("calendar_month_opened")
    unique_add_tour_started_today = get_unique_event_users_today("add_tour_started")
    unique_tours_saved_today = get_unique_event_users_today("tour_saved")

    repeat_active_7d = get_repeat_active_users_last_days(7)

    calendar_open_rate = percent(unique_calendar_users_today, unique_start_users_today)
    month_open_rate = percent(unique_month_open_users_today, unique_calendar_users_today)
    add_tour_save_conversion = percent(unique_tours_saved_today, unique_add_tour_started_today)

    text = (
        "📊 <b>Guide OS — admin report</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"🆕 Новых сегодня: {new_users_today}\n"
        f"🔥 Активных за 7 дней: {active_7d}\n"
        f"📆 Активных за 30 дней: {active_30d}\n"
        f"🔁 Повторно активных за 7 дней: {repeat_active_7d}\n\n"

        f"▶️ /start сегодня: {starts_today}\n"
        f"👤 Уникальных /start сегодня: {unique_start_users_today}\n"
        f"🗓 Открытие календаря: {calendar_today}\n"
        f"👤 Уникально открыли календарь: {unique_calendar_users_today}\n"
        f"📅 Открытие месяца: {month_open_today}\n"
        f"👤 Уникально открыли месяц: {unique_month_open_users_today}\n"
        f"📈 Start → Calendar: {calendar_open_rate}%\n"
        f"📈 Calendar → Month: {month_open_rate}%\n\n"

        f"➕ Начали add tour: {add_tour_started_today}\n"
        f"👤 Уникально начали add tour: {unique_add_tour_started_today}\n"
        f"✅ Сохранили тур: {tours_saved_today}\n"
        f"👤 Уникально сохранили тур: {unique_tours_saved_today}\n"
        f"🎯 Конверсия add tour → saved: {add_tour_save_conversion}%\n\n"

        f"🌴 Сохранили выходной: {day_off_today}\n"
        f"📊 Открыли статистику: {stats_today}\n"
        f"❌ Ошибок сегодня: {errors_today}"
    )

    await message.answer(text, parse_mode="HTML")

@router.message(Command("backup"))
async def backup_database(message: Message) -> None:

    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет доступа")
        return

    try:
        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

        backup_name = f"guide_os_backup_{timestamp}.db"
        backup_path = f"/tmp/{backup_name}"

        shutil.copy(DB_PATH, backup_path)

        file = FSInputFile(backup_path)

        await message.answer_document(
            file,
            caption="📦 SQLite backup"
        )

    except Exception as e:
        await message.answer(f"❌ Backup error: {e}")
