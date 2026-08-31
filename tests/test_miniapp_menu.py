import logging
import pytest

from keyboards.main_menu import (
    MINI_APP_MENU_LABEL,
    configure_miniapp_menu,
    configure_guide_shop_menu,
    get_main_menu,
)
from services.miniapp_api_settings import MiniAppMenuSettings, normalize_miniapp_public_url


def menu_texts(menu):
    return [[button.text for button in row] for row in menu.keyboard]


def mini_app_urls(menu):
    urls = []
    for row in menu.keyboard:
        for button in row:
            if button.web_app is not None:
                urls.append(button.web_app.url)
    return urls


@pytest.fixture(autouse=True)
def reset_menu():
    configure_guide_shop_menu(None)
    configure_miniapp_menu(None)
    yield
    configure_guide_shop_menu(None)
    configure_miniapp_menu(None)


def test_default_menu_has_no_mini_app_button():
    assert MINI_APP_MENU_LABEL not in sum(menu_texts(get_main_menu()), [])
    assert mini_app_urls(get_main_menu()) == []


def test_mini_app_enabled_false_hides_button_even_with_url():
    configure_miniapp_menu(None)
    settings = MiniAppMenuSettings.from_env(
        {
            "MINI_APP_ENABLED": "false",
            "MINI_APP_PUBLIC_URL": "https://miniapp.example.com",
            "APP_ENV": "production",
        }
    )
    assert settings.enabled is False
    assert MINI_APP_MENU_LABEL not in sum(menu_texts(get_main_menu()), [])


def test_enabled_with_valid_url_shows_one_mini_app_button():
    url = "https://miniapp.example.com"
    configure_miniapp_menu(url)
    menu = get_main_menu()
    labels = sum(menu_texts(menu), [])
    assert labels.count(MINI_APP_MENU_LABEL) == 1
    assert mini_app_urls(menu) == [url]


def test_mini_app_button_uses_web_app_info_url():
    url = "https://miniapp.example.com/app"
    configure_miniapp_menu(url)
    menu = get_main_menu()
    button = next(
        button
        for row in menu.keyboard
        for button in row
        if button.text == MINI_APP_MENU_LABEL
    )
    assert button.web_app is not None
    assert button.web_app.url == url


def test_invalid_url_shows_no_button_and_menu_stays_usable():
    settings = MiniAppMenuSettings.from_env(
        {
            "MINI_APP_ENABLED": "true",
            "MINI_APP_PUBLIC_URL": "not-a-valid-url",
            "APP_ENV": "production",
        }
    )
    assert settings.public_url is None
    configure_miniapp_menu(settings.public_url)
    texts = sum(menu_texts(get_main_menu()), [])
    assert MINI_APP_MENU_LABEL not in texts
    assert "➕ Добавить тур" in texts
    assert "👤 Профиль" in texts


def test_guide_shop_rows_remain_when_mini_app_enabled():
    configure_miniapp_menu("https://miniapp.example.com")
    texts = sum(menu_texts(get_main_menu()), [])
    assert "🛍 GuideShop" in texts
    assert ["🛍 GuideShop"] in menu_texts(get_main_menu())


def test_repeated_configuration_does_not_duplicate_mini_app_button():
    url = "https://miniapp.example.com"
    configure_miniapp_menu(url)
    configure_miniapp_menu(url)
    labels = sum(menu_texts(get_main_menu()), [])
    assert labels.count(MINI_APP_MENU_LABEL) == 1


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


def test_configure_miniapp_runtime_from_env(caplog):
    import bot as bot_module

    with caplog.at_level(logging.WARNING):
        bot_module.configure_miniapp_runtime(
            {
                "MINI_APP_ENABLED": "true",
                "MINI_APP_PUBLIC_URL": "",
                "APP_ENV": "production",
            }
        )
    assert MINI_APP_MENU_LABEL not in sum(menu_texts(get_main_menu()), [])
    assert "MINI_APP_PUBLIC_URL missing or invalid" in caplog.text

    bot_module.configure_miniapp_runtime(
        {
            "MINI_APP_ENABLED": "true",
            "MINI_APP_PUBLIC_URL": "https://miniapp.example.com",
            "APP_ENV": "production",
        }
    )
    assert mini_app_urls(get_main_menu()) == ["https://miniapp.example.com"]
