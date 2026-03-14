from aiogram import F, Router
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.fsm.context import FSMContext

from datetime import datetime

from database.queries import get_tours_by_group_id

from states.add_tour_state import AddTourState
from states.tour_edit import EditTourState

from handlers.add_tour import get_company_keyboard

from services.day_view_service import build_day_entries_for_month
from services.day_card_service import get_day_card_data
from services.tour_card_formatter import (
    format_date,
    format_tour_card,
    build_selected_day_entry_text,
)

from services.tour_service import (
    get_tour,
    delete_tour,
    edit_tour_company,
    edit_tour_city,
    edit_tour_income,
    edit_tour_note,
    edit_tour_status,
    edit_tour_payment_status,
    edit_tour_dates,
)

from keyboards.tour_management import (
    get_tour_view_keyboard,
    get_edit_tour_menu_keyboard,
    get_edit_company_keyboard,
    get_edit_city_keyboard,
    get_edit_income_keyboard,
    get_edit_note_keyboard,
    get_delete_confirmation_keyboard,
    get_day_card_keyboard,
    get_day_entries_keyboard,
    get_free_day_card_keyboard,
    get_multiple_day_entries_keyboard,
    get_multiple_selected_entry_keyboard,
    get_day_off_selected_entry_keyboard,
    get_single_day_entry_keyboard,
)

router = Router()

MONTH_NAMES_RU = {
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

def parse_tour_context(callback_data: str) -> tuple[int, int, int]:
    """
    Для callback формата:
    action:tour_id:year:month
    """
    parts = callback_data.split(":")
    tour_id = int(parts[1])
    year = int(parts[2])
    month = int(parts[3])
    return tour_id, year, month


def parse_month_context(callback_data: str) -> tuple[int, int]:
    """
    Для callback формата:
    cal_tours:year:month
    """
    parts = callback_data.split(":")
    year = int(parts[1])
    month = int(parts[2])
    return year, month

def parse_day_card_context(callback_data: str) -> tuple[str, int, int]:
    """
    Для callback формата:
    day_card:date:year:month
    """
    parts = callback_data.split(":")
    date_str = parts[1]
    year = int(parts[2])
    month = int(parts[3])
    return date_str, year, month

def parse_multiple_day_entry_context(callback_data: str) -> tuple[int, str, int, int]:
    """
    Формат:
    multiple_day_entry:tour_id:date:year:month
    """
    parts = callback_data.split(":")
    tour_id = int(parts[1])
    date_str = parts[2]
    year = int(parts[3])
    month = int(parts[4])
    return tour_id, date_str, year, month

def parse_multiple_day_delete_context(callback_data: str) -> tuple[int, str, int, int]:
    """
    Формат:
    multiple_day_delete:tour_id:date:year:month
    """
    parts = callback_data.split(":")
    tour_id = int(parts[1])
    date_str = parts[2]
    year = int(parts[3])
    month = int(parts[4])
    return tour_id, date_str, year, month

def parse_multiple_day_delete_confirm_context(callback_data: str) -> tuple[int, str, int, int]:
    """
    Формат:
    multiple_day_delete_confirm:tour_id:date:year:month
    """
    parts = callback_data.split(":")
    tour_id = int(parts[1])
    date_str = parts[2]
    year = int(parts[3])
    month = int(parts[4])
    return tour_id, date_str, year, month

def parse_create_tour_from_day_context(callback_data: str) -> tuple[str, int, int]:
    """
    Формат:
    create_tour_from_day:date:year:month
    """
    parts = callback_data.split(":")
    date_str = parts[1]
    year = int(parts[2])
    month = int(parts[3])
    return date_str, year, month


def is_multi_day_group(tour: dict) -> bool:
    tour_group_id = tour.get("tour_group_id")

    if not tour_group_id:
        start_date = datetime.strptime(tour["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(tour["end_date"], "%Y-%m-%d").date()
        return (end_date - start_date).days >= 1

    group_rows = [dict(item) for item in get_tours_by_group_id(tour["user_id"], tour_group_id)]

    if len(group_rows) > 1:
        return True

    row = group_rows[0]
    start_date = datetime.strptime(row["start_date"], "%Y-%m-%d").date()
    end_date = datetime.strptime(row["end_date"], "%Y-%m-%d").date()

    return (end_date - start_date).days >= 1

@router.callback_query(lambda c: c.data and c.data.startswith("create_tour_from_day:"))
async def create_tour_from_free_day(callback: CallbackQuery, state: FSMContext):
    date_str, year, month = parse_create_tour_from_day_context(callback.data)

    await state.clear()
    await state.update_data(
        date_text=date_str,
        year=year,
        month=month,
        from_free_day=True,
    )
    await state.set_state(AddTourState.company)

    await callback.message.answer(
        f"Дата выбрана: {format_date(date_str)}\n\n"
        f"Введите название компании",
        reply_markup=get_company_keyboard(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("cal_tours:"))
async def open_month_tours(callback: CallbackQuery):
    user_id = callback.from_user.id
    year, month = parse_month_context(callback.data)

    days = build_day_entries_for_month(user_id, year, month)

    month_title = f"{MONTH_NAMES_RU[month]} {year}"
    text = f"Карточка тура — {month_title}\n\nВыберите день:"

    await callback.message.edit_text(
        text,
        reply_markup=get_day_entries_keyboard(days, year, month),
    )
    await callback.answer()

   
@router.callback_query(lambda c: c.data and c.data.startswith("day_card:"))
async def open_day_card(callback: CallbackQuery):
    user_id = callback.from_user.id
    date_str, year, month = parse_day_card_context(callback.data)

    card_data = get_day_card_data(user_id, date_str)

    if card_data["kind"] == "free":
        await callback.message.edit_text(
            card_data["text"],
            reply_markup=get_free_day_card_keyboard(date_str, year, month),
        )
        await callback.answer()
        return

    if card_data["kind"] == "multiple":
        await callback.message.edit_text(
            format_multiple_day_entries(date_str, card_data["entries"]),
            reply_markup=get_multiple_day_entries_keyboard(
                date_str,
                card_data["entries"],
                year,
                month,
            ),
        )
        await callback.answer()
        return

    entry = card_data["entry"]
    tour_id = entry["id"]
    entry_type = entry.get("entry_type")

    if entry_type == "day_off":
        reply_markup = get_day_off_selected_entry_keyboard(
            tour_id,
            date_str,
            year,
            month,
        )
    else:
        reply_markup = get_single_day_entry_keyboard(
            tour_id,
            date_str,
            year,
            month,
        )

    await callback.message.edit_text(
        card_data["text"],
        reply_markup=reply_markup,
    )
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("multiple_day_entry:"))
async def open_multiple_day_entry(callback: CallbackQuery):
    user_id = callback.from_user.id
    tour_id, date_str, year, month = parse_multiple_day_entry_context(callback.data)

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        build_selected_day_entry_text(date_str, tour),
        reply_markup=get_multiple_selected_entry_keyboard(tour_id, date_str, year, month),
    )
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("multiple_day_delete:"))
async def ask_delete_multiple_day_entry(callback: CallbackQuery):
    user_id = callback.from_user.id
    tour_id, date_str, year, month = parse_multiple_day_delete_context(callback.data)

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    if is_multi_day_group(tour):
        text = (
            "Если удалить этот тур, исчезнут все дни этого тура.\n\n"
            "Если хотите изменить даты тура, нажмите «Редактировать даты».\n\n"
            "Удалить весь тур?"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📅 Редактировать даты",
                        callback_data=f"edit_dates:{tour_id}:{year}:{month}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="✅ Да, удалить весь тур",
                        callback_data=f"multiple_day_delete_confirm:{tour_id}:{date_str}:{year}:{month}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data=f"multiple_day_entry:{tour_id}:{date_str}:{year}:{month}"
                    )
                ],
            ]
        )
    else:
        text = "Удалить этот тур?"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Да, удалить",
                        callback_data=f"multiple_day_delete_confirm:{tour_id}:{date_str}:{year}:{month}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data=f"multiple_day_entry:{tour_id}:{date_str}:{year}:{month}"
                    )
                ],
            ]
        )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
    )
    await callback.answer()



