import logging

logger = logging.getLogger(__name__)

from aiogram import Router, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from utils.validators import (
    validate_company,
    validate_city,
    validate_income,
)

from datetime import datetime

from aiogram.fsm.context import FSMContext

from states.add_tour_state import AddTourState

from services.date_parser import parse_date_input
from keyboards.main_menu import get_main_menu

from services.tour_service import save_tour, save_day_off, get_conflicting_dates

from services.day_view_service import build_day_entries_for_month
from keyboards.tour_management import get_day_entries_keyboard


router = Router()

DATE_INPUT_HINT = (
    "Введите дату или диапазон дат.\n\n"
    "Примеры:\n"
    "• 23/03\n"
    "• 23.03\n"
    "• 2026-03-23\n"
    "• 1-2/06\n"
    "• 7.03-9.03\n"
    "• 1/06-2/06\n"
    "• 1-2/06, 4/06\n"
    "• 7.03, 9.03"
)

DATE_PARSE_ERROR_TEXT = (
    "Не удалось распознать дату.\n\n"
    "Попробуйте формат:\n"
    "23/03\n"
    "23.03\n"
    "2026-03-23\n"
    "1-2/06\n"
    "7.03-9.03\n"
    "1/06-2/06\n"
    "1-2/06, 4/06\n"
    "7.03, 9.03"
)


def get_date_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Введите дату или диапазон дат"
    )

def get_status_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Бронь"), KeyboardButton(text="Занято")],
            [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите статус"
    )


def get_skip_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Пропустить")],
            [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Введите оплату в долларах (например 100)"
    )

def get_company_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="У меня выходной")],
            [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Введите название компании или выберите кнопку"
    )

def get_city_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Введите город"
    )

def get_conflict_warning_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Сохранить как второй тур",
                    callback_data="add_tour_conflict_save"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗓 Посмотреть даты",
                    callback_data=f"add_tour_conflict_view:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="add_tour_conflict_cancel"
                )
            ],
        ]
    )

@router.callback_query(lambda c: c.data and c.data.startswith("add_tour_conflict_view:"))
async def view_conflict_dates(callback: CallbackQuery, state: FSMContext) -> None:
    _, year_str, month_str = callback.data.split(":")
    year = int(year_str)
    month = int(month_str)

    user_id = callback.from_user.id
    days = build_day_entries_for_month(user_id, year, month)

    await callback.message.edit_text(
        f"Выберите день месяца {month:02d}.{year}:",
        reply_markup=get_day_entries_keyboard(days, year, month),
    )
    await callback.answer()

@router.callback_query(F.data == "add_tour_conflict_cancel")
async def cancel_conflict_save(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Создание тура отменено")
    await callback.message.answer(
        "Возвращаю в главное меню",
        reply_markup=get_main_menu()
    )
    await callback.answer()

@router.message(F.text == "➕ Добавить тур")
async def add_tour_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AddTourState.date)
    logger.info("event=add_tour_started user_id=%s", message.from_user.id)
    
    await message.answer(
        f"➕ Новый тур\n\n{DATE_INPUT_HINT}",
        reply_markup=get_date_keyboard()
    )
    
