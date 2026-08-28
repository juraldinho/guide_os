import sqlite3

from database.db import (
    ensure_db_ready,
    get_connection,
    get_db_connection,
    run_write_with_retry,
)
from utils.guide_os_identity import new_guide_os_id, validate_guide_os_id

from utils.constants import (
    PAYMENT_UNPAID,
    ENTRY_TYPE_TOUR,
    ENTRY_TYPE_DAY_OFF,
    STATUS_RESERVED,
    STATUS_CONFIRMED,
    SOURCE_GUIDE_OS_BOT,
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
    title: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    source: str = SOURCE_GUIDE_OS_BOT,
    day_locations_json: str | None = None,
) -> int:
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
                tour_group_id,
                title,
                start_time,
                end_time,
                source,
                day_locations_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                title,
                start_time,
                end_time,
                source,
                day_locations_json,
            ),
        )
        return cursor.lastrowid

    return run_write_with_retry(operation)

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

def update_tour_extended_by_group(
    user_id: int,
    tour_group_id: str,
    company: str | None = None,
    city: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    income: int | None = None,
    payment_status: str | None = None,
    note: str | None = None,
    title: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    source: str | None = None,
    day_locations_json: str | None = None,
) -> bool:
    fields: list[str] = []
    values: list[object] = []

    mapping = {
        "company": company,
        "city": city,
        "start_date": start_date,
        "end_date": end_date,
        "status": status,
        "income": income,
        "payment_status": payment_status,
        "note": note,
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "source": source,
        "day_locations_json": day_locations_json,
    }

    for column, value in mapping.items():
        if value is not None:
            fields.append(f"{column} = ?")
            values.append(value)

    if not fields:
        return False

    def operation(conn):
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE tours
            SET {", ".join(fields)}
            WHERE user_id = ? AND tour_group_id = ?
            """,
            (*values, user_id, tour_group_id),
        )
        return cursor.rowcount > 0

    return run_write_with_retry(operation)


def update_tour_extended(
    user_id: int,
    tour_id: int,
    company: str | None = None,
    city: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    income: int | None = None,
    payment_status: str | None = None,
    note: str | None = None,
    title: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    source: str | None = None,
    day_locations_json: str | None = None,
) -> bool:
    fields: list[str] = []
    values: list[object] = []

    mapping = {
        "company": company,
        "city": city,
        "start_date": start_date,
        "end_date": end_date,
        "status": status,
        "income": income,
        "payment_status": payment_status,
        "note": note,
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "source": source,
        "day_locations_json": day_locations_json,
    }

    for column, value in mapping.items():
        if value is not None:
            fields.append(f"{column} = ?")
            values.append(value)

    if not fields:
        return False

    def operation(conn):
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE tours
            SET {", ".join(fields)}
            WHERE user_id = ? AND id = ?
            """,
            (*values, user_id, tour_id),
        )
        return cursor.rowcount > 0

    return run_write_with_retry(operation)


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
    ensure_db_ready()
    guide_os_id = new_guide_os_id()

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


def get_user_id_by_guide_os_id(guide_os_id: str) -> int | None:
    identity = validate_guide_os_id(guide_os_id)
    conn = get_connection()
    row = conn.execute(
        "SELECT user_id FROM users WHERE guide_os_id = ? LIMIT 1",
        (identity,),
    ).fetchone()
    conn.close()
    return int(row["user_id"]) if row else None


def ensure_staging_guide_user(guide_os_id: str) -> int:
    """Create a Telegram-less staging user bound to an authenticated guide_os_id."""
    import uuid

    identity = validate_guide_os_id(guide_os_id)
    existing = get_user_id_by_guide_os_id(identity)
    if existing is not None:
        return existing
    staging_user_id = -((uuid.UUID(identity).int % (10**15)) + 1)

    def operation(conn):
        row = conn.execute(
            "SELECT user_id FROM users WHERE guide_os_id = ? LIMIT 1",
            (identity,),
        ).fetchone()
        if row is not None:
            return int(row["user_id"])
        try:
            conn.execute(
                "INSERT INTO users (user_id, guide_os_id) VALUES (?, ?)",
                (staging_user_id, identity),
            )
        except sqlite3.IntegrityError:
            row = conn.execute(
                "SELECT user_id FROM users WHERE guide_os_id = ? LIMIT 1",
                (identity,),
            ).fetchone()
            if row is not None:
                return int(row["user_id"])
            raise
        return staging_user_id

    return run_write_with_retry(operation)


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


