import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import inspect
import json
import sqlite3
import threading

import pytest
from pydantic import ValidationError

from database.db import get_connection, init_db
from services.guide_shop_client import (
    GuideShopAccessDeniedError,
    GuideShopAuthenticationError,
    GuideShopClientError,
    GuideShopTemporarilyUnavailableError,
)
from services.guide_shop_contracts import EventListResponseDTO
from services.guide_shop_event_client import HTTPGuideShopEventFeedClient
from services.guide_shop_event_inbox import (
    EventInboxConflictError,
    GuideShopEventInboxService,
)
from services.guide_shop_event_pull import (
    EventCheckpoint,
    EventCheckpointRepository,
    GuideShopEventPullService,
)
from services.guide_shop_settings import GuideShopHTTPSettings


GUIDE_ID = "123e4567-e89b-42d3-a456-426614174000"
OTHER_ID = "123e4567-e89b-42d3-a456-426614174001"
NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def run(value):
    return asyncio.run(value)


def settings(retries=1):
    return GuideShopHTTPSettings(
        "https://api.guideshop.example", "test", 5, retries, 2
    )


def event(event_id="evt_00000001", version=1, guide_id=GUIDE_ID):
    return {
        "event_id": event_id,
        "event_type": "visit.created",
        "event_version": "v1",
        "schema_version": "1.0.0",
        "occurred_at": "2026-08-19T11:00:00Z",
        "producer": "guideshop",
        "subject": {"type": "visit", "id": "vis_00000001"},
        "guide_os_id": guide_id,
        "aggregate_version": version,
        "data": {},
    }


def page(events=(), cursor=None, has_more=False):
    return {
        "schema_version": "1.0.0",
        "request_id": "req_events_0001",
        "data": list(events),
        "page": {"next_cursor": cursor, "has_more": has_more},
    }


class Content:
    def __init__(self, body):
        self.body = body

    async def read(self, size):
        value, self.body = self.body[:size], self.body[size:]
        return value


class Response:
    def __init__(self, status=200, payload=None, headers=None):
        raw = json.dumps(payload).encode()
        self.status = status
        self.headers = headers or {}
        self.content_length = len(raw)
        self.content = Content(raw)
        self.released = False

    def release(self):
        self.released = True


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return self.responses.pop(0)


class Tokens:
    def __init__(self):
        self.identities = []
        self.number = 0

    async def get_access_token(self, identity):
        self.identities.append(identity)
        self.number += 1
        return f"event-token-{self.number}"


def client(responses, **kwargs):
    session = Session(responses)
    tokens = Tokens()
    return HTTPGuideShopEventFeedClient(
        settings(kwargs.pop("retries", 1)), GUIDE_ID, tokens, session=session,
        owns_session=False, sleep=kwargs.pop("sleep", asyncio.sleep), **kwargs
    ), session, tokens


def error(code, retry=None):
    value = {
        "schema_version": "1.0.0",
        "request_id": "req_error_0001",
        "code": code,
        "message": "Request failed",
    }
    if retry is not None:
        value["retry_after_seconds"] = retry
    return value


def test_exact_path_query_identity_token_and_limits():
    http, session, tokens = client(
        [Response(payload=page([event()], "cursor_next_0001"))]
    )
    result = run(http.fetch_events())
    method, url, kwargs = session.requests[0]
    assert method == "GET"
    assert url == "https://api.guideshop.example/integration/v1/me/events"
    assert kwargs["params"] == {"limit": "20"}
    assert set(kwargs["params"]) == {"limit"}
    assert tokens.identities == [GUIDE_ID]
    assert result.data[0].event_id == "evt_00000001"

    http, session, _ = client(
        [Response(payload=page([event()], "cursor_next_0002"))]
    )
    run(http.fetch_events(cursor="cursor_prev_0001", limit=50))
    assert session.requests[0][2]["params"] == {
        "limit": "50", "cursor": "cursor_prev_0001"
    }
    for invalid in (0, 51, True, 1.5):
        with pytest.raises(GuideShopClientError):
            run(http.fetch_events(limit=invalid))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(extra=True),
        lambda value: value["page"].update(extra=True),
        lambda value: value["page"].update(next_cursor=None),
        lambda value: value["page"].update(next_cursor="bad cursor"),
        lambda value: value["data"][0].update(event_version="v2"),
    ],
)
def test_http_strict_response_validation(mutation):
    value = page([event()], "cursor_next_0001")
    mutation(value)
    http, _, _ = client([Response(payload=value)])
    with pytest.raises(GuideShopClientError, match="Invalid GuideShop response"):
        run(http.fetch_events())


