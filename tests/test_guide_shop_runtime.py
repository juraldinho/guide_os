import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import handlers.guide_shop as handler_module
from handlers.guide_shop import (
    DISABLED_TEXT,
    configure_guide_shop_provider,
    configure_guide_shop_ui,
    navigate_guide_shop,
    open_guide_shop,
    open_guide_shop_deep_link,
)
from services.guide_shop_navigation import (
    GuideShopRoute,
    NavigationTokenUnknownError,
    create_navigation_token,
    resolve_navigation_token,
)
from services.guide_shop_runtime import (
    GuideShopClientLifecycleError,
    GuideShopIdentityUnavailableError,
    GuideShopRuntimeConfigurationError,
    GuideShopUIServiceProvider,
    RequestScopedGuideShopUIServiceProvider,
    StaticGuideShopUIServiceProvider,
)
from services.guide_shop_ui import GuideShopScreen, GuideShopUIService


def run(awaitable):
    return asyncio.run(awaitable)


class CloseableClient:
    def __init__(self, identity, *, failure=None):
        self.identity = identity
        self.failure = failure
        self.close = AsyncMock()

    async def list_companies(self):
        if self.failure is not None:
            raise self.failure
        raise AssertionError("unused")

    async def list_visits(self, cursor=None):
        if self.failure is not None:
            raise self.failure
        raise AssertionError("unused")

    async def get_visit(self, visit_id):
        if self.failure is not None:
            raise self.failure
        raise AssertionError("unused")

    async def list_sales(self, cursor=None):
        raise AssertionError("unused")

    async def get_sale(self, sale_id):
        raise AssertionError("unused")

    async def list_points(self, status=None, cursor=None):
        raise AssertionError("unused")

    async def get_points_transaction(self, points_transaction_id):
        raise AssertionError("unused")

    async def list_history(self, cursor=None):
        raise AssertionError("unused")


def provider_for(identities, *, clients=None, failure=None):
    lookup = Mock(side_effect=lambda user_id: identities.get(user_id))
    created = [] if clients is None else clients

    def factory(identity):
        client = CloseableClient(identity, failure=failure)
        created.append(client)
        return client

    return RequestScopedGuideShopUIServiceProvider(lookup, factory), lookup, created


@pytest.fixture(autouse=True)
def reset_runtime():
    configure_guide_shop_ui(None, reads_enabled=False)
    yield
    configure_guide_shop_ui(None, reads_enabled=False)


def message(user_id=101, *, answer_error=None):
    answer = AsyncMock()
    if answer_error is not None:
        answer.side_effect = answer_error
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id), answer=answer)


def callback(raw_token="gs_token", user_id=101, *, edit_error=None):
    edit_text = AsyncMock()
    if edit_error is not None:
        edit_text.side_effect = edit_error
    return SimpleNamespace(
        data=raw_token,
        from_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(edit_text=edit_text),
        answer=AsyncMock(),
    )


def test_provider_protocol_and_one_lookup_client_and_service_per_scope():
    provider, lookup, clients = provider_for({101: "guide-a"})
    assert isinstance(provider, GuideShopUIServiceProvider)

    async def exercise():
        async with provider.service_for(101) as service:
            assert isinstance(service, GuideShopUIService)
            assert service._client is clients[0]

    run(exercise())
    lookup.assert_called_once_with(101)
    assert [client.identity for client in clients] == ["guide-a"]
    clients[0].close.assert_awaited_once_with()


def test_complete_closeable_client_satisfies_runtime_protocol():
    client = CloseableClient("guide-a")
    provider = RequestScopedGuideShopUIServiceProvider(
        Mock(return_value="guide-a"), Mock(return_value=client)
    )

    async def exercise():
        async with provider.service_for(101) as service:
            assert service._client is client

    run(exercise())
    client.close.assert_awaited_once_with()


def test_none_client_is_rejected_before_service_is_yielded():
    provider = RequestScopedGuideShopUIServiceProvider(
        Mock(return_value="guide-a"), Mock(return_value=None)
    )
    yielded = False

    async def exercise():
        nonlocal yielded
        async with provider.service_for(101):
            yielded = True

    with pytest.raises(GuideShopRuntimeConfigurationError):
        run(exercise())
    assert yielded is False