def get_active_guide_shop_guide_os_ids() -> list[str]:
    ensure_db_ready()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT guide_os_id
            FROM guide_shop_link_exchanges
            WHERE status = 'active'
            ORDER BY guide_os_id
            """
        ).fetchall()
    finally:
        conn.close()
    return [validate_guide_os_id(row["guide_os_id"]) for row in rows]


def create_personal_place(
    *,
    public_id: str,
    user_id: int,
    name: str,
    category: str | None,
    general_location: str | None,
    landmark: str | None,
    note: str | None,
    timestamp: str,
) -> None:
    def operation(conn):
        conn.execute(
            """
            INSERT INTO personal_places (
                public_id, user_id, name, category, general_location,
                landmark, note, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                public_id,
                user_id,
                name,
                category,
                general_location,
                landmark,
                note,
                timestamp,
                timestamp,
            ),
        )

    run_write_with_retry(operation)


def get_personal_place(user_id: int, public_id: str) -> dict | None:
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT public_id, user_id, name, category, general_location,
                   landmark, note, status, created_at, updated_at
            FROM personal_places
            WHERE user_id = ? AND public_id = ?
            LIMIT 1
            """,
            (user_id, public_id),
        ).fetchone()
    return dict(row) if row else None


def list_personal_places(
    user_id: int,
    *,
    include_inactive: bool = False,
) -> list[dict]:
    with get_db_connection() as conn:
        if include_inactive:
            rows = conn.execute(
                """
                SELECT public_id, user_id, name, category, general_location,
                       landmark, note, status, created_at, updated_at
                FROM personal_places
                WHERE user_id = ?
                ORDER BY created_at, public_id
                """,
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT public_id, user_id, name, category, general_location,
                       landmark, note, status, created_at, updated_at
                FROM personal_places
                WHERE user_id = ? AND status = 'active'
                ORDER BY created_at, public_id
                """,
                (user_id,),
            ).fetchall()
    return [dict(row) for row in rows]


def update_personal_place(
    *,
    user_id: int,
    public_id: str,
    name: str,
    category: str | None,
    general_location: str | None,
    landmark: str | None,
    note: str | None,
    timestamp: str,
) -> bool:
    def operation(conn):
        cursor = conn.execute(
            """
            UPDATE personal_places
            SET name = ?, category = ?, general_location = ?, landmark = ?,
                note = ?, updated_at = ?
            WHERE user_id = ? AND public_id = ? AND status = 'active'
            """,
            (
                name,
                category,
                general_location,
                landmark,
                note,
                timestamp,
                user_id,
                public_id,
            ),
        )
        return cursor.rowcount == 1

    return run_write_with_retry(operation)


def deactivate_personal_place(
    user_id: int,
    public_id: str,
    timestamp: str,
) -> bool:
    def operation(conn):
        cursor = conn.execute(
            """
            UPDATE personal_places
            SET status = 'inactive', updated_at = ?
            WHERE user_id = ? AND public_id = ? AND status = 'active'
            """,
            (timestamp, user_id, public_id),
        )
        return cursor.rowcount == 1

    return run_write_with_retry(operation)


