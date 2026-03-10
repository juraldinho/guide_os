from aiogram import Router, F
from aiogram.types import Message

from services.stats_service import get_stats_summary

router = Router()


@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message) -> None:
    user_id = message.from_user.id
    stats = get_stats_summary(user_id)

    text = (
        "Statistics\n\n"
        f"Total tours: {stats['total_tours']}\n"
        f"Total income: {stats['total_income']}\n"
        f"Unpaid tours: {stats['unpaid_tours']}"
    )

    await message.answer(text)
