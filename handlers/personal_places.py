from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database.queries import register_user
from services.personal_places_service import (
    PersonalPlace,
    PersonalPlaceConflictError,
    PersonalPlacesService,
    PersonalPlaceValidationError,
)
from states.personal_places import PersonalPlaceCreateState, PersonalPlaceEditState


router = Router()

SAFE_PLACE_TEXT = "Место не найдено или недоступно."
SAVE_FAILED_TEXT = "Не удалось сохранить место. Попробуйте ещё раз."
PRIVATE_EXPLANATION = "Это ваши личные места. Они видны только вам."

_FIELDS = ("name", "category", "general_location", "landmark", "note")
_FIELD_LABELS = {
    "name": "Название",
    "category": "Категория",
    "general_location": "Общее расположение",
    "landmark": "Ориентир",
    "note": "Заметка",
}
_FIELD_LIMITS = {
    "name": 100,
    "category": 100,
    "general_location": 200,
    "landmark": 200,
    "note": 500,
}
_CREATE_STATES = {
    "name": PersonalPlaceCreateState.name,
    "category": PersonalPlaceCreateState.category,
    "general_location": PersonalPlaceCreateState.general_location,
    "landmark": PersonalPlaceCreateState.landmark,
    "note": PersonalPlaceCreateState.note,
}


def _service() -> PersonalPlacesService:
    return PersonalPlacesService()


def _keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


def _list_keyboard(places: list[PersonalPlace], *, inactive: bool):
    rows = [[(place.name, f"pp:view:{place.public_id}")] for place in places]
    if not inactive:
        rows.append([("➕ Добавить место", "pp:create")])
        rows.append([("📁 Неактивные", "pp:inactive")])
    else:
        rows.append([("\u2b05\ufe0f Назад", "pp:list")])
    if not inactive:
        rows.append([("\u2b05\ufe0f Назад", "pp:shop")])
    return _keyboard(rows)


def _detail_text(place: PersonalPlace) -> str:
    lines = [
        "📍 <b>Личное место</b>",
        "🔒 Видно только вам",
        "",
        f"<b>Название:</b> {escape(place.name)}",
    ]
    for field in _FIELDS[1:]:
        value = getattr(place, field)
        if value:
            lines.append(f"<b>{_FIELD_LABELS[field]}:</b> {escape(value)}")
    if place.status == "inactive":
        lines.extend(("", "Место неактивно и доступно только для просмотра."))
    return "\n".join(lines)


def _detail_keyboard(place: PersonalPlace) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    if place.status == "active":
        rows.extend(
            [[(f"✏️ {_FIELD_LABELS[field]}", f"pp:edit:{field}:{place.public_id}")]
             for field in _FIELDS]
        )
        rows.append([("🗃 Деактивировать", f"pp:deactivate:{place.public_id}")])
    back = "pp:list" if place.status == "active" else "pp:inactive"
    rows.append([("⬅️ Назад", back)])
    return _keyboard(rows)


async def _show_list(callback: CallbackQuery, *, inactive: bool) -> None:
    places = _service().list(user_id=callback.from_user.id, include_inactive=inactive)
    if inactive:
        places = [place for place in places if place.status == "inactive"]
        heading = "📁 <b>Неактивные личные места</b>"
        body = "Неактивных мест пока нет." if not places else PRIVATE_EXPLANATION
    else:
        heading = "📍 <b>Мои места</b>"
        body = PRIVATE_EXPLANATION if not places else "Ваши активные личные места:"
    await callback.message.edit_text(
        f"{heading}\n\n{body}",
        parse_mode="HTML",
        reply_markup=_list_keyboard(places, inactive=inactive),
    )
    await callback.answer()


async def _get_place(callback: CallbackQuery, public_id: str) -> PersonalPlace | None:
    try:
        return _service().get(user_id=callback.from_user.id, public_id=public_id)
    except PersonalPlaceValidationError:
        return None


async def _show_detail(callback: CallbackQuery, place: PersonalPlace) -> None:
    await callback.message.edit_text(
        _detail_text(place),
        parse_mode="HTML",
        reply_markup=_detail_keyboard(place),
    )
    await callback.answer()