@router.message(F.text == "❌ Отмена")
async def cancel_add_tour(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if not current_state:
        return

    await state.clear()
    await message.answer(
        "Создание тура отменено",
        reply_markup=get_main_menu()
    )

@router.message(AddTourState.company, F.text == "⬅️ Назад")
async def back_from_company(message: Message, state: FSMContext) -> None:
    await state.set_state(AddTourState.date)
    await message.answer(
        DATE_INPUT_HINT,
        reply_markup=get_date_keyboard()
    )

    
@router.message(AddTourState.city, F.text == "⬅️ Назад")
async def back_from_city(message: Message, state: FSMContext) -> None:
    await state.set_state(AddTourState.company)
    await message.answer(
        "Введите название компании",
        reply_markup=get_company_keyboard()
    )

@router.message(AddTourState.status, F.text == "⬅️ Назад")
async def back_from_status(message: Message, state: FSMContext) -> None:
    await state.set_state(AddTourState.city)
    await message.answer(
        "Введите город",
        reply_markup=get_city_keyboard()
    )

@router.message(AddTourState.income, F.text == "⬅️ Назад")
async def back_from_income(message: Message, state: FSMContext) -> None:
    await state.set_state(AddTourState.status)
    await message.answer(
        "Выберите статус",
        reply_markup=get_status_keyboard()
    )



@router.message(AddTourState.date)
async def add_tour_date(message: Message, state: FSMContext) -> None:
    date_text = message.text.strip()

    try:
        parse_date_input(date_text)
    except ValueError:
        logger.warning(
            "User %s entered invalid date input: %r",
            message.from_user.id,
            message.text,
        )        
        await message.answer(
            DATE_PARSE_ERROR_TEXT,
            reply_markup=get_date_keyboard()
        )
        return

    await state.update_data(date_text=date_text)
    await state.set_state(AddTourState.company)
    await message.answer(
        "🏢 Введите название компании",
        reply_markup=get_company_keyboard()
    )


@router.message(AddTourState.company)
async def add_tour_company(message: Message, state: FSMContext) -> None:
    try:
        company = validate_company(message.text)
    except ValueError as e:
        await message.answer(str(e))
        return

    if company == "У меня выходной":
        data = await state.get_data()
        
        logger.info("event=day_off_saved user_id=%s", message.from_user.id)
        
        logger.info(
            "User %s saving day off for %s",
            message.from_user.id,
            data["date_text"],
        )

        save_day_off(
            user_id=message.from_user.id,
            date_text=data["date_text"],
        )

        await state.clear()
        await message.answer(
            "Выходной сохранён",
            reply_markup=get_main_menu()
        )
        return

    await state.update_data(company=company)
    await state.set_state(AddTourState.city)
    await message.answer(
        "📍 Введите город",
        reply_markup=get_city_keyboard()
    )


@router.message(AddTourState.city)
async def add_tour_city(message: Message, state: FSMContext) -> None:
    try:
        city = validate_city(message.text)
    except ValueError as e:
        await message.answer(str(e))
        return

    await state.update_data(city=city)
    await state.set_state(AddTourState.status)
    await message.answer(
        "📊 Выберите статус тура",
        reply_markup=get_status_keyboard()
    )

@router.message(AddTourState.status)
async def add_tour_status(message: Message, state: FSMContext) -> None:
    raw_status = message.text.strip()

    status_map = {
        "Бронь": "reserved",
        "Занято": "confirmed",
    }

    if raw_status not in status_map:
        await message.answer("Выберите статус кнопкой")
        return

    await state.update_data(status=status_map[raw_status])
    await state.set_state(AddTourState.income)
    await message.answer(
        "💰 Введите доход в день\n\n"
        "Пример: 100\n"
        "Знак $ вводить не нужно.\n\n"
        "Или нажмите «Пропустить».",
        reply_markup=get_skip_keyboard()
    )

@router.message(AddTourState.income)
async def add_tour_income(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    income_text = message.text.strip()

    if income_text == "Пропустить":
        income = None
    else:
        try:
            income = validate_income(income_text)
        except ValueError as e:
            await message.answer(str(e))
            return

    data = await state.get_data()

    company = data["company"]
    city = data["city"]
    date_text = data["date_text"]
    status = data["status"]

    conflicts = get_conflicting_dates(user_id, date_text)

    if conflicts:
        logger.warning(
            "User %s has date conflicts for %r: %s",
            user_id,
            date_text,
            conflicts,
        )
        first_conflict = datetime.strptime(conflicts[0], "%Y-%m-%d")
        year = first_conflict.year
        month = first_conflict.month

        formatted_dates = "\n".join(
            datetime.strptime(d, "%Y-%m-%d").strftime("%d-%m-%y")
            for d in conflicts
        )

        await state.update_data(
            income=income,
            conflict_dates=conflicts,
        )

        await state.set_state(AddTourState.conflict_confirm)

        await message.answer(
            f"⚠️ Эти даты уже заняты:\n\n{formatted_dates}\n\n"
            f"Выберите, что сделать дальше:",
            reply_markup=get_conflict_warning_keyboard(year, month),
        )

        return
    
    logger.info("event=tour_saved user_id=%s", user_id)
    
    logger.info(
        "User %s saving tour: company=%r city=%r date_text=%r status=%r income=%r",
        user_id,
        company,
        city,
        date_text,
        status,
        income,
    )

    save_tour(
        user_id=user_id,
        company=company,
        city=city,
        date_text=date_text,
        status=status,
        income=income,
    )

    await state.clear()

    await message.answer(
        "Тур сохранён",
        reply_markup=get_main_menu(),
    )

@router.callback_query(F.data == "add_tour_conflict_save")
async def confirm_conflict_save(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = callback.from_user.id

    logger.info(
        "User %s saving conflicting tour: company=%r city=%r date_text=%r status=%r income=%r",
        user_id,
        data.get("company"),
        data.get("city"),
        data.get("date_text"),
        data.get("status"),
        data.get("income"),
    )

    save_tour(
        user_id=callback.from_user.id,
        company=data["company"],
        city=data["city"],
        date_text=data["date_text"],
        status=data["status"],
        income=data.get("income"),
    )

    await state.clear()
    await callback.message.edit_text("Тур сохранён как второй тур дня")
    await callback.message.answer(
        "Возвращаю в главное меню",
        reply_markup=get_main_menu()
    )
    await callback.answer()
