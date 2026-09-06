"""Guide Operator ↔ Guide OS service JWT verify/sign (GO8B / ADR-008).

Inbound: verify Guide Operator Ed25519/EdDSA service JWTs.
Outbound: sign Guide OS → Guide Operator service JWTs for future requests.
No HTTP integration routes in this stage.
"""

from __future__ import annotations

import base64
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from database.queries import claim_guide_operator_service_jti
from services.guide_operator_service_auth_settings import (
    GuideOperatorInboundJWTSettings,
    GuideOperatorOutboundJWTSettings,
    GuideOperatorServiceAuthConfigurationError,
    current_guide_operator_auth_clock,
    current_guide_operator_random_bytes,
)
from utils.guide_os_identity import GuideOsIdentityError, validate_guide_os_id


logger = logging.getLogger("guide_os.guide_operator_service_auth")

ALGORITHM = "EdDSA"
INBOUND_TOKEN_TYPE = "guide-operator-service+jwt"
OUTBOUND_TOKEN_TYPE = "guide-os-service+jwt"
INBOUND_ISSUER = "guide-operator"
INBOUND_AUDIENCE = "guide-os"
INBOUND_SUBJECT = "guide-operator:integration"
OUTBOUND_ISSUER = "guide-os"
OUTBOUND_AUDIENCE = "guide-operator"
MAX_TTL_SECONDS = 60
MAX_CLOCK_SKEW_SECONDS = 10
MAX_TOKEN_BYTES = 8192
_KID = re.compile(r"[a-z0-9-]{8,64}\Z")
_ALLOWED_HEADER_KEYS = frozenset({"alg", "kid", "typ", "crit"})

# Guide Operator → Guide OS (Guide OS verifies)
SCOPE_CONNECTIONS_WRITE = "guide-operator:connections:write"
SCOPE_OFFERS_WRITE = "guide-operator:offers:write"
SCOPE_VERSIONS_WRITE = "guide-operator:versions:write"
SCOPE_CANCELLATIONS_WRITE = "guide-operator:cancellations:write"
SCOPE_AVAILABILITY_READ = "guide-operator:availability:read"
SCOPE_OPERATOR_RECONCILE = "guide-operator:reconcile"

INBOUND_SCOPES = frozenset(
    {
        SCOPE_CONNECTIONS_WRITE,
        SCOPE_OFFERS_WRITE,
        SCOPE_VERSIONS_WRITE,
        SCOPE_CANCELLATIONS_WRITE,
        SCOPE_AVAILABILITY_READ,
        SCOPE_OPERATOR_RECONCILE,
    }
)

# Guide OS → Guide Operator (Guide OS signs)
SCOPE_CONNECTIONS_DECIDE = "guide-os:connections:decide"
SCOPE_ASSIGNMENTS_DECIDE = "guide-os:assignments:decide"
SCOPE_VERSIONS_DECIDE = "guide-os:versions:decide"
SCOPE_ASSIGNMENTS_READ = "guide-os:assignments:read"
SCOPE_RECONCILE = "guide-os:reconcile"

OUTBOUND_SCOPES = frozenset(
    {
        SCOPE_CONNECTIONS_DECIDE,
        SCOPE_ASSIGNMENTS_DECIDE,
        SCOPE_VERSIONS_DECIDE,
        SCOPE_ASSIGNMENTS_READ,
        SCOPE_RECONCILE,
    }
)


class GuideOperatorServiceAuthenticationError(Exception):
    """Opaque inbound JWT verification failure."""


class GuideOperatorServiceTokenSigningError(RuntimeError):
    """Outbound JWT signing failure."""


def _log_auth_failure() -> None:
    logger.warning("Service authentication failed")


def hash_jti(jti: str) -> str:
    return sha256(jti.encode("utf-8")).hexdigest()


