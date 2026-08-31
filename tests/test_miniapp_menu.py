import asyncio
import logging
from unittest.mock import AsyncMock

import pytest
from aiogram.types import MenuButtonCommands, MenuButtonWebApp

import bot as bot_module
from keyboards.main_menu import configure_guide_shop_menu, get_main_menu
from services.miniapp_api_settings import MiniAppMenuSettings, normalize_miniapp_public_url


def run(awaitable):
    return asyncio.run(awaitable)


def menu_texts(menu):
    return [[button.text for button in row] for row in menu.keyboard]


def reply_web_app_urls(menu):
    urls = []
    for row in menu.keyboard:
        for button in row:
            if button.web_app is not None:
                urls.append(button.web_app.url)
    return urls


@pytest.fixture(autouse=True)
def reset_menu():
    configure_guide_shop_menu(None)
    yield
    configure_guide_shop_menu(None)


def test_default_menu_has_no_web_app_reply_button():
    assert reply_web_app_urls(get_main_menu()) == []


def test_mini_app_enabled_false_keeps_reply_keyboard_only():
    settings = MiniAppMenuSettings.from_env(
        {
            "MINI_APP_ENABLED": "false",
            "MINI_APP_PUBLIC_URL": "https://miniapp.example.com",
            "APP_ENV": "production",
        }
    )
    assert settings.enabled is False
    assert reply_web_app_urls(get_main_menu()) == []


def test_main_reply_keyboard_unchanged_when_mini_app_enabled_in_settings():
    settings = MiniAppMenuSettings.from_env(
        {
            "MINI_APP_ENABLED": "true",
            "MINI_APP_PUBLIC_URL": "https://miniapp.example.com",
            "APP_ENV": "production",
        }
    )
    assert settings.public_url == "https://miniapp.example.com"
    expected = [
        ["➕ Добавить тур"],
        ["🗓 Календарь"],
        ["🔎 Проверить дату"],
        ["🔔 Уведомления"],
        ["📊 Статистика"],
        ["👤 Профиль"],
        ["🛍 GuideShop"],
    ]
    assert menu_texts(get_main_menu()) == expected
    assert reply_web_app_urls(get_main_menu()) == []


def test_invalid_url_keeps_reply_keyboard_usable():
    settings = MiniAppMenuSettings.from_env(
        {
            "MINI_APP_ENABLED": "true",
            "MINI_APP_PUBLIC_URL": "not-a-valid-url",
            "APP_ENV": "production",
        }
    )
    assert settings.public_url is None
    texts = sum(menu_texts(get_main_menu()), [])
    assert "➕ Добавить тур" in texts
    assert "👤 Профиль" in texts
    assert reply_web_app_urls(get_main_menu()) == []


def test_guide_shop_rows_remain():
    texts = sum(menu_texts(get_main_menu()), [])
    assert "🛍 GuideShop" in texts
    assert ["🛍 GuideShop"] in menu_texts(get_main_menu())


def test_get_main_menu_signature_remains_compatible():
    menu = get_main_menu()
    menu_with_flag = get_main_menu(reads_enabled=False)
    assert menu_texts(menu) == menu_texts(menu_with_flag)


def test_menu_settings_default_disabled():
    settings = MiniAppMenuSettings.from_env({})
    assert settings.enabled is False
    assert settings.public_url is None


def test_normalize_public_url_requires_https_in_production():
    assert normalize_miniapp_public_url("http://miniapp.example.com", "production") is None
    assert normalize_miniapp_public_url("https://miniapp.example.com", "production") == (
        "https://miniapp.example.com"
    )


def test_normalize_public_url_allows_localhost_http_in_development():
    assert normalize_miniapp_public_url("http://127.0.0.1:5173", "development") == (
        "http://127.0.0.1:5173"
    )


def test_configure_miniapp_runtime_warns_on_invalid_public_url(caplog):
    with caplog.at_level(logging.WARNING):
        bot_module.configure_miniapp_runtime(
            {
                "MINI_APP_ENABLED": "true",
                "MINI_APP_PUBLIC_URL": "",
                "APP_ENV": "production",
            }
        )
    assert "MINI_APP_PUBLIC_URL missing or invalid" in caplog.text


def test_setup_miniapp_chat_menu_button_enabled_uses_default_web_app_button():
    bot = AsyncMock()
    run(
        bot_module.setup_miniapp_chat_menu_button(
            bot,
            {
                "MINI_APP_ENABLED": "true",
                "MINI_APP_PUBLIC_URL": "https://miniapp.example.com",
                "APP_ENV": "production",
            },
        )
    )
    bot.set_chat_menu_button.assert_awaited_once()
    call = bot.set_chat_menu_button.await_args
    assert "chat_id" not in call.kwargs
    menu_button = call.kwargs["menu_button"]
    assert isinstance(menu_button, MenuButtonWebApp)
    assert menu_button.text == bot_module.MINIAPP_CHAT_MENU_BUTTON_TEXT
    assert menu_button.web_app.url == "https://miniapp.example.com"


def test_setup_miniapp_chat_menu_button_disabled_uses_commands():
    bot = AsyncMock()
    run(
        bot_module.setup_miniapp_chat_menu_button(
            bot,
            {
                "MINI_APP_ENABLED": "false",
                "MINI_APP_PUBLIC_URL": "https://miniapp.example.com",
                "APP_ENV": "production",
            },
        )
    )
    menu_button = bot.set_chat_menu_button.await_args.kwargs["menu_button"]
    assert isinstance(menu_button, MenuButtonCommands)


def test_setup_miniapp_chat_menu_button_invalid_url_uses_commands():
    bot = AsyncMock()
    run(
        bot_module.setup_miniapp_chat_menu_button(
            bot,
            {
                "MINI_APP_ENABLED": "true",
                "MINI_APP_PUBLIC_URL": "not-a-valid-url",
                "APP_ENV": "production",
            },
        )
    )
    menu_button = bot.set_chat_menu_button.await_args.kwargs["menu_button"]
    assert isinstance(menu_button, MenuButtonCommands)


def test_setup_miniapp_chat_menu_button_failure_is_sanitized(caplog):
    bot = AsyncMock()
    bot.set_chat_menu_button.side_effect = RuntimeError("https://secret-miniapp.example failed")
    with caplog.at_level(logging.WARNING):
        run(
            bot_module.setup_miniapp_chat_menu_button(
                bot,
                {
                    "MINI_APP_ENABLED": "true",
                    "MINI_APP_PUBLIC_URL": "https://secret-miniapp.example",
                    "APP_ENV": "production",
                },
            )
        )
    assert any(
        record.message == "Mini App chat menu button configuration failed"
        for record in caplog.records
    )
    assert "https://secret-miniapp.example" not in caplog.text
