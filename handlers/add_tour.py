import logging

logger = logging.getLogger(__name__)

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from states.add_tour_state import AddTourState
from services.tour_service import save_tour
from services.date_parser import parse_date_input
from keyboards.main_menu import get_main_menu

router = Router()

from services.tour_service import save_tour, save_day_off

def get_status_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Бронь"), KeyboardButton(text="Занято")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите статус"
    )


def get_skip_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Пропустить")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Введите оплату в долларах (например 100)"
    )

def get_company_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="У меня выходной")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Введите название компании или выберите кнопку"
    )

@router.message(F.text == "➕ Добавить тур")
async def add_tour_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AddTourState.date)
    await message.answer(
        "Введите дату или диапазон дат\n\n"
        "Поддерживаются форматы:\n"
        "23/03\n"
        "23.03\n"
        "2026-03-23\n"
        "1-2/06\n"
        "7.03-9.03\n"
        "1/06-2/06\n"
        "1-2/06, 4/06\n"
        "7.03, 9.03"
    )


@router.message(AddTourState.date)
async def add_tour_date(message: Message, state: FSMContext) -> None:
    date_text = message.text.strip()

    try:
        parse_date_input(date_text)
    except ValueError:
        await message.answer(
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
        return

    await state.update_data(date_text=date_text)
    await state.set_state(AddTourState.company)
    await message.answer(
        "Введите название компании",
        reply_markup=get_company_keyboard()
    )


@router.message(AddTourState.company)
async def add_tour_company(message: Message, state: FSMContext) -> None:
    company = message.text.strip()

    if company == "У меня выходной":
        data = await state.get_data()

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

    if not company:
        await message.answer("Название компании не должно быть пустым")
        return

    await state.update_data(company=company)
    await state.set_state(AddTourState.city)
    await message.answer("Введите город")


@router.message(AddTourState.city)
async def add_tour_city(message: Message, state: FSMContext) -> None:
    city = message.text.strip()
    if not city:
        await message.answer("Город не должен быть пустым")
        return

    await state.update_data(city=city)
    await state.set_state(AddTourState.status)
    await message.answer("Выберите статус", reply_markup=get_status_keyboard())


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
        "Введите дневную оплату в долларах\n"
        "Например: 100\n"
        "Знак $ вводить не нужно\n\n"
        "Или нажмите Пропустить",
        reply_markup=get_skip_keyboard()
    )

@router.message(AddTourState.income)
async def add_tour_income(message: Message, state: FSMContext) -> None:
    raw_income = message.text.strip()

    if raw_income == "Пропустить":
        income = None
    else:
        if not raw_income.isdigit():
            await message.answer("Доход должен быть числом")
            return
        income = int(raw_income)

    data = await state.get_data()

    save_tour(
        user_id=message.from_user.id,
        company=data["company"],
        city=data["city"],
        date_text=data["date_text"],
        status=data["status"],
        income=income,
    )

    await state.clear()
    await message.answer(
        "Тур сохранён",
        reply_markup=get_main_menu()
    )
