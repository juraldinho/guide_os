import logging
import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator, Callable, TypeVar

from utils.constants import STATUS_RESERVED, STATUS_CONFIRMED
from utils.guide_os_identity import (
    GuideOsIdentityMigrationError,
    is_canonical_guide_os_id,
    new_guide_os_id,
)

import os

DB_PATH = os.getenv("DATABASE_PATH", "guide_os.db")

SQLITE_TIMEOUT_SECONDS = 5
SQLITE_BUSY_TIMEOUT_MS = 5000
SQLITE_WRITE_RETRY_ATTEMPTS = 3
SQLITE_WRITE_RETRY_DELAY_SECONDS = 0.2

# Test-only hook executed after backfill begins; must raise to inject failure.
_GUIDE_OS_ID_MIGRATION_FAILURE_HOOK: Callable[[], None] | None = None

# Test-only hook executed after BEGIN IMMEDIATE, before schema work.
_INIT_DB_PAUSE_HOOK: Callable[[], None] | None = None

GUIDE_OS_ID_IMMUTABLE_TRIGGER = "trg_users_guide_os_id_immutable"

logger = logging.getLogger(__name__)

T = TypeVar("T")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row

    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


@contextmanager
def get_db_connection() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def run_write_with_retry(operation: Callable[[sqlite3.Connection], T]) -> T:
    last_error: sqlite3.OperationalError | None = None

    for attempt in range(1, SQLITE_WRITE_RETRY_ATTEMPTS + 1):
        try:
            with get_db_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                result = operation(conn)
                conn.commit()
                return result

        except sqlite3.OperationalError as exc:
            error_text = str(exc).lower()
            is_lock_error = "locked" in error_text or "busy" in error_text

            if not is_lock_error:
                raise

            last_error = exc

            logger.warning(
                "SQLite write attempt %s/%s failed due to lock: %s",
                attempt,
                SQLITE_WRITE_RETRY_ATTEMPTS,
                exc,
            )

            if attempt < SQLITE_WRITE_RETRY_ATTEMPTS:
                time.sleep(SQLITE_WRITE_RETRY_DELAY_SECONDS)
            else:
                logger.exception("SQLite write failed after retries")

    if last_error is not None:
        raise last_error

    raise RuntimeError("Unexpected SQLite retry flow reached")


def _ensure_guide_os_id_column(cursor: sqlite3.Cursor) -> None:
    cursor.execute("PRAGMA table_info(users)")
    user_columns = [row["name"] for row in cursor.fetchall()]
    if "guide_os_id" in user_columns:
        return
    cursor.execute("ALTER TABLE users ADD COLUMN guide_os_id TEXT")


def _fail_closed_identity_check(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        SELECT guide_os_id
        FROM users
        WHERE guide_os_id IS NOT NULL AND guide_os_id != ''
        """
    )
    seen: set[str] = set()
    for row in cursor.fetchall():
        value = row["guide_os_id"]
        if not is_canonical_guide_os_id(value):
            raise GuideOsIdentityMigrationError(
                "Guide OS identity migration failed"
            )
        if value in seen:
            raise GuideOsIdentityMigrationError(
                "Guide OS identity migration failed"
            )
        seen.add(value)

    cursor.execute(
        """
        SELECT guide_os_id
        FROM users
        WHERE guide_os_id IS NOT NULL AND guide_os_id != ''
        GROUP BY guide_os_id
        HAVING COUNT(*) > 1
        """
    )
    if cursor.fetchone() is not None:
        raise GuideOsIdentityMigrationError(
            "Guide OS identity migration failed"
        )


def _backfill_missing_guide_os_ids(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        SELECT user_id
        FROM users
        WHERE guide_os_id IS NULL OR guide_os_id = ''
        ORDER BY user_id
        """
    )
    missing_rows = cursor.fetchall()
    assigned: set[str] = set()
    for row in missing_rows:
        identity = new_guide_os_id()
        while identity in assigned:
            identity = new_guide_os_id()
        assigned.add(identity)
        cursor.execute(
            "UPDATE users SET guide_os_id = ? WHERE user_id = ?",
            (identity, row["user_id"]),
        )


