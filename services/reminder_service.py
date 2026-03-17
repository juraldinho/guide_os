import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import TIMEZONE
from database.queries import (
    get_entries_for_reminder_date,
    get_users_with_notifications_enabled,
    update_last_tour_reminder_date,
)

from utils.constants import ENTRY_TYPE_DAY_OFF, MONTH_NAMES_RU_GENITIVE
from services.tour_card_formatter import format_tour_status

logger = logging.getLogger(__name__)
REMINDER_TZ = ZoneInfo(TIMEZONE)



def format_ru_date(value: str) -> str:
    dt = datetime.strptime(value, "%Y-%m-%d").date()
    return f"{dt.day} {MONTH_NAMES_RU_GENITIVE[dt.month]}"


def format_ru_date_range(start_date: str, end_date: str) -> str:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

    if start_dt == end_dt:
        return format_ru_date(start_date)

    if start_dt.month == end_dt.month:
        return f"{start_dt.day}–{end_dt.day} {MONTH_NAMES_RU_GENITIVE[start_dt.month]}"
    return (
        f"{start_dt.day} {MONTH_NAMES_RU_GENITIVE[start_dt.month]} – "
        f"{end_dt.day} {MONTH_NAMES_RU_GENITIVE[end_dt.month]}"
    )


def build_open_tour_keyboard(target_date: str) -> InlineKeyboardMarkup:
    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть тур",
                    callback_data=f"day_card:{target_date}:{target_dt.year}:{target_dt.month}",
                )
            ]
        ]
    )

def build_reminder_text(entry: dict, target_date: str) -> str:
    target_date_ru = format_ru_date(target_date)
    date_range_ru = format_ru_date_range(entry["start_date"], entry["end_date"])

    if entry["entry_type"] == ENTRY_TYPE_DAY_OFF:
        text = (
            "🌴 <b>Напоминание на завтра</b>\n\n"
            f"Дата: {target_date_ru}\n"
            f"Запись: {entry['company']}\n"
            f"Период: {date_range_ru}"
        )

        if entry.get("note"):
            text += f"\nЗаметка: {entry['note']}"

        return text

    text = (
        "🔔 <b>Напоминание о туре на завтра</b>\n\n"
        f"Дата: {target_date_ru}\n"
        f"Компания: {entry['company']}\n"
        f"Маршрут: {entry['city']}\n"
        f"Статус: {format_tour_status(entry['status'])}\n"
        f"Даты тура: {date_range_ru}"
    )

    if entry.get("note"):
        text += f"\nЗаметка: {entry['note']}"

    return text


async def send_tour_reminders(bot: Bot) -> None:
    logger.info("Tour reminders task started")

    while True:
        try:
            now = datetime.now(REMINDER_TZ)
            current_time = now.strftime("%H:%M")
            tomorrow_date = (now.date() + timedelta(days=1)).isoformat()

            users = get_users_with_notifications_enabled()

            logger.info(
                "Reminder tick | now=%s current_time=%s tomorrow_date=%s users_with_notifications=%s",
                now.isoformat(),
                current_time,
                tomorrow_date,
                len(users),
            )

            for user in users:
                user_id = user["user_id"]
                notification_time = user["notification_time"] or "21:00"
                last_sent_date = user["last_tour_reminder_date"]
                logger.info(
                    "Reminder check | user_id=%s notification_time=%s last_sent_date=%s current_time=%s",
                    user_id,
                    notification_time,
                    last_sent_date,
                    current_time,
                )
                
                if current_time < notification_time:
                    logger.info(
                        "Reminder skip by time | user_id=%s current_time=%s notification_time=%s",
                        user_id,
                        current_time,
                        notification_time,
                    )
                    continue
                
                if last_sent_date == tomorrow_date:
                    logger.info(
                        "Reminder skip by last_sent_date | user_id=%s tomorrow_date=%s",
                        user_id,
                        tomorrow_date,
                    )
                    continue

                entries = get_entries_for_reminder_date(user_id, tomorrow_date)

                logger.info(
                    "Reminder entries | user_id=%s tomorrow_date=%s entries_count=%s",
                    user_id,
                    tomorrow_date,
                    len(entries),
                )

                if not entries:
                    logger.info(
                        "Reminder skip no entries | user_id=%s tomorrow_date=%s",
                        user_id,
                        tomorrow_date,
                    )
                    continue

                try:
                    for entry in entries:
                        logger.info(
                            "Reminder sending | user_id=%s entry_id=%s entry_type=%s company=%s",
                            user_id,
                            entry["id"],
                            entry["entry_type"],
                            entry["company"],
                        )
                        await bot.send_message(
                            chat_id=user_id,
                            text=build_reminder_text(entry, tomorrow_date),
                            reply_markup=build_open_tour_keyboard(tomorrow_date),
                            parse_mode="HTML",
                        )
                        
                    logger.info(
                        "Reminder success | user_id=%s tomorrow_date=%s sent_entries=%s",
                        user_id,
                        tomorrow_date,
                        len(entries),
                    )
                    update_last_tour_reminder_date(user_id, tomorrow_date)

                except Exception:
                    logger.exception(
                        "Failed to send reminder to user_id=%s for date=%s",
                        user_id,
                        tomorrow_date,
                    )
            await asyncio.sleep(60)

        except Exception:
            logger.exception("Tour reminders loop failed")
            await asyncio.sleep(60)
