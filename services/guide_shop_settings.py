from dataclasses import dataclass
import os
from typing import Mapping


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
