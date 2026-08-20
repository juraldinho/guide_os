import asyncio
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from database.db import get_connection, init_db
from services.guide_shop_contracts import EventEnvelopeDTO
from services.guide_shop_event_inbox import GuideShopEventInboxService
from services.guide_shop_event_notifications import (
    GuideShopEventNotificationService,
)
from services.guide_shop_navigation import resolve_navigation_token


GUIDE_ID = "123e4567-e89b-42d3-a456-426614174000"
USER_ID = 7001


class Clock:
    def __init__(self):
        self.value = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds=600):
        self.value += timedelta(seconds=seconds)


class Sender:
    def __init__(self, error=None, gate=None):
        self.error = error
        self.gate = gate
        self.calls = []

    async def send(self, telegram_user_id, text, deep_link):
        self.calls.append((telegram_user_id, text, deep_link))
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error


def run(value):
    return asyncio.run(value)


def payload(event_type="visit.created", event_id="evt_notice_0001"):
    visit = event_type.startswith("visit.")
    return {
        "event_id": event_id,
        "event_type": event_type,
        "event_version": "v1",
        "schema_version": "1.0.0",
        "occurred_at": "2026-08-20T08:00:00Z",
        "producer": "guideshop",
        "subject": {
            "type": "visit" if visit else "points_accrual",
            "id": "vis_sensitive_001" if visit else "pts_sensitive_001",
        },
        "guide_os_id": GUIDE_ID,
        "aggregate_version": 1,
        "data": {},
    }


def add_event(inbox, event_type="visit.created", event_id="evt_notice_0001"):
    event = EventEnvelopeDTO.model_validate(payload(event_type, event_id))
    inbox.ingest(event, expected_guide_os_id=GUIDE_ID)


def map_user():
    conn = get_connection()
    conn.execute(
        "INSERT INTO users (user_id, guide_os_id) VALUES (?, ?)",
        (USER_ID, GUIDE_ID),
    )
    conn.commit()
    conn.close()


def notification(clock, sender, inbox=None):
    inbox = inbox or GuideShopEventInboxService(clock=clock)
    return GuideShopEventNotificationService(
        inbox=inbox,
        sender=sender,
        bot_username="GuideOSBot",
        clock=clock,
    ), inbox


@pytest.mark.parametrize(
    ("event_type", "text", "route_kind"),
    [
        ("visit.created", "Новый визит в GuideShop.", "visit_detail"),
        ("visit.updated", "Визит в GuideShop обновлён.", "visit_detail"),
        ("visit.completed", "Визит в GuideShop завершён.", "visit_detail"),
        ("points.accrual_updated", "Баллы в GuideShop обновлены.", "points_detail"),
        ("points.credited", "Баллы в GuideShop зачислены.", "points_detail"),
    ],
)
def test_exact_russian_mapping_routes_and_safe_visible_text(
    event_type, text, route_kind
):
    clock = Clock()
    sender = Sender()
    service, inbox = notification(clock, sender)
    map_user()
    add_event(inbox, event_type)

    result = run(service.process_one())

    assert result.outcome == "delivered"
    assert len(sender.calls) == 1
    user_id, visible_text, deep_link = sender.calls[0]
    assert (user_id, visible_text) == (USER_ID, text)
    for forbidden in (
        "vis_sensitive_001",
        "pts_sensitive_001",
        GUIDE_ID,
        "evt_notice_0001",
        "100.00",
        "Компания",
        "Имя",
    ):
        assert forbidden not in visible_text
    raw_token = deep_link.split("?start=", 1)[1]
    route = resolve_navigation_token(raw_token, USER_ID, now=clock())
    assert route.kind == route_kind
    assert route.object_id == payload(event_type)["subject"]["id"]
    assert inbox.get_event("evt_notice_0001").state == "delivered"


def test_sender_failure_returns_to_pending_with_bounded_retry():
    clock = Clock()
    sender = Sender(RuntimeError("private transport details"))
    service, inbox = notification(clock, sender)
    map_user()
    add_event(inbox)

    result = run(service.process_one())
    stored = inbox.get_event("evt_notice_0001")

    assert result.outcome == "pending"
    assert stored.state == "pending"
    assert stored.attempt_count == 1
    assert stored.next_attempt_at == "2026-08-20T09:00:05Z"
    assert stored.terminal_at is None
    assert run(service.process_one()).outcome == "idle"


def test_exhausted_attempt_marks_dead_letter():
    clock = Clock()
    sender = Sender(RuntimeError("unavailable"))
    service, inbox = notification(clock, sender)
    map_user()
    add_event(inbox)
    conn = get_connection()
    conn.execute(
        "UPDATE guide_shop_event_inbox SET max_attempts = 1 WHERE event_id = ?",
        ("evt_notice_0001",),
    )
    conn.commit()
    conn.close()

    assert run(service.process_one()).outcome == "dead_letter"
    stored = inbox.get_event("evt_notice_0001")
    assert stored.state == "dead_letter"
    assert stored.terminal_at == "2026-08-20T09:00:00Z"
    assert stored.next_attempt_at is None


