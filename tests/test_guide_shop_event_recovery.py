import concurrent.futures
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import subprocess
import sys

from database.db import get_connection, init_db
from services.guide_shop_event_inbox import GuideShopEventInboxService


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
GUIDE_ID = "123e4567-e89b-42d3-a456-426614174000"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "guide_shop_event_recovery.py"


class Clock:
    def __init__(self, value=NOW):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


def insert_event(
    event_id,
    *,
    state="processing",
    attempt_count=1,
    max_attempts=5,
    last_attempt_at=None,
    terminal_at=None,
    received_offset=0,
):
    last_attempt_at = last_attempt_at or NOW - timedelta(minutes=6)
    received_at = NOW - timedelta(minutes=20) + timedelta(seconds=received_offset)
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO guide_shop_event_inbox (
            event_id, event_type, event_version, schema_version, occurred_at,
            producer, guide_os_id, subject_type, subject_id,
            aggregate_version, state, received_at, attempt_count,
            max_attempts, last_attempt_at, terminal_at
        ) VALUES (?, 'visit.created', 'v1', '1.0.0', ?, 'guideshop',
                  ?, 'visit', ?, 1, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            (NOW - timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
            GUIDE_ID,
            f"vis_recovery_{event_id.removeprefix('evt_')}",
            state,
            received_at.isoformat().replace("+00:00", "Z"),
            attempt_count,
            max_attempts,
            (
                last_attempt_at.isoformat().replace("+00:00", "Z")
                if last_attempt_at is not None
                else None
            ),
            (
                terminal_at.isoformat().replace("+00:00", "Z")
                if terminal_at is not None
                else None
            ),
        ),
    )
    conn.commit()
    conn.close()


def row(event_id):
    conn = get_connection()
    stored = conn.execute(
        "SELECT * FROM guide_shop_event_inbox WHERE event_id = ?", (event_id,)
    ).fetchone()
    conn.close()
    return dict(stored)


def test_fresh_processing_row_is_untouched():
    insert_event("evt_fresh_01", last_attempt_at=NOW - timedelta(minutes=4))
    result = GuideShopEventInboxService(clock=Clock()).recover_abandoned(
        limit=100, apply=True
    )
    assert result.selected_count == 0
    assert row("evt_fresh_01")["state"] == "processing"


def test_expired_processing_returns_pending_without_resetting_attempts():
    insert_event("evt_expired_01", attempt_count=2)
    result = GuideShopEventInboxService(clock=Clock()).recover_abandoned(
        limit=100, apply=True
    )
    stored = row("evt_expired_01")
    assert (result.pending_count, result.dead_letter_count) == (1, 0)
    assert stored["state"] == "pending"
    assert stored["attempt_count"] == 2
    assert stored["next_attempt_at"] == "2026-08-20T12:00:00Z"


def test_exhausted_expired_processing_becomes_dead_letter():
    insert_event("evt_exhausted_01", attempt_count=5, max_attempts=5)
    result = GuideShopEventInboxService(clock=Clock()).recover_abandoned(
        limit=100, apply=True
    )
    stored = row("evt_exhausted_01")
    assert (result.pending_count, result.dead_letter_count) == (0, 1)
    assert stored["state"] == "dead_letter"
    assert stored["attempt_count"] == 5
    assert stored["terminal_at"] == "2026-08-20T12:00:00Z"


def test_recovery_limit_uses_deterministic_oldest_order():
    for index in range(4):
        insert_event(
            f"evt_order_{index}",
            last_attempt_at=NOW - timedelta(minutes=10 - index),
            received_offset=index,
        )
    result = GuideShopEventInboxService(clock=Clock()).recover_abandoned(
        limit=2, apply=True
    )
    assert result.pending_count == 2
    assert [row(f"evt_order_{index}")["state"] for index in range(4)] == [
        "pending",
        "pending",
        "processing",
        "processing",
    ]


def test_concurrent_recovery_has_exactly_one_winner():
    insert_event("evt_recovery_race_01")

    def recover():
        return GuideShopEventInboxService(clock=Clock()).recover_abandoned(
            limit=1, apply=True
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: recover(), range(2)))
    assert sum(result.pending_count for result in results) == 1
    assert row("evt_recovery_race_01")["state"] == "pending"


def test_stale_worker_cannot_overwrite_recovered_state_and_duplicate_is_possible():
    # Telegram may have accepted the first claim before this simulated crash.
    insert_event("evt_at_least_once_01", state="pending", attempt_count=0, last_attempt_at=None)
    clock = Clock()
    inbox = GuideShopEventInboxService(clock=clock)
    original_claim = inbox.claim_due()
    clock.advance(301)
    assert inbox.recover_abandoned(limit=1, apply=True).pending_count == 1
    replay_claim = inbox.claim_due()
    assert replay_claim.claim_attempt == original_claim.claim_attempt + 1
    assert inbox.mark_delivered(original_claim) is False
    assert inbox.mark_delivered(replay_claim) is True


def test_dead_letter_dry_run_does_not_change_rows():
    insert_event(
        "evt_dry_run_01",
        state="dead_letter",
        attempt_count=5,
        max_attempts=5,
        terminal_at=NOW - timedelta(minutes=1),
    )
    result = GuideShopEventInboxService(clock=Clock()).replay_dead_letters(
        limit=100, apply=False
    )
    assert (result.selected_count, result.replayed_count) == (1, 0)
    assert row("evt_dry_run_01")["state"] == "dead_letter"