def test_dto_empty_and_nonempty_page_rules():
    EventListResponseDTO.model_validate(page([], None, False))
    EventListResponseDTO.model_validate(page([event()], "cursor_next_0001", False))
    for value in (
        page([], "cursor_next_0001", False),
        page([], None, True),
        page([event()], None, False),
    ):
        with pytest.raises(ValidationError):
            EventListResponseDTO.model_validate(value)


@pytest.mark.parametrize(
    ("status", "payload", "exception"),
    [
        (400, error("invalid_request"), GuideShopClientError),
        (401, error("unauthenticated"), GuideShopAuthenticationError),
        (403, error("link_not_active"), GuideShopAccessDeniedError),
        (429, error("rate_limited", 1), GuideShopTemporarilyUnavailableError),
        (503, error("temporarily_unavailable", 1), GuideShopTemporarilyUnavailableError),
    ],
)
def test_safe_error_envelopes(status, payload, exception):
    responses = [Response(status, payload)]
    if status in {429, 503}:
        responses.append(Response(status, payload))
    http, _, _ = client(responses)
    with pytest.raises(exception):
        run(http.fetch_events())


def test_retry_uses_new_token_per_request():
    sleeps = []

    async def sleep(value):
        sleeps.append(value)

    http, session, tokens = client(
        [
            Response(503, error("temporarily_unavailable", 1)),
            Response(payload=page([], None, False)),
        ],
        sleep=sleep,
    )
    run(http.fetch_events())
    assert len(session.requests) == 2
    assert len(tokens.identities) == 2
    assert session.requests[0][2]["headers"]["Authorization"] != session.requests[1][2]["headers"]["Authorization"]
    assert sleeps == [0.25]


class Feed:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    async def fetch_events(self, *, cursor=None, limit=20):
        self.calls.append((cursor, limit))
        return EventListResponseDTO.model_validate(self.pages.pop(0))


def puller(feed, inbox=None):
    return GuideShopEventPullService(
        client=feed,
        inbox=inbox or GuideShopEventInboxService(clock=lambda: NOW),
        checkpoint=EventCheckpointRepository(),
        expected_guide_os_id=GUIDE_ID,
        clock=lambda: NOW,
    )


def test_initial_success_duplicate_replay_and_empty_preserves_cursor():
    feed = Feed(
        [
            page([event()], "cursor_page_0001", True),
            page([event()], "cursor_page_0001", True),
            page([], None, False),
        ]
    )
    service = puller(feed)
    first = run(service.pull_once())
    second = run(service.pull_once())
    empty = run(service.pull_once())
    assert feed.calls == [(None, 20), ("cursor_page_0001", 20), ("cursor_page_0001", 20)]
    assert (first.inserted_count, first.checkpoint_advanced) == (1, True)
    assert (second.duplicate_count, second.checkpoint_advanced) == (1, False)
    assert (empty.fetched_count, empty.checkpoint_advanced) == (0, False)
    assert EventCheckpointRepository().load(GUIDE_ID).cursor == "cursor_page_0001"


def test_manual_multi_page_sequence():
    feed = Feed([
        page([event()], "cursor_page_0001", True),
        page([event("evt_00000002", 2)], "cursor_page_0002", False),
    ])
    service = puller(feed)
    assert run(service.pull_once()).has_more is True
    result = run(service.pull_once(limit=10))
    checkpoint = EventCheckpointRepository().load(GUIDE_ID)
    assert (result.fetched_count, result.inserted_count) == (1, 1)
    assert (checkpoint.cursor, checkpoint.generation) == ("cursor_page_0002", 2)


