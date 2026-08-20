import asyncio
from dataclasses import dataclass
import logging
import math
import re
import time
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
from services.guide_shop_event_observability import (
    GuideShopEventInboxSnapshot,
    GuideShopEventObservabilityService,
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
MAX_CYCLE_DURATION_MS = 86_400_000

_CYCLE_METRIC_NAMES = (
    "active_identity_count",
    "successful_pull_count",
    "pull_failure_count",
    "client_cleanup_failure_count",
    "fetched_event_count",
    "inserted_event_count",
    "duplicate_event_count",
    "stale_event_count",
    "recovered_pending_count",
    "recovered_dead_letter_count",
    "notification_delivered_count",
    "notification_pending_count",
    "notification_dead_letter_count",
    "notification_superseded_count",
    "notification_processing_failure_count",
    "cycle_duration_ms",
)
_SNAPSHOT_METRIC_NAMES = tuple(
    GuideShopEventInboxSnapshot.__dataclass_fields__
)

logger = logging.getLogger(__name__)


class GuideShopEventRuntimeConfigurationError(GuideShopSettingsError):
    pass


@dataclass(frozen=True)
class GuideShopEventCycleMetrics:
    active_identity_count: int
    successful_pull_count: int
    pull_failure_count: int
    client_cleanup_failure_count: int
    fetched_event_count: int
    inserted_event_count: int
    duplicate_event_count: int
    stale_event_count: int
    recovered_pending_count: int
    recovered_dead_letter_count: int
    notification_delivered_count: int
    notification_pending_count: int
    notification_dead_letter_count: int
    notification_superseded_count: int
    notification_processing_failure_count: int
    cycle_duration_ms: int

    def __post_init__(self) -> None:
        for value in self.__dict__.values():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("invalid event cycle metrics")
        if self.cycle_duration_ms > MAX_CYCLE_DURATION_MS:
            raise ValueError("invalid event cycle metrics")

    def values(self) -> tuple[int, ...]:
        return tuple(self.__dict__.values())


def _duration_ms(started: float, finished: float) -> int:
    duration = (finished - started) * 1000
    if not math.isfinite(duration) or duration < 0:
        return 0
    return min(int(duration), MAX_CYCLE_DURATION_MS)


def _log_cycle_summary(
    metrics: GuideShopEventCycleMetrics,
    snapshot: GuideShopEventInboxSnapshot | None,
) -> None:
    names = _CYCLE_METRIC_NAMES
    values: tuple[int | None, ...] = metrics.values()
    if snapshot is not None:
        names += _SNAPSHOT_METRIC_NAMES
        values += snapshot.values()
    fields = " ".join(f"{name}=%s" for name in names)
    rendered_values = tuple("null" if value is None else value for value in values)
    logger.info("GuideShop event cycle metrics " + fields, *rendered_values)


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
        monotonic: Callable[[], float] = time.monotonic,
        observability_factory=None,
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
        self._monotonic = monotonic
        self._observability_factory = (
            observability_factory or GuideShopEventObservabilityService
        )

    async def run_cycle(self) -> GuideShopEventCycleMetrics:
        started = self._monotonic()
        identities = self._identity_loader()
        successful_pulls = 0
        pull_failures = 0
        cleanup_failures = 0
        fetched = 0
        inserted = 0
        duplicates = 0
        stale = 0
        recovered_pending = 0
        recovered_dead_letter = 0
        notifications_delivered = 0
        notifications_pending = 0
        notifications_dead_letter = 0
        notifications_superseded = 0
        notification_failures = 0
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
                result = await puller.pull_once(limit=EVENT_PAGE_LIMIT)
                successful_pulls += 1
                fetched += result.fetched_count
                inserted += result.inserted_count
                duplicates += result.duplicate_count
                stale += result.stale_count
            except asyncio.CancelledError:
                raise
            except Exception:
                pull_failures += 1
                logger.warning("GuideShop event pull failed")
            finally:
                if client is not None:
                    try:
                        await client.close()
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        cleanup_failures += 1
                        logger.warning("GuideShop event client cleanup failed")

        if self._notifications_enabled:
            inbox = GuideShopEventInboxService(clock=self._clock)
            recovery = inbox.recover_abandoned(
                limit=RECOVERY_BATCH_LIMIT, apply=True
            )
            recovered_pending = recovery.pending_count
            recovered_dead_letter = recovery.dead_letter_count
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
                    notification_failures += 1
                    logger.warning("GuideShop event notification failed")
                    continue
                if result.outcome == "idle":
                    break
                if result.outcome == "delivered":
                    notifications_delivered += 1
                elif result.outcome == "pending":
                    notifications_pending += 1
                elif result.outcome == "dead_letter":
                    notifications_dead_letter += 1
                elif result.outcome == "superseded":
                    notifications_superseded += 1
                else:
                    notification_failures += 1

        snapshot = None
        try:
            snapshot = self._observability_factory(clock=self._clock).snapshot()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("GuideShop event inbox metrics failed")
        metrics = GuideShopEventCycleMetrics(
            active_identity_count=len(identities),
            successful_pull_count=successful_pulls,
            pull_failure_count=pull_failures,
            client_cleanup_failure_count=cleanup_failures,
            fetched_event_count=fetched,
            inserted_event_count=inserted,
            duplicate_event_count=duplicates,
            stale_event_count=stale,
            recovered_pending_count=recovered_pending,
            recovered_dead_letter_count=recovered_dead_letter,
            notification_delivered_count=notifications_delivered,
            notification_pending_count=notifications_pending,
            notification_dead_letter_count=notifications_dead_letter,
            notification_superseded_count=notifications_superseded,
            notification_processing_failure_count=notification_failures,
            cycle_duration_ms=_duration_ms(started, self._monotonic()),
        )
        _log_cycle_summary(metrics, snapshot)
        return metrics

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
