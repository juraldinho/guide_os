import asyncio
import logging
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import handlers.personal_places as handler_module
from handlers.guide_shop import open_guide_shop_local_home
from database.queries import register_user
from handlers.personal_places import (
    SAFE_PLACE_TEXT,
    back_create_field,
    confirm_create_place,
    confirm_deactivate_place,
    deactivate_place,
    list_inactive_places,
    list_places,
    receive_create_field,
    receive_edit_value,
    skip_create_field,
    start_create_place,
    start_edit_place,
    view_place,
)
from services.personal_places_service import PersonalPlacesService
from states.personal_places import PersonalPlaceCreateState, PersonalPlaceEditState


USER_ID = 19301
OTHER_USER_ID = 19302
PLACE_ID = "place_dddddddddddddddddddddddddddddddd"


def run(awaitable):
    return asyncio.run(awaitable)


class State:
    def __init__(self):
        self.current = None
        self.data = {}

    async def clear(self):
        self.current = None
        self.data = {}

    async def set_state(self, value):
        self.current = value.state if hasattr(value, "state") else value

    async def get_state(self):
        return self.current

    async def update_data(self, **values):
        self.data.update(values)

    async def get_data(self):
        return dict(self.data)


def callback(data: str, user_id: int = USER_ID):
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(edit_text=AsyncMock()),
        answer=AsyncMock(),
    )


def message(text: str, user_id: int = USER_ID):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncMock(),
    )


def seed_place(*, user_id: int = USER_ID, public_id: str = PLACE_ID, **values):
    register_user(user_id)
    return PersonalPlacesService(id_factory=lambda: public_id).create(
        user_id=user_id,
        name=values.pop("name", "Тихое место"),
        **values,
    )


def button_pairs(markup):
    return [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]


def test_empty_and_populated_active_lists_are_private_and_local():
    state = State()
    empty = callback("pp:list")
    run(list_places(empty, state))
    empty_text = empty.message.edit_text.await_args.args[0]
    assert "видны только вам" in empty_text
    assert "➕ Добавить место" in [
        text for text, _ in button_pairs(empty.message.edit_text.await_args.kwargs["reply_markup"])
    ]

    seed_place()
    populated = callback("pp:list")
    run(list_places(populated, state))
    call = populated.message.edit_text.await_args
    assert "Ваши активные личные места" in call.args[0]
    assert ("Тихое место", f"pp:view:{PLACE_ID}") in button_pairs(
        call.kwargs["reply_markup"]
    )


def test_create_with_name_only_requires_confirmation():
    state = State()
    cb = callback("pp:create")
    run(start_create_place(cb, state))
    run(receive_create_field(message("Мини-кафе"), state))
    for _ in range(4):
        run(skip_create_field(callback("pp:form_skip"), state))

    assert PersonalPlacesService().list(user_id=USER_ID) == []
    assert state.current == PersonalPlaceCreateState.confirm.state

    confirmed = callback("pp:form_confirm")
    run(confirm_create_place(confirmed, state))
    places = PersonalPlacesService().list(user_id=USER_ID)
    assert len(places) == 1
    assert places[0].name == "Мини-кафе"
    assert all(getattr(places[0], field) is None for field in (
        "category", "general_location", "landmark", "note"
    ))


def test_create_with_every_optional_field_and_escaped_detail():
    state = State()
    run(start_create_place(callback("pp:create"), state))
    values = ("Место <1>", "Кафе", "Центр", "У старых ворот", "Только утром")
    for value in values:
        run(receive_create_field(message(value), state))
    run(confirm_create_place(callback("pp:form_confirm"), state))

    place = PersonalPlacesService().list(user_id=USER_ID)[0]
    assert (place.name, place.category, place.general_location, place.landmark, place.note) == values
    rendered = callback(f"pp:view:{place.public_id}")
    run(view_place(rendered, State()))
    text = rendered.message.edit_text.await_args.args[0]
    assert "Место &lt;1&gt;" in text
    assert "Личное место" in text
    assert "Видно только вам" in text
    assert place.public_id not in text
    assert str(USER_ID) not in text


@pytest.mark.parametrize(
    ("field", "maximum"),
    [("name", 100), ("category", 100), ("general_location", 200), ("landmark", 200), ("note", 500)],
)
def test_create_validation_and_length_boundaries(field, maximum):
    state = State()
    state.current = getattr(PersonalPlaceCreateState, field).state
    state.data = {name: None for name in ("name", "category", "general_location", "landmark", "note")}
    state.data["name"] = "Имя"
    invalid = message("x" * (maximum + 1))
    run(receive_create_field(invalid, state))
    assert state.current == getattr(PersonalPlaceCreateState, field).state
    assert "максимум" in invalid.answer.await_args.args[0]

    valid = message("x" * maximum)
    run(receive_create_field(valid, state))
    assert state.data[field] == "x" * maximum


def test_required_name_rejects_blank():
    state = State()
    state.current = PersonalPlaceCreateState.name.state
    state.data = {name: None for name in ("name", "category", "general_location", "landmark", "note")}
    msg = message("   ")
    run(receive_create_field(msg, state))
    assert state.current == PersonalPlaceCreateState.name.state
    assert PersonalPlacesService().list(user_id=USER_ID) == []


