from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from services.guide_shop_settings import GuideShopSettingsError, _read_flag, _read_int


class MiniAppApiSettingsError(GuideShopSettingsError):
    """Invalid Mini App API configuration."""


def _read_allowlist(values: Mapping[str, str], name: str) -> frozenset[int]:
    raw_value = values.get(name, "")
    if not isinstance(raw_value, str) or not raw_value.strip():
        return frozenset()
    ids: list[int] = []
    for part in raw_value.split(","):
        piece = part.strip()
        if not piece:
            continue
        try:
            user_id = int(piece)
        except ValueError as exc:
            raise MiniAppApiSettingsError(f"Invalid value for {name}") from exc
        if str(user_id) != piece:
            raise MiniAppApiSettingsError(f"Invalid value for {name}")
        ids.append(user_id)
    return frozenset(ids)


@dataclass(frozen=True)
class MiniAppApiSettings:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8083
    dev_auth: bool = False
    bot_token: str = ""
    session_ttl_seconds: int = 3600
    initdata_max_age_seconds: int = 86400
    allowlist: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.enabled, bool)
            or not isinstance(self.host, str)
            or isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 1 <= self.port <= 65535
            or not isinstance(self.dev_auth, bool)
            or not isinstance(self.bot_token, str)
            or isinstance(self.session_ttl_seconds, bool)
            or not isinstance(self.session_ttl_seconds, int)
            or self.session_ttl_seconds <= 0
            or isinstance(self.initdata_max_age_seconds, bool)
            or not isinstance(self.initdata_max_age_seconds, int)
            or self.initdata_max_age_seconds <= 0
            or not isinstance(self.allowlist, frozenset)
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
        bot_token = source.get("BOT_TOKEN", "").strip()
        session_ttl_seconds = _read_int(source, "MINI_APP_SESSION_TTL_SECONDS", 3600)
        initdata_max_age_seconds = _read_int(source, "MINI_APP_INITDATA_MAX_AGE", 86400)
        allowlist = _read_allowlist(source, "MINI_APP_API_ALLOWLIST")
        return cls(
            enabled=enabled,
            host=host,
            port=port,
            dev_auth=dev_auth,
            bot_token=bot_token,
            session_ttl_seconds=session_ttl_seconds,
            initdata_max_age_seconds=initdata_max_age_seconds,
            allowlist=allowlist,
        )
