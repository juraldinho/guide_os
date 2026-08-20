import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.queries import get_active_guide_shop_guide_os_ids
from services.guide_shop_auth import GuideShopJWTEventAccessTokenProvider
from services.guide_shop_event_client import HTTPGuideShopEventFeedClient
from services.guide_shop_event_inbox import GuideShopEventInboxService
from services.guide_shop_event_notifications import (
    GuideShopEventNotificationService,
)
from services.guide_shop_event_pull import (
    EventCheckpointRepository,
    GuideShopEventPullService,
)
from services.guide_shop_settings import (
    GuideShopFeatureFlags,
    GuideShopHTTPSettings,
    GuideShopJWTSigningSettings,
    GuideShopSettingsError,
)


EVENT_PAGE_LIMIT = 20
NOTIFICATION_BATCH_LIMIT = 20
RECOVERY_BATCH_LIMIT = 100
POLL_INTERVAL_SECONDS = 30

logger = logging.getLogger(__name__)


class GuideShopEventRuntimeConfigurationError(GuideShopSettingsError):
    pass


class AiogramGuideShopEventNotificationSender:
    def __init__(self, bot) -> None:
        self._bot = bot

    async def send(self, telegram_user_id: int, text: str, deep_link: str) -> None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Открыть в GuideShop", url=deep_link
                    )
                ]
            ]
        )
        await self._bot.send_message(
            telegram_user_id, text, reply_markup=keyboard
        )


class GuideShopEventWorker:
    def __init__(
        self,
        *,
        http_settings: GuideShopHTTPSettings,
        signing_settings: GuideShopJWTSigningSettings,
        notifications_enabled: bool,
        sender=None,
        bot_username: str | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        identity_loader=get_active_guide_shop_guide_os_ids,
        client_factory=HTTPGuideShopEventFeedClient,
    ) -> None:
        self._http_settings = http_settings
        self._signing_settings = signing_settings
        self._notifications_enabled = notifications_enabled
        self._sender = sender
        self._bot_username = bot_username
        self._clock = clock
        self._sleep = sleep
        self._identity_loader = identity_loader
        self._client_factory = client_factory

    async def run_cycle(self) -> None:
        identities = self._identity_loader()
        for identity in identities:
            client = None
            try:
                token_provider = GuideShopJWTEventAccessTokenProvider(
                    self._signing_settings, clock=self._clock
                )
                client = self._client_factory(
                    self._http_settings, identity, token_provider
                )
                inbox = GuideShopEventInboxService(clock=self._clock)
                puller = GuideShopEventPullService(
                    client=client,
                    inbox=inbox,
                    checkpoint=EventCheckpointRepository(),
                    expected_guide_os_id=identity,
                    clock=self._clock,
                )
                await puller.pull_once(limit=EVENT_PAGE_LIMIT)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("GuideShop event pull failed")
            finally:
                if client is not None:
                    try:
                        await client.close()
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.warning("GuideShop event client cleanup failed")

        if not self._notifications_enabled:
            return
        inbox = GuideShopEventInboxService(clock=self._clock)
        inbox.recover_abandoned(limit=RECOVERY_BATCH_LIMIT, apply=True)
        notifications = GuideShopEventNotificationService(
            inbox=inbox,
            sender=self._sender,
            bot_username=self._bot_username,
            clock=self._clock,
        )
        for _ in range(NOTIFICATION_BATCH_LIMIT):
            try:
                result = await notifications.process_one()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("GuideShop event notification failed")
                continue
            if result.outcome == "idle":
                break

    async def run(self) -> None:
        while True:
            try:
                await self.run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("GuideShop event cycle failed")
            await self._sleep(POLL_INTERVAL_SECONDS)


def validate_guide_shop_event_flags(values=None) -> GuideShopFeatureFlags:
    flags = GuideShopFeatureFlags.from_env(values)
    if flags.notifications_enabled and not flags.events_enabled:
        raise GuideShopEventRuntimeConfigurationError(
            "Invalid GuideShop event runtime configuration"
        )
    return flags


async def build_guide_shop_event_worker(bot, values=None):
    flags = validate_guide_shop_event_flags(values)
    if not flags.events_enabled:
        return None

    http_settings = GuideShopHTTPSettings.from_env(values)
    signing_settings = GuideShopJWTSigningSettings.from_env(values)
    sender = None
    bot_username = None
    if flags.notifications_enabled:
        account = await bot.get_me()
        username = getattr(account, "username", None)
        if (
            not isinstance(username, str)
            or re.fullmatch(r"[A-Za-z0-9_]{5,32}", username) is None
            or not username.casefold().endswith("bot")
        ):
            raise GuideShopEventRuntimeConfigurationError(
                "Invalid GuideShop event runtime configuration"
            )
        bot_username = username
        sender = AiogramGuideShopEventNotificationSender(bot)

    return GuideShopEventWorker(
        http_settings=http_settings,
        signing_settings=signing_settings,
        notifications_enabled=flags.notifications_enabled,
        sender=sender,
        bot_username=bot_username,
    )