def create_personal_place_entry(
    *,
    public_id: str,
    user_id: int,
    personal_place_id: str,
    occurred_at: str,
    purchase_amount_minor: int | None,
    received_income_minor: int | None,
    received_points: int | None,
    currency: str | None,
    note: str | None,
    timestamp: str,
) -> bool:
    def operation(conn):
        place = conn.execute(
            """
            SELECT 1
            FROM personal_places
            WHERE user_id = ? AND public_id = ? AND status = 'active'
            """,
            (user_id, personal_place_id),
        ).fetchone()
        if place is None:
            return False
        conn.execute(
            """
            INSERT INTO personal_place_entries (
                public_id, user_id, personal_place_id, occurred_at,
                purchase_amount_minor, received_income_minor,
                received_points, currency, note, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                public_id,
                user_id,
                personal_place_id,
                occurred_at,
                purchase_amount_minor,
                received_income_minor,
                received_points,
                currency,
                note,
                timestamp,
                timestamp,
            ),
        )
        return True

    return run_write_with_retry(operation)


def get_personal_place_entry(user_id: int, public_id: str) -> dict | None:
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT public_id, user_id, personal_place_id, occurred_at,
                   purchase_amount_minor, received_income_minor,
                   received_points, currency, note, status,
                   created_at, updated_at
            FROM personal_place_entries
            WHERE user_id = ? AND public_id = ?
            LIMIT 1
            """,
            (user_id, public_id),
        ).fetchone()
    return dict(row) if row else None


