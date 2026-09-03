from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from database.queries import register_user
from services.external_sales_service import ExternalSalesService
from services.personal_places_service import PersonalPlacesService
from services.tour_service import (
    TourEntryDraft,
    create_day_off_entry,
    create_tour_entry,
    SOURCE_MINI_APP,
)
from services.reports_service import get_commission_reports_summary, get_reports_summary
from utils.constants import STATUS_CONFIRMED, STATUS_RESERVED, PAYMENT_PAID, PAYMENT_UNPAID

REPORTS_USER = 888001
COMMISSION_USER = 889001
COMMISSION_USER_B = 889002
BUSINESS_TZ = ZoneInfo("Asia/Tashkent")


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


def _local_dt(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=BUSINESS_TZ)


def _ensure_user(user_id: int) -> int:
    register_user(user_id)
    return user_id


def _place(user_id: int, name: str = "Company A"):
    _ensure_user(user_id)
    return PersonalPlacesService().create(user_id=user_id, name=name)


def _commission(
    user_id: int,
    place_id: str,
    points: int,
    occurred_at: datetime,
    *,
    purchase: int | None = None,
    income: int | None = None,
    currency: str | None = None,
):
    return ExternalSalesService().create(
        user_id=user_id,
        personal_place_id=place_id,
        occurred_at=occurred_at,
        received_points=points,
        purchase_amount_minor=purchase,
        received_income_minor=income,
        currency=currency,
    )


def test_commission_reports_empty_summary():
    user_id = _ensure_user(COMMISSION_USER)
    summary = get_commission_reports_summary(user_id, "2026-08-01", "2026-08-31")
    assert summary == {
        "total_commission": 0,
        "record_count": 0,
        "by_company": [],
        "period": {"from": "2026-08-01", "to": "2026-08-31"},
    }
    assert "user_id" not in summary


def test_commission_reports_one_and_multiple_records():
    user_id = 889010
    place = _place(user_id, "Silk")
    _commission(user_id, place.public_id, 15, _local_dt(2026, 8, 10))
    one = get_commission_reports_summary(user_id, "2026-08-01", "2026-08-31")
    assert one["total_commission"] == 15
    assert one["record_count"] == 1
    assert one["by_company"] == [
        {
            "place_id": place.public_id,
            "company_name": "Silk",
            "total_commission": 15,
            "record_count": 1,
        }
    ]

    _commission(user_id, place.public_id, 40, _local_dt(2026, 8, 12))
    many = get_commission_reports_summary(user_id, "2026-08-01", "2026-08-31")
    assert many["total_commission"] == 55
    assert many["record_count"] == 2
    assert many["by_company"][0]["total_commission"] == 55
    assert many["by_company"][0]["record_count"] == 2


def test_commission_reports_breakdown_and_ordering():
    user_id = 889011
    place_b = _place(user_id, "Beta Co")
    place_a = _place(user_id, "Alpha Co")
    place_c = _place(user_id, "alpha co")
    _commission(user_id, place_b.public_id, 30, _local_dt(2026, 8, 5))
    _commission(user_id, place_a.public_id, 55, _local_dt(2026, 8, 6))
    _commission(user_id, place_a.public_id, 10, _local_dt(2026, 8, 7))
    _commission(user_id, place_c.public_id, 65, _local_dt(2026, 8, 8))

    summary = get_commission_reports_summary(user_id, "2026-08-01", "2026-08-31")
    assert summary["total_commission"] == 160
    assert summary["record_count"] == 4
    names = [row["company_name"] for row in summary["by_company"]]
    totals = [row["total_commission"] for row in summary["by_company"]]
    assert totals == [65, 65, 30]
    assert set(names[:2]) == {"Alpha Co", "alpha co"}
    assert names[2] == "Beta Co"
    assert summary["by_company"][0]["place_id"] < summary["by_company"][1]["place_id"]


def test_commission_reports_identical_names_stay_separate():
    user_id = 889012
    first = _place(user_id, "Same Name")
    second = _place(user_id, "Same Name")
    _commission(user_id, first.public_id, 10, _local_dt(2026, 8, 1))
    _commission(user_id, second.public_id, 20, _local_dt(2026, 8, 2))
    summary = get_commission_reports_summary(user_id, "2026-08-01", "2026-08-31")
    assert len(summary["by_company"]) == 2
    place_ids = {row["place_id"] for row in summary["by_company"]}
    assert place_ids == {first.public_id, second.public_id}


