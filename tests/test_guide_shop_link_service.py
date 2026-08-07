from datetime import datetime, timedelta, timezone
import hashlib
import re

import pytest

from database.db import get_connection, init_db
from database.queries import get_guide_os_id, register_user
from services.guide_shop_link_service import (
    ConsumedTokenError,
    ExpiredTokenError,
    GUIDE_SHOP_LINK_AUDIENCE,
    RevokedTokenError,
    UnknownTokenError,
    UnknownUserError,
    WrongAudienceError,
    consume_link_token,
    create_link_request,
    revoke_link_requests,
    validate_link_token,
)


def _stored_request(raw_token: str) -> dict:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM guide_shop_link_requests WHERE token_hash = ?",
        (token_hash,),
    ).fetchone()
    conn.close()
    return dict(row)


def test_existing_user_creates_url_safe_hashed_identity_bound_request():
    register_user(101)
    result = create_link_request(101)

    assert re.fullmatch(r"[A-Za-z0-9_-]+", result.token)
    assert result.expires_at.tzinfo == timezone.utc

    stored = _stored_request(result.token)
    assert stored["token_hash"] == hashlib.sha256(
        result.token.encode("utf-8")
    ).hexdigest()
    assert stored["token_hash"] != result.token
    assert stored["guide_os_id"] == get_guide_os_id(101)

    conn = get_connection()
    raw_occurrences = conn.execute(
        """
        SELECT COUNT(*) AS count FROM guide_shop_link_requests
        WHERE token_hash = ? OR guide_os_id = ? OR audience = ?
        """,
        (result.token, result.token, result.token),
    ).fetchone()["count"]
    conn.close()
    assert raw_occurrences == 0


def test_unknown_user_cannot_create_request_or_be_created():
    with pytest.raises(UnknownUserError):
        create_link_request(202)
    assert get_guide_os_id(202) is None


def test_new_request_revokes_previous_and_explicit_revoke_rejects_token():
    register_user(303)
    first = create_link_request(303)
    second = create_link_request(303)

    assert _stored_request(first.token)["status"] == "revoked"
    assert _stored_request(first.token)["revoked_at"] is not None
    with pytest.raises(RevokedTokenError):
        validate_link_token(first.token, GUIDE_SHOP_LINK_AUDIENCE)

    assert revoke_link_requests(303) == 1
    with pytest.raises(RevokedTokenError):
        validate_link_token(second.token, GUIDE_SHOP_LINK_AUDIENCE)
    assert revoke_link_requests(303) == 0


def test_valid_token_validates_without_consuming_then_consumes_once():
    register_user(404)
    result = create_link_request(404)
    guide_os_id = get_guide_os_id(404)

    assert validate_link_token(result.token, GUIDE_SHOP_LINK_AUDIENCE) == guide_os_id
    assert _stored_request(result.token)["status"] == "issued"
    assert consume_link_token(result.token, GUIDE_SHOP_LINK_AUDIENCE) == guide_os_id
    assert _stored_request(result.token)["consumed_at"] is not None

    with pytest.raises(ConsumedTokenError):
        consume_link_token(result.token, GUIDE_SHOP_LINK_AUDIENCE)
    with pytest.raises(ConsumedTokenError):
        validate_link_token(result.token, GUIDE_SHOP_LINK_AUDIENCE)


def test_expired_token_is_rejected_using_aware_utc_time():
    register_user(505)
    result = create_link_request(505)
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

    conn = get_connection()
    conn.execute(
        "UPDATE guide_shop_link_requests SET expires_at = ? WHERE token_hash = ?",
        (expired_at, hashlib.sha256(result.token.encode("utf-8")).hexdigest()),
    )
    conn.commit()
    conn.close()

    with pytest.raises(ExpiredTokenError):
        validate_link_token(result.token, GUIDE_SHOP_LINK_AUDIENCE)
    with pytest.raises(ExpiredTokenError):
        consume_link_token(result.token, GUIDE_SHOP_LINK_AUDIENCE)


def test_expiration_at_atomic_consumption_boundary_is_rejected(monkeypatch):
    import services.guide_shop_link_service as link_service

    register_user(506)
    result = create_link_request(506)
    original_consume = link_service.consume_guide_shop_link_request

    def expire_then_consume(request_id: int, consumed_at: str) -> bool:
        conn = get_connection()
        conn.execute(
            "UPDATE guide_shop_link_requests SET expires_at = ? WHERE id = ?",
            (consumed_at, request_id),
        )
        conn.commit()
        conn.close()
        return original_consume(request_id, consumed_at)

    monkeypatch.setattr(
        link_service,
        "consume_guide_shop_link_request",
        expire_then_consume,
    )

    with pytest.raises(ExpiredTokenError):
        consume_link_token(result.token, GUIDE_SHOP_LINK_AUDIENCE)

    stored = _stored_request(result.token)
    assert stored["status"] == "issued"
    assert stored["consumed_at"] is None


def test_wrong_audience_and_unknown_token_are_distinguishable():
    register_user(606)
    result = create_link_request(606)

    with pytest.raises(WrongAudienceError):
        validate_link_token(result.token, "another-audience")
    with pytest.raises(UnknownTokenError):
        validate_link_token("unknown-token", GUIDE_SHOP_LINK_AUDIENCE)


def test_repeated_init_preserves_link_request():
    register_user(707)
    result = create_link_request(707)
    before = _stored_request(result.token)

    init_db()
    init_db()

    assert _stored_request(result.token) == before
