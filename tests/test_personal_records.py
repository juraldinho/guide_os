from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from database.db import get_connection, init_db
from database.queries import register_user
from services.external_sales_service import (
    ExternalSaleConflictError,
    ExternalSalePlaceNotFoundError,
    ExternalSaleValidationError,
    ExternalSalesService,
)
from services.personal_places_service import (
    PersonalPlaceConflictError,
    PersonalPlacesService,
)


NOW = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)
PLACE_A = "place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PLACE_B = "place_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
ENTRY_A = "entry_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
ENTRY_B = "entry_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
USER_A = 19001
USER_B = 19002


@pytest.fixture
def users():
    register_user(USER_A)
    register_user(USER_B)


def place_service(identifier: str = PLACE_A) -> PersonalPlacesService:
    return PersonalPlacesService(clock=lambda: NOW, id_factory=lambda: identifier)


def entry_service(identifier: str = ENTRY_A) -> ExternalSalesService:
    return ExternalSalesService(clock=lambda: NOW, id_factory=lambda: identifier)


def test_migration_is_additive_rerunnable_and_inventory_is_stable():
    init_db()
    init_db()
    with get_connection() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert {"personal_places", "personal_place_entries"} <= tables
    assert {
        "idx_personal_places_owner_status",
        "idx_personal_place_entries_owner_status",
        "idx_personal_place_entries_place",
    } <= indexes
    with get_connection() as conn:
        triggers = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
    assert {
        "trg_personal_places_no_delete",
        "trg_personal_place_entries_no_delete",
    } <= triggers


def test_places_are_private_and_names_are_not_globally_deduplicated(users):
    first = place_service(PLACE_A).create(user_id=USER_A, name="Same name")
    second = place_service(PLACE_B).create(user_id=USER_B, name="Same name")

    assert first.public_id != second.public_id
    assert place_service().get(user_id=USER_A, public_id=PLACE_B) is None
    assert place_service().get(user_id=USER_B, public_id=PLACE_A) is None
    assert [row.public_id for row in place_service().list(user_id=USER_A)] == [
        PLACE_A
    ]


def test_place_update_and_deactivation_are_owner_scoped(users):
    service = place_service()
    service.create(
        user_id=USER_A,
        name="Place",
        category="shop",
        general_location="district",
        landmark="landmark",
        note="note",
    )

    assert service.update(user_id=USER_B, public_id=PLACE_A, name="Other") is None
    updated = service.update(user_id=USER_A, public_id=PLACE_A, name="Updated")
    assert updated is not None and updated.name == "Updated"
    assert service.deactivate(user_id=USER_B, public_id=PLACE_A) is False
    assert service.deactivate(user_id=USER_A, public_id=PLACE_A) is True
    assert service.deactivate(user_id=USER_A, public_id=PLACE_A) is False
    assert service.list(user_id=USER_A) == []
    assert service.list(user_id=USER_A, include_inactive=True)[0].status == "inactive"


def test_entry_accepts_only_completed_received_outcomes(users):
    place_service().create(user_id=USER_A, name="Place")
    service = entry_service()

    entry = service.create(
        user_id=USER_A,
        personal_place_id=PLACE_A,
        occurred_at=NOW - timedelta(minutes=1),
        purchase_amount_minor=1500,
        received_income_minor=0,
        received_points=7,
        currency="uzs",
        note="completed",
    )

    assert entry.currency == "UZS"
    assert entry.purchase_amount_minor == 1500
    assert entry.received_income_minor == 0
    assert entry.received_points == 7

    invalid = [
        {},
        {"received_points": 0},
        {"received_points": -1},
        {"purchase_amount_minor": 1},
        {"purchase_amount_minor": 1, "currency": "ZZZ"},
        {"received_points": 1, "currency": "USD"},
    ]
    for index, values in enumerate(invalid):
        with pytest.raises(ExternalSaleValidationError):
            entry_service(f"entry_{index:032x}").create(
                user_id=USER_A,
                personal_place_id=PLACE_A,
                occurred_at=NOW - timedelta(minutes=1),
                **values,
            )

    with pytest.raises(ExternalSaleValidationError):
        entry_service(ENTRY_B).create(
            user_id=USER_A,
            personal_place_id=PLACE_A,
            occurred_at=NOW + timedelta(microseconds=1),
            received_points=1,
        )