def _numeric_date(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GuideOperatorServiceAuthenticationError("Service authentication failed")
    return value


def _aware_utc(clock: Callable[[], datetime]) -> datetime:
    try:
        value = clock()
        valid = (
            isinstance(value, datetime)
            and value.tzinfo is not None
            and value.utcoffset() == timedelta(0)
        )
    except Exception:
        valid = False
        value = None
    if not valid or value is None:
        raise GuideOperatorServiceAuthenticationError("Service authentication failed")
    return value


@dataclass(frozen=True)
class VerifiedGuideOperatorServiceClaims:
    subject: str
    scope: str
    kid: str
    jti_hash: str
    issued_at: int
    expires_at: int


class GuideOperatorInboundJWTVerifier:
    """Verify Guide Operator → Guide OS service JWTs."""

    def __init__(
        self,
        settings: GuideOperatorInboundJWTSettings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(settings, GuideOperatorInboundJWTSettings):
            raise GuideOperatorServiceAuthenticationError(
                "Service authentication failed"
            )
        keys: dict[str, Ed25519PublicKey] = {}
        try:
            for kid, pem in settings.public_keys:
                loaded = serialization.load_pem_public_key(pem.encode("ascii"))
                if not isinstance(loaded, Ed25519PublicKey):
                    raise GuideOperatorServiceAuthenticationError(
                        "Service authentication failed"
                    )
                keys[kid] = loaded
        except GuideOperatorServiceAuthenticationError:
            raise
        except Exception:
            raise GuideOperatorServiceAuthenticationError(
                "Service authentication failed"
            ) from None
        if clock is not None and not callable(clock):
            raise GuideOperatorServiceAuthenticationError(
                "Service authentication failed"
            )
        self._keys = keys
        self._clock = clock or current_guide_operator_auth_clock()

    def verify(
        self, token: str, expected_scope: str
    ) -> VerifiedGuideOperatorServiceClaims:
        try:
            return self._verify(token, expected_scope)
        except GuideOperatorServiceAuthenticationError:
            _log_auth_failure()
            raise
        except Exception:
            _log_auth_failure()
            raise GuideOperatorServiceAuthenticationError(
                "Service authentication failed"
            ) from None

    def _verify(
        self, token: str, expected_scope: str
    ) -> VerifiedGuideOperatorServiceClaims:
        if (
            not isinstance(token, str)
            or not token
            or len(token.encode("utf-8")) > MAX_TOKEN_BYTES
            or token.count(".") != 2
            or expected_scope not in INBOUND_SCOPES
        ):
            raise GuideOperatorServiceAuthenticationError(
                "Service authentication failed"
            )
        header = jwt.get_unverified_header(token)
        if (
            not isinstance(header, dict)
            or set(header) - _ALLOWED_HEADER_KEYS
            or not {"alg", "kid", "typ"} <= set(header)
            or header["alg"] != ALGORITHM
            or header["typ"] != INBOUND_TOKEN_TYPE
            or not isinstance(header["kid"], str)
            or _KID.fullmatch(header["kid"]) is None
            or ("crit" in header and header["crit"] != [])
        ):
            raise GuideOperatorServiceAuthenticationError(
                "Service authentication failed"
            )
        key = self._keys.get(header["kid"])
        if key is None:
            raise GuideOperatorServiceAuthenticationError(
                "Service authentication failed"
            )
        claims = jwt.decode(
            token,
            key,
            algorithms=[ALGORITHM],
            options={
                "verify_aud": False,
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
                "require": [],
            },
        )
        required = {"iss", "aud", "sub", "scope", "iat", "nbf", "exp", "jti"}
        if (
            not isinstance(claims, dict)
            or not required <= set(claims)
            or set(claims) - required
            or claims["iss"] != INBOUND_ISSUER
            or claims["aud"] != INBOUND_AUDIENCE
            or claims["sub"] != INBOUND_SUBJECT
            or claims["scope"] not in INBOUND_SCOPES
            or claims["scope"] != expected_scope
            or not isinstance(claims["jti"], str)
            or not 16 <= len(claims["jti"]) <= 256
        ):
            raise GuideOperatorServiceAuthenticationError(
                "Service authentication failed"
            )
        scope = claims["scope"]
        if not isinstance(scope, str):
            raise GuideOperatorServiceAuthenticationError(
                "Service authentication failed"
            )
        issued_at = _numeric_date(claims["iat"])
        not_before = _numeric_date(claims["nbf"])
        expires_at = _numeric_date(claims["exp"])
        now = _aware_utc(self._clock)
        now_seconds = now.timestamp()
        if (
            expires_at <= issued_at
            or expires_at - issued_at > MAX_TTL_SECONDS
            or not_before < issued_at
            or not_before >= expires_at
            or issued_at > now_seconds + MAX_CLOCK_SKEW_SECONDS
            or expires_at + MAX_CLOCK_SKEW_SECONDS <= now_seconds
            or not_before > now_seconds + MAX_CLOCK_SKEW_SECONDS
        ):
            raise GuideOperatorServiceAuthenticationError(
                "Service authentication failed"
            )
        return VerifiedGuideOperatorServiceClaims(
            subject=INBOUND_SUBJECT,
            scope=scope,
            kid=header["kid"],
            jti_hash=hash_jti(claims["jti"]),
            issued_at=issued_at,
            expires_at=expires_at,
        )


class GuideOSOutboundJWTAccessTokenProvider:
    """Sign Guide OS → Guide Operator service JWTs."""

    def __init__(
        self,
        settings: GuideOperatorOutboundJWTSettings,
        *,
        clock: Callable[[], datetime] | None = None,
        random_bytes: Callable[[int], bytes] | None = None,
    ) -> None:
        if not isinstance(settings, GuideOperatorOutboundJWTSettings):
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            )
        if clock is not None and not callable(clock):
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            )
        rng = random_bytes or current_guide_operator_random_bytes()
        if not callable(rng):
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            )
        try:
            private_key = serialization.load_pem_private_key(
                settings.private_key_pem.encode("ascii"), password=None
            )
        except Exception:
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            ) from None
        if not isinstance(private_key, Ed25519PrivateKey):
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            )
        self._key_id = settings.key_id
        self._private_key = private_key
        self._clock = clock or current_guide_operator_auth_clock()
        self._random_bytes = rng

    def sign(self, scope: str, guide_os_id: str) -> str:
        if scope not in OUTBOUND_SCOPES:
            raise GuideOperatorServiceTokenSigningError("Service token signing failed")
        try:
            subject = validate_guide_os_id(guide_os_id)
        except GuideOsIdentityError as exc:
            raise GuideOperatorServiceTokenSigningError(
                "Service token signing failed"
            ) from exc
        try:
            now = self._clock()
            valid_clock = (
                isinstance(now, datetime)
                and now.tzinfo is not None
                and now.utcoffset() == timedelta(0)
            )
        except Exception:
            raise GuideOperatorServiceTokenSigningError(
                "Service token signing failed"
            ) from None
        if not valid_clock:
            raise GuideOperatorServiceTokenSigningError("Service token signing failed")
        try:
            random_value = self._random_bytes(16)
        except Exception:
            raise GuideOperatorServiceTokenSigningError(
                "Service token signing failed"
            ) from None
        if not isinstance(random_value, bytes) or len(random_value) != 16:
            raise GuideOperatorServiceTokenSigningError("Service token signing failed")
        try:
            issued_at = int(now.timestamp())
        except (OverflowError, OSError, ValueError):
            raise GuideOperatorServiceTokenSigningError(
                "Service token signing failed"
            ) from None
        jti = base64.urlsafe_b64encode(random_value).rstrip(b"=").decode("ascii")
        headers = {
            "alg": ALGORITHM,
            "typ": OUTBOUND_TOKEN_TYPE,
            "kid": self._key_id,
        }
        claims: dict[str, Any] = {
            "iss": OUTBOUND_ISSUER,
            "aud": OUTBOUND_AUDIENCE,
            "sub": subject,
            "scope": scope,
            "iat": issued_at,
            "nbf": issued_at,
            "exp": issued_at + MAX_TTL_SECONDS,
            "jti": jti,
        }
        try:
            token = jwt.encode(
                claims, self._private_key, algorithm=ALGORITHM, headers=headers
            )
        except Exception:
            raise GuideOperatorServiceTokenSigningError(
                "Service token signing failed"
            ) from None
        if not isinstance(token, str) or not token:
            raise GuideOperatorServiceTokenSigningError("Service token signing failed")
        return token


def authenticate_guide_operator_service_jwt(
    token: str,
    expected_scope: str,
    settings: GuideOperatorInboundJWTSettings,
    *,
    clock: Callable[[], datetime] | None = None,
) -> VerifiedGuideOperatorServiceClaims:
    """Verify inbound token and claim hashed jti (SQLite replay + expiry cleanup)."""
    verifier = GuideOperatorInboundJWTVerifier(settings, clock=clock)
    verified = verifier.verify(token, expected_scope)
    now = _aware_utc(clock or current_guide_operator_auth_clock())
    retain_until = datetime.fromtimestamp(
        verified.expires_at + MAX_CLOCK_SKEW_SECONDS, timezone.utc
    )
    claimed = claim_guide_operator_service_jti(
        verified.jti_hash,
        now.isoformat(),
        retain_until.isoformat(),
        now_iso=now.isoformat(),
    )
    if not claimed:
        _log_auth_failure()
        raise GuideOperatorServiceAuthenticationError("Service authentication failed")
    return verified
