"""GO10A2A: deliver one queued Guide Operator guide notification via Telegram.

Reusable deliver_one_notification() boundary only. No worker/scheduler, no
getUpdates, and no changes to bot polling lifecycle.
"""

from __future__ import annotations

import json
import logging
import socket
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from database.db import ensure_db_ready
from database.queries import (
    claim_guide_operator_guide_notification_for_delivery,
    finish_guide_operator_guide_notification_delivery,
    get_user_id_by_guide_os_id,
)
from services.guide_operator_notification_delivery_settings import (
    GuideOperatorNotificationDeliveryConfigurationError,
    GuideOperatorNotificationDeliverySettings,
)
from services.guide_operator_notification_outbox import NOTIFICATION_TYPES
from utils.guide_os_identity import GuideOsIdentityError, validate_guide_os_id

logger = logging.getLogger("guide_os.guide_operator_notification_delivery")

ERROR_TIMEOUT = "timeout"
ERROR_NETWORK = "network"
ERROR_UNAVAILABLE = "unavailable"
ERROR_AUTHENTICATION = "authentication"
ERROR_RECIPIENT = "recipient"
ERROR_VALIDATION = "validation"
ERROR_CONTRACT = "contract"
ERROR_RETRY_EXHAUSTED = "retry_exhausted"

PERMANENT_ERROR_CODES = frozenset(
    {
        ERROR_AUTHENTICATION,
        ERROR_RECIPIENT,
        ERROR_VALIDATION,
        ERROR_CONTRACT,
        ERROR_RETRY_EXHAUSTED,
    }
)

CLAIM_LEASE = timedelta(seconds=30)
MAX_DELIVERY_ATTEMPTS = 10
BASE_RETRY_DELAY = timedelta(seconds=15)
MAX_RETRY_DELAY = timedelta(minutes=15)
RETRY_JITTER_FRACTION = 0.2
CONNECT_TIMEOUT_SECONDS = 2.0
READ_TIMEOUT_SECONDS = 5.0
MAX_RESPONSE_BYTES = 16 * 1024

BUTTON_TEXT = "Открыть Guide Operator"

DeliveryOutcome = Literal["delivered", "retrying", "failed"]

_MESSAGE_TEMPLATES = {
    "connection_invitation": (
        "Новое приглашение от {company}. Откройте Guide Operator, "
        "чтобы подтвердить или отклонить."
    ),
    "assignment_offer": (
        "Новое предложение тура от {company}. Откройте Guide Operator, "
        "чтобы ответить."
    ),
    "ordinary_version_change": (
        "Обновление по туру от {company}. Откройте Guide Operator, "
        "чтобы ознакомиться."
    ),
    "critical_confirmation_required": (
        "Требуется подтверждение изменений от {company}. "
        "Откройте Guide Operator."
    ),
    "assignment_cancellation": "Тур от {company} отменён оператором.",
    "connection_disconnection": "Подключение к {company} отключено.",
}


@dataclass(frozen=True)
class NotificationDeliveryResult:
    source_event_id: str
    notification_type: str
    outcome: DeliveryOutcome
    error_code: str | None
    attempt_count: int = 0
    mini_app_button_url: str | None = None
    notification_id: int | None = None


@dataclass(frozen=True)
class TelegramHttpResult:
    status_code: int | None
    ok: bool
    telegram_error_code: int | None
    transport_error: str | None


