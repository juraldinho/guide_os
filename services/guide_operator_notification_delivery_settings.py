"""GO10A2A: settings for Guide Operator → guide Telegram notification delivery.

Feature flag defaults off. When enabled, BOT_TOKEN and an approved Mini App
HTTPS public URL are required and fail closed.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from services.miniapp_api_settings import normalize_miniapp_public_url

_APP_ENVIRONMENTS = frozenset({"development", "test", "staging", "production"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})
# Telegram bot tokens look like digits:secret; never log the value.
_BOT_TOKEN_RE = re.compile(r"^\d{5,20}:[A-Za-z0-9_-]{20,}$")
_DEFAULT_TELEGRAM_API_BASE = "https://api.telegram.org"


class GuideOperatorNotificationDeliveryConfigurationError(ValueError):
    """Raised when notification delivery is enabled with incomplete/invalid config."""


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_VALUES:
            return True
        if lowered in _FALSE_VALUES:
            return False
    raise GuideOperatorNotificationDeliveryConfigurationError(
        "Guide Operator notification delivery configuration is invalid"
    )


def _validate_bot_token(value: object) -> str:
    if not isinstance(value, str):
        raise GuideOperatorNotificationDeliveryConfigurationError(
            "Guide Operator notification delivery configuration is invalid"
        )
    token = value.strip()
    if _BOT_TOKEN_RE.fullmatch(token) is None:
        raise GuideOperatorNotificationDeliveryConfigurationError(
            "Guide Operator notification delivery configuration is invalid"
        )
    return token


def _validate_api_base(value: object) -> str:
    if not isinstance(value, str):
        raise GuideOperatorNotificationDeliveryConfigurationError(
            "Guide Operator notification delivery configuration is invalid"
        )
    raw = value.strip().rstrip("/")
    if not raw.startswith("https://") or " " in raw or "?" in raw or "#" in raw:
        raise GuideOperatorNotificationDeliveryConfigurationError(
            "Guide Operator notification delivery configuration is invalid"
        )
    return raw


@dataclass(frozen=True)
class GuideOperatorNotificationDeliverySettings:
    enabled: bool = False
    app_env: str = "development"
    bot_token: str | None = None
    mini_app_public_url: str | None = None
    telegram_api_base_url: str = _DEFAULT_TELEGRAM_API_BASE

    @classmethod
    def disabled(
        cls, app_env: str = "development"
    ) -> GuideOperatorNotificationDeliverySettings:
        if app_env not in _APP_ENVIRONMENTS:
            raise GuideOperatorNotificationDeliveryConfigurationError(
                "Guide Operator notification delivery configuration is invalid"
            )
        return cls(enabled=False, app_env=app_env)

    @classmethod
    def enabled_with(
        cls,
        *,
        app_env: str,
        bot_token: str,
        mini_app_public_url: str,
        telegram_api_base_url: str = _DEFAULT_TELEGRAM_API_BASE,
    ) -> GuideOperatorNotificationDeliverySettings:
        if app_env not in _APP_ENVIRONMENTS:
            raise GuideOperatorNotificationDeliveryConfigurationError(
                "Guide Operator notification delivery configuration is invalid"
            )
        public_url = normalize_miniapp_public_url(mini_app_public_url, app_env)
        if public_url is None:
            raise GuideOperatorNotificationDeliveryConfigurationError(
                "Guide Operator notification delivery configuration is invalid"
            )
        # Staging/production already require HTTPS via normalize_miniapp_public_url.
        # Delivery additionally requires HTTPS always (Telegram WebApp button).
        if not public_url.startswith("https://"):
            raise GuideOperatorNotificationDeliveryConfigurationError(
                "Guide Operator notification delivery configuration is invalid"
            )
        return cls(
            enabled=True,
            app_env=app_env,
            bot_token=_validate_bot_token(bot_token),
            mini_app_public_url=public_url,
            telegram_api_base_url=_validate_api_base(telegram_api_base_url),
        )

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> GuideOperatorNotificationDeliverySettings:
        source: Mapping[str, str] = os.environ if values is None else values
        app_env = source.get("APP_ENV", "development")
        if app_env not in _APP_ENVIRONMENTS:
            raise GuideOperatorNotificationDeliveryConfigurationError(
                "Guide Operator notification delivery configuration is invalid"
            )
        enabled = _as_bool(
            source.get(
                "GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_DELIVERY_ENABLED", "false"
            )
        )
        if not enabled:
            return cls.disabled(app_env)
        api_base = source.get(
            "GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_TELEGRAM_API_BASE_URL",
            _DEFAULT_TELEGRAM_API_BASE,
        )
        return cls.enabled_with(
            app_env=app_env,
            bot_token=source.get("BOT_TOKEN", ""),
            mini_app_public_url=source.get("MINI_APP_PUBLIC_URL", ""),
            telegram_api_base_url=api_base
            if isinstance(api_base, str)
            else _DEFAULT_TELEGRAM_API_BASE,
        )
