import asyncio
import logging
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import database.db as db_module
import handlers.admin_report as admin_report_module
from database.db import get_connection
from database.queries import (
    get_new_user_acquisition_counts_today,
    get_recognized_acquisition_link_starts_today,
    register_user,
    set_user_acquisition_source_if_unset,
)
from handlers.admin_report import build_admin_report_text
from handlers.start import ACQUISITION_PAYLOADS, cmd_start
from keyboards.main_menu import configure_guide_shop_menu


def run(awaitable):
    return asyncio.run(awaitable)


def _message(user_id=101):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncMock(),
        edit_reply_markup=AsyncMock(),
    )


def _command(args):
    return SimpleNamespace(args=args)


def _user_attribution(user_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT acquisition_source, acquisition_recorded_at
        FROM users
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    conn.close()
    return row


def _source_event_names(user_id):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT event_name
        FROM events
        WHERE user_id = ? AND event_name LIKE 'start_source_%'
        ORDER BY id
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [row["event_name"] for row in rows]


@pytest.fixture(autouse=True)
def reset_menu():
    configure_guide_shop_menu(None)
    yield
    configure_guide_shop_menu(None)


def test_start_sends_single_welcome_with_reply_keyboard():
    msg = _message()

    run(cmd_start(msg))

    msg.answer.assert_awaited_once()
    call = msg.answer.await_args
    assert call.kwargs["parse_mode"] == "HTML"
    assert "Добро пожаловать" in call.args[0]
    assert call.kwargs["reply_markup"].keyboard is not None
    assert not any(
        button.web_app is not None
        for row in call.kwargs["reply_markup"].keyboard
        for button in row
    )
    msg.edit_reply_markup.assert_not_awaited()


def test_start_single_message_for_existing_user():
    user_id = 424242
    register_user(user_id)
    msg = _message(user_id=user_id)

    run(cmd_start(msg))

    msg.answer.assert_awaited_once()
    msg.edit_reply_markup.assert_not_awaited()


def test_start_single_message_for_newly_registered_user():
    msg = _message(user_id=999888)

    run(cmd_start(msg))

    msg.answer.assert_awaited_once()
    msg.edit_reply_markup.assert_not_awaited()


@pytest.mark.parametrize(
    ("payload", "source", "event_name"),
    [
        (payload, source, event_name)
        for payload, (source, event_name) in ACQUISITION_PAYLOADS.items()
    ],
)
def test_approved_payload_maps_to_first_touch_and_event(
    payload, source, event_name
):
    user_id = 2001

    run(cmd_start(_message(user_id), _command(payload)))

    row = _user_attribution(user_id)
    assert row["acquisition_source"] == source
    assert row["acquisition_recorded_at"] is not None
    assert _source_event_names(user_id) == [event_name]


def test_public_payloads_are_telegram_safe_and_bounded():
    assert set(ACQUISITION_PAYLOADS) == {
        "src_ig_guideos",
        "src_ig_personal",
        "src_threads",
        "src_tg_personal",
        "src_web_guideos",
        "src_articles",
    }
    for payload in ACQUISITION_PAYLOADS:
        assert len(payload) <= 64
        assert payload.replace("_", "").isalnum()


def test_plain_start_records_organic_attribution_and_event():
    user_id = 2002

    run(cmd_start(_message(user_id)))

    assert _user_attribution(user_id)["acquisition_source"] == "organic"
    assert _source_event_names(user_id) == ["start_source_organic"]


def test_repeated_and_later_sources_preserve_first_touch_but_record_opens():
    user_id = 2003

    run(cmd_start(_message(user_id), _command("src_threads")))
    run(cmd_start(_message(user_id), _command("src_threads")))
    run(cmd_start(_message(user_id), _command("src_articles")))

    assert _user_attribution(user_id)["acquisition_source"] == "threads"
    assert _source_event_names(user_id) == [
        "start_source_threads",
        "start_source_threads",
        "start_source_articles",
    ]


def test_legacy_unknown_is_never_reattributed():
    user_id = 2004
    register_user(user_id)
    conn = get_connection()
    conn.execute(
        """
        UPDATE users
        SET acquisition_source = 'legacy_unknown',
            acquisition_recorded_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
        """,
        (user_id,),
    )
    conn.commit()
    conn.close()

    run(cmd_start(_message(user_id), _command("src_ig_guideos")))

    assert _user_attribution(user_id)["acquisition_source"] == "legacy_unknown"
    assert _source_event_names(user_id) == [
        "start_source_instagram_guide_os"
    ]


@pytest.mark.parametrize(
    "payload",
    ["unknown-sensitive-value", "src_", " src_threads", "src_threads ", "gs_opaque"],
)
def test_unrecognized_payload_is_not_stored_or_tracked(payload, caplog):
    user_id = 2005

    with caplog.at_level(logging.INFO):
        run(cmd_start(_message(user_id), _command(payload)))

    assert _user_attribution(user_id)["acquisition_source"] is None
    assert _source_event_names(user_id) == []
    assert payload not in caplog.text


def test_query_rejects_unsupported_source_before_write():
    register_user(2006)

    with pytest.raises(ValueError, match="Unsupported acquisition source"):
        set_user_acquisition_source_if_unset(2006, "unsupported")

    assert _user_attribution(2006)["acquisition_source"] is None


def test_migration_marks_existing_users_and_preserves_attribution(
    tmp_path, monkeypatch
):
    migration_db = tmp_path / "pre_acquisition.db"
    conn = sqlite3.connect(migration_db)
    conn.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users (user_id) VALUES (3001)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(db_module, "DB_PATH", str(migration_db))

    db_module.init_db()
    row = _user_attribution(3001)
    assert row["acquisition_source"] == "legacy_unknown"
    assert row["acquisition_recorded_at"] is not None

    register_user(3002)
    assert _user_attribution(3002)["acquisition_source"] is None
    assert _user_attribution(3002)["acquisition_recorded_at"] is None

    assert set_user_acquisition_source_if_unset(3002, "articles") is True
    recorded_at = _user_attribution(3002)["acquisition_recorded_at"]
    db_module.init_db()
    row = _user_attribution(3002)
    assert row["acquisition_source"] == "articles"
    assert row["acquisition_recorded_at"] == recorded_at


def test_daily_counts_are_zero_filled_and_tagged_total_excludes_organic():
    run(cmd_start(_message(4001), _command("src_ig_personal")))
    run(cmd_start(_message(4001), _command("src_ig_personal")))
    run(cmd_start(_message(4002)))
    run(cmd_start(_message(4003), _command("unknown")))

    assert get_new_user_acquisition_counts_today() == {
        "instagram_guide_os": 0,
        "instagram_personal": 1,
        "threads": 0,
        "telegram_personal_channel": 0,
        "guide_os_website": 0,
        "articles": 0,
        "organic": 1,
    }
    assert get_recognized_acquisition_link_starts_today() == 2


def test_admin_report_shows_stable_acquisition_labels_and_counts():
    run(cmd_start(_message(5001), _command("src_web_guideos")))
    run(cmd_start(_message(5002)))

    text = build_admin_report_text()

    for expected_line in (
        "• Instagram Guide OS: 0",
        "• Личный Instagram: 0",
        "• Threads: 0",
        "• Личный Telegram-канал: 0",
        "• Сайт Guide OS: 1",
        "• Статьи: 0",
        "• Органика: 1",
        "🔗 Переходов по отслеживаемым ссылкам сегодня: 1",
    ):
        assert expected_line in text
    assert "legacy_unknown" not in text


def test_daily_admin_report_log_does_not_expose_telegram_id(monkeypatch, caplog):
    admin_id = 987654321
    bot = SimpleNamespace(send_message=AsyncMock())
    sleep_calls = 0

    async def stop_after_delivery(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(admin_report_module, "ADMIN_ID", admin_id)
    monkeypatch.setattr(admin_report_module, "seconds_until_next_midnight", lambda: 0)
    monkeypatch.setattr(admin_report_module.asyncio, "sleep", stop_after_delivery)

    with caplog.at_level(logging.INFO), pytest.raises(asyncio.CancelledError):
        run(admin_report_module.send_daily_admin_report(bot))

    bot.send_message.assert_awaited_once()
    assert "Daily admin report sent" in caplog.text
    assert str(admin_id) not in caplog.text
