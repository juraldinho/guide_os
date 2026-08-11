import sqlite3
import threading
import uuid
from pathlib import Path

import pytest

from database.db import (
    GUIDE_OS_ID_IMMUTABLE_TRIGGER,
    get_connection,
    init_db,
)
from database.queries import (
    get_guide_os_id,
    register_user,
    set_notification_time,
    set_notifications_enabled,
    update_user_display_name,
)
from utils.guide_os_identity import (
    GuideOsIdentityError,
    GuideOsIdentityMigrationError,
    is_canonical_guide_os_id,
    new_guide_os_id,
    validate_guide_os_id,
)


def assert_uuid4(value: str) -> None:
    assert is_canonical_guide_os_id(value)
    parsed = uuid.UUID(value)
    assert parsed.version == 4
    assert str(parsed) == value


def _user_columns(conn: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in conn.execute("PRAGMA table_info(users)")}


def _has_unique_index(conn: sqlite3.Connection) -> bool:
    rows = conn.execute("PRAGMA index_list(users)").fetchall()
    for row in rows:
        if row["name"] == "idx_users_guide_os_id" and row["unique"] == 1:
            return True
    return False


def _has_immutability_trigger(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (GUIDE_OS_ID_IMMUTABLE_TRIGGER,),
    ).fetchone()
    return row is not None


def _quick_check_ok(conn: sqlite3.Connection) -> bool:
    return conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_canonical_uuid4_validation_matrix():
    valid = new_guide_os_id()
    assert validate_guide_os_id(valid) == valid

    invalid_values = [
        None,
        123,
        True,
        "",
        " ",
        f" {valid}",
        f"{valid} ",
        valid.upper(),
        f"{{{valid}}}",
        f"urn:uuid:{valid}",
        "00000000-0000-0000-0000-000000000000",
        "123e4567-e89b-12d3-a456-426614174000",  # version 1
        "not-a-uuid",
    ]
    for value in invalid_values:
        assert is_canonical_guide_os_id(value) is False
        with pytest.raises(GuideOsIdentityError):
            validate_guide_os_id(value)


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


def test_all_user_creation_paths_assign_canonical_uuid():
    register_user(1001)
    set_notifications_enabled(1002, True)
    set_notification_time(1003, "19:00")

    for user_id in (1001, 1002, 1003):
        identity = get_guide_os_id(user_id)
        assert identity is not None
        assert_uuid4(identity)

    existing = get_guide_os_id(1001)
    set_notifications_enabled(1001, False)
    set_notification_time(1001, "20:00")
    assert get_guide_os_id(1001) == existing


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


