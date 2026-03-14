from aiogram import F, Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from states.check_date_state import CheckDateState
from services.date_parser import parse_date_input
from services.day_card_service import get_day_card_data
from services.tour_card_formatter import format_date
from keyboards.main_menu import get_main_menu
from keyboards.tour_management import (
    get_free_day_card_keyboard,
    get_multiple_day_entries_keyboard,
    get_single_day_entry_keyboard,
)
from datetime import datetime

router = Router()

def get_check_date_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Введите дату"
    )


def format_multiple_day_entries(date_str: str, entries: list[dict]) -> str:
    date_formatted = format_date(date_str)

    lines = [
        f"📅 Дата: {date_formatted}\n\n"
        f"На эту дату найдено несколько записей.\n"
        f"Выберите карточку:"
    ]

    return "\n".join(lines)



@router.message(F.text == "🔎 Проверить дату")
async def check_date_start(message: Message, state: FSMContext):
    await state.set_state(CheckDateState.waiting_for_date)
    await message.answer(
        "🔎 Проверка даты\n\n"
        "Введите дату экскурсии.\n\n"
        "Примеры:\n"
        "• 12/03\n"
        "• 12.03\n"
        "• 2026-03-12",
        reply_markup=get_check_date_keyboard()
    )

@router.message(CheckDateState.waiting_for_date, F.text == "❌ Отмена")
async def cancel_check_date(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Проверка даты отменена",
        reply_markup=get_main_menu()
    )

@router.message(CheckDateState.waiting_for_date)
async def check_date_result(message: Message, state: FSMContext):

    date_text = message.text.strip()

    try:
        dates = parse_date_input(date_text)
    except ValueError:
        await message.answer(
            "Не удалось распознать дату.\n\n"
            "Попробуйте формат:\n"
            "• 12/03\n"
            "• 12.03\n"
            "• 2026-03-12",
            reply_markup=get_check_date_keyboard()
        )
        return

    first_item = dates[0]

    if isinstance(first_item, dict):
        date_str = first_item["start_date"]
    else:
        date_str = first_item
        
    await state.clear()

    await message.answer(
        "Дата найдена",
        reply_markup=get_main_menu()
    )

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    year = dt.year
    month = dt.month

    user_id = message.from_user.id

    card_data = get_day_card_data(user_id, date_str)

    if card_data["kind"] == "free":
        await message.answer(
            card_data["text"],
            reply_markup=get_free_day_card_keyboard(date_str, year, month)
        )
        return

    if card_data["kind"] == "multiple":
        await message.answer(
            format_multiple_day_entries(date_str, card_data["entries"]),
            reply_markup=get_multiple_day_entries_keyboard(
                date_str,
                card_data["entries"],
                year,
                month,
            ),
        )
        return

    entry = card_data["entry"]

    await message.answer(
        card_data["text"],
        reply_markup=get_single_day_entry_keyboard(
            entry["id"],
            date_str,
            year,
            month
        )
    )