def test_form_back_moves_one_step_and_preserves_data():
    state = State()
    state.current = PersonalPlaceCreateState.general_location.state
    state.data = {"name": "Сохранённое имя", "category": "Категория"}
    run(back_create_field(callback("pp:form_back"), state))
    assert state.current == PersonalPlaceCreateState.category.state
    assert state.data == {"name": "Сохранённое имя", "category": "Категория"}

    state.current = PersonalPlaceCreateState.confirm.state
    run(back_create_field(callback("pp:form_back"), state))
    assert state.current == PersonalPlaceCreateState.note.state
    assert state.data["name"] == "Сохранённое имя"


@pytest.mark.parametrize(
    ("field", "old_value", "new_value"),
    [
        ("name", "Старое", "Новое"),
        ("category", "Старая категория", "Новая категория"),
        ("general_location", "Старый район", "Новый район"),
        ("landmark", "Старый ориентир", "Новый ориентир"),
        ("note", "Старая заметка", "Новая заметка"),
    ],
)
def test_edit_each_field(field, old_value, new_value):
    values = {field: old_value}
    if field != "name":
        values["name"] = "Место"
    seed_place(**values)
    state = State()
    run(start_edit_place(callback(f"pp:edit:{field}:{PLACE_ID}"), state))
    assert state.current == PersonalPlaceEditState.value.state
    run(receive_edit_value(message(new_value), state))
    updated = PersonalPlacesService().get(user_id=USER_ID, public_id=PLACE_ID)
    assert getattr(updated, field) == new_value


def test_deactivate_confirmation_and_inactive_read_only():
    seed_place()
    state = State()
    requested = callback(f"pp:deactivate:{PLACE_ID}")
    run(confirm_deactivate_place(requested, state))
    assert PersonalPlacesService().get(user_id=USER_ID, public_id=PLACE_ID).status == "active"
    assert "Деактивировать" in requested.message.edit_text.await_args.args[0]

    confirmed = callback(f"pp:deactivate_confirm:{PLACE_ID}")
    run(deactivate_place(confirmed, state))
    place = PersonalPlacesService().get(user_id=USER_ID, public_id=PLACE_ID)
    assert place.status == "inactive"
    assert "только для просмотра" in confirmed.message.edit_text.await_args.args[0]
    buttons = button_pairs(confirmed.message.edit_text.await_args.kwargs["reply_markup"])
    assert all("pp:edit:" not in data for _, data in buttons)

    edit = callback(f"pp:edit:name:{PLACE_ID}")
    run(start_edit_place(edit, state))
    edit.answer.assert_awaited_once_with(SAFE_PLACE_TEXT)

    inactive = callback("pp:inactive")
    run(list_inactive_places(inactive, state))
    assert ("Тихое место", f"pp:view:{PLACE_ID}") in button_pairs(
        inactive.message.edit_text.await_args.kwargs["reply_markup"]
    )


@pytest.mark.parametrize("requested_id", [PLACE_ID, "place_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"])
def test_cross_user_and_unknown_place_are_denied(requested_id):
    seed_place()
    cb = callback(f"pp:view:{requested_id}", OTHER_USER_ID)
    run(view_place(cb, State()))
    cb.answer.assert_awaited_once_with(SAFE_PLACE_TEXT)
    cb.message.edit_text.assert_not_awaited()


def test_personal_places_flow_has_no_guide_shop_or_network_dependency(monkeypatch):
    seed_place()
    unexpected = Mock(side_effect=AssertionError("network attempted"))
    monkeypatch.setattr(socket, "create_connection", unexpected)
    monkeypatch.setattr("handlers.guide_shop._provider", unexpected)

    cb = callback("pp:list")
    run(list_places(cb, State()))
    run(view_place(callback(f"pp:view:{PLACE_ID}"), State()))
    unexpected.assert_not_called()


def test_places_back_uses_local_home_without_provider_network_or_navigation_token(
    monkeypatch,
):
    unexpected = Mock(side_effect=AssertionError("provider or network attempted"))
    monkeypatch.setattr("handlers.guide_shop._provider", None)
    monkeypatch.setattr(socket, "create_connection", unexpected)

    listed = callback("pp:list")
    run(list_places(listed, State()))
    buttons = button_pairs(listed.message.edit_text.await_args.kwargs["reply_markup"])
    assert ("\u2b05\ufe0f Назад", "pp:shop") in buttons
    assert all(not data.startswith("gs_") for _, data in buttons)

    back = callback("pp:shop")
    run(open_guide_shop_local_home(back))
    call = back.message.edit_text.await_args
    assert "Личные места доступны" in call.args[0]
    assert [
        button.callback_data
        for row in call.kwargs["reply_markup"].inline_keyboard
        for button in row
    ] == ["pp:list"]
    unexpected.assert_not_called()


def test_personal_values_and_callback_payloads_are_not_logged(caplog):
    private_values = ("Скрытое место", "Скрытый район", "Скрытая заметка")
    seed_place(name=private_values[0], general_location=private_values[1], note=private_values[2])
    raw_callback = f"pp:view:{PLACE_ID}"
    with caplog.at_level(logging.DEBUG):
        run(view_place(callback(raw_callback), State()))
    for value in (*private_values, raw_callback, PLACE_ID, str(USER_ID)):
        assert value not in caplog.text
