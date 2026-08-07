import sqlite3
import uuid

from database.db import get_connection, run_write_with_retry

from utils.constants import (
    PAYMENT_UNPAID,
    ENTRY_TYPE_TOUR,
    ENTRY_TYPE_DAY_OFF,
    STATUS_RESERVED,
    STATUS_CONFIRMED,
)

def create_tour(
    user_id: int,
    company: str,
    city: str,
    start_date: str,
    end_date: str,
    status: str,
    income: int | None = None,
    payment_status: str = PAYMENT_UNPAID,
    note: str | None = None,
    entry_type: str = ENTRY_TYPE_TOUR,
    tour_group_id: str | None = None,
) -> None:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO tours (
                user_id,
                company,
                city,
                start_date,
                end_date,
                status,
                income,
                payment_status,
                note,
                entry_type,
                tour_group_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                company,
                city,
                start_date,
                end_date,
                status,
                income,
                payment_status,
                note,
                entry_type,
                tour_group_id,
            ),
        )

    run_write_with_retry(operation)

def get_tours_for_month(user_id: int, month_start: str, month_end: str) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, company, city, start_date, end_date, status, income, payment_status, note, entry_type
        FROM tours
        WHERE user_id = ?
          AND status IN (?, ?)
          AND start_date <= ?
          AND end_date >= ?
        ORDER BY start_date ASC
        """,
        (user_id, STATUS_RESERVED, STATUS_CONFIRMED, month_end, month_start),
    )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_tour_by_id(user_id: int, tour_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, user_id, company, city, start_date, end_date, status, income, payment_status, note, entry_type, tour_group_id
        FROM tours
        WHERE id = ? AND user_id = ?
        LIMIT 1
        """,
        (tour_id, user_id),
    )

    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None

def delete_tour_by_id(user_id: int, tour_id: int) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM tours
            WHERE id = ? AND user_id = ?
            """,
            (tour_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)

def delete_tours_by_group_id(user_id: int, tour_group_id: str) -> int:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM tours
            WHERE tour_group_id = ? AND user_id = ?
            """,
            (tour_group_id, user_id),
        )

        return cursor.rowcount

    return run_write_with_retry(operation)

def update_tour_company(user_id: int, tour_id: int, company: str) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET company = ?
            WHERE id = ? AND user_id = ?
            """,
            (company, tour_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)

def update_tour_company_by_group(user_id: int, tour_group_id: str, company: str) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET company = ?
            WHERE tour_group_id = ? AND user_id = ?
            """,
            (company, tour_group_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)

def update_tour_city(user_id: int, tour_id: int, city: str) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET city = ?
            WHERE id = ? AND user_id = ?
            """,
            (city, tour_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)

def update_tour_city_by_group(user_id: int, tour_group_id: str, city: str) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET city = ?
            WHERE tour_group_id = ? AND user_id = ?
            """,
            (city, tour_group_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)

def update_tour_income(user_id: int, tour_id: int, income: int) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET income = ?
            WHERE id = ? AND user_id = ?
            """,
            (income, tour_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)

def update_tour_income_by_group(user_id: int, tour_group_id: str, income: int) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET income = ?
            WHERE tour_group_id = ? AND user_id = ?
            """,
            (income, tour_group_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)

def update_tour_note(user_id: int, tour_id: int, note: str | None) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET note = ?
            WHERE id = ? AND user_id = ?
            """,
            (note, tour_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)

def update_tour_note_by_group(user_id: int, tour_group_id: str, note: str | None) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET note = ?
            WHERE tour_group_id = ? AND user_id = ?
            """,
            (note, tour_group_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)

def update_tour_status(user_id: int, tour_id: int, status: str) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET status = ?
            WHERE id = ? AND user_id = ?
            """,
            (status, tour_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)


def update_tour_status_by_group(user_id: int, tour_group_id: str, status: str) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET status = ?
            WHERE tour_group_id = ? AND user_id = ?
            """,
            (status, tour_group_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)


def update_tour_payment_status(user_id: int, tour_id: int, payment_status: str) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET payment_status = ?
            WHERE id = ? AND user_id = ?
            """,
            (payment_status, tour_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)

def update_tour_payment_status_by_group(user_id: int, tour_group_id: str, payment_status: str) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET payment_status = ?
            WHERE tour_group_id = ? AND user_id = ?
            """,
            (payment_status, tour_group_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)

