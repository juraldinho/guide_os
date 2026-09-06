"""Mini App API transport for Guide Operator assignments (GO6B1).

Delegates to GO6A service. Identity comes only from the validated session.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from aiohttp import web

from database.queries import get_guide_os_id
from services.guide_operator_assignment_service import (
    AssignmentConflictError,
    AssignmentNotActionableError,
    AssignmentNotFoundError,
    AssignmentValidationError,
    CalendarConflictError,
    GuideOperatorAssignmentError,
    accept_assignment,
    acknowledge_ordinary_version,
    build_assignment_detail_for_guide,
    decide_critical_assignment_version,
    decline_assignment,
    list_assignment_lifecycle,
    list_pending_offers,
)
from web_api.auth import read_json_body
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error

_ASSIGNMENT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_DECISION_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_MSG_NOT_FOUND = "Назначение не найдено."
_MSG_NOT_ACTIONABLE = "Предложение больше недоступно для ответа."
_MSG_CONFLICT = "Назначение пересекается с занятыми датами в календаре."
_MSG_CRITICAL_CONFLICT = (
    "Новые даты пересекаются с занятыми датами в календаре."
)
_MSG_CRITICAL_NOT_ACTIONABLE = "Критическая версия больше недоступна для решения."
_MSG_IDEMPOTENCY = "Конфликт идемпотентности запроса."
_MSG_VALIDATION = "Некорректные данные запроса."
_MSG_IDENTITY = "Профиль гида недоступен."


def _assignment_to_api(row: dict[str, Any]) -> dict[str, Any]:
    pending_critical = row.get("pending_critical_version_number")
    return {
        "id": row["assignment_id"],
        "companyId": row["company_id"],
        "companyName": row["company_name"],
        "role": row["role"],
        "startDate": row["start_date"],
        "endDate": row["end_date"],
        "responseDeadline": row.get("response_deadline"),
        "operatorMessage": row.get("operator_message"),
        "status": row["status"],
        "activeVersionNumber": int(row["active_version_number"]),
        "activeVersionUnread": bool(int(row.get("active_version_unread") or 0)),
        "pendingCriticalVersionNumber": (
            int(pending_critical) if pending_critical is not None else None
        ),
        "projectionTourId": (
            str(row["projection_tour_id"])
            if row.get("projection_tour_id") is not None
            else None
        ),
        "offeredAt": row["offered_at"],
        "decidedAt": row.get("decided_at"),
        "cancelledAt": row.get("cancelled_at"),
    }


def _version_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "versionNumber": int(row["version_number"]),
        "severity": row["severity"],
        "publishedAt": row["published_at"],
        "changeSummary": row.get("change_summary") or [],
        "workingPackage": row["working_package"],
        "sourceEventId": row.get("source_event_id"),
    }


def _active_version_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "versionNumber": int(row["version_number"]),
        "severity": row["severity"],
        "publishedAt": row["published_at"],
        "changeSummary": row.get("change_summary") or [],
        "unread": bool(row.get("unread")),
        "sourceEventId": row.get("source_event_id"),
    }


def _decision_to_api(result) -> dict[str, Any]:
    return {
        "assignmentId": result.assignment_id,
        "status": result.status,
        "decision": result.decision,
        "decisionEventId": result.decision_event_id,
        "projectionTourId": (
            str(result.projection_tour_id)
            if result.projection_tour_id is not None
            else None
        ),
        "replayed": bool(result.replayed),
    }


def _version_ack_to_api(result) -> dict[str, Any]:
    return {
        "assignmentId": result.assignment_id,
        "versionNumber": result.version_number,
        "decisionEventId": result.decision_event_id,
        "unread": bool(result.unread),
        "replayed": bool(result.replayed),
    }


def _pending_critical_to_api(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "versionNumber": int(row["version_number"]),
        "severity": row["severity"],
        "publishedAt": row["published_at"],
        "changeSummary": row.get("change_summary") or [],
        "workingPackage": row["working_package"],
        "sourceEventId": row.get("source_event_id"),
        "conflictDates": list(row.get("conflict_dates") or []),
    }


def _critical_decision_to_api(result) -> dict[str, Any]:
    return {
        "assignmentId": result.assignment_id,
        "status": result.status,
        "decision": result.decision,
        "versionNumber": result.version_number,
        "decisionEventId": result.decision_event_id,
        "pendingCriticalVersionNumber": result.pending_critical_version_number,
        "activeVersionNumber": result.active_version_number,
        "projectionTourId": (
            str(result.projection_tour_id)
            if result.projection_tour_id is not None
            else None
        ),
        "replayed": bool(result.replayed),
    }


def _parse_assignment_id(raw: str) -> str | None:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        return None
    if _ASSIGNMENT_ID_RE.fullmatch(raw) is None:
        return None
    return raw


def _parse_decision_event_id(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value or _DECISION_EVENT_ID_RE.fullmatch(value) is None:
        return None
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        return value
    if str(parsed) == value.lower() and parsed.version == 4:
        return value.lower()
    return value


def _session_guide_os_id(
    request: web.Request,
) -> tuple[str, int | None, str | None, web.Response | None]:
    rid, user_id, failure = _auth_or_error(request)
    if failure is not None:
        return rid, None, None, failure
    assert user_id is not None
    guide_os_id = get_guide_os_id(user_id)
    if not guide_os_id:
        return (
            rid,
            user_id,
            None,
            error_response(
                "integration_unavailable",
                _MSG_IDENTITY,
                rid,
                503,
            ),
        )
    return rid, user_id, guide_os_id, None


def _map_service_error(
    exc: GuideOperatorAssignmentError,
    rid: str,
    *,
    critical_decision: bool = False,
) -> web.Response:
    if isinstance(exc, AssignmentNotFoundError):
        return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
    if isinstance(exc, CalendarConflictError):
        return error_response(
            "calendar_conflict",
            _MSG_CRITICAL_CONFLICT if critical_decision else _MSG_CONFLICT,
            rid,
            409,
            details=exc.details,
        )
    if isinstance(exc, AssignmentNotActionableError):
        return error_response(
            "assignment_not_actionable",
            (
                _MSG_CRITICAL_NOT_ACTIONABLE
                if critical_decision
                else _MSG_NOT_ACTIONABLE
            ),
            rid,
            409,
        )
    if isinstance(exc, AssignmentConflictError):
        return error_response(
            "idempotency_conflict",
            _MSG_IDEMPOTENCY,
            rid,
            409,
        )
    if isinstance(exc, AssignmentValidationError):
        code = exc.details.get("code") if isinstance(exc.details, dict) else None
        if code == "integration_unavailable":
            return error_response(
                "integration_unavailable",
                _MSG_IDENTITY,
                rid,
                503,
            )
        return error_response("validation_error", _MSG_VALIDATION, rid, 400)
    return error_response("validation_error", _MSG_VALIDATION, rid, 400)


async def _read_decision_body(
    request: web.Request, rid: str
) -> tuple[str | None, web.Response | None]:
    try:
        data = await read_json_body(request, request.app["max_body_bytes"])
    except (ValueError, TypeError):
        return None, error_response(
            "validation_error",
            _MSG_VALIDATION,
            rid,
            400,
        )
    if not isinstance(data, dict):
        return None, error_response(
            "validation_error",
            _MSG_VALIDATION,
            rid,
            400,
        )
    # Authorization identity is session-only; ignore spoof fields.
    data.pop("guide_os_id", None)
    data.pop("guideOsId", None)
    data.pop("user_id", None)
    data.pop("userId", None)
    data.pop("telegram_id", None)
    data.pop("telegramId", None)

    decision_event_id = _parse_decision_event_id(data.get("decisionEventId"))
    if decision_event_id is None:
        return None, error_response(
            "validation_error",
            "Укажите decisionEventId.",
            rid,
            400,
        )
    return decision_event_id, None


async def _read_version_ack_body(
    request: web.Request, rid: str
) -> tuple[tuple[str, int] | None, web.Response | None]:
    try:
        data = await read_json_body(request, request.app["max_body_bytes"])
    except (ValueError, TypeError):
        return None, error_response(
            "validation_error",
            _MSG_VALIDATION,
            rid,
            400,
        )
    if not isinstance(data, dict):
        return None, error_response(
            "validation_error",
            _MSG_VALIDATION,
            rid,
            400,
        )
    data.pop("guide_os_id", None)
    data.pop("guideOsId", None)
    data.pop("user_id", None)
    data.pop("userId", None)
    data.pop("telegram_id", None)
    data.pop("telegramId", None)

    decision_event_id = _parse_decision_event_id(data.get("decisionEventId"))
    if decision_event_id is None:
        return None, error_response(
            "validation_error",
            "Укажите decisionEventId.",
            rid,
            400,
        )
    version_raw = data.get("versionNumber")
    if not isinstance(version_raw, int) or isinstance(version_raw, bool) or version_raw < 1:
        return None, error_response(
            "validation_error",
            "Укажите versionNumber.",
            rid,
            400,
        )
    return (decision_event_id, version_raw), None


def register_guide_operator_assignment_routes(app: web.Application) -> None:
    async def list_pending_handler(request: web.Request) -> web.Response:
        rid, _user_id, guide_os_id, failure = _session_guide_os_id(request)
        if failure is not None:
            return failure
        assert guide_os_id is not None
        try:
            rows = list_pending_offers(guide_os_id)
        except GuideOperatorAssignmentError as exc:
            return _map_service_error(exc, rid)
        return success_response(
            {"assignments": [_assignment_to_api(row) for row in rows]},
            rid,
        )

    async def list_lifecycle_handler(request: web.Request) -> web.Response:
        rid, _user_id, guide_os_id, failure = _session_guide_os_id(request)
        if failure is not None:
            return failure
        assert guide_os_id is not None
        try:
            buckets = list_assignment_lifecycle(guide_os_id)
        except GuideOperatorAssignmentError as exc:
            return _map_service_error(exc, rid)
        return success_response(
            {
                "asOfDate": buckets["as_of_date"],
                "awaiting": [_assignment_to_api(row) for row in buckets["awaiting"]],
                "upcoming": [_assignment_to_api(row) for row in buckets["upcoming"]],
                "inProgress": [
                    _assignment_to_api(row) for row in buckets["in_progress"]
                ],
                "completed": [
                    _assignment_to_api(row) for row in buckets["completed"]
                ],
                "cancelled": [
                    _assignment_to_api(row) for row in buckets["cancelled"]
                ],
            },
            rid,
        )

    async def get_assignment_handler(request: web.Request) -> web.Response:
        rid, _user_id, guide_os_id, failure = _session_guide_os_id(request)
        if failure is not None:
            return failure
        assert guide_os_id is not None
        assignment_id = _parse_assignment_id(request.match_info["assignmentId"])
        if assignment_id is None:
            return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
        try:
            detail = build_assignment_detail_for_guide(guide_os_id, assignment_id)
        except GuideOperatorAssignmentError as exc:
            return _map_service_error(exc, rid)
        return success_response(
            {
                "assignment": _assignment_to_api(detail["assignment"]),
                "workingPackage": detail["working_package"],
                "conflictDates": detail["conflict_dates"],
                "activeVersion": _active_version_to_api(detail["active_version"]),
                "pendingCriticalVersion": _pending_critical_to_api(
                    detail.get("pending_critical_version")
                ),
                "versions": [
                    _version_to_api(row) for row in detail["versions"]
                ],
            },
            rid,
        )

    async def accept_handler(request: web.Request) -> web.Response:
        rid, _user_id, guide_os_id, failure = _session_guide_os_id(request)
        if failure is not None:
            return failure
        assert guide_os_id is not None
        assignment_id = _parse_assignment_id(request.match_info["assignmentId"])
        if assignment_id is None:
            return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
        decision_event_id, body_error = await _read_decision_body(request, rid)
        if body_error is not None:
            return body_error
        assert decision_event_id is not None
        try:
            result = accept_assignment(
                guide_os_id,
                assignment_id,
                decision_event_id=decision_event_id,
            )
        except GuideOperatorAssignmentError as exc:
            return _map_service_error(exc, rid)
        return success_response(_decision_to_api(result), rid)

    async def decline_handler(request: web.Request) -> web.Response:
        rid, _user_id, guide_os_id, failure = _session_guide_os_id(request)
        if failure is not None:
            return failure
        assert guide_os_id is not None
        assignment_id = _parse_assignment_id(request.match_info["assignmentId"])
        if assignment_id is None:
            return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
        decision_event_id, body_error = await _read_decision_body(request, rid)
        if body_error is not None:
            return body_error
        assert decision_event_id is not None
        try:
            result = decline_assignment(
                guide_os_id,
                assignment_id,
                decision_event_id=decision_event_id,
            )
        except GuideOperatorAssignmentError as exc:
            return _map_service_error(exc, rid)
        return success_response(_decision_to_api(result), rid)

    async def acknowledge_version_handler(request: web.Request) -> web.Response:
        rid, _user_id, guide_os_id, failure = _session_guide_os_id(request)
        if failure is not None:
            return failure
        assert guide_os_id is not None
        assignment_id = _parse_assignment_id(request.match_info["assignmentId"])
        if assignment_id is None:
            return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
        parsed, body_error = await _read_version_ack_body(request, rid)
        if body_error is not None:
            return body_error
        assert parsed is not None
        decision_event_id, version_number = parsed
        try:
            result = acknowledge_ordinary_version(
                guide_os_id,
                assignment_id,
                version_number=version_number,
                decision_event_id=decision_event_id,
            )
        except GuideOperatorAssignmentError as exc:
            return _map_service_error(exc, rid)
        return success_response(_version_ack_to_api(result), rid)

    async def confirm_critical_handler(request: web.Request) -> web.Response:
        rid, _user_id, guide_os_id, failure = _session_guide_os_id(request)
        if failure is not None:
            return failure
        assert guide_os_id is not None
        assignment_id = _parse_assignment_id(request.match_info["assignmentId"])
        if assignment_id is None:
            return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
        parsed, body_error = await _read_version_ack_body(request, rid)
        if body_error is not None:
            return body_error
        assert parsed is not None
        decision_event_id, version_number = parsed
        try:
            result = decide_critical_assignment_version(
                guide_os_id,
                assignment_id,
                version_number=version_number,
                decision="confirm_critical",
                decision_event_id=decision_event_id,
            )
        except GuideOperatorAssignmentError as exc:
            return _map_service_error(exc, rid, critical_decision=True)
        return success_response(_critical_decision_to_api(result), rid)

    async def reject_critical_handler(request: web.Request) -> web.Response:
        rid, _user_id, guide_os_id, failure = _session_guide_os_id(request)
        if failure is not None:
            return failure
        assert guide_os_id is not None
        assignment_id = _parse_assignment_id(request.match_info["assignmentId"])
        if assignment_id is None:
            return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
        parsed, body_error = await _read_version_ack_body(request, rid)
        if body_error is not None:
            return body_error
        assert parsed is not None
        decision_event_id, version_number = parsed
        try:
            result = decide_critical_assignment_version(
                guide_os_id,
                assignment_id,
                version_number=version_number,
                decision="reject_critical",
                decision_event_id=decision_event_id,
            )
        except GuideOperatorAssignmentError as exc:
            return _map_service_error(exc, rid, critical_decision=True)
        return success_response(_critical_decision_to_api(result), rid)

    app.router.add_get(
        "/app/v1/guide-operator/assignments/pending",
        list_pending_handler,
    )
    app.router.add_get(
        "/app/v1/guide-operator/assignments/lists",
        list_lifecycle_handler,
    )
    app.router.add_get(
        "/app/v1/guide-operator/assignments/{assignmentId}",
        get_assignment_handler,
    )
    app.router.add_post(
        "/app/v1/guide-operator/assignments/{assignmentId}/accept",
        accept_handler,
    )
    app.router.add_post(
        "/app/v1/guide-operator/assignments/{assignmentId}/decline",
        decline_handler,
    )
    app.router.add_post(
        "/app/v1/guide-operator/assignments/{assignmentId}/acknowledge-version",
        acknowledge_version_handler,
    )
    app.router.add_post(
        "/app/v1/guide-operator/assignments/{assignmentId}/confirm-critical",
        confirm_critical_handler,
    )
    app.router.add_post(
        "/app/v1/guide-operator/assignments/{assignmentId}/reject-critical",
        reject_critical_handler,
    )
