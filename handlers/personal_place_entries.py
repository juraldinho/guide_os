from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import TIMEZONE
from services.external_sales_service import (
    ExternalSale,
    ExternalSaleConflictError,
    ExternalSalePlaceNotFoundError,
    ExternalSalesService,
    ExternalSaleValidationError,
    ISO_4217_CODES,
)
from services.personal_places_service import PersonalPlacesService, PersonalPlaceValidationError
from states.personal_places import PersonalPlaceEntryCreateState, PersonalPlaceEntryEditState


router = Router()
LOCAL_TZ = ZoneInfo(TIMEZONE)
SAFE_ENTRY_TEXT = "Запись не найдена или недоступна."
INVALID_VALUE_TEXT = "Проверьте введённое значение."
OUTCOME_REQUIRED_TEXT = "Укажите полученные баллы или полученную сумму."


def _entries() -> ExternalSalesService:
    return ExternalSalesService()


def _places() -> PersonalPlacesService:
    return PersonalPlacesService()


def _keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


def _is_callback(target: Message | CallbackQuery) -> bool:
    return hasattr(target, "message")


def _entry_date(entry: ExternalSale) -> date:
    return datetime.fromisoformat(entry.occurred_at.replace("Z", "+00:00")).astimezone(
        LOCAL_TZ
    ).date()


def _money_text(minor: int, currency: str) -> str:
    value = Decimal(minor) / Decimal(100)
    return f"{value:.2f} {escape(currency)}"


def render_recent_entries(entries: list[ExternalSale]) -> str:
    if not entries:
        return "Записей о полученных результатах пока нет."
    lines = ["<b>Последние записи:</b>"]
    for entry in reversed(entries[-5:]):
        outcomes = []
        if entry.received_points is not None:
            outcomes.append(f"комиссия {entry.received_points}")
        if entry.received_income_minor is not None and entry.currency:
            outcomes.append("денежный результат")
        lines.append(f"• {_entry_date(entry).strftime('%d.%m.%Y')} — {', '.join(outcomes)}")
    return "\n".join(lines)


def entry_action_rows(place_id: str, entries: list[ExternalSale], *, active: bool):
    rows = [[("🧾 " + _entry_date(entry).strftime("%d.%m.%Y"), f"ppe:view:{entry.public_id}")]
            for entry in reversed(entries[-5:])]
    if active:
        rows.insert(0, [("➕ Добавить запись", f"ppe:add:{place_id}")])
    return rows


def _detail_text(entry: ExternalSale, place_name: str) -> str:
    lines = [
        "🧾 <b>Личная запись</b>",
        f"<b>Место:</b> {escape(place_name)}",
        f"<b>Дата:</b> {_entry_date(entry).strftime('%d.%m.%Y')}",
    ]
    if entry.received_points is not None:
        lines.append(f"<b>Полученная комиссия:</b> {entry.received_points}")
    if entry.received_income_minor is not None and entry.currency:
        lines.append("<b>Денежный результат:</b> сохранён")
    if entry.note:
        lines.append(f"<b>Заметка:</b> {escape(entry.note)}")
    status = "Активна" if entry.status == "active" else "Неактивна"
    lines.append(f"<b>Статус:</b> {status}")
    return "\n".join(lines)


def _detail_keyboard(entry: ExternalSale) -> InlineKeyboardMarkup:
    rows = []
    if entry.status == "active":
        rows.extend([
            [("✏️ Редактировать комиссию", f"ppe:edit:points:{entry.public_id}")],
            [("✏️ Редактировать дату", f"ppe:edit:date:{entry.public_id}")],
            [("✏️ Редактировать заметку", f"ppe:edit:note:{entry.public_id}")],
            [("🚫 Деактивировать", f"ppe:deactivate:{entry.public_id}")],
        ])
    rows.append([("⬅️ Назад к месту", f"pp:view:{entry.personal_place_id}")])
    return _keyboard(rows)


