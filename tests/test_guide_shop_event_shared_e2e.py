import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlencode, urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import SecretStr
import pytest

GUIDESHOP_ROOT = Path(__file__).resolve().parents[2] / "guideshop"
SHARED_E2E_SKIP_REASON = "shared E2E requires sibling GuideShop checkout"
SHARED_E2E_REQUIRED = os.getenv("GUIDESHOP_SHARED_E2E_REQUIRED") == "true"

if not (GUIDESHOP_ROOT / "app" / "main.py").is_file():
    if SHARED_E2E_REQUIRED:
        raise RuntimeError("required sibling GuideShop checkout is missing")
    pytest.skip(SHARED_E2E_SKIP_REASON, allow_module_level=True)

if SHARED_E2E_REQUIRED:
    import fastapi as _fastapi
else:
    pytest.importorskip(
        "fastapi", reason="shared E2E requires the sibling GuideShop test runtime"
    )

import database.db as guide_os_db
from database.db import get_connection
from services.guide_shop_auth import GuideShopJWTEventAccessTokenProvider
from services.guide_shop_client import GuideShopClientError
from services.guide_shop_event_client import HTTPGuideShopEventFeedClient
from services.guide_shop_event_inbox import GuideShopEventInboxService
from services.guide_shop_event_notifications import GuideShopEventNotificationService
from services.guide_shop_event_pull import (
    EventCheckpoint,
    EventCheckpointRepository,
    GuideShopEventPullService,
)
from services.guide_shop_event_reconciliation import (
    GuideShopEventReconciliationService,
)
from services.guide_shop_navigation import resolve_navigation_token
from services.guide_shop_settings import (
    GuideShopHTTPSettings,
    GuideShopJWTSigningSettings,
)


GUIDE_A = "123e4567-e89b-42d3-a456-426614175001"
GUIDE_B = "123e4567-e89b-42d3-a456-426614175002"
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)
JWT_KID = "stage15-key-1"


def run(value):
    return asyncio.run(value)


class Clock:
    def __init__(self):
        self.value = NOW

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


class _Content:
    def __init__(self, body):
        self._body = body

    async def read(self, size):
        value, self._body = self._body[:size], self._body[size:]
        return value


class _Response:
    def __init__(self, response):
        body = response.content
        self.status = response.status_code
        self.headers = response.headers
        self.content_length = len(body)
        self.content = _Content(body)
        self.released = False

    def release(self):
        self.released = True


class InProcessGuideShopSession:
    def __init__(self, app):
        self._app = app
        self.calls = []
        self.closed = False

    async def request(self, method, url, **kwargs):
        params = kwargs.get("params") or {}
        headers = kwargs.get("headers") or {}
        parsed = urlsplit(url)
        self.calls.append((method, params))
        messages = []
        request_sent = False

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": parsed.scheme,
            "path": parsed.path,
            "raw_path": parsed.path.encode("ascii"),
            "query_string": urlencode(params).encode("ascii"),
            "root_path": "",
            "headers": [
                (name.lower().encode("ascii"), value.encode("ascii"))
                for name, value in headers.items()
            ],
            "client": ("127.0.0.1", 1),
            "server": (parsed.hostname, parsed.port or 443),
        }
        await self._app(scope, receive, send)
        start = next(item for item in messages if item["type"] == "http.response.start")
        body = b"".join(
            item.get("body", b"")
            for item in messages
            if item["type"] == "http.response.body"
        )
        response = SimpleNamespace(
            status_code=start["status"],
            headers={
                key.decode("latin-1"): value.decode("latin-1")
                for key, value in start.get("headers", [])
            },
            content=body,
        )
        return _Response(response)

    async def close(self):
        if not self.closed:
            self.closed = True


class FakeTelegramSender:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def send(self, telegram_user_id, text, deep_link):
        self.calls.append((telegram_user_id, text, deep_link))
        if self.error is not None:
            raise self.error


class FailOnSecondInbox(GuideShopEventInboxService):
    def __init__(self, *, clock):
        super().__init__(clock=clock)
        self.calls = 0

    def ingest(self, event, *, expected_guide_os_id):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("synthetic page interruption")
        return super().ingest(
            event, expected_guide_os_id=expected_guide_os_id
        )


@dataclass
class GuideShopRuntime:
    app: object
    db: object
    settings: object
    integration_v1: object
    links: object
    create_company_with_owner: object
    create_guide_for_company: object
    create_visit_for_company: object
    add_sale_to_visit_for_company: object
    guide_source_type: str
    signing_key: Ed25519PrivateKey


