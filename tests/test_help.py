import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import ADMIN_ID
from handlers.help import (
    ADMIN_COMMANDS_SECTION,
    PUBLIC_COMMANDS_MENU_TEXT,
    build_commands_menu_text,
    commands_menu_button,
    help_command,
)
from keyboards.main_menu import COMMANDS_MENU_LABEL


def run(awaitable):
    return asyncio.run(awaitable)


def _message(user_id=101, text=COMMANDS_MENU_LABEL):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        text=text,
        answer=AsyncMock(),
    )


def test_commands_menu_button_sends_public_command_list():
    msg = _message()

    run(commands_menu_button(msg))

    msg.answer.assert_awaited_once_with(
        PUBLIC_COMMANDS_MENU_TEXT,
        parse_mode="HTML",
    )


def test_commands_menu_button_includes_admin_commands_for_admin():
    if ADMIN_ID == 0:
        pytest.skip("ADMIN_ID is not configured")

    msg = _message(user_id=ADMIN_ID)

    run(commands_menu_button(msg))

    text = msg.answer.await_args.args[0]
    assert "/profile — открыть профиль" in text
    assert ADMIN_COMMANDS_SECTION in text
    assert "/cancel — отменить активную рассылку" in text
    assert msg.answer.await_args.kwargs["parse_mode"] == "HTML"


def test_build_commands_menu_text_omits_admin_commands_for_regular_user():
    if ADMIN_ID == 0:
        regular_user_id = 101
    else:
        regular_user_id = ADMIN_ID + 1

    text = build_commands_menu_text(regular_user_id)
    assert text == PUBLIC_COMMANDS_MENU_TEXT
    assert "/admin_report" not in text
    assert "/cancel" not in text


def test_help_command_still_sends_detailed_help():
    msg = _message()

    run(help_command(msg))

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "Guide OS — помощь" in text
    assert msg.answer.await_args.kwargs["parse_mode"] == "HTML"
