import asyncio
from datetime import datetime, timedelta, timezone
import logging
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

from database.queries import register_user
from handlers import personal_place_entries as entries_mod
from handlers.personal_place_entries import (
    SAFE_ENTRY_TEXT,
    back_field,
    confirm_deactivate,
    confirm_entry,
    deactivate_entry,
    receive_commission,
    receive_date,
    receive_edit,
    receive_note,
    skip_field,
    start_edit,
    start_entry,
    use_today,
    view_entry,
)
from handlers.personal_places import view_place
from services.external_sales_service import ExternalSalesService
from services.personal_places_service import PersonalPlacesService
from states.personal_places import (
    PersonalPlaceEntryCreateState,
    PersonalPlaceEntryEditState,
)


USER_ID = 19401
OTHER_USER_ID = 19402
PLACE_ID = "place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
ENTRY_ID = "entry_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
LEGACY_ID = "entry_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


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


def seed_place(*, user_id=USER_ID, active=True):
    register_user(user_id)
    place = PersonalPlacesService(id_factory=lambda: PLACE_ID).create(
        user_id=user_id,
        name="Личное кафе",
    )
    if not active:
        PersonalPlacesService().deactivate(user_id=user_id, public_id=PLACE_ID)
        place = PersonalPlacesService().get(user_id=user_id, public_id=PLACE_ID)
    return place


def seed_entry(*, points=5, note="Заметка"):
    seed_place()
    return ExternalSalesService(id_factory=lambda: ENTRY_ID).create(
        user_id=USER_ID,
        personal_place_id=PLACE_ID,
        occurred_at=datetime.now(timezone.utc) - timedelta(days=1),
        received_points=points,
        purchase_amount_minor=None,
        received_income_minor=None,
        currency=None,
        note=note,
    )


def seed_legacy_money_entry():
    return ExternalSalesService(id_factory=lambda: LEGACY_ID).create(
        user_id=USER_ID,
        personal_place_id=PLACE_ID,
        occurred_at=datetime.now(timezone.utc) - timedelta(days=1),
        received_points=None,
        purchase_amount_minor=None,
        received_income_minor=1500,
        currency="USD",
        note="LEGACY_MONEY_NOTE",
    )


def test_create_follows_commission_date_note_confirmation():
    seed_place()
    state = State()
    started = callback(f"ppe:add:{PLACE_ID}")
    run(start_entry(started, state))
    assert started.message.edit_text.await_args.args[0] == "Введите комиссию:"
    assert state.current == PersonalPlaceEntryCreateState.commission.state

    run(receive_commission(message("7"), state))
    assert state.current == PersonalPlaceEntryCreateState.occurred_date.state

    run(use_today(callback("ppe:form_today"), state))
    assert state.current == PersonalPlaceEntryCreateState.note.state

    confirm_msg = message("Комиссия получена")
    run(receive_note(confirm_msg, state))
    assert state.current == PersonalPlaceEntryCreateState.confirm.state
    confirmation = confirm_msg.answer.await_args.args[0]
    assert "Комиссия: 7" in confirmation
    assert "Дата:" in confirmation
    assert "Комиссия получена" in confirmation
    assert "Балл" not in confirmation
    assert "валют" not in confirmation.lower()
    assert "сумм" not in confirmation.lower()
    assert "денежн" not in confirmation.lower()

    run(confirm_entry(callback("ppe:form_confirm"), state))
    entries = ExternalSalesService().list(user_id=USER_ID, personal_place_id=PLACE_ID)
    assert len(entries) == 1
    assert entries[0].received_points == 7
    assert entries[0].purchase_amount_minor is None
    assert entries[0].received_income_minor is None
    assert entries[0].currency is None
    assert entries[0].note == "Комиссия получена"


def test_entry_creation_never_prompts_for_currency_or_money():
    seed_place()
    state = State()
    prompts = []
    started = callback(f"ppe:add:{PLACE_ID}")
    run(start_entry(started, state))
    prompts.append(started.message.edit_text.await_args.args[0])
    commission = message("12")
    run(receive_commission(commission, state))
    prompts.append(commission.answer.await_args.args[0])
    today = callback("ppe:form_today")
    run(use_today(today, state))
    prompts.append(today.message.edit_text.await_args.args[0])
    combined = " ".join(prompts).lower()
    assert "валют" not in combined
    assert "сумм" not in combined
    assert "балл" not in combined
    assert "денежн" not in combined


