"""GO10A2A: deliver one queued Guide Operator notification via Telegram."""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

import bot as bot_module
import guide_operator_integration_api as integration_api
from database.db import init_db, run_write_with_retry
from database.queries import (
    get_guide_operator_guide_notification_by_source_event_id,
    get_guide_os_id,
    register_user,
)
from services.guide_operator_notification_delivery import (
    BUTTON_TEXT,
    ERROR_AUTHENTICATION,
    ERROR_RECIPIENT,
    ERROR_TIMEOUT,
    ERROR_UNAVAILABLE,
    ERROR_VALIDATION,
    TelegramHttpResult,
    deliver_one_notification,
    render_notification_text,
)
from services.guide_operator_notification_delivery_settings import (
    GuideOperatorNotificationDeliveryConfigurationError,
    GuideOperatorNotificationDeliverySettings,
)
from services.guide_operator_notification_outbox import (
    deep_link_target_for_assignment,
    deep_link_target_for_connection,
    insert_guide_operator_guide_notification,
)
from services.guide_operator_notification_delivery import logger as delivery_logger

FIXED_NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
BOT_TOKEN = "7000000000:TEST_guide_operator_notify_token_01"
MINI_APP_URL = "https://miniapp.example.com"
SECRET_CONTACT = "Hidden Ops Contact"
JWT_MARKER = "eyJ"


