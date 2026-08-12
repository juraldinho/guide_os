from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

from database.db import get_connection, init_db
from services.guide_shop_inbound_auth import (
    AuthenticatedGuideShopPrincipal,
    GuideShopAuthenticationError,
    GuideShopInboundJWTVerifier,
)
from services.guide_shop_settings import (
    GuideShopInboundJWTSettings,
    GuideShopInboundJWTSettingsError,
)


NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
EXCHANGE_SCOPE = "guideshop:link:exchange"
STATUS_SCOPE = "guideshop:link:status"


def public_pem(key):
    return key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


@pytest.fixture
def keys():
    return ed25519.Ed25519PrivateKey.generate(), ed25519.Ed25519PrivateKey.generate()


@pytest.fixture
def settings(keys):
    return GuideShopInboundJWTSettings(
        "test",
        {"link-key-2026": public_pem(keys[0].public_key())},
    )


def claims(scope=EXCHANGE_SCOPE, jti="jti_link_exchange_0001", **changes):
    issued_at = int(NOW.timestamp())
    value = {
        "iss": "guideshop-integration",
        "aud": "guide-os-integration",
        "sub": "guideshop:link-service",
        "scope": scope,
        "iat": issued_at,
        "exp": issued_at + 60,
        "jti": jti,
    }
    value.update(changes)
    return value


def token(key, *, kid="link-key-2026", headers=None, algorithm="EdDSA", **claim_values):
    protected = {
        "kid": kid,
        "typ": "guideshop-link-service+jwt",
    }
    if headers:
        protected.update(headers)
    return jwt.encode(claims(**claim_values), key, algorithm=algorithm, headers=protected)


def verifier(settings):
    return GuideShopInboundJWTVerifier(settings, clock=lambda: NOW)


def replay_rows():
    conn = get_connection()
    result = [dict(row) for row in conn.execute("SELECT * FROM guide_shop_link_jti_replay")]
    conn.close()
    return result


def test_settings_direct_and_environment_parity_rotation_immutability_and_repr(keys):
    mapping = {
        "link-key-2026": public_pem(keys[0].public_key()),
        "link-key-2027": public_pem(keys[1].public_key()),
    }
    direct = GuideShopInboundJWTSettings("staging", mapping)
    environment = GuideShopInboundJWTSettings.from_env(
        {
            "APP_ENV": "staging",
            "GUIDESHOP_LINK_JWT_PUBLIC_KEYS": json.dumps(mapping),
        }
    )
    assert direct.app_env == environment.app_env == "staging"
    assert direct.public_keys == environment.public_keys
    assert all(pem not in repr(direct) for pem in mapping.values())
    with pytest.raises(FrozenInstanceError):
        direct.app_env = "production"
    mapping.clear()
    assert len(direct.public_keys) == 2


@pytest.mark.parametrize("app_env", [None, "", "Staging", "local", True])
def test_settings_reject_invalid_environment(keys, app_env):
    with pytest.raises(GuideShopInboundJWTSettingsError):
        GuideShopInboundJWTSettings(
            app_env, {"link-key-2026": public_pem(keys[0].public_key())}
        )


@pytest.mark.parametrize("kid", ["", "short", "BAD-key-1", "bad_key_1", "a" * 65, None])
def test_settings_reject_invalid_kid(keys, kid):
    with pytest.raises(GuideShopInboundJWTSettingsError):
        GuideShopInboundJWTSettings(
            "test", {kid: public_pem(keys[0].public_key())}
        )


def test_settings_reject_empty_duplicate_malformed_private_and_wrong_key_types(keys):
    with pytest.raises(GuideShopInboundJWTSettingsError):
        GuideShopInboundJWTSettings("test", {})
    pem = public_pem(keys[0].public_key())
    duplicate_json = json.dumps({"APP_ENV": "ignored"})
    duplicate_keys = '{"link-key-2026":' + json.dumps(pem) + ',"link-key-2026":' + json.dumps(pem) + "}"
    with pytest.raises(GuideShopInboundJWTSettingsError):
        GuideShopInboundJWTSettings.from_env(
            {"APP_ENV": "test", "GUIDESHOP_LINK_JWT_PUBLIC_KEYS": duplicate_keys}
        )
    assert duplicate_json
    wrong_values = [
        "malformed",
        keys[0].private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        public_pem(rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()),
        public_pem(ec.generate_private_key(ec.SECP256R1()).public_key()),
    ]
    for value in wrong_values:
        with pytest.raises(GuideShopInboundJWTSettingsError) as error:
            GuideShopInboundJWTSettings("production", {"link-key-2026": value})
        assert value not in str(error.value)


