from copy import deepcopy
from datetime import datetime, timezone
import sqlite3
import threading

import pytest
from pydantic import ValidationError

from database.db import get_connection, init_db
from services.guide_shop_contracts import EventEnvelopeDTO
from services.guide_shop_event_inbox import (
    EventInboxConflictError,
    EventInboxIdentityMismatchError,
    GuideShopEventInboxService,
    IngestionOutcome,
)


GUIDE_OS_ID = "123e4567-e89b-42d3-a456-426614174000"
OTHER_GUIDE_OS_ID = "123e4567-e89b-42d3-a456-426614174001"


class Clock:
    def __init__(self, value: datetime | None = None):
        self.value = value or datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


def payload(
    event_type: str = "visit.created",
    *,
    event_id: str = "evt_00000001",
    aggregate_version: int = 1,
    occurred_at: str = "2026-08-19T09:00:00Z",
) -> dict:
    is_visit = event_type.startswith("visit.")
    return {
        "event_id": event_id,
        "event_type": event_type,
        "event_version": "v1",
        "schema_version": "1.0.0",
        "occurred_at": occurred_at,
        "producer": "guideshop",
        "subject": {
            "type": "visit" if is_visit else "points_accrual",
            "id": "vis_00000001" if is_visit else "pts_00000001",
        },
        "guide_os_id": GUIDE_OS_ID,
        "aggregate_version": aggregate_version,
        "data": {},
    }


def event(**changes) -> EventEnvelopeDTO:
    value = payload(**changes)
    return EventEnvelopeDTO.model_validate(value)


def service(**kwargs) -> GuideShopEventInboxService:
    return GuideShopEventInboxService(clock=Clock(), **kwargs)


def table_count(name: str) -> int:
    conn = get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    finally:
        conn.close()


@pytest.mark.parametrize(
    "event_type",
    [
        "visit.created",
        "visit.updated",
        "visit.completed",
        "points.accrual_updated",
        "points.credited",
    ],
)
def test_exact_v1_2_catalog_is_valid(event_type):
    parsed = EventEnvelopeDTO.model_validate(payload(event_type))
    assert parsed.event_type == event_type
    assert parsed.data.model_dump() == {}


def test_dto_rejects_invalid_combinations_unknown_fields_and_nonempty_data():
    invalid = []
    wrong_subject = payload("visit.updated")
    wrong_subject["subject"] = {"type": "points_accrual", "id": "pts_00000001"}
    invalid.append(wrong_subject)
    wrong_prefix = payload("points.credited")
    wrong_prefix["subject"]["id"] = "vis_00000001"
    invalid.append(wrong_prefix)
    unknown = payload()
    unknown["unknown"] = True
    invalid.append(unknown)
    nonempty = payload()
    nonempty["data"] = {"phone": "not-stored"}
    invalid.append(nonempty)
    for value in invalid:
        with pytest.raises(ValidationError):
            EventEnvelopeDTO.model_validate(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_id", "vis_00000001"),
        ("event_type", "sale.created"),
        ("event_version", "v2"),
        ("schema_version", "1.2.0"),
        ("occurred_at", "2026-08-19T09:00:00"),
        ("producer", "guide-os"),
        ("guide_os_id", "not-a-uuid"),
        ("aggregate_version", 0),
        ("aggregate_version", True),
    ],
)
def test_dto_rejects_invalid_contract_fields(field, value):
    value_payload = payload()
    value_payload[field] = value
    with pytest.raises(ValidationError):
        EventEnvelopeDTO.model_validate(value_payload)


def test_migration_forward_rerun_and_schema_inventory():
    init_db()
    init_db()
    conn = get_connection()
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        triggers = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        assert {"guide_shop_event_inbox", "guide_shop_event_watermarks"} <= tables
        assert {
            "idx_guide_shop_event_inbox_pending",
            "idx_guide_shop_event_inbox_aggregate",
        } <= indexes
        assert "trg_guide_shop_event_inbox_content_immutable" in triggers
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_existing_production_like_database_migrates(monkeypatch, tmp_path):
    import database.db as db_module

    path = tmp_path / "production-like.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, first_seen TEXT, last_seen TEXT)")
    conn.execute("INSERT INTO users VALUES (77, '2025-01-01', '2025-01-02')")
    conn.execute("CREATE TABLE tours (id INTEGER PRIMARY KEY, user_id INTEGER, company TEXT, city TEXT, start_date TEXT, end_date TEXT, status TEXT, income INTEGER, payment_status TEXT, note TEXT)")
    conn.execute("INSERT INTO tours VALUES (1, 77, 'A', 'B', '2026-01-01', '2026-01-02', 'reserved', NULL, 'unpaid', NULL)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(db_module, "DB_PATH", str(path))
    init_db()
    init_db()
    conn = get_connection()
    try:
        assert conn.execute("SELECT company FROM tours WHERE id = 1").fetchone()[0] == "A"
        assert conn.execute("SELECT COUNT(*) FROM guide_shop_event_inbox").fetchone()[0] == 0
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_first_insert_exact_retry_and_conflicting_duplicate():
    inbox = service()
    original = event()
    first = inbox.ingest(original, expected_guide_os_id=GUIDE_OS_ID)
    duplicate = inbox.ingest(original, expected_guide_os_id=GUIDE_OS_ID)
    assert (first.outcome, first.state) == (IngestionOutcome.INSERTED, "pending")
    assert (duplicate.outcome, duplicate.state) == (IngestionOutcome.DUPLICATE, "pending")
    assert table_count("guide_shop_event_inbox") == 1
    assert table_count("guide_shop_event_watermarks") == 1
    with pytest.raises(EventInboxConflictError, match="event identity conflict"):
        inbox.ingest(
            event(event_id=original.event_id, aggregate_version=2),
            expected_guide_os_id=GUIDE_OS_ID,
        )
    assert table_count("guide_shop_event_inbox") == 1


def _run_concurrent(events):
    barrier = threading.Barrier(len(events), timeout=5)
    results = []
    errors = []

    def ingest_one(item):
        try:
            barrier.wait()
            results.append(service().ingest(item, expected_guide_os_id=GUIDE_OS_ID))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=ingest_one, args=(item,)) for item in events]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()
    return results, errors


