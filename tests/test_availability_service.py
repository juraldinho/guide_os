from services.availability_service import build_availability_preview, build_free_dates_heading
from services.tour_service import TourEntryDraft, create_tour_entry, create_day_off_entry, SOURCE_MINI_APP
from utils.constants import STATUS_CONFIRMED, PAYMENT_PAID

AVAIL_USER = 889001


def test_september_full_month_heading():
    user_id = AVAIL_USER
    create_tour_entry(
        user_id,
        TourEntryDraft(
            title="Август тур",
            company="Co",
            location="Самарканд",
            start_date="2026-08-28",
            end_date="2026-08-28",
            income=100,
            source=SOURCE_MINI_APP,
        ),
    )

    preview = build_availability_preview(user_id, "2026-09-01", "2026-09-30")

    assert preview["heading"] == "Свободные даты в сентябре:"
    assert preview["text"].startswith("Свободные даты в сентябре:")
    assert preview["free_dates"]
    assert "сентября" in preview["text"]


def test_cross_month_heading():
    heading = build_free_dates_heading("2026-08-15", "2026-09-10")
    assert heading.startswith("Свободные даты с ")
    assert " по " in heading


def test_no_free_dates_empty_text():
    user_id = AVAIL_USER + 1
    create_day_off_entry(user_id, "2026-10-01", "2026-10-05")

    preview = build_availability_preview(user_id, "2026-10-01", "2026-10-05")

    assert preview["text"] == ""
    assert preview["free_dates"] == []
    assert preview["ranges"] == []


def test_timed_tour_blocks_whole_day_from_export():
    user_id = AVAIL_USER + 2
    create_tour_entry(
        user_id,
        TourEntryDraft(
            title="Timed",
            company="Co",
            location="Самарканд",
            start_date="2026-11-12",
            end_date="2026-11-12",
            start_time="10:00",
            end_time="12:00",
            income=50,
            status=STATUS_CONFIRMED,
            payment=PAYMENT_PAID,
            source=SOURCE_MINI_APP,
        ),
    )

    preview = build_availability_preview(user_id, "2026-11-12", "2026-11-12")
    assert preview["free_dates"] == []
    assert preview["text"] == ""
