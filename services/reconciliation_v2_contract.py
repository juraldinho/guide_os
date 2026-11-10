"""Read-only v2 reconciliation contract. Mirrored in Guide OS; no repair DTOs."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

SCHEMA = "reconcile.snapshot.v2"
REPORT_SCHEMA = "reconcile.compare.v2"
IDENTITY = ("source_service", "company_id", "assignment_id", "guide_os_id", "operator_tour_id")
FIELDS = frozenset(
    (
        *IDENTITY,
        "schema_version",
        "guide_connection_id",
        "role",
        "status",
        "projection_mode",
        "active_version_number",
        "pending_critical_version_number",
        "latest_published_version_number",
        "cancelled",
        "cancelled_at",
        "legacy_start_date",
        "legacy_end_date",
        "active_days",
        "projections",
        "state_issues",
        "fingerprint",
    )
)
PROJECTION_FIELDS = frozenset(
    (
        "tour_day_id",
        "date",
        "end_date",
        "projection_tour_id",
        "active_version_number",
        "binding",
        "issues",
    )
)
STATUSES = frozenset(
    ("draft", "offered", "accepted", "active", "declined", "withdrawn", "expired", "cancelled")
)
ISSUES = frozenset(
    (
        "missing_tour",
        "owner_mismatch",
        "binding_mismatch",
        "unlinked",
        "date_mismatch",
        "not_daily",
        "not_protected",
        "group_mismatch",
        "missing_active_version",
        "version_gap",
        "pending_version_missing",
        "malformed_active_scope",
        "unsupported_package",
        "unsupported_mode",
        "scope_state_mismatch",
        "unsupported_remuneration",
    )
)


class SnapshotContractError(ValueError):
    pass


def _uuid(value: Any) -> bool:
    try:
        parsed = UUID(value)
        return parsed.version == 4 and str(parsed) == value
    except (TypeError, ValueError, AttributeError):
        return False


def _date(value: Any) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _number(value: Any, minimum: int = 1) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def fingerprint(snapshot: dict[str, Any]) -> str:
    payload = {key: value for key, value in snapshot.items() if key != "fingerprint"}
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def _projection_key(row: dict[str, Any]) -> tuple[int, str, str]:
    return (
        row["projection_tour_id"],
        row["tour_day_id"] or "",
        json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
    )


def seal(snapshot: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(snapshot)
    result["active_days"].sort(key=lambda row: (row["date"], row["tour_day_id"]))
    # Lists retain duplicates: a duplicate projection must never disappear in a set conversion.
    result["state_issues"] = sorted(set(result["state_issues"]))
    for projection in result["projections"]:
        projection["issues"] = sorted(set(projection["issues"]))
    result["projections"].sort(key=_projection_key)
    result["fingerprint"] = fingerprint(result)
    return validate_snapshot(result)


def validate_snapshot(raw: Any, guide_os_id: str | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != FIELDS or raw.get("schema_version") != SCHEMA:
        raise SnapshotContractError("unsupported_schema")
    if raw["projection_mode"] not in ("legacy_range", "explicit_days"):
        raise SnapshotContractError("unsupported_mode")
    for key in ("assignment_id", "company_id", "guide_connection_id", "role"):
        if not isinstance(raw[key], str) or not 0 < len(raw[key]) <= 128:
            raise SnapshotContractError("malformed_identity")
    if (
        raw["source_service"] != "guide_operator"
        or not _uuid(raw["guide_os_id"])
        or (guide_os_id is not None and raw["guide_os_id"] != guide_os_id)
    ):
        raise SnapshotContractError("identity_mismatch")
    if raw["operator_tour_id"] is not None and not _uuid(raw["operator_tour_id"]):
        raise SnapshotContractError("malformed_identity")
    if (
        not isinstance(raw["status"], str)
        or raw["status"] not in STATUSES
        or raw["cancelled"] is not (raw["status"] == "cancelled")
    ):
        raise SnapshotContractError("malformed_state")
    if raw["cancelled_at"] is not None:
        try:
            if (
                not isinstance(raw["cancelled_at"], str)
                or datetime.fromisoformat(raw["cancelled_at"]).tzinfo is None
            ):
                raise ValueError("timestamp")
        except (TypeError, ValueError) as exc:
            raise SnapshotContractError("malformed_state") from exc
    for key in ("active_version_number", "pending_critical_version_number"):
        if raw[key] is not None and not _number(raw[key]):
            raise SnapshotContractError("malformed_version")
    if not _number(raw["latest_published_version_number"], 0):
        raise SnapshotContractError("malformed_version")
    if not isinstance(raw["state_issues"], list) or any(
        not isinstance(v, str) or v not in ISSUES for v in raw["state_issues"]
    ):
        raise SnapshotContractError("malformed_issues")
    days = raw["active_days"]
    if not isinstance(days, list) or len(days) > 366:
        raise SnapshotContractError("malformed_days")
    for day in days:
        if (
            not isinstance(day, dict)
            or set(day) != {"tour_day_id", "date"}
            or not _uuid(day["tour_day_id"])
            or not _date(day["date"])
        ):
            raise SnapshotContractError("malformed_days")
    if len({d["tour_day_id"] for d in days}) != len(days) or len({d["date"] for d in days}) != len(
        days
    ):
        raise SnapshotContractError("duplicate_days")
    if raw["projection_mode"] == "legacy_range":
        if days or not _date(raw["legacy_start_date"]) or not _date(raw["legacy_end_date"]):
            raise SnapshotContractError("malformed_legacy")
        if raw["legacy_start_date"] > raw["legacy_end_date"]:
            raise SnapshotContractError("malformed_legacy")
    elif (
        raw["legacy_start_date"] is not None
        or raw["legacy_end_date"] is not None
        or raw["operator_tour_id"] is None
    ):
        raise SnapshotContractError("malformed_days")
    if not raw["state_issues"]:
        if (
            raw["projection_mode"] == "explicit_days"
            and raw["active_version_number"] is not None
            and not days
        ):
            raise SnapshotContractError("malformed_days")
        if any(
            raw[key] is not None and raw[key] > raw["latest_published_version_number"]
            for key in ("active_version_number", "pending_critical_version_number")
        ):
            raise SnapshotContractError("malformed_version")
    if raw["cancelled_at"] is not None and not raw["cancelled"]:
        raise SnapshotContractError("malformed_state")
    projections = raw["projections"]
    if not isinstance(projections, list) or len(projections) > 1000:
        raise SnapshotContractError("projection_bound")
    for item in projections:
        if (
            not isinstance(item, dict)
            or set(item) != PROJECTION_FIELDS
            or not _number(item["projection_tour_id"])
        ):
            raise SnapshotContractError("malformed_projection")
        if item["tour_day_id"] is not None and not _uuid(item["tour_day_id"]):
            raise SnapshotContractError("malformed_projection")
        for key in ("date", "end_date"):
            if item[key] is not None and not _date(item[key]):
                raise SnapshotContractError("malformed_projection")
        if item["active_version_number"] is not None and not _number(item["active_version_number"]):
            raise SnapshotContractError("malformed_projection")
        binding = item["binding"]
        if not isinstance(binding, dict) or set(binding) != set(IDENTITY):
            raise SnapshotContractError("malformed_binding")
        if any(
            value is not None and (not isinstance(value, str) or len(value) > 128)
            for value in binding.values()
        ):
            raise SnapshotContractError("malformed_binding")
        if not isinstance(item["issues"], list) or any(
            not isinstance(v, str) or v not in ISSUES for v in item["issues"]
        ):
            raise SnapshotContractError("malformed_issues")
    if (
        days != sorted(days, key=lambda d: (d["date"], d["tour_day_id"]))
        or projections != sorted(projections, key=_projection_key)
        or raw.get("fingerprint") != fingerprint(raw)
    ):
        raise SnapshotContractError("invalid_fingerprint")
    return dict(raw)


def snapshot_base(
    state: dict[str, Any], versions: list[dict[str, Any]], mode: str
) -> dict[str, Any]:
    """Derive scope exclusively from the immutable active snapshot, never proposed rows."""
    issues: list[str] = []
    numbers = sorted(v["version_number"] for v in versions)
    latest = max(numbers, default=0)
    if any(number != index for index, number in enumerate(numbers, 1)):
        issues.append("version_gap")
    active = state.get("active_version_number")
    pending = state.get("pending_critical_version_number")
    version = next((v for v in versions if v["version_number"] == active), None)
    if active is not None and version is None:
        issues.append("missing_active_version")
    if pending is not None and (pending not in numbers or pending <= (active or 0)):
        issues.append("pending_version_missing")
    result = {key: state.get(key) for key in IDENTITY}
    result.update(
        schema_version=SCHEMA,
        guide_connection_id=state["guide_connection_id"],
        role=state["role"],
        status=state["status"],
        projection_mode=mode,
        active_version_number=active,
        pending_critical_version_number=pending,
        latest_published_version_number=latest,
        cancelled=state["status"] == "cancelled",
        cancelled_at=state.get("cancelled_at"),
        legacy_start_date=state["start_date"] if mode == "legacy_range" else None,
        legacy_end_date=state["end_date"] if mode == "legacy_range" else None,
        active_days=[],
        projections=[],
        state_issues=issues,
    )
    if mode == "explicit_days" and version is not None:
        package = version["package"]
        try:
            if (
                not isinstance(package, dict)
                or package.get("schema_version") != "assignment.working_package.v2"
            ):
                raise SnapshotContractError("unsupported_package")
            scope = package["assignment"]
            if scope.get("role") not in {
                "main_guide",
                "accompanying_guide",
                "local_guide",
                "meet_and_greet",
                "other",
            }:
                raise SnapshotContractError("malformed_active_scope")
            if (
                package["tour"]["id"] != state["operator_tour_id"]
                or package["company_id"] != state["company_id"]
                or scope["id"] != state["assignment_id"]
                or scope["guide_os_id"] != state["guide_os_id"]
                or scope["role"] != state["role"]
            ):
                raise SnapshotContractError("scope_state_mismatch")
            if package.get("remuneration") is not None:
                raise SnapshotContractError("unsupported_remuneration")
            days = [
                {"tour_day_id": day["tour_day_id"], "date": day["date"]} for day in package["days"]
            ]
            if (
                not days
                or len(days) > 366
                or any(not _uuid(d["tour_day_id"]) or not _date(d["date"]) for d in days)
                or len({d["tour_day_id"] for d in days}) != len(days)
                or len({d["date"] for d in days}) != len(days)
            ):
                raise SnapshotContractError("malformed_active_scope")
            dates = sorted(d["date"] for d in days)
            if (
                scope["start_date"] != dates[0]
                or scope["end_date"] != dates[-1]
                or state["start_date"] != dates[0]
                or state["end_date"] != dates[-1]
            ):
                raise SnapshotContractError("scope_state_mismatch")
            result["active_days"] = days
        except SnapshotContractError as exc:
            issues.append(str(exc))
        except (KeyError, TypeError, ValueError):
            issues.append("malformed_active_scope")
    if mode == "legacy_range" and version is not None:
        package = version["package"]
        if not isinstance(package, dict) or package.get("schema_version") is not None:
            issues.append("unsupported_package")
    if state["status"] in ("accepted", "active") and active is None:
        issues.append("missing_active_version")
    return result