@pytest.mark.parametrize("scope", [EXCHANGE_SCOPE, STATUS_SCOPE])
def test_valid_verification_returns_small_immutable_principal(keys, settings, scope):
    raw = token(keys[0], scope=scope, jti=f"jti_{scope}_00000001")
    principal = verifier(settings).verify(raw, scope)
    assert isinstance(principal, AuthenticatedGuideShopPrincipal)
    assert principal.subject == "guideshop:link-service"
    assert principal.scope == scope
    assert principal.kid == "link-key-2026"
    assert principal.issued_at == int(NOW.timestamp())
    assert principal.expires_at == int(NOW.timestamp()) + 60
    with pytest.raises(FrozenInstanceError):
        principal.scope = STATUS_SCOPE


def test_key_rotation_accepts_both_approved_kids(keys):
    configured = GuideShopInboundJWTSettings(
        "production",
        {
            "link-key-2026": public_pem(keys[0].public_key()),
            "link-key-2027": public_pem(keys[1].public_key()),
        },
    )
    check = verifier(configured)
    first = check.verify(token(keys[0], jti="rotation-jti-value-0001"), EXCHANGE_SCOPE)
    second = check.verify(
        token(keys[1], kid="link-key-2027", jti="rotation-jti-value-0002"),
        EXCHANGE_SCOPE,
    )
    assert {first.kid, second.kid} == {"link-key-2026", "link-key-2027"}


@pytest.mark.parametrize(
    "headers",
    [
        {"typ": "wrong+jwt"},
        {"crit": ["exp"]},
        {"crit": ""},
        {"unknown": "value"},
    ],
)
def test_wrong_typ_crit_and_unknown_headers_fail(keys, settings, headers):
    with pytest.raises(GuideShopAuthenticationError):
        verifier(settings).verify(token(keys[0], headers=headers), EXCHANGE_SCOPE)


def test_missing_malformed_unknown_kid_wrong_alg_and_bad_signature_fail(keys, settings):
    candidates = [
        jwt.encode(claims(), keys[0], algorithm="EdDSA", headers={"typ": "guideshop-link-service+jwt"}),
        token(keys[0], kid="BAD*KEY"),
        token(keys[0], kid="unknown-key-2026"),
        jwt.encode(claims(), "symmetric-secret-value-32-bytes!!", algorithm="HS256", headers={"kid": "link-key-2026", "typ": "guideshop-link-service+jwt"}),
        token(keys[1]),
    ]
    for candidate in candidates:
        with pytest.raises(GuideShopAuthenticationError):
            verifier(settings).verify(candidate, EXCHANGE_SCOPE)
    assert replay_rows() == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("iss", "wrong"),
        ("aud", "wrong"),
        ("sub", "wrong"),
        ("scope", "guideshop:link:delete"),
    ],
)
def test_wrong_fixed_claims_fail(keys, settings, field, value):
    with pytest.raises(GuideShopAuthenticationError):
        verifier(settings).verify(token(keys[0], **{field: value}), EXCHANGE_SCOPE)


def test_missing_and_unknown_claims_fail(keys, settings):
    missing = claims()
    del missing["jti"]
    unknown = claims(extra="private")
    for value in (missing, unknown):
        raw = jwt.encode(
            value,
            keys[0],
            algorithm="EdDSA",
            headers={"kid": "link-key-2026", "typ": "guideshop-link-service+jwt"},
        )
        with pytest.raises(GuideShopAuthenticationError):
            verifier(settings).verify(raw, EXCHANGE_SCOPE)


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": int(NOW.timestamp()) - 11},
        {"iat": int(NOW.timestamp()) + 11, "exp": int(NOW.timestamp()) + 60},
        {"nbf": int(NOW.timestamp()) + 11},
        {"exp": int(NOW.timestamp()) + 61},
        {"exp": int(NOW.timestamp())},
    ],
)
def test_invalid_time_boundaries_fail(keys, settings, changes):
    with pytest.raises(GuideShopAuthenticationError):
        verifier(settings).verify(token(keys[0], **changes), EXCHANGE_SCOPE)


