import asyncio
import hashlib
import logging
from pathlib import Path
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import bot as bot_module
import handlers.guide_shop as handler_module
from database.db import get_connection
from handlers.guide_shop import (
    ACCESS_DENIED_TEXT,
    DISABLED_TEXT,
    INVALID_ROUTE_TEXT,
    STALE_TOKEN_TEXT,
    _dispatch_route,
    configure_guide_shop_ui,
    navigate_guide_shop,
    open_guide_shop,
    router,
)
from keyboards.main_menu import configure_guide_shop_menu, get_main_menu
from services.guide_shop_contracts import PointsStatus
from services.guide_shop_navigation import (
    GuideShopRoute,
    NavigationRouteInvalidError,
    NavigationTokenAccessDeniedError,
    NavigationTokenConsumedError,
    NavigationTokenExpiredError,
    NavigationTokenRevokedError,
    NavigationTokenUnknownError,
    create_navigation_token,
    resolve_navigation_token,
)
from services.guide_shop_settings import (
    GuideShopFeatureFlags,
    GuideShopJWTSigningSettingsError,
    GuideShopRuntimeSettings,
    GuideShopSettingsError,
)
from services.guide_shop_ui import GuideShopAction, GuideShopScreen


def run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture(autouse=True)
def reset_runtime():
    configure_guide_shop_ui(None, reads_enabled=False)
    configure_guide_shop_menu(None)
    yield
    configure_guide_shop_ui(None, reads_enabled=False)
    configure_guide_shop_menu(None)


def menu_texts(menu):
    return [[button.text for button in row] for row in menu.keyboard]


def navigation_count():
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) AS count FROM guide_shop_navigation_tokens"
    ).fetchone()["count"]
    conn.close()
    return count


def message(user_id=101):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncMock(),
    )


def callback(raw_token="gs_token", user_id=101):
    return SimpleNamespace(
        data=raw_token,
        from_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(
            chat=SimpleNamespace(id=999999),
            edit_text=AsyncMock(),
        ),
        answer=AsyncMock(),
    )


def real_environment(private_key_pem):
    return {
        "GUIDESHOP_READS_ENABLED": "true",
        "APP_ENV": "test",
        "GUIDESHOP_API_BASE_URL": "https://guideshop.test",
        "GUIDESHOP_JWT_KEY_ID": "guide-os.test-1",
        "GUIDESHOP_JWT_PRIVATE_KEY": private_key_pem,
    }


@pytest.fixture
def ephemeral_private_key_pem():
    return Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


def test_fake_setting_defaults_off_and_existing_flags_are_unchanged():
    assert GuideShopRuntimeSettings.from_env({}).use_fake is False
    assert GuideShopFeatureFlags.from_env({}) == GuideShopFeatureFlags(
        False, False, False, False
    )


@pytest.mark.parametrize("app_env", ["development", "DEVELOPMENT", "test", "Test"])
def test_fake_true_is_allowed_only_in_development_or_test(app_env):
    settings = GuideShopRuntimeSettings.from_env(
        {"GUIDESHOP_USE_FAKE": "true", "APP_ENV": app_env}
    )
    assert settings.use_fake


@pytest.mark.parametrize("app_env", [None, "production", "staging", "unknown", ""])
def test_fake_true_is_rejected_outside_authorized_environments(app_env):
    values = {"GUIDESHOP_USE_FAKE": "true"}
    if app_env is not None:
        values["APP_ENV"] = app_env
    with pytest.raises(GuideShopSettingsError):
        GuideShopRuntimeSettings.from_env(values)


def test_default_menu_is_exact_and_reads_append_without_reordering(monkeypatch):
    expected = [
        ["➕ Добавить тур"],
        ["🗓 Календарь"],
        ["🔎 Проверить дату"],
        ["🔔 Уведомления"],
        ["📊 Статистика"],
        ["👤 Профиль"],
    ]
    assert menu_texts(get_main_menu(reads_enabled=False)) == expected
    assert menu_texts(get_main_menu(reads_enabled=True)) == expected + [
        ["🛍 GuideShop"]
    ]

    configure_guide_shop_menu(None)
    monkeypatch.delenv("GUIDESHOP_READS_ENABLED", raising=False)
    assert menu_texts(get_main_menu()) == expected


