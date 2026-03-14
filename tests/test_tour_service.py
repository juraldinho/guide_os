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
