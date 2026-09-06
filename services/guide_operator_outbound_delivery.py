"""GO8F2A: authenticated single-event delivery Guide OS → Guide Operator.

Claims one eligible outbox row, builds the frozen envelope, signs with GO8B
EdDSA outbound JWT, and POSTs to the matching GO8F1 route. No worker/scheduler.
"""

from __future__ import annotations

import json
import logging
import socket
import ssl
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from database.db import ensure_db_ready
from database.queries import (
    claim_guide_operator_outbox_for_delivery,
    finish_guide_operator_outbox_delivery,
)
from services.guide_operator_outbound_settings import (
    GuideOperatorOutboundConfigurationError,
    GuideOperatorOutboundSettings,
)
from services.guide_operator_service_auth_settings import (
    GuideOperatorServiceAuthConfigurationError,
    current_guide_operator_auth_clock,
    current_guide_operator_random_bytes,
)
from services.guide_operator_service_jwt import (
    SCOPE_ASSIGNMENTS_DECIDE,
    SCOPE_CONNECTIONS_DECIDE,
    SCOPE_VERSIONS_DECIDE,
    GuideOSOutboundJWTAccessTokenProvider,
    GuideOperatorServiceTokenSigningError,
)
from utils.guide_os_identity import GuideOsIdentityError, validate_guide_os_id

logger = logging.getLogger("guide_os.guide_operator_outbound")

EVENT_CONNECTION_DECIDED = "guide_connection.decided.v1"
EVENT_ASSIGNMENT_DECISION = "assignment.decision.v1"
EVENT_CANCELLATION_ACK = "assignment.cancellation.ack.v1"
EVENT_VERSION_APPLIED_ACK = "assignment.version.applied.ack.v1"
EVENT_VERSION_RECEIVED_ACK = "assignment.version.received.ack.v1"
EVENT_CRITICAL_VERSION_DECIDED = "assignment.critical_version.decided.v1"
EVENT_VERSION_ACKNOWLEDGED = "assignment.version.acknowledged.v1"

DELIVERABLE_EVENT_TYPES = frozenset(
    {
        EVENT_CONNECTION_DECIDED,
        EVENT_ASSIGNMENT_DECISION,
        EVENT_CANCELLATION_ACK,
        EVENT_VERSION_APPLIED_ACK,
        EVENT_VERSION_RECEIVED_ACK,
        EVENT_CRITICAL_VERSION_DECIDED,
        EVENT_VERSION_ACKNOWLEDGED,
    }
)

_EVENT_SCOPE = {
    EVENT_CONNECTION_DECIDED: SCOPE_CONNECTIONS_DECIDE,
    EVENT_ASSIGNMENT_DECISION: SCOPE_ASSIGNMENTS_DECIDE,
    EVENT_CANCELLATION_ACK: SCOPE_ASSIGNMENTS_DECIDE,
    EVENT_VERSION_APPLIED_ACK: SCOPE_VERSIONS_DECIDE,
    EVENT_VERSION_RECEIVED_ACK: SCOPE_VERSIONS_DECIDE,
    EVENT_CRITICAL_VERSION_DECIDED: SCOPE_VERSIONS_DECIDE,
    EVENT_VERSION_ACKNOWLEDGED: SCOPE_VERSIONS_DECIDE,
}

_PATH_ID_FIELD = {
    EVENT_CONNECTION_DECIDED: "connection_id",
    EVENT_ASSIGNMENT_DECISION: "assignment_id",
    EVENT_CANCELLATION_ACK: "assignment_id",
    EVENT_VERSION_APPLIED_ACK: "assignment_id",
    EVENT_VERSION_RECEIVED_ACK: "assignment_id",
    EVENT_CRITICAL_VERSION_DECIDED: "assignment_id",
    EVENT_VERSION_ACKNOWLEDGED: "assignment_id",
}

