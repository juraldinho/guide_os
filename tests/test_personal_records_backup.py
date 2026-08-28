import asyncio
from datetime import datetime, timezone
import inspect
import logging
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import database.db as db_module
from database.db import create_sqlite_backup, get_connection
from database.queries import register_user
import handlers.admin_report as admin_report_module
from handlers.admin_report import backup_database
from services.external_sales_service import ExternalSalesService
from services.personal_places_service import PersonalPlacesService


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
USER_ID = 19101
PLACE_ID = "place_cccccccccccccccccccccccccccccccc"
ENTRY_ID = "entry_cccccccccccccccccccccccccccccccc"
SAFE_BACKUP_ERROR = "❌ Не удалось создать или отправить резервную копию."


def run(awaitable):
    return asyncio.run(awaitable)


def logical_database_dump() -> tuple[str, ...]:
    with get_connection() as conn:
        return tuple(conn.iterdump())


def backup_message(admin_id: int):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=admin_id),
        answer=AsyncMock(),
        answer_document=AsyncMock(),
    )


def track_backup_paths(monkeypatch) -> list[Path]:
    paths: list[Path] = []

    def tracked_backup(source_path: str, destination_path: str) -> None:
        paths.append(Path(destination_path))
        create_sqlite_backup(source_path, destination_path)

    monkeypatch.setattr(admin_report_module, "create_sqlite_backup", tracked_backup)
    return paths


def seed_personal_records() -> None:
    register_user(USER_ID)
    PersonalPlacesService(
        clock=lambda: NOW,
        id_factory=lambda: PLACE_ID,
    ).create(user_id=USER_ID, name="Private place")
    ExternalSalesService(
        clock=lambda: NOW,
        id_factory=lambda: ENTRY_ID,
    ).create(
        user_id=USER_ID,
        personal_place_id=PLACE_ID,
        occurred_at=NOW,
        received_points=3,
    )


def test_wal_restart_persists_personal_records():
    seed_personal_records()
    with get_connection() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"

    reopened = sqlite3.connect(db_module.DB_PATH)
    try:
        assert reopened.execute("SELECT COUNT(*) FROM personal_places").fetchone()[0] == 1
        assert reopened.execute(
            "SELECT COUNT(*) FROM personal_place_entries"
        ).fetchone()[0] == 1
        assert reopened.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_online_backup_restores_committed_wal_records(tmp_path):
    seed_personal_records()
    with get_connection() as writer:
        writer.execute(
            "UPDATE personal_places SET note = ? WHERE public_id = ?",
            ("committed in WAL", PLACE_ID),
        )
        writer.commit()

    backup_path = tmp_path / "personal-records-backup.db"
    create_sqlite_backup(db_module.DB_PATH, str(backup_path))

    restored = sqlite3.connect(backup_path)
    try:
        assert restored.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert restored.execute("SELECT COUNT(*) FROM personal_places").fetchone()[0] == 1
        assert restored.execute(
            "SELECT COUNT(*) FROM personal_place_entries"
        ).fetchone()[0] == 1
        assert restored.execute(
            "SELECT note FROM personal_places WHERE public_id = ?",
            (PLACE_ID,),
        ).fetchone()[0] == "committed in WAL"
    finally:
        restored.close()


def test_admin_backup_uses_online_sqlite_backup():
    source = inspect.getsource(backup_database)
    assert "create_sqlite_backup" in source
    assert "shutil.copy" not in source


def test_admin_backup_success_deletes_temporary_file_and_preserves_source(monkeypatch):
    seed_personal_records()
    admin_id = USER_ID
    monkeypatch.setattr(admin_report_module, "ADMIN_ID", admin_id)
    monkeypatch.setattr(admin_report_module, "DB_PATH", db_module.DB_PATH)
    paths = track_backup_paths(monkeypatch)
    message = backup_message(admin_id)
    before = logical_database_dump()

    run(backup_database(message))

    message.answer_document.assert_awaited_once()
    message.answer.assert_not_awaited()
    assert len(paths) == 1
    assert not paths[0].exists()
    assert logical_database_dump() == before


def test_admin_backup_failed_send_deletes_temporary_file_and_sanitizes_error(
    monkeypatch,
    caplog,
):
    admin_id = USER_ID
    sensitive_error = "sensitive-database-path-and-telegram-identifier"
    monkeypatch.setattr(admin_report_module, "ADMIN_ID", admin_id)
    monkeypatch.setattr(admin_report_module, "DB_PATH", db_module.DB_PATH)
    paths = track_backup_paths(monkeypatch)
    message = backup_message(admin_id)
    message.answer_document.side_effect = RuntimeError(sensitive_error)

    with caplog.at_level(logging.DEBUG):
        run(backup_database(message))

    assert len(paths) == 1
    assert not paths[0].exists()
    message.answer.assert_awaited_once_with(SAFE_BACKUP_ERROR)
    assert sensitive_error not in caplog.text
    assert sensitive_error not in str(message.answer.await_args_list)


def test_admin_backup_cancellation_deletes_temporary_file_and_propagates(monkeypatch):
    admin_id = USER_ID
    monkeypatch.setattr(admin_report_module, "ADMIN_ID", admin_id)
    monkeypatch.setattr(admin_report_module, "DB_PATH", db_module.DB_PATH)
    paths = track_backup_paths(monkeypatch)
    message = backup_message(admin_id)
    message.answer_document.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        run(backup_database(message))

    assert len(paths) == 1
    assert not paths[0].exists()
    message.answer.assert_not_awaited()