def test_close_only_partial_client_is_rejected_and_closed_once():
    partial = SimpleNamespace(close=AsyncMock())
    provider = RequestScopedGuideShopUIServiceProvider(
        Mock(return_value="guide-a"), Mock(return_value=partial)
    )

    async def exercise():
        async with provider.service_for(101):
            raise AssertionError("must not yield")

    with pytest.raises(GuideShopRuntimeConfigurationError):
        run(exercise())
    partial.close.assert_awaited_once_with()


def test_complete_client_with_non_async_close_is_rejected_safely():
    client = CloseableClient("private-identity")
    client.close = Mock(return_value=None)
    provider = RequestScopedGuideShopUIServiceProvider(
        Mock(return_value="private-identity"), Mock(return_value=client)
    )

    async def exercise():
        async with provider.service_for(101):
            raise AssertionError("must not yield")

    with pytest.raises(GuideShopRuntimeConfigurationError) as error:
        run(exercise())
    client.close.assert_not_called()
    assert "private-identity" not in str(error.value)


def test_invalid_client_cleanup_failure_is_focused_and_safe():
    partial = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("private")))
    provider = RequestScopedGuideShopUIServiceProvider(
        Mock(return_value="secret-identity"), Mock(return_value=partial)
    )

    async def exercise():
        async with provider.service_for(101):
            pass

    with pytest.raises(GuideShopClientLifecycleError) as error:
        run(exercise())
    assert "private" not in str(error.value)
    assert "secret-identity" not in str(error.value)
    partial.close.assert_awaited_once_with()


@pytest.mark.parametrize("user_id", [True, False, 0, -1, "101", 1.5])
def test_invalid_telegram_user_id_performs_no_lookup_or_client_creation(user_id):
    provider, lookup, clients = provider_for({101: "guide-a"})

    async def exercise():
        async with provider.service_for(user_id):
            pass

    with pytest.raises(GuideShopIdentityUnavailableError):
        run(exercise())
    lookup.assert_not_called()
    assert clients == []


@pytest.mark.parametrize("identity", [None, "", "   ", " guide-a", "guide-a\n", 123, True])
def test_missing_or_malformed_identity_creates_no_client(identity):
    provider, lookup, clients = provider_for({101: identity})

    async def exercise():
        async with provider.service_for(101):
            pass

    with pytest.raises(GuideShopIdentityUnavailableError):
        run(exercise())
    lookup.assert_called_once_with(101)
    assert clients == []


def test_client_factory_failure_is_safe_and_has_no_close_attempt():
    lookup = Mock(return_value="private-guide")
    factory = Mock(side_effect=RuntimeError("private credential detail"))
    provider = RequestScopedGuideShopUIServiceProvider(lookup, factory)

    async def exercise():
        async with provider.service_for(101):
            pass

    with pytest.raises(GuideShopClientLifecycleError) as error:
        run(exercise())
    assert "private" not in str(error.value)
    factory.assert_called_once_with("private-guide")


def test_two_users_and_repeated_user_requests_receive_distinct_scopes():
    provider, lookup, clients = provider_for({101: "guide-a", 202: "guide-b"})

    async def exercise():
        services = []
        for user_id in (101, 202, 101):
            async with provider.service_for(user_id) as service:
                services.append(service)
        return services

    services = run(exercise())
    assert [called.args for called in lookup.call_args_list] == [(101,), (202,), (101,)]
    assert [client.identity for client in clients] == ["guide-a", "guide-b", "guide-a"]
    assert len({id(client) for client in clients}) == 3
    assert len({id(service) for service in services}) == 3
    for client in clients:
        client.close.assert_awaited_once_with()