class GuideOperatorNotificationTelegramClient(Protocol):
    def send_webapp_message(
        self,
        *,
        bot_token: str,
        api_base_url: str,
        chat_id: int,
        text: str,
        web_app_url: str,
        button_text: str,
    ) -> TelegramHttpResult: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class UrllibTelegramNotificationClient:
    """Strict Telegram Bot API POST: timeouts, bounded body, no redirects, no retries."""

    def send_webapp_message(
        self,
        *,
        bot_token: str,
        api_base_url: str,
        chat_id: int,
        text: str,
        web_app_url: str,
        button_text: str,
    ) -> TelegramHttpResult:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": button_text,
                            "web_app": {"url": web_app_url},
                        }
                    ]
                ]
            },
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        # Token is only used to build the request URL; never log it.
        url = f"{api_base_url}/bot{bot_token}/sendMessage"
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
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
                status_code = int(getattr(response, "status", None) or response.getcode())
                content = _read_limited(response)
        except HTTPError as exc:
            status_code = int(exc.code)
            try:
                content = _read_limited(exc)
            except Exception:
                content = b""
            return _parse_telegram_result(status_code, content)
        except TimeoutError:
            _opaque_log("Guide Operator notification delivery timed out")
            return TelegramHttpResult(
                status_code=None, ok=False, telegram_error_code=None, transport_error=ERROR_TIMEOUT
            )
        except socket.timeout:
            _opaque_log("Guide Operator notification delivery timed out")
            return TelegramHttpResult(
                status_code=None, ok=False, telegram_error_code=None, transport_error=ERROR_TIMEOUT
            )
        except (URLError, ssl.SSLError, OSError):
            _opaque_log("Guide Operator notification delivery failed")
            return TelegramHttpResult(
                status_code=None, ok=False, telegram_error_code=None, transport_error=ERROR_NETWORK
            )
        except Exception:
            _opaque_log("Guide Operator notification delivery failed")
            return TelegramHttpResult(
                status_code=None, ok=False, telegram_error_code=None, transport_error=ERROR_NETWORK
            )
        return _parse_telegram_result(status_code, content)


def render_notification_text(notification_type: str, company_name: str) -> str:
    template = _MESSAGE_TEMPLATES.get(notification_type)
    if template is None:
        raise ValueError("unsupported notification type")
    company = company_name.strip()
    if not company:
        raise ValueError("company_name required")
    return template.format(company=company)


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


def deliver_one_notification(
    *,
    settings: GuideOperatorNotificationDeliverySettings | None = None,
    clock: Callable[[], datetime] | None = None,
    http_client: GuideOperatorNotificationTelegramClient | None = None,
    source_event_id: str | None = None,
    notification_id: int | None = None,
    jitter_unit: float | Callable[[], float] | None = None,
) -> NotificationDeliveryResult | None:
    """Claim and deliver exactly one eligible pending guide notification."""
    ensure_db_ready()
    try:
        resolved = (
            settings
            if settings is not None
            else GuideOperatorNotificationDeliverySettings.from_env()
        )
    except GuideOperatorNotificationDeliveryConfigurationError:
        _opaque_log("Guide Operator notification delivery configuration is invalid")
        return None
    if (
        not resolved.enabled
        or resolved.bot_token is None
        or resolved.mini_app_public_url is None
    ):
        _opaque_log("Guide Operator notification delivery is disabled")
        return None

    now = _utc_now(clock)
    claimed = claim_guide_operator_guide_notification_for_delivery(
        now_iso=now.isoformat(),
        lease_until_iso=(now + CLAIM_LEASE).isoformat(),
        permanent_error_codes=tuple(sorted(PERMANENT_ERROR_CODES)),
        source_event_id=source_event_id,
        notification_id=notification_id,
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
        http_client=http_client or UrllibTelegramNotificationClient(),
        now=now,
        jitter_unit=resolved_jitter,
    )


