import asyncio
from datetime import datetime
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest

from services import reminder_service as reminder


@pytest.fixture(autouse=True)
def miniapp_env(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('MINI_APP_ENABLED', 'true')
    monkeypatch.setenv('MINI_APP_PUBLIC_URL', 'https://example.test/miniapp')


def test_button_keeps_bot_action_and_targets_exact_entry():
    keyboard = reminder.build_open_tour_keyboard('2026-10-29', entry_id=17)
    old, new = [row[0] for row in keyboard.inline_keyboard]
    assert old.text == 'Открыть тур'
    assert old.callback_data == 'day_card:2026-10-29:2026:10'
    assert new.text == 'Открыть в приложении'
    url = urlsplit(new.web_app.url)
    assert (url.scheme, url.netloc, url.path) == ('https', 'example.test', '/miniapp')
    assert parse_qs(url.query) == {'reminder_entry': ['17'], 'reminder_date': ['2026-10-29']}
    assert new.callback_data is None


@pytest.mark.parametrize('value', ['', 'http://example.test', 'https://user:pass@example.test',
                                   'https://example.test?redirect=x', 'https://example.test/#x'])
def test_bad_url_does_not_break_bot_reminder(monkeypatch, value):
    monkeypatch.setenv('MINI_APP_PUBLIC_URL', value)
    assert len(reminder.build_open_tour_keyboard('2026-10-29', 17).inline_keyboard) == 1


@pytest.mark.parametrize('flag', ['false', 'invalid'])
def test_disabled_or_invalid_configuration_preserves_bot_action(monkeypatch, flag):
    monkeypatch.setenv('MINI_APP_ENABLED', flag)
    assert len(reminder.build_open_tour_keyboard('2026-10-29', 17).inline_keyboard) == 1


@pytest.mark.parametrize('entry_id', [None, True, 0, -1, '17', 2**63])
def test_invalid_entry_id_omits_app_button(entry_id):
    assert len(reminder.build_open_tour_keyboard('2026-10-29', entry_id).inline_keyboard) == 1


def test_reminder_loop_passes_each_entry_id(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 28, 21, 0, tzinfo=tz)

    monkeypatch.setattr(reminder, 'datetime', Clock)
    monkeypatch.setattr(reminder, 'get_users_with_notifications_enabled', lambda: [
        {'user_id': 123, 'notification_time': '21:00', 'last_tour_reminder_date': None},
    ])
    rows = [dict(id=i, company='Test', city='Test', start_date='2026-10-29',
                 end_date='2026-10-31', status='confirmed', entry_type='tour', note=None)
            for i in (17, 18)]
    monkeypatch.setattr(reminder, 'get_entries_for_reminder_date', lambda *args: rows)
    updated = []
    monkeypatch.setattr(reminder, 'update_last_tour_reminder_date', lambda *args: updated.append(args))
    monkeypatch.setattr(reminder.asyncio, 'sleep', AsyncMock(side_effect=asyncio.CancelledError))
    bot = AsyncMock()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(reminder.send_tour_reminders(bot))
    assert bot.send_message.await_count == 2
    for call, entry_id in zip(bot.send_message.await_args_list, (17, 18)):
        url = call.kwargs['reply_markup'].inline_keyboard[1][0].web_app.url
        assert parse_qs(urlsplit(url).query)['reminder_entry'] == [str(entry_id)]
    assert updated == [(123, '2026-10-29')]


def test_multi_day_target_is_owner_scoped():
    from database.queries import get_entries_for_reminder_date
    from services.tour_service import TourEntryDraft, create_tour_entry, get_entry

    entry = create_tour_entry(123, TourEntryDraft(
        title='Multi', company='Test', location='Test',
        start_date='2026-10-29', end_date='2026-10-31',
    ))
    row = get_entries_for_reminder_date(123, '2026-10-30')[0]
    assert get_entry(123, str(row['id']))['id'] == entry['id']
    assert get_entry(456, str(row['id'])) is None
