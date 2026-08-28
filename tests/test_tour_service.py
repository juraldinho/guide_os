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
    get_conflicting_dates,
    TourEntryDraft,
    check_entry_conflicts,
    create_tour_entry,
    create_day_off_entry,
    copy_tour_entry,
    update_day_locations,
    SOURCE_MINI_APP,
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


def test_check_entry_conflicts_timed_non_overlap_warns():
    user_id = 999001
    create_tour_entry(
        user_id,
        TourEntryDraft(
            title="Morning",
            company="Co",
            location="Самарканд",
            start_date="2026-12-01",
            end_date="2026-12-01",
            start_time="09:00",
            end_time="14:00",
            income=100,
            source=SOURCE_MINI_APP,
        ),
    )

    draft = TourEntryDraft(
        title="Evening",
        company="Co",
        location="Самарканд",
        start_date="2026-12-01",
        end_date="2026-12-01",
        start_time="18:00",
        end_time="21:00",
        income=80,
        source=SOURCE_MINI_APP,
    )
    result = check_entry_conflicts(user_id, draft)
    assert result is not None
    assert result.get("warn") is True
    assert result.get("block") is not True


def test_check_entry_conflicts_timed_overlap_blocks():
    user_id = 999002
    create_tour_entry(
        user_id,
        TourEntryDraft(
            title="Morning",
            company="Co",
            location="Самарканд",
            start_date="2026-12-02",
            end_date="2026-12-02",
            start_time="09:00",
            end_time="14:00",
            income=100,
            source=SOURCE_MINI_APP,
        ),
    )

    draft = TourEntryDraft(
        title="Overlap",
        company="Co",
        location="Самарканд",
        start_date="2026-12-02",
        end_date="2026-12-02",
        start_time="12:00",
        end_time="16:00",
        income=80,
        source=SOURCE_MINI_APP,
    )
    result = check_entry_conflicts(user_id, draft)
    assert result is not None
    assert result.get("block") is True


def test_check_entry_conflicts_legacy_full_day_blocks_timed():
    user_id = 999003
    save_tour(
        user_id=user_id,
        company=random_company(),
        city="Самарканд",
        date_text="2026-12-03",
        status="reserved",
        income=100,
    )

    draft = TourEntryDraft(
        title="Timed",
        company="Co",
        location="Самарканд",
        start_date="2026-12-03",
        end_date="2026-12-03",
        start_time="12:00",
        end_time="16:00",
        income=80,
        source=SOURCE_MINI_APP,
    )
    result = check_entry_conflicts(user_id, draft)
    assert result is not None
    assert result.get("block") is True


def test_check_entry_conflicts_day_off_blocks():
    user_id = 999004
    create_day_off_entry(user_id, "2026-12-04", "2026-12-04")

    draft = TourEntryDraft(
        title="Tour",
        company="Co",
        location="Самарканд",
        start_date="2026-12-04",
        end_date="2026-12-04",
        income=50,
        source=SOURCE_MINI_APP,
    )
    result = check_entry_conflicts(user_id, draft)
    assert result is not None
    assert result.get("block") is True


def test_copy_tour_entry_and_day_locations():
    user_id = 999005
    created = create_tour_entry(
        user_id,
        TourEntryDraft(
            title="Route",
            company="Co",
            location="Ташкент",
            start_date="2026-12-10",
            end_date="2026-12-12",
            income=90,
            source=SOURCE_MINI_APP,
        ),
    )

    updated = update_day_locations(
        user_id,
        created["id"],
        {
            "2026-12-10": "Ташкент",
            "2026-12-11": "Самарканд",
            "2026-12-12": "Бухара",
        },
    )
    assert updated is not None
    assert updated["day_locations"]["2026-12-11"] == "Самарканд"

    copied = copy_tour_entry(user_id, created["id"], "2026-12-20", "2026-12-20")
    assert copied is not None
    assert copied["start_date"] == "2026-12-20"
    assert copied["title"] == "Route"
