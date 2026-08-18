from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import re
import sqlite3
import socket

import pytest
from pydantic import ValidationError

from database.db import get_connection, init_db
from database.queries import get_guide_os_id
from services.guide_shop_contracts import PointsStatus
from services.guide_shop_navigation import (
    GuideShopRoute,
    NavigationRouteInvalidError,
    NavigationTokenAccessDeniedError,
    NavigationTokenConsumedError,
    NavigationTokenExpiredError,
    NavigationTokenRevokedError,
    NavigationTokenUnknownError,
    create_navigation_token,
    resolve_navigation_token,
    revoke_navigation_tokens,
)


NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "home"},
        {"kind": "companies"},
        {"kind": "company_detail", "object_id": "company-1"},
        {"kind": "visits", "cursor": "opaque-cursor"},
        {"kind": "visit_detail", "object_id": "visit-1"},
        {"kind": "sales", "cursor": "opaque-cursor"},
        {"kind": "sale_detail", "object_id": "sale-1"},
        {"kind": "points", "points_status": "credited"},
        {"kind": "points_detail", "object_id": "points-1"},
        {"kind": "history", "cursor": "opaque-cursor"},
    ],
)
def test_valid_route_variants(payload):
    route = GuideShopRoute.model_validate(payload)
    assert route.kind == payload["kind"]


@pytest.mark.parametrize(
    "kind", ["company_detail", "visit_detail", "sale_detail", "points_detail"]
)
def test_detail_routes_require_object_id(kind):
    with pytest.raises(ValidationError, match="requires object_id"):
        GuideShopRoute.model_validate({"kind": kind})


@pytest.mark.parametrize(
    "kind", ["home", "companies", "visits", "sales", "points", "history"]
)
def test_non_detail_routes_reject_object_id(kind):
    with pytest.raises(ValidationError, match="must not contain object_id"):
        GuideShopRoute.model_validate({"kind": kind, "object_id": "object-1"})


@pytest.mark.parametrize(
    "kind",
    ["home", "companies", "company_detail", "visit_detail", "sale_detail", "points_detail"],
)
def test_cursor_is_rejected_outside_allowed_list_routes(kind):
    payload = {"kind": kind, "cursor": "cursor-1"}
    if kind.endswith("_detail"):
        payload["object_id"] = "object-1"
    with pytest.raises(ValidationError, match="must not contain cursor"):
        GuideShopRoute.model_validate(payload)


def test_points_status_is_only_allowed_for_points():
    assert GuideShopRoute(kind="points", points_status=PointsStatus.PENDING)
    with pytest.raises(ValidationError, match="must not contain points_status"):
        GuideShopRoute.model_validate(
            {"kind": "visits", "points_status": "pending"}
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "home", "unknown": "value"},
        {"kind": "visit_detail", "object_id": ""},
        {"kind": "visit_detail", "object_id": 123},
        {"kind": "visits", "cursor": ""},
        {"kind": "visits", "cursor": 123},
        {"kind": "home", "guide_os_id": "guide-1"},
        {"kind": "home", "telegram_user_id": 1},
        {"kind": "home", "credentials": "secret"},
    ],
)
def test_route_rejects_unknown_empty_and_coerced_fields(payload):
    with pytest.raises(ValidationError):
        GuideShopRoute.model_validate(payload)


def stored_row(raw_token: str) -> dict:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM guide_shop_navigation_tokens WHERE token_hash = ?",
        (token_hash,),
    ).fetchone()
    conn.close()
    return dict(row)


