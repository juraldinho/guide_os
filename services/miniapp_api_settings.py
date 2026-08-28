from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from services.guide_shop_settings import GuideShopSettingsError, _read_flag, _read_int


class MiniAppApiSettingsError(GuideShopSettingsError):
    """Invalid Mini App API configuration."""


@dataclass(frozen=True)
class MiniAppApiSettings:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8083
    dev_auth: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.enabled, bool)
            or not isinstance(self.host, str)
            or isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 1 <= self.port <= 65535
            or not isinstance(self.dev_auth, bool)
        ):
            raise MiniAppApiSettingsError("Invalid Mini App API configuration")
        if self.enabled and self.host not in {"127.0.0.1", "0.0.0.0", "localhost"}:
            raise MiniAppApiSettingsError("Invalid Mini App API configuration")

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "MiniAppApiSettings":
        source = os.environ if values is None else values
        enabled = _read_flag(source, "MINI_APP_API_ENABLED")
        if not enabled:
            return cls()
        host = source.get("MINI_APP_API_HOST", "127.0.0.1")
        port = _read_int(source, "MINI_APP_API_PORT", 8083)
        dev_auth = _read_flag(source, "MINI_APP_API_DEV_AUTH")
        return cls(enabled=enabled, host=host, port=port, dev_auth=dev_auth)
