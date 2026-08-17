from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.queries import (
    get_user_profile,
    register_user,
    update_user_display_name,
)
from states.profile_state import ProfileState

router = Router()


def _build_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="profile_edit_name")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="profile_main_menu")],
        ]
    )


def _build_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="profile_cancel_edit")],
        ]
    )


def _format_profile_card(user_id: int, display_name: str | None) -> str:
    name = display_name if display_name else "не указано"
    return (
        "👤 Профиль\n\n"
        f"Имя: {name}\n"
        f"Telegram ID: {user_id}"
    )


async def _show_profile(target: Message | CallbackQuery, user_id: int) -> None:
    register_user(user_id)
    profile = get_user_profile(user_id)
    display_name = profile.get("display_name") if profile else None
    text = _format_profile_card(user_id, display_name)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=_build_profile_keyboard())
        await target.answer()
    else:
        await target.answer(text, reply_markup=_build_profile_keyboard())


@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_profile(message, message.from_user.id)


@router.message(F.text == "👤 Профиль")
async def btn_profile(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_profile(message, message.from_user.id)


@router.callback_query(F.data == "profile_edit_name")
async def start_edit_name(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileState.waiting_for_name)
    await callback.message.edit_text(
        "Введите имя:",
        reply_markup=_build_cancel_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "profile_cancel_edit")
async def cancel_edit_name(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _show_profile(callback, callback.from_user.id)


@router.callback_query(F.data == "profile_main_menu")
async def go_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    from keyboards.main_menu import get_main_menu
    await state.clear()
    await callback.message.edit_text("Главное меню")
    await callback.message.answer("Выберите действие:", reply_markup=get_main_menu())
    await callback.answer()


@router.message(StateFilter(ProfileState.waiting_for_name))
async def process_new_name(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    name = message.text.strip()

    if not name:
        await message.answer(
            "Имя не может быть пустым. Введите имя:",
            reply_markup=_build_cancel_keyboard(),
        )
        return

    if len(name) > 100:
        await message.answer(
            "Имя слишком длинное (максимум 100 символов). Введите имя:",
            reply_markup=_build_cancel_keyboard(),
        )
        return

    update_user_display_name(user_id, name)
    await state.clear()
    await _show_profile(message, user_id)