@pytest.mark.parametrize(
    "invalid_value",
    ["0", "-1", "1.5", "10,5", "1e3", "+7", "abc", "  ", "7.0"],
)
def test_invalid_commission_values_are_rejected(invalid_value):
    seed_place()
    state = State()
    run(start_entry(callback(f"ppe:add:{PLACE_ID}"), state))
    invalid = message(invalid_value)
    run(receive_commission(invalid, state))
    assert state.current == PersonalPlaceEntryCreateState.commission.state
    assert invalid.answer.await_args.args[0] != ""
    assert ExternalSalesService().list(user_id=USER_ID) == []


def test_whitespace_trimmed_positive_integer_is_accepted():
    seed_place()
    state = State()
    run(start_entry(callback(f"ppe:add:{PLACE_ID}"), state))
    run(receive_commission(message("  15  "), state))
    assert state.current == PersonalPlaceEntryCreateState.occurred_date.state
    assert state.data["received_points"] == 15


def test_future_date_is_rejected():
    seed_place()
    state = State()
    run(start_entry(callback(f"ppe:add:{PLACE_ID}"), state))
    run(receive_commission(message("2"), state))
    future = (datetime.now() + timedelta(days=2)).strftime("%d.%m.%Y")
    invalid = message(future)
    run(receive_date(invalid, state))
    assert state.current == PersonalPlaceEntryCreateState.occurred_date.state
    assert ExternalSalesService().list(user_id=USER_ID) == []


def test_inactive_place_cannot_receive_entry():
    seed_place(active=False)
    cb = callback(f"ppe:add:{PLACE_ID}")
    run(start_entry(cb, State()))
    cb.answer.assert_awaited_once_with(SAFE_ENTRY_TEXT)
    assert ExternalSalesService().list(user_id=USER_ID) == []


def test_place_list_and_entry_detail_use_commission_not_points():
    entry = seed_entry()
    ExternalSalesService(
        id_factory=lambda: "entry_cccccccccccccccccccccccccccccccc"
    ).create(
        user_id=USER_ID,
        personal_place_id=PLACE_ID,
        occurred_at=datetime.now(timezone.utc) - timedelta(days=1),
        received_points=30,
    )
    inactive = ExternalSalesService(
        id_factory=lambda: "entry_dddddddddddddddddddddddddddddddd"
    ).create(
        user_id=USER_ID,
        personal_place_id=PLACE_ID,
        occurred_at=datetime.now(timezone.utc) - timedelta(days=1),
        received_points=40,
    )
    ExternalSalesService().deactivate(user_id=USER_ID, public_id=inactive.public_id)
    place_cb = callback(f"pp:view:{PLACE_ID}")
    run(view_place(place_cb, State()))
    place_text = place_cb.message.edit_text.await_args.args[0]
    assert "Последние записи" in place_text
    assert "Комиссия: 5" in place_text
    assert "Комиссия: 30" in place_text
    assert "Всего получено комиссии:</b> 35" in place_text
    assert "Всего получено комиссии:</b> 75" not in place_text
    assert "Балл" not in place_text
    assert "USD" not in place_text
    assert "денежн" not in place_text.lower()
    assert PLACE_ID not in place_text
    assert ENTRY_ID not in place_text
    assert str(USER_ID) not in place_text

    entry_cb = callback(f"ppe:view:{entry.public_id}")
    run(view_entry(entry_cb, State()))
    detail = entry_cb.message.edit_text.await_args.args[0]
    assert "Личное кафе" in detail
    assert "<b>Комиссия:</b> 5" in detail
    assert "Балл" not in detail
    assert "USD" not in detail
    assert "денежн" not in detail.lower()
    assert "Статус:</b> Активна" in detail
    keyboard = entry_cb.message.edit_text.await_args.kwargs["reply_markup"]
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert labels == [
        "✏️ Редактировать комиссию",
        "✏️ Редактировать дату",
        "✏️ Редактировать заметку",
        "🚫 Деактивировать",
        "⬅️ Назад к месту",
    ]


