import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from database.queries import get_user_id_by_guide_os_id
from services.guide_shop_event_inbox import GuideShopEventInboxService
from services.guide_shop_navigation import (
    GuideShopRoute,
    build_navigation_deep_link,
    create_navigation_token,
)


_EVENT_PRESENTATION = {
    "visit.created": ("Новый визит в GuideShop.", "visit", "visit_detail"),
    "visit.updated": ("Визит в GuideShop обновлён.", "visit", "visit_detail"),
    "visit.completed": ("Визит в GuideShop завершён.", "visit", "visit_detail"),
    "points.accrual_updated": (
        "Баллы в GuideShop обновлены.",
        "points_accrual",
        "points_detail",
    ),
    "points.credited": (
        "Баллы в GuideShop зачислены.",
        "points_accrual",
        "points_detail",
    ),
}


@runtime_checkable
class GuideShopEventNotificationSender(Protocol):
    async def send(
        self, telegram_user_id: int, text: str, deep_link: str
    ) -> None: ...


@dataclass(frozen=True)
class NotificationProcessingResult:
    outcome: str
    attempted: bool


class GuideShopEventNotificationService:
    def __init__(
        self,
        *,
        inbox: GuideShopEventInboxService,
        sender: GuideShopEventNotificationSender,
        bot_username: str,
        clock,
    ) -> None:
        if not isinstance(inbox, GuideShopEventInboxService):
            raise TypeError("GuideShopEventInboxService required")
        if not isinstance(sender, GuideShopEventNotificationSender):
            raise TypeError("GuideShopEventNotificationSender required")
        if not isinstance(bot_username, str) or not bot_username:
            raise ValueError("bot username required")
        if not callable(clock):
            raise TypeError("UTC clock required")
        self._inbox = inbox
        self._sender = sender
        self._bot_username = bot_username
        self._clock = clock

    async def process_one(self) -> NotificationProcessingResult:
        claim = self._inbox.claim_due()
        if claim is None:
            return NotificationProcessingResult("idle", False)

        event = claim.event
        presentation = _EVENT_PRESENTATION.get(event.event_type)
        if (
            presentation is None
            or event.subject_type != presentation[1]
        ):
            self._inbox.mark_dead_letter(claim)
            return NotificationProcessingResult("dead_letter", False)

        telegram_user_id = get_user_id_by_guide_os_id(event.guide_os_id)
        if telegram_user_id is None:
            failed = self._inbox.mark_failed(claim)
            return NotificationProcessingResult(failed.state, False)

        try:
            route = GuideShopRoute(
                kind=presentation[2], object_id=event.subject_id
            )
            token = create_navigation_token(
                telegram_user_id, route, now=self._clock()
            )
            deep_link = build_navigation_deep_link(
                self._bot_username, token.raw_token
            )
            await self._sender.send(
                telegram_user_id, presentation[0], deep_link
            )
        except asyncio.CancelledError:
            self._inbox.mark_failed(claim)
            raise
        except Exception:
            failed = self._inbox.mark_failed(claim)
            return NotificationProcessingResult(failed.state, True)

        delivered = self._inbox.mark_delivered(claim)
        return NotificationProcessingResult(
            "delivered" if delivered else "superseded", True
        )