def test_apply_grants_exactly_one_additional_attempt():
    insert_event(
        "evt_replay_01",
        state="dead_letter",
        attempt_count=5,
        max_attempts=5,
        terminal_at=NOW - timedelta(minutes=1),
    )
    inbox = GuideShopEventInboxService(clock=Clock())
    assert inbox.replay_dead_letters(limit=1, apply=True).replayed_count == 1
    stored = row("evt_replay_01")
    assert (stored["state"], stored["attempt_count"], stored["max_attempts"]) == (
        "pending",
        5,
        6,
    )
    assert inbox.claim_due().claim_attempt == 6


def test_early_dead_letter_replay_grants_only_one_attempt():
    insert_event(
        "evt_replay_early_01",
        state="dead_letter",
        attempt_count=1,
        max_attempts=5,
        terminal_at=NOW - timedelta(minutes=1),
    )
    inbox = GuideShopEventInboxService(clock=Clock())

    assert inbox.replay_dead_letters(limit=1, apply=True).replayed_count == 1
    stored = row("evt_replay_early_01")
    assert (stored["state"], stored["attempt_count"], stored["max_attempts"]) == (
        "pending",
        1,
        2,
    )

    claim = inbox.claim_due()
    assert claim.claim_attempt == 2
    assert inbox.mark_failed(claim).state == "dead_letter"
    stored = row("evt_replay_early_01")
    assert (stored["state"], stored["attempt_count"], stored["max_attempts"]) == (
        "dead_letter",
        2,
        2,
    )
    assert inbox.claim_due() is None


def test_repeated_replay_stays_bounded_at_twenty():
    insert_event(
        "evt_replay_cap_01",
        state="dead_letter",
        attempt_count=19,
        max_attempts=19,
        terminal_at=NOW - timedelta(minutes=1),
    )
    inbox = GuideShopEventInboxService(clock=Clock())
    assert inbox.replay_dead_letters(limit=1, apply=True).replayed_count == 1
    claim = inbox.claim_due()
    assert claim.claim_attempt == 20
    assert inbox.mark_failed(claim).state == "dead_letter"
    assert inbox.replay_dead_letters(limit=1, apply=True).selected_count == 0
    stored = row("evt_replay_cap_01")
    assert (stored["attempt_count"], stored["max_attempts"]) == (20, 20)


def test_concurrent_replay_does_not_grant_duplicate_attempts():
    insert_event(
        "evt_replay_race_01",
        state="dead_letter",
        attempt_count=5,
        max_attempts=5,
        terminal_at=NOW - timedelta(minutes=1),
    )

    def replay():
        return GuideShopEventInboxService(clock=Clock()).replay_dead_letters(
            limit=1, apply=True
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: replay(), range(2)))
    assert sum(result.replayed_count for result in results) == 1
    stored = row("evt_replay_race_01")
    assert (stored["state"], stored["max_attempts"]) == ("pending", 6)


def test_only_eligible_dead_letters_are_replayed():
    for state in ("delivered", "stale", "pending"):
        insert_event(f"evt_skip_{state}", state=state, last_attempt_at=None)
    insert_event(
        "evt_dead_cap_01",
        state="dead_letter",
        attempt_count=20,
        max_attempts=20,
        terminal_at=NOW,
    )
    result = GuideShopEventInboxService(clock=Clock()).replay_dead_letters(
        limit=100, apply=True
    )
    assert result.selected_count == 0
    assert all(row(f"evt_skip_{state}")["state"] == state for state in ("delivered", "stale", "pending"))
    assert row("evt_dead_cap_01")["state"] == "dead_letter"


def test_cli_dry_run_and_apply_output_only_sanitized_counts():
    event_id = "evt_private_cli_01"
    insert_event(
        event_id,
        state="dead_letter",
        attempt_count=5,
        max_attempts=5,
        terminal_at=NOW - timedelta(minutes=1),
    )
    dry = subprocess.run(
        [sys.executable, str(SCRIPT), "replay-dead-letter", "--limit", "1"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert dry.stdout.strip() == (
        "action=replay-dead-letter selected=1 replayed=0"
    )
    assert row(event_id)["state"] == "dead_letter"
    applied = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "replay-dead-letter",
            "--limit",
            "1",
            "--apply",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert applied.stdout.strip() == (
        "action=replay-dead-letter selected=1 replayed=1"
    )
    combined = dry.stdout + dry.stderr + applied.stdout + applied.stderr
    assert event_id not in combined
    assert GUIDE_ID not in combined


def test_cli_has_no_bot_network_or_runtime_imports():
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("import bot", "import config", "aiogram", "aiohttp", "BOT_TOKEN"):
        assert forbidden not in source
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "recover-abandoned", "--limit", "1"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.startswith("action=recover-abandoned selected=")


def test_rerun_wal_backup_restore_and_quick_check(tmp_path):
    insert_event("evt_backup_recovery_01")
    init_db()
    init_db()
    source = get_connection()
    assert source.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    destination = sqlite3.connect(tmp_path / "recovery-backup.db")
    source.backup(destination)
    source.close()
    assert destination.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert destination.execute(
        "SELECT state, attempt_count FROM guide_shop_event_inbox"
    ).fetchone() == ("processing", 1)
    destination.close()