def _get_entry(user_id: int, entry_id: str) -> ExternalSale | None:
    try:
        return _entries().get(user_id=user_id, public_id=entry_id)
    except ExternalSaleValidationError:
        return None


async def _show_entry(target: Message | CallbackQuery, user_id: int, entry: ExternalSale):
    try:
        place = _places().get(user_id=user_id, public_id=entry.personal_place_id)
    except PersonalPlaceValidationError:
        place = None
    if place is None:
        method = target.message.edit_text if _is_callback(target) else target.answer
        await method(SAFE_ENTRY_TEXT)
        if _is_callback(target):
            await target.answer()
        return
    method = target.message.edit_text if _is_callback(target) else target.answer
    await method(
        _detail_text(entry, place.name),
        parse_mode="HTML",
        reply_markup=_detail_keyboard(entry),
    )
    if _is_callback(target):
        await target.answer()


def _form_keyboard(*, skip: bool = False, today: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if skip:
        rows.append([("Пропустить", "ppe:form_skip")])
    if today:
        rows.append([("Сегодня", "ppe:form_today")])
    rows.append([("⬅️ Назад", "ppe:form_back"), ("❌ Отмена", "ppe:form_cancel")])
    return _keyboard(rows)


async def _prompt(target: Message | CallbackQuery, state: FSMContext, field: str):
    prompts = {
        "points": "Введите полученную комиссию:",
        "money": "Введите уже полученную сумму или пропустите:",
        "currency": "Введите код валюты, например UZS или USD:",
        "occurred_date": "Введите дату результата в формате ДД.ММ.ГГГГ или выберите сегодня:",
        "note": "Введите заметку или пропустите:",
    }
    states = {
        "points": PersonalPlaceEntryCreateState.points,
        "money": PersonalPlaceEntryCreateState.money,
        "currency": PersonalPlaceEntryCreateState.currency,
        "occurred_date": PersonalPlaceEntryCreateState.occurred_date,
        "note": PersonalPlaceEntryCreateState.note,
    }
    await state.set_state(states[field])
    method = target.message.edit_text if _is_callback(target) else target.answer
    await method(
        prompts[field],
        reply_markup=_form_keyboard(skip=field == "note", today=field == "occurred_date"),
    )
    if _is_callback(target):
        await target.answer()


def _parse_points(value: str) -> int | None:
    if value == "0":
        return None
    try:
        parsed = Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None
    if parsed <= 0 or parsed != parsed.to_integral_value():
        return None
    return int(parsed)


def _parse_money(value: str) -> int | None:
    if value == "0":
        return None
    try:
        parsed = Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None
    if parsed <= 0 or parsed.as_tuple().exponent < -2:
        return None
    return int(parsed * 100)


def _parse_date(value: str) -> datetime | None:
    for pattern in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, pattern).date()
            return datetime.combine(parsed, datetime.min.time(), tzinfo=LOCAL_TZ)
        except ValueError:
            continue
    return None


