from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from config import ADMIN_ID
from keyboards.main_menu import COMMANDS_MENU_LABEL

router = Router()

PUBLIC_COMMANDS_MENU_TEXT = (
    "⚙️ <b>Команды Guide OS</b>\n\n"
    "/start — открыть главное меню\n"
    "/help — помощь и инструкция\n"
    "/profile — открыть профиль\n\n"
    "Основные функции доступны кнопками в меню ниже.\n\n"
    "📱 Guide OS Mini App открывается через синюю кнопку Menu."
)

ADMIN_COMMANDS_SECTION = (
    "/admin_report — админ-отчёт\n"
    "/broadcast — начать рассылку\n"
    "/backup — скачать backup базы данных\n"
    "/cancel — отменить активную рассылку"
)


def build_commands_menu_text(user_id: int) -> str:
    if user_id == ADMIN_ID and ADMIN_ID != 0:
        return (
            "⚙️ <b>Команды Guide OS</b>\n\n"
            "/start — открыть главное меню\n"
            "/help — помощь и инструкция\n"
            "/profile — открыть профиль\n\n"
            f"{ADMIN_COMMANDS_SECTION}\n\n"
            "Основные функции доступны кнопками в меню ниже.\n\n"
            "📱 Guide OS Mini App открывается через синюю кнопку Menu."
        )
    return PUBLIC_COMMANDS_MENU_TEXT


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
    await message.answer(
        build_commands_menu_text(message.from_user.id),
        parse_mode="HTML",
    )