def test_concurrent_scopes_do_not_share_or_overwrite_identity():
    provider, _, clients = provider_for({101: "guide-a", 202: "guide-b"})
    both_open = asyncio.Event()
    opened = 0

    async def use_scope(user_id):
        nonlocal opened
        async with provider.service_for(user_id) as service:
            opened += 1
            if opened == 2:
                both_open.set()
            await both_open.wait()
            return service._client.identity, id(service._client)

    async def exercise():
        return await asyncio.gather(use_scope(101), use_scope(202))

    results = run(exercise())
    assert {result[0] for result in results} == {"guide-a", "guide-b"}
    assert results[0][1] != results[1][1]
    assert len(clients) == 2


def test_client_closes_once_after_body_exception_and_preserves_original():
    provider, _, clients = provider_for({101: "guide-a"})

    async def exercise():
        async with provider.service_for(101):
            clients[0].close.side_effect = RuntimeError("private close detail")
            raise ValueError("original error")

    with pytest.raises(ValueError, match="original error"):
        run(exercise())
    clients[0].close.assert_awaited_once_with()


def test_cleanup_failure_without_active_error_is_focused_and_safe():
    provider, _, clients = provider_for({101: "guide-a"})

    async def exercise():
        async with provider.service_for(101):
            clients[0].close.side_effect = RuntimeError("private close detail")

    with pytest.raises(GuideShopClientLifecycleError) as error:
        run(exercise())
    assert "private" not in str(error.value)
    clients[0].close.assert_awaited_once_with()


def test_context_cancellation_closes_once_and_preserves_cancellation():
    provider, _, clients = provider_for({101: "guide-a"})
    entered = asyncio.Event()

    async def worker():
        async with provider.service_for(101):
            entered.set()
            await asyncio.Event().wait()

    async def exercise():
        task = asyncio.create_task(worker())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(exercise())
    clients[0].close.assert_awaited_once_with()


def test_static_provider_reuses_service_and_never_closes_shared_client():
    client = CloseableClient("shared")
    service = GuideShopUIService(client)
    provider = StaticGuideShopUIServiceProvider(service)

    async def exercise():
        async with provider.service_for(101) as first:
            pass
        async with provider.service_for(202) as second:
            pass
        return first, second

    first, second = run(exercise())
    assert first is service and second is service
    client.close.assert_not_awaited()


def test_configure_ui_remains_backward_compatible_static_provider():
    service = SimpleNamespace(home=AsyncMock(return_value=GuideShopScreen("Home", ())))
    configure_guide_shop_ui(service, reads_enabled=True)
    msg = message(101)
    run(open_guide_shop(msg))
    service.home.assert_awaited_once_with()
    msg.answer.assert_awaited_once()


@pytest.mark.parametrize("malformed", [object(), SimpleNamespace(), SimpleNamespace(service_for=None)])
def test_malformed_service_provider_is_rejected_immediately(malformed):
    with pytest.raises(GuideShopRuntimeConfigurationError):
        configure_guide_shop_provider(malformed, reads_enabled=True)


def test_failed_provider_reconfiguration_clears_previous_provider():
    service = SimpleNamespace(home=AsyncMock(return_value=GuideShopScreen("Home", ())))
    configure_guide_shop_ui(service, reads_enabled=True)
    with pytest.raises(GuideShopRuntimeConfigurationError):
        configure_guide_shop_provider(object(), reads_enabled=True)

    msg = message(101)
    run(open_guide_shop(msg))
    service.home.assert_not_awaited()
    msg.answer.assert_awaited_once_with(DISABLED_TEXT)


def test_invalid_client_does_not_consume_callback_or_deep_link_tokens():
    provider = RequestScopedGuideShopUIServiceProvider(
        Mock(return_value="trusted-guide"), Mock(return_value=None)
    )
    configure_guide_shop_provider(provider, reads_enabled=True)

    callback_token = create_navigation_token(101, GuideShopRoute(kind="home"))
    cb = callback(callback_token.raw_token, 101)
    run(navigate_guide_shop(cb))
    cb.answer.assert_awaited_once_with(DISABLED_TEXT)
    assert resolve_navigation_token(callback_token.raw_token, 101).kind == "home"

    deep_link_token = create_navigation_token(101, GuideShopRoute(kind="home"))
    msg = message(101)
    run(
        open_guide_shop_deep_link(
            msg, SimpleNamespace(args=deep_link_token.raw_token)
        )
    )
    msg.answer.assert_awaited_once_with(DISABLED_TEXT)
    assert resolve_navigation_token(deep_link_token.raw_token, 101).kind == "home"


