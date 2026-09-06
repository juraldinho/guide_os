"""GO8B Guide Operator service authentication foundation tests."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from database.db import get_connection, init_db
from services.guide_operator_service_auth_settings import (
    GuideOperatorServiceAuthConfigurationError,
    GuideOperatorServiceAuthSettings,
    configure_guide_operator_service_auth_for_tests,
    reset_guide_operator_service_auth_for_tests,
)
from services.guide_operator_service_jwt import (
    ALGORITHM,
    INBOUND_AUDIENCE,
    INBOUND_ISSUER,
    INBOUND_SUBJECT,
    INBOUND_TOKEN_TYPE,
    MAX_CLOCK_SKEW_SECONDS,
    MAX_TTL_SECONDS,
    OUTBOUND_AUDIENCE,
    OUTBOUND_ISSUER,
    OUTBOUND_TOKEN_TYPE,
    SCOPE_ASSIGNMENTS_DECIDE,
    SCOPE_CONNECTIONS_DECIDE,
    SCOPE_CONNECTIONS_WRITE,
    SCOPE_OFFERS_WRITE,
    GuideOperatorInboundJWTVerifier,
    GuideOperatorServiceAuthenticationError,
    GuideOperatorServiceTokenSigningError,
    GuideOSOutboundJWTAccessTokenProvider,
    authenticate_guide_operator_service_jwt,
    hash_jti,
)

GUIDE_A = "11111111-1111-4111-8111-111111111111"
FIXED_NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
NOW_TS = int(FIXED_NOW.timestamp())
INBOUND_KID = "guide-operator-test-key"
OUTBOUND_KID = "guide-os-test-key-01"


@dataclass
class KeyPair:
    private_pem: str = field(repr=False)
    public_pem: str = field(repr=False)

    def __repr__(self) -> str:
        return "KeyPair(redacted)"


class FrozenClock:
    def __init__(self, now: datetime = FIXED_NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _pem_pair() -> KeyPair:
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return KeyPair(private_pem=private_pem, public_pem=public_pem)


def _private_key(pem: str) -> Ed25519PrivateKey:
    loaded = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    assert isinstance(loaded, Ed25519PrivateKey)
    return loaded


def mint_inbound_token(
    private_pem: str,
    *,
    kid: str = INBOUND_KID,
    subject: str = INBOUND_SUBJECT,
    scope: str = SCOPE_OFFERS_WRITE,
    issued_at: int = NOW_TS,
    not_before: int | None = None,
    expires_at: int | None = None,
    jti: str = "jti-test-token-01",
    issuer: str = INBOUND_ISSUER,
    audience: str = INBOUND_AUDIENCE,
    algorithm: str = ALGORITHM,
    token_type: str = INBOUND_TOKEN_TYPE,
    extra_claims: dict[str, Any] | None = None,
    extra_headers: dict[str, Any] | None = None,
    secret: str | None = None,
) -> str:
    headers = {"alg": algorithm, "typ": token_type, "kid": kid}
    if extra_headers:
        headers.update(extra_headers)
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "scope": scope,
        "iat": issued_at,
        "nbf": issued_at if not_before is None else not_before,
        "exp": issued_at + MAX_TTL_SECONDS if expires_at is None else expires_at,
        "jti": jti,
    }
    if extra_claims:
        claims.update(extra_claims)
    key: Any = secret if secret is not None else _private_key(private_pem)
    return jwt.encode(claims, key, algorithm=algorithm, headers=headers)


@pytest.fixture
def inbound_keys() -> KeyPair:
    return _pem_pair()


@pytest.fixture
def outbound_keys() -> KeyPair:
    return _pem_pair()


@pytest.fixture
def guideshop_keys() -> KeyPair:
    return _pem_pair()


@pytest.fixture
def auth_settings(inbound_keys: KeyPair, outbound_keys: KeyPair) -> GuideOperatorServiceAuthSettings:
    return GuideOperatorServiceAuthSettings.enabled_with(
        app_env="test",
        public_keys={INBOUND_KID: inbound_keys.public_pem},
        signing_kid=OUTBOUND_KID,
        signing_private_key_pem=outbound_keys.private_pem,
    )


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture(autouse=True)
def _reset_auth_hooks_and_db() -> Iterator[None]:
    reset_guide_operator_service_auth_for_tests()
    init_db()
    yield
    reset_guide_operator_service_auth_for_tests()


def replay_rows() -> list[dict]:
    conn = get_connection()
    rows = [
        dict(row)
        for row in conn.execute("SELECT * FROM guide_operator_service_jti_replay")
    ]
    conn.close()
    return rows


def test_from_env_defaults_disabled() -> None:
    settings = GuideOperatorServiceAuthSettings.from_env({})
    assert settings.enabled is False
    assert settings.inbound is None
    assert settings.outbound is None


def test_enabled_without_keys_fails_closed() -> None:
    with pytest.raises(GuideOperatorServiceAuthConfigurationError):
        GuideOperatorServiceAuthSettings.from_env(
            {"GUIDE_OS_SERVICE_AUTH_ENABLED": "true"}
        )


def test_from_env_enabled_with_complete_config(
    inbound_keys: KeyPair, outbound_keys: KeyPair
) -> None:
    settings = GuideOperatorServiceAuthSettings.from_env(
        {
            "APP_ENV": "test",
            "GUIDE_OS_SERVICE_AUTH_ENABLED": "true",
            "GUIDE_OS_GUIDE_OPERATOR_JWT_PUBLIC_KEYS": json.dumps(
                {INBOUND_KID: inbound_keys.public_pem}
            ),
            "GUIDE_OS_SIGNING_KID": OUTBOUND_KID,
            "GUIDE_OS_SIGNING_PRIVATE_KEY_PEM": outbound_keys.private_pem,
        }
    )
    assert settings.enabled is True
    assert settings.inbound is not None
    assert settings.outbound is not None
    assert settings.outbound.key_id == OUTBOUND_KID


def test_production_rejects_staging_kid(
    inbound_keys: KeyPair, outbound_keys: KeyPair
) -> None:
    with pytest.raises(GuideOperatorServiceAuthConfigurationError):
        GuideOperatorServiceAuthSettings.enabled_with(
            app_env="production",
            public_keys={"guide-operator-staging-key": inbound_keys.public_pem},
            signing_kid=OUTBOUND_KID,
            signing_private_key_pem=outbound_keys.private_pem,
        )


def test_settings_repr_hides_pems(auth_settings: GuideOperatorServiceAuthSettings) -> None:
    rendered = repr(auth_settings)
    assert "BEGIN" not in rendered
    assert auth_settings.inbound is not None
    assert auth_settings.outbound is not None
    assert auth_settings.inbound.public_keys[0][1] not in rendered
    assert auth_settings.outbound.private_key_pem not in rendered


def test_valid_inbound_token(
    inbound_keys: KeyPair,
    auth_settings: GuideOperatorServiceAuthSettings,
    clock: FrozenClock,
) -> None:
    assert auth_settings.inbound is not None
    verifier = GuideOperatorInboundJWTVerifier(auth_settings.inbound, clock=clock)
    token = mint_inbound_token(inbound_keys.private_pem)
    verified = verifier.verify(token, SCOPE_OFFERS_WRITE)
    assert verified.subject == INBOUND_SUBJECT
    assert verified.scope == SCOPE_OFFERS_WRITE
    assert verified.kid == INBOUND_KID
    assert verified.jti_hash == hash_jti("jti-test-token-01")


@pytest.mark.parametrize(
    ("kwargs",),
    [
        ({"issuer": "guideshop-integration"},),
        ({"audience": "guide-operator"},),
        ({"subject": "guideshop:link-service"},),
        ({"scope": SCOPE_CONNECTIONS_WRITE},),
        ({"kid": "unknown-kid-xx"},),
        ({"algorithm": "HS256", "secret": "not-ed25519-secret-value-32bytes!"},),
        ({"expires_at": NOW_TS + 61},),
        ({"issued_at": NOW_TS + MAX_CLOCK_SKEW_SECONDS + 1},),
        ({"expires_at": NOW_TS - MAX_CLOCK_SKEW_SECONDS, "issued_at": NOW_TS - 70},),
        ({"token_type": "JWT"},),
        ({"token_type": "guideshop-link-service+jwt"},),
        ({"not_before": NOW_TS - 1},),
        ({"not_before": NOW_TS + MAX_TTL_SECONDS},),
        ({"extra_claims": {"guide_os_id": GUIDE_A}},),
    ],
)
def test_inbound_token_rejects_invalid_claims(
    inbound_keys: KeyPair,
    auth_settings: GuideOperatorServiceAuthSettings,
    clock: FrozenClock,
    kwargs: dict[str, Any],
) -> None:
    assert auth_settings.inbound is not None
    verifier = GuideOperatorInboundJWTVerifier(auth_settings.inbound, clock=clock)
    token = mint_inbound_token(inbound_keys.private_pem, **kwargs)
    with pytest.raises(GuideOperatorServiceAuthenticationError):
        verifier.verify(token, SCOPE_OFFERS_WRITE)


def test_clock_skew_boundaries(
    inbound_keys: KeyPair,
    auth_settings: GuideOperatorServiceAuthSettings,
    clock: FrozenClock,
) -> None:
    assert auth_settings.inbound is not None
    verifier = GuideOperatorInboundJWTVerifier(auth_settings.inbound, clock=clock)
    future_ok = mint_inbound_token(
        inbound_keys.private_pem,
        issued_at=NOW_TS + MAX_CLOCK_SKEW_SECONDS,
        jti="jti-skew-future-okxx",
    )
    assert verifier.verify(future_ok, SCOPE_OFFERS_WRITE).subject == INBOUND_SUBJECT
    expired_ok = mint_inbound_token(
        inbound_keys.private_pem,
        issued_at=NOW_TS - MAX_TTL_SECONDS - (MAX_CLOCK_SKEW_SECONDS - 1),
        expires_at=NOW_TS - (MAX_CLOCK_SKEW_SECONDS - 1),
        jti="jti-skew-expired-okx",
    )
    assert verifier.verify(expired_ok, SCOPE_OFFERS_WRITE).subject == INBOUND_SUBJECT
    with pytest.raises(GuideOperatorServiceAuthenticationError):
        verifier.verify(
            mint_inbound_token(
                inbound_keys.private_pem,
                issued_at=NOW_TS + MAX_CLOCK_SKEW_SECONDS + 1,
                jti="jti-skew-future-bad",
            ),
            SCOPE_OFFERS_WRITE,
        )
    with pytest.raises(GuideOperatorServiceAuthenticationError):
        verifier.verify(
            mint_inbound_token(
                inbound_keys.private_pem,
                issued_at=NOW_TS - MAX_TTL_SECONDS - MAX_CLOCK_SKEW_SECONDS,
                expires_at=NOW_TS - MAX_CLOCK_SKEW_SECONDS,
                jti="jti-skew-expired-bad",
            ),
            SCOPE_OFFERS_WRITE,
        )


def test_exact_ttl_sixty_seconds_is_allowed(
    inbound_keys: KeyPair,
    auth_settings: GuideOperatorServiceAuthSettings,
    clock: FrozenClock,
) -> None:
    assert auth_settings.inbound is not None
    verifier = GuideOperatorInboundJWTVerifier(auth_settings.inbound, clock=clock)
    token = mint_inbound_token(
        inbound_keys.private_pem,
        expires_at=NOW_TS + MAX_TTL_SECONDS,
        jti="jti-ttl-exactly-60s",
    )
    assert verifier.verify(token, SCOPE_OFFERS_WRITE).issued_at == NOW_TS


def test_key_rotation_accepts_allowlisted_second_key(
    outbound_keys: KeyPair, clock: FrozenClock
) -> None:
    first = _pem_pair()
    second = _pem_pair()
    settings = GuideOperatorServiceAuthSettings.enabled_with(
        app_env="test",
        public_keys={
            "guide-operator-key-one": first.public_pem,
            "guide-operator-key-two": second.public_pem,
        },
        signing_kid=OUTBOUND_KID,
        signing_private_key_pem=outbound_keys.private_pem,
    )
    assert settings.inbound is not None
    verifier = GuideOperatorInboundJWTVerifier(settings.inbound, clock=clock)
    token = mint_inbound_token(
        second.private_pem, kid="guide-operator-key-two", jti="jti-rotation-key-two"
    )
    assert verifier.verify(token, SCOPE_OFFERS_WRITE).kid == "guide-operator-key-two"
    with pytest.raises(GuideOperatorServiceAuthenticationError):
        verifier.verify(
            mint_inbound_token(
                first.private_pem,
                kid="guide-operator-key-two",
                jti="jti-wrong-key-for-kid",
            ),
            SCOPE_OFFERS_WRITE,
        )


def test_guideshop_keys_are_isolated(
    inbound_keys: KeyPair,
    guideshop_keys: KeyPair,
    outbound_keys: KeyPair,
    clock: FrozenClock,
) -> None:
    settings = GuideOperatorServiceAuthSettings.enabled_with(
        app_env="test",
        public_keys={INBOUND_KID: inbound_keys.public_pem},
        signing_kid=OUTBOUND_KID,
        signing_private_key_pem=outbound_keys.private_pem,
    )
    assert settings.inbound is not None
    verifier = GuideOperatorInboundJWTVerifier(settings.inbound, clock=clock)
    with pytest.raises(GuideOperatorServiceAuthenticationError):
        verifier.verify(
            mint_inbound_token(
                guideshop_keys.private_pem,
                jti="jti-guideshop-wrong-key",
            ),
            SCOPE_OFFERS_WRITE,
        )
    # Even when GuideShop PEMs are mistakenly allowlisted under a GO kid name,
    # GuideShop typ/iss/aud/sub still fail closed.
    polluted = GuideOperatorServiceAuthSettings.enabled_with(
        app_env="test",
        public_keys={"guide-operator-gs-pem": guideshop_keys.public_pem},
        signing_kid=OUTBOUND_KID,
        signing_private_key_pem=outbound_keys.private_pem,
    )
    assert polluted.inbound is not None
    polluted_verifier = GuideOperatorInboundJWTVerifier(polluted.inbound, clock=clock)
    guideshop_shaped = jwt.encode(
        {
            "iss": "guideshop-integration",
            "aud": "guide-os-integration",
            "sub": "guideshop:link-service",
            "scope": SCOPE_OFFERS_WRITE,
            "iat": NOW_TS,
            "nbf": NOW_TS,
            "exp": NOW_TS + MAX_TTL_SECONDS,
            "jti": "jti-guideshop-shaped-tok",
        },
        _private_key(guideshop_keys.private_pem),
        algorithm=ALGORITHM,
        headers={
            "alg": ALGORITHM,
            "typ": "guideshop-link-service+jwt",
            "kid": "guide-operator-gs-pem",
        },
    )
    with pytest.raises(GuideOperatorServiceAuthenticationError):
        polluted_verifier.verify(guideshop_shaped, SCOPE_OFFERS_WRITE)


def test_auth_failure_logs_are_redacted(
    inbound_keys: KeyPair,
    auth_settings: GuideOperatorServiceAuthSettings,
    clock: FrozenClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert auth_settings.inbound is not None
    verifier = GuideOperatorInboundJWTVerifier(auth_settings.inbound, clock=clock)
    jti = "jti-should-never-appear"
    token = mint_inbound_token(inbound_keys.private_pem, issuer="wrong-issuer", jti=jti)
    auth_logger = logging.getLogger("guide_os.guide_operator_service_auth")
    auth_logger.disabled = False
    with caplog.at_level(logging.WARNING):
        with pytest.raises(GuideOperatorServiceAuthenticationError):
            verifier.verify(token, SCOPE_OFFERS_WRITE)
    logged = caplog.text
    assert token not in logged
    assert jti not in logged
    assert GUIDE_A not in logged
    assert "BEGIN" not in logged
    assert inbound_keys.private_pem not in logged
    assert "Service authentication failed" in logged


def test_outbound_signing_contains_required_claims(
    auth_settings: GuideOperatorServiceAuthSettings,
    clock: FrozenClock,
    outbound_keys: KeyPair,
) -> None:
    assert auth_settings.outbound is not None
    provider = GuideOSOutboundJWTAccessTokenProvider(
        auth_settings.outbound,
        clock=clock,
        random_bytes=lambda _n: b"\x02" * 16,
    )
    token = provider.sign(SCOPE_CONNECTIONS_DECIDE, GUIDE_A)
    public = serialization.load_pem_public_key(outbound_keys.public_pem.encode("ascii"))
    header = jwt.get_unverified_header(token)
    claims = jwt.decode(
        token,
        public,
        algorithms=[ALGORITHM],
        options={
            "verify_aud": False,
            "verify_exp": False,
            "verify_iat": False,
            "verify_nbf": False,
        },
    )
    assert header["alg"] == ALGORITHM
    assert header["typ"] == OUTBOUND_TOKEN_TYPE
    assert header["kid"] == OUTBOUND_KID
    assert claims == {
        "iss": OUTBOUND_ISSUER,
        "aud": OUTBOUND_AUDIENCE,
        "sub": GUIDE_A,
        "scope": SCOPE_CONNECTIONS_DECIDE,
        "iat": NOW_TS,
        "nbf": NOW_TS,
        "exp": NOW_TS + MAX_TTL_SECONDS,
        "jti": base64.urlsafe_b64encode(b"\x02" * 16).rstrip(b"=").decode("ascii"),
    }


def test_outbound_rejects_inbound_scope(
    auth_settings: GuideOperatorServiceAuthSettings, clock: FrozenClock
) -> None:
    assert auth_settings.outbound is not None
    provider = GuideOSOutboundJWTAccessTokenProvider(
        auth_settings.outbound, clock=clock, random_bytes=lambda _n: b"\x03" * 16
    )
    with pytest.raises(GuideOperatorServiceTokenSigningError):
        provider.sign(SCOPE_OFFERS_WRITE, GUIDE_A)


def test_replay_rejects_hashed_jti_and_cleans_expired(
    inbound_keys: KeyPair,
    auth_settings: GuideOperatorServiceAuthSettings,
    clock: FrozenClock,
) -> None:
    assert auth_settings.inbound is not None
    token = mint_inbound_token(inbound_keys.private_pem, jti="jti-replay-same-token")
    first = authenticate_guide_operator_service_jwt(
        token, SCOPE_OFFERS_WRITE, auth_settings.inbound, clock=clock
    )
    assert first.jti_hash == hash_jti("jti-replay-same-token")
    assert len(replay_rows()) == 1
    with pytest.raises(GuideOperatorServiceAuthenticationError):
        authenticate_guide_operator_service_jwt(
            token, SCOPE_OFFERS_WRITE, auth_settings.inbound, clock=clock
        )
    conn = get_connection()
    conn.execute(
        """
        UPDATE guide_operator_service_jti_replay
        SET retain_until = ?
        WHERE jti_hash = ?
        """,
        (clock.now.isoformat(), hash_jti("jti-replay-same-token")),
    )
    conn.commit()
    conn.close()
    later = mint_inbound_token(inbound_keys.private_pem, jti="jti-replay-same-token")
    reused = authenticate_guide_operator_service_jwt(
        later, SCOPE_OFFERS_WRITE, auth_settings.inbound, clock=clock
    )
    assert reused.jti_hash == hash_jti("jti-replay-same-token")
    assert len(replay_rows()) == 1


def test_test_hooks_inject_settings_and_clock(
    auth_settings: GuideOperatorServiceAuthSettings, clock: FrozenClock
) -> None:
    configure_guide_operator_service_auth_for_tests(
        settings=auth_settings, clock=clock, random_bytes=lambda n: b"\x04" * n
    )
    from services.guide_operator_service_auth_settings import (
        current_guide_operator_auth_clock,
        load_guide_operator_service_auth_settings,
    )

    loaded = load_guide_operator_service_auth_settings()
    assert loaded.enabled is True
    assert current_guide_operator_auth_clock()() == FIXED_NOW


def test_source_has_no_hardcoded_production_keys() -> None:
    from pathlib import Path
    import re

    root = Path(__file__).resolve().parents[1]
    pem_block = re.compile(
        r"-----BEGIN (?:PRIVATE|PUBLIC) KEY-----\n(?:[A-Za-z0-9+/=]+\n)+-----END (?:PRIVATE|PUBLIC) KEY-----"
    )
    jwt_like = re.compile(r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
    for relative in (
        "services/guide_operator_service_auth_settings.py",
        "services/guide_operator_service_jwt.py",
        ".env.example",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert pem_block.search(text) is None
        assert jwt_like.search(text) is None
        assert "MIGH" not in text
        assert "MCow" not in text


def test_all_inbound_and_outbound_scopes_are_exact() -> None:
    from services.guide_operator_service_jwt import (
        INBOUND_SCOPES,
        OUTBOUND_SCOPES,
        SCOPE_ASSIGNMENTS_READ,
        SCOPE_AVAILABILITY_READ,
        SCOPE_CANCELLATIONS_WRITE,
        SCOPE_OPERATOR_RECONCILE,
        SCOPE_RECONCILE,
        SCOPE_VERSIONS_DECIDE,
        SCOPE_VERSIONS_WRITE,
    )

    assert INBOUND_SCOPES == {
        "guide-operator:connections:write",
        "guide-operator:offers:write",
        "guide-operator:versions:write",
        "guide-operator:cancellations:write",
        "guide-operator:availability:read",
        "guide-operator:reconcile",
    }
    assert OUTBOUND_SCOPES == {
        "guide-os:connections:decide",
        "guide-os:assignments:decide",
        "guide-os:versions:decide",
        "guide-os:assignments:read",
        "guide-os:reconcile",
    }
    assert SCOPE_ASSIGNMENTS_DECIDE in OUTBOUND_SCOPES
    assert SCOPE_VERSIONS_DECIDE in OUTBOUND_SCOPES
    assert SCOPE_ASSIGNMENTS_READ in OUTBOUND_SCOPES
    assert SCOPE_RECONCILE in OUTBOUND_SCOPES
    assert SCOPE_VERSIONS_WRITE in INBOUND_SCOPES
    assert SCOPE_CANCELLATIONS_WRITE in INBOUND_SCOPES
    assert SCOPE_AVAILABILITY_READ in INBOUND_SCOPES
    assert SCOPE_OPERATOR_RECONCILE in INBOUND_SCOPES