_PATH_TEMPLATE = {
    EVENT_CONNECTION_DECIDED: "/integration/v1/guide-connections/{path_id}/decided",
    EVENT_ASSIGNMENT_DECISION: "/integration/v1/assignments/{path_id}/decided",
    EVENT_CANCELLATION_ACK: "/integration/v1/assignments/{path_id}/cancellation-ack",
    EVENT_VERSION_APPLIED_ACK: (
        "/integration/v1/assignments/{path_id}/version-applied-ack"
    ),
    EVENT_VERSION_RECEIVED_ACK: (
        "/integration/v1/assignments/{path_id}/version-received-ack"
    ),
    EVENT_CRITICAL_VERSION_DECIDED: (
        "/integration/v1/assignments/{path_id}/critical-version-decided"
    ),
    EVENT_VERSION_ACKNOWLEDGED: (
        "/integration/v1/assignments/{path_id}/version-acknowledged"
    ),
}

_PAYLOAD_KEYS = {
    EVENT_CONNECTION_DECIDED: frozenset(
        {
            "connection_id",
            "guide_os_id",
            "company_id",
            "company_name",
            "decision",
            "decided_at",
        }
    ),
    EVENT_ASSIGNMENT_DECISION: frozenset(
        {
            "assignment_id",
            "guide_os_id",
            "decision",
            "version_number",
            "decided_at",
            "projection_tour_id",
        }
    ),
    EVENT_CANCELLATION_ACK: frozenset(
        {
            "assignment_id",
            "guide_os_id",
            "version_number",
            "cancelled_at",
            "source_event_id",
        }
    ),
    EVENT_VERSION_APPLIED_ACK: frozenset(
        {
            "assignment_id",
            "guide_os_id",
            "version_number",
            "previous_active_version_number",
            "severity",
            "source_event_id",
            "published_at",
            "applied_at",
        }
    ),
    EVENT_VERSION_RECEIVED_ACK: frozenset(
        {
            "assignment_id",
            "guide_os_id",
            "version_number",
            "previous_active_version_number",
            "severity",
            "source_event_id",
            "published_at",
            "received_at",
        }
    ),
    EVENT_CRITICAL_VERSION_DECIDED: frozenset(
        {
            "assignment_id",
            "guide_os_id",
            "decision",
            "version_number",
            "decided_at",
            "projection_tour_id",
            "active_version_number",
        }
    ),
    EVENT_VERSION_ACKNOWLEDGED: frozenset(
        {
            "assignment_id",
            "guide_os_id",
            "version_number",
            "acknowledged_at",
            "decision_event_id",
        }
    ),
}

ERROR_TIMEOUT = "timeout"
ERROR_NETWORK = "network"
ERROR_UNAVAILABLE = "unavailable"
ERROR_AUTHENTICATION = "authentication"
ERROR_CONTRACT = "contract"
ERROR_VALIDATION = "validation"
ERROR_UNSUPPORTED = "unsupported"
ERROR_IDENTIFIER_MISMATCH = "identifier_mismatch"
ERROR_NOT_FOUND = "not_found"
ERROR_CONFLICT = "conflict"
ERROR_RETRY_EXHAUSTED = "retry_exhausted"

PERMANENT_ERROR_CODES = frozenset(
    {
        ERROR_AUTHENTICATION,
        ERROR_CONTRACT,
        ERROR_VALIDATION,
        ERROR_UNSUPPORTED,
        ERROR_IDENTIFIER_MISMATCH,
        ERROR_NOT_FOUND,
        ERROR_CONFLICT,
        ERROR_RETRY_EXHAUSTED,
    }
)

CLAIM_LEASE = timedelta(seconds=30)
MAX_DELIVERY_ATTEMPTS = 10
MAX_RETRY_DELAY = timedelta(minutes=15)
BASE_RETRY_DELAY = timedelta(seconds=15)
RETRY_JITTER_FRACTION = 0.2
CONNECT_TIMEOUT_SECONDS = 2.0
READ_TIMEOUT_SECONDS = 5.0
MAX_RESPONSE_BYTES = 16 * 1024

DeliveryOutcome = Literal["delivered", "retrying", "failed"]


@dataclass(frozen=True)
class OutboundDeliveryResult:
    event_id: str
    event_type: str
    outcome: DeliveryOutcome
    error_code: str | None
    replayed: bool = False
    attempt_count: int = 0


