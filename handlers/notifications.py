import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.queries import (
    get_user_notification_settings,
    set_notification_time,
    set_notifications_enabled,
)
from keyboards.main_menu import get_main_menu

router = Router()


class NotificationState(StatesGroup):
    waiting_for_time = State()


def build_notifications_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    if enabled:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⏰ Изменить время", callback_data="notif:set_time")],
                [InlineKeyboardButton(text="🔕 Выключить уведомление", callback_data="notif:disable")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="notif:back")],
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Включить уведомление", callback_data="notif:enable")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="notif:back")],
        ]
    )


def build_enable_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Оставить 21:00", callback_data="notif:enable_default")],
            [InlineKeyboardButton(text="⏰ Задать своё время", callback_data="notif:set_time")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="notif:back_to_settings")],
        ]
    )


def build_set_time_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="notif:back_to_settings")],
        ]
    )


def render_notifications_text(settings: dict) -> str:
    if settings["notifications_enabled"]:
        return (
            "🔔 <b>Уведомления включены</b>\n\n"
            f"Напоминание будет приходить каждый день в <b>{settings['notification_time']}</b>, "
            "если на завтра у вас есть тур или выходной.\n\n"
            "Бот отправит карточку записи с кнопкой «Открыть тур»."
        )

    return (
        "🔔 <b>Уведомления выключены</b>\n\n"
        "Напоминание будет приходить за день до тура.\n"
        "По умолчанию время отправки: <b>21:00</b>.\n\n"
        "После включения можно оставить это время или задать своё."
    )


def normalize_time_input(value: str) -> str | None:
    text = value.strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    if hour < 0 or hour > 23:
        return None

    if minute < 0 or minute > 59:
        return None

    return f"{hour:02d}:{minute:02d}"


@router.message(F.text == "🔔 Уведомления")
async def open_notifications(message: Message, state: FSMContext) -> None:
    await state.clear()

    settings = get_user_notification_settings(message.from_user.id)

    await message.answer(
        render_notifications_text(settings),
        reply_markup=build_notifications_keyboard(settings["notifications_enabled"]),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "notif:enable")
async def ask_enable_options(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()

    await callback.message.edit_text(
        "🔔 <b>Включить уведомления</b>\n\n"
        "По умолчанию напоминание будет приходить в <b>21:00</b>.\n"
        "Можно оставить это время или задать своё.",
        reply_markup=build_enable_choice_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "notif:enable_default")
async def enable_default_notifications(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()

    user_id = callback.from_user.id
    set_notification_time(user_id, "21:00")
    set_notifications_enabled(user_id, True)

    settings = get_user_notification_settings(user_id)

    await callback.message.edit_text(
        "✅ <b>Уведомления включены</b>\n\n"
        "Напоминание будет приходить в <b>21:00</b>, если на завтра есть тур или выходной.",
        reply_markup=build_notifications_keyboard(True),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "notif:disable")
async def disable_notifications(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()

    set_notifications_enabled(callback.from_user.id, False)
    settings = get_user_notification_settings(callback.from_user.id)

    await callback.message.edit_text(
        render_notifications_text(settings),
        reply_markup=build_notifications_keyboard(False),
        parse_mode="HTML",
    )
    await callback.answer("Уведомления выключены")


@router.callback_query(F.data == "notif:set_time")
async def ask_notification_time(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NotificationState.waiting_for_time)

    await callback.message.edit_text(
        "⏰ <b>Введите время уведомления</b>\n\n"
        "Формат: <b>чч:мм</b>\n"
        "Примеры:\n"
        "16:00\n"
        "8:00",
        reply_markup=build_set_time_back_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(NotificationState.waiting_for_time)
async def save_notification_time(message: Message, state: FSMContext) -> None:
    normalized_time = normalize_time_input(message.text or "")

    if not normalized_time:
        await message.answer(
            "Неверный формат времени.\n\n"
            "Введите время так:\n"
            "16:00\n"
            "8:00"
        )
        return

    user_id = message.from_user.id
    set_notification_time(user_id, normalized_time)
    set_notifications_enabled(user_id, True)

    await state.clear()

    settings = get_user_notification_settings(user_id)

    await message.answer(
        "✅ Уведомления включены.\n\n"
        f"Теперь напоминание будет приходить в {normalized_time}, "
        "если на завтра есть тур или выходной.",
        reply_markup=get_main_menu(),
    )

    await message.answer(
        render_notifications_text(settings),
        reply_markup=build_notifications_keyboard(True),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "notif:back_to_settings")
async def back_to_notification_settings(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()

    settings = get_user_notification_settings(callback.from_user.id)

    await callback.message.edit_text(
        render_notifications_text(settings),
        reply_markup=build_notifications_keyboard(settings["notifications_enabled"]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "notif:back")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()

    await callback.message.edit_text("Главное меню")
    await callback.answer()
