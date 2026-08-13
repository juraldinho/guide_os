from dataclasses import dataclass, field
import json
import math
import os
import re
from typing import Mapping
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class GuideShopSettingsError(ValueError):
    pass


class GuideShopJWTSigningSettingsError(GuideShopSettingsError):
    pass


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_APP_ENVIRONMENTS = {"development", "test", "staging", "production"}
_JWT_KEY_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
_PKCS8_PEM_PATTERN = re.compile(
    r"-----BEGIN PRIVATE KEY-----\n"
    r"(?:[A-Za-z0-9+/]{1,64}\n)+"
    r"-----END PRIVATE KEY-----(?:\n)?\Z"
)
_LINK_KID_PATTERN = re.compile(r"[a-z0-9-]{8,64}\Z")
_PUBLIC_KEY_PEM_PATTERN = re.compile(
    r"-----BEGIN PUBLIC KEY-----\n"
    r"(?:[A-Za-z0-9+/=]{1,64}\n)+"
    r"-----END PUBLIC KEY-----(?:\n)?\Z"
)
_PROVIDER_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
_PROVIDER_RAILWAY_STAGING_HOSTS = frozenset({"0.0.0.0"})
_PROVIDER_LOCAL_APP_ENVS = frozenset({"development", "test"})


class GuideShopInboundJWTSettingsError(GuideShopSettingsError):
    pass


@dataclass(frozen=True)
class GuideShopLinkProviderSettings:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8081
    app_env: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.enabled, bool)
            or not isinstance(self.host, str)
            or isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 1 <= self.port <= 65535
        ):
            raise GuideShopSettingsError("Invalid GuideShop provider configuration")
        if not self.enabled:
            if (
                self.host not in _PROVIDER_LOOPBACK_HOSTS
                or (
                    self.app_env is not None
                    and self.app_env not in _APP_ENVIRONMENTS
                )
            ):
                raise GuideShopSettingsError("Invalid GuideShop provider configuration")
            return
        if self.app_env in _PROVIDER_LOCAL_APP_ENVS:
            if self.host not in _PROVIDER_LOOPBACK_HOSTS:
                raise GuideShopSettingsError("Invalid GuideShop provider configuration")
            return
        if self.app_env == "staging":
            if self.host not in _PROVIDER_RAILWAY_STAGING_HOSTS:
                raise GuideShopSettingsError("Invalid GuideShop provider configuration")
            return
        raise GuideShopSettingsError("Invalid GuideShop provider configuration")

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "GuideShopLinkProviderSettings":
        source = os.environ if values is None else values
        enabled = _read_flag(source, "GUIDESHOP_LINK_PROVIDER_ENABLED")
        if not enabled:
            return cls()
        app_env = source.get("APP_ENV")
        if app_env in _PROVIDER_LOCAL_APP_ENVS:
            host = source.get("GUIDESHOP_LINK_PROVIDER_HOST", "127.0.0.1")
            port = _read_int(source, "GUIDESHOP_LINK_PROVIDER_PORT", 8081)
            return cls(
                enabled=True,
                host=host,
                port=port,
                app_env=app_env,
            )
        if app_env == "staging":
            if not _read_flag(source, "GUIDESHOP_LINK_PROVIDER_STAGING_ENABLED"):
                raise GuideShopSettingsError("Invalid GuideShop provider configuration")
            if "GUIDESHOP_LINK_PROVIDER_HOST" not in source:
                raise GuideShopSettingsError("Invalid GuideShop provider configuration")
            host = source.get("GUIDESHOP_LINK_PROVIDER_HOST")
            port = _read_required_int(source, "PORT")
            return cls(
                enabled=True,
                host=host,
                port=port,
                app_env=app_env,
            )
        raise GuideShopSettingsError("Invalid GuideShop provider configuration")