class FrozenClock:
    def __init__(self, now: datetime = FIXED_NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeTelegram:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[TelegramHttpResult] = []

    def queue(self, result: TelegramHttpResult) -> None:
        self.responses.append(result)

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
        self.calls.append(
            {
                "bot_token": bot_token,
                "api_base_url": api_base_url,
                "chat_id": chat_id,
                "text": text,
                "web_app_url": web_app_url,
                "button_text": button_text,
            }
        )
        if not self.responses:
            return TelegramHttpResult(
                status_code=200, ok=True, telegram_error_code=None, transport_error=None
            )
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def _reset_db() -> Iterator[None]:
    init_db()
    yield


def _settings() -> GuideOperatorNotificationDeliverySettings:
    return GuideOperatorNotificationDeliverySettings.enabled_with(
        app_env="test",
        bot_token=BOT_TOKEN,
        mini_app_public_url=MINI_APP_URL,
    )


def _seed_guide(user_id: int = 1201) -> tuple[str, int]:
    register_user(user_id)
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    return guide_os_id, user_id


def _insert_notification(
    *,
    guide_os_id: str,
    notification_type: str,
    company_name: str = "Operator Co",
    source_event_id: str | None = None,
    connection_id: str | None = None,
    assignment_id: str | None = None,
    version_number: int | None = None,
    created_at: str = "2026-09-06T10:00:00+00:00",
) -> str:
    eid = source_event_id or str(uuid4())

    def operation(conn):
        insert_guide_operator_guide_notification(
            conn,
            source_event_id=eid,
            guide_os_id=guide_os_id,
            notification_type=notification_type,  # type: ignore[arg-type]
            company_name=company_name,
            connection_id=connection_id,
            assignment_id=assignment_id,
            version_number=version_number,
            created_at=created_at,
        )

    run_write_with_retry(operation)
    return eid


def test_settings_default_disabled() -> None:
    settings = GuideOperatorNotificationDeliverySettings.from_env({})
    assert settings.enabled is False


def test_settings_enabled_without_token_or_url_fails_closed() -> None:
    with pytest.raises(GuideOperatorNotificationDeliveryConfigurationError):
        GuideOperatorNotificationDeliverySettings.from_env(
            {
                "GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_DELIVERY_ENABLED": "true",
                "BOT_TOKEN": "",
                "MINI_APP_PUBLIC_URL": MINI_APP_URL,
            }
        )
    with pytest.raises(GuideOperatorNotificationDeliveryConfigurationError):
        GuideOperatorNotificationDeliverySettings.from_env(
            {
                "GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_DELIVERY_ENABLED": "true",
                "BOT_TOKEN": BOT_TOKEN,
                "MINI_APP_PUBLIC_URL": "http://miniapp.example.com",
            }
        )


def test_bot_and_integration_api_do_not_start_notification_delivery() -> None:
    for source in (
        inspect.getsource(bot_module),
        inspect.getsource(integration_api),
    ):
        assert "deliver_one_notification" not in source
        assert "guide_operator_notification_delivery" not in source
        assert "NOTIFICATION_DELIVERY" not in source


@pytest.mark.parametrize(
    ("notification_type", "company", "expected_snippet"),
    [
        ("connection_invitation", "Invite Co", "Новое приглашение от Invite Co"),
        ("assignment_offer", "Offer Co", "Новое предложение тура от Offer Co"),
        (
            "ordinary_version_change",
            "Update Co",
            "Обновление по туру от Update Co",
        ),
        (
            "critical_confirmation_required",
            "Critical Co",
            "Требуется подтверждение изменений от Critical Co",
        ),
        (
            "assignment_cancellation",
            "Cancel Co",
            "Тур от Cancel Co отменён оператором",
        ),
        (
            "connection_disconnection",
            "Leave Co",
            "Подключение к Leave Co отключено",
        ),
    ],
)
def test_russian_message_for_each_type(
    notification_type: str, company: str, expected_snippet: str
) -> None:
    text = render_notification_text(notification_type, company)
    assert expected_snippet in text
    assert SECRET_CONTACT not in text
    assert JWT_MARKER not in text


@pytest.mark.parametrize(
    "notification_type",
    [
        "connection_invitation",
        "assignment_offer",
        "ordinary_version_change",
        "critical_confirmation_required",
        "assignment_cancellation",
        "connection_disconnection",
    ],
)
def test_deliver_one_success_every_type(notification_type: str) -> None:
    guide_os_id, user_id = _seed_guide(1202)
    connection_id = str(uuid4()) if "connection" in notification_type else None
    assignment_id = None if connection_id else str(uuid4())
    version_number = None if connection_id else 2
    if notification_type == "assignment_offer":
        version_number = 1
    if notification_type == "assignment_cancellation":
        version_number = 1
    event_id = _insert_notification(
        guide_os_id=guide_os_id,
        notification_type=notification_type,
        company_name="Operator Co",
        connection_id=connection_id,
        assignment_id=assignment_id,
        version_number=version_number,
    )
    http = FakeTelegram()
    http.queue(
        TelegramHttpResult(
            status_code=200, ok=True, telegram_error_code=None, transport_error=None
        )
    )
    result = deliver_one_notification(
        settings=_settings(),
        clock=FrozenClock(),
        http_client=http,
        source_event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "delivered"
    assert result.notification_type == notification_type
    assert result.mini_app_button_url == MINI_APP_URL
    assert len(http.calls) == 1
    call = http.calls[0]
    assert call["chat_id"] == user_id
    assert call["web_app_url"] == MINI_APP_URL
    assert call["button_text"] == BUTTON_TEXT
    assert "Operator Co" in call["text"]
    assert SECRET_CONTACT not in call["text"]
    row = get_guide_operator_guide_notification_by_source_event_id(event_id)
    assert row is not None
    assert row["delivery_status"] == "delivered"
    assert row["delivered_at"] is not None
    assert row["failed_at"] is None
    if connection_id:
        assert row["deep_link_target"] == deep_link_target_for_connection(connection_id)
    else:
        assert row["deep_link_target"] == deep_link_target_for_assignment(assignment_id)


def test_recipient_bound_from_guide_os_id_not_payload() -> None:
    guide_os_id, user_id = _seed_guide(1203)
    other_guide, other_user = _seed_guide(1204)
    del other_guide
    event_id = _insert_notification(
        guide_os_id=guide_os_id,
        notification_type="assignment_offer",
        assignment_id=str(uuid4()),
        version_number=1,
    )
    http = FakeTelegram()
    result = deliver_one_notification(
        settings=_settings(),
        clock=FrozenClock(),
        http_client=http,
        source_event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "delivered"
    assert http.calls[0]["chat_id"] == user_id
    assert http.calls[0]["chat_id"] != other_user


def test_duplicate_delivery_does_not_resend() -> None:
    guide_os_id, _ = _seed_guide(1205)
    event_id = _insert_notification(
        guide_os_id=guide_os_id,
        notification_type="assignment_offer",
        assignment_id=str(uuid4()),
        version_number=1,
    )
    http = FakeTelegram()
    first = deliver_one_notification(
        settings=_settings(),
        clock=FrozenClock(),
        http_client=http,
        source_event_id=event_id,
    )
    second = deliver_one_notification(
        settings=_settings(),
        clock=FrozenClock(),
        http_client=http,
        source_event_id=event_id,
    )
    assert first is not None and first.outcome == "delivered"
    assert second is None
    assert len(http.calls) == 1


def test_retryable_telegram_errors_keep_pending() -> None:
    guide_os_id, _ = _seed_guide(1206)
    event_id = _insert_notification(
        guide_os_id=guide_os_id,
        notification_type="assignment_offer",
        assignment_id=str(uuid4()),
        version_number=1,
    )
    http = FakeTelegram()
    http.queue(
        TelegramHttpResult(
            status_code=503, ok=False, telegram_error_code=None, transport_error=None
        )
    )
    result = deliver_one_notification(
        settings=_settings(),
        clock=FrozenClock(),
        http_client=http,
        source_event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "retrying"
    assert result.error_code == ERROR_UNAVAILABLE
    row = get_guide_operator_guide_notification_by_source_event_id(event_id)
    assert row is not None
    assert row["delivery_status"] == "pending"
    assert row["last_error_code"] == ERROR_UNAVAILABLE
    assert row["next_attempt_at"] is not None
    assert row["failed_at"] is None


def test_timeout_is_retryable() -> None:
    guide_os_id, _ = _seed_guide(1207)
    event_id = _insert_notification(
        guide_os_id=guide_os_id,
        notification_type="connection_invitation",
        connection_id=str(uuid4()),
    )
    http = FakeTelegram()
    http.queue(
        TelegramHttpResult(
            status_code=None,
            ok=False,
            telegram_error_code=None,
            transport_error=ERROR_TIMEOUT,
        )
    )
    result = deliver_one_notification(
        settings=_settings(),
        clock=FrozenClock(),
        http_client=http,
        source_event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "retrying"
    assert result.error_code == ERROR_TIMEOUT


def test_permanent_auth_and_recipient_failures_remain_inspectable() -> None:
    guide_os_id, _ = _seed_guide(1208)
    auth_event = _insert_notification(
        guide_os_id=guide_os_id,
        notification_type="assignment_offer",
        assignment_id=str(uuid4()),
        version_number=1,
    )
    http = FakeTelegram()
    http.queue(
        TelegramHttpResult(
            status_code=401, ok=False, telegram_error_code=401, transport_error=None
        )
    )
    auth_result = deliver_one_notification(
        settings=_settings(),
        clock=FrozenClock(),
        http_client=http,
        source_event_id=auth_event,
    )
    assert auth_result is not None
    assert auth_result.outcome == "failed"
    assert auth_result.error_code == ERROR_AUTHENTICATION
    auth_row = get_guide_operator_guide_notification_by_source_event_id(auth_event)
    assert auth_row is not None
    assert auth_row["delivery_status"] == "failed"
    assert auth_row["failed_at"] is not None

    blocked_event = _insert_notification(
        guide_os_id=guide_os_id,
        notification_type="assignment_offer",
        assignment_id=str(uuid4()),
        version_number=1,
    )
    http.queue(
        TelegramHttpResult(
            status_code=403, ok=False, telegram_error_code=403, transport_error=None
        )
    )
    blocked = deliver_one_notification(
        settings=_settings(),
        clock=FrozenClock(),
        http_client=http,
        source_event_id=blocked_event,
    )
    assert blocked is not None
    assert blocked.error_code == ERROR_RECIPIENT
    blocked_row = get_guide_operator_guide_notification_by_source_event_id(blocked_event)
    assert blocked_row is not None
    assert blocked_row["delivery_status"] == "failed"
    # Permanent failures are not reclaimed.
    assert (
        deliver_one_notification(
            settings=_settings(),
            clock=FrozenClock(),
            http_client=http,
            source_event_id=blocked_event,
        )
        is None
    )
    assert len(http.calls) == 2


def test_disabled_configuration_does_not_claim() -> None:
    guide_os_id, _ = _seed_guide(1209)
    event_id = _insert_notification(
        guide_os_id=guide_os_id,
        notification_type="assignment_offer",
        assignment_id=str(uuid4()),
        version_number=1,
    )
    http = FakeTelegram()
    result = deliver_one_notification(
        settings=GuideOperatorNotificationDeliverySettings.disabled("test"),
        clock=FrozenClock(),
        http_client=http,
        source_event_id=event_id,
    )
    assert result is None
    assert http.calls == []
    row = get_guide_operator_guide_notification_by_source_event_id(event_id)
    assert row is not None
    assert int(row["attempt_count"]) == 0
    assert row["delivery_status"] == "pending"


def test_unknown_guide_recipient_is_permanent() -> None:
    missing_guide = str(uuid4())
    event_id = _insert_notification(
        guide_os_id=missing_guide,
        notification_type="assignment_offer",
        assignment_id=str(uuid4()),
        version_number=1,
    )
    http = FakeTelegram()
    result = deliver_one_notification(
        settings=_settings(),
        clock=FrozenClock(),
        http_client=http,
        source_event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "failed"
    assert result.error_code == ERROR_RECIPIENT
    assert http.calls == []


def test_malformed_empty_company_is_permanent() -> None:
    guide_os_id, _ = _seed_guide(1210)
    event_id = str(uuid4())
    assignment_id = str(uuid4())

    def operation(conn):
        conn.execute(
            """
            INSERT INTO guide_operator_guide_notifications (
                source_event_id, guide_os_id, notification_type, company_name,
                connection_id, assignment_id, version_number, deep_link_target,
                created_at, delivery_status, delivered_at, failed_at,
                attempt_count, last_error_code, next_attempt_at
            ) VALUES (?, ?, 'assignment_offer', '', NULL, ?, 1, ?, ?,
                      'pending', NULL, NULL, 0, NULL, NULL)
            """,
            (
                event_id,
                guide_os_id,
                assignment_id,
                deep_link_target_for_assignment(assignment_id),
                "2026-09-06T10:00:00+00:00",
            ),
        )

    run_write_with_retry(operation)
    http = FakeTelegram()
    result = deliver_one_notification(
        settings=_settings(),
        clock=FrozenClock(),
        http_client=http,
        source_event_id=event_id,
    )
    assert result is not None
    assert result.outcome == "failed"
    assert result.error_code == ERROR_VALIDATION
    assert http.calls == []


def test_privacy_excludes_secrets_from_logs_and_results(caplog) -> None:
    guide_os_id, _ = _seed_guide(1211)
    event_id = _insert_notification(
        guide_os_id=guide_os_id,
        notification_type="assignment_offer",
        company_name="Operator Co",
        assignment_id=str(uuid4()),
        version_number=1,
    )
    http = FakeTelegram()
    http.queue(
        TelegramHttpResult(
            status_code=500, ok=False, telegram_error_code=None, transport_error=None
        )
    )
    with caplog.at_level(logging.WARNING, logger=delivery_logger.name):
        result = deliver_one_notification(
            settings=_settings(),
            clock=FrozenClock(),
            http_client=http,
            source_event_id=event_id,
        )
    assert result is not None
    joined = " ".join(record.getMessage() for record in caplog.records)
    combined = joined + str(result)
    assert BOT_TOKEN not in combined
    assert JWT_MARKER not in combined
    assert SECRET_CONTACT not in combined
    assert "working_package" not in combined
    assert "chat_id" not in joined
    for record in caplog.records:
        assert "Operator Co" not in record.getMessage()
        assert "Новое предложение" not in record.getMessage()
