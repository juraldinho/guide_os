from dataclasses import dataclass
import math
import os
from typing import Mapping
from urllib.parse import urlsplit


class GuideShopSettingsError(ValueError):
    pass


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


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


def _read_bounded_float(
    values: Mapping[str, str], name: str, default: float, maximum: float
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
    if not math.isfinite(value) or value <= 0 or value > maximum:
        raise GuideShopSettingsError(f"Invalid value for {name}")
    return value


def _read_bounded_int(
    values: Mapping[str, str], name: str, default: int, maximum: int
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
    if str(value) != raw_value or value <= 0 or value > maximum:
        raise GuideShopSettingsError(f"Invalid value for {name}")
    return value


@dataclass(frozen=True)
class GuideShopHTTPSettings:
    base_url: str
    request_timeout_seconds: float = 10.0
    max_retries: int = 2
    max_retry_after_seconds: float = 10.0

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "GuideShopHTTPSettings":
        source = os.environ if values is None else values
        base_url = source.get("GUIDESHOP_API_BASE_URL")
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

        app_env = source.get("APP_ENV")
        if not isinstance(app_env, str):
            raise GuideShopSettingsError("APP_ENV is required for GuideShop HTTP")
        normalized_env = app_env.casefold()
        if normalized_env not in {"development", "test", "staging", "production"}:
            raise GuideShopSettingsError("Invalid APP_ENV for GuideShop HTTP")
        if normalized_env in {"staging", "production"} and parsed.scheme != "https":
            raise GuideShopSettingsError("HTTPS is required for GuideShop HTTP")
        if parsed.scheme == "http" and normalized_env not in {"development", "test"}:
            raise GuideShopSettingsError("HTTP is not allowed for GuideShop HTTP")

        return cls(
            base_url=base_url.rstrip("/"),
            request_timeout_seconds=_read_bounded_float(
                source, "GUIDESHOP_API_TIMEOUT_SECONDS", 10.0, 60.0
            ),
            max_retries=_read_bounded_int(
                source, "GUIDESHOP_API_MAX_RETRIES", 2, 5
            ),
            max_retry_after_seconds=_read_bounded_float(
                source,
                "GUIDESHOP_API_MAX_RETRY_AFTER_SECONDS",
                10.0,
                60.0,
            ),
        )