def test_fake_alone_does_not_show_menu_button(monkeypatch):
    monkeypatch.setenv("GUIDESHOP_USE_FAKE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("GUIDESHOP_READS_ENABLED", raising=False)
    assert "🛍 GuideShop" not in sum(menu_texts(get_main_menu()), [])


def test_runtime_defaults_disabled_and_entry_creates_no_token():
    msg = message()
    before = navigation_count()
    run(open_guide_shop(msg))
    msg.answer.assert_awaited_once_with(DISABLED_TEXT)
    assert navigation_count() == before


class HomeService:
    async def home(self):
        return GuideShopScreen(
            "<b>GuideShop</b>",
            tuple(
                GuideShopAction(label, GuideShopRoute(kind=kind))
                for label, kind in (
                    ("Компании", "companies"),
                    ("Визиты", "visits"),
                    ("Продажи", "sales"),
                    ("Баллы 1", "points"),
                    ("Баллы 2", "points"),
                    ("История", "history"),
                )
            ),
        )


def test_enabled_entry_renders_six_user_bound_buttons():
    user_id = 424242
    msg = message(user_id)
    configure_guide_shop_ui(HomeService(), reads_enabled=True)
    run(open_guide_shop(msg))

    msg.answer.assert_awaited_once()
    call = msg.answer.await_args
    assert call.args == ("<b>GuideShop</b>",)
    assert call.kwargs["parse_mode"] == "HTML"
    callbacks = [
        row[0].callback_data
        for row in call.kwargs["reply_markup"].inline_keyboard
    ]
    assert len(callbacks) == 6
    for raw_token in callbacks:
        with pytest.raises(NavigationTokenAccessDeniedError):
            resolve_navigation_token(raw_token, user_id + 1)
        assert resolve_navigation_token(raw_token, user_id)


class RecordingService:
    def __init__(self):
        self.calls = []

    async def _record(self, name, *args):
        self.calls.append((name, args))
        return GuideShopScreen("Screen", ())

    async def home(self): return await self._record("home")
    async def companies(self): return await self._record("companies")
    async def visits(self, cursor=None): return await self._record("visits", cursor)
    async def visit_detail(self, object_id): return await self._record("visit_detail", object_id)
    async def sales(self, cursor=None): return await self._record("sales", cursor)
    async def sale_detail(self, object_id): return await self._record("sale_detail", object_id)
    async def points(self, status=None, cursor=None): return await self._record("points", status, cursor)
    async def points_detail(self, object_id): return await self._record("points_detail", object_id)
    async def history(self, cursor=None): return await self._record("history", cursor)


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        (GuideShopRoute(kind="home"), ("home", ())),
        (GuideShopRoute(kind="companies"), ("companies", ())),
        (GuideShopRoute(kind="visits", cursor="c1"), ("visits", ("c1",))),
        (GuideShopRoute(kind="visit_detail", object_id="v1"), ("visit_detail", ("v1",))),
        (GuideShopRoute(kind="sales", cursor="c2"), ("sales", ("c2",))),
        (GuideShopRoute(kind="sale_detail", object_id="s1"), ("sale_detail", ("s1",))),
        (GuideShopRoute(kind="points", cursor="c3", points_status=PointsStatus.PENDING), ("points", (PointsStatus.PENDING, "c3"))),
        (GuideShopRoute(kind="points_detail", object_id="p1"), ("points_detail", ("p1",))),
        (GuideShopRoute(kind="history", cursor="c4"), ("history", ("c4",))),
    ],
)
def test_every_typed_route_dispatches_exact_service_arguments(route, expected):
    service = RecordingService()
    assert run(_dispatch_route(service, route)).text == "Screen"
    assert service.calls == [expected]


def test_disabled_callback_does_not_resolve_or_edit(monkeypatch):
    cb = callback()
    resolver = Mock(side_effect=AssertionError("resolver called"))
    monkeypatch.setattr(handler_module, "resolve_navigation_token", resolver)
    run(navigate_guide_shop(cb))
    resolver.assert_not_called()
    cb.message.edit_text.assert_not_awaited()
    cb.answer.assert_awaited_once_with(DISABLED_TEXT)


def test_disabled_callback_leaves_existing_token_issued():
    token = create_navigation_token(101, GuideShopRoute(kind="home"))
    cb = callback(token.raw_token, 101)
    run(navigate_guide_shop(cb))

    cb.answer.assert_awaited_once_with(DISABLED_TEXT)
    assert resolve_navigation_token(token.raw_token, 101).kind == "home"


