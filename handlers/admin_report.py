import os

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.queries import (
    get_total_users_count,
    get_new_users_today_count,
    get_active_users_last_days,
    get_event_count_today,
)

router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


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

    text = (
        "📊 <b>Guide OS — admin report</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"🆕 Новых сегодня: {new_users_today}\n"
        f"🔥 Активных за 7 дней: {active_7d}\n"
        f"📆 Активных за 30 дней: {active_30d}\n\n"
        f"▶️ /start сегодня: {starts_today}\n"
        f"🗓 Открытие календаря: {calendar_today}\n"
        f"📅 Открытие месяца: {month_open_today}\n"
        f"➕ Начали add tour: {add_tour_started_today}\n"
        f"✅ Сохранили тур: {tours_saved_today}\n"
        f"🌴 Сохранили выходной: {day_off_today}\n"
        f"📊 Открыли статистику: {stats_today}\n"
        f"❌ Ошибок сегодня: {errors_today}"
    )

    await message.answer(text, parse_mode="HTML")
