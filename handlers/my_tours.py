from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime
from states.tour_edit import EditTourState

from services.tour_service import (
    get_current_month_tours,
    get_tour,
    delete_tour,
    edit_tour_company,
    edit_tour_city,
    edit_tour_income,
    edit_tour_note,
    edit_tour_status,
    edit_tour_payment_status,
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
)

router = Router()

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

@router.message(lambda message: message.text == "📋 Туры")
async def my_tours(message: Message):
    user_id = message.from_user.id
    tours = get_current_month_tours(user_id)

    if not tours:
        await message.answer("В этом месяце туров нет.")
        return

    await message.answer(
        "Ваши туры за текущий месяц:",
        reply_markup=get_tours_list_keyboard(tours),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("tour_view:"))
async def view_tour(callback: CallbackQuery):
    user_id = callback.from_user.id
    tour_id = int(callback.data.split(":")[1])

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "tours_back")
async def back_to_tours_list(callback: CallbackQuery):
    user_id = callback.from_user.id
    tours = get_current_month_tours(user_id)

    if not tours:
        await callback.message.edit_text("В этом месяце туров нет.")
        await callback.answer()
        return

    await callback.message.edit_text(
        "Ваши туры за текущий месяц:",
        reply_markup=get_tours_list_keyboard(tours),
    )
    await callback.answer()
    
@router.callback_query(lambda c: c.data and c.data.startswith("tour_edit_menu:"))
async def open_edit_tour_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    tour_id = int(callback.data.split(":")[1])

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        "Что хотите изменить?",
        reply_markup=get_edit_tour_menu_keyboard(tour),
    )
    await callback.answer()
    
@router.callback_query(lambda c: c.data and c.data.startswith("set_status_"))
async def set_tour_status(callback: CallbackQuery):
    user_id = callback.from_user.id
    action, tour_id_str = callback.data.split(":")
    tour_id = int(tour_id_str)

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
        reply_markup=get_edit_tour_menu_keyboard(tour),
    )
    await callback.answer()
@router.callback_query(lambda c: c.data and c.data.startswith("set_payment_"))
async def set_tour_payment_status(callback: CallbackQuery):
    user_id = callback.from_user.id
    action, tour_id_str = callback.data.split(":")
    tour_id = int(tour_id_str)

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
        reply_markup=get_edit_tour_menu_keyboard(tour),
    )
    await callback.answer()

@router.callback_query(
    lambda c: c.data and (
        c.data.startswith("edit_start_date:")
        or c.data.startswith("edit_end_date:")
    )
)

async def edit_tour_placeholder(callback: CallbackQuery):
    await callback.answer("Функция скоро будет доступна", show_alert=True)

@router.callback_query(lambda c: c.data and c.data.startswith("edit_company:"))
async def start_edit_company(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id = int(callback.data.split(":")[1])

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await state.set_state(EditTourState.waiting_for_company)
    await state.update_data(tour_id=tour_id)

    await callback.message.edit_text(
        f'Текущая компания: {tour["company"]}\n\n'
        f'Введите новое название компании\n'
        f'или выберите действие ниже:',
        reply_markup=get_edit_company_keyboard(tour_id, tour["company"]),
    )
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("edit_city:"))
async def start_edit_city(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id = int(callback.data.split(":")[1])

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await state.set_state(EditTourState.waiting_for_city)
    await state.update_data(tour_id=tour_id)

    await callback.message.edit_text(
        f'Текущий город: {tour["city"]}\n\n'
        f'Введите новый город\n'
        f'или выберите действие ниже:',
        reply_markup=get_edit_city_keyboard(tour_id, tour["city"]),
    )
    await callback.answer()

    
@router.callback_query(lambda c: c.data and c.data.startswith("edit_income:"))
async def start_edit_income(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id = int(callback.data.split(":")[1])

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await state.set_state(EditTourState.waiting_for_income)
    await state.update_data(tour_id=tour_id)

    current_income = tour["income"] if tour["income"] is not None else "—"

    await callback.message.edit_text(
        f'Текущая стоимость в день: {current_income}\n\n'
        f'Введите новую стоимость в день\n'
        f'или выберите действие ниже:',
        reply_markup=get_edit_income_keyboard(tour_id, tour["income"]),
    )
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("edit_note:"))
async def start_edit_note(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id = int(callback.data.split(":")[1])

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await state.set_state(EditTourState.waiting_for_note)
    await state.update_data(tour_id=tour_id)

    current_note = tour["note"] if tour["note"] else "—"

    await callback.message.edit_text(
        f'Текущая заметка: {current_note}\n\n'
        f'Введите новую заметку\n'
        f'или выберите действие ниже:',
        reply_markup=get_edit_note_keyboard(tour_id, tour["note"]),
    )
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("edit_note_keep:"))
async def keep_current_note(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id = int(callback.data.split(":")[1])

    await state.clear()

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id),
    )
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("edit_income_keep:"))
async def keep_current_income(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id = int(callback.data.split(":")[1])

    await state.clear()

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id),
    )
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("edit_company_keep:"))
async def keep_current_company(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id = int(callback.data.split(":")[1])

    await state.clear()

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id),
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

    if not tour_id:
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
        reply_markup=get_tour_view_keyboard(tour_id),
    )
    
@router.callback_query(lambda c: c.data and c.data.startswith("tour_delete:"))
async def ask_delete_tour(callback: CallbackQuery):
    user_id = callback.from_user.id
    tour_id = int(callback.data.split(":")[1])

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        "Удалить этот тур?",
        reply_markup=get_delete_confirmation_keyboard(tour_id),
    )
    await callback.answer()
    
@router.callback_query(lambda c: c.data and c.data.startswith("tour_delete_confirm:"))
async def confirm_delete_tour(callback: CallbackQuery):
    user_id = callback.from_user.id
    tour_id = int(callback.data.split(":")[1])

    deleted = delete_tour(user_id, tour_id)
    if not deleted:
        await callback.answer("Тур не найден или уже удалён", show_alert=True)
        return

    tours = get_current_month_tours(user_id)

    if not tours:
        await callback.message.edit_text("Тур удалён.\n\nВ этом месяце туров больше нет.")
        await callback.answer()
        return

    await callback.message.edit_text(
        "Тур удалён.\n\nВаши туры за текущий месяц:",
        reply_markup=get_tours_list_keyboard(tours),
    )
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("edit_city_keep:"))
async def keep_current_city(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tour_id = int(callback.data.split(":")[1])

    await state.clear()

    tour = get_tour(user_id, tour_id)
    if not tour:
        await callback.answer("Тур не найден", show_alert=True)
        return

    await callback.message.edit_text(
        format_tour_card(tour),
        reply_markup=get_tour_view_keyboard(tour_id),
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

    if not tour_id:
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
        reply_markup=get_tour_view_keyboard(tour_id),
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

    if not tour_id:
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
        reply_markup=get_tour_view_keyboard(tour_id),
    )

@router.message(EditTourState.waiting_for_note)
async def process_edit_note(message: Message, state: FSMContext):
    user_id = message.from_user.id
    new_note = message.text.strip()

    data = await state.get_data()
    tour_id = data.get("tour_id")

    if not tour_id:
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
        reply_markup=get_tour_view_keyboard(tour_id),
    )