@dataclass(frozen=True)
class SignedHttpResult:
    status_code: int | None
    data: dict[str, Any] | None
    transport_error: str | None


class UnsupportedOutboxEventError(ValueError):
    """Raised when an outbox event type has no Guide Operator delivery route."""


class OutboxIdentifierMismatchError(ValueError):
    """Raised when path/payload/aggregate identifiers disagree."""


class MalformedOutboxPayloadError(ValueError):
    """Raised when stored payload_json cannot be delivered."""


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class GuideOperatorOutboundHttpClient(Protocol):
    def post_signed(
        self,
        *,
        url: str,
        authorization: str,
        body: bytes,
    ) -> SignedHttpResult: ...


class UrllibGuideOperatorOutboundHttpClient:
    """Strict HTTP POST client: timeouts, bounded body, no redirects, no retries."""

    def post_signed(
        self,
        *,
        url: str,
        authorization: str,
        body: bytes,
    ) -> SignedHttpResult:
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": authorization,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        opener = build_opener(_NoRedirectHandler)
        try:
            with opener.open(
                request,
                timeout=CONNECT_TIMEOUT_SECONDS + READ_TIMEOUT_SECONDS,
            ) as response:
                status_code = getattr(response, "status", None) or response.getcode()
                content_type = response.headers.get("Content-Type", "")
                content = _read_limited(response)
        except HTTPError as exc:
            status_code = int(exc.code)
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            try:
                content = _read_limited(exc)
            except Exception:
                content = b""
            if status_code != 200:
                return SignedHttpResult(
                    status_code=status_code, data=None, transport_error=None
                )
            return SignedHttpResult(
                status_code=status_code,
                data=_parse_success_data(content_type, content),
                transport_error=None,
            )
        except TimeoutError:
            _opaque_log("Guide Operator delivery timed out")
            return SignedHttpResult(
                status_code=None, data=None, transport_error=ERROR_TIMEOUT
            )
        except socket.timeout:
            _opaque_log("Guide Operator delivery timed out")
            return SignedHttpResult(
                status_code=None, data=None, transport_error=ERROR_TIMEOUT
            )
        except (URLError, ssl.SSLError, OSError):
            _opaque_log("Guide Operator delivery failed")
            return SignedHttpResult(
                status_code=None, data=None, transport_error=ERROR_NETWORK
            )
        except Exception:
            _opaque_log("Guide Operator delivery failed")
            return SignedHttpResult(
                status_code=None, data=None, transport_error=ERROR_NETWORK
            )
        if status_code != 200:
            return SignedHttpResult(
                status_code=int(status_code), data=None, transport_error=None
            )
        return SignedHttpResult(
            status_code=int(status_code),
            data=_parse_success_data(content_type, content),
            transport_error=None,
        )


def _opaque_log(message: str) -> None:
    logger.warning(message)


def _read_limited(stream) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise OSError("response too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_success_data(content_type: str, content: bytes) -> dict[str, Any] | None:
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        return None
    try:
        parsed: object = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict) or set(parsed) - {"data", "meta"} or "data" not in parsed:
        return None
    data = parsed["data"]
    if not isinstance(data, dict):
        return None
    return data


