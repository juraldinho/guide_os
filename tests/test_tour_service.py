import uuid

from services.tour_service import (
    save_tour,
    delete_tour,
    get_tour,
    edit_tour_company,
    edit_tour_city,
    edit_tour_income,
    edit_tour_status,
    edit_tour_payment_status,
    get_conflicting_dates
)
from database.queries import get_tours_for_date

TEST_USER = 999999


def random_company():
    return f"test_{uuid.uuid4().hex[:6]}"


def test_save_and_get_tour():

    save_tour(
        user_id=TEST_USER,
        company=random_company(),
        city="Самарканд",
        date_text="2026-06-10",
        status="reserved",
        income=100
    )

    conflicts = get_conflicting_dates(TEST_USER, "2026-06-10")

    assert "2026-06-10" in conflicts


def test_edit_functions():

    save_tour(
        user_id=TEST_USER,
        company="Test",
        city="Самарканд",
        date_text="2026-06-12",
        status="reserved",
        income=100
    )

    conflicts = get_conflicting_dates(TEST_USER, "2026-06-12")

    assert len(conflicts) > 0


def test_conflict_detection():

    save_tour(
        user_id=TEST_USER,
        company="CompanyA",
        city="Самарканд",
        date_text="2026-07-01",
        status="reserved",
        income=50
    )

    conflicts = get_conflicting_dates(TEST_USER, "2026-07-01")

    assert "2026-07-01" in conflicts


def test_delete_multi_date_group():
    save_tour(
        user_id=TEST_USER,
        company=random_company(),
        city="Бухара",
        date_text="2026-08-01, 2026-08-03",
        status="reserved",
    )

    assert "2026-08-01" in get_conflicting_dates(TEST_USER, "2026-08-01")
    assert "2026-08-03" in get_conflicting_dates(TEST_USER, "2026-08-03")

    rows = get_tours_for_date(TEST_USER, "2026-08-01")
    tour_id = rows[0]["id"]

    deleted = delete_tour(TEST_USER, tour_id)
    assert deleted is True

    assert "2026-08-01" not in get_conflicting_dates(TEST_USER, "2026-08-01")
    assert "2026-08-03" not in get_conflicting_dates(TEST_USER, "2026-08-03")


def test_conflict_check_excludes_tour_id():
    save_tour(
        user_id=TEST_USER,
        company=random_company(),
        city="Ташкент",
        date_text="2026-09-15",
        status="reserved",
    )

    rows = get_tours_for_date(TEST_USER, "2026-09-15")
    tour_id = rows[0]["id"]

    assert "2026-09-15" in get_conflicting_dates(TEST_USER, "2026-09-15")

    assert get_conflicting_dates(TEST_USER, "2026-09-15", exclude_tour_id=tour_id) == []


def test_conflict_excludes_own_group():
    save_tour(
        user_id=TEST_USER,
        company=random_company(),
        city="Самарканд",
        date_text="2026-11-05, 2026-11-07",
        status="reserved",
    )

    rows = get_tours_for_date(TEST_USER, "2026-11-05")
    tour_group_id = rows[0]["tour_group_id"]

    assert "2026-11-05" in get_conflicting_dates(TEST_USER, "2026-11-05")

    result = get_conflicting_dates(
        TEST_USER,
        "2026-11-05",
        exclude_tour_group_id=tour_group_id,
    )
    assert result == []


def test_edit_company_propagates_to_group():
    original_company = random_company()
    save_tour(
        user_id=TEST_USER,
        company=original_company,
        city="Самарканд",
        date_text="2026-10-01, 2026-10-03",
        status="reserved",
    )

    rows_day1 = get_tours_for_date(TEST_USER, "2026-10-01")
    tour_id = rows_day1[0]["id"]

    updated = edit_tour_company(TEST_USER, tour_id, "NewCompany")
    assert updated is True

    rows_day3 = get_tours_for_date(TEST_USER, "2026-10-03")
    assert rows_day3[0]["company"] == "NewCompany"