def test_legacy_money_is_hidden_and_excluded_from_summary():
    seed_entry(points=5)
    seed_legacy_money_entry()
    place_cb = callback(f"pp:view:{PLACE_ID}")
    run(view_place(place_cb, State()))
    place_text = place_cb.message.edit_text.await_args.args[0]
    assert "Всего получено комиссии:</b> 5" in place_text
    assert "LEGACY_MONEY_NOTE" not in place_text
    assert "USD" not in place_text
    assert "15.00" not in place_text
    assert "денежн" not in place_text.lower()
    keyboard = place_cb.message.edit_text.await_args.kwargs["reply_markup"]
    callback_data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert f"ppe:view:{LEGACY_ID}" not in callback_data

    legacy_cb = callback(f"ppe:view:{LEGACY_ID}")
    run(view_entry(legacy_cb, State()))
    detail = legacy_cb.message.edit_text.await_args.args[0]
    assert "USD" not in detail
    assert "15.00" not in detail
    assert "денежн" not in detail.lower()
    assert "Балл" not in detail
    assert "<b>Комиссия:</b>" not in detail


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("commission", "9", ("received_points", 9)),
        ("date", "01.08.2026", ("date", "2026-08-01")),
        ("note", "Новая заметка", ("note", "Новая заметка")),
    ],
)
def test_edit_entry_fields(field, value, expected):
    seed_entry()
    state = State()
    run(start_edit(callback(f"ppe:edit:{field}:{ENTRY_ID}"), state))
    run(receive_edit(message(value), state))
    entry = ExternalSalesService().get(user_id=USER_ID, public_id=ENTRY_ID)
    attribute, expected_value = expected
    actual = (
        datetime.fromisoformat(entry.occurred_at.replace("Z", "+00:00"))
        .astimezone(ZoneInfo("Asia/Tashkent"))
        .date()
        .isoformat()
        if attribute == "date"
        else getattr(entry, attribute)
    )
    assert actual == expected_value
    assert entry.purchase_amount_minor is None
    assert entry.received_income_minor is None
    assert entry.currency is None


def test_edit_clears_legacy_monetary_fields():
    seed_place()
    ExternalSalesService(id_factory=lambda: ENTRY_ID).create(
        user_id=USER_ID,
        personal_place_id=PLACE_ID,
        occurred_at=datetime.now(timezone.utc) - timedelta(days=1),
        received_points=5,
        received_income_minor=1500,
        currency="USD",
        note="keep",
    )
    state = State()
    run(start_edit(callback(f"ppe:edit:commission:{ENTRY_ID}"), state))
    run(receive_edit(message("11"), state))
    entry = ExternalSalesService().get(user_id=USER_ID, public_id=ENTRY_ID)
    assert entry.received_points == 11
    assert entry.purchase_amount_minor is None
    assert entry.received_income_minor is None
    assert entry.currency is None
    assert entry.note == "keep"


def test_invalid_edit_keeps_draft_and_state():
    seed_entry()
    state = State()
    run(start_edit(callback(f"ppe:edit:commission:{ENTRY_ID}"), state))
    invalid = message("1.5")
    run(receive_edit(invalid, state))
    assert state.current == PersonalPlaceEntryEditState.value.state
    assert state.data["edit_field"] == "commission"
    entry = ExternalSalesService().get(user_id=USER_ID, public_id=ENTRY_ID)
    assert entry.received_points == 5
    assert invalid.answer.await_args.args[0] != ""


def test_legacy_record_cannot_start_edit():
    seed_place()
    seed_legacy_money_entry()
    cb = callback(f"ppe:edit:commission:{LEGACY_ID}")
    run(start_edit(cb, State()))
    cb.answer.assert_awaited_once_with(SAFE_ENTRY_TEXT)