def test_commission_reports_inclusive_boundaries_and_exclusions():
    user_id = 889013
    place = _place(user_id)
    _commission(user_id, place.public_id, 1, _local_dt(2026, 7, 31))
    _commission(user_id, place.public_id, 2, _local_dt(2026, 8, 1))
    _commission(user_id, place.public_id, 4, _local_dt(2026, 8, 31))
    _commission(user_id, place.public_id, 8, _local_dt(2026, 9, 1))
    summary = get_commission_reports_summary(user_id, "2026-08-01", "2026-08-31")
    assert summary["total_commission"] == 6
    assert summary["record_count"] == 2


def test_commission_reports_tashkent_utc_day_boundary():
    user_id = 889014
    place = _place(user_id)
    # 2026-07-31T20:30:00Z == 2026-08-01 01:30 Asia/Tashkent
    _commission(
        user_id,
        place.public_id,
        7,
        datetime(2026, 7, 31, 20, 30, tzinfo=timezone.utc),
    )
    july = get_commission_reports_summary(user_id, "2026-07-01", "2026-07-31")
    august = get_commission_reports_summary(user_id, "2026-08-01", "2026-08-31")
    assert july["total_commission"] == 0
    assert august["total_commission"] == 7


def test_commission_reports_excludes_inactive_and_legacy_money():
    user_id = 889015
    place = _place(user_id)
    active = _commission(user_id, place.public_id, 11, _local_dt(2026, 8, 10))
    ExternalSalesService().deactivate(user_id=user_id, public_id=active.public_id)
    ExternalSalesService().create(
        user_id=user_id,
        personal_place_id=place.public_id,
        occurred_at=_local_dt(2026, 8, 11),
        purchase_amount_minor=10000,
        received_income_minor=2500,
        currency="USD",
        received_points=None,
    )
    _commission(
        user_id,
        place.public_id,
        9,
        _local_dt(2026, 8, 12),
        purchase=5000,
        income=1000,
        currency="USD",
    )
    summary = get_commission_reports_summary(user_id, "2026-08-01", "2026-08-31")
    assert summary["total_commission"] == 9
    assert summary["record_count"] == 1


def test_commission_reports_keeps_active_under_deactivated_company():
    user_id = 889016
    place = _place(user_id, "Historical Co")
    _commission(user_id, place.public_id, 21, _local_dt(2026, 8, 15))
    PersonalPlacesService().deactivate(user_id=user_id, public_id=place.public_id)
    summary = get_commission_reports_summary(user_id, "2026-08-01", "2026-08-31")
    assert summary["total_commission"] == 21
    assert summary["by_company"][0]["company_name"] == "Historical Co"


def test_commission_reports_excludes_other_users_and_rejects_bad_input():
    owner = 889017
    other = COMMISSION_USER_B
    place = _place(owner, "Mine")
    foreign = _place(other, "Theirs")
    _commission(owner, place.public_id, 13, _local_dt(2026, 8, 3))
    _commission(other, foreign.public_id, 99, _local_dt(2026, 8, 3))
    summary = get_commission_reports_summary(owner, "2026-08-01", "2026-08-31")
    assert summary["total_commission"] == 13
    assert "user_id" not in summary
    assert all("user_id" not in row for row in summary["by_company"])

    with pytest.raises(ValueError):
        get_commission_reports_summary(0, "2026-08-01", "2026-08-31")
    with pytest.raises(ValueError):
        get_commission_reports_summary(owner, "2026-13-01", "2026-08-31")
    with pytest.raises(ValueError):
        get_commission_reports_summary(owner, "2026-08-31", "2026-08-01")
    with pytest.raises(ValueError):
        get_commission_reports_summary(owner, "not-a-date", "2026-08-31")


def test_commission_reports_does_not_mutate_source_records():
    user_id = 889018
    place = _place(user_id)
    sale = _commission(user_id, place.public_id, 5, _local_dt(2026, 8, 9))
    before = ExternalSalesService().list(user_id=user_id)
    snapshot = [
        (
            item.public_id,
            item.received_points,
            item.purchase_amount_minor,
            item.received_income_minor,
            item.status,
        )
        for item in before
    ]
    get_commission_reports_summary(user_id, "2026-08-01", "2026-08-31")
    after = ExternalSalesService().list(user_id=user_id)
    assert [
        (
            item.public_id,
            item.received_points,
            item.purchase_amount_minor,
            item.received_income_minor,
            item.status,
        )
        for item in after
    ] == snapshot
    assert sale.received_points == 5
