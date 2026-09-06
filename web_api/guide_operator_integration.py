"""Authenticated Guide Operator → Guide OS inbound HTTP surface (GO8D1/GO8D2/GO11A).

API-only: no Telegram polling, no Mini App session routes.
GO8D1 event intake + GO8D2 discovery/availability reads + GO11A read-only reconcile.
Delegates to GO8B JWT auth and existing GO domain services.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from aiohttp import web

from database.queries import (
    get_guide_operator_cancellation_inbox,
    get_guide_operator_connection_inbox,
    get_guide_operator_offer_inbox,
    get_guide_operator_version_inbox,
)
from services.guide_operator_assignment_service import (
    AssignmentCancellationIntake,
    AssignmentConflictError,
    AssignmentNotActionableError,
    AssignmentNotFoundError,
    AssignmentOfferIntake,
    AssignmentValidationError,
    AssignmentVersionPublishedIntake,
    CalendarConflictError,
    GuideOperatorAssignmentError,
    apply_assignment_cancellation,
    apply_ordinary_assignment_version,
    intake_critical_assignment_version,
    receive_assignment_offer,
)
from services.guide_operator_connection_service import (
    ConnectionConflictError,
    ConnectionDisconnectIntake,
    ConnectionInvitationIntake,
    ConnectionNotActionableError,
    ConnectionNotFoundError,
    ConnectionValidationError,
    GuideOperatorConnectionError,
    receive_connection_disconnect,
    receive_connection_invitation,
)
from services.guide_operator_discovery_service import (
    GuideOperatorDiscoveryNotFoundError,
    GuideOperatorDiscoveryValidationError,
    discover_guide_for_operator,
    guide_availability_for_operator,
)
from services.guide_operator_reconcile_service import (
    GuideOperatorReconcileNotFoundError,
    GuideOperatorReconcileValidationError,
    get_local_assignment,
    get_local_connection,
    list_local_assignments,
    list_local_connections,
)
from services.guide_operator_service_auth_settings import (
    GuideOperatorServiceAuthConfigurationError,
    GuideOperatorServiceAuthSettings,
    load_guide_operator_service_auth_settings,
)
from services.guide_operator_service_jwt import (
    SCOPE_AVAILABILITY_READ,
    SCOPE_CANCELLATIONS_WRITE,
    SCOPE_CONNECTIONS_WRITE,
    SCOPE_OFFERS_WRITE,
    SCOPE_OPERATOR_RECONCILE,
    SCOPE_VERSIONS_WRITE,
    GuideOperatorServiceAuthenticationError,
    authenticate_guide_operator_service_jwt,
)
from web_api.errors import error_response, success_response

logger = logging.getLogger("guide_os.guide_operator_integration")

MAX_REQUEST_BODY_BYTES = 256 * 1024
_ENVELOPE_KEYS = frozenset({"event_id", "event_type", "occurred_at", "payload"})
_PATH_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

EVENT_CONNECTION_INVITED = "guide_connection.invited.v1"
EVENT_CONNECTION_DISCONNECTED = "guide_connection.disconnected.v1"
EVENT_ASSIGNMENT_OFFERED = "assignment.offered.v1"
EVENT_VERSION_PUBLISHED = "assignment.version.published.v1"
EVENT_ASSIGNMENT_CANCELLED = "assignment.cancelled.v1"

_MSG_AUTH = "Authentication failed"
_MSG_AUTH_UNAVAILABLE = "Service authentication is unavailable"
_MSG_INVALID = "Invalid request"
_MSG_CONFLICT = "Event conflict"
_MSG_NOT_FOUND = "Entity not found"
_MSG_NOT_ACTIONABLE = "Event is not actionable"
_MSG_VALIDATION = "Invalid event payload"
_MSG_DISCOVERY = "Invalid discovery request"
_MSG_AVAILABILITY = "Invalid availability request"
_MSG_RECONCILE = "Invalid reconciliation request"
_DISCOVERY_BODY_KEYS = frozenset({"guide_os_id"})
_AVAILABILITY_BODY_KEYS = frozenset({"start_date", "end_date"})


def _opaque_log(message: str) -> None:
    logger.warning(message)


def _parse_uuid4(value: object) -> str | None:
    if not isinstance(value, str) or value != value.lower():
        return None
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None
    if parsed.version != 4 or str(parsed) != value:
        return None
    return value


def _parse_path_id(raw: str) -> str | None:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        return None
    if _PATH_ID_RE.fullmatch(raw) is None:
        return None
    return raw


def _require_iso_datetime(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return text


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate json key")
        result[key] = value
    return result


async def _read_envelope(request: web.Request) -> dict[str, Any]:
    if request.content_type != "application/json":
        raise ValueError("content type")
    body = await request.read()
    if len(body) > MAX_REQUEST_BODY_BYTES:
        raise ValueError("body too large")
    data = json.loads(body, object_pairs_hook=_unique_object)
    if not isinstance(data, dict) or set(data) != _ENVELOPE_KEYS:
        raise ValueError("envelope keys")
    event_id = _parse_uuid4(data.get("event_id"))
    event_type = data.get("event_type")
    occurred_at = _require_iso_datetime(data.get("occurred_at"))
    payload = data.get("payload")
    if (
        event_id is None
        or not isinstance(event_type, str)
        or not event_type
        or occurred_at is None
        or not isinstance(payload, dict)
    ):
        raise ValueError("envelope fields")
    return {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "payload": payload,
    }


async def _read_json_object(
    request: web.Request, *, allowed_keys: frozenset[str]
) -> dict[str, Any]:
    if request.content_type != "application/json":
        raise ValueError("content type")
    body = await request.read()
    if len(body) > MAX_REQUEST_BODY_BYTES:
        raise ValueError("body too large")
    data = json.loads(body, object_pairs_hook=_unique_object)
    if not isinstance(data, dict) or set(data) != allowed_keys:
        raise ValueError("json keys")
    return data


def _auth_or_error(
    request: web.Request,
    *,
    expected_scope: str,
    rid: str,
    auth_settings: GuideOperatorServiceAuthSettings,
    clock: Callable[[], datetime] | None,
) -> web.Response | None:
    if not auth_settings.enabled or auth_settings.inbound is None:
        _opaque_log("Service authentication unavailable")
        return error_response(
            "service_authentication_unavailable",
            _MSG_AUTH_UNAVAILABLE,
            rid,
            503,
        )
    values = request.headers.getall("Authorization", [])
    if len(values) != 1 or not values[0].startswith("Bearer "):
        _opaque_log("Service authentication failed")
        return error_response("unauthenticated", _MSG_AUTH, rid, 401)
    token = values[0][7:]
    if not token or token != token.strip() or any(c.isspace() for c in token):
        _opaque_log("Service authentication failed")
        return error_response("unauthenticated", _MSG_AUTH, rid, 401)
    try:
        authenticate_guide_operator_service_jwt(
            token,
            expected_scope,
            auth_settings.inbound,
            clock=clock,
        )
    except GuideOperatorServiceAuthenticationError:
        return error_response("unauthenticated", _MSG_AUTH, rid, 401)
    return None


def _map_connection_error(exc: GuideOperatorConnectionError, rid: str) -> web.Response:
    if isinstance(exc, ConnectionNotFoundError):
        return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
    if isinstance(exc, ConnectionConflictError):
        return error_response("idempotency_conflict", _MSG_CONFLICT, rid, 409)
    if isinstance(exc, ConnectionNotActionableError):
        return error_response("not_actionable", _MSG_NOT_ACTIONABLE, rid, 409)
    if isinstance(exc, ConnectionValidationError):
        code = exc.details.get("code") if isinstance(exc.details, dict) else None
        if code == "integration_unavailable":
            return error_response(
                "integration_unavailable",
                _MSG_VALIDATION,
                rid,
                503,
            )
        return error_response("validation_error", _MSG_VALIDATION, rid, 400)
    return error_response("validation_error", _MSG_VALIDATION, rid, 400)


def _map_assignment_error(exc: GuideOperatorAssignmentError, rid: str) -> web.Response:
    if isinstance(exc, AssignmentNotFoundError):
        return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
    if isinstance(exc, CalendarConflictError):
        return error_response("calendar_conflict", _MSG_CONFLICT, rid, 409)
    if isinstance(exc, AssignmentConflictError):
        return error_response("idempotency_conflict", _MSG_CONFLICT, rid, 409)
    if isinstance(exc, AssignmentNotActionableError):
        return error_response("not_actionable", _MSG_NOT_ACTIONABLE, rid, 409)
    if isinstance(exc, AssignmentValidationError):
        code = exc.details.get("code") if isinstance(exc.details, dict) else None
        if code == "integration_unavailable":
            return error_response(
                "integration_unavailable",
                _MSG_VALIDATION,
                rid,
                503,
            )
        return error_response("validation_error", _MSG_VALIDATION, rid, 400)
    return error_response("validation_error", _MSG_VALIDATION, rid, 400)


def _applied_response(
    *,
    rid: str,
    event_id: str,
    event_type: str,
    replayed: bool,
) -> web.Response:
    return success_response(
        {
            "status": "replayed" if replayed else "applied",
            "eventId": event_id,
            "eventType": event_type,
            "replayed": replayed,
        },
        rid,
    )


def create_guide_operator_integration_app(
    *,
    auth_settings: GuideOperatorServiceAuthSettings | None = None,
    clock: Callable[[], datetime] | None = None,
    random_bytes=secrets.token_bytes,
) -> web.Application:
    """Build the Guide Operator inbound event aiohttp application."""

    app = web.Application(client_max_size=MAX_REQUEST_BODY_BYTES)
    resolved_auth = auth_settings
    if resolved_auth is None:
        try:
            resolved_auth = load_guide_operator_service_auth_settings()
        except GuideOperatorServiceAuthConfigurationError:
            resolved_auth = GuideOperatorServiceAuthSettings.disabled()

    app["go_integration_auth_settings"] = resolved_auth
    app["go_integration_clock"] = clock
    app["go_integration_random_bytes"] = random_bytes

    def make_request_id(request: web.Request) -> str:
        values = request.headers.getall("X-Request-Id", [])
        if values:
            value = values[0].strip()
            if 8 <= len(value) <= 128:
                return value
        return "req_" + random_bytes(16).hex()

    async def _prepare(
        request: web.Request, *, expected_scope: str
    ) -> tuple[str, web.Response | None]:
        rid = make_request_id(request)
        auth = request.app["go_integration_auth_settings"]
        failure = _auth_or_error(
            request,
            expected_scope=expected_scope,
            rid=rid,
            auth_settings=auth,
            clock=request.app["go_integration_clock"],
        )
        return rid, failure

    async def invited_handler(request: web.Request) -> web.Response:
        rid, failure = await _prepare(request, expected_scope=SCOPE_CONNECTIONS_WRITE)
        if failure is not None:
            return failure
        connection_id = _parse_path_id(request.match_info.get("connectionId", ""))
        if connection_id is None:
            return error_response("validation_error", _MSG_INVALID, rid, 400)
        try:
            envelope = await _read_envelope(request)
        except (ValueError, UnicodeError, json.JSONDecodeError, web.HTTPRequestEntityTooLarge):
            return error_response("invalid_request", _MSG_INVALID, rid, 400)
        if envelope["event_type"] != EVENT_CONNECTION_INVITED:
            return error_response("invalid_request", _MSG_INVALID, rid, 400)
        payload = envelope["payload"]
        if payload.get("connection_id") != connection_id:
            return error_response("validation_error", _MSG_INVALID, rid, 400)
        prior = get_guide_operator_connection_inbox(envelope["event_id"])
        try:
            receive_connection_invitation(
                ConnectionInvitationIntake(
                    event_id=envelope["event_id"],
                    connection_id=connection_id,
                    company_id=payload.get("company_id"),
                    company_name=payload.get("company_name"),
                    guide_os_id=payload.get("guide_os_id"),
                    invitation_expires_at=payload.get("invitation_expires_at"),
                    invited_at=payload.get("invited_at") or envelope["occurred_at"],
                )
            )
        except GuideOperatorConnectionError as exc:
            return _map_connection_error(exc, rid)
        except TypeError:
            return error_response("validation_error", _MSG_VALIDATION, rid, 400)
        return _applied_response(
            rid=rid,
            event_id=envelope["event_id"],
            event_type=envelope["event_type"],
            replayed=prior is not None,
        )

    async def disconnected_handler(request: web.Request) -> web.Response:
        rid, failure = await _prepare(request, expected_scope=SCOPE_CONNECTIONS_WRITE)
        if failure is not None:
            return failure
        connection_id = _parse_path_id(request.match_info.get("connectionId", ""))
        if connection_id is None:
            return error_response("validation_error", _MSG_INVALID, rid, 400)
        try:
            envelope = await _read_envelope(request)
        except (ValueError, UnicodeError, json.JSONDecodeError, web.HTTPRequestEntityTooLarge):
            return error_response("invalid_request", _MSG_INVALID, rid, 400)
        if envelope["event_type"] != EVENT_CONNECTION_DISCONNECTED:
            return error_response("invalid_request", _MSG_INVALID, rid, 400)
        payload = envelope["payload"]
        if payload.get("connection_id") != connection_id:
            return error_response("validation_error", _MSG_INVALID, rid, 400)
        prior = get_guide_operator_connection_inbox(envelope["event_id"])
        try:
            receive_connection_disconnect(
                ConnectionDisconnectIntake(
                    event_id=envelope["event_id"],
                    connection_id=connection_id,
                    company_id=payload.get("company_id"),
                    company_name=payload.get("company_name"),
                    guide_os_id=payload.get("guide_os_id"),
                    disconnected_at=payload.get("disconnected_at")
                    or envelope["occurred_at"],
                )
            )
        except GuideOperatorConnectionError as exc:
            return _map_connection_error(exc, rid)
        except TypeError:
            return error_response("validation_error", _MSG_VALIDATION, rid, 400)
        return _applied_response(
            rid=rid,
            event_id=envelope["event_id"],
            event_type=envelope["event_type"],
            replayed=prior is not None,
        )

    async def offered_handler(request: web.Request) -> web.Response:
        rid, failure = await _prepare(request, expected_scope=SCOPE_OFFERS_WRITE)
        if failure is not None:
            return failure
        assignment_id = _parse_path_id(request.match_info.get("assignmentId", ""))
        if assignment_id is None:
            return error_response("validation_error", _MSG_INVALID, rid, 400)
        try:
            envelope = await _read_envelope(request)
        except (ValueError, UnicodeError, json.JSONDecodeError, web.HTTPRequestEntityTooLarge):
            return error_response("invalid_request", _MSG_INVALID, rid, 400)
        if envelope["event_type"] != EVENT_ASSIGNMENT_OFFERED:
            return error_response("invalid_request", _MSG_INVALID, rid, 400)
        payload = envelope["payload"]
        if payload.get("assignment_id") != assignment_id:
            return error_response("validation_error", _MSG_INVALID, rid, 400)
        prior = get_guide_operator_offer_inbox(envelope["event_id"])
        try:
            receive_assignment_offer(
                AssignmentOfferIntake(
                    event_id=envelope["event_id"],
                    assignment_id=assignment_id,
                    guide_os_id=payload.get("guide_os_id"),
                    company_id=payload.get("company_id"),
                    company_name=payload.get("company_name"),
                    guide_connection_id=payload.get("guide_connection_id"),
                    role=payload.get("role"),
                    start_date=payload.get("start_date"),
                    end_date=payload.get("end_date"),
                    working_package=payload.get("working_package") or {},
                    version_number=payload.get("version_number", 1),
                    response_deadline=payload.get("response_deadline"),
                    operator_message=payload.get("operator_message"),
                    offered_at=payload.get("offered_at") or envelope["occurred_at"],
                )
            )
        except GuideOperatorAssignmentError as exc:
            return _map_assignment_error(exc, rid)
        except TypeError:
            return error_response("validation_error", _MSG_VALIDATION, rid, 400)
        return _applied_response(
            rid=rid,
            event_id=envelope["event_id"],
            event_type=envelope["event_type"],
            replayed=prior is not None,
        )

    async def version_handler(request: web.Request) -> web.Response:
        rid, failure = await _prepare(request, expected_scope=SCOPE_VERSIONS_WRITE)
        if failure is not None:
            return failure
        assignment_id = _parse_path_id(request.match_info.get("assignmentId", ""))
        if assignment_id is None:
            return error_response("validation_error", _MSG_INVALID, rid, 400)
        try:
            envelope = await _read_envelope(request)
        except (ValueError, UnicodeError, json.JSONDecodeError, web.HTTPRequestEntityTooLarge):
            return error_response("invalid_request", _MSG_INVALID, rid, 400)
        if envelope["event_type"] != EVENT_VERSION_PUBLISHED:
            return error_response("invalid_request", _MSG_INVALID, rid, 400)
        payload = envelope["payload"]
        if payload.get("assignment_id") != assignment_id:
            return error_response("validation_error", _MSG_INVALID, rid, 400)
        severity = payload.get("severity")
        if severity not in {"ordinary", "critical"}:
            return error_response("validation_error", _MSG_VALIDATION, rid, 400)
        prior = get_guide_operator_version_inbox(envelope["event_id"])
        intake = AssignmentVersionPublishedIntake(
            event_id=envelope["event_id"],
            assignment_id=assignment_id,
            guide_os_id=payload.get("guide_os_id"),
            version_number=payload.get("version_number"),
            previous_active_version_number=payload.get(
                "previous_active_version_number"
            ),
            severity=severity,
            working_package=payload.get("working_package") or {},
            change_summary=payload.get("change_summary") or [],
            published_at=payload.get("published_at") or envelope["occurred_at"],
        )
        try:
            if severity == "ordinary":
                apply_ordinary_assignment_version(intake)
            else:
                intake_critical_assignment_version(intake)
        except GuideOperatorAssignmentError as exc:
            return _map_assignment_error(exc, rid)
        except TypeError:
            return error_response("validation_error", _MSG_VALIDATION, rid, 400)
        return _applied_response(
            rid=rid,
            event_id=envelope["event_id"],
            event_type=envelope["event_type"],
            replayed=prior is not None,
        )

    async def cancelled_handler(request: web.Request) -> web.Response:
        rid, failure = await _prepare(request, expected_scope=SCOPE_CANCELLATIONS_WRITE)
        if failure is not None:
            return failure
        assignment_id = _parse_path_id(request.match_info.get("assignmentId", ""))
        if assignment_id is None:
            return error_response("validation_error", _MSG_INVALID, rid, 400)
        try:
            envelope = await _read_envelope(request)
        except (ValueError, UnicodeError, json.JSONDecodeError, web.HTTPRequestEntityTooLarge):
            return error_response("invalid_request", _MSG_INVALID, rid, 400)
        if envelope["event_type"] != EVENT_ASSIGNMENT_CANCELLED:
            return error_response("invalid_request", _MSG_INVALID, rid, 400)
        payload = envelope["payload"]
        if payload.get("assignment_id") != assignment_id:
            return error_response("validation_error", _MSG_INVALID, rid, 400)
        prior = get_guide_operator_cancellation_inbox(envelope["event_id"])
        try:
            apply_assignment_cancellation(
                AssignmentCancellationIntake(
                    event_id=envelope["event_id"],
                    assignment_id=assignment_id,
                    guide_os_id=payload.get("guide_os_id"),
                    version_number=payload.get("version_number"),
                    cancelled_at=payload.get("cancelled_at") or envelope["occurred_at"],
                )
            )
        except GuideOperatorAssignmentError as exc:
            return _map_assignment_error(exc, rid)
        except TypeError:
            return error_response("validation_error", _MSG_VALIDATION, rid, 400)
        return _applied_response(
            rid=rid,
            event_id=envelope["event_id"],
            event_type=envelope["event_type"],
            replayed=prior is not None,
        )

    async def discovery_handler(request: web.Request) -> web.Response:
        rid, failure = await _prepare(request, expected_scope=SCOPE_CONNECTIONS_WRITE)
        if failure is not None:
            return failure
        try:
            body = await _read_json_object(
                request, allowed_keys=_DISCOVERY_BODY_KEYS
            )
        except (ValueError, UnicodeError, json.JSONDecodeError, web.HTTPRequestEntityTooLarge):
            return error_response("invalid_request", _MSG_DISCOVERY, rid, 400)
        try:
            result = discover_guide_for_operator(body.get("guide_os_id"))
        except GuideOperatorDiscoveryValidationError:
            return error_response("validation_error", _MSG_DISCOVERY, rid, 400)
        except GuideOperatorDiscoveryNotFoundError:
            return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
        return success_response(
            {
                "guideOsId": result["guide_os_id"],
                "canReceiveInvitation": result["can_receive_invitation"],
            },
            rid,
        )

    async def availability_handler(request: web.Request) -> web.Response:
        rid, failure = await _prepare(request, expected_scope=SCOPE_AVAILABILITY_READ)
        if failure is not None:
            return failure
        guide_os_id = _parse_uuid4(request.match_info.get("guideOsId", ""))
        if guide_os_id is None:
            return error_response("validation_error", _MSG_AVAILABILITY, rid, 400)
        try:
            body = await _read_json_object(
                request, allowed_keys=_AVAILABILITY_BODY_KEYS
            )
        except (ValueError, UnicodeError, json.JSONDecodeError, web.HTTPRequestEntityTooLarge):
            return error_response("invalid_request", _MSG_AVAILABILITY, rid, 400)
        try:
            result = guide_availability_for_operator(
                guide_os_id,
                body.get("start_date"),
                body.get("end_date"),
            )
        except GuideOperatorDiscoveryValidationError:
            return error_response("validation_error", _MSG_AVAILABILITY, rid, 400)
        return success_response(
            {
                "guideOsId": result["guide_os_id"],
                "startDate": result["start_date"],
                "endDate": result["end_date"],
                "status": result["status"],
            },
            rid,
        )

    def _reconcile_query_ids(request: web.Request) -> list[str] | None:
        values = request.rel_url.query.getall("ids", [])
        if not values:
            return None
        return values

    async def reconcile_connections_handler(request: web.Request) -> web.Response:
        rid, failure = await _prepare(request, expected_scope=SCOPE_OPERATOR_RECONCILE)
        if failure is not None:
            return failure
        guide_os_id = _parse_uuid4(request.match_info.get("guideOsId", ""))
        if guide_os_id is None:
            return error_response("validation_error", _MSG_RECONCILE, rid, 400)
        try:
            payload = list_local_connections(
                guide_os_id,
                limit=request.rel_url.query.get("limit"),
                cursor=request.rel_url.query.get("cursor"),
                ids=_reconcile_query_ids(request),
            )
        except GuideOperatorReconcileValidationError:
            return error_response("validation_error", _MSG_RECONCILE, rid, 400)
        return success_response(payload, rid)

    async def reconcile_connection_handler(request: web.Request) -> web.Response:
        rid, failure = await _prepare(request, expected_scope=SCOPE_OPERATOR_RECONCILE)
        if failure is not None:
            return failure
        guide_os_id = _parse_uuid4(request.match_info.get("guideOsId", ""))
        connection_id = _parse_path_id(request.match_info.get("connectionId", ""))
        if guide_os_id is None or connection_id is None:
            return error_response("validation_error", _MSG_RECONCILE, rid, 400)
        try:
            payload = get_local_connection(guide_os_id, connection_id)
        except GuideOperatorReconcileValidationError:
            return error_response("validation_error", _MSG_RECONCILE, rid, 400)
        except GuideOperatorReconcileNotFoundError:
            return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
        return success_response(payload, rid)

    async def reconcile_assignments_handler(request: web.Request) -> web.Response:
        rid, failure = await _prepare(request, expected_scope=SCOPE_OPERATOR_RECONCILE)
        if failure is not None:
            return failure
        guide_os_id = _parse_uuid4(request.match_info.get("guideOsId", ""))
        if guide_os_id is None:
            return error_response("validation_error", _MSG_RECONCILE, rid, 400)
        try:
            payload = list_local_assignments(
                guide_os_id,
                limit=request.rel_url.query.get("limit"),
                cursor=request.rel_url.query.get("cursor"),
                ids=_reconcile_query_ids(request),
            )
        except GuideOperatorReconcileValidationError:
            return error_response("validation_error", _MSG_RECONCILE, rid, 400)
        return success_response(payload, rid)

    async def reconcile_assignment_handler(request: web.Request) -> web.Response:
        rid, failure = await _prepare(request, expected_scope=SCOPE_OPERATOR_RECONCILE)
        if failure is not None:
            return failure
        guide_os_id = _parse_uuid4(request.match_info.get("guideOsId", ""))
        assignment_id = _parse_path_id(request.match_info.get("assignmentId", ""))
        if guide_os_id is None or assignment_id is None:
            return error_response("validation_error", _MSG_RECONCILE, rid, 400)
        try:
            payload = get_local_assignment(guide_os_id, assignment_id)
        except GuideOperatorReconcileValidationError:
            return error_response("validation_error", _MSG_RECONCILE, rid, 400)
        except GuideOperatorReconcileNotFoundError:
            return error_response("not_found", _MSG_NOT_FOUND, rid, 404)
        return success_response(payload, rid)

    app.router.add_post(
        "/integration/v1/guide-connections/{connectionId}/invited",
        invited_handler,
    )
    app.router.add_post(
        "/integration/v1/guide-connections/{connectionId}/disconnected",
        disconnected_handler,
    )
    app.router.add_post(
        "/integration/v1/assignments/{assignmentId}/offered",
        offered_handler,
    )
    app.router.add_post(
        "/integration/v1/assignments/{assignmentId}/versions",
        version_handler,
    )
    app.router.add_post(
        "/integration/v1/assignments/{assignmentId}/cancelled",
        cancelled_handler,
    )
    app.router.add_post("/integration/v1/guides/discovery", discovery_handler)
    app.router.add_post(
        "/integration/v1/guides/{guideOsId}/availability",
        availability_handler,
    )
    app.router.add_get(
        "/integration/v1/reconcile/guides/{guideOsId}/connections",
        reconcile_connections_handler,
    )
    app.router.add_get(
        "/integration/v1/reconcile/guides/{guideOsId}/connections/{connectionId}",
        reconcile_connection_handler,
    )
    app.router.add_get(
        "/integration/v1/reconcile/guides/{guideOsId}/assignments",
        reconcile_assignments_handler,
    )
    app.router.add_get(
        "/integration/v1/reconcile/guides/{guideOsId}/assignments/{assignmentId}",
        reconcile_assignment_handler,
    )
    return app