def update_tour_dates(user_id: int, tour_id: int, start_date: str, end_date: str) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tours
            SET start_date = ?, end_date = ?
            WHERE id = ? AND user_id = ?
            """,
            (start_date, end_date, tour_id, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)

def get_total_income(user_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COALESCE(
            SUM(income * (julianday(end_date) - julianday(start_date) + 1)), 0
        ) AS total_income
        FROM tours
        WHERE user_id = ?
          AND status IN (?, ?)
          AND income IS NOT NULL
          AND entry_type = ?
        """,
        (user_id, STATUS_RESERVED, STATUS_CONFIRMED, ENTRY_TYPE_TOUR),
    )

    row = cursor.fetchone()
    conn.close()

    return int(row["total_income"])


def get_unpaid_tours_count(user_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*) AS unpaid_count
        FROM tours
        WHERE user_id = ?
          AND status IN (?, ?)
          AND payment_status = ?
          AND entry_type = ?
        """,
        (
            user_id,
            STATUS_RESERVED,
            STATUS_CONFIRMED,
            PAYMENT_UNPAID,
            ENTRY_TYPE_TOUR,
        ),
    )

    row = cursor.fetchone()
    conn.close()

    return int(row["unpaid_count"])

def get_total_tours_count(user_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*) AS total_count
        FROM tours
        WHERE user_id = ?
          AND status IN (?, ?)
          AND entry_type = ?
        """,
        (user_id, STATUS_RESERVED, STATUS_CONFIRMED, ENTRY_TYPE_TOUR),
    )

    row = cursor.fetchone()
    conn.close()

    return int(row["total_count"]) if row else 0

def get_all_tours_for_stats(user_id: int) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, company, city, start_date, end_date, status, income, payment_status, note, entry_type
        FROM tours
        WHERE user_id = ?
          AND status IN (?, ?)
          AND entry_type = ?
        ORDER BY start_date ASC
        """,
        (user_id, STATUS_RESERVED, STATUS_CONFIRMED, ENTRY_TYPE_TOUR),
    )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]

def get_tours_by_group_id(user_id: int, tour_group_id: str) -> list[sqlite3.Row]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM tours
        WHERE user_id = ? AND tour_group_id = ?
        ORDER BY start_date, end_date, id
        """,
        (user_id, tour_group_id),
    )

    rows = cursor.fetchall()
    conn.close()
    return rows

def get_tours_for_date(user_id: int, target_date: str) -> list[sqlite3.Row]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM tours
        WHERE user_id = ?
          AND start_date <= ?
          AND end_date >= ?
        ORDER BY
            CASE
                WHEN entry_type = ? THEN 1
                ELSE 0
            END,
            start_date,
            end_date,
            id
        """,
        (user_id, target_date, target_date, ENTRY_TYPE_DAY_OFF),
    )

    rows = cursor.fetchall()
    conn.close()
    return rows

def get_tours_in_range(user_id: int, range_start: str, range_end: str) -> list[sqlite3.Row]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM tours
        WHERE user_id = ?
          AND start_date <= ?
          AND end_date >= ?
        ORDER BY start_date, end_date, id
        """,
        (user_id, range_end, range_start),
    )

    rows = cursor.fetchall()
    conn.close()
    return rows

def get_tours_for_month_raw(user_id: int, month_start: str, month_end: str) -> list[sqlite3.Row]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM tours
        WHERE user_id = ?
          AND start_date <= ?
          AND end_date >= ?
        ORDER BY start_date, end_date, id
        """,
        (user_id, month_end, month_start),
    )

    rows = cursor.fetchall()
    conn.close()
    return rows

def register_user(user_id: int) -> None:
    guide_os_id = str(uuid.uuid4())

    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO users (user_id, guide_os_id)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_seen = CURRENT_TIMESTAMP
            """,
            (user_id, guide_os_id),
        )

    run_write_with_retry(operation)


def get_guide_os_id(user_id: int) -> str | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT guide_os_id FROM users WHERE user_id = ? LIMIT 1",
        (user_id,),
    )

    row = cursor.fetchone()
    conn.close()

    return row["guide_os_id"] if row else None