def _form_keyboard(*, optional: bool) -> InlineKeyboardMarkup:
    rows = []
    if optional:
        rows.append([("Пропустить", "pp:form_skip")])
    rows.append([("⬅️ Назад", "pp:form_back"), ("❌ Отмена", "pp:form_cancel")])
    return _keyboard(rows)


def _prompt(field: str) -> str:
    hints = {
        "name": "Введите название места (обязательно):",
        "category": "Введите категорию или пропустите:",
        "general_location": "Введите общее расположение или пропустите:",
        "landmark": "Введите ориентир или пропустите:",
        "note": "Введите заметку или пропустите:",
    }
    return hints[field]


async def _show_form_prompt(target: Message | CallbackQuery, state: FSMContext, field: str):
    await state.set_state(_CREATE_STATES[field])
    method = target.message.edit_text if isinstance(target, CallbackQuery) else target.answer
    await method(_prompt(field), reply_markup=_form_keyboard(optional=field != "name"))
    if isinstance(target, CallbackQuery):
        await target.answer()


def _confirmation_text(data: dict) -> str:
    lines = ["📍 <b>Проверьте личное место</b>", "", f"<b>Название:</b> {escape(data['name'])}"]
    for field in _FIELDS[1:]:
        value = data.get(field)
        if value:
            lines.append(f"<b>{_FIELD_LABELS[field]}:</b> {escape(value)}")
    return "\n".join(lines)


async def _show_confirmation(target: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PersonalPlaceCreateState.confirm)
    data = await state.get_data()
    markup = _keyboard([
        [("✅ Сохранить", "pp:form_confirm")],
        [("⬅️ Назад", "pp:form_back"), ("❌ Отмена", "pp:form_cancel")],
    ])
    method = target.message.edit_text if isinstance(target, CallbackQuery) else target.answer
    await method(_confirmation_text(data), parse_mode="HTML", reply_markup=markup)
    if isinstance(target, CallbackQuery):
        await target.answer()