def list_personal_place_entries(
    user_id: int,
    *,
    personal_place_id: str | None = None,
    include_inactive: bool = False,
) -> list[dict]:
    clauses = ["user_id = ?"]
    parameters: list[object] = [user_id]
    if personal_place_id is not None:
        clauses.append("personal_place_id = ?")
        parameters.append(personal_place_id)
    if not include_inactive:
        clauses.append("status = 'active'")
    where = " AND ".join(clauses)
    with get_db_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT public_id, user_id, personal_place_id, occurred_at,
                   purchase_amount_minor, received_income_minor,
                   received_points, currency, note, status,
                   created_at, updated_at
            FROM personal_place_entries
            WHERE {where}
            ORDER BY occurred_at, created_at, public_id
            """,
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


def update_personal_place_entry(
    *,
    user_id: int,
    public_id: str,
    occurred_at: str,
    purchase_amount_minor: int | None,
    received_income_minor: int | None,
    received_points: int | None,
    currency: str | None,
    note: str | None,
    timestamp: str,
) -> bool:
    def operation(conn):
        cursor = conn.execute(
            """
            UPDATE personal_place_entries
            SET occurred_at = ?, purchase_amount_minor = ?,
                received_income_minor = ?, received_points = ?,
                currency = ?, note = ?, updated_at = ?
            WHERE user_id = ? AND public_id = ? AND status = 'active'
            """,
            (
                occurred_at,
                purchase_amount_minor,
                received_income_minor,
                received_points,
                currency,
                note,
                timestamp,
                user_id,
                public_id,
            ),
        )
        return cursor.rowcount == 1

    return run_write_with_retry(operation)


def deactivate_personal_place_entry(
    user_id: int,
    public_id: str,
    timestamp: str,
) -> bool:
    def operation(conn):
        cursor = conn.execute(
            """
            UPDATE personal_place_entries
            SET status = 'inactive', updated_at = ?
            WHERE user_id = ? AND public_id = ? AND status = 'active'
            """,
            (timestamp, user_id, public_id),
        )
        return cursor.rowcount == 1

    return run_write_with_retry(operation)


def create_guide_shop_link_request(
    guide_os_id: str,
    token_hash: str,
    audience: str,
    created_at: str,
    expires_at: str,
) -> None:
    identity = validate_guide_os_id(guide_os_id)

    def operation(conn):
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE guide_shop_link_requests
            SET status = 'revoked', revoked_at = ?
            WHERE guide_os_id = ? AND audience = ? AND status = 'issued'
            """,
            (created_at, identity, audience),
        )
        cursor.execute(
            """
            INSERT INTO guide_shop_link_requests (
                guide_os_id, token_hash, audience, status, created_at, expires_at
            )
            VALUES (?, ?, ?, 'issued', ?, ?)
            """,
            (identity, token_hash, audience, created_at, expires_at),
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


def create_guide_shop_link_exchange_atomic(
    *,
    token_hash: str,
    audience: str,
    link_exchange_id: str,
    service_subject: str,
    guide_membership_ref: str,
    transitioned_at: str,
    exchange_expires_at: str,
) -> tuple[str, dict | None]:
    """Consume one issued request and create its exchange in one transaction."""
    def operation(conn):
        request = conn.execute(
            """
            SELECT * FROM guide_shop_link_requests
            WHERE token_hash = ?
            LIMIT 1
            """,
            (token_hash,),
        ).fetchone()
        if request is None:
            return "unknown", None
        if request["audience"] != audience:
            return "wrong_audience", None
        if request["status"] != "issued":
            return request["status"], None
        if request["expires_at"] <= transitioned_at:
            return "expired", None
        try:
            validate_guide_os_id(request["guide_os_id"])
        except Exception:
            return "invalid_identity", None

        consumed = conn.execute(
            """
            UPDATE guide_shop_link_requests
            SET status = 'consumed', consumed_at = ?
            WHERE id = ?
              AND status = 'issued'
              AND audience = ?
              AND expires_at > ?
            """,
            (transitioned_at, request["id"], audience, transitioned_at),
        )
        if consumed.rowcount != 1:
            return "unavailable", None

        conn.execute(
            """
            INSERT INTO guide_shop_link_exchanges (
                link_exchange_id, link_request_id, guide_os_id,
                service_subject, guide_membership_ref, status,
                token_expires_at, exchange_expires_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'awaiting_guide_confirmation', ?, ?, ?, ?)
            """,
            (
                link_exchange_id,
                request["id"],
                request["guide_os_id"],
                service_subject,
                guide_membership_ref,
                request["expires_at"],
                exchange_expires_at,
                transitioned_at,
                transitioned_at,
            ),
        )
        row = conn.execute(
            "SELECT * FROM guide_shop_link_exchanges WHERE link_exchange_id = ?",
            (link_exchange_id,),
        ).fetchone()
        return "created", dict(row)

    return run_write_with_retry(operation)


def create_or_activate_guide_profile_link_exchange(
    *,
    guide_os_id: str,
    audience: str,
    token_hash: str,
    link_exchange_id: str,
    evidence_ref: str,
    service_subject: str,
    guide_membership_ref: str,
    now_iso: str,
    token_expires_at: str,
    exchange_expires_at: str,
) -> tuple[str, dict | None]:
    """Owner/Manager verified-profile linking in one atomic transaction.

    Returns ("existing", row) for an idempotent retry of the exact binding,
    ("conflict", None) when another active association exists, and
    ("created", row) after creating and activating a normal exchange.
    """
    identity = validate_guide_os_id(guide_os_id)

    def operation(conn):
        active_rows = conn.execute(
            """
            SELECT * FROM guide_shop_link_exchanges
            WHERE service_subject = ?
              AND status = 'active'
              AND (guide_membership_ref = ? OR guide_os_id = ?)
            """,
            (service_subject, guide_membership_ref, identity),
        ).fetchall()
        for row in active_rows:
            if (
                row["guide_membership_ref"] == guide_membership_ref
                and row["guide_os_id"] == identity
            ):
                return "existing", dict(row)
        if active_rows:
            return "conflict", None

        # Recover the exact awaiting binding first so a retry after a partial
        # failure between creation and activation stays idempotent.
        awaiting = conn.execute(
            """
            SELECT link_exchange_id FROM guide_shop_link_exchanges
            WHERE service_subject = ?
              AND guide_membership_ref = ?
              AND guide_os_id = ?
              AND status = 'awaiting_guide_confirmation'
              AND exchange_expires_at > ?
            ORDER BY id LIMIT 1
            """,
            (service_subject, guide_membership_ref, identity, now_iso),
        ).fetchone()
        if awaiting is not None:
            target_id = awaiting["link_exchange_id"]
        else:
            conn.execute(
                """
                UPDATE guide_shop_link_requests
                SET status = 'revoked', revoked_at = ?
                WHERE guide_os_id = ? AND audience = ? AND status = 'issued'
                """,
                (now_iso, identity, audience),
            )
            cursor = conn.execute(
                """
                INSERT INTO guide_shop_link_requests (
                    guide_os_id, token_hash, audience, status,
                    created_at, expires_at, consumed_at
                ) VALUES (?, ?, ?, 'consumed', ?, ?, ?)
                """,
                (identity, token_hash, audience, now_iso, token_expires_at, now_iso),
            )
            conn.execute(
                """
                INSERT INTO guide_shop_link_exchanges (
                    link_exchange_id, link_request_id, guide_os_id,
                    service_subject, guide_membership_ref, status,
                    token_expires_at, exchange_expires_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'awaiting_guide_confirmation', ?, ?, ?, ?)
                """,
                (
                    link_exchange_id,
                    cursor.lastrowid,
                    identity,
                    service_subject,
                    guide_membership_ref,
                    token_expires_at,
                    exchange_expires_at,
                    now_iso,
                    now_iso,
                ),
            )
            target_id = link_exchange_id

        updated = conn.execute(
            """
            UPDATE guide_shop_link_exchanges
            SET status = 'active', updated_at = ?
            WHERE link_exchange_id = ? AND status = 'awaiting_guide_confirmation'
            """,
            (now_iso, target_id),
        )
        if updated.rowcount != 1:
            return "unavailable", None
        conn.execute(
            """
            INSERT INTO guide_shop_link_exchange_evidence (
                link_exchange_id, status, evidence_ref, occurred_at
            ) VALUES (?, 'active', ?, ?)
            """,
            (target_id, evidence_ref, now_iso),
        )
        row = conn.execute(
            "SELECT * FROM guide_shop_link_exchanges WHERE link_exchange_id = ?",
            (target_id,),
        ).fetchone()
        return "created", dict(row)

    return run_write_with_retry(operation)


def get_guide_shop_link_exchange_scoped(
    link_exchange_id: str, service_subject: str, guide_membership_ref: str
) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT * FROM guide_shop_link_exchanges
        WHERE link_exchange_id = ?
          AND service_subject = ?
          AND guide_membership_ref = ?
        LIMIT 1
        """,
        (link_exchange_id, service_subject, guide_membership_ref),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_guide_shop_link_exchange_for_service(
    link_exchange_id: str, service_subject: str
) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT * FROM guide_shop_link_exchanges
        WHERE link_exchange_id = ? AND service_subject = ?
        LIMIT 1
        """,
        (link_exchange_id, service_subject),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def transition_guide_shop_link_exchange(
    *,
    link_exchange_id: str,
    service_subject: str,
    guide_membership_ref: str,
    expected_status: str,
    new_status: str,
    transitioned_at: str,
    evidence_ref: str | None,
) -> tuple[str, dict | None]:
    def operation(conn):
        row = conn.execute(
            """
            SELECT * FROM guide_shop_link_exchanges
            WHERE link_exchange_id = ?
              AND service_subject = ?
              AND guide_membership_ref = ?
            LIMIT 1
            """,
            (link_exchange_id, service_subject, guide_membership_ref),
        ).fetchone()
        if row is None:
            return "unknown", None
        if row["status"] != expected_status:
            return "invalid_transition", dict(row)

        updated = conn.execute(
            """
            UPDATE guide_shop_link_exchanges
            SET status = ?, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (new_status, transitioned_at, row["id"], expected_status),
        )
        if updated.rowcount != 1:
            return "invalid_transition", None
        if evidence_ref is not None:
            conn.execute(
                """
                INSERT INTO guide_shop_link_exchange_evidence (
                    link_exchange_id, status, evidence_ref, occurred_at
                ) VALUES (?, ?, ?, ?)
                """,
                (link_exchange_id, new_status, evidence_ref, transitioned_at),
            )
        current = conn.execute(
            "SELECT * FROM guide_shop_link_exchanges WHERE id = ?",
            (row["id"],),
        ).fetchone()
        return "transitioned", dict(current)

    return run_write_with_retry(operation)


def get_guide_shop_link_exchange_evidence_scoped(
    link_exchange_id: str, service_subject: str, guide_membership_ref: str
) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT e.link_exchange_id, x.guide_os_id, e.status,
               e.evidence_ref, e.occurred_at
        FROM guide_shop_link_exchanges AS x
        JOIN guide_shop_link_exchange_evidence AS e
          ON e.link_exchange_id = x.link_exchange_id
         AND e.status = x.status
        WHERE x.link_exchange_id = ?
          AND x.service_subject = ?
          AND x.guide_membership_ref = ?
        LIMIT 1
        """,
        (link_exchange_id, service_subject, guide_membership_ref),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def claim_guide_shop_link_jti(
    jti_hash: str, claimed_at: str, retain_until: str
) -> bool:
    def operation(conn):
        try:
            conn.execute(
                """
                INSERT INTO guide_shop_link_jti_replay (
                    jti_hash, claimed_at, retain_until
                ) VALUES (?, ?, ?)
                """,
                (jti_hash, claimed_at, retain_until),
            )
        except sqlite3.IntegrityError:
            return False
        return True

    return run_write_with_retry(operation)


def claim_guide_shop_lifecycle_jti(
    jti_hash: str, claimed_at: str, retain_until: str
) -> bool:
    def operation(conn):
        try:
            conn.execute(
                """
                INSERT INTO guide_shop_lifecycle_jti_replay (
                    jti_hash, claimed_at, retain_until
                ) VALUES (?, ?, ?)
                """,
                (jti_hash, claimed_at, retain_until),
            )
        except sqlite3.IntegrityError:
            return False
        return True

    return run_write_with_retry(operation)


def get_guide_shop_link_exchange_for_guide(
    link_exchange_id: str, guide_os_id: str
) -> dict | None:
    identity = validate_guide_os_id(guide_os_id)
    conn = get_connection()
    row = conn.execute(
        """
        SELECT * FROM guide_shop_link_exchanges
        WHERE link_exchange_id = ? AND guide_os_id = ?
        LIMIT 1
        """,
        (link_exchange_id, identity),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_guide_shop_link_exchange_evidence_for_guide(
    link_exchange_id: str, guide_os_id: str
) -> dict | None:
    identity = validate_guide_os_id(guide_os_id)
    conn = get_connection()
    row = conn.execute(
        """
        SELECT e.link_exchange_id, x.guide_os_id, e.status,
               e.evidence_ref, e.occurred_at
        FROM guide_shop_link_exchanges AS x
        JOIN guide_shop_link_exchange_evidence AS e
          ON e.link_exchange_id = x.link_exchange_id
         AND e.status = x.status
        WHERE x.link_exchange_id = ?
          AND x.guide_os_id = ?
        LIMIT 1
        """,
        (link_exchange_id, identity),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def transition_guide_shop_link_exchange_for_guide(
    *,
    link_exchange_id: str,
    guide_os_id: str,
    expected_status: str,
    new_status: str,
    transitioned_at: str,
    evidence_ref: str | None,
) -> tuple[str, dict | None]:
    identity = validate_guide_os_id(guide_os_id)

    def operation(conn):
        row = conn.execute(
            """
            SELECT * FROM guide_shop_link_exchanges
            WHERE link_exchange_id = ? AND guide_os_id = ?
            LIMIT 1
            """,
            (link_exchange_id, identity),
        ).fetchone()
        if row is None:
            return "unknown", None
        if row["status"] == new_status:
            return "identical", dict(row)
        if row["status"] != expected_status:
            return "invalid_transition", dict(row)

        updated = conn.execute(
            """
            UPDATE guide_shop_link_exchanges
            SET status = ?, updated_at = ?
            WHERE id = ? AND status = ? AND guide_os_id = ?
            """,
            (new_status, transitioned_at, row["id"], expected_status, identity),
        )
        if updated.rowcount != 1:
            return "invalid_transition", None
        if evidence_ref is not None:
            conn.execute(
                """
                INSERT INTO guide_shop_link_exchange_evidence (
                    link_exchange_id, status, evidence_ref, occurred_at
                ) VALUES (?, ?, ?, ?)
                """,
                (link_exchange_id, new_status, evidence_ref, transitioned_at),
            )
        current = conn.execute(
            "SELECT * FROM guide_shop_link_exchanges WHERE id = ?",
            (row["id"],),
        ).fetchone()
        return "transitioned", dict(current)

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
    ensure_db_ready()
    guide_os_id = new_guide_os_id()

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
    ensure_db_ready()
    guide_os_id = new_guide_os_id()

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
