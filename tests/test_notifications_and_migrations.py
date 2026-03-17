from database.db import get_connection, init_db
from database.queries import (
    create_tour,
    get_entries_for_reminder_date,
    get_user_notification_settings,
    set_notification_time,
    set_notifications_enabled,
    reset_last_tour_reminder_date,
)
from utils.constants import (
    STATUS_RESERVED,
    STATUS_CONFIRMED,
    ENTRY_TYPE_TOUR,
    PAYMENT_UNPAID,
)

TEST_USER = 123456


def test_reminder_sees_reserved_entry():
    create_tour(
        user_id=TEST_USER,
        company="Test Reserved",
        city="Самарканд",
        start_date="2026-06-10",
        end_date="2026-06-10",
        status=STATUS_RESERVED,
        payment_status=PAYMENT_UNPAID,
        entry_type=ENTRY_TYPE_TOUR,
    )

    entries = get_entries_for_reminder_date(TEST_USER, "2026-06-10")

    assert len(entries) == 1
    assert entries[0]["status"] == STATUS_RESERVED


def test_reminder_sees_confirmed_entry():
    create_tour(
        user_id=TEST_USER,
        company="Test Confirmed",
        city="Бухара",
        start_date="2026-06-11",
        end_date="2026-06-11",
        status=STATUS_CONFIRMED,
        payment_status=PAYMENT_UNPAID,
        entry_type=ENTRY_TYPE_TOUR,
    )

    entries = get_entries_for_reminder_date(TEST_USER, "2026-06-11")

    assert len(entries) == 1
    assert entries[0]["status"] == STATUS_CONFIRMED


def test_status_migration_converts_old_russian_values(monkeypatch):
    import database.db as db_module

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO tours (
            user_id, company, city, start_date, end_date, status,
            income, payment_status, note, entry_type
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            TEST_USER,
            "Old Reserved",
            "Самарканд",
            "2026-07-01",
            "2026-07-01",
            "Бронь",
            100,
            PAYMENT_UNPAID,
            None,
            ENTRY_TYPE_TOUR,
        ),
    )

    cursor.execute(
        """
        INSERT INTO tours (
            user_id, company, city, start_date, end_date, status,
            income, payment_status, note, entry_type
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            TEST_USER,
            "Old Confirmed",
            "Бухара",
            "2026-07-02",
            "2026-07-02",
            "Занято",
            100,
            PAYMENT_UNPAID,
            None,
            ENTRY_TYPE_TOUR,
        ),
    )

    conn.commit()
    conn.close()

    db_module.init_db()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM tours ORDER BY start_date")
    statuses = [row["status"] for row in cursor.fetchall()]
    conn.close()

    assert STATUS_RESERVED in statuses
    assert STATUS_CONFIRMED in statuses
    assert "Бронь" not in statuses
    assert "Занято" not in statuses


def test_notification_settings_and_reset():
    set_notification_time(TEST_USER, "18:30")
    set_notifications_enabled(TEST_USER, True)

    settings = get_user_notification_settings(TEST_USER)
    assert settings["notifications_enabled"] is True
    assert settings["notification_time"] == "18:30"

    reset_last_tour_reminder_date(TEST_USER)
