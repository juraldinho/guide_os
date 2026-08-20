from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import subprocess
import sys

import database.db as db_module
from database.db import get_connection
from services.guide_shop_event_reconciliation import (
    GuideShopEventReconciliationService,
)


NOW = datetime(2026, 8, 21, 8, 0, tzinfo=timezone.utc)
GUIDE_A = "123e4567-e89b-42d3-a456-426614174000"
GUIDE_B = "123e4567-e89b-42d3-a456-426614174001"
SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "guide_shop_event_reconciliation.py"
)


def iso(value):
    return value.isoformat().replace("+00:00", "Z")


def insert_event(
    event_id,
    version,
    *,
    guide_id=GUIDE_A,
    subject_id="vis_reconcile_subject_01",
    state="delivered",
    last_attempt_at=None,
    terminal_at=None,
):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO guide_shop_event_inbox (
            event_id, event_type, event_version, schema_version, occurred_at,
            producer, guide_os_id, subject_type, subject_id,
            aggregate_version, state, received_at, attempt_count,
            max_attempts, last_attempt_at, terminal_at
        ) VALUES (?, 'visit.created', 'v1', '1.0.0', ?, 'guideshop',
                  ?, 'visit', ?, ?, ?, ?, 1, 5, ?, ?)
        """,
        (
            event_id,
            iso(NOW - timedelta(hours=1)),
            guide_id,
            subject_id,
            version,
            state,
            iso(NOW - timedelta(minutes=30)),
            iso(last_attempt_at) if last_attempt_at else None,
            iso(terminal_at) if terminal_at else None,
        ),
    )
    conn.commit()
    conn.close()


def insert_watermark(
    event_id,
    version,
    *,
    guide_id=GUIDE_A,
    subject_id="vis_reconcile_subject_01",
):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO guide_shop_event_watermarks (
            guide_os_id, subject_type, subject_id,
            highest_aggregate_version, event_id, updated_at
        ) VALUES (?, 'visit', ?, ?, ?, ?)
        """,
        (guide_id, subject_id, version, event_id, iso(NOW)),
    )
    conn.commit()
    conn.close()


