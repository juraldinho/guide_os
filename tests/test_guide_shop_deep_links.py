import asyncio
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiogram import Bot
from aiogram.filters import CommandObject
from aiogram.types import Chat, Message, User
import pytest

import bot as bot_module
import handlers.guide_shop as handler_module
from database.db import get_connection
from handlers.guide_shop import (
    DISABLED_TEXT,
    INVALID_ROUTE_TEXT,
    LINK_ACCESS_DENIED_TEXT,
    STALE_LINK_TEXT,
    configure_guide_shop_ui,
    open_guide_shop_deep_link,
    router,
)
from services.guide_shop_navigation import (
    GuideShopRoute,
    NavigationDeepLinkInvalidError,
    NavigationRouteInvalidError,
    NavigationTokenAccessDeniedError,
    NavigationTokenConsumedError,
    NavigationTokenExpiredError,
    NavigationTokenRevokedError,
    NavigationTokenUnknownError,
    build_navigation_deep_link,
    create_navigation_token,
    resolve_navigation_token,
)
from services.guide_shop_ui import GuideShopAction, GuideShopScreen


FIXED_TOKEN = "gs_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"


def run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture(autouse=True)
def reset_runtime():
    configure_guide_shop_ui(None, reads_enabled=False)
    yield
    configure_guide_shop_ui(None, reads_enabled=False)


def direct_message(user_id=101):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncMock(),
    )


def command(raw_token=FIXED_TOKEN):
    return CommandObject(command="start", args=raw_token)


def stored_status(raw_token):
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM guide_shop_navigation_tokens WHERE token_hash = ?",
        (token_hash,),
    ).fetchone()
    conn.close()
    return row["status"]


@pytest.mark.parametrize("username", ["GuideOSBot", "@GuideOSBot", "guideosBOT"])
def test_builder_normalizes_valid_usernames_and_returns_exact_url(username):
    assert build_navigation_deep_link(username, FIXED_TOKEN) == (
        f"https://t.me/{username.lstrip('@')}?start={FIXED_TOKEN}"
    )


@pytest.mark.parametrize(
    "username",
    [
        None,
        123,
        "bot",
        "a" * 30 + "bot",
        "Guide OS Bot",
        "ГайдБот",
        "Guide/OSBot",
        "GuideOSBot?x=1",
        "GuideOSBot#fragment",
        "@@GuideOSBot",
        "GuideOS",
    ],
)
def test_builder_rejects_invalid_usernames(username):
    with pytest.raises(NavigationDeepLinkInvalidError):
        build_navigation_deep_link(username, FIXED_TOKEN)


@pytest.mark.parametrize(
    "raw_token",
    [
        None,
        123,
        "gs_short",
        "gs_" + "A" * 31,
        "gs_" + "A" * 33,
        "gs_" + "A" * 31 + "!",
        "gs_" + "A" * 31 + " ",
        "gs_" + "A" * 31 + "/",
        "gs_" + "A" * 31 + "?",
        "other_" + "A" * 32,
    ],
)
def test_builder_enforces_exact_token_format(raw_token):
    with pytest.raises(NavigationDeepLinkInvalidError):
        build_navigation_deep_link("GuideOSBot", raw_token)