def _ensure_guide_os_id_unique_index(cursor: sqlite3.Cursor) -> None:
    try:
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_guide_os_id
            ON users(guide_os_id)
            """
        )
    except sqlite3.IntegrityError as exc:
        raise GuideOsIdentityMigrationError(
            "Guide OS identity migration failed"
        ) from exc


def _ensure_guide_os_id_immutability_trigger(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS {GUIDE_OS_ID_IMMUTABLE_TRIGGER}
        BEFORE UPDATE OF guide_os_id ON users
        FOR EACH ROW
        WHEN
            OLD.guide_os_id IS NOT NULL
            AND OLD.guide_os_id != ''
            AND (
                NEW.guide_os_id IS NULL
                OR NEW.guide_os_id = ''
                OR NEW.guide_os_id != OLD.guide_os_id
            )
        BEGIN
            SELECT RAISE(ABORT, 'guide_os_id is immutable');
        END
        """
    )


def _migrate_guide_os_identity(
    conn: sqlite3.Connection, cursor: sqlite3.Cursor
) -> None:
    """Add, validate, backfill, index, and protect guide_os_id atomically.

    Uses a SAVEPOINT so any failure rolls back every write from this migration
    attempt without silently repairing malformed or duplicate identities.
    """
    cursor.execute("SAVEPOINT guide_os_identity_migration")
    try:
        _ensure_guide_os_id_column(cursor)
        _fail_closed_identity_check(cursor)
        _backfill_missing_guide_os_ids(cursor)

        if _GUIDE_OS_ID_MIGRATION_FAILURE_HOOK is not None:
            _GUIDE_OS_ID_MIGRATION_FAILURE_HOOK()

        _fail_closed_identity_check(cursor)
        _ensure_guide_os_id_unique_index(cursor)
        _ensure_guide_os_id_immutability_trigger(cursor)
        cursor.execute("RELEASE SAVEPOINT guide_os_identity_migration")
    except GuideOsIdentityMigrationError:
        cursor.execute("ROLLBACK TO SAVEPOINT guide_os_identity_migration")
        cursor.execute("RELEASE SAVEPOINT guide_os_identity_migration")
        raise
    except Exception as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT guide_os_identity_migration")
        cursor.execute("RELEASE SAVEPOINT guide_os_identity_migration")
        raise GuideOsIdentityMigrationError(
            "Guide OS identity migration failed"
        ) from exc