def test_deactivate_entry_preserves_readable_history():
    seed_entry()
    state = State()
    requested = callback(f"ppe:deactivate:{ENTRY_ID}")
    run(confirm_deactivate(requested, state))
    assert ExternalSalesService().get(user_id=USER_ID, public_id=ENTRY_ID).status == "active"

    confirmed = callback(f"ppe:deactivate_confirm:{ENTRY_ID}")
    run(deactivate_entry(confirmed, state))
    entry = ExternalSalesService().get(user_id=USER_ID, public_id=ENTRY_ID)
    assert entry.status == "inactive"
    assert "Статус:</b> Неактивна" in confirmed.message.edit_text.await_args.args[0]
    assert ExternalSalesService().list(
        user_id=USER_ID,
        personal_place_id=PLACE_ID,
        include_inactive=True,
    ) == [entry]


@pytest.mark.parametrize(
    "raw_callback",
    [f"ppe:view:{ENTRY_ID}", "ppe:view:entry_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"],
)
def test_cross_user_and_missing_entry_access_fail_calmly(raw_callback):
    seed_entry()
    cb = callback(raw_callback, OTHER_USER_ID)
    run(view_entry(cb, State()))
    cb.answer.assert_awaited_once_with(SAFE_ENTRY_TEXT)
    cb.message.edit_text.assert_not_awaited()


def test_cross_user_place_access_cannot_start_entry():
    seed_place()
    cb = callback(f"ppe:add:{PLACE_ID}", OTHER_USER_ID)
    run(start_entry(cb, State()))
    cb.answer.assert_awaited_once_with(SAFE_ENTRY_TEXT)


def test_back_navigation_preserves_form_data_one_step():
    seed_place()
    state = State()
    state.current = PersonalPlaceEntryCreateState.note.state
    state.data = {
        "personal_place_id": PLACE_ID,
        "received_points": 4,
        "occurred_at": datetime.now(timezone.utc),
        "note": "Сохранить",
    }
    run(back_field(callback("ppe:form_back"), state))
    assert state.current == PersonalPlaceEntryCreateState.occurred_date.state
    assert state.data["received_points"] == 4
    assert state.data["note"] == "Сохранить"


def test_cancel_returns_without_saving():
    seed_place()
    state = State()
    run(start_entry(callback(f"ppe:add:{PLACE_ID}"), state))
    run(receive_commission(message("8"), state))
    cancel = callback("ppe:form_cancel")
    run(entries_mod.cancel_entry(cancel, state))
    assert state.current is None
    assert ExternalSalesService().list(user_id=USER_ID) == []


def test_obsolete_money_currency_paths_are_gone():
    assert not hasattr(entries_mod, "receive_money")
    assert not hasattr(entries_mod, "receive_currency")
    assert not hasattr(entries_mod, "receive_edit_currency")
    assert not hasattr(entries_mod, "_after_money")
    assert not hasattr(entries_mod, "_parse_money")
    assert not hasattr(entries_mod, "receive_points")
    assert not hasattr(PersonalPlaceEntryCreateState, "money")
    assert not hasattr(PersonalPlaceEntryCreateState, "currency")
    assert not hasattr(PersonalPlaceEntryCreateState, "points")
    assert not hasattr(PersonalPlaceEntryEditState, "currency")


def test_entry_flow_uses_no_guide_shop_client_or_network(monkeypatch, caplog):
    seed_place()
    private_note = "Секретная заметка"
    unexpected = Mock(side_effect=AssertionError("network or provider used"))
    monkeypatch.setattr(socket, "create_connection", unexpected)
    monkeypatch.setattr("handlers.guide_shop._provider", unexpected)
    state = State()

    with caplog.at_level(logging.DEBUG):
        run(start_entry(callback(f"ppe:add:{PLACE_ID}"), state))
        run(receive_commission(message("3"), state))
        run(use_today(callback("ppe:form_today"), state))
        run(receive_note(message(private_note), state))
        run(confirm_entry(callback("ppe:form_confirm"), state))

    unexpected.assert_not_called()
    for value in (private_note, PLACE_ID, str(USER_ID), f"ppe:add:{PLACE_ID}"):
        assert value not in caplog.text