def test_builder_has_no_external_operations_and_url_contains_only_opaque_data(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("external operation attempted")

    monkeypatch.setattr(socket, "socket", unexpected)
    monkeypatch.setattr(sqlite3, "connect", unexpected)
    url = build_navigation_deep_link("@GuideOSBot", FIXED_TOKEN)
    assert url == f"https://t.me/GuideOSBot?start={FIXED_TOKEN}"
    for private_value in ("visit_detail", "object-1", "123456", "Personal Name"):
        assert private_value not in url


def aiogram_message(text):
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=101, type="private"),
        from_user=User(id=101, is_bot=False, first_name="Test"),
        text=text,
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"/start {FIXED_TOKEN}", True),
        ("/start", False),
        ("/start ", False),
        ("/start other_payload", False),
        ("/start gs_short", False),
        ("/start gs_" + "A" * 31, False),
        ("/start gs_" + "A" * 33, False),
        (f"/start {FIXED_TOKEN}\n", False),
    ],
)
def test_deep_link_handler_claims_only_exact_navigation_payload(text, expected):
    handler = router.message.handlers[0]
    bot = Bot(token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    matched, _ = run(handler.check(aiogram_message(text), bot=bot))
    assert matched is expected
    run(bot.session.close())


def test_generic_start_router_remains_after_guide_shop_router():
    source = Path(bot_module.__file__).read_text(encoding="utf-8")
    assert source.index("dp.include_router(guide_shop_router)") < source.index(
        "dp.include_router(start_router)"
    )
    assert source.index("dp.include_router(guide_shop_router)") < source.index(
        "dp.include_router(errors.router)"
    )


class RecordingService:
    def __init__(self, screen=None):
        self.calls = []
        self.screen = screen or GuideShopScreen("Screen", ())

    async def visits(self, cursor=None):
        self.calls.append(("visits", cursor))
        return self.screen


def test_disabled_deep_link_does_not_resolve_or_consume(monkeypatch):
    token = create_navigation_token(101, GuideShopRoute(kind="visits"))
    resolver = Mock(side_effect=AssertionError("resolved"))
    monkeypatch.setattr(handler_module, "resolve_navigation_token", resolver)
    msg = direct_message(101)
    run(open_guide_shop_deep_link(msg, command(token.raw_token)))
    msg.answer.assert_awaited_once_with(DISABLED_TEXT)
    resolver.assert_not_called()
    assert stored_status(token.raw_token) == "issued"


def test_correct_user_opens_typed_route_and_new_tokens_use_message_user():
    user_id = 303030
    token = create_navigation_token(
        user_id, GuideShopRoute(kind="visits", cursor="opaque-cursor")
    )
    screen = GuideShopScreen(
        "Visits",
        (GuideShopAction("Home", GuideShopRoute(kind="home")),),
    )
    service = RecordingService(screen)
    configure_guide_shop_ui(service, reads_enabled=True)
    msg = direct_message(user_id)
    run(open_guide_shop_deep_link(msg, command(token.raw_token)))

    assert service.calls == [("visits", "opaque-cursor")]
    msg.answer.assert_awaited_once()
    fresh_token = msg.answer.await_args.kwargs[
        "reply_markup"
    ].inline_keyboard[0][0].callback_data
    with pytest.raises(NavigationTokenAccessDeniedError):
        resolve_navigation_token(fresh_token, user_id + 1)
    assert resolve_navigation_token(fresh_token, user_id).kind == "home"
    assert stored_status(token.raw_token) == "consumed"


def test_cross_user_link_is_denied_without_consuming():
    token = create_navigation_token(101, GuideShopRoute(kind="visits"))
    configure_guide_shop_ui(RecordingService(), reads_enabled=True)
    msg = direct_message(202)
    run(open_guide_shop_deep_link(msg, command(token.raw_token)))
    msg.answer.assert_awaited_once_with(LINK_ACCESS_DENIED_TEXT)
    assert stored_status(token.raw_token) == "issued"
    assert resolve_navigation_token(token.raw_token, 101).kind == "visits"


@pytest.mark.parametrize(
    "error",
    [
        NavigationTokenUnknownError("private"),
        NavigationTokenExpiredError("private"),
        NavigationTokenConsumedError("private"),
        NavigationTokenRevokedError("private"),
    ],
)
def test_stale_link_errors_are_safe_without_replacement(monkeypatch, error):
    configure_guide_shop_ui(RecordingService(), reads_enabled=True)
    monkeypatch.setattr(
        handler_module, "resolve_navigation_token", Mock(side_effect=error)
    )
    keyboard = Mock(side_effect=AssertionError("replacement created"))
    monkeypatch.setattr(handler_module, "build_guide_shop_keyboard", keyboard)
    msg = direct_message()
    run(open_guide_shop_deep_link(msg, command()))
    msg.answer.assert_awaited_once_with(STALE_LINK_TEXT)
    assert "private" not in msg.answer.await_args.args[0]
    keyboard.assert_not_called()


def test_invalid_stored_route_error_is_safe_without_replacement(monkeypatch):
    configure_guide_shop_ui(RecordingService(), reads_enabled=True)
    monkeypatch.setattr(
        handler_module,
        "resolve_navigation_token",
        Mock(side_effect=NavigationRouteInvalidError("private object")),
    )
    keyboard = Mock(side_effect=AssertionError("replacement created"))
    monkeypatch.setattr(handler_module, "build_guide_shop_keyboard", keyboard)
    msg = direct_message()
    run(open_guide_shop_deep_link(msg, command()))
    msg.answer.assert_awaited_once_with(INVALID_ROUTE_TEXT)
    keyboard.assert_not_called()


def test_unexpected_errors_are_not_swallowed(monkeypatch):
    configure_guide_shop_ui(RecordingService(), reads_enabled=True)
    monkeypatch.setattr(
        handler_module,
        "resolve_navigation_token",
        Mock(side_effect=TypeError("programming")),
    )
    with pytest.raises(TypeError, match="programming"):
        run(open_guide_shop_deep_link(direct_message(), command()))


def test_successful_link_is_single_use_and_repeat_is_stale():
    token = create_navigation_token(101, GuideShopRoute(kind="visits"))
    configure_guide_shop_ui(RecordingService(), reads_enabled=True)
    first = direct_message(101)
    run(open_guide_shop_deep_link(first, command(token.raw_token)))
    assert first.answer.await_args.args == ("Screen",)

    repeated = direct_message(101)
    run(open_guide_shop_deep_link(repeated, command(token.raw_token)))
    repeated.answer.assert_awaited_once_with(STALE_LINK_TEXT)
