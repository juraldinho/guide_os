from services.day_view_service import build_day_entries_for_month
from calendar import monthrange
from datetime import datetime, date

from services.day_card_service import get_day_card_data

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.queries import get_tours_for_month
from states.tour_edit import EditTourState
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
    get_tours_list_keyboard,
    get_tour_view_keyboard,
    get_edit_tour_menu_keyboard,
    get_edit_company_keyboard,
    get_edit_city_keyboard,
    get_edit_income_keyboard,
    get_edit_note_keyboard,
    get_delete_confirmation_keyboard,
    get_day_card_keyboard,
    get_test_day_cards_keyboard,
    get_day_entries_keyboard,
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

def format_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d-%m-%y")


def format_tour_status(status: str) -> str:
    status_map = {
        "reserved": "Бронь",
        "confirmed": "Занято",
    }
    return status_map.get(status, status)


def format_payment_status(payment_status: str) -> str:
    payment_map = {
        "paid": "Оплачено",
        "unpaid": "Нет оплаты",
    }
    return payment_map.get(payment_status, payment_status)


def format_tour_card(tour: dict) -> str:
    income = tour["income"] if tour["income"] is not None else "—"
    note = tour["note"] if tour["note"] else "—"

    start_date = format_date(tour["start_date"])
    end_date = format_date(tour["end_date"])
    tour_status = format_tour_status(tour["status"])
    payment_status = format_payment_status(tour["payment_status"])

    return (
        f"Компания: {tour['company']}\n"
        f"Город: {tour['city']}\n"
        f"Дата начала: {start_date}\n"
        f"Дата окончания: {end_date}\n"
        f"Статус: {tour_status}\n"
        f"Оплата: {payment_status}\n"
        f"Стоимость в день: {income}\n"
        f"Заметка: {note}"
    )


def get_month_bounds(year: int, month: int) -> tuple[str, str]:
    last_day = monthrange(year, month)[1]
    month_start = date(year, month, 1).isoformat()
    month_end = date(year, month, last_day).isoformat()
    return month_start, month_end


def get_month_tours(user_id: int, year: int, month: int) -> list[dict]:
    month_start, month_end = get_month_bounds(year, month)
    return get_tours_for_month(user_id, month_start, month_end)


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

def parse_day_cards_month_context(callback_data: str) -> tuple[int, int]:
    """
    Для callback формата:
    cal_day_cards:year:month
    """
    parts = callback_data.split(":")
    year = int(parts[1])
    month = int(parts[2])
    return year, month

def format_multiple_day_entries(date_str: str, entries: list[dict]) -> str:
    date_formatted = format_date(date_str)

    lines = [
        f"Дата: {date_formatted}",
        "На эту дату найдено несколько записей:",
        "",
    ]

    for entry in entries:
        if entry.get("entry_type") == "day_off":
            label = "У меня выходной"
        else:
            label = entry.get("company", "—")

        lines.append(f"• {label}")

    return "\n".join(lines)

def parse_test_days_context(callback_data: str) -> tuple[int, int]:
    """
    Для callback формата:
    cal_tours_test_days:year:month
    """
    parts = callback_data.split(":")
    year = int(parts[1])
    month = int(parts[2])
    return year, month

@router.callback_query(lambda c: c.data and c.data.startswith("cal_tours:"))
async def open_month_tours(callback: CallbackQuery):
    user_id = callback.from_user.id
    year, month = parse_month_context(callback.data)

    tours = get_month_tours(user_id, year, month)

    if not tours:
        await callback.message.edit_text(
            "В этом месяце туров нет."
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"Туры за {month:02d}.{year}:",
        reply_markup=get_tours_list_keyboard(tours, year, month),
    )
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("cal_day_cards:"))
async def open_month_day_cards(callback: CallbackQuery):
    user_id = callback.from_user.id
    year, month = parse_day_cards_month_context(callback.data)

    days = build_day_entries_for_month(user_id, year, month)

    month_title = f"{MONTH_NAMES_RU[month]} {year}"
    text = f"Карточка тура — {month_title}\n\nВыберите день:"

    await callback.message.edit_text(
        text,
        reply_markup=get_day_entries_keyboard(days, year, month),
    )
    await callback.answer()
    
@router.callback_query(lambda c: c.data and c.data.startswith("cal_tours_test_days:"))
async def open_test_day_cards(callback: CallbackQuery):
    year, month = parse_test_days_context(callback.data)

    await callback.message.edit_text(
        f"Тест дневных карточек за {month:02d}.{year}:",
        reply_markup=get_test_day_cards_keyboard(year, month),
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
            reply_markup=get_day_card_keyboard(year, month),
        )
        await callback.answer()
        return

    if card_data["kind"] == "multiple":
        await callback.message.edit_text(
            format_multiple_day_entries(date_str, card_data["entries"]),
            reply_markup=get_day_card_keyboard(year, month),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        card_data["text"],
        reply_markup=get_day_card_keyboard(year, month),
    )
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("tour_view:"))
async def view_tour(callback: CallbackQuery):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id, year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("tour_edit_menu:"))
async def open_edit_tour_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        "Что хотите изменить?",
        reply_markup=get_edit_tour_menu_keyboard(tour, year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("set_status_"))
