from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from keyboards.main_menu import COMMANDS_MENU_LABEL

router = Router()

COMMANDS_MENU_TEXT = (
    "⚙️ Команды Guide OS\n\n"
    "/start — открыть главное меню\n"
    "/help — помощь и описание возможностей\n\n"
    "Основные функции также доступны кнопками в меню ниже.\n\n"
    "📱 Guide OS Mini App открывается через синюю кнопку Menu."
)


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

        "🔔 <b>Уведомления (новая функция)</b>\n"
        "Бот может сам напоминать тебе о турах на завтра.\n\n"

        "Что ты получишь:\n"
        "• напоминание о времени экскурсии\n"
        "• информация о компании\n"
        "• маршрут и детали тура\n\n"

        "📌 Это помогает:\n"
        "— не забыть про тур\n"
        "— подготовиться заранее\n"
        "— не держать всё в голове\n\n"

        "👉 Включи уведомления в меню бота\n\n"

        "Как начать:\n"
        "1️⃣ Нажмите /start\n"
        "2️⃣ Откройте календарь\n"
        "3️⃣ Добавьте первый тур\n\n"

        "Если возникнут проблемы — напишите администратору @juraldinho"
    )

    await message.answer(text, parse_mode="HTML")


@router.message(F.text == COMMANDS_MENU_LABEL)
async def commands_menu_button(message: Message) -> None:
    await message.answer(COMMANDS_MENU_TEXT)