def _deliver_claimed(
    row: dict[str, Any],
    *,
    settings: GuideOperatorNotificationDeliverySettings,
    http_client: GuideOperatorNotificationTelegramClient,
    now: datetime,
    jitter_unit: float = 0.0,
) -> NotificationDeliveryResult:
    attempt_count = int(row["attempt_count"])
    source_event_id = str(row["source_event_id"])
    notification_type = str(row["notification_type"])
    notification_id = int(row["id"])
    company_name = str(row.get("company_name") or "")

    if attempt_count > MAX_DELIVERY_ATTEMPTS:
        return _finish(
            notification_id=notification_id,
            source_event_id=source_event_id,
            notification_type=notification_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_RETRY_EXHAUSTED,
            now=now,
            mini_app_button_url=settings.mini_app_public_url,
            jitter_unit=jitter_unit,
        )

    if notification_type not in NOTIFICATION_TYPES or not company_name.strip():
        _opaque_log("Guide Operator notification delivery skipped malformed record")
        return _finish(
            notification_id=notification_id,
            source_event_id=source_event_id,
            notification_type=notification_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_VALIDATION,
            now=now,
            mini_app_button_url=settings.mini_app_public_url,
            jitter_unit=jitter_unit,
        )

    try:
        guide_os_id = validate_guide_os_id(row["guide_os_id"])
    except GuideOsIdentityError:
        return _finish(
            notification_id=notification_id,
            source_event_id=source_event_id,
            notification_type=notification_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_VALIDATION,
            now=now,
            mini_app_button_url=settings.mini_app_public_url,
            jitter_unit=jitter_unit,
        )

    telegram_user_id = get_user_id_by_guide_os_id(guide_os_id)
    if telegram_user_id is None:
        _opaque_log("Guide Operator notification delivery recipient unavailable")
        return _finish(
            notification_id=notification_id,
            source_event_id=source_event_id,
            notification_type=notification_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_RECIPIENT,
            now=now,
            mini_app_button_url=settings.mini_app_public_url,
            jitter_unit=jitter_unit,
        )

    try:
        text = render_notification_text(notification_type, company_name)
    except ValueError:
        return _finish(
            notification_id=notification_id,
            source_event_id=source_event_id,
            notification_type=notification_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_VALIDATION,
            now=now,
            mini_app_button_url=settings.mini_app_public_url,
            jitter_unit=jitter_unit,
        )

    assert settings.bot_token is not None
    assert settings.mini_app_public_url is not None
    response = http_client.send_webapp_message(
        bot_token=settings.bot_token,
        api_base_url=settings.telegram_api_base_url,
        chat_id=int(telegram_user_id),
        text=text,
        web_app_url=settings.mini_app_public_url,
        button_text=BUTTON_TEXT,
    )
    return _apply_telegram_result(
        notification_id=notification_id,
        source_event_id=source_event_id,
        notification_type=notification_type,
        attempt_count=attempt_count,
        response=response,
        now=now,
        mini_app_button_url=settings.mini_app_public_url,
        jitter_unit=jitter_unit,
    )


