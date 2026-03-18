import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

from database.queries import get_all_user_ids, track_event

router = Router()
logger = logging.getLogger(__name__)

from config import ADMIN_ID


class BroadcastState(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirm = State()


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel"),
            ]
        ]
    )


@router.message(Command("broadcast"))
async def broadcast_start(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return

    await state.clear()
    await state.set_state(BroadcastState.waiting_for_message)

    await message.answer(
        "Отправь сообщение для рассылки.\n\n"
        "Можно отправить:\n"
        "• текст\n"
        "• фото с подписью\n"
        "• видео с подписью\n\n"
        "После этого я покажу предпросмотр и попрошу подтверждение.\n"
        "Чтобы отменить — /cancel"
    )


@router.message(Command("cancel"))
async def cancel_broadcast(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return

    current_state = await state.get_state()

    if current_state is None:
        await message.answer("Сейчас нет активной рассылки.")
        return

    await state.clear()
    await message.answer("Рассылка отменена.")


@router.message(BroadcastState.waiting_for_message)
async def broadcast_preview(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return

    await state.update_data(
        source_chat_id=message.chat.id,
        source_message_id=message.message_id,
    )
    await state.set_state(BroadcastState.waiting_for_confirm)

    await message.answer("Предпросмотр рассылки:")
    await message.send_copy(chat_id=message.chat.id)

    await message.answer(
        "Отправить это сообщение всем пользователям?",
        reply_markup=get_broadcast_confirm_keyboard(),
    )


@router.callback_query(BroadcastState.waiting_for_confirm, F.data == "broadcast_cancel")
async def broadcast_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return

    await state.clear()
    await callback.message.edit_text("Рассылка отменена.")
    await callback.answer()


@router.callback_query(BroadcastState.waiting_for_confirm, F.data == "broadcast_confirm")
async def broadcast_confirm_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return

    data = await state.get_data()
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")

    if not source_chat_id or not source_message_id:
        await state.clear()
        await callback.message.edit_text("Не удалось найти сообщение для рассылки.")
        await callback.answer()
        return

    users = get_all_user_ids()

    if not users:
        await state.clear()
        await callback.message.edit_text("Пользователей для рассылки нет.")
        await callback.answer()
        return

    sent_count = 0
    failed_count = 0

    await callback.message.edit_text(f"Начинаю рассылку. Пользователей: {len(users)}")
    await callback.answer()

    for user_id in users:
        try:
            await callback.bot.copy_message(
                chat_id=user_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id,
            )
            sent_count += 1
            await asyncio.sleep(0.05)

        except Exception:
            failed_count += 1
            logger.exception("Broadcast failed for user_id=%s", user_id)

    track_event(callback.from_user.id, "broadcast_sent")

    await callback.message.answer(
        f"Рассылка завершена.\n"
        f"Отправлено: {sent_count}\n"
        f"Ошибок: {failed_count}"
    )

    await state.clear()