def test_successful_callback_uses_callback_user_edits_and_answers_once():
    user_id = 515151
    original = create_navigation_token(
        user_id, GuideShopRoute(kind="home")
    )
    service = RecordingService()

    async def home_with_action():
        service.calls.append(("home", ()))
        return GuideShopScreen(
            "<b>Fresh</b>",
            (GuideShopAction("Next", GuideShopRoute(kind="companies")),),
        )

    service.home = home_with_action
    configure_guide_shop_ui(service, reads_enabled=True)
    cb = callback(original.raw_token, user_id)
    run(navigate_guide_shop(cb))

    cb.message.edit_text.assert_awaited_once()
    edit = cb.message.edit_text.await_args
    assert edit.args == ("<b>Fresh</b>",)
    assert edit.kwargs["parse_mode"] == "HTML"
    fresh_token = edit.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
    with pytest.raises(NavigationTokenAccessDeniedError):
        resolve_navigation_token(fresh_token, cb.message.chat.id)
    assert resolve_navigation_token(fresh_token, user_id).kind == "companies"
    cb.answer.assert_awaited_once_with()


def test_cross_user_callback_is_safe_and_leaves_token_unconsumed():
    token = create_navigation_token(101, GuideShopRoute(kind="home"))
    configure_guide_shop_ui(RecordingService(), reads_enabled=True)
    cb = callback(token.raw_token, 202)
    run(navigate_guide_shop(cb))
    cb.answer.assert_awaited_once_with(ACCESS_DENIED_TEXT)
    cb.message.edit_text.assert_not_awaited()
    assert resolve_navigation_token(token.raw_token, 101).kind == "home"


@pytest.mark.parametrize(
    ("error", "text"),
    [
        (NavigationTokenUnknownError("private"), STALE_TOKEN_TEXT),
        (NavigationTokenExpiredError("private"), STALE_TOKEN_TEXT),
        (NavigationTokenConsumedError("private"), STALE_TOKEN_TEXT),
        (NavigationTokenRevokedError("private"), STALE_TOKEN_TEXT),
        (NavigationTokenAccessDeniedError("private"), ACCESS_DENIED_TEXT),
        (NavigationRouteInvalidError("private"), INVALID_ROUTE_TEXT),
    ],
)
def test_navigation_errors_answer_once_without_edit_or_replacement(monkeypatch, error, text):
    configure_guide_shop_ui(RecordingService(), reads_enabled=True)
    monkeypatch.setattr(
        handler_module,
        "resolve_navigation_token",
        Mock(side_effect=error),
    )
    keyboard_builder = Mock(side_effect=AssertionError("keyboard built"))
    monkeypatch.setattr(handler_module, "build_guide_shop_keyboard", keyboard_builder)
    cb = callback()
    run(navigate_guide_shop(cb))
    cb.answer.assert_awaited_once_with(text)
    cb.message.edit_text.assert_not_awaited()
    keyboard_builder.assert_not_called()


def test_unexpected_programming_errors_are_not_swallowed(monkeypatch):
    configure_guide_shop_ui(RecordingService(), reads_enabled=True)
    monkeypatch.setattr(
        handler_module,
        "resolve_navigation_token",
        Mock(side_effect=TypeError("programming")),
    )
    with pytest.raises(TypeError, match="programming"):
        run(navigate_guide_shop(callback()))


def test_callback_filter_does_not_claim_non_navigation_data():
    handler = router.callback_query.handlers[0]
    matched, _ = run(handler.check(callback("other:data")))
    assert not matched
    matched, _ = run(handler.check(callback("gs_value")))
    assert matched