def canonicalize(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def dumps_canonical(value: object) -> str:
    return json.dumps(
        canonicalize(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _aware_iso(value: str) -> str:
    text = value.strip()
    if not text:
        raise MalformedOutboxPayloadError("Outbox payload is malformed")
    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise MalformedOutboxPayloadError("Outbox payload is malformed") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _canonical_uuid(value: object) -> str:
    if not isinstance(value, str) or value != value.lower():
        raise MalformedOutboxPayloadError("Outbox payload is malformed")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError) as exc:
        raise MalformedOutboxPayloadError("Outbox payload is malformed") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise MalformedOutboxPayloadError("Outbox payload is malformed")
    return value


def delivery_scope(event_type: str) -> str:
    scope = _EVENT_SCOPE.get(event_type)
    if scope is None:
        raise UnsupportedOutboxEventError("Unsupported outbox event type")
    return scope


def delivery_path(
    event_type: str, payload: Mapping[str, Any], *, aggregate_id: str
) -> str:
    field = _PATH_ID_FIELD.get(event_type)
    template = _PATH_TEMPLATE.get(event_type)
    if field is None or template is None:
        raise UnsupportedOutboxEventError("Unsupported outbox event type")
    path_id = payload.get(field)
    if not isinstance(path_id, str) or not path_id:
        raise MalformedOutboxPayloadError("Outbox payload is malformed")
    if path_id != aggregate_id:
        raise OutboxIdentifierMismatchError("Outbox path identifier does not match")
    return template.format(path_id=path_id)


def validate_deliverable_payload(
    event_type: str,
    payload: object,
    *,
    guide_os_id: str,
    aggregate_id: str,
) -> dict[str, Any]:
    required = _PAYLOAD_KEYS.get(event_type)
    if required is None:
        raise UnsupportedOutboxEventError("Unsupported outbox event type")
    if not isinstance(payload, dict) or set(payload) != required:
        raise MalformedOutboxPayloadError("Outbox payload is malformed")
    try:
        payload_guide = validate_guide_os_id(payload.get("guide_os_id"))
        row_guide = validate_guide_os_id(guide_os_id)
    except GuideOsIdentityError as exc:
        raise OutboxIdentifierMismatchError(
            "Outbox guide identifier does not match"
        ) from exc
    if payload_guide != row_guide:
        raise OutboxIdentifierMismatchError("Outbox guide identifier does not match")
    field = _PATH_ID_FIELD[event_type]
    path_id = payload.get(field)
    if not isinstance(path_id, str) or path_id != aggregate_id:
        raise OutboxIdentifierMismatchError("Outbox path identifier does not match")
    _canonical_uuid(payload.get("guide_os_id"))
    return payload


def serialize_event_envelope(row: Mapping[str, Any]) -> dict[str, Any]:
    """Build frozen envelope from outbox row without rewriting payload_json."""
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError, KeyError) as exc:
        raise MalformedOutboxPayloadError("Outbox payload is malformed") from exc
    if not isinstance(payload, dict):
        raise MalformedOutboxPayloadError("Outbox payload is malformed")
    event_id = _canonical_uuid(row.get("event_id"))
    event_type = row.get("event_type")
    if not isinstance(event_type, str) or not event_type:
        raise MalformedOutboxPayloadError("Outbox payload is malformed")
    occurred_at = _aware_iso(str(row.get("created_at") or ""))
    return {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "payload": canonicalize(payload),
    }


def dumps_event_envelope(row: Mapping[str, Any]) -> str:
    return dumps_canonical(serialize_event_envelope(row))


def retry_delay(attempt_count: int, *, jitter_unit: float = 0.0) -> timedelta:
    exponent = max(attempt_count - 1, 0)
    delay = BASE_RETRY_DELAY * (2**exponent)
    if delay > MAX_RETRY_DELAY:
        delay = MAX_RETRY_DELAY
    unit = min(max(jitter_unit, 0.0), 1.0)
    jittered = delay + timedelta(
        seconds=delay.total_seconds() * RETRY_JITTER_FRACTION * unit
    )
    return jittered if jittered < MAX_RETRY_DELAY else MAX_RETRY_DELAY


def _utc_now(clock: Callable[[], datetime] | None) -> datetime:
    now = (clock or current_guide_operator_auth_clock())()
    if not isinstance(now, datetime):
        raise GuideOperatorOutboundConfigurationError(
            "Guide Operator outbound configuration is invalid"
        )
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def deliver_one(
    *,
    settings: GuideOperatorOutboundSettings | None = None,
    clock: Callable[[], datetime] | None = None,
    http_client: GuideOperatorOutboundHttpClient | None = None,
    event_id: str | None = None,
    random_bytes: Callable[[int], bytes] | None = None,
    jitter_unit: float | Callable[[], float] | None = None,
) -> OutboundDeliveryResult | None:
    """Claim and deliver exactly one eligible Guide Operator outbox event."""
    ensure_db_ready()
    try:
        resolved = (
            settings
            if settings is not None
            else GuideOperatorOutboundSettings.from_env()
        )
    except GuideOperatorOutboundConfigurationError:
        _opaque_log("Guide Operator delivery configuration is invalid")
        return None
    if not resolved.enabled or resolved.base_url is None or resolved.outbound_jwt is None:
        _opaque_log("Guide Operator delivery is disabled")
        return None

    now = _utc_now(clock)
    lease_until = now + CLAIM_LEASE
    claimed = claim_guide_operator_outbox_for_delivery(
        now_iso=now.isoformat(),
        lease_until_iso=lease_until.isoformat(),
        deliverable_event_types=tuple(sorted(DELIVERABLE_EVENT_TYPES)),
        permanent_error_codes=tuple(sorted(PERMANENT_ERROR_CODES)),
        event_id=event_id,
    )
    if claimed is None:
        return None
    resolved_jitter = 0.0
    if callable(jitter_unit):
        resolved_jitter = float(jitter_unit())
    elif jitter_unit is not None:
        resolved_jitter = float(jitter_unit)
    return _deliver_claimed(
        claimed,
        settings=resolved,
        clock=clock,
        http_client=http_client or UrllibGuideOperatorOutboundHttpClient(),
        random_bytes=random_bytes,
        now=now,
        jitter_unit=resolved_jitter,
    )


def _deliver_claimed(
    row: dict[str, Any],
    *,
    settings: GuideOperatorOutboundSettings,
    clock: Callable[[], datetime] | None,
    http_client: GuideOperatorOutboundHttpClient,
    random_bytes: Callable[[int], bytes] | None,
    now: datetime,
    jitter_unit: float = 0.0,
) -> OutboundDeliveryResult:
    attempt_count = int(row["attempt_count"])
    event_id = str(row["event_id"])
    event_type = str(row["event_type"])
    outbox_id = int(row["id"])

    if attempt_count > MAX_DELIVERY_ATTEMPTS:
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_RETRY_EXHAUSTED,
            now=now,
            jitter_unit=jitter_unit,
        )
    if event_type not in DELIVERABLE_EVENT_TYPES:
        _opaque_log("Guide Operator delivery skipped unsupported event")
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_UNSUPPORTED,
            now=now,
            jitter_unit=jitter_unit,
        )

    try:
        envelope = serialize_event_envelope(row)
        payload = validate_deliverable_payload(
            event_type,
            envelope["payload"],
            guide_os_id=str(row["guide_os_id"]),
            aggregate_id=str(row["aggregate_id"]),
        )
        path = delivery_path(event_type, payload, aggregate_id=str(row["aggregate_id"]))
        scope = delivery_scope(event_type)
        guide_os_id = validate_guide_os_id(row["guide_os_id"])
    except UnsupportedOutboxEventError:
        _opaque_log("Guide Operator delivery skipped unsupported event")
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_UNSUPPORTED,
            now=now,
        )
    except OutboxIdentifierMismatchError:
        _opaque_log("Guide Operator delivery failed identifier check")
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_IDENTIFIER_MISMATCH,
            now=now,
        )
    except (MalformedOutboxPayloadError, GuideOsIdentityError):
        _opaque_log("Guide Operator delivery failed payload check")
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_VALIDATION,
            now=now,
        )

    assert settings.outbound_jwt is not None
    assert settings.base_url is not None
    try:
        token = GuideOSOutboundJWTAccessTokenProvider(
            settings.outbound_jwt,
            clock=clock or current_guide_operator_auth_clock(),
            random_bytes=random_bytes or current_guide_operator_random_bytes(),
        ).sign(scope, guide_os_id)
    except (
        GuideOperatorServiceTokenSigningError,
        GuideOperatorServiceAuthConfigurationError,
    ):
        _opaque_log("Guide Operator delivery authentication failed")
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_AUTHENTICATION,
            now=now,
        )

    canonical = dumps_canonical(envelope)
    response = http_client.post_signed(
        url=f"{settings.base_url}{path}",
        authorization=f"Bearer {token}",
        body=canonical.encode("utf-8"),
    )
    return _apply_http_result(
        outbox_id=outbox_id,
        event_id=event_id,
        event_type=event_type,
        attempt_count=attempt_count,
        envelope=envelope,
        response=response,
        now=now,
        jitter_unit=jitter_unit,
    )


