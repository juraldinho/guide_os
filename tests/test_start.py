import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database.queries import register_user
from handlers.start import cmd_start
from keyboards.main_menu import configure_guide_shop_menu


def run(awaitable):
    return asyncio.run(awaitable)


def _message(user_id=101):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncMock(),
        edit_reply_markup=AsyncMock(),
    )


@pytest.fixture(autouse=True)
def reset_menu():
    configure_guide_shop_menu(None)
    yield
    configure_guide_shop_menu(None)


def test_start_sends_single_welcome_with_reply_keyboard():
    msg = _message()

    run(cmd_start(msg))

    msg.answer.assert_awaited_once()
    call = msg.answer.await_args
    assert call.kwargs["parse_mode"] == "HTML"
    assert "Добро пожаловать" in call.args[0]
    assert call.kwargs["reply_markup"].keyboard is not None
    assert not any(
        button.web_app is not None
        for row in call.kwargs["reply_markup"].keyboard
        for button in row
    )
    msg.edit_reply_markup.assert_not_awaited()


def test_start_single_message_for_existing_user():
    user_id = 424242
    register_user(user_id)
    msg = _message(user_id=user_id)

    run(cmd_start(msg))

    msg.answer.assert_awaited_once()
    msg.edit_reply_markup.assert_not_awaited()


def test_start_single_message_for_newly_registered_user():
    msg = _message(user_id=999888)

    run(cmd_start(msg))

    msg.answer.assert_awaited_once()
    msg.edit_reply_markup.assert_not_awaited()
