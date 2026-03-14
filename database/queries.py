import sqlite3

from database.db import get_connection, run_write_with_retry

def create_tour(
    user_id: int,
    company: str,
    city: str,
    start_date: str,
    end_date: str,
    status: str,
    income: int | None = None,
    payment_status: str = "unpaid",
    note: str | None = None,
    entry_type: str = "tour",
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
          AND status IN ('reserved', 'confirmed')
          AND start_date <= ?
          AND end_date >= ?
        ORDER BY start_date ASC
        """,
        (user_id, month_end, month_start),
    )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_tour_by_id(user_id: int, tour_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, user_id, company, city, start_date, end_date, status, income, payment_status, note, entry_type
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
          AND status IN ('reserved', 'confirmed')
          AND income IS NOT NULL
          AND entry_type = 'tour'
        """,
        (user_id,),
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
          AND status IN ('reserved', 'confirmed')
          AND payment_status = 'unpaid'
          AND entry_type = 'tour'
        """,
        (user_id,),
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
          AND status IN ('reserved', 'confirmed')
          AND entry_type = 'tour'
        """,
        (user_id,),
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
          AND status IN ('reserved', 'confirmed')
          AND entry_type = 'tour'
        ORDER BY start_date ASC
        """,
        (user_id,),
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
                WHEN entry_type = 'day_off' THEN 1
                ELSE 0
            END,
            start_date,
            end_date,
            id
        """,
        (user_id, target_date, target_date),
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