def create_guide_shop_link_request(
    guide_os_id: str,
    token_hash: str,
    audience: str,
    created_at: str,
    expires_at: str,
) -> None:
    def operation(conn):
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE guide_shop_link_requests
            SET status = 'revoked', revoked_at = ?
            WHERE guide_os_id = ? AND audience = ? AND status = 'issued'
            """,
            (created_at, guide_os_id, audience),
        )
        cursor.execute(
            """
            INSERT INTO guide_shop_link_requests (
                guide_os_id, token_hash, audience, status, created_at, expires_at
            )
            VALUES (?, ?, ?, 'issued', ?, ?)
            """,
            (guide_os_id, token_hash, audience, created_at, expires_at),
        )

    run_write_with_retry(operation)


def get_guide_shop_link_request(token_hash: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM guide_shop_link_requests WHERE token_hash = ? LIMIT 1",
        (token_hash,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def consume_guide_shop_link_request(request_id: int, consumed_at: str) -> bool:
    def operation(conn):
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE guide_shop_link_requests
            SET status = 'consumed', consumed_at = ?
            WHERE id = ? AND status = 'issued' AND expires_at > ?
            """,
            (consumed_at, request_id, consumed_at),
        )
        return cursor.rowcount == 1

    return run_write_with_retry(operation)


def revoke_guide_shop_link_requests(
    guide_os_id: str, audience: str, revoked_at: str
) -> int:
    def operation(conn):
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE guide_shop_link_requests
            SET status = 'revoked', revoked_at = ?
            WHERE guide_os_id = ? AND audience = ? AND status = 'issued'
            """,
            (revoked_at, guide_os_id, audience),
        )
        return cursor.rowcount

    return run_write_with_retry(operation)


def create_guide_shop_navigation_token(
    token_hash: str,
    telegram_user_id: int,
    route_kind: str,
    object_id: str | None,
    cursor: str | None,
    points_status: str | None,
    created_at: str,
    expires_at: str,
) -> None:
    def operation(conn):
        conn.execute(
            """
            INSERT INTO guide_shop_navigation_tokens (
                token_hash, telegram_user_id, route_kind, object_id, cursor,
                points_status, created_at, expires_at, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'issued')
            """,
            (
                token_hash,
                telegram_user_id,
                route_kind,
                object_id,
                cursor,
                points_status,
                created_at,
                expires_at,
            ),
        )

    run_write_with_retry(operation)


def get_guide_shop_navigation_token(token_hash: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT * FROM guide_shop_navigation_tokens
        WHERE token_hash = ?
        LIMIT 1
        """,
        (token_hash,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def consume_guide_shop_navigation_token(
    token_hash: str, telegram_user_id: int, resolved_at: str
) -> bool:
    def operation(conn):
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE guide_shop_navigation_tokens
            SET status = 'consumed', consumed_at = ?
            WHERE token_hash = ?
              AND telegram_user_id = ?
              AND status = 'issued'
              AND expires_at > ?
            """,
            (resolved_at, token_hash, telegram_user_id, resolved_at),
        )
        return cursor.rowcount == 1

    return run_write_with_retry(operation)


def revoke_guide_shop_navigation_tokens(
    telegram_user_id: int, revoked_at: str
) -> int:
    def operation(conn):
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE guide_shop_navigation_tokens
            SET status = 'revoked', revoked_at = ?
            WHERE telegram_user_id = ? AND status = 'issued'
            """,
            (revoked_at, telegram_user_id),
        )
        return cursor.rowcount

    return run_write_with_retry(operation)
    
def track_event(user_id: int | None, event_name: str) -> None:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO events (user_id, event_name)
            VALUES (?, ?)
            """,
            (user_id, event_name),
        )

    run_write_with_retry(operation)


def get_total_users_count() -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total_count FROM users")
    row = cursor.fetchone()
    conn.close()

    return int(row["total_count"]) if row else 0


def get_new_users_today_count() -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*) AS total_count
        FROM users
        WHERE date(first_seen) = date('now')
        """
    )
    row = cursor.fetchone()
    conn.close()

    return int(row["total_count"]) if row else 0


def get_active_users_last_days(days: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        SELECT COUNT(*) AS total_count
        FROM users
        WHERE datetime(last_seen) >= datetime('now', '-{days} days')
        """
    )
    row = cursor.fetchone()
    conn.close()

    return int(row["total_count"]) if row else 0


def get_event_count_today(event_name: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*) AS total_count
        FROM events
        WHERE event_name = ?
          AND date(created_at) = date('now')
        """,
        (event_name,),
    )
    row = cursor.fetchone()
    conn.close()

    return int(row["total_count"]) if row else 0

