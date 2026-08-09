import base64
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.guide_shop_settings import GuideShopJWTSigningSettings


ALGORITHM = "EdDSA"
TOKEN_TYPE = "guideshop-service+jwt"
ISSUER = "guide-os"
AUDIENCE = "guideshop-integration"
SCOPE = "guideshop:read"
TOKEN_TTL_SECONDS = 60


class GuideShopAuthenticationConfigurationError(ValueError):
    pass


class GuideShopTokenSigningError(RuntimeError):
    pass


class GuideShopJWTAccessTokenProvider:
    def __init__(
        self,
        settings: GuideShopJWTSigningSettings,
        *,
        clock: Callable[[], datetime] | None = None,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        if not isinstance(settings, GuideShopJWTSigningSettings):
            raise GuideShopAuthenticationConfigurationError(
                "Invalid GuideShop authentication configuration"
            )
        if clock is not None and not callable(clock):
            raise GuideShopAuthenticationConfigurationError(
                "Invalid GuideShop authentication configuration"
            )
        if not callable(random_bytes):
            raise GuideShopAuthenticationConfigurationError(
                "Invalid GuideShop authentication configuration"
            )
        try:
            private_key = serialization.load_pem_private_key(
                settings.private_key_pem.encode("ascii"), password=None
            )
        except Exception:
            raise GuideShopAuthenticationConfigurationError(
                "Invalid GuideShop authentication configuration"
            ) from None
        if not isinstance(private_key, Ed25519PrivateKey):
            raise GuideShopAuthenticationConfigurationError(
                "Invalid GuideShop authentication configuration"
            )
        self._key_id = settings.key_id
        self._private_key = private_key
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._random_bytes = random_bytes

    @staticmethod
    def _validate_identity(guide_os_id: object) -> str:
        if not isinstance(guide_os_id, str) or not guide_os_id:
            raise GuideShopTokenSigningError("GuideShop token signing failed")
        try:
            parsed = UUID(guide_os_id)
        except (ValueError, AttributeError, TypeError):
            raise GuideShopTokenSigningError("GuideShop token signing failed") from None
        if parsed.version != 4 or str(parsed) != guide_os_id:
            raise GuideShopTokenSigningError("GuideShop token signing failed")
        return guide_os_id

    async def get_access_token(self, guide_os_id: str) -> str:
        identity = self._validate_identity(guide_os_id)
        try:
            now = self._clock()
        except Exception:
            raise GuideShopTokenSigningError("GuideShop token signing failed") from None
        try:
            valid_clock = (
                isinstance(now, datetime)
                and now.tzinfo is not None
                and now.utcoffset() == timedelta(0)
            )
        except Exception:
            raise GuideShopTokenSigningError("GuideShop token signing failed") from None
        if not valid_clock:
            raise GuideShopTokenSigningError("GuideShop token signing failed")
        try:
            random_value = self._random_bytes(16)
        except Exception:
            raise GuideShopTokenSigningError("GuideShop token signing failed") from None
        if not isinstance(random_value, bytes) or len(random_value) != 16:
            raise GuideShopTokenSigningError("GuideShop token signing failed")

        try:
            issued_at = int(now.timestamp())
        except (OverflowError, OSError, ValueError):
            raise GuideShopTokenSigningError("GuideShop token signing failed") from None
        jti = base64.urlsafe_b64encode(random_value).rstrip(b"=").decode("ascii")
        headers = {
            "alg": ALGORITHM,
            "typ": TOKEN_TYPE,
            "kid": self._key_id,
        }
        claims = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": f"guide_os:{identity}",
            "guide_os_id": identity,
            "scope": SCOPE,
            "iat": issued_at,
            "nbf": issued_at,
            "exp": issued_at + TOKEN_TTL_SECONDS,
            "jti": jti,
        }
        try:
            token = jwt.encode(
                claims,
                self._private_key,
                algorithm=ALGORITHM,
                headers=headers,
            )
        except Exception:
            raise GuideShopTokenSigningError("GuideShop token signing failed") from None
        if not isinstance(token, str) or not token:
            raise GuideShopTokenSigningError("GuideShop token signing failed")
        return token
