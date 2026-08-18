import re

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from keyboards.guide_shop import build_guide_shop_keyboard
from services.guide_shop_navigation import (
    GuideShopRoute,
    NavigationRouteInvalidError,
    NavigationTokenAccessDeniedError,
    NavigationTokenConsumedError,
    NavigationTokenExpiredError,
    NavigationTokenRevokedError,
    NavigationTokenUnknownError,
    resolve_navigation_token,
)
from services.guide_shop_ui import GuideShopScreen, GuideShopUIService
from services.guide_shop_runtime import (
    GuideShopIdentityUnavailableError,
    GuideShopRuntimeConfigurationError,
    GuideShopUIServiceProvider,
    StaticGuideShopUIServiceProvider,
)


router = Router()

_provider: GuideShopUIServiceProvider | None = None
_reads_enabled = False

DISABLED_TEXT = "Раздел GuideShop временно отключён."
STALE_TOKEN_TEXT = "Кнопка устарела. Откройте GuideShop снова."
ACCESS_DENIED_TEXT = "Эта кнопка недоступна."
INVALID_ROUTE_TEXT = "Не удалось открыть раздел GuideShop."
STALE_LINK_TEXT = "Ссылка устарела. Откройте GuideShop снова."
LINK_ACCESS_DENIED_TEXT = "Эта ссылка недоступна."

_NAVIGATION_TOKEN_PATTERN = r"\Ags_[A-Za-z0-9_-]{32}\Z"


def configure_guide_shop_ui(
    service: GuideShopUIService | None,
    *,
    reads_enabled: bool,
) -> None:
    provider = StaticGuideShopUIServiceProvider(service) if service is not None else None
    configure_guide_shop_provider(provider, reads_enabled=reads_enabled)


def configure_guide_shop_provider(
    provider: GuideShopUIServiceProvider | None,
    *,
    reads_enabled: bool,
) -> None:
    global _provider, _reads_enabled
    _provider = None
    _reads_enabled = False
    if provider is not None:
        try:
            valid_provider = isinstance(provider, GuideShopUIServiceProvider)
        except Exception as exc:
            raise GuideShopRuntimeConfigurationError(
                "GuideShop runtime is not configured"
            ) from exc
        if not valid_provider:
            raise GuideShopRuntimeConfigurationError(
                "GuideShop runtime is not configured"
            )
    _provider = provider
    _reads_enabled = reads_enabled


async def _answer_screen(
    message: Message, telegram_user_id: int, screen: GuideShopScreen
) -> None:
    keyboard = build_guide_shop_keyboard(telegram_user_id, screen.actions)
    await message.answer(
        screen.text,
        parse_mode=screen.parse_mode,
        reply_markup=keyboard,
    )


async def _edit_screen(
    callback: CallbackQuery, telegram_user_id: int, screen: GuideShopScreen
) -> None:
    keyboard = build_guide_shop_keyboard(telegram_user_id, screen.actions)
    await callback.message.edit_text(
        screen.text,
        parse_mode=screen.parse_mode,
        reply_markup=keyboard,
    )


async def _dispatch_route(
    service: GuideShopUIService, route: GuideShopRoute
) -> GuideShopScreen:
    if route.kind == "home":
        return await service.home()
    if route.kind == "companies":
        return await service.companies()
    if route.kind == "company_detail":
        return await service.company_detail(route.object_id)
    if route.kind == "visits":
        return await service.visits(route.cursor)
    if route.kind == "visit_detail":
        return await service.visit_detail(route.object_id)
    if route.kind == "sales":
        return await service.sales(route.cursor)
    if route.kind == "sale_detail":
        return await service.sale_detail(route.object_id)
    if route.kind == "points":
        return await service.points(route.points_status, route.cursor)
    if route.kind == "points_detail":
        return await service.points_detail(route.object_id)
    if route.kind == "history":
        return await service.history(route.cursor)
    raise NavigationRouteInvalidError("Unsupported GuideShop route")


@router.message(
    CommandStart(
        deep_link=True,
        magic=F.args.regexp(_NAVIGATION_TOKEN_PATTERN),
    )
)
async def open_guide_shop_deep_link(
    message: Message,
    command: CommandObject,
) -> None:
    if not _reads_enabled or _provider is None:
        await message.answer(DISABLED_TEXT)
        return

    raw_token = command.args
    if not isinstance(raw_token, str) or re.fullmatch(
        _NAVIGATION_TOKEN_PATTERN, raw_token
    ) is None:
        return

    try:
        async with _provider.service_for(message.from_user.id) as service:
            try:
                route = resolve_navigation_token(raw_token, message.from_user.id)
            except (
                NavigationTokenExpiredError,
                NavigationTokenConsumedError,
                NavigationTokenRevokedError,
                NavigationTokenUnknownError,
            ):
                await message.answer(STALE_LINK_TEXT)
                return
            except NavigationTokenAccessDeniedError:
                await message.answer(LINK_ACCESS_DENIED_TEXT)
                return
            except NavigationRouteInvalidError:
                await message.answer(INVALID_ROUTE_TEXT)
                return

            screen = await _dispatch_route(service, route)
            await _answer_screen(message, message.from_user.id, screen)
    except (GuideShopIdentityUnavailableError, GuideShopRuntimeConfigurationError):
        await message.answer(DISABLED_TEXT)


@router.message(F.text == "🛍 GuideShop")
async def open_guide_shop(message: Message) -> None:
    if not _reads_enabled or _provider is None:
        await message.answer(DISABLED_TEXT)
        return

    try:
        async with _provider.service_for(message.from_user.id) as service:
            screen = await service.home()
            await _answer_screen(message, message.from_user.id, screen)
    except (GuideShopIdentityUnavailableError, GuideShopRuntimeConfigurationError):
        await message.answer(DISABLED_TEXT)


@router.callback_query(F.data.startswith("gs_"))
async def navigate_guide_shop(callback: CallbackQuery) -> None:
    if not _reads_enabled or _provider is None:
        await callback.answer(DISABLED_TEXT)
        return

    try:
        async with _provider.service_for(callback.from_user.id) as service:
            try:
                route = resolve_navigation_token(
                    callback.data,
                    callback.from_user.id,
                )
            except (
                NavigationTokenExpiredError,
                NavigationTokenConsumedError,
                NavigationTokenRevokedError,
                NavigationTokenUnknownError,
            ):
                await callback.answer(STALE_TOKEN_TEXT)
                return
            except NavigationTokenAccessDeniedError:
                await callback.answer(ACCESS_DENIED_TEXT)
                return
            except NavigationRouteInvalidError:
                await callback.answer(INVALID_ROUTE_TEXT)
                return

            screen = await _dispatch_route(service, route)
            await _edit_screen(callback, callback.from_user.id, screen)
            await callback.answer()
    except (GuideShopIdentityUnavailableError, GuideShopRuntimeConfigurationError):
        await callback.answer(DISABLED_TEXT)
