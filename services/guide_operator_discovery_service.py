"""GO8D2: guide discovery and availability for Guide Operator integration.

Read-only. Uses existing calendar occupancy rules; returns only minimum statuses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from database.queries import get_user_id_by_guide_os_id
from services.availability_service import day_status
from services.tour_service import days_in_range, list_entries
from utils.constants import ENTRY_TYPE_DAY_OFF
from utils.guide_os_identity import GuideOsIdentityError, validate_guide_os_id

AvailabilityStatus = Literal["free", "busy", "partial", "unavailable"]
DayAvailability = Literal["free", "busy", "partial"]

# Inclusive bound for operator assignment window checks (~3 months).
MAX_AVAILABILITY_RANGE_DAYS = 93

_DATE_FMT = "%Y-%m-%d"


class GuideOperatorDiscoveryError(Exception):
    """Base error for discovery/availability domain failures."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class GuideOperatorDiscoveryValidationError(GuideOperatorDiscoveryError):
    code = "validation_error"


class GuideOperatorDiscoveryNotFoundError(GuideOperatorDiscoveryError):
    code = "not_found"


def _parse_iso_date(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GuideOperatorDiscoveryValidationError(f"{field} is required.")
    text = value.strip()
    try:
        parsed = datetime.strptime(text, _DATE_FMT).date()
    except ValueError as exc:
        raise GuideOperatorDiscoveryValidationError(
            f"{field} must be YYYY-MM-DD."
        ) from exc
    if parsed.strftime(_DATE_FMT) != text:
        raise GuideOperatorDiscoveryValidationError(
            f"{field} must be YYYY-MM-DD."
        )
    return text


def _is_full_day_occupancy(entry: dict[str, Any]) -> bool:
    """Match tour_service full-day occupancy: day_off or missing time pair."""
    if entry.get("type") == ENTRY_TYPE_DAY_OFF:
        return True
    return not entry.get("start_time") or not entry.get("end_time")


def classify_day_availability(
    date_text: str, entries: list[dict[str, Any]]
) -> DayAvailability:
    """Map one calendar day to free | busy | partial using shared day_status."""
    status = day_status(date_text, entries)
    if status == "free":
        return "free"
    if status == "dayoff":
        return "busy"

    day_entries = [
        entry
        for entry in entries
        if entry["start_date"] <= date_text <= entry["end_date"]
    ]
    tours = [entry for entry in day_entries if entry.get("type") != ENTRY_TYPE_DAY_OFF]
    if not tours:
        return "free"
    if any(_is_full_day_occupancy(entry) for entry in tours):
        return "busy"
    if all(entry.get("start_time") and entry.get("end_time") for entry in tours):
        return "partial"
    return "busy"


def aggregate_range_availability(
    day_statuses: list[DayAvailability],
) -> AvailabilityStatus:
    if not day_statuses:
        return "unavailable"
    unique = set(day_statuses)
    if unique == {"free"}:
        return "free"
    if unique == {"busy"}:
        return "busy"
    return "partial"


def discover_guide_for_operator(guide_os_id: object) -> dict[str, Any]:
    """Return minimum discovery payload if the guide can receive invitations."""
    try:
        identity = validate_guide_os_id(guide_os_id)
    except GuideOsIdentityError as exc:
        raise GuideOperatorDiscoveryValidationError(
            "guide_os_id must be a canonical UUIDv4."
        ) from exc
    if get_user_id_by_guide_os_id(identity) is None:
        raise GuideOperatorDiscoveryNotFoundError("Guide was not found.")
    return {
        "guide_os_id": identity,
        "can_receive_invitation": True,
    }


def guide_availability_for_operator(
    guide_os_id: object,
    start_date: object,
    end_date: object,
) -> dict[str, Any]:
    """Return bound availability status for an inclusive date range."""
    try:
        identity = validate_guide_os_id(guide_os_id)
    except GuideOsIdentityError as exc:
        raise GuideOperatorDiscoveryValidationError(
            "guide_os_id must be a canonical UUIDv4."
        ) from exc

    start = _parse_iso_date(start_date, "start_date")
    end = _parse_iso_date(end_date, "end_date")
    if start > end:
        raise GuideOperatorDiscoveryValidationError(
            "start_date must not be after end_date."
        )
    day_count = len(days_in_range(start, end))
    if day_count > MAX_AVAILABILITY_RANGE_DAYS:
        raise GuideOperatorDiscoveryValidationError(
            "Date range exceeds the maximum allowed length.",
            details={"code": "range_too_large"},
        )

    user_id = get_user_id_by_guide_os_id(identity)
    if user_id is None:
        return {
            "guide_os_id": identity,
            "start_date": start,
            "end_date": end,
            "status": "unavailable",
        }

    entries = list_entries(user_id, start, end)
    day_statuses = [
        classify_day_availability(day, entries) for day in days_in_range(start, end)
    ]
    return {
        "guide_os_id": identity,
        "start_date": start,
        "end_date": end,
        "status": aggregate_range_availability(day_statuses),
    }