def insert_checkpoint(
    *, guide_id=GUIDE_A, cursor="cursor_reconcile_01", generation=1
):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO guide_shop_event_checkpoints (
            guide_os_id, cursor, generation, updated_at
        ) VALUES (?, ?, ?, ?)
        """,
        (guide_id, cursor, generation, iso(NOW)),
    )
    conn.commit()
    conn.close()


def service(**kwargs):
    return GuideShopEventReconciliationService(
        database_path=db_module.DB_PATH, clock=lambda: NOW, **kwargs
    )


def seed_consistent(*, version=1, event_id="evt_reconcile_clean_01"):
    insert_event(event_id, version)
    insert_watermark(event_id, version)
    insert_checkpoint()


def test_clean_empty_database():
    report = service().reconcile()
    assert report.verdict == "CLEAN"
    assert all(count == 0 for _, count in report.metrics())


def test_clean_consistent_inbox_watermark_and_checkpoint():
    seed_consistent()
    report = service().reconcile()
    assert report.verdict == "CLEAN"
    assert report.inbox_delivered_count == 1
    assert sum(
        count
        for name, count in report.metrics()
        if name != "inbox_delivered_count"
    ) == 0


def test_abandoned_processing_needs_attention_but_fresh_does_not():
    insert_event(
        "evt_processing_old_01",
        1,
        state="processing",
        last_attempt_at=NOW - timedelta(minutes=6),
    )
    insert_event(
        "evt_processing_fresh_01",
        2,
        state="processing",
        last_attempt_at=NOW - timedelta(minutes=4),
    )
    insert_watermark("evt_processing_fresh_01", 2)
    insert_checkpoint()
    report = service().reconcile()
    assert report.abandoned_processing_count == 1
    assert report.verdict == "NEEDS_ATTENTION"


def test_dead_letter_needs_attention():
    insert_event(
        "evt_dead_reconcile_01",
        1,
        state="dead_letter",
        terminal_at=NOW,
    )
    insert_watermark("evt_dead_reconcile_01", 1)
    insert_checkpoint()
    report = service().reconcile()
    assert report.inbox_dead_letter_count == 1
    assert report.dead_letter_count == 1
    assert report.verdict == "NEEDS_ATTENTION"


def test_internal_aggregate_gap_is_counted():
    insert_event("evt_gap_02", 2, state="stale")
    insert_event("evt_gap_04", 4)
    insert_watermark("evt_gap_04", 4)
    insert_checkpoint()
    report = service().reconcile()
    assert report.aggregate_gap_count == 1
    assert report.verdict == "NEEDS_ATTENTION"


def test_first_observed_version_greater_than_one_is_not_gap():
    seed_consistent(version=4, event_id="evt_first_four_01")
    report = service().reconcile()
    assert report.aggregate_gap_count == 0
    assert report.verdict == "CLEAN"


def test_equal_version_collision_is_counted():
    insert_event("evt_collision_a_01", 2)
    insert_event("evt_collision_b_01", 2, state="stale")
    insert_watermark("evt_collision_a_01", 2)
    insert_checkpoint()
    report = service().reconcile()
    assert report.equal_version_collision_count == 1
    assert report.verdict == "NEEDS_ATTENTION"


def test_missing_and_mismatched_watermarks_are_counted():
    insert_event("evt_missing_watermark_01", 1, subject_id="vis_missing_watermark")
    insert_event("evt_mismatch_watermark_01", 2, subject_id="vis_bad_watermark")
    insert_watermark(
        "evt_mismatch_watermark_01", 1, subject_id="vis_bad_watermark"
    )
    insert_checkpoint()
    report = service().reconcile()
    assert report.missing_watermark_count == 1
    assert report.watermark_mismatch_count == 1


def test_inbox_without_checkpoint_and_checkpoint_without_inbox():
    insert_event("evt_no_checkpoint_01", 1, guide_id=GUIDE_A)
    insert_watermark("evt_no_checkpoint_01", 1, guide_id=GUIDE_A)
    insert_checkpoint(guide_id=GUIDE_B)
    report = service().reconcile()
    assert report.inbox_without_checkpoint_count == 1
    assert report.checkpoint_without_inbox_count == 1


def test_invalid_checkpoint_cursor_and_generation_are_counted():
    conn = get_connection()
    conn.execute("PRAGMA ignore_check_constraints = ON")
    conn.execute(
        """
        INSERT INTO guide_shop_event_checkpoints (
            guide_os_id, cursor, generation, updated_at
        ) VALUES (?, 'bad cursor', 0, ?)
        """,
        (GUIDE_A, iso(NOW)),
    )
    conn.commit()
    conn.close()
    report = service().reconcile()
    assert report.invalid_checkpoint_count == 1
    assert report.verdict == "NEEDS_ATTENTION"


def test_counts_are_deterministic_independent_of_insertion_order():
    def populate(order):
        for event_id, version, state in order:
            insert_event(event_id, version, state=state)
        insert_watermark("evt_deterministic_04", 4)
        insert_checkpoint()
        return service().reconcile()

    values = [
        ("evt_deterministic_02", 2, "stale"),
        ("evt_deterministic_04", 4, "delivered"),
        ("evt_deterministic_04b", 4, "stale"),
    ]
    first = populate(values)
    conn = get_connection()
    conn.execute("DELETE FROM guide_shop_event_watermarks")
    conn.execute("DELETE FROM guide_shop_event_checkpoints")
    conn.execute("DELETE FROM guide_shop_event_inbox")
    conn.commit()
    conn.close()
    second = populate(list(reversed(values)))
    assert first == second


def test_one_consistent_snapshot_during_concurrent_writer():
    seed_consistent()

    def writer():
        insert_event(
            "evt_snapshot_late_01",
            1,
            guide_id=GUIDE_B,
            subject_id="vis_snapshot_late",
            state="dead_letter",
            terminal_at=NOW,
        )

    report = service(after_snapshot_started=writer).reconcile()
    assert report.verdict == "CLEAN"
    assert report.inbox_dead_letter_count == 0
    assert service().reconcile().dead_letter_count == 1


def test_cli_clean_and_attention_exit_codes_and_safe_output():
    clean = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True
    )
    assert clean.returncode == 0
    assert clean.stdout.startswith("verdict=CLEAN\n")
    sensitive_event = "evt_sensitive_reconciliation_value"
    sensitive_subject = "vis_sensitive_reconciliation_value"
    insert_event(
        sensitive_event,
        1,
        subject_id=sensitive_subject,
        state="dead_letter",
        terminal_at=NOW,
    )
    attention = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True
    )
    assert attention.returncode == 2
    assert attention.stdout.startswith("verdict=NEEDS_ATTENTION\n")
    output = clean.stdout + clean.stderr + attention.stdout + attention.stderr
    for forbidden in (sensitive_event, sensitive_subject, GUIDE_A, str(db_module.DB_PATH)):
        assert forbidden not in output
    assert all(
        line.startswith("verdict=")
        or (line.rsplit("=", 1)[0].replace("_", "").isalpha() and line.rsplit("=", 1)[1].isdigit())
        for line in attention.stdout.splitlines()
    )


def test_reconciliation_is_logically_read_only_and_has_no_runtime_imports():
    seed_consistent()
    conn = get_connection()
    before = list(conn.iterdump())
    schema_version = conn.execute("PRAGMA schema_version").fetchone()[0]
    conn.close()
    service().reconcile()
    conn = get_connection()
    assert list(conn.iterdump()) == before
    assert conn.execute("PRAGMA schema_version").fetchone()[0] == schema_version
    conn.close()
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "--apply",
        "repair",
        "replay",
        "reset",
        "delete",
        "import bot",
        "import config",
        "aiogram",
        "aiohttp",
        "BOT_TOKEN",
    ):
        assert forbidden not in source
    rejected = subprocess.run(
        [sys.executable, str(SCRIPT), "--apply"],
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 1
    assert rejected.stdout == "verdict=EXECUTION_FAILURE\n"
    assert rejected.stderr == ""


def test_wal_backup_restore_and_quick_check(tmp_path):
    seed_consistent()
    assert service().reconcile().verdict == "CLEAN"
    source = get_connection()
    assert source.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    destination_path = tmp_path / "reconciliation-backup.db"
    destination = sqlite3.connect(destination_path)
    source.backup(destination)
    source.close()
    assert destination.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    destination.close()
    restored = GuideShopEventReconciliationService(
        database_path=destination_path, clock=lambda: NOW
    ).reconcile()
    assert restored.verdict == "CLEAN"