@dataclass(frozen=True, init=False)
class GuideShopInboundJWTSettings:
    app_env: str
    public_keys: tuple[tuple[str, str], ...] = field(repr=False, compare=False)

    def __init__(self, app_env: str, public_keys: Mapping[str, str]) -> None:
        if (
            not isinstance(app_env, str)
            or app_env not in _APP_ENVIRONMENTS
            or not isinstance(public_keys, Mapping)
        ):
            raise GuideShopInboundJWTSettingsError(
                "Invalid GuideShop verification configuration"
            )
        items = []
        seen = set()
        for kid, pem in public_keys.items():
            if (
                not isinstance(kid, str)
                or _LINK_KID_PATTERN.fullmatch(kid) is None
                or kid in seen
                or not isinstance(pem, str)
                or _PUBLIC_KEY_PEM_PATTERN.fullmatch(pem) is None
            ):
                raise GuideShopInboundJWTSettingsError(
                    "Invalid GuideShop verification configuration"
                )
            try:
                key = serialization.load_pem_public_key(pem.encode("ascii"))
            except Exception:
                raise GuideShopInboundJWTSettingsError(
                    "Invalid GuideShop verification configuration"
                ) from None
            if not isinstance(key, Ed25519PublicKey):
                raise GuideShopInboundJWTSettingsError(
                    "Invalid GuideShop verification configuration"
                )
            seen.add(kid)
            items.append((kid, pem))
        if not items:
            raise GuideShopInboundJWTSettingsError(
                "Invalid GuideShop verification configuration"
            )
        object.__setattr__(self, "app_env", app_env)
        object.__setattr__(self, "public_keys", tuple(items))

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "GuideShopInboundJWTSettings":
        source = os.environ if values is None else values
        raw_keys = source.get("GUIDESHOP_LINK_JWT_PUBLIC_KEYS")
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result
        try:
            parsed = (
                json.loads(raw_keys, object_pairs_hook=unique_object)
                if isinstance(raw_keys, str)
                else None
            )
        except (TypeError, ValueError):
            parsed = None
        if not isinstance(parsed, dict):
            raise GuideShopInboundJWTSettingsError(
                "Invalid GuideShop verification configuration"
            )
        return cls(source.get("APP_ENV"), parsed)


@dataclass(frozen=True)
class GuideShopJWTSigningSettings:
    app_env: str
    key_id: str
    private_key_pem: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.app_env, str)
            or self.app_env not in _APP_ENVIRONMENTS
        ):
            raise GuideShopJWTSigningSettingsError(
                "Invalid GuideShop signing configuration"
            )
        if (
            not isinstance(self.key_id, str)
            or not self.key_id.isascii()
            or _JWT_KEY_ID_PATTERN.fullmatch(self.key_id) is None
        ):
            raise GuideShopJWTSigningSettingsError(
                "Invalid GuideShop signing configuration"
            )
        if (
            not isinstance(self.private_key_pem, str)
            or not self.private_key_pem
            or not self.private_key_pem.isascii()
            or _PKCS8_PEM_PATTERN.fullmatch(self.private_key_pem) is None
        ):
            raise GuideShopJWTSigningSettingsError(
                "Invalid GuideShop signing configuration"
            )
        try:
            private_key = serialization.load_pem_private_key(
                self.private_key_pem.encode("ascii"), password=None
            )
        except Exception:
            raise GuideShopJWTSigningSettingsError(
                "Invalid GuideShop signing configuration"
            ) from None
        if not isinstance(private_key, Ed25519PrivateKey):
            raise GuideShopJWTSigningSettingsError(
                "Invalid GuideShop signing configuration"
            )

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "GuideShopJWTSigningSettings":
        source = os.environ if values is None else values
        return cls(
            app_env=source.get("APP_ENV"),
            key_id=source.get("GUIDESHOP_JWT_KEY_ID"),
            private_key_pem=source.get("GUIDESHOP_JWT_PRIVATE_KEY"),
        )


def _read_flag(values: Mapping[str, str], name: str) -> bool:
    if name not in values:
        return False

    value = values[name]
    if not isinstance(value, str) or not value:
        raise GuideShopSettingsError(f"Invalid value for {name}")

    normalized = value.casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise GuideShopSettingsError(f"Invalid value for {name}")


@dataclass(frozen=True)
class GuideShopFeatureFlags:
    reads_enabled: bool = False
    linking_enabled: bool = False
    events_enabled: bool = False
    notifications_enabled: bool = False

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "GuideShopFeatureFlags":
        source = os.environ if values is None else values
        return cls(
            reads_enabled=_read_flag(source, "GUIDESHOP_READS_ENABLED"),
            linking_enabled=_read_flag(source, "GUIDESHOP_LINKING_ENABLED"),
            events_enabled=_read_flag(source, "GUIDESHOP_EVENTS_ENABLED"),
            notifications_enabled=_read_flag(
                source, "GUIDESHOP_NOTIFICATIONS_ENABLED"
            ),
        )


@dataclass(frozen=True)
class GuideShopRuntimeSettings:
    use_fake: bool = False

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "GuideShopRuntimeSettings":
        source = os.environ if values is None else values
        use_fake = _read_flag(source, "GUIDESHOP_USE_FAKE")
        if use_fake:
            app_env = source.get("APP_ENV")
            if not isinstance(app_env, str) or app_env.casefold() not in {
                "development",
                "test",
            }:
                raise GuideShopSettingsError(
                    "GuideShop fake is allowed only in development or test"
                )
        return cls(use_fake=use_fake)


