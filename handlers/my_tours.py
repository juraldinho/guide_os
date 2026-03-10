from aiogram import Router
from aiogram.types import Message

from services.tour_service import get_current_month_tours

router = Router()


@router.message(lambda message: message.text == "📋 Туры")
async def my_tours(message: Message):

    user_id = message.from_user.id

    tours = get_current_month_tours(user_id)

    if not tours:
        await message.answer("В этом месяце туров нет.")
        return

    text = "Ваши туры:\n\n"

    for tour in tours:

        start = tour["start_date"]
        end = tour["end_date"]
        company = tour["company"]
        city = tour["city"]
        status = tour["status"]
        payment = tour["payment_status"]

        text += f"{start} → {end}\n"
        text += f"{city} | {company}\n"
        text += f"status: {status} | payment: {payment}\n\n"

    await message.answer(text)
