import sqlite3


DB_PATH = "guide_os.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
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

    conn.commit()
    conn.close()