def test_composition_default_off_ignores_real_settings_and_clears_provider(monkeypatch):
    fake = Mock(side_effect=AssertionError("fake instantiated"))
    http_settings = Mock(side_effect=AssertionError("HTTP settings parsed"))
    signing_settings = Mock(side_effect=AssertionError("JWT settings parsed"))
    token_provider = Mock(side_effect=AssertionError("token provider created"))
    http_client = Mock(side_effect=AssertionError("HTTP client created"))
    monkeypatch.setattr(bot_module, "InMemoryGuideShopClient", fake)
    monkeypatch.setattr(bot_module.GuideShopHTTPSettings, "from_env", http_settings)
    monkeypatch.setattr(
        bot_module.GuideShopJWTSigningSettings, "from_env", signing_settings
    )
    monkeypatch.setattr(bot_module, "GuideShopJWTAccessTokenProvider", token_provider)
    monkeypatch.setattr(bot_module, "HTTPGuideShopClient", http_client)

    configure_guide_shop_ui(HomeService(), reads_enabled=True)
    bot_module.configure_guide_shop_runtime(
        {
            "APP_ENV": "private-invalid",
            "GUIDESHOP_USE_FAKE": "private-invalid",
            "GUIDESHOP_API_BASE_URL": "private-invalid",
            "GUIDESHOP_JWT_PRIVATE_KEY": "private-invalid",
        }
    )
    fake.assert_not_called()
    http_settings.assert_not_called()
    signing_settings.assert_not_called()
    token_provider.assert_not_called()
    http_client.assert_not_called()
    assert "🛍 GuideShop" not in sum(menu_texts(get_main_menu()), [])
    msg = message()
    run(open_guide_shop(msg))
    msg.answer.assert_awaited_once_with(DISABLED_TEXT)


def test_composition_explicit_development_fake_uses_empty_data(monkeypatch):
    client = object()
    fake = Mock(return_value=client)
    ui = Mock(return_value=object())
    configured = Mock()
    monkeypatch.setattr(bot_module, "InMemoryGuideShopClient", fake)
    monkeypatch.setattr(bot_module, "GuideShopUIService", ui)
    monkeypatch.setattr(bot_module, "configure_guide_shop_ui", configured)

    bot_module.configure_guide_shop_runtime(
        {
            "GUIDESHOP_READS_ENABLED": "true",
            "GUIDESHOP_USE_FAKE": "true",
            "APP_ENV": "development",
        }
    )
    fake.assert_called_once_with(
        companies=(), visits=(), sales=(), points=(), points_history=()
    )
    ui.assert_called_once_with(client)
    configured.assert_called_once_with(ui.return_value, reads_enabled=True)


def test_fake_composition_does_not_parse_or_require_real_settings(monkeypatch):
    monkeypatch.setattr(
        bot_module.GuideShopHTTPSettings,
        "from_env",
        Mock(side_effect=AssertionError("HTTP settings parsed")),
    )
    monkeypatch.setattr(
        bot_module.GuideShopJWTSigningSettings,
        "from_env",
        Mock(side_effect=AssertionError("JWT settings parsed")),
    )
    bot_module.configure_guide_shop_runtime(
        {
            "GUIDESHOP_READS_ENABLED": "true",
            "GUIDESHOP_USE_FAKE": "true",
            "APP_ENV": "test",
        }
    )


def test_composition_reads_without_fake_rejects_missing_configuration_and_clears():
    configure_guide_shop_ui(HomeService(), reads_enabled=True)
    with pytest.raises(GuideShopSettingsError):
        bot_module.configure_guide_shop_runtime(
            {"GUIDESHOP_READS_ENABLED": "true"}
        )
    msg = message()
    run(open_guide_shop(msg))
    msg.answer.assert_awaited_once_with(DISABLED_TEXT)


class ComposedClient:
    def __init__(self, settings, identity, token_provider):
        self.settings = settings
        self.identity = identity
        self.token_provider = token_provider
        self.close_calls = 0

    async def close(self): self.close_calls += 1
    async def list_companies(self): raise AssertionError("unused")
    async def list_visits(self, cursor=None): raise AssertionError("unused")
    async def get_visit(self, visit_id): raise AssertionError("unused")
    async def list_sales(self, cursor=None): raise AssertionError("unused")
    async def get_sale(self, sale_id): raise AssertionError("unused")
    async def list_points(self, status=None, cursor=None): raise AssertionError("unused")
    async def get_points_transaction(self, points_transaction_id): raise AssertionError("unused")
    async def list_history(self, cursor=None): raise AssertionError("unused")