def _init_db_schema(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tours (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        company TEXT NOT NULL,
        city TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        status TEXT NOT NULL,
        income INTEGER,
        payment_status TEXT DEFAULT 'unpaid',
        note TEXT,
        entry_type TEXT NOT NULL DEFAULT 'tour',
        tour_group_id TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("PRAGMA table_info(tours)")
    columns = [row["name"] for row in cursor.fetchall()]

    if "entry_type" not in columns:
        cursor.execute(
            "ALTER TABLE tours ADD COLUMN entry_type TEXT NOT NULL DEFAULT 'tour'"
        )

    if "tour_group_id" not in columns:
        cursor.execute(
            "ALTER TABLE tours ADD COLUMN tour_group_id TEXT"
        )

    if "title" not in columns:
        cursor.execute("ALTER TABLE tours ADD COLUMN title TEXT")

    if "start_time" not in columns:
        cursor.execute("ALTER TABLE tours ADD COLUMN start_time TEXT")

    if "end_time" not in columns:
        cursor.execute("ALTER TABLE tours ADD COLUMN end_time TEXT")

    if "source" not in columns:
        cursor.execute(
            "ALTER TABLE tours ADD COLUMN source TEXT NOT NULL DEFAULT 'guide_os_bot'"
        )

    if "day_locations_json" not in columns:
        cursor.execute("ALTER TABLE tours ADD COLUMN day_locations_json TEXT")

    cursor.execute(
        "UPDATE tours SET title = company WHERE title IS NULL AND entry_type = 'tour'"
    )

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_tours_user_dates
    ON tours(user_id, start_date, end_date)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_tours_user_status_entry_type
    ON tours(user_id, status, entry_type)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_tours_user_payment_status
    ON tours(user_id, payment_status)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_tours_user_group
    ON tours(user_id, tour_group_id)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        last_seen TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("PRAGMA table_info(users)")
    user_columns = [row["name"] for row in cursor.fetchall()]

    if "first_seen" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN first_seen TEXT"
        )

    if "last_seen" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN last_seen TEXT"
        )

    if "notifications_enabled" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN notifications_enabled INTEGER NOT NULL DEFAULT 0"
        )

    if "notification_time" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN notification_time TEXT NOT NULL DEFAULT '21:00'"
        )

    if "last_tour_reminder_date" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN last_tour_reminder_date TEXT"
        )

    if "display_name" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN display_name TEXT"
        )

    _migrate_guide_os_identity(conn, cursor)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_users_last_seen
    ON users(last_seen)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS personal_places (
        public_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 100),
        category TEXT CHECK(category IS NULL OR length(category) <= 100),
        general_location TEXT CHECK(
            general_location IS NULL OR length(general_location) <= 200
        ),
        landmark TEXT CHECK(landmark IS NULL OR length(landmark) <= 200),
        note TEXT CHECK(note IS NULL OR length(note) <= 500),
        status TEXT NOT NULL CHECK(status IN ('active', 'inactive')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(
            length(public_id) = 38
            AND substr(public_id, 1, 6) = 'place_'
            AND substr(public_id, 7) NOT GLOB '*[^0-9a-f]*'
        ),
        UNIQUE(public_id, user_id),
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_personal_places_owner_status
    ON personal_places(user_id, status, created_at, public_id)
    """)

    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_personal_places_no_delete
    BEFORE DELETE ON personal_places
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'personal places use deactivation');
    END
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS personal_place_entries (
        public_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        personal_place_id TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        purchase_amount_minor INTEGER CHECK(
            purchase_amount_minor IS NULL OR purchase_amount_minor >= 0
        ),
        received_income_minor INTEGER CHECK(
            received_income_minor IS NULL OR received_income_minor >= 0
        ),
        received_points INTEGER CHECK(
            received_points IS NULL OR received_points > 0
        ),
        currency TEXT CHECK(
            currency IS NULL OR (
                length(currency) = 3 AND currency = upper(currency)
            )
        ),
        note TEXT CHECK(note IS NULL OR length(note) <= 500),
        status TEXT NOT NULL CHECK(status IN ('active', 'inactive')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(
            length(public_id) = 38
            AND substr(public_id, 1, 6) = 'entry_'
            AND substr(public_id, 7) NOT GLOB '*[^0-9a-f]*'
        ),
        CHECK(
            COALESCE(purchase_amount_minor, 0) > 0
            OR COALESCE(received_income_minor, 0) > 0
            OR COALESCE(received_points, 0) > 0
        ),
        CHECK(
            (
                purchase_amount_minor IS NULL
                AND received_income_minor IS NULL
                AND currency IS NULL
            )
            OR (
                (purchase_amount_minor IS NOT NULL OR received_income_minor IS NOT NULL)
                AND currency IS NOT NULL
            )
        ),
        FOREIGN KEY(user_id) REFERENCES users(user_id),
        FOREIGN KEY(personal_place_id, user_id)
            REFERENCES personal_places(public_id, user_id)
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_personal_place_entries_owner_status
    ON personal_place_entries(user_id, status, occurred_at, public_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_personal_place_entries_place
    ON personal_place_entries(
        user_id, personal_place_id, status, occurred_at, public_id
    )
    """)

    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_personal_place_entries_no_delete
    BEFORE DELETE ON personal_place_entries
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'personal place entries use deactivation');
    END
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guide_shop_link_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guide_os_id TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        audience TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('issued', 'consumed', 'revoked')),
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        consumed_at TEXT,
        revoked_at TEXT
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_guide_shop_link_requests_guide
    ON guide_shop_link_requests(guide_os_id, audience)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guide_shop_link_exchanges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link_exchange_id TEXT NOT NULL UNIQUE,
        link_request_id INTEGER NOT NULL UNIQUE,
        guide_os_id TEXT NOT NULL,
        service_subject TEXT NOT NULL,
        guide_membership_ref TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN (
            'awaiting_guide_confirmation', 'active', 'revoked',
            'expired', 'conflict'
        )),
        token_expires_at TEXT NOT NULL,
        exchange_expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(link_request_id) REFERENCES guide_shop_link_requests(id)
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_guide_shop_link_exchanges_scope
    ON guide_shop_link_exchanges(
        service_subject, guide_membership_ref, link_exchange_id
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guide_shop_link_exchange_evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link_exchange_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('active', 'revoked', 'conflict')),
        evidence_ref TEXT NOT NULL UNIQUE,
        occurred_at TEXT NOT NULL,
        UNIQUE(link_exchange_id, status),
        FOREIGN KEY(link_exchange_id)
            REFERENCES guide_shop_link_exchanges(link_exchange_id)
    )
    """)

    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_guide_shop_link_exchanges_binding_immutable
    BEFORE UPDATE ON guide_shop_link_exchanges
    FOR EACH ROW
    WHEN
        NEW.id IS NOT OLD.id
        OR NEW.link_exchange_id IS NOT OLD.link_exchange_id
        OR NEW.link_request_id IS NOT OLD.link_request_id
        OR NEW.guide_os_id IS NOT OLD.guide_os_id
        OR NEW.service_subject IS NOT OLD.service_subject
        OR NEW.guide_membership_ref IS NOT OLD.guide_membership_ref
        OR NEW.token_expires_at IS NOT OLD.token_expires_at
        OR NEW.exchange_expires_at IS NOT OLD.exchange_expires_at
        OR NEW.created_at IS NOT OLD.created_at
    BEGIN
        SELECT RAISE(ABORT, 'link exchange binding is immutable');
    END
    """)

    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_guide_shop_link_exchange_evidence_immutable
    BEFORE UPDATE ON guide_shop_link_exchange_evidence
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'link exchange evidence is immutable');
    END
    """)

    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_guide_shop_link_exchange_evidence_no_delete
    BEFORE DELETE ON guide_shop_link_exchange_evidence
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'link exchange evidence is immutable');
    END
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guide_shop_link_jti_replay (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        jti_hash TEXT NOT NULL UNIQUE,
        claimed_at TEXT NOT NULL,
        retain_until TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guide_shop_lifecycle_jti_replay (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        jti_hash TEXT NOT NULL UNIQUE,
        claimed_at TEXT NOT NULL,
        retain_until TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guide_shop_navigation_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_hash TEXT NOT NULL UNIQUE,
        telegram_user_id INTEGER NOT NULL,
        route_kind TEXT NOT NULL,
        object_id TEXT,
        cursor TEXT,
        points_status TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        consumed_at TEXT,
        revoked_at TEXT,
        status TEXT NOT NULL CHECK(status IN ('issued', 'consumed', 'revoked'))
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_guide_shop_navigation_user_status
    ON guide_shop_navigation_tokens(telegram_user_id, status)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guide_shop_event_inbox (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        event_version TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        producer TEXT NOT NULL,
        guide_os_id TEXT NOT NULL,
        subject_type TEXT NOT NULL,
        subject_id TEXT NOT NULL,
        aggregate_version INTEGER NOT NULL CHECK(aggregate_version >= 1),
        state TEXT NOT NULL CHECK(state IN (
            'pending', 'processing', 'delivered', 'stale', 'dead_letter'
        )),
        received_at TEXT NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
        max_attempts INTEGER NOT NULL DEFAULT 5 CHECK(
            max_attempts >= 1 AND max_attempts <= 20
        ),
        next_attempt_at TEXT,
        last_attempt_at TEXT,
        terminal_at TEXT,
        CHECK(attempt_count <= max_attempts)
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_guide_shop_event_inbox_pending
    ON guide_shop_event_inbox(state, received_at, occurred_at, event_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_guide_shop_event_inbox_aggregate
    ON guide_shop_event_inbox(
        guide_os_id, subject_type, subject_id, aggregate_version
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guide_shop_event_watermarks (
        guide_os_id TEXT NOT NULL,
        subject_type TEXT NOT NULL,
        subject_id TEXT NOT NULL,
        highest_aggregate_version INTEGER NOT NULL CHECK(
            highest_aggregate_version >= 1
        ),
        event_id TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(guide_os_id, subject_type, subject_id),
        FOREIGN KEY(event_id) REFERENCES guide_shop_event_inbox(event_id)
    )
    """)

    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_guide_shop_event_inbox_content_immutable
    BEFORE UPDATE ON guide_shop_event_inbox
    FOR EACH ROW
    WHEN
        NEW.event_id IS NOT OLD.event_id
        OR NEW.event_type IS NOT OLD.event_type
        OR NEW.event_version IS NOT OLD.event_version
        OR NEW.schema_version IS NOT OLD.schema_version
        OR NEW.occurred_at IS NOT OLD.occurred_at
        OR NEW.producer IS NOT OLD.producer
        OR NEW.guide_os_id IS NOT OLD.guide_os_id
        OR NEW.subject_type IS NOT OLD.subject_type
        OR NEW.subject_id IS NOT OLD.subject_id
        OR NEW.aggregate_version IS NOT OLD.aggregate_version
        OR NEW.received_at IS NOT OLD.received_at
    BEGIN
        SELECT RAISE(ABORT, 'event inbox content is immutable');
    END
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guide_shop_event_checkpoints (
        guide_os_id TEXT PRIMARY KEY,
        cursor TEXT NOT NULL,
        generation INTEGER NOT NULL CHECK(generation >= 1),
        updated_at TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        event_name TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_created_at
    ON events(created_at)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_user_created_at
    ON events(user_id, created_at)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_name_created_at
    ON events(event_name, created_at)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS miniapp_idempotency (
        user_id INTEGER NOT NULL,
        endpoint TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        body_hash TEXT NOT NULL,
        status_code INTEGER NOT NULL,
        response_body TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, endpoint, idempotency_key)
    )
    """)
    cursor.execute(
        """
        UPDATE tours
        SET status = ?
        WHERE status = 'Бронь'
        """,
        (STATUS_RESERVED,),
    )

    cursor.execute(
        """
        UPDATE tours
        SET status = ?
        WHERE status = 'Занято'
        """,
        (STATUS_CONFIRMED,),
    )
    logger.info("SQLite status migration checked")


def init_db() -> None:
    """Initialize schema under an exclusive SQLite write lock.

    BEGIN IMMEDIATE serializes concurrent init_db callers so PRAGMA inspection
    and ALTER TABLE decisions cannot race. The lock is held until commit so
    writers that take BEGIN IMMEDIATE wait for migration to finish.

    WAL mode is enabled before BEGIN IMMEDIATE (it cannot change inside a
    transaction) and is not set on every connection, which previously raced
    with the exclusive init lock.
    """
    last_error: sqlite3.OperationalError | None = None

    for attempt in range(1, SQLITE_WRITE_RETRY_ATTEMPTS + 1):
        try:
            with get_db_connection() as conn:
                try:
                    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                    if str(mode).lower() != "wal":
                        conn.execute("PRAGMA journal_mode = WAL")
                    conn.execute("BEGIN IMMEDIATE")
                    if _INIT_DB_PAUSE_HOOK is not None:
                        _INIT_DB_PAUSE_HOOK()
                    _init_db_schema(conn)
                    conn.commit()
                    logger.info(
                        "SQLite initialized with WAL, busy_timeout and indexes"
                    )
                    return
                except Exception:
                    conn.rollback()
                    raise
        except sqlite3.OperationalError as exc:
            error_text = str(exc).lower()
            if "locked" not in error_text and "busy" not in error_text:
                raise
            last_error = exc
            logger.warning(
                "SQLite init attempt %s/%s failed due to lock: %s",
                attempt,
                SQLITE_WRITE_RETRY_ATTEMPTS,
                exc,
            )
            if attempt < SQLITE_WRITE_RETRY_ATTEMPTS:
                time.sleep(SQLITE_WRITE_RETRY_DELAY_SECONDS)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected SQLite init retry flow reached")



def ensure_db_ready() -> None:
    """Deterministic readiness before operations that require migrated schema."""
    init_db()


def create_sqlite_backup(source_path: str, destination_path: str) -> None:
    """Create and verify an online SQLite backup, including committed WAL data."""
    source = sqlite3.connect(source_path, timeout=SQLITE_TIMEOUT_SECONDS)
    destination = sqlite3.connect(
        destination_path,
        timeout=SQLITE_TIMEOUT_SECONDS,
    )
    try:
        source.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        destination.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        source.backup(destination)
        result = destination.execute("PRAGMA quick_check").fetchone()
        if result is None or result[0] != "ok":
            raise RuntimeError("SQLite backup verification failed")
    finally:
        destination.close()
        source.close()