def _apply_telegram_result(
    *,
    notification_id: int,
    source_event_id: str,
    notification_type: str,
    attempt_count: int,
    response: TelegramHttpResult,
    now: datetime,
    mini_app_button_url: str,
    jitter_unit: float = 0.0,
) -> NotificationDeliveryResult:
    if response.transport_error == ERROR_TIMEOUT:
        return _finish(
            notification_id=notification_id,
            source_event_id=source_event_id,
            notification_type=notification_type,
            attempt_count=attempt_count,
            outcome="retrying",
            error_code=ERROR_TIMEOUT,
            now=now,
            mini_app_button_url=mini_app_button_url,
            jitter_unit=jitter_unit,
        )
    if response.transport_error is not None:
        return _finish(
            notification_id=notification_id,
            source_event_id=source_event_id,
            notification_type=notification_type,
            attempt_count=attempt_count,
            outcome="retrying",
            error_code=response.transport_error,
            now=now,
            mini_app_button_url=mini_app_button_url,
            jitter_unit=jitter_unit,
        )
    status = response.status_code
    telegram_error = response.telegram_error_code
    if response.ok and status == 200:
        return _finish(
            notification_id=notification_id,
            source_event_id=source_event_id,
            notification_type=notification_type,
            attempt_count=attempt_count,
            outcome="delivered",
            error_code=None,
            now=now,
            mini_app_button_url=mini_app_button_url,
            delivered_at=now,
            jitter_unit=jitter_unit,
        )
    if status in {401, 403} or telegram_error in {401, 403}:
        # 401 = invalid bot token; 403 = chat forbidden / bot blocked.
        error = (
            ERROR_AUTHENTICATION
            if status == 401 or telegram_error == 401
            else ERROR_RECIPIENT
        )
        return _finish(
            notification_id=notification_id,
            source_event_id=source_event_id,
            notification_type=notification_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=error,
            now=now,
            mini_app_button_url=mini_app_button_url,
            jitter_unit=jitter_unit,
        )
    if status == 429 or (status is not None and status >= 500):
        return _finish(
            notification_id=notification_id,
            source_event_id=source_event_id,
            notification_type=notification_type,
            attempt_count=attempt_count,
            outcome="retrying",
            error_code=ERROR_UNAVAILABLE,
            now=now,
            mini_app_button_url=mini_app_button_url,
            jitter_unit=jitter_unit,
        )
    if status in {400, 404} or telegram_error in {400, 404}:
        return _finish(
            notification_id=notification_id,
            source_event_id=source_event_id,
            notification_type=notification_type,
            attempt_count=attempt_count,
            outcome="failed",
            error_code=ERROR_RECIPIENT,
            now=now,
            mini_app_button_url=mini_app_button_url,
            jitter_unit=jitter_unit,
        )
    return _finish(
        notification_id=notification_id,
        source_event_id=source_event_id,
        notification_type=notification_type,
        attempt_count=attempt_count,
        outcome="failed",
        error_code=ERROR_CONTRACT,
        now=now,
        mini_app_button_url=mini_app_button_url,
            jitter_unit=jitter_unit,
    )


def _finish(
    *,
    notification_id: int,
    source_event_id: str,
    notification_type: str,
    attempt_count: int,
    outcome: DeliveryOutcome,
    error_code: str | None,
    now: datetime,
    mini_app_button_url: str | None,
    delivered_at: datetime | None = None,
    jitter_unit: float = 0.0,
) -> NotificationDeliveryResult:
    next_attempt: str | None = None
    failed_at: str | None = None
    if outcome == "retrying":
        next_attempt = (
            now + retry_delay(attempt_count, jitter_unit=jitter_unit)
        ).isoformat()
    elif outcome == "failed":
        next_attempt = now.isoformat()
        failed_at = now.isoformat()
    finish_guide_operator_guide_notification_delivery(
        notification_id=notification_id,
        attempt_count=attempt_count,
        outcome=outcome,
        now_iso=now.isoformat(),
        next_attempt_at=next_attempt,
        last_error_code=error_code,
        delivered_at=delivered_at.isoformat() if delivered_at is not None else None,
        failed_at=failed_at,
    )
    return NotificationDeliveryResult(
        source_event_id=source_event_id,
        notification_type=notification_type,
        outcome=outcome,
        error_code=error_code,
        attempt_count=attempt_count,
        mini_app_button_url=mini_app_button_url,
        notification_id=notification_id,
    )


def _utc_now(clock: Callable[[], datetime] | None) -> datetime:
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    if not isinstance(now, datetime):
        raise GuideOperatorNotificationDeliveryConfigurationError(
            "Guide Operator notification delivery configuration is invalid"
        )
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


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


def _parse_telegram_result(status_code: int, content: bytes) -> TelegramHttpResult:
    try:
        data = json.loads(content.decode("utf-8")) if content else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = None
    if not isinstance(data, dict):
        return TelegramHttpResult(
            status_code=status_code,
            ok=False,
            telegram_error_code=None,
            transport_error=None,
        )
    ok = data.get("ok") is True
    error_code = data.get("error_code")
    telegram_error_code = int(error_code) if isinstance(error_code, int) else None
    return TelegramHttpResult(
        status_code=status_code,
        ok=ok,
        telegram_error_code=telegram_error_code,
        transport_error=None,
    )
