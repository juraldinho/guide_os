"""HTTP settings for Guide Operator → Guide OS integration intake (GO8D1).

Feature flag defaults off. Does not start Telegram polling or Mini App routes.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})
_HOST_PATTERN = re.compile(
    r"^(?:127\.0\.0\.1|localhost|::1|[0-9a-fA-F:.]+|[a-zA-Z0-9.-]+)\Z"
)


class GuideOperatorIntegrationConfigurationError(ValueError):
    """Raised when integration HTTP is enabled with invalid host/port."""


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_VALUES:
            return True
        if lowered in _FALSE_VALUES:
            return False
    raise GuideOperatorIntegrationConfigurationError(
        "Guide Operator integration configuration is invalid"
    )


@dataclass(frozen=True)
class GuideOperatorIntegrationSettings:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8084

    @classmethod
    def disabled(cls) -> GuideOperatorIntegrationSettings:
        return cls(enabled=False, host="127.0.0.1", port=8084)

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> GuideOperatorIntegrationSettings:
        source: Mapping[str, str] = os.environ if values is None else values
        enabled = _as_bool(
            source.get("GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED", "false")
        )
        if not enabled:
            return cls.disabled()
        host = source.get("GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_HOST", "127.0.0.1")
        port_raw = source.get("GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_PORT", "8084")
        if not isinstance(host, str) or _HOST_PATTERN.fullmatch(host) is None:
            raise GuideOperatorIntegrationConfigurationError(
                "Guide Operator integration configuration is invalid"
            )
        app_env = source.get("APP_ENV", "development")
        if app_env == "production" and host in {"0.0.0.0", "::"}:
            raise GuideOperatorIntegrationConfigurationError(
                "Guide Operator integration configuration is invalid"
            )
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            raise GuideOperatorIntegrationConfigurationError(
                "Guide Operator integration configuration is invalid"
            ) from None
        if not (1 <= port <= 65535):
            raise GuideOperatorIntegrationConfigurationError(
                "Guide Operator integration configuration is invalid"
            )
        return cls(enabled=True, host=host, port=port)
