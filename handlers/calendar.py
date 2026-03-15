from datetime import date

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from keyboards.calendar import get_month_picker_keyboard, get_month_actions_keyboard
from services.calendar_service import (
    get_month_window,
    shift_month,
    build_month_calendar,
    get_free_days,
)
from utils.formatters import format_month_calendar, format_free_days

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "🗓 Календарь")
async def show_calendar_entry(message: Message) -> None:
    logger.info("event=calendar_opened user_id=%s", message.from_user.id)
    
    today = date.today()
    months = get_month_window(today.year, today.month)

    await message.answer(
        "Выберите месяц:",
        reply_markup=get_month_picker_keyboard(months, today.year, today.month),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("cal_picker:"))
async def show_month_picker(callback: CallbackQuery) -> None:
    _, year_str, month_str = callback.data.split(":")
    year = int(year_str)
    month = int(month_str)

    months = get_month_window(year, month)

    await callback.message.edit_text(
        "Выберите месяц:",
        reply_markup=get_month_picker_keyboard(months, year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("cal_shift:"))
async def shift_calendar_window(callback: CallbackQuery) -> None:
    _, year_str, month_str, offset_str = callback.data.split(":")
    year = int(year_str)
    month = int(month_str)
    offset = int(offset_str)

    new_year, new_month = shift_month(year, month, offset)
    months = get_month_window(new_year, new_month)

    await callback.message.edit_text(
        "Выберите месяц:",
        reply_markup=get_month_picker_keyboard(months, new_year, new_month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("cal_month:"))
async def open_month(callback: CallbackQuery) -> None:
    _, year_str, month_str = callback.data.split(":")
    year = int(year_str)
    month = int(month_str)

    logger.info(
        "event=calendar_month_opened user_id=%s year=%s month=%s",
        callback.from_user.id,
        year,
        month,
    )

    user_id = callback.from_user.id
    calendar_data = build_month_calendar(user_id, year, month)
    text = format_month_calendar(calendar_data)

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_month_actions_keyboard(year, month, year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("cal_free:"))
async def open_free_days(callback: CallbackQuery) -> None:
    _, year_str, month_str = callback.data.split(":")
    year = int(year_str)
    month = int(month_str)
    logger.info(
        "event=free_days_opened user_id=%s year=%s month=%s",
        callback.from_user.id,
        year,
        month,
    )

    user_id = callback.from_user.id
    free_days_data = get_free_days(user_id, year, month)
    text = format_free_days(free_days_data)

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_month_actions_keyboard(year, month, year, month),
    )
    await callback.answer()