def test_token_is_short_opaque_hashed_and_route_stays_server_side(monkeypatch):
    import services.guide_shop_navigation as navigation

    fixed_random_value = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    requested_bytes = []

    def fixed_token_urlsafe(byte_count):
        requested_bytes.append(byte_count)
        return fixed_random_value

    monkeypatch.setattr(
        navigation.secrets,
        "token_urlsafe",
        fixed_token_urlsafe,
    )

    route = GuideShopRoute(
        kind="points", cursor="private-cursor", points_status=PointsStatus.CREDITED
    )
    result = create_navigation_token(101, route, now=NOW)

    assert requested_bytes == [24]
    assert result.raw_token == f"gs_{fixed_random_value}"
    assert re.fullmatch(r"gs_[A-Za-z0-9_-]{32}", result.raw_token)
    assert len(result.raw_token) <= 48
    assert result.expires_at == NOW + timedelta(hours=24)

    row = stored_row(result.raw_token)
    assert row["token_hash"] == hashlib.sha256(
        result.raw_token.encode("utf-8")
    ).hexdigest()
    assert row["token_hash"] != result.raw_token
    assert result.raw_token not in {str(value) for value in row.values()}
    assert row["route_kind"] == "points"
    assert row["cursor"] == "private-cursor"
    assert row["points_status"] == "credited"
    assert get_guide_os_id(101) is None


def test_hashes_are_unique_for_independent_192_bit_tokens():
    first = create_navigation_token(101, GuideShopRoute(kind="home"), now=NOW)
    second = create_navigation_token(101, GuideShopRoute(kind="home"), now=NOW)
    assert first.raw_token != second.raw_token
    assert stored_row(first.raw_token)["token_hash"] != stored_row(second.raw_token)["token_hash"]


@pytest.mark.parametrize("user_id", [True, False, 0, -1, "101", 1.5])
def test_invalid_telegram_user_ids_are_rejected(user_id):
    with pytest.raises(ValueError):
        create_navigation_token(user_id, GuideShopRoute(kind="home"), now=NOW)


def test_unchecked_route_dictionary_is_rejected():
    with pytest.raises(NavigationRouteInvalidError):
        create_navigation_token(101, {"kind": "home"}, now=NOW)


def test_correct_user_resolves_original_route_once_with_same_timestamp():
    route = GuideShopRoute(kind="visit_detail", object_id="visit-1")
    token = create_navigation_token(101, route, now=NOW)
    resolved_at = NOW + timedelta(minutes=5)

    assert resolve_navigation_token(token.raw_token, 101, now=resolved_at) == route
    row = stored_row(token.raw_token)
    assert row["status"] == "consumed"
    assert row["consumed_at"] == resolved_at.isoformat()
    with pytest.raises(NavigationTokenConsumedError):
        resolve_navigation_token(token.raw_token, 101, now=resolved_at)


def test_atomic_expiration_boundary_does_not_consume(monkeypatch):
    import services.guide_shop_navigation as navigation

    token = create_navigation_token(101, GuideShopRoute(kind="home"), now=NOW)
    resolved_at = NOW + timedelta(minutes=5)
    original_consume = navigation.consume_guide_shop_navigation_token

    def expire_then_consume(token_hash, telegram_user_id, timestamp):
        conn = get_connection()
        conn.execute(
            "UPDATE guide_shop_navigation_tokens SET expires_at = ? WHERE token_hash = ?",
            (timestamp, token_hash),
        )
        conn.commit()
        conn.close()
        return original_consume(token_hash, telegram_user_id, timestamp)

    monkeypatch.setattr(
        navigation,
        "consume_guide_shop_navigation_token",
        expire_then_consume,
    )

    with pytest.raises(NavigationTokenExpiredError):
        resolve_navigation_token(token.raw_token, 101, now=resolved_at)
    row = stored_row(token.raw_token)
    assert row["status"] == "issued"
    assert row["consumed_at"] is None


def test_cross_user_access_is_denied_without_consumption_or_revocation():
    token = create_navigation_token(101, GuideShopRoute(kind="home"), now=NOW)
    with pytest.raises(NavigationTokenAccessDeniedError):
        resolve_navigation_token(token.raw_token, 202, now=NOW)
    row = stored_row(token.raw_token)
    assert row["status"] == "issued"
    assert row["consumed_at"] is None
    assert row["revoked_at"] is None


