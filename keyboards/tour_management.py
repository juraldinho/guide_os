from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def format_short_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d-%m-%y")


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
                    text="⬅️ Назад к дням месяца",
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

def get_day_card_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к дням месяца",
                    callback_data=f"cal_tours:{year}:{month}"
                )
            ],
        ]
    )

def get_day_entries_keyboard(days: list[dict], year: int, month: int) -> InlineKeyboardMarkup:
    buttons = []

    for day in days:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=day["label"],
                    callback_data=f"day_card:{day['date']}:{year}:{month}"
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад к месяцу",
                callback_data=f"cal_month:{year}:{month}"
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_free_day_card_keyboard(date_str: str, year: int, month: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Создать тур на эту дату",
                    callback_data=f"create_tour_from_day:{date_str}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к дням месяца",
                    callback_data=f"cal_tours:{year}:{month}"
                )
            ],
        ]
    )


def get_multiple_day_entries_keyboard(
    date_str: str,
    entries: list[dict],
    year: int,
    month: int,
) -> InlineKeyboardMarkup:
    buttons = []

    for entry in entries:
        if entry.get("entry_type") == "day_off":
            label = "У меня выходной"
        else:
            label = entry.get("company", "—")

        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"multiple_day_entry:{entry['id']}:{date_str}:{year}:{month}"
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад к дням месяца",
                callback_data=f"cal_tours:{year}:{month}"
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_multiple_selected_entry_keyboard(
    tour_id: int,
    date_str: str,
    year: int,
    month: int
) -> InlineKeyboardMarkup:

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
                    callback_data=f"multiple_day_delete:{tour_id}:{date_str}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"day_card:{date_str}:{year}:{month}"
                )
            ]
        ]
    )

def get_day_off_selected_entry_keyboard(
    tour_id: int,
    date_str: str,
    year: int,
    month: int
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Даты",
                    callback_data=f"edit_dates:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📝 Заметка",
                    callback_data=f"edit_note:{tour_id}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"multiple_day_delete:{tour_id}:{date_str}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к дням месяца",
                    callback_data=f"cal_tours:{year}:{month}"
                )
            ],
        ]
    )

def get_single_day_entry_keyboard(
    tour_id: int,
    date_str: str,
    year: int,
    month: int
) -> InlineKeyboardMarkup:
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
                    callback_data=f"multiple_day_delete:{tour_id}:{date_str}:{year}:{month}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к дням месяца",
                    callback_data=f"cal_tours:{year}:{month}"
                )
            ]
        ]
    )