async def _after_money(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("received_points") is None and data.get("received_income_minor") is None:
        method = target.message.edit_text if _is_callback(target) else target.answer
        await method(OUTCOME_REQUIRED_TEXT, reply_markup=_form_keyboard(skip=True))
        if _is_callback(target):
            await target.answer()
        return
    if data.get("received_income_minor") is not None:
        await _prompt(target, state, "currency")
    else:
        await state.update_data(currency=None)
        await _prompt(target, state, "occurred_date")


@router.callback_query(F.data.startswith("ppe:add:"))
async def start_entry(callback: CallbackQuery, state: FSMContext) -> None:
    place_id = callback.data.removeprefix("ppe:add:")
    try:
        place = _places().get(user_id=callback.from_user.id, public_id=place_id)
    except PersonalPlaceValidationError:
        place = None
    if place is None or place.status != "active":
        await callback.answer(SAFE_ENTRY_TEXT)
        return
    await state.clear()
    await state.update_data(
        personal_place_id=place_id,
        received_points=None,
        received_income_minor=None,
        currency=None,
        occurred_at=None,
        note=None,
    )
    await _prompt(callback, state, "points")


@router.message(StateFilter(PersonalPlaceEntryCreateState.points))
async def receive_points(message: Message, state: FSMContext) -> None:
    value = _parse_points(message.text.strip() if isinstance(message.text, str) else "")
    if value is None:
        await message.answer(INVALID_VALUE_TEXT)
        return
    await state.update_data(received_points=value)
    await state.update_data(received_income_minor=None, currency=None)
    await _prompt(message, state, "occurred_date")


@router.message(StateFilter(PersonalPlaceEntryCreateState.money))
async def receive_money(message: Message, state: FSMContext) -> None:
    value = _parse_money(message.text.strip() if isinstance(message.text, str) else "")
    if value is None:
        await message.answer(INVALID_VALUE_TEXT, reply_markup=_form_keyboard(skip=True))
        return
    await state.update_data(received_income_minor=value)
    await _after_money(message, state)


@router.message(StateFilter(PersonalPlaceEntryCreateState.currency))
async def receive_currency(message: Message, state: FSMContext) -> None:
    currency = message.text.strip().upper() if isinstance(message.text, str) else ""
    if currency not in ISO_4217_CODES:
        await message.answer(INVALID_VALUE_TEXT)
        return
    await state.update_data(currency=currency)
    await _prompt(message, state, "occurred_date")


@router.message(StateFilter(PersonalPlaceEntryCreateState.occurred_date))
async def receive_date(message: Message, state: FSMContext) -> None:
    occurred = _parse_date(message.text.strip() if isinstance(message.text, str) else "")
    if occurred is None or occurred.date() > datetime.now(LOCAL_TZ).date():
        await message.answer(INVALID_VALUE_TEXT, reply_markup=_form_keyboard(today=True))
        return
    await state.update_data(occurred_at=occurred)
    await _prompt(message, state, "note")


@router.message(StateFilter(PersonalPlaceEntryCreateState.note))
async def receive_note(message: Message, state: FSMContext) -> None:
    note = message.text.strip() if isinstance(message.text, str) else ""
    if len(note) > 500:
        await message.answer(INVALID_VALUE_TEXT, reply_markup=_form_keyboard(skip=True))
        return
    await state.update_data(note=note or None)
    await _show_confirmation(message, state)


@router.callback_query(F.data == "ppe:form_skip")
async def skip_field(callback: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    if current == PersonalPlaceEntryCreateState.points.state:
        await callback.answer(INVALID_VALUE_TEXT)
    elif current == PersonalPlaceEntryCreateState.money.state:
        await state.update_data(received_income_minor=None)
        await _after_money(callback, state)
    elif current == PersonalPlaceEntryCreateState.note.state:
        await state.update_data(note=None)
        await _show_confirmation(callback, state)
    else:
        await callback.answer(SAFE_ENTRY_TEXT)


@router.callback_query(F.data == "ppe:form_today")
async def use_today(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != PersonalPlaceEntryCreateState.occurred_date.state:
        await callback.answer(SAFE_ENTRY_TEXT)
        return
    today = datetime.combine(datetime.now(LOCAL_TZ).date(), datetime.min.time(), tzinfo=LOCAL_TZ)
    await state.update_data(occurred_at=today)
    await _prompt(callback, state, "note")


async def _show_confirmation(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lines = ["🧾 <b>Проверьте запись</b>"]
    if data.get("received_points") is not None:
        lines.append(f"Полученная комиссия: {data['received_points']}")
    lines.append(f"Дата: {data['occurred_at'].strftime('%d.%m.%Y')}")
    if data.get("note"):
        lines.append(f"Заметка: {escape(data['note'])}")
    await state.set_state(PersonalPlaceEntryCreateState.confirm)
    method = target.message.edit_text if _is_callback(target) else target.answer
    await method(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_keyboard([
            [("✅ Сохранить", "ppe:form_confirm")],
            [("⬅️ Назад", "ppe:form_back"), ("❌ Отмена", "ppe:form_cancel")],
        ]),
    )
    if _is_callback(target):
        await target.answer()


@router.callback_query(F.data == "ppe:form_back")
async def back_field(callback: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    data = await state.get_data()
    if current == PersonalPlaceEntryCreateState.points.state:
        await _return_to_place(callback, state, data.get("personal_place_id"))
    elif current == PersonalPlaceEntryCreateState.money.state:
        await _prompt(callback, state, "points")
    elif current == PersonalPlaceEntryCreateState.currency.state:
        await _prompt(callback, state, "money")
    elif current == PersonalPlaceEntryCreateState.occurred_date.state:
        await _prompt(callback, state, "points")
    elif current == PersonalPlaceEntryCreateState.note.state:
        await _prompt(callback, state, "occurred_date")
    elif current == PersonalPlaceEntryCreateState.confirm.state:
        await _prompt(callback, state, "note")
    else:
        await callback.answer(SAFE_ENTRY_TEXT)


@router.callback_query(F.data == "ppe:form_cancel")
async def cancel_entry(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await _return_to_place(callback, state, data.get("personal_place_id"))


async def _return_to_place(callback: CallbackQuery, state: FSMContext, place_id):
    try:
        place = _places().get(user_id=callback.from_user.id, public_id=place_id)
    except PersonalPlaceValidationError:
        place = None
    await state.clear()
    if place is None:
        await callback.answer(SAFE_ENTRY_TEXT)
        return
    from handlers.personal_places import _show_detail
    await _show_detail(callback, place)


@router.callback_query(
    StateFilter(PersonalPlaceEntryCreateState.confirm),
    F.data == "ppe:form_confirm",
)
async def confirm_entry(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        entry = _entries().create(user_id=callback.from_user.id, **data)
    except (
        ExternalSaleValidationError,
        ExternalSaleConflictError,
        ExternalSalePlaceNotFoundError,
    ):
        await callback.answer(INVALID_VALUE_TEXT)
        return
    await state.clear()
    await _show_entry(callback, callback.from_user.id, entry)


@router.callback_query(F.data.startswith("ppe:view:"))
async def view_entry(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    entry = _get_entry(callback.from_user.id, callback.data.removeprefix("ppe:view:"))
    if entry is None:
        await callback.answer(SAFE_ENTRY_TEXT)
        return
    await _show_entry(callback, callback.from_user.id, entry)


@router.callback_query(F.data.startswith("ppe:edit:"))
async def start_edit(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":", 3)
    if len(parts) != 4 or parts[2] not in {"points", "date", "note"}:
        await callback.answer(SAFE_ENTRY_TEXT)
        return
    field, entry_id = parts[2], parts[3]
    entry = _get_entry(callback.from_user.id, entry_id)
    if entry is None or entry.status != "active":
        await callback.answer(SAFE_ENTRY_TEXT)
        return
    await state.set_state(PersonalPlaceEntryEditState.value)
    await state.update_data(edit_entry_id=entry_id, edit_field=field)
    prompt = {
        "points": "Введите полученную комиссию:",
        "money": "Введите полученную сумму. Отправьте 0, чтобы очистить:",
        "currency": "Введите новый код валюты:",
        "date": "Введите дату в формате ДД.ММ.ГГГГ:",
        "note": "Введите заметку. Отправьте «-», чтобы очистить:",
    }[field]
    await callback.message.edit_text(
        prompt,
        reply_markup=_keyboard([[ ("⬅️ Назад", f"ppe:view:{entry_id}") ]]),
    )
    await callback.answer()


@router.message(StateFilter(PersonalPlaceEntryEditState.value))
async def receive_edit(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    entry = _get_entry(message.from_user.id, data.get("edit_entry_id"))
    field = data.get("edit_field")
    if entry is None or entry.status != "active" or field not in {"points", "money", "currency", "date", "note"}:
        await state.clear()
        await message.answer(SAFE_ENTRY_TEXT)
        return
    raw = message.text.strip() if isinstance(message.text, str) else ""
    values = {
        "occurred_at": datetime.fromisoformat(entry.occurred_at.replace("Z", "+00:00")),
        "received_income_minor": entry.received_income_minor,
        "received_points": entry.received_points,
        "currency": entry.currency,
        "note": entry.note,
    }
    if field == "points":
        values["received_points"] = None if raw == "0" else _parse_points(raw)
    elif field == "money":
        money = None if raw == "0" else _parse_money(raw)
        if raw != "0" and money is None:
            await message.answer(INVALID_VALUE_TEXT)
            return
        values["received_income_minor"] = money
        if money is None:
            values["currency"] = None
    elif field == "currency":
        currency = raw.upper()
        if entry.received_income_minor is None or currency not in ISO_4217_CODES:
            await message.answer(INVALID_VALUE_TEXT)
            return
        values["currency"] = currency
    elif field == "date":
        occurred = _parse_date(raw)
        if occurred is None or occurred.date() > datetime.now(LOCAL_TZ).date():
            await message.answer(INVALID_VALUE_TEXT)
            return
        values["occurred_at"] = occurred
    else:
        if len(raw) > 500:
            await message.answer(INVALID_VALUE_TEXT)
            return
        values["note"] = None if raw == "-" else raw or None
    if field == "points" and raw != "0" and values["received_points"] is None:
        await message.answer(INVALID_VALUE_TEXT)
        return
    if field == "money" and values["received_income_minor"] is not None:
        await state.set_state(PersonalPlaceEntryEditState.currency)
        await state.update_data(pending_values=values)
        await message.answer("Введите код валюты:")
        return
    await _save_edit(message, state, entry, values)


@router.message(StateFilter(PersonalPlaceEntryEditState.currency))
async def receive_edit_currency(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    entry = _get_entry(message.from_user.id, data.get("edit_entry_id"))
    currency = message.text.strip().upper() if isinstance(message.text, str) else ""
    if entry is None or currency not in ISO_4217_CODES:
        await message.answer(INVALID_VALUE_TEXT)
        return
    values = data.get("pending_values")
    if not isinstance(values, dict):
        await state.clear()
        await message.answer(SAFE_ENTRY_TEXT)
        return
    values["currency"] = currency
    await _save_edit(message, state, entry, values)


async def _save_edit(message: Message, state: FSMContext, entry: ExternalSale, values: dict):
    try:
        updated = _entries().update(
            user_id=message.from_user.id,
            public_id=entry.public_id,
            **values,
        )
    except ExternalSaleValidationError:
        updated = None
    if updated is None:
        await message.answer(INVALID_VALUE_TEXT)
        return
    await state.clear()
    await _show_entry(message, message.from_user.id, updated)


@router.callback_query(F.data.startswith("ppe:deactivate:"))
async def confirm_deactivate(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    entry_id = callback.data.removeprefix("ppe:deactivate:")
    entry = _get_entry(callback.from_user.id, entry_id)
    if entry is None or entry.status != "active":
        await callback.answer(SAFE_ENTRY_TEXT)
        return
    await callback.message.edit_text(
        "Деактивировать эту запись? История сохранится.",
        reply_markup=_keyboard([
            [("✅ Деактивировать", f"ppe:deactivate_confirm:{entry_id}")],
            [("⬅️ Назад", f"ppe:view:{entry_id}")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ppe:deactivate_confirm:"))
async def deactivate_entry(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    entry_id = callback.data.removeprefix("ppe:deactivate_confirm:")
    try:
        changed = _entries().deactivate(user_id=callback.from_user.id, public_id=entry_id)
    except ExternalSaleValidationError:
        changed = False
    if not changed:
        await callback.answer(SAFE_ENTRY_TEXT)
        return
    entry = _get_entry(callback.from_user.id, entry_id)
    if entry is None:
        await callback.answer(SAFE_ENTRY_TEXT)
        return
    await _show_entry(callback, callback.from_user.id, entry)
