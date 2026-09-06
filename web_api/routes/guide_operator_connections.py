"""Mini App API transport for Guide Operator connections (GO8C3).

Delegates to GO8C2 service. Identity comes only from the validated session.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from aiohttp import web

from database.queries import get_guide_os_id
from services.guide_operator_connection_service import (
    ConnectionConflictError,
    ConnectionNotActionableError,
    ConnectionNotFoundError,
    ConnectionValidationError,
    GuideOperatorConnectionError,
    confirm_connection,
    decline_connection,
    list_connections_for_guide,
)
from web_api.auth import read_json_body
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error

_CONNECTION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_DECISION_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_MSG_NOT_FOUND = "Подключение не найдено."
_MSG_NOT_ACTIONABLE = "Приглашение больше недоступно для ответа."
_MSG_EXPIRED = "Срок приглашения истёк."
_MSG_IDEMPOTENCY = "Конфликт идемпотентности запроса."
_MSG_VALIDATION = "Некорректные данные запроса."
_MSG_IDENTITY = "Профиль гида недоступен."


def _connection_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "companyName": row["companyName"],
        "status": row["status"],
        "invitedAt": row["invitedAt"],
        "invitationExpiresAt": row["invitationExpiresAt"],
        "decidedAt": row.get("decidedAt"),
        "disconnectedAt": row.get("disconnectedAt"),
        "expired": bool(row.get("expired")),
        "actionable": bool(row.get("actionable")),
    }


def _decision_to_api(result) -> dict[str, Any]:
    return {
        "connectionId": result.connection_id,
        "status": result.status,
        "decision": result.decision,
        "decisionEventId": result.decision_event_id,
        "replayed": bool(result.replayed),
    }


def _parse_connection_id(raw: str) -> str | None:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        return None
    if _CONNECTION_ID_RE.fullmatch(raw) is None:
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


def _map_service_error(exc: GuideOperatorConnectionError, rid: str) -> web.Response:
    if isinstance(exc, ConnectionNotFoundError):
        return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
    if isinstance(exc, ConnectionNotActionableError):
        code = exc.details.get("code") if isinstance(exc.details, dict) else None
        if code == "connection_expired":
            return error_response(
                "connection_not_actionable",
                _MSG_EXPIRED,
                rid,
                409,
            )
        return error_response(
            "connection_not_actionable",
            _MSG_NOT_ACTIONABLE,
            rid,
            409,
        )
    if isinstance(exc, ConnectionConflictError):
        return error_response(
            "idempotency_conflict",
            _MSG_IDEMPOTENCY,
            rid,
            409,
        )
    if isinstance(exc, ConnectionValidationError):
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
        body = await read_json_body(request, request.app["max_body_bytes"])
    except (ValueError, TypeError):
        return None, error_response("validation_error", _MSG_VALIDATION, rid, 400)
    if not isinstance(body, dict):
        return None, error_response("validation_error", _MSG_VALIDATION, rid, 400)
    body.pop("guide_os_id", None)
    body.pop("guideOsId", None)
    body.pop("user_id", None)
    body.pop("userId", None)
    body.pop("telegram_id", None)
    body.pop("telegramId", None)
    decision_event_id = _parse_decision_event_id(body.get("decisionEventId"))
    if decision_event_id is None:
        return None, error_response("validation_error", _MSG_VALIDATION, rid, 400)
    return decision_event_id, None


def register_guide_operator_connection_routes(app: web.Application) -> None:
    async def list_connections_handler(request: web.Request) -> web.Response:
        rid, _user_id, guide_os_id, failure = _session_guide_os_id(request)
        if failure is not None:
            return failure
        assert guide_os_id is not None
        try:
            rows = list_connections_for_guide(guide_os_id)
        except GuideOperatorConnectionError as exc:
            return _map_service_error(exc, rid)
        return success_response(
            {"connections": [_connection_to_api(row) for row in rows]},
            rid,
        )

    async def confirm_handler(request: web.Request) -> web.Response:
        rid, _user_id, guide_os_id, failure = _session_guide_os_id(request)
        if failure is not None:
            return failure
        assert guide_os_id is not None
        connection_id = _parse_connection_id(request.match_info.get("connectionId", ""))
        if connection_id is None:
            return error_response("validation_error", _MSG_VALIDATION, rid, 400)
        decision_event_id, body_error = await _read_decision_body(request, rid)
        if body_error is not None:
            return body_error
        assert decision_event_id is not None
        try:
            result = confirm_connection(
                guide_os_id,
                connection_id,
                decision_event_id=decision_event_id,
            )
        except GuideOperatorConnectionError as exc:
            return _map_service_error(exc, rid)
        return success_response(_decision_to_api(result), rid)

    async def decline_handler(request: web.Request) -> web.Response:
        rid, _user_id, guide_os_id, failure = _session_guide_os_id(request)
        if failure is not None:
            return failure
        assert guide_os_id is not None
        connection_id = _parse_connection_id(request.match_info.get("connectionId", ""))
        if connection_id is None:
            return error_response("validation_error", _MSG_VALIDATION, rid, 400)
        decision_event_id, body_error = await _read_decision_body(request, rid)
        if body_error is not None:
            return body_error
        assert decision_event_id is not None
        try:
            result = decline_connection(
                guide_os_id,
                connection_id,
                decision_event_id=decision_event_id,
            )
        except GuideOperatorConnectionError as exc:
            return _map_service_error(exc, rid)
        return success_response(_decision_to_api(result), rid)

    app.router.add_get(
        "/app/v1/guide-operator/connections",
        list_connections_handler,
    )
    app.router.add_post(
        "/app/v1/guide-operator/connections/{connectionId}/confirm",
        confirm_handler,
    )
    app.router.add_post(
        "/app/v1/guide-operator/connections/{connectionId}/decline",
        decline_handler,
    )
