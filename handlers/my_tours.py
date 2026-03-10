from aiogram import Router
from aiogram.types import Message, CallbackQuery
from datetime import datetime

from services.tour_service import (
    get_current_month_tours,
    get_tour,
    delete_tour,
)
from keyboards.tour_management import (
    get_tours_list_keyboard,
    get_tour_view_keyboard,
    get_delete_confirmation_keyboard,
)

router = Router()

def format_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d-%m-%y")

def format_tour_card(tour: dict) -> str:
    income = tour["income"] if tour["income"] is not None else "—"
    note = tour["note"] if tour["note"] else "—"

    start_date = format_date(tour["start_date"])
    end_date = format_date(tour["end_date"])

    return (
        f"Компания: {tour['company']}\n"
        f"Город: {tour['city']}\n"
        f"Дата начала: {start_date}\n"
        f"Дата окончания: {end_date}\n"
        f"Статус: {tour['status']}\n"
        f"Оплата: {tour['payment_status']}\n"
        f"Доход в день: {income}\n"
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
