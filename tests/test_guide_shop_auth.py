import asyncio
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import logging
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa, x25519

import services.guide_shop_auth as auth_module
from services.guide_shop_auth import (
    AUDIENCE,
    ISSUER,
    GuideShopAuthenticationConfigurationError,
    GuideShopJWTAccessTokenProvider,
    GuideShopTokenSigningError,
)
from services.guide_shop_client import GuideShopAccessTokenProvider
from services.guide_shop_settings import (
    GuideShopJWTSigningSettings,
    GuideShopJWTSigningSettingsError,
)


GUIDE_ID = "123e4567-e89b-42d3-a456-426614174000"


def run(awaitable):
    return asyncio.run(awaitable)


def private_pem(key, encryption=serialization.NoEncryption()):
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        encryption,
    ).decode("ascii")


@pytest.fixture
def key_pair():
    private_key = ed25519.Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


@pytest.fixture
def signing_settings(key_pair):
    return GuideShopJWTSigningSettings(
        app_env="test",
        key_id="guide-os.test-1",
        private_key_pem=private_pem(key_pair[0]),
    )


def test_settings_direct_environment_immutability_and_secret_safe(key_pair):
    pem = private_pem(key_pair[0])
    direct = GuideShopJWTSigningSettings("production", "key_1", pem)
    from_environment = GuideShopJWTSigningSettings.from_env(
        {
            "APP_ENV": "production",
            "GUIDESHOP_JWT_KEY_ID": "key_1",
            "GUIDESHOP_JWT_PRIVATE_KEY": pem,
        }
    )
    assert direct == from_environment
    assert pem not in repr(direct)
    assert pem not in str(direct)
    with pytest.raises(FrozenInstanceError):
        direct.key_id = "changed"


@pytest.mark.parametrize(
    "app_env", [None, "", "Development", "dev", "production ", True]
)
def test_settings_reject_invalid_environment(key_pair, app_env):
    with pytest.raises(GuideShopJWTSigningSettingsError):
        GuideShopJWTSigningSettings(app_env, "key-1", private_pem(key_pair[0]))


@pytest.mark.parametrize(
    "key_id",
    [None, "", " key", "key ", "key/value", "ключ", "a" * 65, True],
)
def test_settings_reject_invalid_key_id(key_pair, key_id):
    with pytest.raises(GuideShopJWTSigningSettingsError):
        GuideShopJWTSigningSettings("test", key_id, private_pem(key_pair[0]))


def test_settings_have_no_key_defaults_or_generation():
    with pytest.raises(GuideShopJWTSigningSettingsError):
        GuideShopJWTSigningSettings.from_env({})


@pytest.mark.parametrize("bad_pem", ["", "not pem", "literal\\nprivate\\nkey"])
def test_settings_reject_malformed_and_literal_backslash_newline(bad_pem):
    with pytest.raises(GuideShopJWTSigningSettingsError) as error:
        GuideShopJWTSigningSettings("test", "key-1", bad_pem)
    if bad_pem:
        assert bad_pem not in str(error.value)


def test_settings_reject_public_and_unsupported_private_keys(key_pair):
    public_pem = key_pair[1].public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    unsupported = [
        private_pem(rsa.generate_private_key(public_exponent=65537, key_size=2048)),
        private_pem(ec.generate_private_key(ec.SECP256R1())),
        private_pem(x25519.X25519PrivateKey.generate()),
        public_pem,
    ]
    for value in unsupported:
        with pytest.raises(GuideShopJWTSigningSettingsError):
            GuideShopJWTSigningSettings("test", "key-1", value)


def test_settings_reject_encrypted_key_and_surrounding_junk(key_pair):
    encrypted = private_pem(
        key_pair[0], serialization.BestAvailableEncryption(b"password")
    )
    valid = private_pem(key_pair[0])
    for value in (encrypted, f"junk{valid}", f"{valid}junk", f" {valid}"):
        with pytest.raises(GuideShopJWTSigningSettingsError) as error:
            GuideShopJWTSigningSettings("test", "key-1", value)
        assert value not in str(error.value)


def test_provider_satisfies_protocol_and_construction_has_no_side_effects(
    signing_settings, monkeypatch
):
    monkeypatch.setattr("builtins.open", Mock(side_effect=AssertionError("filesystem")))
    monkeypatch.setattr("sqlite3.connect", Mock(side_effect=AssertionError("database")))
    monkeypatch.setattr("socket.create_connection", Mock(side_effect=AssertionError("network")))
    provider = GuideShopJWTAccessTokenProvider(signing_settings)
    assert isinstance(provider, GuideShopAccessTokenProvider)


@pytest.mark.parametrize(
    "identity",
    [
        None,
        True,
        b"123e4567-e89b-42d3-a456-426614174000",
        "",
        f" {GUIDE_ID}",
        GUIDE_ID.upper(),
        "not-a-uuid",
        "00000000-0000-0000-0000-000000000000",
        "123e4567-e89b-12d3-a456-426614174000",
    ],
)
def test_provider_requires_canonical_lowercase_uuid4(signing_settings, identity):
    provider = GuideShopJWTAccessTokenProvider(signing_settings)
    with pytest.raises(GuideShopTokenSigningError) as error:
        run(provider.get_access_token(identity))
    if str(identity):
        assert str(identity) not in str(error.value)


