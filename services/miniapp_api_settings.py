from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit

from services.guide_shop_settings import GuideShopSettingsError, _read_flag, _read_int

_LOCAL_MINIAPP_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_MINIAPP_SECURE_ENVS = frozenset({"staging", "production"})
_MINIAPP_LOCAL_ENVS = frozenset({"development", "test"})


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


def _normalized_app_env(values: Mapping[str, str]) -> str:
    raw = values.get("APP_ENV", "development")
    if not isinstance(raw, str):
        return "development"
    normalized = raw.strip().lower()
    if normalized in _MINIAPP_SECURE_ENVS:
        return normalized
    if normalized in _MINIAPP_LOCAL_ENVS:
        return normalized
    return "development"


def normalize_miniapp_public_url(raw: str | None, app_env: str) -> str | None:
    if not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if not candidate or not candidate.isascii() or any(character.isspace() for character in candidate):
        return None

    try:
        parsed = urlsplit(candidate)
        parsed.port
    except ValueError:
        return None

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None

    normalized_env = app_env.strip().lower()
    if normalized_env in _MINIAPP_SECURE_ENVS:
        if parsed.scheme != "https":
            return None
    elif parsed.scheme == "http":
        if parsed.hostname not in _LOCAL_MINIAPP_HOSTS:
            return None

    return candidate


def derive_miniapp_allowed_origin(normalized_public_url: str) -> str:
    parsed = urlsplit(normalized_public_url)
    hostname = parsed.hostname
    if not hostname:
        raise MiniAppApiSettingsError("Invalid Mini App public URL")
    scheme = parsed.scheme
    port = parsed.port
    if port is None or (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return f"{scheme}://{hostname}"
    return f"{scheme}://{hostname}:{port}"


@dataclass(frozen=True)
class MiniAppMenuSettings:
    enabled: bool = False
    public_url: str | None = None

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "MiniAppMenuSettings":
        source = os.environ if values is None else values
        enabled = _read_flag(source, "MINI_APP_ENABLED")
        if not enabled:
            return cls()
        app_env = _normalized_app_env(source)
        public_url = normalize_miniapp_public_url(source.get("MINI_APP_PUBLIC_URL", ""), app_env)
        return cls(enabled=True, public_url=public_url)


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
    allowed_origin: str | None = None

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
            or not (self.allowed_origin is None or isinstance(self.allowed_origin, str))
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
        app_env = _normalized_app_env(source)
        public_url = normalize_miniapp_public_url(source.get("MINI_APP_PUBLIC_URL", ""), app_env)
        allowed_origin = (
            derive_miniapp_allowed_origin(public_url) if public_url is not None else None
        )
        return cls(
            enabled=enabled,
            host=host,
            port=port,
            dev_auth=dev_auth,
            bot_token=bot_token,
            session_ttl_seconds=session_ttl_seconds,
            initdata_max_age_seconds=initdata_max_age_seconds,
            allowlist=allowlist,
            allowed_origin=allowed_origin,
        )