def test_database_immutability_trigger_rejects_identity_mutation():
    register_user(808)
    original = get_guide_os_id(808)
    assert original is not None

    conn = get_connection()
    try:
        assert _has_immutability_trigger(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE users SET guide_os_id = ? WHERE user_id = ?",
                (new_guide_os_id(), 808),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE users SET guide_os_id = NULL WHERE user_id = ?",
                (808,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE users SET guide_os_id = '' WHERE user_id = ?",
                (808,),
            )
        conn.execute(
            "UPDATE users SET display_name = ? WHERE user_id = ?",
            ("Allowed Name", 808),
        )
        conn.commit()
    finally:
        conn.close()

    assert get_guide_os_id(808) == original
    assert update_user_display_name(808, "Service Path") is True
    assert get_guide_os_id(808) == original


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


def _prepare_legacy_db(path: Path, setup) -> None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    setup(conn)
    conn.commit()
    conn.close()


def test_migration_matrix_cases(monkeypatch, tmp_path):
    import database.db as db_module

    results = {}

    def run_case(name: str, setup, expect_success: bool):
        db_path = tmp_path / f"{name}.db"
        monkeypatch.setenv("DATABASE_PATH", str(db_path))
        monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
        db_module._GUIDE_OS_ID_MIGRATION_FAILURE_HOOK = None
        _prepare_legacy_db(db_path, setup)

        before = sqlite3.connect(db_path)
        before.row_factory = sqlite3.Row
        try:
            before_users = [
                dict(row) for row in before.execute("SELECT * FROM users").fetchall()
            ]
            before_columns = _user_columns(before)
        except sqlite3.OperationalError:
            before_users = []
            before_columns = set()
        before.close()

        if expect_success:
            init_db()
            init_db()
            conn = get_connection()
            users = [
                dict(row) for row in conn.execute("SELECT * FROM users ORDER BY user_id")
            ]
            assert _has_unique_index(conn)
            assert _has_immutability_trigger(conn)
            assert _quick_check_ok(conn)
            for user in users:
                assert_uuid4(user["guide_os_id"])
            identities = [user["guide_os_id"] for user in users]
            assert len(identities) == len(set(identities))
            conn.close()
            results[name] = {
                "result": "success",
                "users": len(users),
                "preserved_valid": True,
            }
        else:
            with pytest.raises(GuideOsIdentityMigrationError):
                init_db()
            after = sqlite3.connect(db_path)
            after.row_factory = sqlite3.Row
            try:
                after_users = [
                    dict(row) for row in after.execute("SELECT * FROM users").fetchall()
                ]
                after_columns = _user_columns(after)
            except sqlite3.OperationalError:
                after_users = []
                after_columns = set()
            assert len(after_users) == len(before_users)
            if "guide_os_id" not in before_columns:
                assert "guide_os_id" not in after_columns
            else:
                for before_row, after_row in zip(before_users, after_users, strict=True):
                    assert after_row.get("guide_os_id") == before_row.get("guide_os_id")
            assert _quick_check_ok(after)
            after.close()
            results[name] = {"result": "fail_closed", "users": len(after_users)}

    run_case(
        "fresh_empty",
        lambda conn: None,
        True,
    )

    def legacy_without_column(conn):
        conn.execute(
            """
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("INSERT INTO users (user_id) VALUES (1), (2)")

    run_case("legacy_without_guide_os_id", legacy_without_column, True)

    def mixed_valid_and_blank(conn):
        valid = str(uuid.uuid4())
        conn.execute(
            """
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                guide_os_id TEXT,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT INTO users (user_id, guide_os_id) VALUES (1, ?), (2, NULL), (3, '')",
            (valid,),
        )

    run_case("mixed_valid_and_null_blank", mixed_valid_and_blank, True)

    def malformed(conn):
        conn.execute(
            """
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                guide_os_id TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO users (user_id, guide_os_id) VALUES (1, ?)",
            ("not-a-uuid",),
        )

    run_case("malformed_non_empty", malformed, False)

    def uppercase(conn):
        value = str(uuid.uuid4()).upper()
        conn.execute(
            """
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                guide_os_id TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO users (user_id, guide_os_id) VALUES (1, ?)",
            (value,),
        )

    run_case("uppercase_uuid", uppercase, False)

    def non_v4(conn):
        conn.execute(
            """
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                guide_os_id TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO users (user_id, guide_os_id) VALUES (1, ?)",
            ("123e4567-e89b-12d3-a456-426614174000",),
        )

    run_case("non_v4_uuid", non_v4, False)

    def duplicates(conn):
        shared = str(uuid.uuid4())
        conn.execute(
            """
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                guide_os_id TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO users (user_id, guide_os_id) VALUES (1, ?), (2, ?)",
            (shared, shared),
        )

    run_case("duplicate_valid_uuids", duplicates, False)

    def already_migrated(conn):
        first = str(uuid.uuid4())
        second = str(uuid.uuid4())
        conn.execute(
            """
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                guide_os_id TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO users (user_id, guide_os_id) VALUES (1, ?), (2, ?)",
            (first, second),
        )

    run_case("already_migrated", already_migrated, True)

    # Injected failure after backfill begins
    db_path = tmp_path / "injected_failure.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))

    def legacy_for_hook(conn):
        conn.execute(
            """
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("INSERT INTO users (user_id) VALUES (9)")

    _prepare_legacy_db(db_path, legacy_for_hook)

    def boom():
        raise RuntimeError("injected migration failure")

    db_module._GUIDE_OS_ID_MIGRATION_FAILURE_HOOK = boom
    with pytest.raises(GuideOsIdentityMigrationError):
        init_db()
    db_module._GUIDE_OS_ID_MIGRATION_FAILURE_HOOK = None

    after = sqlite3.connect(db_path)
    after.row_factory = sqlite3.Row
    assert "guide_os_id" not in _user_columns(after)
    assert after.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 1
    assert _quick_check_ok(after)
    after.close()
    results["injected_failure_after_backfill"] = {"result": "rolled_back"}

    assert results["fresh_empty"]["result"] == "success"
    assert results["legacy_without_guide_os_id"]["result"] == "success"
    assert results["malformed_non_empty"]["result"] == "fail_closed"
    assert results["duplicate_valid_uuids"]["result"] == "fail_closed"


def _prepare_legacy_users(db_path, user_ids):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
            last_seen TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for user_id in user_ids:
        conn.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()


def _bind_tmp_db(monkeypatch, db_module, db_path):
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module._GUIDE_OS_ID_MIGRATION_FAILURE_HOOK = None
    db_module._INIT_DB_PAUSE_HOOK = None


def _run_threads(targets, *, join_timeout=15):
    errors: list[BaseException] = []

    def wrap(fn):
        def runner():
            try:
                fn()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        return runner

    threads = [threading.Thread(target=wrap(fn)) for fn in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=join_timeout)
        assert not thread.is_alive()
    assert errors == []
    return errors


def _assert_identity_state(conn, expected_user_ids, *, stable_pairs=None):
    users = {
        row["user_id"]: row["guide_os_id"]
        for row in conn.execute(
            "SELECT user_id, guide_os_id FROM users ORDER BY user_id"
        )
    }
    assert set(users) == set(expected_user_ids)
    identities = list(users.values())
    assert len(identities) == len(set(identities))
    for identity in identities:
        assert_uuid4(identity)
    assert _has_unique_index(conn)
    assert _has_immutability_trigger(conn)
    assert _quick_check_ok(conn)
    if stable_pairs:
        for user_id, identity in stable_pairs.items():
            assert users[user_id] == identity
    return users


def test_concurrent_repeated_init_db(monkeypatch, tmp_path):
    import database.db as db_module

    db_path = tmp_path / "concurrent_init.db"
    _bind_tmp_db(monkeypatch, db_module, db_path)
    _prepare_legacy_users(db_path, [10])

    barrier = threading.Barrier(4, timeout=5)
    _run_threads(
        [
            lambda: (barrier.wait(), init_db()),
            lambda: (barrier.wait(), init_db()),
            lambda: (barrier.wait(), init_db()),
            lambda: (barrier.wait(), init_db()),
        ]
    )

    conn = get_connection()
    users = _assert_identity_state(conn, [10])
    conn.close()

    init_db()
    assert get_guide_os_id(10) == users[10]


def test_concurrent_init_vs_same_user_registration(monkeypatch, tmp_path):
    import database.db as db_module

    db_path = tmp_path / "init_vs_same_register.db"
    _bind_tmp_db(monkeypatch, db_module, db_path)
    _prepare_legacy_users(db_path, [20])

    entered = threading.Event()
    release = threading.Event()

    def pause():
        entered.set()
        assert release.wait(timeout=5)

    db_module._INIT_DB_PAUSE_HOOK = pause
    barrier = threading.Barrier(2, timeout=5)

    def run_init():
        barrier.wait()
        init_db()

    def run_register():
        barrier.wait()
        assert entered.wait(timeout=5)
        register_user(20)

    errors: list[BaseException] = []

    def wrap(fn):
        def runner():
            try:
                fn()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        return runner

    threads = [
        threading.Thread(target=wrap(run_init)),
        threading.Thread(target=wrap(run_register)),
    ]
    try:
        for thread in threads:
            thread.start()
        assert entered.wait(timeout=5)
        # Holders: init owns BEGIN IMMEDIATE; register blocks on readiness/write lock.
        threading.Event().wait(0.05)
        release.set()
        for thread in threads:
            thread.join(timeout=15)
            assert not thread.is_alive()
        assert errors == []
    finally:
        db_module._INIT_DB_PAUSE_HOOK = None
        release.set()

    conn = get_connection()
    users = _assert_identity_state(conn, [20])
    conn.close()
    init_db()
    assert get_guide_os_id(20) == users[20]


def test_concurrent_init_vs_different_user_registrations(monkeypatch, tmp_path):
    import database.db as db_module

    db_path = tmp_path / "init_vs_diff_register.db"
    _bind_tmp_db(monkeypatch, db_module, db_path)
    _prepare_legacy_users(db_path, [30])

    entered = threading.Event()
    release = threading.Event()

    def pause():
        entered.set()
        assert release.wait(timeout=5)

    db_module._INIT_DB_PAUSE_HOOK = pause
    barrier = threading.Barrier(3, timeout=5)

    def run_init():
        barrier.wait()
        init_db()

    def run_register(user_id):
        barrier.wait()
        assert entered.wait(timeout=5)
        register_user(user_id)

    def release_after_starters():
        assert entered.wait(timeout=5)
        # Give both registers a chance to block on BEGIN IMMEDIATE.
        threading.Event().wait(0.05)
        release.set()

    try:
        release_thread = threading.Thread(target=release_after_starters)
        release_thread.start()
        _run_threads(
            [
                run_init,
                lambda: run_register(31),
                lambda: run_register(32),
            ]
        )
        release_thread.join(timeout=5)
        assert not release_thread.is_alive()
    finally:
        db_module._INIT_DB_PAUSE_HOOK = None
        release.set()

    conn = get_connection()
    users = _assert_identity_state(conn, [30, 31, 32])
    conn.close()
    init_db()
    assert get_guide_os_id(30) == users[30]


def test_concurrent_same_user_registrations(monkeypatch, tmp_path):
    import database.db as db_module

    db_path = tmp_path / "same_user_register.db"
    _bind_tmp_db(monkeypatch, db_module, db_path)
    init_db()

    barrier = threading.Barrier(4, timeout=5)
    _run_threads(
        [
            lambda: (barrier.wait(), register_user(40)),
            lambda: (barrier.wait(), register_user(40)),
            lambda: (barrier.wait(), register_user(40)),
            lambda: (barrier.wait(), register_user(40)),
        ]
    )

    conn = get_connection()
    users = _assert_identity_state(conn, [40])
    conn.close()
    first = users[40]
    register_user(40)
    assert get_guide_os_id(40) == first
    init_db()
    assert get_guide_os_id(40) == first


def test_concurrent_different_user_registrations(monkeypatch, tmp_path):
    import database.db as db_module

    db_path = tmp_path / "diff_user_register.db"
    _bind_tmp_db(monkeypatch, db_module, db_path)
    init_db()

    barrier = threading.Barrier(4, timeout=5)
    user_ids = [51, 52, 53, 54]
    _run_threads(
        [
            lambda user_id=user_id: (barrier.wait(), register_user(user_id))
            for user_id in user_ids
        ]
    )

    conn = get_connection()
    users = _assert_identity_state(conn, user_ids)
    conn.close()
    init_db()
    for user_id, identity in users.items():
        assert get_guide_os_id(user_id) == identity


def test_concurrent_init_vs_each_creation_path(monkeypatch, tmp_path):
    import database.db as db_module

    cases = [
        ("register_user", lambda: register_user(61), 61),
        ("set_notifications_enabled", lambda: set_notifications_enabled(62, True), 62),
        ("set_notification_time", lambda: set_notification_time(63, "19:00"), 63),
    ]

    for name, action, user_id in cases:
        db_path = tmp_path / f"init_vs_{name}.db"
        _bind_tmp_db(monkeypatch, db_module, db_path)
        _prepare_legacy_users(db_path, [])

        entered = threading.Event()
        release = threading.Event()

        def pause(entered=entered, release=release):
            entered.set()
            assert release.wait(timeout=5)

        db_module._INIT_DB_PAUSE_HOOK = pause
        barrier = threading.Barrier(2, timeout=5)

        def run_init(barrier=barrier):
            barrier.wait()
            init_db()

        def run_action(barrier=barrier, entered=entered, action=action):
            barrier.wait()
            assert entered.wait(timeout=5)
            action()

        errors: list[BaseException] = []

        def wrap(fn):
            def runner():
                try:
                    fn()
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            return runner

        threads = [
            threading.Thread(target=wrap(run_init)),
            threading.Thread(target=wrap(run_action)),
        ]
        try:
            for thread in threads:
                thread.start()
            assert entered.wait(timeout=5)
            threading.Event().wait(0.05)
            release.set()
            for thread in threads:
                thread.join(timeout=15)
                assert not thread.is_alive()
            assert errors == []
        finally:
            db_module._INIT_DB_PAUSE_HOOK = None
            release.set()

        conn = get_connection()
        users = _assert_identity_state(conn, [user_id])
        conn.close()
        init_db()
        assert get_guide_os_id(user_id) == users[user_id]


def test_feature_flags_default_off_and_invalid_values_fail_closed():
    from services.guide_shop_settings import (
        GuideShopFeatureFlags,
        GuideShopSettingsError,
    )

    flags = GuideShopFeatureFlags.from_env({})
    assert flags == GuideShopFeatureFlags(False, False, False, False)

    with pytest.raises(GuideShopSettingsError):
        GuideShopFeatureFlags.from_env({"GUIDESHOP_READS_ENABLED": "maybe"})
    with pytest.raises(GuideShopSettingsError):
        GuideShopFeatureFlags.from_env({"GUIDESHOP_LINKING_ENABLED": ""})