@router.callback_query(F.data == "pp:list")
async def list_places(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _show_list(callback, inactive=False)


@router.callback_query(F.data == "pp:inactive")
async def list_inactive_places(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _show_list(callback, inactive=True)


@router.callback_query(F.data.startswith("pp:view:"))
async def view_place(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    place = await _get_place(callback, callback.data.removeprefix("pp:view:"))
    if place is None:
        await callback.answer(SAFE_PLACE_TEXT)
        return
    await _show_detail(callback, place)


@router.callback_query(F.data == "pp:create")
async def start_create_place(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(name=None, category=None, general_location=None, landmark=None, note=None)
    await _show_form_prompt(callback, state, "name")


@router.message(StateFilter(*_CREATE_STATES.values()))
async def receive_create_field(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    field = next((name for name, value in _CREATE_STATES.items() if value.state == current), None)
    if field is None:
        return
    value = message.text.strip() if isinstance(message.text, str) else ""
    maximum = _FIELD_LIMITS[field]
    if (field == "name" and not value) or len(value) > maximum:
        await message.answer(
            f"Проверьте значение: максимум {maximum} символов.",
            reply_markup=_form_keyboard(optional=field != "name"),
        )
        return
    await state.update_data(**{field: value or None})
    index = _FIELDS.index(field)
    if index + 1 == len(_FIELDS):
        await _show_confirmation(message, state)
    else:
        await _show_form_prompt(message, state, _FIELDS[index + 1])


@router.callback_query(F.data == "pp:form_skip")
async def skip_create_field(callback: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    field = next((name for name, value in _CREATE_STATES.items() if value.state == current), None)
    if field not in _FIELDS[1:]:
        await callback.answer(SAFE_PLACE_TEXT)
        return
    await state.update_data(**{field: None})
    index = _FIELDS.index(field)
    if index + 1 == len(_FIELDS):
        await _show_confirmation(callback, state)
    else:
        await _show_form_prompt(callback, state, _FIELDS[index + 1])


@router.callback_query(F.data == "pp:form_back")
async def back_create_field(callback: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    if current == PersonalPlaceCreateState.name.state:
        await state.clear()
        await _show_list(callback, inactive=False)
        return
    if current == PersonalPlaceCreateState.confirm.state:
        await _show_form_prompt(callback, state, "note")
        return
    field = next((name for name, value in _CREATE_STATES.items() if value.state == current), None)
    if field is None:
        await callback.answer(SAFE_PLACE_TEXT)
        return
    await _show_form_prompt(callback, state, _FIELDS[_FIELDS.index(field) - 1])


@router.callback_query(F.data == "pp:form_cancel")
async def cancel_create_place(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _show_list(callback, inactive=False)


@router.callback_query(
    StateFilter(PersonalPlaceCreateState.confirm),
    F.data == "pp:form_confirm",
)
async def confirm_create_place(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        register_user(callback.from_user.id)
        place = _service().create(user_id=callback.from_user.id, **data)
    except (PersonalPlaceValidationError, PersonalPlaceConflictError):
        await callback.answer(SAVE_FAILED_TEXT)
        return
    await state.clear()
    await _show_detail(callback, place)


@router.callback_query(F.data.startswith("pp:edit:"))
async def start_edit_place(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":", 3)
    if len(parts) != 4 or parts[2] not in _FIELDS:
        await callback.answer(SAFE_PLACE_TEXT)
        return
    field, public_id = parts[2], parts[3]
    place = await _get_place(callback, public_id)
    if place is None or place.status != "active":
        await callback.answer(SAFE_PLACE_TEXT)
        return
    await state.set_state(PersonalPlaceEditState.value)
    await state.update_data(edit_public_id=public_id, edit_field=field)
    optional = field != "name"
    suffix = " Отправьте «-», чтобы очистить." if optional else ""
    await callback.message.edit_text(
        f"Введите новое значение поля «{_FIELD_LABELS[field]}».{suffix}",
        reply_markup=_keyboard([[ ("⬅️ Назад", f"pp:view:{public_id}") ]]),
    )
    await callback.answer()


@router.message(StateFilter(PersonalPlaceEditState.value))
async def receive_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("edit_field")
    public_id = data.get("edit_public_id")
    if field not in _FIELDS or not isinstance(public_id, str):
        await state.clear()
        await message.answer(SAFE_PLACE_TEXT)
        return
    try:
        place = _service().get(user_id=message.from_user.id, public_id=public_id)
    except PersonalPlaceValidationError:
        place = None
    if place is None or place.status != "active":
        await state.clear()
        await message.answer(SAFE_PLACE_TEXT)
        return
    value = message.text.strip() if isinstance(message.text, str) else ""
    if field != "name" and value == "-":
        value = None
    if (field == "name" and not value) or (value is not None and len(value) > _FIELD_LIMITS[field]):
        await message.answer(f"Проверьте значение: максимум {_FIELD_LIMITS[field]} символов.")
        return
    values = {name: getattr(place, name) for name in _FIELDS}
    values[field] = value
    try:
        updated = _service().update(
            user_id=message.from_user.id,
            public_id=public_id,
            **values,
        )
    except PersonalPlaceValidationError:
        updated = None
    await state.clear()
    if updated is None:
        await message.answer(SAFE_PLACE_TEXT)
        return
    await message.answer(
        _detail_text(updated),
        parse_mode="HTML",
        reply_markup=_detail_keyboard(updated),
    )


@router.callback_query(F.data.startswith("pp:deactivate:"))
async def confirm_deactivate_place(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    public_id = callback.data.removeprefix("pp:deactivate:")
    place = await _get_place(callback, public_id)
    if place is None or place.status != "active":
        await callback.answer(SAFE_PLACE_TEXT)
        return
    await callback.message.edit_text(
        "Деактивировать это личное место? Оно останется доступно для просмотра.",
        reply_markup=_keyboard([
            [("✅ Деактивировать", f"pp:deactivate_confirm:{public_id}")],
            [("⬅️ Назад", f"pp:view:{public_id}")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pp:deactivate_confirm:"))
async def deactivate_place(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    public_id = callback.data.removeprefix("pp:deactivate_confirm:")
    try:
        changed = _service().deactivate(
            user_id=callback.from_user.id,
            public_id=public_id,
        )
    except PersonalPlaceValidationError:
        changed = False
    if not changed:
        await callback.answer(SAFE_PLACE_TEXT)
        return
    place = await _get_place(callback, public_id)
    if place is None:
        await callback.answer(SAFE_PLACE_TEXT)
        return
    await _show_detail(callback, place)