def test_exact_header_claims_ttl_randomness_and_signature(signing_settings, key_pair):
    now = datetime(2026, 8, 9, 10, 11, 12, tzinfo=timezone.utc)
    random_bytes = Mock(return_value=bytes(range(16)))
    provider = GuideShopJWTAccessTokenProvider(
        signing_settings, clock=lambda: now, random_bytes=random_bytes
    )
    token = run(provider.get_access_token(GUIDE_ID))
    random_bytes.assert_called_once_with(16)

    assert jwt.get_unverified_header(token) == {
        "alg": "EdDSA",
        "typ": "guideshop-service+jwt",
        "kid": "guide-os.test-1",
    }
    claims = jwt.decode(
        token,
        key_pair[1],
        algorithms=["EdDSA"],
        audience=AUDIENCE,
        issuer=ISSUER,
        options={"verify_exp": False, "verify_iat": False, "verify_nbf": False},
    )
    issued_at = int(now.timestamp())
    assert claims == {
        "iss": "guide-os",
        "aud": "guideshop-integration",
        "sub": f"guide_os:{GUIDE_ID}",
        "guide_os_id": GUIDE_ID,
        "scope": "guideshop:read",
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + 60,
        "jti": "AAECAwQFBgcICQoLDA0ODw",
    }


def test_repeated_calls_create_unique_jti_and_token(signing_settings, key_pair):
    random_bytes = Mock(side_effect=[b"a" * 16, b"b" * 16])
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    provider = GuideShopJWTAccessTokenProvider(
        signing_settings, clock=lambda: now, random_bytes=random_bytes
    )
    first = run(provider.get_access_token(GUIDE_ID))
    second = run(provider.get_access_token(GUIDE_ID))
    assert first != second
    decode = lambda token: jwt.decode(
        token, options={"verify_signature": False}
    )
    assert decode(first)["jti"] != decode(second)["jti"]
    assert [called.args for called in random_bytes.call_args_list] == [(16,), (16,)]


def test_verification_security_boundaries(signing_settings, key_pair):
    now = datetime.now(timezone.utc)
    provider = GuideShopJWTAccessTokenProvider(signing_settings, clock=lambda: now)
    token = run(provider.get_access_token(GUIDE_ID))
    other_public_key = ed25519.Ed25519PrivateKey.generate().public_key()

    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, other_public_key, algorithms=["EdDSA"], audience=AUDIENCE)
    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(token, key_pair[1], algorithms=["EdDSA"], audience="wrong")
    with pytest.raises(jwt.InvalidIssuerError):
        jwt.decode(
            token,
            key_pair[1],
            algorithms=["EdDSA"],
            audience=AUDIENCE,
            issuer="wrong",
        )
    parts = token.split(".")
    parts[1] = ("A" if parts[1][0] != "A" else "B") + parts[1][1:]
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(".".join(parts), key_pair[1], algorithms=["EdDSA"])
    parts = token.split(".")
    parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(".".join(parts), key_pair[1], algorithms=["EdDSA"])


def test_expired_token_fails_verification(signing_settings, key_pair):
    provider = GuideShopJWTAccessTokenProvider(
        signing_settings,
        clock=lambda: datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    token = run(provider.get_access_token(GUIDE_ID))
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(token, key_pair[1], algorithms=["EdDSA"], audience=AUDIENCE)


@pytest.mark.parametrize(
    "clock",
    [lambda: datetime.now(), lambda: "private-clock", lambda: None],
)
def test_invalid_clock_fails_safely(signing_settings, clock):
    provider = GuideShopJWTAccessTokenProvider(signing_settings, clock=clock)
    with pytest.raises(GuideShopTokenSigningError) as error:
        run(provider.get_access_token(GUIDE_ID))
    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    "random_value", [None, True, b"", b"a" * 15, b"a" * 17, bytearray(16)]
)
def test_invalid_random_output_fails_safely(signing_settings, random_value):
    provider = GuideShopJWTAccessTokenProvider(
        signing_settings, random_bytes=lambda size: random_value
    )
    with pytest.raises(GuideShopTokenSigningError):
        run(provider.get_access_token(GUIDE_ID))


def test_signing_failure_and_logs_expose_no_private_values(
    signing_settings, monkeypatch, caplog
):
    private_detail = "private-library-token-jti-route"
    monkeypatch.setattr(
        auth_module.jwt,
        "encode",
        Mock(side_effect=RuntimeError(private_detail)),
    )
    provider = GuideShopJWTAccessTokenProvider(signing_settings)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(GuideShopTokenSigningError) as error:
            run(provider.get_access_token(GUIDE_ID))
    combined = str(error.value) + caplog.text
    assert private_detail not in combined
    assert GUIDE_ID not in combined
    assert signing_settings.private_key_pem not in combined


def test_provider_rejects_unvalidated_settings():
    with pytest.raises(GuideShopAuthenticationConfigurationError):
        GuideShopJWTAccessTokenProvider(object())
