"""GO6B4: Guide Operator projections — occupancy without income/paid-unpaid."""

from __future__ import annotations

from uuid import uuid4

from database.queries import get_total_income, get_unpaid_tours_count, get_user_id_by_guide_os_id
from services.guide_operator_assignment_service import (
    accept_assignment,
    receive_assignment_offer,
)
from services.income_service import get_income_summary
from services.reports_service import get_reports_summary
from services.stats_service import get_stats_summary
from services.tour_service import TourEntryDraft, create_tour_entry, get_entry
from utils.constants import (
    PAYMENT_PAID,
    PAYMENT_UNPAID,
    SOURCE_MINI_APP,
    STATUS_CONFIRMED,
    STATUS_RESERVED,
)
from web_api.dto import entry_to_api

from tests.test_guide_operator_assignments import _offer, _seed_guide


def _personal(
    user_id: int,
    *,
    title: str,
    start: str,
    end: str,
    income: int,
    payment: str = PAYMENT_UNPAID,
    status: str = STATUS_CONFIRMED,
) -> None:
    create_tour_entry(
        user_id,
        TourEntryDraft(
            title=title,
            company="Personal Co",
            location="Самарканд",
            start_date=start,
            end_date=end,
            start_time=None,
            end_time=None,
            status=status,
            payment=payment,
            income=income,
            source=SOURCE_MINI_APP,
        ),
    )


def _accept_go(
    guide_os_id: str,
    *,
    start_date: str,
    end_date: str,
    assignment_id: str | None = None,
) -> int:
    offer = _offer(
        guide_os_id,
        assignment_id=assignment_id or str(uuid4()),
        start_date=start_date,
        end_date=end_date,
    )
    receive_assignment_offer(offer)
    result = accept_assignment(
        guide_os_id,
        offer.assignment_id,
        decision_event_id=str(uuid4()),
    )
    assert result.projection_tour_id is not None
    return int(result.projection_tour_id)


def test_mixed_personal_and_operator_reports_and_stats():
    guide_os_id = _seed_guide(7101)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    assert user_id is not None

    _personal(
        user_id,
        title="Paid personal",
        start="2026-05-10",
        end="2026-05-10",
        income=100,
        payment=PAYMENT_PAID,
    )
    _personal(
        user_id,
        title="Unpaid personal",
        start="2026-05-11",
        end="2026-05-11",
        income=80,
        payment=PAYMENT_UNPAID,
        status=STATUS_RESERVED,
    )
    _accept_go(guide_os_id, start_date="2026-05-12", end_date="2026-05-13")

    summary = get_reports_summary(user_id, "2026-05-01", "2026-05-31", {})
    assert summary["tour_count"] == 3
    assert summary["work_days"] == 4  # 10, 11, 12, 13
    assert summary["income"] == 180
    assert summary["paid_tours"] == 1
    assert summary["unpaid_tours"] == 1

    stats = get_stats_summary(user_id, 2026, 5)
    assert stats["total_tours"] == 3
    assert stats["working_days"] == 4
    assert stats["total_income"] == 180
    assert stats["paid_tours"] == 1
    assert stats["unpaid_tours"] == 1

    income = get_income_summary(user_id)
    assert income["total_income"] == 180
    assert income["unpaid_tours"] == 1
    assert get_total_income(user_id) == 180
    assert get_unpaid_tours_count(user_id) == 1


def test_operator_only_period_has_work_days_zero_income():
    guide_os_id = _seed_guide(7102)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    assert user_id is not None
    _accept_go(guide_os_id, start_date="2026-06-01", end_date="2026-06-03")

    summary = get_reports_summary(user_id, "2026-06-01", "2026-06-30", {})
    assert summary["tour_count"] == 1
    assert summary["work_days"] == 3
    assert summary["income"] == 0
    assert summary["paid_tours"] == 0
    assert summary["unpaid_tours"] == 0

    stats = get_stats_summary(user_id, 2026, 6)
    assert stats["total_tours"] == 1
    assert stats["working_days"] == 3
    assert stats["total_income"] == 0
    assert stats["paid_tours"] == 0
    assert stats["unpaid_tours"] == 0


def test_payment_filters_exclude_operator_projections():
    guide_os_id = _seed_guide(7103)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    assert user_id is not None
    _personal(
        user_id,
        title="Paid",
        start="2026-07-01",
        end="2026-07-01",
        income=50,
        payment=PAYMENT_PAID,
    )
    _accept_go(guide_os_id, start_date="2026-07-02", end_date="2026-07-02")

    paid = get_reports_summary(
        user_id, "2026-07-01", "2026-07-31", {"payment": "paid"}
    )
    unpaid = get_reports_summary(
        user_id, "2026-07-01", "2026-07-31", {"payment": "unpaid"}
    )
    assert paid["tour_count"] == 1
    assert paid["income"] == 50
    assert unpaid["tour_count"] == 0
    assert unpaid["income"] == 0


def test_same_day_personal_and_operator_count_one_work_day():
    guide_os_id = _seed_guide(7104)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    assert user_id is not None
    # Accept operator first; personal save warns but does not block on overlap.
    _accept_go(guide_os_id, start_date="2026-08-05", end_date="2026-08-05")
    _personal(
        user_id,
        title="Morning",
        start="2026-08-05",
        end="2026-08-05",
        income=70,
        payment=PAYMENT_PAID,
    )

    summary = get_reports_summary(user_id, "2026-08-01", "2026-08-31", {})
    assert summary["tour_count"] == 2
    assert summary["work_days"] == 1
    assert summary["income"] == 70
    assert summary["paid_tours"] == 1
    assert summary["unpaid_tours"] == 0

    stats = get_stats_summary(user_id, 2026, 8)
    assert stats["working_days"] == 1
    assert stats["total_income"] == 70


def test_nullable_income_serialization_for_operator_entry():
    guide_os_id = _seed_guide(7105)
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    assert user_id is not None
    projection_id = _accept_go(
        guide_os_id, start_date="2026-09-01", end_date="2026-09-01"
    )
    entry = get_entry(user_id, str(projection_id))
    assert entry is not None
    assert entry["income"] is None
    assert entry["payment"] is None
    api = entry_to_api(entry)
    assert api["income"] is None
    assert api["payment"] is None
    assert "guideOperatorAssignmentId" in api
