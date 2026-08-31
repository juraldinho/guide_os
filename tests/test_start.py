import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from database.queries import register_user
from handlers.start import cmd_start
from keyboards.main_menu import (
    MINI_APP_MENU_LABEL,
    configure_miniapp_menu,
    configure_guide_shop_menu,
)


def run(awaitable):
    return asyncio.run(awaitable)


def _message(user_id=101):
    sent = SimpleNamespace(edit_reply_markup=AsyncMock())
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncMock(return_value=sent),
    )


@pytest.fixture(autouse=True)
def reset_menu():
    configure_guide_shop_menu(None)
    configure_miniapp_menu(None)
    yield
    configure_guide_shop_menu(None)
    configure_miniapp_menu(None)


def _inline_web_app_labels(markup):
    if markup is None:
        return []
    return [button.text for row in markup.inline_keyboard for button in row]


def test_start_attaches_inline_mini_app_when_configured():
    configure_miniapp_menu("https://miniapp.example.com")
    msg = _message()

    run(cmd_start(msg))

    msg.answer.assert_awaited_once()
    assert msg.answer.await_args.kwargs["parse_mode"] == "HTML"
    reply_markup = msg.answer.await_args.kwargs["reply_markup"]
    assert reply_markup.keyboard is not None

    sent = msg.answer.return_value
    sent.edit_reply_markup.assert_awaited_once()
    inline = sent.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert _inline_web_app_labels(inline) == [MINI_APP_MENU_LABEL]
    assert inline.inline_keyboard[0][0].web_app.url == "https://miniapp.example.com"


def test_start_has_no_inline_mini_app_when_not_configured():
    msg = _message()

    run(cmd_start(msg))

    msg.answer.assert_awaited_once()
    sent = msg.answer.return_value
    sent.edit_reply_markup.assert_not_awaited()


def test_start_inline_mini_app_for_existing_user():
    user_id = 424242
    register_user(user_id)
    configure_miniapp_menu("https://miniapp.example.com")
    msg = _message(user_id=user_id)

    run(cmd_start(msg))

    sent = msg.answer.return_value
    sent.edit_reply_markup.assert_awaited_once()
    inline = sent.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert _inline_web_app_labels(inline) == [MINI_APP_MENU_LABEL]


def test_start_inline_mini_app_for_newly_registered_user():
    configure_miniapp_menu("https://miniapp.example.com")
    msg = _message(user_id=999888)

    run(cmd_start(msg))

    sent = msg.answer.return_value
    sent.edit_reply_markup.assert_awaited_once()
    inline = sent.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert _inline_web_app_labels(inline) == [MINI_APP_MENU_LABEL]
