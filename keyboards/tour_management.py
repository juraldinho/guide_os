from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def format_short_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d-%m-%y")


def get_tours_list_keyboard(tours: list[dict], year: int, month: int) -> InlineKeyboardMarkup:
    buttons = []

    for tour in tours:
        start_raw = tour["start_date"]
        end_raw = tour["end_date"]

        start_dt = datetime.strptime(start_raw, "%Y-%m-%d")
        end_dt = datetime.strptime(end_raw, "%Y-%m-%d")

        days = (end_dt - start_dt).days + 1
        start_date = format_short_date(start_raw)

        company = tour["company"]
        tour_id = tour["id"]

        if days == 1:
            text = f"{start_date} | {company}"
        else:
            text = f"{start_date} | {days} дня | {company}"

        buttons.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"tour_view:{tour_id}:{year}:{month}"
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад к месяцу", callback_data=f"cal_month:{year}:{month}")]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_tour_view_keyboard(tour_id: int, year: int, month: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать",
                    callback_data=f"tour_edit_menu:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"tour_delete:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к списку",
                    callback_data=f"cal_tours:{year}:{month}"
                )
            ],
        ]
    )


def get_edit_tour_menu_keyboard(tour: dict, year: int, month: int) -> InlineKeyboardMarkup:
    tour_id = tour["id"]
    status = tour["status"]
    payment_status = tour["payment_status"]

    reserved_text = "✅ Бронь" if status == "reserved" else "Бронь"
    confirmed_text = "✅ Занято" if status == "confirmed" else "Занято"

    paid_text = "✅ Оплачено" if payment_status == "paid" else "Оплачено"
    unpaid_text = "✅ Нет оплаты" if payment_status == "unpaid" else "Нет оплаты"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Компания",
                    callback_data=f"edit_company:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Город",
                    callback_data=f"edit_city:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Даты",
                    callback_data=f"edit_dates:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Стоимость в день",
                    callback_data=f"edit_income:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Заметка",
                    callback_data=f"edit_note:{tour_id}:{year}:{month}"
                )
            ],

            [
                InlineKeyboardButton(
                    text=reserved_text,
                    callback_data=f"set_status_reserved:{tour_id}:{year}:{month}"
                ),
                InlineKeyboardButton(
                    text=confirmed_text,
                    callback_data=f"set_status_confirmed:{tour_id}:{year}:{month}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=unpaid_text,
                    callback_data=f"set_payment_unpaid:{tour_id}:{year}:{month}"
                ),
                InlineKeyboardButton(
                    text=paid_text,
                    callback_data=f"set_payment_paid:{tour_id}:{year}:{month}"
                ),
            ],

            [
                InlineKeyboardButton(
                    text="⬅️ Назад к туру",
                    callback_data=f"tour_view:{tour_id}:{year}:{month}"
                )
            ],
        ]
    )


def get_delete_confirmation_keyboard(tour_id: int, year: int, month: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=f"tour_delete_confirm:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"tour_view:{tour_id}:{year}:{month}"
                )
            ],
        ]
    )


def get_edit_company_keyboard(tour_id: int, current_company: str, year: int, month: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f'Оставить "{current_company}"',
                    callback_data=f"edit_company_keep:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"tour_edit_menu:{tour_id}:{year}:{month}"
                )
            ],
        ]
    )


def get_edit_city_keyboard(tour_id: int, current_city: str, year: int, month: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f'Оставить "{current_city}"',
                    callback_data=f"edit_city_keep:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"tour_edit_menu:{tour_id}:{year}:{month}"
                )
            ],
        ]
    )


def get_edit_income_keyboard(tour_id: int, current_income, year: int, month: int) -> InlineKeyboardMarkup:
    income_text = current_income if current_income is not None else "—"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f'Оставить "{income_text}"',
                    callback_data=f"edit_income_keep:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"tour_edit_menu:{tour_id}:{year}:{month}"
                )
            ],
        ]
    )


def get_edit_note_keyboard(tour_id: int, current_note: str | None, year: int, month: int) -> InlineKeyboardMarkup:
    note_text = current_note if current_note else "—"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f'Оставить "{note_text}"',
                    callback_data=f"edit_note_keep:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"tour_edit_menu:{tour_id}:{year}:{month}"
                )
            ],
        ]
    )