async def set_tour_status(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    action = parts[0]
    tour_id = int(parts[1])
    year = int(parts[2])
    month = int(parts[3])

    if action == "set_status_reserved":
        new_status = "reserved"
    elif action == "set_status_confirmed":
        new_status = "confirmed"
    else:
        await callback.answer("Некорректный статус", show_alert=True)
        return

    updated = edit_tour_status(user_id, tour_id, new_status)
    if not updated:
        await callback.answer("Не удалось обновить статус", show_alert=True)
        return

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        "Что хотите изменить?",
        reply_markup=get_edit_tour_menu_keyboard(tour, year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("set_payment_"))
async def set_tour_payment_status(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    action = parts[0]
    tour_id = int(parts[1])
    year = int(parts[2])
    month = int(parts[3])

    if action == "set_payment_paid":
        new_payment_status = "paid"
    elif action == "set_payment_unpaid":
        new_payment_status = "unpaid"
    else:
        await callback.answer("Некорректный статус оплаты", show_alert=True)
        return

    updated = edit_tour_payment_status(user_id, tour_id, new_payment_status)
    if not updated:
        await callback.answer("Не удалось обновить оплату", show_alert=True)
        return

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        "Что хотите изменить?",
        reply_markup=get_edit_tour_menu_keyboard(tour, year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit_company:"))
async def start_edit_company(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await state.set_state(EditTourState.waiting_for_company)
    await state.update_data(tour_id=tour_id, year=year, month=month)

    await callback.message.edit_text(
        f'Текущая компания: {tour["company"]}\n\n'
        f'Введите новое название компании\n'
        f'или выберите действие ниже:',
        reply_markup=get_edit_company_keyboard(tour_id, tour["company"], year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit_city:"))
async def start_edit_city(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await state.set_state(EditTourState.waiting_for_city)
    await state.update_data(tour_id=tour_id, year=year, month=month)

    await callback.message.edit_text(
        f'Текущий город: {tour["city"]}\n\n'
        f'Введите новый город\n'
        f'или выберите действие ниже:',
        reply_markup=get_edit_city_keyboard(tour_id, tour["city"], year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit_income:"))
async def start_edit_income(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await state.set_state(EditTourState.waiting_for_income)
    await state.update_data(tour_id=tour_id, year=year, month=month)

    current_income = tour["income"] if tour["income"] is not None else "—"

    await callback.message.edit_text(
        f'Текущая стоимость в день: {current_income}\n\n'
        f'Введите новую стоимость в день\n'
        f'или выберите действие ниже:',
        reply_markup=get_edit_income_keyboard(tour_id, tour["income"], year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit_note:"))
async def start_edit_note(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await state.set_state(EditTourState.waiting_for_note)
    await state.update_data(tour_id=tour_id, year=year, month=month)

    current_note = tour["note"] if tour["note"] else "—"

    await callback.message.edit_text(
        f'Текущая заметка: {current_note}\n\n'
        f'Введите новую заметку\n'
        f'или выберите действие ниже:',
        reply_markup=get_edit_note_keyboard(tour_id, tour["note"], year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit_dates:"))
async def start_edit_dates(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    current_start = format_date(tour["start_date"])
    current_end = format_date(tour["end_date"])

    await state.set_state(EditTourState.waiting_for_dates)
    await state.update_data(tour_id=tour_id, year=year, month=month)

    await callback.message.edit_text(
        f"Текущие даты: {current_start} — {current_end}\n\n"
        f"Введите новую дату или диапазон.\n\n"
        f"Примеры:\n"
        f"12/03\n"
        f"12-14/03\n"
        f"2026-03-12"
    )
    await callback.answer()


@router.message(EditTourState.waiting_for_dates)
async def process_edit_dates(message: Message, state: FSMContext):
    user_id = message.from_user.id
    date_text = message.text.strip()

    data = await state.get_data()
    tour_id = data.get("tour_id")
    year = data.get("year")
    month = data.get("month")

    if not tour_id or not year or not month:
        await state.clear()
        await message.answer("Ошибка. Откройте тур заново.")
        return

    try:
        updated = edit_tour_dates(user_id, tour_id, date_text)
    except ValueError:
        await message.answer(
            "Не удалось распознать дату.\n\n"
            "Введите дату заново.\n"
            "Примеры:\n"
            "12/03\n"
            "12-14/03\n"
            "2026-03-12"
        )
        return

    if not updated:
        await message.answer(
            "Нужна одна дата или один диапазон.\n\n"
            "Примеры:\n"
            "12/03\n"
            "12-14/03\n"
            "2026-03-12"
        )
        return

    tour = get_tour(user_id, tour_id)
    await state.clear()

    if not tour:
        await message.answer("Даты обновлены, но тур не найден.")
        return

    await message.answer(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id, year, month),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("edit_note_keep:"))
async def keep_current_note(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    await state.clear()

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id, year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit_income_keep:"))
async def keep_current_income(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    await state.clear()

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id, year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit_company_keep:"))
async def keep_current_company(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    await state.clear()

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id, year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit_city_keep:"))
async def keep_current_city(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    await state.clear()

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id, year, month),
    )
    await callback.answer()


@router.message(EditTourState.waiting_for_company)
async def process_edit_company(message: Message, state: FSMContext):
    user_id = message.from_user.id
    new_company = message.text.strip()

    if not new_company:
        await message.answer("Название компании не может быть пустым. Введите новое название:")
        return

    data = await state.get_data()
    tour_id = data.get("tour_id")
    year = data.get("year")
    month = data.get("month")

    if not tour_id or not year or not month:
        await state.clear()
        await message.answer("Ошибка. Откройте тур заново.")
        return

    updated = edit_tour_company(user_id, tour_id, new_company)
    if not updated:
        await state.clear()
        await message.answer("Не удалось обновить компанию.")
        return

    tour = get_tour(user_id, tour_id)
    await state.clear()

    if not tour:
        await message.answer("Компания обновлена, но тур не найден.")
        return

    await message.answer(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id, year, month),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("tour_delete:"))
async def ask_delete_tour(callback: CallbackQuery):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        "Удалить этот тур?",
        reply_markup=get_delete_confirmation_keyboard(tour_id, year, month),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("tour_delete_confirm:"))
async def confirm_delete_tour(callback: CallbackQuery):
    user_id = callback.from_user.id
    tour_id, year, month = parse_tour_context(callback.data)

    deleted = delete_tour(user_id, tour_id)
    if not deleted:
        await callback.answer("Тур не найден или уже удалён", show_alert=True)
        return

    tours = get_month_tours(user_id, year, month)

    if not tours:
        await callback.message.edit_text(
            "Тур удалён.\n\nВ этом месяце туров больше нет."
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"Тур удалён.\n\nТуры за {month:02d}.{year}:",
        reply_markup=get_tours_list_keyboard(tours, year, month),
    )
    await callback.answer()


@router.message(EditTourState.waiting_for_city)
async def process_edit_city(message: Message, state: FSMContext):
    user_id = message.from_user.id
    new_city = message.text.strip()

    if not new_city:
        await message.answer("Город не может быть пустым. Введите новый город:")
        return

    data = await state.get_data()
    tour_id = data.get("tour_id")
    year = data.get("year")
    month = data.get("month")

    if not tour_id or not year or not month:
        await state.clear()
        await message.answer("Ошибка. Откройте тур заново.")
        return

    updated = edit_tour_city(user_id, tour_id, new_city)
    if not updated:
        await state.clear()
        await message.answer("Не удалось обновить город.")
        return

    tour = get_tour(user_id, tour_id)
    await state.clear()

    if not tour:
        await message.answer("Город обновлён, но тур не найден.")
        return

    await message.answer(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id, year, month),
    )


@router.message(EditTourState.waiting_for_income)
async def process_edit_income(message: Message, state: FSMContext):
    user_id = message.from_user.id
    income_text = message.text.strip()

    if not income_text.isdigit():
        await message.answer("Введите стоимость числом, например: 100")
        return

    new_income = int(income_text)

    data = await state.get_data()
    tour_id = data.get("tour_id")
    year = data.get("year")
    month = data.get("month")

    if not tour_id or not year or not month:
        await state.clear()
        await message.answer("Ошибка. Откройте тур заново.")
        return

    updated = edit_tour_income(user_id, tour_id, new_income)
    if not updated:
        await state.clear()
        await message.answer("Не удалось обновить стоимость.")
        return

    tour = get_tour(user_id, tour_id)
    await state.clear()

    if not tour:
        await message.answer("Стоимость обновлена, но тур не найден.")
        return

    await message.answer(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id, year, month),
    )


@router.message(EditTourState.waiting_for_note)
async def process_edit_note(message: Message, state: FSMContext):
    user_id = message.from_user.id
    new_note = message.text.strip()

    data = await state.get_data()
    tour_id = data.get("tour_id")
    year = data.get("year")
    month = data.get("month")

    if not tour_id or not year or not month:
        await state.clear()
        await message.answer("Ошибка. Откройте тур заново.")
        return

    updated = edit_tour_note(user_id, tour_id, new_note)
    if not updated:
        await state.clear()
        await message.answer("Не удалось обновить заметку.")
        return

    tour = get_tour(user_id, tour_id)
    await state.clear()

    if not tour:
        await message.answer("Заметка обновлена, но тур не найден.")
        return

    await message.answer(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id, year, month),
    )