def test_concurrent_identical_ingestion_creates_one_row():
    same = event()
    results, errors = _run_concurrent([same, same])
    assert errors == []
    assert sorted(result.outcome.value for result in results) == ["duplicate", "inserted"]
    assert table_count("guide_shop_event_inbox") == 1


def test_concurrent_conflicting_ingestion_has_one_safe_winner():
    results, errors = _run_concurrent([event(), event(aggregate_version=2)])
    assert len(results) == 1
    assert results[0].outcome == IngestionOutcome.INSERTED
    assert len(errors) == 1
    assert isinstance(errors[0], EventInboxConflictError)
    assert str(errors[0]) == "event identity conflict"
    assert table_count("guide_shop_event_inbox") == 1


def test_identity_mismatch_has_no_write():
    with pytest.raises(EventInboxIdentityMismatchError, match="event identity mismatch"):
        service().ingest(event(), expected_guide_os_id=OTHER_GUIDE_OS_ID)
    assert table_count("guide_shop_event_inbox") == 0


def test_aggregate_versions_advance_and_out_of_order_is_stale():
    inbox = service()
    assert inbox.ingest(event(aggregate_version=1), expected_guide_os_id=GUIDE_OS_ID).state == "pending"
    assert inbox.ingest(event(event_id="evt_00000002", aggregate_version=2), expected_guide_os_id=GUIDE_OS_ID).state == "pending"
    watermark = inbox.get_watermark(
        guide_os_id=GUIDE_OS_ID, subject_type="visit", subject_id="vis_00000001"
    )
    assert watermark.highest_aggregate_version == 2
    assert watermark.event_id == "evt_00000002"
    assert inbox.get_event("evt_00000001").state == "stale"

    stale = inbox.ingest(
        event(event_id="evt_00000003", aggregate_version=1),
        expected_guide_os_id=GUIDE_OS_ID,
    )
    assert stale.state == "stale"
    assert inbox.get_watermark(
        guide_os_id=GUIDE_OS_ID, subject_type="visit", subject_id="vis_00000001"
    ).highest_aggregate_version == 2


def test_out_of_order_two_then_one_and_equal_version_do_not_regress():
    inbox = service()
    assert inbox.ingest(event(aggregate_version=2), expected_guide_os_id=GUIDE_OS_ID).state == "pending"
    assert inbox.ingest(event(event_id="evt_00000002", aggregate_version=1), expected_guide_os_id=GUIDE_OS_ID).state == "stale"
    assert inbox.ingest(event(event_id="evt_00000003", aggregate_version=2), expected_guide_os_id=GUIDE_OS_ID).state == "stale"
    watermark = inbox.get_watermark(
        guide_os_id=GUIDE_OS_ID, subject_type="visit", subject_id="vis_00000001"
    )
    assert (watermark.highest_aggregate_version, watermark.event_id) == (2, "evt_00000001")


def test_failure_after_insert_rolls_back_inbox_and_watermark():
    def fail():
        raise RuntimeError("injected failure")

    inbox = service(after_inbox_insert=fail)
    with pytest.raises(RuntimeError, match="injected failure"):
        inbox.ingest(event(), expected_guide_os_id=GUIDE_OS_ID)
    assert table_count("guide_shop_event_inbox") == 0
    assert table_count("guide_shop_event_watermarks") == 0


def test_pending_order_is_deterministic_and_stale_is_excluded():
    inbox = service()
    inbox.ingest(event(event_id="evt_00000003", aggregate_version=3, occurred_at="2026-08-19T09:03:00Z"), expected_guide_os_id=GUIDE_OS_ID)
    inbox.ingest(event(event_id="evt_00000001", aggregate_version=1, occurred_at="2026-08-19T09:01:00Z"), expected_guide_os_id=GUIDE_OS_ID)
    points = event(event_type="points.credited", event_id="evt_00000002", aggregate_version=1, occurred_at="2026-08-19T09:02:00Z")
    inbox.ingest(points, expected_guide_os_id=GUIDE_OS_ID)
    assert [item.event_id for item in inbox.list_pending()] == ["evt_00000002", "evt_00000003"]
    assert inbox.get_event("evt_00000001").state == "stale"


def test_wal_restart_persistence_and_backup_restore(tmp_path):
    inbox = service()
    inbox.ingest(event(), expected_guide_os_id=GUIDE_OS_ID)
    conn = get_connection()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()
    init_db()
    assert service().get_event("evt_00000001").state == "pending"

    backup_path = tmp_path / "restored.db"
    source = get_connection()
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        source.close()
        destination.close()
    restored = sqlite3.connect(backup_path)
    try:
        assert restored.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert restored.execute("SELECT state FROM guide_shop_event_inbox WHERE event_id = 'evt_00000001'").fetchone()[0] == "pending"
        names = {row[0] for row in restored.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'index', 'trigger')")}
        assert {
            "guide_shop_event_inbox",
            "guide_shop_event_watermarks",
            "idx_guide_shop_event_inbox_pending",
            "idx_guide_shop_event_inbox_aggregate",
            "trg_guide_shop_event_inbox_content_immutable",
        } <= names
    finally:
        restored.close()