class FailingInbox(GuideShopEventInboxService):
    def __init__(self, fail_on):
        super().__init__(clock=lambda: NOW)
        self.number = 0
        self.fail_on = fail_on

    def ingest(self, event, *, expected_guide_os_id):
        self.number += 1
        if self.number == self.fail_on:
            raise RuntimeError("safe injected failure")
        return super().ingest(event, expected_guide_os_id=expected_guide_os_id)


def test_failure_on_event_n_checkpoint_unchanged_and_replay_safe():
    value = page(
        [event(), event("evt_00000002", 2)], "cursor_page_0001", False
    )
    with pytest.raises(RuntimeError, match="safe injected failure"):
        run(puller(Feed([value]), FailingInbox(2)).pull_once())
    assert EventCheckpointRepository().load(GUIDE_ID) == EventCheckpoint(None, 0)
    assert GuideShopEventInboxService(clock=lambda: NOW).get_event("evt_00000001") is not None
    replay = run(puller(Feed([value])).pull_once())
    assert (replay.duplicate_count, replay.inserted_count, replay.checkpoint_advanced) == (1, 1, True)


def test_identity_conflict_and_malformed_page_leave_checkpoint():
    with pytest.raises(ValueError, match="event identity mismatch"):
        run(puller(Feed([page([event(guide_id=OTHER_ID)], "cursor_page_0001")])).pull_once())
    assert EventCheckpointRepository().load(GUIDE_ID).cursor is None

    inbox = GuideShopEventInboxService(clock=lambda: NOW)
    original = EventListResponseDTO.model_validate(page([event()], "cursor_seed_0001")).data[0]
    inbox.ingest(original, expected_guide_os_id=GUIDE_ID)
    conflict = event(version=2)
    with pytest.raises(EventInboxConflictError):
        run(puller(Feed([page([conflict], "cursor_page_0001")]), inbox).pull_once())
    assert EventCheckpointRepository().load(GUIDE_ID).cursor is None


def test_checkpoint_cas_concurrency_and_no_regression():
    repo = EventCheckpointRepository()
    initial = repo.load(GUIDE_ID)
    barrier = threading.Barrier(2)
    results = []

    def advance(cursor):
        barrier.wait()
        results.append(repo.advance(GUIDE_ID, expected=initial, next_cursor=cursor, updated_at=NOW))

    threads = [threading.Thread(target=advance, args=(value,)) for value in ("cursor_next_0001", "cursor_next_0002")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive()
    assert sorted(results) == [False, True]
    winner = repo.load(GUIDE_ID)
    assert repo.advance(GUIDE_ID, expected=initial, next_cursor="cursor_old_0001", updated_at=NOW) is False
    assert repo.load(GUIDE_ID) == winner


def test_checkpoint_migration_wal_restart_backup_restore(tmp_path):
    init_db()
    init_db()
    repo = EventCheckpointRepository()
    assert repo.advance(GUIDE_ID, expected=repo.load(GUIDE_ID), next_cursor="cursor_next_0001", updated_at=NOW)
    init_db()
    assert repo.load(GUIDE_ID) == EventCheckpoint("cursor_next_0001", 1)
    source = get_connection()
    assert source.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    destination = sqlite3.connect(tmp_path / "backup.db")
    source.backup(destination)
    source.close()
    assert destination.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert destination.execute("SELECT cursor, generation FROM guide_shop_event_checkpoints").fetchone() == ("cursor_next_0001", 1)
    destination.close()


def test_construction_import_has_no_network_and_no_background_tasks(monkeypatch):
    called = []
    monkeypatch.setattr("aiohttp.ClientSession", lambda *a, **k: called.append(True))
    HTTPGuideShopEventFeedClient(settings(), GUIDE_ID, Tokens())
    assert called == []
    source = inspect.getsource(__import__("services.guide_shop_event_pull", fromlist=["*"]))
    assert "create_task" not in source
    assert "while True" not in source
