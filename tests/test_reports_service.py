import uuid

from services.tour_service import (
    TourEntryDraft,
    check_entry_conflicts,
    create_day_off_entry,
    create_tour_entry,
    copy_tour_entry,
    update_day_locations,
    get_entry,
    SOURCE_MINI_APP,
)
from services.reports_service import get_reports_summary
from utils.constants import STATUS_CONFIRMED, STATUS_RESERVED, PAYMENT_PAID, PAYMENT_UNPAID

REPORTS_USER = 888001


def _draft(
    title: str,
    start: str,
    end: str,
    income: int,
    status: str = STATUS_RESERVED,
    payment: str = PAYMENT_UNPAID,
    start_time: str | None = None,
    end_time: str | None = None,
) -> TourEntryDraft:
    return TourEntryDraft(
        title=title,
        company="Silk Road Travel",
        location="Самарканд",
        start_date=start,
        end_date=end,
        start_time=start_time,
        end_time=end_time,
        status=status,
        payment=payment,
        income=income,
        source=SOURCE_MINI_APP,
    )


def seed_ma3_reports_fixtures(user_id: int) -> None:
    create_tour_entry(
        user_id,
        _draft("Обзорный Самарканд", "2026-08-28", "2026-08-28", 100, start_time="09:00", end_time="14:00"),
    )
    create_tour_entry(
        user_id,
        _draft("Бухара классика", "2026-08-15", "2026-08-15", 120, STATUS_CONFIRMED, PAYMENT_PAID),
    )
    create_tour_entry(
        user_id,
        _draft(
            "Маршрут Узбекистан",
            "2026-08-22",
            "2026-08-24",
            90,
            STATUS_CONFIRMED,
            start_time="10:00",
            end_time="18:00",
        ),
    )
    create_day_off_entry(user_id, "2026-08-10", "2026-08-10")
    create_tour_entry(
        user_id,
        _draft(
            "Вечерний Самарканд",
            "2026-08-05",
            "2026-08-05",
            80,
            start_time="18:00",
            end_time="21:00",
        ),
    )


def test_reports_summary_matches_ma3_logic():
    seed_ma3_reports_fixtures(REPORTS_USER)

    summary = get_reports_summary(REPORTS_USER, "2026-08-01", "2026-08-31", {})

    assert summary["tour_count"] == 4
    assert summary["work_days"] == 6
    assert summary["income"] == 570
    assert summary["paid_tours"] == 1
    assert summary["unpaid_tours"] == 3


def test_reports_summary_unique_work_days_multi_day():
    user_id = 888002
    create_tour_entry(
        user_id,
        _draft("Multi", "2026-09-01", "2026-09-03", 50, STATUS_CONFIRMED),
    )

    summary = get_reports_summary(user_id, "2026-09-01", "2026-09-30", {})
    assert summary["tour_count"] == 1
    assert summary["work_days"] == 3
    assert summary["income"] == 150


def test_reports_summary_payment_filter():
    user_id = 888010
    seed_ma3_reports_fixtures(user_id)

    paid = get_reports_summary(
        user_id,
        "2026-08-01",
        "2026-08-31",
        {"payment": "paid"},
    )
    assert paid["paid_tours"] == 1
    assert paid["unpaid_tours"] == 0
    assert paid["tour_count"] == 1


def test_reports_year_boundary_caps_in_range():
    user_id = 888003
    create_tour_entry(user_id, _draft("Edge", "2026-08-28", "2026-08-28", 40))

    summary = get_reports_summary(user_id, "2026-01-01", "2026-08-28", {})
    assert summary["tour_count"] == 1
    assert summary["income"] == 40