def _apply_http_result(
    *,
    outbox_id: int,
    event_id: str,
    event_type: str,
    attempt_count: int,
    envelope: dict[str, Any],
    response: SignedHttpResult,
    now: datetime,
    jitter_unit: float = 0.0,
) -> OutboundDeliveryResult:
    if response.transport_error == ERROR_TIMEOUT:
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="retrying",
            error_code=ERROR_TIMEOUT,
            now=now,
            jitter_unit=jitter_unit,
        )
    if response.transport_error == ERROR_AUTHENTICATION:
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_AUTHENTICATION,
            now=now,
            jitter_unit=jitter_unit,
        )
    if response.transport_error is not None:
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="retrying",
            error_code=response.transport_error,
            now=now,
            jitter_unit=jitter_unit,
        )
    status = response.status_code
    if status in {401, 403}:
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_AUTHENTICATION,
            now=now,
            jitter_unit=jitter_unit,
        )
    if status in {400, 422}:
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_CONTRACT,
            now=now,
            jitter_unit=jitter_unit,
        )
    if status == 404:
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_NOT_FOUND,
            now=now,
            jitter_unit=jitter_unit,
        )
    if status == 409:
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_CONFLICT,
            now=now,
            jitter_unit=jitter_unit,
        )
    if status in {429, 500, 502, 503, 504} or (status is not None and status >= 500):
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="retrying",
            error_code=ERROR_UNAVAILABLE,
            now=now,
            jitter_unit=jitter_unit,
        )
    if status != 200 or response.data is None:
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_CONTRACT,
            now=now,
            jitter_unit=jitter_unit,
        )
    data = response.data
    ack_event_id = data.get("eventId")
    ack_event_type = data.get("eventType")
    ack_status = data.get("status")
    ack_replayed = data.get("replayed")
    if (
        ack_event_id != envelope["event_id"]
        or ack_event_type != envelope["event_type"]
        or ack_status not in {"applied", "replayed"}
        or not isinstance(ack_replayed, bool)
        or ack_replayed != (ack_status == "replayed")
    ):
        return _finish(
            outbox_id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_CONTRACT,
            now=now,
            jitter_unit=jitter_unit,
        )
    return _finish(
        outbox_id=outbox_id,
        event_id=event_id,
        event_type=event_type,
        attempt_count=attempt_count,
        outcome="delivered",
        error_code=None,
        now=now,
            jitter_unit=jitter_unit,
        replayed=ack_replayed,
        delivered_at=now,
    )


def _finish(
    *,
    outbox_id: int,
    event_id: str,
    event_type: str,
    attempt_count: int,
    outcome: DeliveryOutcome,
    error_code: str | None,
    now: datetime,
    replayed: bool = False,
    delivered_at: datetime | None = None,
    jitter_unit: float = 0.0,
) -> OutboundDeliveryResult:
    next_attempt: str | None = None
    if outcome == "retrying":
        next_attempt = (
            now + retry_delay(attempt_count, jitter_unit=jitter_unit)
        ).isoformat()
    elif outcome == "failed":
        next_attempt = now.isoformat()
    finish_guide_operator_outbox_delivery(
        outbox_id=outbox_id,
        attempt_count=attempt_count,
        outcome=outcome,
        now_iso=now.isoformat(),
        next_attempt_at=next_attempt,
        last_error_code=error_code,
        delivered_at=delivered_at.isoformat() if delivered_at is not None else None,
    )
    return OutboundDeliveryResult(
        event_id=event_id,
        event_type=event_type,
        outcome=outcome,
        error_code=error_code,
        replayed=replayed,
        attempt_count=attempt_count,
    )