@pytest.fixture
def guideshop_runtime(tmp_path, monkeypatch):
    existing_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "app" or name.startswith("app.")
    }
    assert existing_modules == {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("BOT_TOKEN", "synthetic-local-token")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///synthetic")
    guideshop_db_path = tmp_path / "guideshop.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(guideshop_db_path))
    monkeypatch.setenv("GUIDESHOP_EVENTS_ENABLED", "false")
    monkeypatch.setenv("GUIDESHOP_READS_ENABLED", "false")
    sys.path.insert(0, str(GUIDESHOP_ROOT))

    from app.api import integration_v1
    from app.core.config import settings
    from app.database import db
    from app.main import create_app_for_combined_runtime
    from app.services import guide_os_link_service as links
    from app.services.company_provisioning_service import (
        create_company_with_owner,
    )
    from app.services.guide_service import create_guide_for_company
    from app.services.visit_sqlite_service import (
        GUIDE_SOURCE_TYPE,
        add_sale_to_visit_for_company,
        create_visit_for_company,
    )

    signing_key = Ed25519PrivateKey.generate()
    public_pem = signing_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    monkeypatch.setattr(settings, "guideshop_events_enabled", True)
    monkeypatch.setattr(settings, "guide_os_read_allowlist_enabled", False)
    monkeypatch.setattr(settings, "guide_os_read_rate_limit_enabled", False)
    monkeypatch.setattr(
        settings,
        "guide_os_read_jwt_public_keys_json",
        SecretStr(json.dumps({JWT_KID: public_pem})),
    )
    integration_v1.set_verifier_clock_for_tests(lambda: NOW)
    db.init_db()
    runtime = GuideShopRuntime(
        app=create_app_for_combined_runtime(),
        db=db,
        settings=settings,
        integration_v1=integration_v1,
        links=links,
        create_company_with_owner=create_company_with_owner,
        create_guide_for_company=create_guide_for_company,
        create_visit_for_company=create_visit_for_company,
        add_sale_to_visit_for_company=add_sale_to_visit_for_company,
        guide_source_type=GUIDE_SOURCE_TYPE,
        signing_key=signing_key,
    )
    yield runtime

    integration_v1.set_verifier_clock_for_tests(None)
    if str(GUIDESHOP_ROOT) in sys.path:
        sys.path.remove(str(GUIDESHOP_ROOT))
    for name in tuple(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)
    for database_path in (guideshop_db_path, Path(guide_os_db.DB_PATH)):
        for candidate in (
            database_path,
            Path(f"{database_path}-wal"),
            Path(f"{database_path}-shm"),
        ):
            candidate.unlink(missing_ok=True)


def _seed_linked_guide(runtime, *, identity, suffix):
    provisioned = runtime.create_company_with_owner(
        company_name=f"Synthetic Partner {suffix}",
        owner_name=f"Synthetic Owner {suffix}",
        owner_telegram_id=910_000 + suffix,
    )
    company_id = int(provisioned.company["id"])
    membership = runtime.create_guide_for_company(
        f"Synthetic Guide {suffix}", company_id
    )
    membership_id = int(membership["id"])
    exchange_id = f"ex-stage15-{suffix}"
    exchange = runtime.links.VerifiedExchangeResult(
        link_exchange_id=exchange_id,
        guide_os_id=identity,
        token_expires_at=runtime.links.format_utc_z(NOW + timedelta(minutes=5)),
        exchange_expires_at=runtime.links.format_utc_z(
            NOW + timedelta(minutes=10)
        ),
    )
    pending = runtime.links.create_pending_from_verified_exchange(
        actor_telegram_id=910_000 + suffix,
        company_id=company_id,
        company_guide_id=membership_id,
        exchange=exchange,
        clock=lambda: NOW,
    )
    awaiting = runtime.links.mark_awaiting_guide_confirmation(
        actor_telegram_id=910_000 + suffix,
        company_id=company_id,
        link_id=int(pending["id"]),
        clock=lambda: NOW,
    )
    runtime.links.activate_from_guide_confirmation(
        link_id=int(awaiting["id"]),
        confirmation=runtime.links.VerifiedGuideConfirmation(
            link_exchange_id=exchange_id,
            guide_os_id=identity,
            confirmation_evidence_ref=f"confirm-stage15-{suffix}",
            confirmed_status="active",
            confirmed_at=runtime.links.format_utc_z(NOW),
        ),
        clock=lambda: NOW,
        actor_telegram_id=910_000 + suffix,
        company_id=company_id,
    )
    return company_id, membership_id


def _create_visit_and_points_event(runtime, company_id, membership_id):
    visit = runtime.create_visit_for_company(
        {
            "tourist_count": 2,
            "country": "Synthetic Country",
            "language": "Synthetic Language",
            "source_type": runtime.guide_source_type,
            "company_guide_id": membership_id,
            "commission_percent": 10,
        },
        company_id,
    )
    runtime.add_sale_to_visit_for_company(
        int(visit["id"]), company_id, 100, "USD"
    )


def _guide_os_token_settings(key):
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return GuideShopJWTSigningSettings(
        app_env="test",
        key_id=JWT_KID,
        private_key_pem=private_pem,
    )


def _event_client(runtime, identity, clock):
    counter = iter(range(1 if identity == GUIDE_A else 101, 200))
    provider = GuideShopJWTEventAccessTokenProvider(
        _guide_os_token_settings(runtime.signing_key),
        clock=clock,
        random_bytes=lambda size: next(counter).to_bytes(size, "big"),
    )
    session = InProcessGuideShopSession(runtime.app)
    client = HTTPGuideShopEventFeedClient(
        GuideShopHTTPSettings(
            "https://guideshop.invalid", "test", 5, 1, 1
        ),
        identity,
        provider,
        session=session,
        owns_session=True,
        sleep=AsyncMock(),
    )
    return client, session


def _pull_service(client, inbox, identity, clock):
    return GuideShopEventPullService(
        client=client,
        inbox=inbox,
        checkpoint=EventCheckpointRepository(),
        expected_guide_os_id=identity,
        clock=clock,
    )


def _map_telegram(identity, telegram_id):
    conn = get_connection()
    conn.execute(
        "INSERT INTO users (user_id, guide_os_id) VALUES (?, ?)",
        (telegram_id, identity),
    )
    conn.commit()
    conn.close()


def _row_count(table):
    conn = get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_shared_guideshop_to_guide_os_event_lifecycle(guideshop_runtime):
    runtime = guideshop_runtime
    clock = Clock()
    inbox = GuideShopEventInboxService(clock=clock)
    company_a, membership_a = _seed_linked_guide(
        runtime, identity=GUIDE_A, suffix=1
    )
    company_b, membership_b = _seed_linked_guide(
        runtime, identity=GUIDE_B, suffix=2
    )
    _create_visit_and_points_event(runtime, company_a, membership_a)
    _create_visit_and_points_event(runtime, company_b, membership_b)

    client_a, session_a = _event_client(runtime, GUIDE_A, clock)
    client_b, session_b = _event_client(runtime, GUIDE_B, clock)
    try:
        page_a = run(client_a.fetch_events(limit=20))
        assert {item.event_type for item in page_a.data} == {
            "visit.created",
            "points.accrual_updated",
        }
        assert {item.subject.type for item in page_a.data} == {
            "visit",
            "points_accrual",
        }
        assert {item.aggregate_version for item in page_a.data} == {1}
        assert {item.guide_os_id for item in page_a.data} == {GUIDE_A}

        pull_a = _pull_service(client_a, inbox, GUIDE_A, clock)
        first = run(pull_a.pull_once(limit=20))
        checkpoint_a = EventCheckpointRepository().load(GUIDE_A)
        assert (first.fetched_count, first.inserted_count) == (2, 2)
        assert first.checkpoint_advanced is True
        assert checkpoint_a.cursor is not None
        assert _row_count("guide_shop_event_inbox") == 2

        _map_telegram(GUIDE_A, 7_001)
        sender_a = FakeTelegramSender()
        notifications_a = GuideShopEventNotificationService(
            inbox=inbox,
            sender=sender_a,
            bot_username="GuideOSBot",
            clock=clock,
        )
        outcomes = [
            run(notifications_a.process_one()).outcome,
            run(notifications_a.process_one()).outcome,
        ]
        assert outcomes == ["delivered", "delivered"]
        assert {call[1] for call in sender_a.calls} == {
            "Новый визит в GuideShop.",
            "Баллы в GuideShop обновлены.",
        }
        resolved = {
            resolve_navigation_token(
                call[2].split("?start=", 1)[1], call[0], now=clock()
            ).kind
            for call in sender_a.calls
        }
        assert resolved == {"visit_detail", "points_detail"}

        replay_page = run(client_a.fetch_events(cursor=None, limit=20))
        replay_results = [
            inbox.ingest(item, expected_guide_os_id=GUIDE_A)
            for item in replay_page.data
        ]
        assert {result.outcome.value for result in replay_results} == {
            "duplicate"
        }
        assert _row_count("guide_shop_event_inbox") == 2
        assert run(notifications_a.process_one()).outcome == "idle"
        assert len(sender_a.calls) == 2
        assert EventCheckpointRepository().load(GUIDE_A) == checkpoint_a

        page_b = run(client_b.fetch_events(limit=20))
        assert len(page_b.data) == 2
        assert {item.guide_os_id for item in page_b.data} == {GUIDE_B}
        assert not {item.event_id for item in page_a.data}.intersection(
            item.event_id for item in page_b.data
        )
        with pytest.raises(GuideShopClientError):
            run(
                client_a.fetch_events(
                    cursor=page_b.page.next_cursor, limit=20
                )
            )

        failing_inbox = FailOnSecondInbox(clock=clock)
        failed_pull = _pull_service(client_b, failing_inbox, GUIDE_B, clock)
        with pytest.raises(RuntimeError, match="synthetic page interruption"):
            run(failed_pull.pull_once(limit=20))
        assert EventCheckpointRepository().load(GUIDE_B) == EventCheckpoint(
            None, 0
        )
        assert _row_count("guide_shop_event_inbox") == 3

        replay_b = run(
            _pull_service(client_b, inbox, GUIDE_B, clock).pull_once(limit=20)
        )
        assert (replay_b.duplicate_count, replay_b.inserted_count) == (1, 1)
        assert replay_b.checkpoint_advanced is True
        checkpoint_b = EventCheckpointRepository().load(GUIDE_B)
        assert checkpoint_b.cursor is not None
        assert _row_count("guide_shop_event_inbox") == 4

        abandoned = inbox.claim_due()
        assert abandoned is not None
        clock.advance(301)
        attention = GuideShopEventReconciliationService(
            database_path=guide_os_db.DB_PATH, clock=clock
        ).reconcile()
        assert attention.verdict == "NEEDS_ATTENTION"
        recovered = inbox.recover_abandoned(limit=100, apply=True)
        assert (recovered.pending_count, recovered.dead_letter_count) == (1, 0)
        assert inbox.get_event(abandoned.event.event_id).attempt_count == 1

        _map_telegram(GUIDE_B, 7_002)
        failing_sender = FakeTelegramSender(
            RuntimeError("synthetic telegram failure")
        )
        failing_notifications = GuideShopEventNotificationService(
            inbox=inbox,
            sender=failing_sender,
            bot_username="GuideOSBot",
            clock=clock,
        )
        candidate = inbox.list_pending()
        assert candidate
        conn = get_connection()
        conn.execute(
            "UPDATE guide_shop_event_inbox SET max_attempts = attempt_count + 1 WHERE event_id = ?",
            (candidate[0].event_id,),
        )
        conn.commit()
        conn.close()
        assert run(failing_notifications.process_one()).outcome == "dead_letter"
        replayed = inbox.replay_dead_letters(limit=100, apply=True)
        assert (replayed.selected_count, replayed.replayed_count) == (1, 1)

        sender_b = FakeTelegramSender()
        notifications_b = GuideShopEventNotificationService(
            inbox=inbox,
            sender=sender_b,
            bot_username="GuideOSBot",
            clock=clock,
        )
        delivered_b = []
        while True:
            result = run(notifications_b.process_one())
            if result.outcome == "idle":
                break
            delivered_b.append(result.outcome)
        assert delivered_b == ["delivered", "delivered"]
        assert len(failing_sender.calls) == 1
        assert len(sender_b.calls) == 2

        final = GuideShopEventReconciliationService(
            database_path=guide_os_db.DB_PATH, clock=clock
        ).reconcile()
        assert final.verdict == "CLEAN"
        assert final.inbox_delivered_count == 4
        assert _row_count("guide_shop_event_inbox") == 4
        assert EventCheckpointRepository().load(GUIDE_A) == checkpoint_a
        assert EventCheckpointRepository().load(GUIDE_B) == checkpoint_b
        assert len(session_a.calls) <= 4
        assert len(session_b.calls) <= 3
    finally:
        run(client_a.close())
        run(client_b.close())
    assert session_a.closed is True
    assert session_b.closed is True