def test_valid_real_composition_is_lazy_isolated_and_uses_trusted_lookup(
    monkeypatch, ephemeral_private_key_pem
):
    identity_lookup = Mock(
        side_effect=lambda user_id: {101: "guide-a", 202: "guide-b"}[user_id]
    )
    token_provider = SimpleNamespace(get_access_token=AsyncMock())
    token_provider_factory = Mock(return_value=token_provider)
    http_client_factory = Mock(side_effect=ComposedClient)
    configured = Mock()
    monkeypatch.setattr(bot_module, "get_guide_os_id", identity_lookup)
    monkeypatch.setattr(
        bot_module, "GuideShopJWTAccessTokenProvider", token_provider_factory
    )
    monkeypatch.setattr(bot_module, "HTTPGuideShopClient", http_client_factory)
    monkeypatch.setattr(bot_module, "configure_guide_shop_provider", configured)

    bot_module.configure_guide_shop_runtime(
        real_environment(ephemeral_private_key_pem)
    )

    token_provider_factory.assert_called_once()
    http_client_factory.assert_not_called()
    identity_lookup.assert_not_called()
    assert configured.call_count == 2
    assert configured.call_args_list[0].args == (None,)
    assert configured.call_args_list[0].kwargs == {"reads_enabled": False}
    provider = configured.call_args_list[1].args[0]
    assert configured.call_args_list[1].kwargs == {"reads_enabled": True}

    async def exercise():
        clients = []
        for user_id in (101, 202, 101):
            async with provider.service_for(user_id) as service:
                clients.append(service._client)
        return clients

    clients = run(exercise())
    assert [client.identity for client in clients] == ["guide-a", "guide-b", "guide-a"]
    assert len({id(client) for client in clients}) == 3
    assert [client.close_calls for client in clients] == [1, 1, 1]
    assert [called.args[0] for called in identity_lookup.call_args_list] == [101, 202, 101]
    assert all(client.token_provider is token_provider for client in clients)
    assert len({id(client.settings) for client in clients}) == 1


def test_real_composition_startup_has_no_request_side_effects(
    monkeypatch, ephemeral_private_key_pem
):
    identity_lookup = Mock(side_effect=AssertionError("identity lookup"))
    token_provider = SimpleNamespace(
        get_access_token=AsyncMock(side_effect=AssertionError("token signing"))
    )
    http_client = Mock(side_effect=AssertionError("HTTP client"))
    navigation = Mock(side_effect=AssertionError("navigation token"))
    network = Mock(side_effect=AssertionError("network"))
    monkeypatch.setattr(bot_module, "get_guide_os_id", identity_lookup)
    monkeypatch.setattr(
        bot_module, "GuideShopJWTAccessTokenProvider", Mock(return_value=token_provider)
    )
    monkeypatch.setattr(bot_module, "HTTPGuideShopClient", http_client)
    monkeypatch.setattr(
        "services.guide_shop_navigation.create_navigation_token", navigation
    )
    monkeypatch.setattr(socket, "create_connection", network)

    bot_module.configure_guide_shop_runtime(real_environment(ephemeral_private_key_pem))
    identity_lookup.assert_not_called()
    token_provider.get_access_token.assert_not_awaited()
    http_client.assert_not_called()
    navigation.assert_not_called()
    network.assert_not_called()


def test_real_configuration_error_is_safe_and_has_no_fallback(
    caplog, ephemeral_private_key_pem
):
    private_value = "private-key-route-token-value"
    values = real_environment(ephemeral_private_key_pem)
    values["GUIDESHOP_JWT_PRIVATE_KEY"] = private_value
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(GuideShopJWTSigningSettingsError) as error:
            bot_module.configure_guide_shop_runtime(values)
    assert private_value not in str(error.value)
    assert private_value not in caplog.text
    msg = message()
    run(open_guide_shop(msg))
    msg.answer.assert_awaited_once_with(DISABLED_TEXT)


def test_guide_shop_router_is_registered_before_errors_router():
    source = Path(bot_module.__file__).read_text(encoding="utf-8")
    assert source.index("dp.include_router(guide_shop_router)") < source.index(
        "dp.include_router(errors.router)"
    )


def test_handler_flow_performs_no_network_and_logs_no_sensitive_data(
    monkeypatch, caplog
):
    user_id = 676767
    configure_guide_shop_ui(HomeService(), reads_enabled=True)
    msg = message(user_id)

    def unexpected(*args, **kwargs):
        raise AssertionError("network operation attempted")

    async def exercise():
        monkeypatch.setattr(socket, "socket", unexpected)
        await open_guide_shop(msg)

    caplog.set_level(logging.DEBUG)
    run(exercise())
    callback_data = msg.answer.await_args.kwargs[
        "reply_markup"
    ].inline_keyboard[0][0].callback_data
    token_hash = hashlib.sha256(callback_data.encode("utf-8")).hexdigest()
    assert str(user_id) not in caplog.text
    assert callback_data not in caplog.text
    assert token_hash not in caplog.text