@router.callback_query(lambda c: c.data and c.data.startswith("multiple_day_delete_confirm:"))
async def confirm_delete_multiple_day_entry(callback: CallbackQuery):
    user_id = callback.from_user.id
    tour_id, date_str, year, month = parse_multiple_day_delete_confirm_context(callback.data)

    deleted = delete_tour(user_id, tour_id)
    if not deleted:
        await callback.answer("Тур не найден или уже удалён", show_alert=True)
        return

    # После удаления возвращаем пользователя обратно в карточку этого дня
    card_data = get_day_card_data(user_id, date_str)

    if card_data["kind"] == "free":
        await callback.message.edit_text(
            f"Тур удалён.\n\n{card_data['text']}",
            reply_markup=get_free_day_card_keyboard(date_str, year, month),
        )
        await callback.answer()
        return

    if card_data["kind"] == "multiple":
        await callback.message.edit_text(
            f"Тур удалён.\n\n{format_multiple_day_entries(date_str, card_data['entries'])}",
            reply_markup=get_multiple_day_entries_keyboard(
                date_str,
                card_data["entries"],
                year,
                month,
            ),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"Тур удалён.\n\n{card_data['text']}",
        reply_markup=get_day_card_keyboard(year, month),
    )
    await callback.answer()








def format_multiple_day_entries(date_str: str, entries: list[dict]) -> str:
    date_formatted = format_date(date_str)

    lines = [
        f"📅 Дата: {date_formatted}\n\n"
        f"На эту дату найдено несколько записей.\n"
        f"Выберите карточку:"
    ]

    return "\n".join(lines)
