import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from handlers.help import COMMANDS_MENU_TEXT, commands_menu_button, help_command
from keyboards.main_menu import COMMANDS_MENU_LABEL


def run(awaitable):
    return asyncio.run(awaitable)


def _message(text=COMMANDS_MENU_LABEL):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=101),
        text=text,
        answer=AsyncMock(),
    )


def test_commands_menu_button_sends_concise_command_list():
    msg = _message()

    run(commands_menu_button(msg))

    msg.answer.assert_awaited_once_with(COMMANDS_MENU_TEXT)


def test_help_command_still_sends_detailed_help():
    msg = _message()

    run(help_command(msg))

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "Guide OS — помощь" in text
    assert msg.answer.await_args.kwargs["parse_mode"] == "HTML"