def test_handler_missing_identity_maps_safe_and_does_not_render():
    provider, lookup, clients = provider_for({})
    configure_guide_shop_provider(provider, reads_enabled=True)
    msg = message(101)
    run(open_guide_shop(msg))
    msg.answer.assert_awaited_once_with(DISABLED_TEXT)
    lookup.assert_called_once_with(101)
    assert clients == []


def test_handler_success_and_telegram_answer_failure_close_client_once():
    provider, _, clients = provider_for({101: "guide-a"})
    configure_guide_shop_provider(provider, reads_enabled=True)

    successful = message(101)
    run(open_guide_shop(successful))
    clients[0].close.assert_awaited_once_with()

    failing = message(101, answer_error=RuntimeError("telegram failure"))
    with pytest.raises(RuntimeError, match="telegram failure"):
        run(open_guide_shop(failing))
    clients[1].close.assert_awaited_once_with()


def test_telegram_edit_failure_closes_client_once():
    provider, _, clients = provider_for({101: "guide-a"})
    configure_guide_shop_provider(provider, reads_enabled=True)
    token = create_navigation_token(101, GuideShopRoute(kind="home"))
    cb = callback(token.raw_token, 101, edit_error=RuntimeError("telegram failure"))
    with pytest.raises(RuntimeError, match="telegram failure"):
        run(navigate_guide_shop(cb))
    clients[0].close.assert_awaited_once_with()


def test_ui_dispatch_failure_closes_client_once():
    provider, _, clients = provider_for(
        {101: "guide-a"}, failure=TypeError("programming")
    )
    configure_guide_shop_provider(provider, reads_enabled=True)
    token = create_navigation_token(101, GuideShopRoute(kind="companies"))
    cb = callback(token.raw_token, 101)
    with pytest.raises(TypeError, match="programming"):
        run(navigate_guide_shop(cb))
    clients[0].close.assert_awaited_once_with()


def test_navigation_failure_after_scope_creation_closes_without_replacement(monkeypatch):
    provider, _, clients = provider_for({101: "trusted-guide"})
    configure_guide_shop_provider(provider, reads_enabled=True)
    resolver = Mock(side_effect=NavigationTokenUnknownError("private route"))
    monkeypatch.setattr(handler_module, "resolve_navigation_token", resolver)
    cb = callback(user_id=101)
    run(navigate_guide_shop(cb))
    resolver.assert_called_once_with("gs_token", 101)
    clients[0].close.assert_awaited_once_with()
    cb.message.edit_text.assert_not_awaited()


@pytest.mark.parametrize(
    "route",
    [
        GuideShopRoute(kind="visits", cursor="untrusted-guide-value"),
        GuideShopRoute(kind="visit_detail", object_id="untrusted-guide-value"),
    ],
)
def test_route_object_and_cursor_cannot_change_factory_identity(route):
    provider, _, clients = provider_for({101: "trusted-guide"})
    configure_guide_shop_provider(provider, reads_enabled=True)
    token = create_navigation_token(101, route)
    cb = callback(token.raw_token, 101)
    with pytest.raises(AssertionError, match="unused"):
        run(navigate_guide_shop(cb))
    assert clients[0].identity == "trusted-guide"


def test_deep_link_payload_cannot_change_factory_identity():
    provider, _, clients = provider_for({101: "trusted-guide"})
    configure_guide_shop_provider(provider, reads_enabled=True)
    token = create_navigation_token(
        101,
        GuideShopRoute(kind="visits", cursor="untrusted-guide-value"),
    )
    msg = message(101)
    with pytest.raises(AssertionError, match="unused"):
        run(open_guide_shop_deep_link(msg, SimpleNamespace(args=token.raw_token)))
    assert clients[0].identity == "trusted-guide"
    clients[0].close.assert_awaited_once_with()
