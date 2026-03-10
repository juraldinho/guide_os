from aiogram import Router, F
from aiogram.types import Message

from services.calendar_service import build_month_calendar, get_free_days
from utils.formatters import format_month_calendar, format_free_days

router = Router()


@router.message(F.text == "📅 Календарь")
async def show_calendar(message: Message) -> None:
    calendar_data = build_month_calendar(message.from_user.id)
    text = format_month_calendar(calendar_data)
    await message.answer(text)
    await message.answer("Нажми: Free Dates")


@router.message(F.text == "Free Dates")
async def show_free_dates(message: Message) -> None:
    free_days_data = get_free_days(message.from_user.id)
    text = format_free_days(free_days_data)
    await message.answer(text)
