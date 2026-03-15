import logging
import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator, Callable, TypeVar


import os

DB_PATH = os.getenv("DATABASE_PATH", "guide_os.db")

SQLITE_TIMEOUT_SECONDS = 5
SQLITE_BUSY_TIMEOUT_MS = 5000
SQLITE_WRITE_RETRY_ATTEMPTS = 3
SQLITE_WRITE_RETRY_DELAY_SECONDS = 0.2

logger = logging.getLogger(__name__)

T = TypeVar("T")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row

    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
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


def init_db() -> None:
    with get_db_connection() as conn:
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

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_last_seen
        ON users(last_seen)
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

        conn.commit()
        logger.info("SQLite initialized with WAL, busy_timeout and indexes")
