from services.tour_service import save_tour
from services.stats_service import get_all_time_stats_summary


TEST_USER = 777777


def test_stats_calculation():

    save_tour(
        user_id=TEST_USER,
        company="StatTest",
        city="Самарканд",
        date_text="2026-08-01",
        status="confirmed",
        income=100
    )

    stats = get_all_time_stats_summary(TEST_USER)

    assert stats["total_tours"] >= 1
    assert stats["working_days"] >= 1
    assert stats["total_income"] >= 100
