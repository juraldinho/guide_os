"""Guide Operator ↔ Guide OS service-auth settings (GO8B / ADR-008).

Feature flag defaults off. When enabled, inbound Guide Operator public keys and
outbound Guide OS signing material are required and fail closed.
Never reuse GuideShop JWT keys.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


class GuideOperatorServiceAuthConfigurationError(ValueError):
    """Raised when service authentication is enabled with incomplete/invalid config."""


_APP_ENVIRONMENTS = frozenset({"development", "test", "staging", "production"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})
_KID_PATTERN = re.compile(r"[a-z0-9-]{8,64}\Z")
_PKCS8_PEM_PATTERN = re.compile(
    r"-----BEGIN PRIVATE KEY-----\n"
    r"(?:[A-Za-z0-9+/]{1,64}\n)+"
    r"-----END PRIVATE KEY-----(?:\n)?\Z"
)
_PUBLIC_KEY_PEM_PATTERN = re.compile(
    r"-----BEGIN PUBLIC KEY-----\n"
    r"(?:[A-Za-z0-9+/=]{1,64}\n)+"
    r"-----END PUBLIC KEY-----(?:\n)?\Z"
)


def _normalize_pem(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\\n", "\n")


def _kid_forbidden_for_env(app_env: str, kid: str) -> bool:
    tokens = set(kid.split("-"))
    if app_env == "production":
        return bool(tokens & {"staging", "test", "dev", "development"})
    if app_env == "staging":
        return "production" in tokens
    return False


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_VALUES:
            return True
        if lowered in _FALSE_VALUES:
            return False
    raise GuideOperatorServiceAuthConfigurationError(
        "Service authentication configuration is invalid"
    )


@dataclass(frozen=True, init=False)
class GuideOperatorInboundJWTSettings:
    """Public keys used to verify Guide Operator → Guide OS service JWTs."""

    public_keys: tuple[tuple[str, str], ...] = field(repr=False, compare=False)

    def __init__(self, public_keys: Mapping[str, str], *, app_env: str) -> None:
        if not isinstance(public_keys, Mapping) or not public_keys:
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            )
        items: list[tuple[str, str]] = []
        seen: set[str] = set()
        for kid, pem in public_keys.items():
            normalized = _normalize_pem(pem) if isinstance(pem, str) else ""
            if (
                not isinstance(kid, str)
                or _KID_PATTERN.fullmatch(kid) is None
                or kid in seen
                or _kid_forbidden_for_env(app_env, kid)
                or _PUBLIC_KEY_PEM_PATTERN.fullmatch(normalized) is None
            ):
                raise GuideOperatorServiceAuthConfigurationError(
                    "Service authentication configuration is invalid"
                )
            try:
                key = serialization.load_pem_public_key(normalized.encode("ascii"))
            except Exception:
                raise GuideOperatorServiceAuthConfigurationError(
                    "Service authentication configuration is invalid"
                ) from None
            if not isinstance(key, Ed25519PublicKey):
                raise GuideOperatorServiceAuthConfigurationError(
                    "Service authentication configuration is invalid"
                )
            seen.add(kid)
            items.append((kid, normalized))
        object.__setattr__(self, "public_keys", tuple(items))

    def __repr__(self) -> str:
        kids = ",".join(kid for kid, _pem in self.public_keys)
        return f"GuideOperatorInboundJWTSettings(kids={kids!r})"


@dataclass(frozen=True, init=False)
class GuideOperatorOutboundJWTSettings:
    """Private key used to sign Guide OS → Guide Operator service JWTs."""

    key_id: str
    private_key_pem: str = field(repr=False, compare=False)

    def __init__(self, key_id: str, private_key_pem: str, *, app_env: str) -> None:
        normalized = _normalize_pem(private_key_pem) if isinstance(private_key_pem, str) else ""
        if (
            not isinstance(key_id, str)
            or _KID_PATTERN.fullmatch(key_id) is None
            or _kid_forbidden_for_env(app_env, key_id)
            or _PKCS8_PEM_PATTERN.fullmatch(normalized) is None
        ):
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            )
        try:
            key = serialization.load_pem_private_key(
                normalized.encode("ascii"), password=None
            )
        except Exception:
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            ) from None
        if not isinstance(key, Ed25519PrivateKey):
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            )
        object.__setattr__(self, "key_id", key_id)
        object.__setattr__(self, "private_key_pem", normalized)

    def __repr__(self) -> str:
        return f"GuideOperatorOutboundJWTSettings(key_id={self.key_id!r})"


@dataclass(frozen=True)
class GuideOperatorServiceAuthSettings:
    enabled: bool
    app_env: str
    inbound: GuideOperatorInboundJWTSettings | None = field(default=None, repr=True)
    outbound: GuideOperatorOutboundJWTSettings | None = field(default=None, repr=True)

    @classmethod
    def disabled(cls, app_env: str = "development") -> GuideOperatorServiceAuthSettings:
        if app_env not in _APP_ENVIRONMENTS:
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            )
        return cls(enabled=False, app_env=app_env, inbound=None, outbound=None)

    @classmethod
    def enabled_with(
        cls,
        *,
        app_env: str,
        public_keys: Mapping[str, str],
        signing_kid: str,
        signing_private_key_pem: str,
    ) -> GuideOperatorServiceAuthSettings:
        if app_env not in _APP_ENVIRONMENTS:
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            )
        return cls(
            enabled=True,
            app_env=app_env,
            inbound=GuideOperatorInboundJWTSettings(public_keys, app_env=app_env),
            outbound=GuideOperatorOutboundJWTSettings(
                signing_kid, signing_private_key_pem, app_env=app_env
            ),
        )

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> GuideOperatorServiceAuthSettings:
        source: Mapping[str, str]
        if values is None:
            source = os.environ
        else:
            source = values
        app_env = source.get("APP_ENV", "development")
        raw_enabled = source.get("GUIDE_OS_SERVICE_AUTH_ENABLED", "false")
        enabled = _as_bool(raw_enabled)
        if app_env not in _APP_ENVIRONMENTS:
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            )
        if not enabled:
            return cls.disabled(app_env)
        public_keys_json = source.get("GUIDE_OS_GUIDE_OPERATOR_JWT_PUBLIC_KEYS", "")
        signing_kid = source.get("GUIDE_OS_SIGNING_KID", "")
        signing_pem = source.get("GUIDE_OS_SIGNING_PRIVATE_KEY_PEM", "")
        try:
            parsed = json.loads(public_keys_json) if public_keys_json else {}
        except json.JSONDecodeError:
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            ) from None
        if not isinstance(parsed, dict):
            raise GuideOperatorServiceAuthConfigurationError(
                "Service authentication configuration is invalid"
            )
        return cls.enabled_with(
            app_env=app_env,
            public_keys=parsed,
            signing_kid=signing_kid if isinstance(signing_kid, str) else "",
            signing_private_key_pem=signing_pem if isinstance(signing_pem, str) else "",
        )


@dataclass
class _ServiceAuthTestHooks:
    settings: GuideOperatorServiceAuthSettings | None = None
    clock: Callable[[], datetime] | None = None
    random_bytes: Callable[[int], bytes] | None = None


_hooks = _ServiceAuthTestHooks()


def configure_guide_operator_service_auth_for_tests(
    *,
    settings: GuideOperatorServiceAuthSettings,
    clock: Callable[[], datetime] | None = None,
    random_bytes: Callable[[int], bytes] | None = None,
) -> None:
    """Test-only dependency injection for settings/clock/randomness."""
    _hooks.settings = settings
    _hooks.clock = clock
    _hooks.random_bytes = random_bytes


def reset_guide_operator_service_auth_for_tests() -> None:
    _hooks.settings = None
    _hooks.clock = None
    _hooks.random_bytes = None


def load_guide_operator_service_auth_settings() -> GuideOperatorServiceAuthSettings:
    if _hooks.settings is not None:
        return _hooks.settings
    return GuideOperatorServiceAuthSettings.from_env()


def current_guide_operator_auth_clock() -> Callable[[], datetime]:
    return _hooks.clock or (lambda: datetime.now(timezone.utc))


def current_guide_operator_random_bytes() -> Callable[[int], bytes]:
    return _hooks.random_bytes or secrets.token_bytes
