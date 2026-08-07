import sqlite3
import uuid

from database.db import get_connection, init_db
from database.queries import get_guide_os_id, register_user


def assert_uuid4(value: str) -> None:
    parsed = uuid.UUID(value)
    assert parsed.version == 4
    assert str(parsed) == value


def test_new_users_receive_stable_unique_uuid4_ids():
    register_user(101)
    first_id = get_guide_os_id(101)

    assert first_id is not None
    assert_uuid4(first_id)

    register_user(101)
    assert get_guide_os_id(101) == first_id

    register_user(202)
    second_id = get_guide_os_id(202)
    assert second_id is not None
    assert_uuid4(second_id)
    assert second_id != first_id


def test_init_db_backfills_pre_migration_user_once(monkeypatch, tmp_path):
    import database.db as db_module

    legacy_db = tmp_path / "legacy.db"
    monkeypatch.setenv("DATABASE_PATH", str(legacy_db))
    monkeypatch.setattr(db_module, "DB_PATH", str(legacy_db))

    conn = sqlite3.connect(legacy_db)
    conn.execute(
        """
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
            last_seen TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("INSERT INTO users (user_id) VALUES (303)")
    conn.commit()
    conn.close()

    init_db()
    backfilled_id = get_guide_os_id(303)
    assert backfilled_id is not None
    assert_uuid4(backfilled_id)

    init_db()
    assert get_guide_os_id(303) == backfilled_id


def test_unique_index_rejects_duplicate_guide_os_id():
    register_user(404)
    register_user(505)
    guide_os_id = get_guide_os_id(404)

    conn = get_connection()
    try:
        with conn:
            try:
                conn.execute(
                    "UPDATE users SET guide_os_id = ? WHERE user_id = ?",
                    (guide_os_id, 505),
                )
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError("duplicate guide_os_id was accepted")
    finally:
        conn.close()


def test_unknown_user_lookup_has_no_side_effect():
    assert get_guide_os_id(606) is None

    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM users WHERE user_id = ?", (606,)
    ).fetchone()
    conn.close()
    assert row is None


def test_registration_preserves_existing_fields_and_updates_only_last_seen():
    register_user(707)
    guide_os_id = get_guide_os_id(707)

    conn = get_connection()
    conn.execute(
        """
        UPDATE users
        SET first_seen = ?, last_seen = ?, notifications_enabled = ?,
            notification_time = ?, last_tour_reminder_date = ?, display_name = ?
        WHERE user_id = ?
        """,
        ("2020-01-01 00:00:00", "2020-01-02 00:00:00", 1,
         "18:30", "2020-01-03", "Test Guide", 707),
    )
    conn.commit()
    conn.close()

    register_user(707)

    conn = get_connection()
    row = dict(conn.execute("SELECT * FROM users WHERE user_id = 707").fetchone())
    conn.close()

    assert row["guide_os_id"] == guide_os_id
    assert row["first_seen"] == "2020-01-01 00:00:00"
    assert row["last_seen"] != "2020-01-02 00:00:00"
    assert row["notifications_enabled"] == 1
    assert row["notification_time"] == "18:30"
    assert row["last_tour_reminder_date"] == "2020-01-03"
    assert row["display_name"] == "Test Guide"