def test_self_reported_points_remain_separate_from_guideshop_points(users):
    place_service().create(user_id=USER_A, name="Place")
    entry_service().create(
        user_id=USER_A,
        personal_place_id=PLACE_A,
        occurred_at=NOW,
        received_points=5,
    )
    with get_connection() as conn:
        assert conn.execute(
            "SELECT received_points FROM personal_place_entries"
        ).fetchone()[0] == 5
        assert conn.execute(
            "SELECT COUNT(*) FROM guide_shop_event_inbox"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM guide_shop_event_watermarks"
        ).fetchone()[0] == 0


def test_entry_ownership_is_enforced_by_service_and_composite_foreign_key(users):
    place_service().create(user_id=USER_A, name="Place")
    with pytest.raises(ExternalSalePlaceNotFoundError):
        entry_service().create(
            user_id=USER_B,
            personal_place_id=PLACE_A,
            occurred_at=NOW,
            received_points=1,
        )

    with get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO personal_place_entries (
                    public_id, user_id, personal_place_id, occurred_at,
                    received_points, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    ENTRY_A,
                    USER_B,
                    PLACE_A,
                    NOW.isoformat(),
                    1,
                    NOW.isoformat(),
                    NOW.isoformat(),
                ),
            )


def test_entry_reads_updates_and_deactivation_are_owner_scoped(users):
    place_service().create(user_id=USER_A, name="Place")
    service = entry_service()
    service.create(
        user_id=USER_A,
        personal_place_id=PLACE_A,
        occurred_at=NOW,
        received_points=1,
    )

    assert service.get(user_id=USER_B, public_id=ENTRY_A) is None
    assert service.list(user_id=USER_B) == []
    assert service.update(
        user_id=USER_B,
        public_id=ENTRY_A,
        occurred_at=NOW,
        received_points=2,
    ) is None
    updated = service.update(
        user_id=USER_A,
        public_id=ENTRY_A,
        occurred_at=NOW,
        received_points=2,
    )
    assert updated is not None and updated.received_points == 2
    assert service.deactivate(user_id=USER_B, public_id=ENTRY_A) is False
    assert service.deactivate(user_id=USER_A, public_id=ENTRY_A) is True
    assert service.list(user_id=USER_A) == []
    assert service.list(user_id=USER_A, include_inactive=True)[0].status == "inactive"


def test_inactive_place_cannot_receive_new_entry(users):
    places = place_service()
    places.create(user_id=USER_A, name="Place")
    assert places.deactivate(user_id=USER_A, public_id=PLACE_A)
    with pytest.raises(ExternalSalePlaceNotFoundError):
        entry_service().create(
            user_id=USER_A,
            personal_place_id=PLACE_A,
            occurred_at=NOW,
            received_points=1,
        )


def test_personal_records_cannot_be_hard_deleted(users):
    place_service().create(user_id=USER_A, name="Place")
    entry_service().create(
        user_id=USER_A,
        personal_place_id=PLACE_A,
        occurred_at=NOW,
        received_points=1,
    )
    with get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "DELETE FROM personal_place_entries WHERE public_id = ?",
                (ENTRY_A,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "DELETE FROM personal_places WHERE public_id = ?",
                (PLACE_A,),
            )


def test_concurrent_place_id_collision_has_one_winner(users):
    def create(user_id: int):
        try:
            return place_service().create(user_id=user_id, name="Place").user_id
        except PersonalPlaceConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, (USER_A, USER_B)))

    assert sum(result is not None for result in results) == 1
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM personal_places").fetchone()[0] == 1


def test_concurrent_entry_id_collision_has_one_winner(users):
    place_service().create(user_id=USER_A, name="Place")

    def create():
        try:
            return entry_service().create(
                user_id=USER_A,
                personal_place_id=PLACE_A,
                occurred_at=NOW,
                received_points=1,
            ).public_id
        except ExternalSaleConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))

    assert sum(result is not None for result in results) == 1
    with get_connection() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM personal_place_entries"
        ).fetchone()[0] == 1