def _read_float(
    values: Mapping[str, str], name: str, default: float
) -> float:
    raw_value = values.get(name)
    if raw_value is None:
        return default
    if isinstance(raw_value, bool) or not isinstance(raw_value, str) or not raw_value:
        raise GuideShopSettingsError(f"Invalid value for {name}")
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise GuideShopSettingsError(f"Invalid value for {name}") from exc
    return value


def _read_int(
    values: Mapping[str, str], name: str, default: int
) -> int:
    raw_value = values.get(name)
    if raw_value is None:
        return default
    if isinstance(raw_value, bool) or not isinstance(raw_value, str) or not raw_value:
        raise GuideShopSettingsError(f"Invalid value for {name}")
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise GuideShopSettingsError(f"Invalid value for {name}") from exc
    if str(value) != raw_value:
        raise GuideShopSettingsError(f"Invalid value for {name}")
    return value


def _read_required_int(values: Mapping[str, str], name: str) -> int:
    if name not in values:
        raise GuideShopSettingsError(f"Invalid value for {name}")
    return _read_int(values, name, 0)


@dataclass(frozen=True)
class GuideShopHTTPSettings:
    base_url: str
    app_env: str
    request_timeout_seconds: float = 10.0
    max_retries: int = 2
    max_retry_after_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not isinstance(self.app_env, str):
            raise GuideShopSettingsError("Invalid APP_ENV for GuideShop HTTP")
        normalized_env = self.app_env.casefold()
        if normalized_env not in {"development", "test", "staging", "production"}:
            raise GuideShopSettingsError("Invalid APP_ENV for GuideShop HTTP")

        base_url = self.base_url
        if (
            not isinstance(base_url, str)
            or not base_url
            or base_url != base_url.strip()
            or not base_url.isascii()
            or any(character.isspace() for character in base_url)
        ):
            raise GuideShopSettingsError("Invalid GuideShop API base URL")

        try:
            parsed = urlsplit(base_url)
            parsed.port
        except ValueError as exc:
            raise GuideShopSettingsError("Invalid GuideShop API base URL") from exc

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or not all(
                character.isalnum() or character in ".-"
                for character in parsed.hostname
            )
        ):
            raise GuideShopSettingsError("Invalid GuideShop API base URL")
        if normalized_env in {"staging", "production"} and parsed.scheme != "https":
            raise GuideShopSettingsError("HTTPS is required for GuideShop HTTP")
        if parsed.scheme == "http" and normalized_env not in {"development", "test"}:
            raise GuideShopSettingsError("HTTP is not allowed for GuideShop HTTP")

        timeout = self.request_timeout_seconds
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
            or timeout > 60
        ):
            raise GuideShopSettingsError("Invalid GuideShop request timeout")
        if (
            isinstance(self.max_retries, bool)
            or not isinstance(self.max_retries, int)
            or self.max_retries <= 0
            or self.max_retries > 5
        ):
            raise GuideShopSettingsError("Invalid GuideShop retry count")
        retry_after = self.max_retry_after_seconds
        if (
            isinstance(retry_after, bool)
            or not isinstance(retry_after, (int, float))
            or not math.isfinite(retry_after)
            or retry_after <= 0
            or retry_after > 60
        ):
            raise GuideShopSettingsError("Invalid GuideShop Retry-After limit")

        object.__setattr__(self, "app_env", normalized_env)
        object.__setattr__(self, "base_url", base_url.rstrip("/"))
        object.__setattr__(self, "request_timeout_seconds", float(timeout))
        object.__setattr__(self, "max_retry_after_seconds", float(retry_after))

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "GuideShopHTTPSettings":
        source = os.environ if values is None else values
        base_url = source.get("GUIDESHOP_API_BASE_URL")
        app_env = source.get("APP_ENV")

        return cls(
            base_url=base_url,
            app_env=app_env,
            request_timeout_seconds=_read_float(
                source, "GUIDESHOP_API_TIMEOUT_SECONDS", 10.0
            ),
            max_retries=_read_int(
                source, "GUIDESHOP_API_MAX_RETRIES", 2
            ),
            max_retry_after_seconds=_read_float(
                source,
                "GUIDESHOP_API_MAX_RETRY_AFTER_SECONDS",
                10.0,
            ),
        )
