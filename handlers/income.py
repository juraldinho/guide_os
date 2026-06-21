from aiogram import Router, F
from aiogram.types import Message

from services.income_service import get_income_summary

router = Router()


@router.message(F.text == "💰 Оплата")
async def show_income(message: Message) -> None:
    summary = get_income_summary(message.from_user.id)

    text = (
        "💰 Оплата\n\n"
        f"Общий доход: {summary['total_income']}$\n"
        f"Неоплаченных туров: {summary['unpaid_tours']}"
    )

    await message.answer(text)
