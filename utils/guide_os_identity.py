"""Canonical Guide OS identity validation and generation.

guide_os_id is an immutable lowercase UUIDv4 string representing one real person.
"""

from __future__ import annotations

import re
import uuid

_CANONICAL_UUID4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class GuideOsIdentityError(ValueError):
    """Safe domain error for invalid Guide OS identity values."""


class GuideOsIdentityMigrationError(RuntimeError):
    """Safe domain error for identity migration/startup failures."""


def is_canonical_guide_os_id(value: object) -> bool:
    """Return True only for canonical lowercase UUIDv4 text."""
    if not isinstance(value, str):
        return False
    if value != value.strip():
        return False
    if _CANONICAL_UUID4_PATTERN.fullmatch(value) is None:
        return False
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    if parsed.version != 4:
        return False
    if parsed.int == 0:
        return False
    return str(parsed) == value


def validate_guide_os_id(value: object) -> str:
    """Validate and return a canonical guide_os_id or raise GuideOsIdentityError."""
    if not is_canonical_guide_os_id(value):
        raise GuideOsIdentityError("Invalid Guide OS identity")
    return value  # type: ignore[return-value]


def new_guide_os_id() -> str:
    """Generate a new canonical lowercase UUIDv4 identity."""
    return str(uuid.uuid4())
