from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import re
import sqlite3

import pytest

from database.db import get_connection, init_db
from database.queries import create_guide_shop_link_request, get_guide_os_id, register_user
from services.guide_shop_link_exchange_service import (
    EvidenceNotReadyError,
    GuideShopLinkExchangeService,
    InvalidLinkExchangeTransitionError,
    LinkExchangeError,
    LinkExchangeNotFoundError,
    LinkExchangeTokenError,
)


RAW_TOKEN = "synthetic-link-token-1234567890"
AUDIENCE = "guideshop-link"
MEMBERSHIP = "cgm_b20af940"


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def issue(user_id=101, token=RAW_TOKEN, *, expires_at=None, audience=AUDIENCE):
    register_user(user_id)
    now = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
    create_guide_shop_link_request(
        guide_os_id=get_guide_os_id(user_id),
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        audience=audience,
        created_at=now.isoformat(),
        expires_at=(expires_at or now + timedelta(minutes=10)).isoformat(),
    )
    return now


def rows(table):
    conn = get_connection()
    result = [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
    conn.close()
    return result


def test_additive_idempotent_migration_preserves_existing_rows():
    now = issue()
    before_users = rows("users")
    service = GuideShopLinkExchangeService(clock=Clock(now))
    exchange = service.create(RAW_TOKEN, AUDIENCE, MEMBERSHIP)
    service.transition(exchange.link_exchange_id, MEMBERSHIP, "active")
    before_requests = rows("guide_shop_link_requests")
    before_exchange = rows("guide_shop_link_exchanges")
    before_evidence = rows("guide_shop_link_exchange_evidence")

    init_db()
    init_db()

    assert rows("users") == before_users
    assert rows("guide_shop_link_requests") == before_requests
    assert rows("guide_shop_link_exchanges") == before_exchange
    assert rows("guide_shop_link_exchange_evidence") == before_evidence


def test_atomic_creation_binds_identity_scope_and_never_persists_raw_token():
    now = issue()
    service = GuideShopLinkExchangeService(clock=Clock(now))
    exchange = service.create(RAW_TOKEN, AUDIENCE, MEMBERSHIP)

    assert re.fullmatch(r"lex_[0-9a-f]{32}", exchange.link_exchange_id)
    assert exchange.guide_os_id == get_guide_os_id(101)
    assert exchange.status == "awaiting_guide_confirmation"
    assert exchange.exchange_expires_at == now + timedelta(minutes=10)
    stored = rows("guide_shop_link_exchanges")[0]
    assert stored["guide_membership_ref"] == MEMBERSHIP
    assert stored["service_subject"] == "guideshop:link-service"
    assert stored["guide_os_id"] == exchange.guide_os_id
    assert rows("guide_shop_link_requests")[0]["status"] == "consumed"
    conn = get_connection()
    dump = " ".join(
        str(value)
        for table in ("guide_shop_link_requests", "guide_shop_link_exchanges")
        for row in conn.execute(f"SELECT * FROM {table}")
        for value in row
    )
    conn.close()
    assert RAW_TOKEN not in dump


@pytest.mark.parametrize("state", ["consumed", "revoked"])
def test_non_issued_token_states_fail_closed(state):
    now = issue()
    conn = get_connection()
    conn.execute(
        "UPDATE guide_shop_link_requests SET status = ?",
        (state,),
    )
    conn.commit()
    conn.close()
    with pytest.raises(LinkExchangeTokenError):
        GuideShopLinkExchangeService(clock=Clock(now)).create(
            RAW_TOKEN, AUDIENCE, MEMBERSHIP
        )
    assert rows("guide_shop_link_exchanges") == []


def test_unknown_expired_and_wrong_audience_fail_closed():
    now = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
    service = GuideShopLinkExchangeService(clock=Clock(now))
    with pytest.raises(LinkExchangeTokenError):
        service.create(RAW_TOKEN, AUDIENCE, MEMBERSHIP)
    issue(expires_at=now)
    with pytest.raises(LinkExchangeTokenError):
        service.create(RAW_TOKEN, AUDIENCE, MEMBERSHIP)
    assert rows("guide_shop_link_exchanges") == []

    other = "another-synthetic-link-token-1234"
    issue(102, other, audience="another-audience")
    with pytest.raises(LinkExchangeTokenError):
        service.create(other, AUDIENCE, MEMBERSHIP)


def test_token_is_single_use_and_concurrent_race_has_one_success():
    now = issue()

    def attempt():
        try:
            return GuideShopLinkExchangeService(clock=Clock(now)).create(
                RAW_TOKEN, AUDIENCE, MEMBERSHIP
            )
        except LinkExchangeTokenError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert len(rows("guide_shop_link_exchanges")) == 1
    with pytest.raises(LinkExchangeTokenError):
        GuideShopLinkExchangeService(clock=Clock(now)).create(
            RAW_TOKEN, AUDIENCE, MEMBERSHIP
        )


def test_invalid_stored_identity_is_rejected_without_consumption():
    now = issue()
    conn = get_connection()
    conn.execute("UPDATE guide_shop_link_requests SET guide_os_id = 'invalid'")
    conn.commit()
    conn.close()
    with pytest.raises(LinkExchangeTokenError):
        GuideShopLinkExchangeService(clock=Clock(now)).create(
            RAW_TOKEN, AUDIENCE, MEMBERSHIP
        )
    assert rows("guide_shop_link_requests")[0]["status"] == "issued"


def test_lifecycle_evidence_timestamps_and_immutability():
    now = issue()
    clock = Clock(now)
    service = GuideShopLinkExchangeService(clock=clock)
    exchange = service.create(RAW_TOKEN, AUDIENCE, MEMBERSHIP)
    with pytest.raises(EvidenceNotReadyError):
        service.get_evidence(exchange.link_exchange_id, MEMBERSHIP)

    clock.value = now + timedelta(minutes=1)
    active = service.transition(exchange.link_exchange_id, MEMBERSHIP, "active")
    assert active.updated_at == clock.value
    active_evidence = service.get_evidence(exchange.link_exchange_id, MEMBERSHIP)
    assert active_evidence.status == "active"
    assert active_evidence.occurred_at == clock.value
    assert re.fullmatch(
        r"evd_[0-9a-f]{8}(?::[0-9a-f]{8}){3}",
        active_evidence.evidence_ref,
    )

    with pytest.raises(InvalidLinkExchangeTransitionError):
        service.transition(exchange.link_exchange_id, MEMBERSHIP, "active")
    assert service.get_evidence(exchange.link_exchange_id, MEMBERSHIP) == active_evidence

    clock.value += timedelta(minutes=1)
    service.transition(exchange.link_exchange_id, MEMBERSHIP, "revoked")
    revoked = service.get_evidence(exchange.link_exchange_id, MEMBERSHIP)
    assert revoked.status == "revoked"
    assert revoked.occurred_at == clock.value
    assert len(rows("guide_shop_link_exchange_evidence")) == 2
    with pytest.raises(InvalidLinkExchangeTransitionError):
        service.transition(exchange.link_exchange_id, MEMBERSHIP, "revoked")


def test_evidence_ref_is_contract_valid_for_long_decimal_random_bytes():
    random_value = bytes.fromhex("12345678901234567890123456789012")
    assert re.search(r"[0-9]{10,}", random_value.hex())
    now = issue()
    service = GuideShopLinkExchangeService(
        clock=Clock(now), random_bytes=lambda size: random_value
    )
    exchange = service.create(RAW_TOKEN, AUDIENCE, MEMBERSHIP)
    service.transition(exchange.link_exchange_id, MEMBERSHIP, "active")
    evidence_ref = service.get_evidence(
        exchange.link_exchange_id, MEMBERSHIP
    ).evidence_ref

    assert evidence_ref == "evd_12345678:90123456:78901234:56789012"
    assert evidence_ref == evidence_ref.lower()
    assert 8 <= len(evidence_ref) <= 128
    assert evidence_ref.startswith("evd_")
    assert re.fullmatch(r"[a-z0-9._:-]+", evidence_ref)
    assert re.search(r"[0-9]{10,}", evidence_ref) is None
    assert random_value.hex() not in evidence_ref


def test_exchange_binding_and_evidence_are_immutable_in_sql():
    now = issue()
    service = GuideShopLinkExchangeService(clock=Clock(now))
    exchange = service.create(RAW_TOKEN, AUDIENCE, MEMBERSHIP)
    service.transition(exchange.link_exchange_id, MEMBERSHIP, "active")
    original_exchange = rows("guide_shop_link_exchanges")[0]
    original_evidence = rows("guide_shop_link_exchange_evidence")[0]

    immutable_columns = (
        "link_exchange_id",
        "link_request_id",
        "guide_os_id",
        "service_subject",
        "guide_membership_ref",
        "token_expires_at",
        "exchange_expires_at",
        "created_at",
    )
    for column in immutable_columns:
        conn = get_connection()
        with pytest.raises(sqlite3.IntegrityError, match="binding is immutable"):
            conn.execute(
                f"UPDATE guide_shop_link_exchanges SET {column} = ? WHERE id = ?",
                ("changed", original_exchange["id"]),
            )
        conn.close()

    conn = get_connection()
    with pytest.raises(sqlite3.IntegrityError, match="evidence is immutable"):
        conn.execute(
            "UPDATE guide_shop_link_exchange_evidence SET evidence_ref = ?",
            ("evd_changed",),
        )
    conn.close()
    conn = get_connection()
    with pytest.raises(sqlite3.IntegrityError, match="evidence is immutable"):
        conn.execute("DELETE FROM guide_shop_link_exchange_evidence")
    conn.close()

    assert rows("guide_shop_link_exchanges")[0] == original_exchange
    assert rows("guide_shop_link_exchange_evidence")[0] == original_evidence

    service.transition(exchange.link_exchange_id, MEMBERSHIP, "revoked")
    assert len(rows("guide_shop_link_exchange_evidence")) == 2


def test_repeated_init_preserves_immutability_triggers_and_rows():
    now = issue()
    service = GuideShopLinkExchangeService(clock=Clock(now))
    exchange = service.create(RAW_TOKEN, AUDIENCE, MEMBERSHIP)
    service.transition(exchange.link_exchange_id, MEMBERSHIP, "active")
    before = rows("guide_shop_link_exchange_evidence")
    init_db()
    init_db()

    conn = get_connection()
    trigger_names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    with pytest.raises(sqlite3.IntegrityError, match="evidence is immutable"):
        conn.execute("DELETE FROM guide_shop_link_exchange_evidence")
    conn.close()
    assert {
        "trg_guide_shop_link_exchanges_binding_immutable",
        "trg_guide_shop_link_exchange_evidence_immutable",
        "trg_guide_shop_link_exchange_evidence_no_delete",
    } <= trigger_names
    assert rows("guide_shop_link_exchange_evidence") == before


@pytest.mark.parametrize("outcome", ["conflict", "expired"])
def test_supported_terminal_outcomes_and_unsupported_transitions(outcome):
    now = issue()
    service = GuideShopLinkExchangeService(clock=Clock(now))
    exchange = service.create(RAW_TOKEN, AUDIENCE, MEMBERSHIP)
    result = service.transition(exchange.link_exchange_id, MEMBERSHIP, outcome)
    assert result.status == outcome
    if outcome == "conflict":
        assert service.get_evidence(exchange.link_exchange_id, MEMBERSHIP).status == outcome
    else:
        with pytest.raises(EvidenceNotReadyError):
            service.get_evidence(exchange.link_exchange_id, MEMBERSHIP)
    with pytest.raises(InvalidLinkExchangeTransitionError):
        service.transition(exchange.link_exchange_id, MEMBERSHIP, "active")


def test_scope_isolation_and_unknown_are_indistinguishable():
    now = issue()
    service = GuideShopLinkExchangeService(clock=Clock(now))
    exchange = service.create(RAW_TOKEN, AUDIENCE, MEMBERSHIP)
    service.transition(exchange.link_exchange_id, MEMBERSHIP, "active")
    assert service.get_status(exchange.link_exchange_id, MEMBERSHIP) == service.get_status(
        exchange.link_exchange_id, MEMBERSHIP
    )
    errors = []
    for exchange_id, membership in (
        (exchange.link_exchange_id, "cgm_foreign1"),
        ("lex_00000000000000000000000000000000", MEMBERSHIP),
    ):
        with pytest.raises(LinkExchangeNotFoundError) as error:
            service.get_status(exchange_id, membership)
        errors.append(str(error.value))
    assert errors[0] == errors[1]


def test_injected_clock_expiry_boundary_uses_one_authoritative_utc_instant():
    now = issue()
    clock = Clock(now)
    service = GuideShopLinkExchangeService(clock=clock)
    exchange = service.create(RAW_TOKEN, AUDIENCE, MEMBERSHIP)
    clock.value = exchange.exchange_expires_at
    expired = service.get_status(exchange.link_exchange_id, MEMBERSHIP)
    assert expired.status == "expired"
    assert expired.updated_at == clock.value


def test_safe_errors_contain_no_sensitive_values():
    secret = "private-membership-token-value-1234"
    service = GuideShopLinkExchangeService(clock=lambda: "bad-private-clock")
    with pytest.raises(LinkExchangeError) as error:
        service.create(secret, AUDIENCE, "cgm_private1")
    text = str(error.value)
    assert secret not in text
    assert "cgm_private1" not in text
    assert "private-clock" not in text