def get_unique_event_users_today(event_name: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(DISTINCT user_id) AS total_count
        FROM events
        WHERE event_name = ?
          AND user_id IS NOT NULL
          AND date(created_at) = date('now')
        """,
        (event_name,),
    )
    row = cursor.fetchone()
    conn.close()

    return int(row["total_count"]) if row else 0


def get_repeat_active_users_last_days(days: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        SELECT COUNT(*) AS total_count
        FROM users
        WHERE datetime(last_seen) >= datetime('now', '-{days} days')
          AND datetime(first_seen) < datetime('now', '-{days} days')
        """
    )
    row = cursor.fetchone()
    conn.close()

    return int(row["total_count"]) if row else 0


def get_user_notification_settings(user_id: int) -> dict:
    register_user(user_id)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT notifications_enabled, notification_time
        FROM users
        WHERE user_id = ?
        LIMIT 1
        """,
        (user_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "notifications_enabled": False,
            "notification_time": "21:00",
        }

    return {
        "notifications_enabled": bool(row["notifications_enabled"]),
        "notification_time": row["notification_time"] or "21:00",
    }


def set_notifications_enabled(user_id: int, enabled: bool) -> None:
    guide_os_id = str(uuid.uuid4())

    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO users (user_id, notifications_enabled, guide_os_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                notifications_enabled = excluded.notifications_enabled
            """,
            (user_id, int(enabled), guide_os_id),
        )

    run_write_with_retry(operation)


def set_notification_time(user_id: int, time_text: str) -> None:
    guide_os_id = str(uuid.uuid4())

    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO users (
                user_id, notification_time, last_tour_reminder_date, guide_os_id
            )
            VALUES (?, ?, NULL, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                notification_time = excluded.notification_time,
                last_tour_reminder_date = NULL
            """,
            (user_id, time_text, guide_os_id),
        )

    run_write_with_retry(operation)


def get_users_with_notifications_enabled() -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT user_id, notification_time, last_tour_reminder_date
        FROM users
        WHERE notifications_enabled = 1
        """
    )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def update_last_tour_reminder_date(user_id: int, reminder_date: str) -> None:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE users
            SET last_tour_reminder_date = ?
            WHERE user_id = ?
            """,
            (reminder_date, user_id),
        )

    run_write_with_retry(operation)


def get_entries_for_reminder_date(user_id: int, target_date: str) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, company, city, start_date, end_date, status, note, entry_type
        FROM tours
        WHERE user_id = ?
          AND status IN (?, ?)
          AND start_date <= ?
          AND end_date >= ?
          AND entry_type IN (?, ?)
        ORDER BY
            CASE
                WHEN entry_type = ? THEN 1
                ELSE 0
            END,
            start_date,
            end_date,
            id
        """,
        (
            user_id,
            STATUS_RESERVED,
            STATUS_CONFIRMED,
            target_date,
            target_date,
            ENTRY_TYPE_TOUR,
            ENTRY_TYPE_DAY_OFF,
            ENTRY_TYPE_DAY_OFF,
        ),
    )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]

def reset_last_tour_reminder_date(user_id: int) -> None:
    def operation(conn):
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE users
            SET last_tour_reminder_date = NULL
            WHERE user_id = ?
            """,
            (user_id,),
        )

    run_write_with_retry(operation)
    
def get_all_user_ids() -> list[int]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT user_id
        FROM users
        ORDER BY user_id
        """
    )

    rows = cursor.fetchall()
    conn.close()

    return [row["user_id"] for row in rows]

def has_user_tours(user_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT 1 FROM tours
        WHERE user_id = ?
        LIMIT 1
        """,
        (user_id,),
    )

    result = cursor.fetchone()
    conn.close()

    return result is not None


def get_user_profile(user_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT user_id, display_name, first_seen
        FROM users
        WHERE user_id = ?
        LIMIT 1
        """,
        (user_id,),
    )

    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def update_user_display_name(user_id: int, display_name: str) -> bool:
    def operation(conn):
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE users
            SET display_name = ?
            WHERE user_id = ?
            """,
            (display_name, user_id),
        )

        return cursor.rowcount > 0

    return run_write_with_retry(operation)
