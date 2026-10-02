from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from database.queries import get_third_future_tour_retention_evidence, track_event
from config import TIMEZONE

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
        "next_day_schedule_viewed",
        "availability_date_checked",
        "calendar_month_viewed",
        "expected_income_viewed",
        "tour_detail_viewed",
    }
)

SERVER_MINIAPP_EVENTS = frozenset(
    {
        "miniapp_opened",
        "miniapp_tour_created",
        "miniapp_day_off_created",
        "miniapp_tour_updated",
        "miniapp_entry_deleted",
        "profile_city_submitted",
    }
)

MINIAPP_EVENTS = CLIENT_MINIAPP_EVENTS | SERVER_MINIAPP_EVENTS

CANONICAL_BUSINESS_EVENT_NAMES = {
    "miniapp_tour_created": "tour_created",
    "tour_saved": "tour_created",
    "miniapp_tour_updated": "tour_updated",
    "tour_updated": "tour_updated",
    "miniapp_entry_deleted": "tour_deleted",
    "tour_deleted": "tour_deleted",
    "calendar_month_viewed": "calendar_month_viewed",
    "miniapp_month_picker_opened": "calendar_month_viewed",
    "calendar_month_opened": "calendar_month_viewed",
}


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


def build_third_future_tour_retention_report(
    *, now: datetime | None = None
) -> dict[str, int | float]:
    current = now or datetime.now(ZoneInfo(TIMEZONE))
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo(TIMEZONE))
    cohorts, activities, sessions = get_third_future_tour_retention_evidence(
        current.astimezone(ZoneInfo(TIMEZONE)).date().isoformat()
    )
    evidence: dict[int, list[datetime]] = {}
    for row in [*activities, *sessions]:
        evidence.setdefault(int(row["user_id"]), []).append(
            datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
        )

    w1_users = 0
    w4_users = 0
    for row in cohorts:
        cohort_at = datetime.fromisoformat(str(row["cohort_at"]).replace("Z", "+00:00"))
        later = [value for value in evidence.get(int(row["user_id"]), []) if value > cohort_at]
        if any(value <= cohort_at + timedelta(days=7) for value in later):
            w1_users += 1
        if any(value <= cohort_at + timedelta(days=28) for value in later):
            w4_users += 1

    cohort_users = len(cohorts)
    return {
        "cohortUsers": cohort_users,
        "w1Users": w1_users,
        "w1Rate": round(w1_users / cohort_users, 4) if cohort_users else 0,
        "w4Users": w4_users,
        "w4Rate": round(w4_users / cohort_users, 4) if cohort_users else 0,
    }
