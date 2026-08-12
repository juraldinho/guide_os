from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re

import jwt
from cryptography.hazmat.primitives import serialization

from database.queries import claim_guide_shop_link_jti
from services.guide_shop_settings import GuideShopInboundJWTSettings


ALGORITHM = "EdDSA"
TOKEN_TYPE = "guideshop-link-service+jwt"
ISSUER = "guideshop-integration"
AUDIENCE = "guide-os-integration"
SUBJECT = "guideshop:link-service"
ALLOWED_SCOPES = {"guideshop:link:exchange", "guideshop:link:status"}
MAX_TTL_SECONDS = 60
MAX_CLOCK_SKEW_SECONDS = 10
MAX_TOKEN_BYTES = 8192
_KID = re.compile(r"[a-z0-9-]{8,64}\Z")


class GuideShopAuthenticationError(Exception):
    pass


@dataclass(frozen=True)
class AuthenticatedGuideShopPrincipal:
    subject: str
    scope: str
    kid: str
    jti: str
    issued_at: int
    expires_at: int


class GuideShopInboundJWTVerifier:
    def __init__(self, settings: GuideShopInboundJWTSettings, *, clock=None) -> None:
        if not isinstance(settings, GuideShopInboundJWTSettings):
            raise GuideShopAuthenticationError("GuideShop authentication failed")
        self._keys = {}
        try:
            for kid, pem in settings.public_keys:
                self._keys[kid] = serialization.load_pem_public_key(
                    pem.encode("ascii")
                )
        except Exception:
            raise GuideShopAuthenticationError("GuideShop authentication failed") from None
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if not callable(self._clock):
            raise GuideShopAuthenticationError("GuideShop authentication failed")

    def _now(self) -> datetime:
        try:
            value = self._clock()
            valid = (
                isinstance(value, datetime)
                and value.tzinfo is not None
                and value.utcoffset() == timedelta(0)
            )
        except Exception:
            valid = False
        if not valid:
            raise GuideShopAuthenticationError("GuideShop authentication failed")
        return value

    @staticmethod
    def _numeric_date(value) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise GuideShopAuthenticationError("GuideShop authentication failed")
        return value

    def verify(self, token: str, expected_scope: str) -> AuthenticatedGuideShopPrincipal:
        try:
            if (
                not isinstance(token, str)
                or not token
                or len(token.encode("utf-8")) > MAX_TOKEN_BYTES
                or token.count(".") != 2
                or expected_scope not in ALLOWED_SCOPES
            ):
                raise GuideShopAuthenticationError("GuideShop authentication failed")
            header = jwt.get_unverified_header(token)
            allowed_header = {"alg", "kid", "typ", "crit"}
            if (
                not isinstance(header, dict)
                or set(header) - allowed_header
                or not {"alg", "kid", "typ"} <= set(header)
                or header["alg"] != ALGORITHM
                or header["typ"] != TOKEN_TYPE
                or not isinstance(header["kid"], str)
                or _KID.fullmatch(header["kid"]) is None
                or ("crit" in header and header["crit"] != [])
            ):
                raise GuideShopAuthenticationError("GuideShop authentication failed")
            key = self._keys.get(header["kid"])
            if key is None:
                raise GuideShopAuthenticationError("GuideShop authentication failed")
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
            required = {"iss", "aud", "sub", "scope", "iat", "exp", "jti"}
            if (
                not isinstance(claims, dict)
                or not required <= set(claims)
                or set(claims) - (required | {"nbf"})
                or claims["iss"] != ISSUER
                or claims["aud"] != AUDIENCE
                or claims["sub"] != SUBJECT
                or claims["scope"] not in ALLOWED_SCOPES
                or claims["scope"] != expected_scope
                or not isinstance(claims["jti"], str)
                or not 16 <= len(claims["jti"]) <= 256
            ):
                raise GuideShopAuthenticationError("GuideShop authentication failed")
            issued_at = self._numeric_date(claims["iat"])
            expires_at = self._numeric_date(claims["exp"])
            not_before = (
                self._numeric_date(claims["nbf"])
                if "nbf" in claims
                else None
            )
            now = self._now()
            now_seconds = now.timestamp()
            if (
                expires_at <= issued_at
                or expires_at - issued_at > MAX_TTL_SECONDS
                or issued_at > now_seconds + MAX_CLOCK_SKEW_SECONDS
                or expires_at + MAX_CLOCK_SKEW_SECONDS <= now_seconds
                or (
                    not_before is not None
                    and not_before > now_seconds + MAX_CLOCK_SKEW_SECONDS
                )
            ):
                raise GuideShopAuthenticationError("GuideShop authentication failed")
            jti_hash = hashlib.sha256(claims["jti"].encode("utf-8")).hexdigest()
            retain_until = datetime.fromtimestamp(
                expires_at + MAX_CLOCK_SKEW_SECONDS, timezone.utc
            )
            claimed = claim_guide_shop_link_jti(
                jti_hash, now.isoformat(), retain_until.isoformat()
            )
            if not claimed:
                raise GuideShopAuthenticationError("GuideShop authentication failed")
            return AuthenticatedGuideShopPrincipal(
                subject=SUBJECT,
                scope=claims["scope"],
                kid=header["kid"],
                jti=claims["jti"],
                issued_at=issued_at,
                expires_at=expires_at,
            )
        except GuideShopAuthenticationError:
            raise
        except Exception:
            raise GuideShopAuthenticationError("GuideShop authentication failed") from None
