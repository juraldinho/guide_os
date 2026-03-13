from datetime import date

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from keyboards.stats import (
    get_stats_picker_keyboard,
    get_stats_actions_keyboard,
)
from services.calendar_service import get_month_window, shift_month
from services.stats_service import get_stats_summary, get_all_time_stats_summary

from aiogram.exceptions import TelegramBadRequest


router = Router()


async def safe_edit_text(message, text, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        raise

    
MONTHS_RU = {
    1: "январь",
    2: "февраль",
    3: "март",
    4: "апрель",
    5: "май",
    6: "июнь",
    7: "июль",
    8: "август",
    9: "сентябрь",
    10: "октябрь",
    11: "ноябрь",
    12: "декабрь",
}


def format_month_stats_text(stats: dict) -> str:
    return (
        f"Статистика за {MONTHS_RU[stats['month']]} {stats['year']}\n\n"
        f"Туров: {stats['total_tours']}\n"
        f"Рабочих дней: {stats['working_days']}\n"
        f"Доход: {stats['total_income']}$\n"
        f"Оплаченных туров: {stats['paid_tours']}\n"
        f"Неоплаченных туров: {stats['unpaid_tours']}"
    )


def format_all_time_stats_text(stats: dict) -> str:
    return (
        "Статистика за весь период\n\n"
        f"Туров: {stats['total_tours']}\n"
        f"Рабочих дней: {stats['working_days']}\n"
        f"Доход: {stats['total_income']}$\n"
        f"Оплаченных туров: {stats['paid_tours']}\n"
        f"Неоплаченных туров: {stats['unpaid_tours']}"
    )


@router.message(F.text == "📊 Статистика")
async def show_stats_entry(message: Message) -> None:
    today = date.today()
    months = get_month_window(today.year, today.month)

    await message.answer(
        "Выберите период статистики:",
        reply_markup=get_stats_picker_keyboard(months, today.year, today.month),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("stats_picker:"))
async def show_stats_picker(callback: CallbackQuery) -> None:
    _, year_str, month_str = callback.data.split(":")
    year = int(year_str)
    month = int(month_str)

    months = get_month_window(year, month)

    await safe_edit_text(
        callback.message,
        "Выберите период статистики:",
        reply_markup=get_stats_picker_keyboard(months, year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("stats_shift:"))
async def shift_stats_window(callback: CallbackQuery) -> None:
    _, year_str, month_str, offset_str = callback.data.split(":")
    year = int(year_str)
    month = int(month_str)
    offset = int(offset_str)

    new_year, new_month = shift_month(year, month, offset)
    months = get_month_window(new_year, new_month)

    await safe_edit_text(
        callback.message,
        "Выберите период статистики:",
        reply_markup=get_stats_picker_keyboard(months, new_year, new_month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("stats_month:"))
async def open_stats_month(callback: CallbackQuery) -> None:
    _, year_str, month_str = callback.data.split(":")
    year = int(year_str)
    month = int(month_str)

    user_id = callback.from_user.id
    stats = get_stats_summary(user_id, year, month)

    await safe_edit_text(
        callback.message,
        format_month_stats_text(stats),
        reply_markup=get_stats_actions_keyboard(year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "stats_all")
async def open_stats_all_time(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    stats = get_all_time_stats_summary(user_id)

    today = date.today()
    months = get_month_window(today.year, today.month)

    await safe_edit_text(
        callback.message,
        format_all_time_stats_text(stats),
        reply_markup=get_stats_picker_keyboard(months, today.year, today.month),
    )
    await callback.answer()
