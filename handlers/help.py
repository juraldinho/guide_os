from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("help"))
async def help_command(message: Message) -> None:

    text = (
        "ℹ️ <b>Guide OS — помощь</b>\n\n"

        "Этот бот помогает гиду вести расписание туров.\n\n"

        "Основные возможности:\n"
        "• 📅 Календарь — посмотреть занятые и свободные даты\n"
        "• ➕ Добавить тур — записать новую экскурсию\n"
        "• 🌴 Выходной — отметить день отдыха\n"
        "• 🔎 Проверить дату — узнать свободен ли день\n"
        "• 💰 Статистика — посмотреть доход\n\n"

        "Как начать:\n"
        "1️⃣ Нажмите /start\n"
        "2️⃣ Откройте календарь\n"
        "3️⃣ Добавьте первый тур\n\n"

        "Если возникнут проблемы — напишите администратору @juraldinho"
    )

    await message.answer(text, parse_mode="HTML")