def test_unknown_expired_consumed_and_revoked_errors_are_focused():
    with pytest.raises(NavigationTokenUnknownError):
        resolve_navigation_token("gs_unknown", 101, now=NOW)

    expired = create_navigation_token(101, GuideShopRoute(kind="home"), now=NOW)
    with pytest.raises(NavigationTokenExpiredError):
        resolve_navigation_token(expired.raw_token, 101, now=expired.expires_at)

    consumed = create_navigation_token(101, GuideShopRoute(kind="home"), now=NOW)
    resolve_navigation_token(consumed.raw_token, 101, now=NOW)
    with pytest.raises(NavigationTokenConsumedError):
        resolve_navigation_token(consumed.raw_token, 101, now=NOW)

    revoked = create_navigation_token(101, GuideShopRoute(kind="home"), now=NOW)
    revoke_navigation_tokens(101, now=NOW)
    with pytest.raises(NavigationTokenRevokedError):
        resolve_navigation_token(revoked.raw_token, 101, now=NOW)


def test_corrupted_stored_route_is_rejected_without_partial_result():
    token = create_navigation_token(101, GuideShopRoute(kind="home"), now=NOW)
    conn = get_connection()
    conn.execute(
        "UPDATE guide_shop_navigation_tokens SET object_id = 'unexpected' WHERE token_hash = ?",
        (hashlib.sha256(token.raw_token.encode("utf-8")).hexdigest(),),
    )
    conn.commit()
    conn.close()

    with pytest.raises(NavigationRouteInvalidError):
        resolve_navigation_token(token.raw_token, 101, now=NOW)
    assert stored_row(token.raw_token)["status"] == "issued"


def test_concurrent_resolution_succeeds_only_once():
    token = create_navigation_token(101, GuideShopRoute(kind="home"), now=NOW)

    def resolve():
        try:
            return resolve_navigation_token(token.raw_token, 101, now=NOW)
        except NavigationTokenConsumedError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: resolve(), range(2)))

    assert sum(result is not None for result in results) == 1


def test_revocation_affects_only_selected_users_issued_rows_and_preserves_audit():
    consumed = create_navigation_token(101, GuideShopRoute(kind="home"), now=NOW)
    resolve_navigation_token(consumed.raw_token, 101, now=NOW)
    issued = create_navigation_token(101, GuideShopRoute(kind="visits"), now=NOW)
    other = create_navigation_token(202, GuideShopRoute(kind="sales"), now=NOW)

    assert revoke_navigation_tokens(101, now=NOW) == 1
    assert revoke_navigation_tokens(101, now=NOW) == 0
    assert stored_row(consumed.raw_token)["status"] == "consumed"
    assert stored_row(issued.raw_token)["status"] == "revoked"
    assert stored_row(other.raw_token)["status"] == "issued"

    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) AS count FROM guide_shop_navigation_tokens"
    ).fetchone()["count"]
    conn.close()
    assert count == 3


def test_repeated_init_preserves_navigation_rows():
    token = create_navigation_token(101, GuideShopRoute(kind="history"), now=NOW)
    before = stored_row(token.raw_token)
    init_db()
    init_db()
    assert stored_row(token.raw_token) == before


def test_service_performs_no_network_calls_and_does_not_log_secrets(monkeypatch, caplog):
    def unexpected(*args, **kwargs):
        raise AssertionError("network operation attempted")

    monkeypatch.setattr(socket, "socket", unexpected)
    caplog.set_level(logging.DEBUG)
    token = create_navigation_token(101, GuideShopRoute(kind="home"), now=NOW)
    resolve_navigation_token(token.raw_token, 101, now=NOW)

    messages = caplog.text
    token_hash = hashlib.sha256(token.raw_token.encode("utf-8")).hexdigest()
    assert token.raw_token not in messages
    assert token_hash not in messages
