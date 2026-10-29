import sqlite3

import pytest

from database.db import get_db_connection, init_db
from database.queries import register_user
from services.daily_tips_service import (
    MAX_DAILY_TIPS, get_daily_tip, get_daily_tips, set_daily_tip,
)


def test_replace_delete_isolation_and_migration():
    register_user(101)
    register_user(102)
    for amount in (10, 10, 42, MAX_DAILY_TIPS):
        assert set_daily_tip(101, '2026-10-22', amount)['amount'] == amount
    set_daily_tip(102, '2026-10-22', 5)
    init_db()
    assert get_daily_tips(101, '0001-01-01', '9999-12-31') == [
        {'date': '2026-10-22', 'amount': MAX_DAILY_TIPS}]
    assert get_daily_tip(102, '2026-10-22')['amount'] == 5
    with get_db_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM daily_tips').fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO daily_tips(user_id, tip_date, amount) VALUES (101, '2026-10-22', 1)")
    for _ in range(2):
        set_daily_tip(101, '2026-10-22', 0)
    assert get_daily_tip(101, '2026-10-22')['amount'] == 0
    assert get_daily_tip(102, '2026-10-22')['amount'] == 5


@pytest.mark.parametrize('amount', [-1, True, False, 1.0, 1.5, '20', None, MAX_DAILY_TIPS + 1, 2**64])
def test_invalid_amount(amount):
    with pytest.raises(ValueError):
        set_daily_tip(101, '2026-10-22', amount)


@pytest.mark.parametrize('day', ['2026-02-29', '2026-13-01', '20261022', '2026-1-01', '', None, '2026-10-22T00:00:00Z'])
def test_invalid_date(day):
    with pytest.raises(ValueError):
        set_daily_tip(101, day, 10)
    with pytest.raises(ValueError):
        get_daily_tips(101, day, '2026-12-31')


def test_invalid_range_and_owner():
    with pytest.raises(ValueError):
        get_daily_tips(101, '2026-12-31', '2026-01-01')
    for owner in (True, 0, -1, '101'):
        with pytest.raises(ValueError):
            set_daily_tip(owner, '2026-10-22', 1)


def test_reports_and_calendar_independence():
    from services.reports_service import get_reports_summary
    from services.tour_service import list_entries, copy_tour_entry, delete_tour
    from tests.test_reports_service import seed_ma3_reports_fixtures

    register_user(101)
    register_user(102)
    seed_ma3_reports_fixtures(101)
    before = get_reports_summary(101, '2026-08-01', '2026-08-31')
    entries = list_entries(101, '2026-08-01', '2026-08-31')
    # Empty date, day off, single tour and day within a multi-day tour.
    for day in ('2026-08-01', '2026-08-10', '2026-08-28', '2026-08-23'):
        set_daily_tip(101, day, 20)
    set_daily_tip(101, '1999-01-01', 7)
    set_daily_tip(101, '2027-01-01', 9)
    after = get_reports_summary(101, '2026-08-01', '2026-08-31')
    assert after['tips'] == 80
    assert after['total_earnings'] == before['income'] + 80
    for key in ('income', 'tour_count', 'work_days', 'paid_tours', 'unpaid_tours'):
        assert after[key] == before[key]
    assert list_entries(101, '2026-08-01', '2026-08-31') == entries
    assert get_reports_summary(102, '0001-01-01', '9999-12-31')['tips'] == 0
    assert get_reports_summary(101, '2026-01-01', '2026-12-31')['tips'] == 80
    assert get_reports_summary(101, '0001-01-01', '9999-12-31')['tips'] == 96
    for filters in ({'payment': 'paid'}, {'payment': 'unpaid'}, {'status': 'confirmed'}, {'company': 'absent'}, {'location': 'absent'}):
        filtered = get_reports_summary(101, '2026-08-01', '2026-08-31', filters)
        assert filtered['tips'] == 80
        assert filtered['total_earnings'] == filtered['income'] + 80
    tour = next(e for e in entries if e['type'] == 'tour')
    copied = copy_tour_entry(101, tour['id'], '2028-01-01', '2028-01-01')
    delete_tour(101, int(tour['id']))
    delete_tour(101, int(copied['id']))
    assert sum(row['amount'] for row in get_daily_tips(101, '0001-01-01', '9999-12-31')) == 96


def test_multiple_tours_do_not_duplicate_tips_or_change_availability():
    from services.tour_service import TourEntryDraft, create_tour_entry
    from services.availability_service import build_availability_preview
    from services.reports_service import get_reports_summary

    register_user(101)
    for start, end in (('09:00', '12:00'), ('13:00', '16:00')):
        create_tour_entry(101, TourEntryDraft(
            title='Tour', company='Company', location='City',
            start_date='2026-10-22', end_date='2026-10-22',
            start_time=start, end_time=end, income=100,
        ))
    before = build_availability_preview(101, '2026-10-01', '2026-10-31')
    set_daily_tip(101, '2026-10-22', 15)
    summary = get_reports_summary(101, '2026-10-01', '2026-10-31')
    assert summary['tips'] == 15
    assert summary['income'] == 200
    assert summary['total_earnings'] == 215
    assert summary['tour_count'] == 2
    assert summary['work_days'] == 1
    assert summary['unpaid_tours'] == 2
    assert build_availability_preview(101, '2026-10-01', '2026-10-31') == before


def test_concurrent_replace_and_database_amount_constraint():
    from concurrent.futures import ThreadPoolExecutor
    register_user(101)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda amount: set_daily_tip(101, '2026-10-22', amount), range(1, 9)))
    rows = get_daily_tips(101, '2026-10-22', '2026-10-22')
    assert len(rows) == 1
    assert rows[0]['amount'] in range(1, 9)
    for value in (-1, 1.5, 'invalid', MAX_DAILY_TIPS + 1):
        with get_db_connection() as conn, pytest.raises(sqlite3.IntegrityError):
            conn.execute('UPDATE daily_tips SET amount = ? WHERE user_id = 101', (value,))
