import asyncio
from datetime import datetime, timedelta, timezone
import logging
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

from database.queries import register_user
from handlers.personal_place_entries import (
    SAFE_ENTRY_TEXT,
    back_field,
    confirm_deactivate,
    confirm_entry,
    deactivate_entry,
    receive_date,
    receive_edit,
    receive_note,
    receive_points,
    skip_field,
    start_edit,
    start_entry,
    use_today,
    view_entry,
)
from handlers.personal_places import view_place
from services.external_sales_service import ExternalSalesService
from services.personal_places_service import PersonalPlacesService
from states.personal_places import PersonalPlaceEntryCreateState


USER_ID = 19401
OTHER_USER_ID = 19402
PLACE_ID = "place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
ENTRY_ID = "entry_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


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


def seed_entry(*, points=5, money=None, currency=None, note="Заметка"):
    seed_place()
    return ExternalSalesService(id_factory=lambda: ENTRY_ID).create(
        user_id=USER_ID,
        personal_place_id=PLACE_ID,
        occurred_at=datetime.now(timezone.utc) - timedelta(days=1),
        received_points=points,
        received_income_minor=money,
        currency=currency,
        note=note,
    )


def create_points_entry(state):
    run(start_entry(callback(f"ppe:add:{PLACE_ID}"), state))
    run(receive_points(message("7"), state))
    run(use_today(callback("ppe:form_today"), state))
    run(skip_field(callback("ppe:form_skip"), state))
    run(confirm_entry(callback("ppe:form_confirm"), state))


def test_create_entry_asks_for_commission_and_stores_received_points():
    seed_place()
    state = State()
    started = callback(f"ppe:add:{PLACE_ID}")
    run(start_entry(started, state))
    assert started.message.edit_text.await_args.args[0] == "Введите полученную комиссию:"
    run(receive_points(message("7"), state))
    assert state.current == PersonalPlaceEntryCreateState.occurred_date.state
    run(use_today(callback("ppe:form_today"), state))
    run(skip_field(callback("ppe:form_skip"), state))
    run(confirm_entry(callback("ppe:form_confirm"), state))
    entries = ExternalSalesService().list(user_id=USER_ID, personal_place_id=PLACE_ID)
    assert len(entries) == 1
    assert entries[0].received_points == 7
    assert entries[0].received_income_minor is None
    assert entries[0].currency is None


def test_entry_creation_never_prompts_for_currency_or_money():
    seed_place()
    state = State()
    prompts = []
    started = callback(f"ppe:add:{PLACE_ID}")
    run(start_entry(started, state))
    prompts.append(started.message.edit_text.await_args.args[0])
    commission = message("12")
    run(receive_points(commission, state))
    prompts.append(commission.answer.await_args.args[0])
    run(use_today(callback("ppe:form_today"), state))
    run(receive_note(message("Комиссия получена"), state))
    run(confirm_entry(callback("ppe:form_confirm"), state))
    entry = ExternalSalesService().list(user_id=USER_ID)[0]
    assert entry.received_points == 12
    assert entry.received_income_minor is None
    assert entry.currency is None
    combined = " ".join(prompts).lower()
    assert "валют" not in combined
    assert "сумм" not in combined


@pytest.mark.parametrize("invalid_value", ["0", "-1", "bad"])
def test_zero_negative_and_invalid_commission_are_rejected(invalid_value):
    seed_place()
    state = State()
    run(start_entry(callback(f"ppe:add:{PLACE_ID}"), state))
    invalid = message(invalid_value)
    run(receive_points(invalid, state))
    assert state.current == PersonalPlaceEntryCreateState.points.state
    assert invalid.answer.await_args.args[0] != ""
    assert ExternalSalesService().list(user_id=USER_ID) == []


def test_future_date_is_rejected():
    seed_place()
    state = State()
    run(start_entry(callback(f"ppe:add:{PLACE_ID}"), state))
    run(receive_points(message("2"), state))
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


def test_place_list_and_entry_detail_render_history_without_internal_ids():
    entry = seed_entry()
    ExternalSalesService(
        id_factory=lambda: "entry_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    ).create(
        user_id=USER_ID,
        personal_place_id=PLACE_ID,
        occurred_at=datetime.now(timezone.utc) - timedelta(days=1),
        received_points=30,
    )
    inactive = ExternalSalesService(
        id_factory=lambda: "entry_cccccccccccccccccccccccccccccccc"
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
    assert "комиссия 5" in place_text
    assert "комиссия 30" in place_text
    assert "Всего получено комиссии:</b> 35" in place_text
    assert "Всего получено комиссии:</b> 75" not in place_text
    assert "USD" not in place_text
    assert PLACE_ID not in place_text
    assert ENTRY_ID not in place_text
    assert str(USER_ID) not in place_text

    entry_cb = callback(f"ppe:view:{entry.public_id}")
    run(view_entry(entry_cb, State()))
    detail = entry_cb.message.edit_text.await_args.args[0]
    assert "Личное кафе" in detail
    assert "Полученная комиссия" in detail
    assert "USD" not in detail
    assert "Статус:</b> Активна" in detail
    assert PLACE_ID not in detail
    assert ENTRY_ID not in detail


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("points", "9", ("received_points", 9)),
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
        "received_income_minor": None,
        "currency": None,
        "occurred_at": datetime.now(timezone.utc),
        "note": "Сохранить",
    }
    run(back_field(callback("ppe:form_back"), state))
    assert state.current == PersonalPlaceEntryCreateState.occurred_date.state
    assert state.data["received_points"] == 4
    assert state.data["note"] == "Сохранить"


def test_entry_flow_uses_no_guide_shop_client_or_network(monkeypatch, caplog):
    seed_place()
    private_note = "Секретная заметка"
    unexpected = Mock(side_effect=AssertionError("network or provider used"))
    monkeypatch.setattr(socket, "create_connection", unexpected)
    monkeypatch.setattr("handlers.guide_shop._provider", unexpected)
    state = State()

    with caplog.at_level(logging.DEBUG):
        run(start_entry(callback(f"ppe:add:{PLACE_ID}"), state))
        run(receive_points(message("3"), state))
        run(use_today(callback("ppe:form_today"), state))
        run(receive_note(message(private_note), state))
        run(confirm_entry(callback("ppe:form_confirm"), state))

    unexpected.assert_not_called()
    for value in (private_note, PLACE_ID, str(USER_ID), f"ppe:add:{PLACE_ID}"):
        assert value not in caplog.text
