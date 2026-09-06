"""Guide OS → Guide Operator outbound HTTP settings (GO8F2A).

Feature flag defaults off. When enabled, base URL and GO8B outbound signing
are required and fail closed. HTTPS is required outside local development/test.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from services.guide_operator_service_auth_settings import (
    GuideOperatorOutboundJWTSettings,
    GuideOperatorServiceAuthConfigurationError,
    GuideOperatorServiceAuthSettings,
    load_guide_operator_service_auth_settings,
)

_APP_ENVIRONMENTS = frozenset({"development", "test", "staging", "production"})
_HTTPS_ONLY_ENVIRONMENTS = frozenset({"staging", "production"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})
_HOST_OK = re.compile(r"^[A-Za-z0-9.-]+(?::\d+)?\Z")


class GuideOperatorOutboundConfigurationError(ValueError):
    """Raised when outbound delivery is enabled with incomplete/invalid config."""


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_VALUES:
            return True
        if lowered in _FALSE_VALUES:
            return False
    raise GuideOperatorOutboundConfigurationError(
        "Guide Operator outbound configuration is invalid"
    )


def validate_guide_operator_base_url(value: str, *, app_env: str) -> str:
    if app_env not in _APP_ENVIRONMENTS:
        raise GuideOperatorOutboundConfigurationError(
            "Guide Operator outbound configuration is invalid"
        )
    if not isinstance(value, str):
        raise GuideOperatorOutboundConfigurationError(
            "Guide Operator outbound configuration is invalid"
        )
    raw = value.strip().rstrip("/")
    parsed = urlparse(raw)
    if (
        not raw
        or parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.params
        or parsed.path not in {"", "/"}
        or _HOST_OK.fullmatch(parsed.netloc) is None
    ):
        raise GuideOperatorOutboundConfigurationError(
            "Guide Operator outbound configuration is invalid"
        )
    if app_env in _HTTPS_ONLY_ENVIRONMENTS and parsed.scheme != "https":
        raise GuideOperatorOutboundConfigurationError(
            "Guide Operator outbound configuration is invalid"
        )
    return raw


@dataclass(frozen=True)
class GuideOperatorOutboundSettings:
    enabled: bool = False
    app_env: str = "development"
    base_url: str | None = None
    outbound_jwt: GuideOperatorOutboundJWTSettings | None = None

    @classmethod
    def disabled(cls, app_env: str = "development") -> GuideOperatorOutboundSettings:
        if app_env not in _APP_ENVIRONMENTS:
            raise GuideOperatorOutboundConfigurationError(
                "Guide Operator outbound configuration is invalid"
            )
        return cls(enabled=False, app_env=app_env, base_url=None, outbound_jwt=None)

    @classmethod
    def enabled_with(
        cls,
        *,
        app_env: str,
        base_url: str,
        outbound_jwt: GuideOperatorOutboundJWTSettings,
    ) -> GuideOperatorOutboundSettings:
        if not isinstance(outbound_jwt, GuideOperatorOutboundJWTSettings):
            raise GuideOperatorOutboundConfigurationError(
                "Guide Operator outbound configuration is invalid"
            )
        return cls(
            enabled=True,
            app_env=app_env,
            base_url=validate_guide_operator_base_url(base_url, app_env=app_env),
            outbound_jwt=outbound_jwt,
        )

    @classmethod
    def from_env(
        cls,
        values: Mapping[str, str] | None = None,
        *,
        auth_settings: GuideOperatorServiceAuthSettings | None = None,
    ) -> GuideOperatorOutboundSettings:
        source: Mapping[str, str] = os.environ if values is None else values
        app_env = source.get("APP_ENV", "development")
        if app_env not in _APP_ENVIRONMENTS:
            raise GuideOperatorOutboundConfigurationError(
                "Guide Operator outbound configuration is invalid"
            )
        enabled = _as_bool(
            source.get("GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_ENABLED", "false")
        )
        if not enabled:
            return cls.disabled(app_env)

        try:
            auth = (
                auth_settings
                if auth_settings is not None
                else load_guide_operator_service_auth_settings()
            )
        except GuideOperatorServiceAuthConfigurationError as exc:
            raise GuideOperatorOutboundConfigurationError(
                "Guide Operator outbound configuration is invalid"
            ) from exc
        if not auth.enabled or auth.outbound is None:
            raise GuideOperatorOutboundConfigurationError(
                "Guide Operator outbound configuration is invalid"
            )

        base_url = source.get("GUIDE_OS_GUIDE_OPERATOR_BASE_URL", "")
        if not isinstance(base_url, str):
            raise GuideOperatorOutboundConfigurationError(
                "Guide Operator outbound configuration is invalid"
            )
        return cls.enabled_with(
            app_env=app_env,
            base_url=base_url,
            outbound_jwt=auth.outbound,
        )