def insert_unsupported():
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO guide_shop_event_inbox (
            event_id, event_type, event_version, schema_version, occurred_at,
            producer, guide_os_id, subject_type, subject_id,
            aggregate_version, state, received_at
        ) VALUES (?, ?, 'v1', '1.0.0', ?, 'guideshop', ?, 'visit', ?, 1,
                  'pending', ?)
        """,
        (
            "evt_unsupported_01",
            "sale.created",
            "2026-08-20T08:00:00Z",
            GUIDE_ID,
            "vis_sensitive_001",
            "2026-08-20T08:01:00Z",
        ),
    )
    conn.commit()
    conn.close()


def test_unsupported_event_dead_letters_without_send():
    clock = Clock()
    sender = Sender()
    service, inbox = notification(clock, sender)
    map_user()
    insert_unsupported()

    result = run(service.process_one())

    assert (result.outcome, result.attempted) == ("dead_letter", False)
    assert sender.calls == []
    assert inbox.get_event("evt_unsupported_01").state == "dead_letter"


def test_missing_telegram_mapping_uses_bounded_failure():
    clock = Clock()
    sender = Sender()
    service, inbox = notification(clock, sender)
    add_event(inbox)

    assert run(service.process_one()).outcome == "pending"
    assert sender.calls == []
    assert inbox.get_event("evt_notice_0001").attempt_count == 1


def test_concurrent_claims_make_exactly_one_sender_call():
    async def scenario():
        clock = Clock()
        gate = asyncio.Event()
        sender = Sender(gate=gate)
        service, inbox = notification(clock, sender)
        map_user()
        add_event(inbox)
        first = asyncio.create_task(service.process_one())
        while not sender.calls:
            await asyncio.sleep(0)
        second = asyncio.create_task(service.process_one())
        second_result = await second
        gate.set()
        first_result = await first
        return first_result, second_result, sender, inbox

    first, second, sender, inbox = run(scenario())
    assert sorted([first.outcome, second.outcome]) == ["delivered", "idle"]
    assert len(sender.calls) == 1
    assert inbox.get_event("evt_notice_0001").state == "delivered"


@pytest.mark.parametrize("state", ["stale", "delivered", "dead_letter"])
def test_non_processable_states_are_ignored(state):
    clock = Clock()
    sender = Sender()
    service, inbox = notification(clock, sender)
    add_event(inbox)
    conn = get_connection()
    conn.execute(
        "UPDATE guide_shop_event_inbox SET state = ? WHERE event_id = ?",
        (state, "evt_notice_0001"),
    )
    conn.commit()
    conn.close()
    assert run(service.process_one()).outcome == "idle"
    assert sender.calls == []


def test_conditional_transitions_reject_stale_worker():
    clock = Clock()
    inbox = GuideShopEventInboxService(clock=clock)
    add_event(inbox)
    first = inbox.claim_due()
    assert first.claim_attempt == 1
    assert inbox.mark_failed(first).transitioned is True
    clock.advance()
    second = inbox.claim_due()
    assert second.claim_attempt == 2
    assert inbox.mark_delivered(first) is False
    assert inbox.get_event("evt_notice_0001").state == "processing"
    assert inbox.mark_delivered(second) is True


def test_cancellation_never_marks_delivered():
    clock = Clock()
    sender = Sender(asyncio.CancelledError())
    service, inbox = notification(clock, sender)
    map_user()
    add_event(inbox)
    with pytest.raises(asyncio.CancelledError):
        run(service.process_one())
    stored = inbox.get_event("evt_notice_0001")
    assert stored.state == "pending"
    assert stored.terminal_at is None


def test_deep_link_token_and_failures_are_not_logged(caplog):
    clock = Clock()
    sender = Sender(RuntimeError("secret exception text"))
    service, inbox = notification(clock, sender)
    map_user()
    add_event(inbox)
    run(service.process_one())
    raw_token = sender.calls[0][2].split("?start=", 1)[1]
    log_text = caplog.text
    assert raw_token not in log_text
    assert "secret exception text" not in log_text
    assert GUIDE_ID not in log_text


def test_migration_rerun_wal_restart_and_backup_restore(tmp_path):
    clock = Clock()
    inbox = GuideShopEventInboxService(clock=clock)
    add_event(inbox)
    init_db()
    init_db()
    assert inbox.get_event("evt_notice_0001").state == "pending"
    source = get_connection()
    assert source.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    destination = sqlite3.connect(tmp_path / "notifications-backup.db")
    source.backup(destination)
    source.close()
    assert destination.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert destination.execute(
        "SELECT state, attempt_count FROM guide_shop_event_inbox"
    ).fetchone() == ("pending", 0)
    destination.close()
