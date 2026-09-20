from __future__ import annotations

import logging

from database.queries import track_event

logger = logging.getLogger(__name__)

CLIENT_MINIAPP_EVENTS = frozenset(
    {
        "miniapp_calendar_opened",
        "miniapp_month_picker_opened",
        "miniapp_day_opened",
        "miniapp_tour_create_started",
        "miniapp_tour_step_dates_completed",
        "miniapp_tour_step_details_completed",
        "miniapp_tour_save_clicked",
        "miniapp_tour_create_cancelled",
        "miniapp_tour_edit_started",
        "miniapp_tour_delete_started",
        "miniapp_reports_opened",
        "miniapp_profile_opened",
        "miniapp_guideshop_opened",
        "miniapp_guide_operator_opened",
    }
)

SERVER_MINIAPP_EVENTS = frozenset(
    {
        "miniapp_opened",
        "miniapp_tour_created",
        "miniapp_day_off_created",
        "miniapp_tour_updated",
        "miniapp_entry_deleted",
    }
)

MINIAPP_EVENTS = CLIENT_MINIAPP_EVENTS | SERVER_MINIAPP_EVENTS


def is_valid_client_miniapp_event(event_name: object) -> bool:
    return isinstance(event_name, str) and event_name in CLIENT_MINIAPP_EVENTS


def track_miniapp_event_safely(user_id: int, event_name: str) -> bool:
    if event_name not in MINIAPP_EVENTS:
        return False
    try:
        track_event(user_id, event_name)
    except Exception:
        logger.warning(
            "Mini App analytics event=%s outcome=write_failed",
            event_name,
        )
        return False
    logger.info("Mini App analytics event=%s outcome=stored", event_name)
    return True