@pytest.mark.parametrize("value", [True, 1.5, "1", -1, None])
@pytest.mark.parametrize("field", ["iat", "exp", "nbf"])
def test_malformed_numeric_dates_fail(keys, settings, field, value):
    with pytest.raises(GuideShopAuthenticationError):
        verifier(settings).verify(token(keys[0], **{field: value}), EXCHANGE_SCOPE)


def test_expected_scope_isolation_and_cross_scope_jti_replay(keys, settings):
    check = verifier(settings)
    exchange_token = token(keys[0], jti="shared-jti-value-0001")
    with pytest.raises(GuideShopAuthenticationError):
        check.verify(exchange_token, STATUS_SCOPE)
    assert replay_rows() == []
    check.verify(exchange_token, EXCHANGE_SCOPE)
    status_token = token(
        keys[0], scope=STATUS_SCOPE, jti="shared-jti-value-0001"
    )
    with pytest.raises(GuideShopAuthenticationError):
        check.verify(status_token, STATUS_SCOPE)


def test_replay_is_shared_across_approved_kids(keys):
    configured = GuideShopInboundJWTSettings(
        "staging",
        {
            "link-key-2026": public_pem(keys[0].public_key()),
            "link-key-2027": public_pem(keys[1].public_key()),
        },
    )
    check = verifier(configured)
    check.verify(
        token(keys[0], jti="cross-key-jti-value-0001"), EXCHANGE_SCOPE
    )
    with pytest.raises(GuideShopAuthenticationError):
        check.verify(
            token(
                keys[1],
                kid="link-key-2027",
                jti="cross-key-jti-value-0001",
            ),
            EXCHANGE_SCOPE,
        )


def test_malformed_oversized_tampered_and_invalid_clock_fail(keys, settings):
    valid = token(keys[0])
    parts = valid.split(".")
    parts[1] = ("A" if parts[1][0] != "A" else "B") + parts[1][1:]
    candidates = ["", "not-a-jwt", "a" * 8193, ".".join(parts)]
    for candidate in candidates:
        with pytest.raises(GuideShopAuthenticationError):
            verifier(settings).verify(candidate, EXCHANGE_SCOPE)
    with pytest.raises(GuideShopAuthenticationError):
        GuideShopInboundJWTVerifier(settings, clock=lambda: datetime.now()).verify(
            valid, EXCHANGE_SCOPE
        )


def test_jti_digest_only_atomic_replay_and_retention(keys, settings):
    raw_jti = "private-jti-value-0001"
    raw = token(keys[0], jti=raw_jti)
    check = verifier(settings)
    check.verify(raw, EXCHANGE_SCOPE)
    with pytest.raises(GuideShopAuthenticationError):
        check.verify(raw, EXCHANGE_SCOPE)
    stored = replay_rows()[0]
    assert stored["jti_hash"] == hashlib.sha256(raw_jti.encode()).hexdigest()
    assert raw_jti not in " ".join(str(value) for value in stored.values())
    assert raw not in " ".join(str(value) for value in stored.values())
    assert datetime.fromisoformat(stored["retain_until"]) == datetime.fromtimestamp(
        int(NOW.timestamp()) + 70, timezone.utc
    )


def test_concurrent_identical_jti_has_exactly_one_success(keys, settings):
    raw = token(keys[0], jti="concurrent-jti-000001")

    def attempt():
        try:
            return verifier(settings).verify(raw, EXCHANGE_SCOPE)
        except GuideShopAuthenticationError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert len(replay_rows()) == 1


def test_invalid_tokens_do_not_claim_jti_and_init_preserves_claim(keys, settings):
    check = verifier(settings)
    with pytest.raises(GuideShopAuthenticationError):
        check.verify(token(keys[0], iss="wrong"), EXCHANGE_SCOPE)
    assert replay_rows() == []
    check.verify(token(keys[0]), EXCHANGE_SCOPE)
    before = replay_rows()
    init_db()
    init_db()
    assert replay_rows() == before


def test_errors_and_logs_expose_no_token_jti_key_kid_or_library_detail(
    keys, settings, caplog
):
    raw = token(keys[1], jti="private-jti-value-0001")
    private_values = [
        raw,
        "private-jti-value-0001",
        "link-key-2026",
        public_pem(keys[0].public_key()),
    ]
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(GuideShopAuthenticationError) as error:
            verifier(settings).verify(raw, EXCHANGE_SCOPE)
    combined = str(error.value) + caplog.text
    assert all(value not in combined for value in private_values)
