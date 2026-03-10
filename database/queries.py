from database.db import get_connection


def create_tour(
    user_id: int,
    company: str,
    city: str,
    start_date: str,
    end_date: str,
    status: str,
    income: int | None = None,
    note: str | None = None,
) -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO tours (
            user_id, company, city, start_date, end_date, status, income, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, company, city, start_date, end_date, status, income, note),
    )

    conn.commit()
    conn.close()


def get_tours_for_month(user_id: int, month_start: str, month_end: str) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, company, city, start_date, end_date, status, income, payment_status, note
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


def get_total_income(user_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COALESCE(SUM(income), 0) AS total_income
        FROM tours
        WHERE user_id = ?
          AND status IN ('reserved', 'confirmed')
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
        """,
        (user_id,),
    )

    row = cursor.fetchone()
    conn.close()

    return int(row["unpaid_count"])
