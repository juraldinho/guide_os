from aiogram import Router, F
from aiogram.types import Message

from services.stats_service import get_stats_summary

router = Router()

MONTHS_RU = {
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


@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message) -> None:
    user_id = message.from_user.id
    stats = get_stats_summary(user_id)

    text = (
        f"Статистика за {MONTHS_RU[stats['month']]} {stats['year']}\n\n"
        f"Туров: {stats['total_tours']}\n"
        f"Рабочих дней: {stats['working_days']}\n"
        f"Доход: {stats['total_income']}\n"
        f"Оплаченных туров: {stats['paid_tours']}\n"
        f"Неоплаченных туров: {stats['unpaid_tours']}"
    )

    await message.answer(text)
