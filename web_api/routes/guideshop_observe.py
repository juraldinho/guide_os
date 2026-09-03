"""Sanitized Mini App GuideShop observability (latency + outcome class)."""

from __future__ import annotations

import logging
import time

from services.guide_shop_client import (
    GuideShopAccessDeniedError,
    GuideShopAuthenticationError,
    GuideShopIntegrationDisabledError,
    GuideShopObjectNotFoundError,
)
from services.guide_shop_runtime import GuideShopIdentityUnavailableError

logger = logging.getLogger("web_api.guideshop")

# Allowlisted outcome labels only — never log IDs, tokens, or PII.
_OUTCOMES = frozenset(
    {
        "ok",
        "access_denied",
        "integration_disabled",
        "unavailable",
        "not_found",
    }
)


def outcome_from_guideshop_exc(exc: BaseException) -> str:
    if isinstance(exc, GuideShopIdentityUnavailableError):
        return "access_denied"
    if isinstance(
        exc, (GuideShopAccessDeniedError, GuideShopAuthenticationError)
    ):
        return "access_denied"
    if isinstance(exc, GuideShopObjectNotFoundError):
        return "not_found"
    if isinstance(exc, GuideShopIntegrationDisabledError):
        return "integration_disabled"
    return "unavailable"


class MiniAppGuideShopSpan:
    """Request-scoped latency/outcome logger for Mini App GuideShop routes."""

    __slots__ = ("_route", "_t0", "outcome")

    def __init__(self, route: str) -> None:
        # Callers must pass a static route label (e.g. "companies.list").
        self._route = route
        self._t0 = time.perf_counter()
        self.outcome = "ok"

    def set_outcome(self, outcome: str) -> None:
        self.outcome = outcome if outcome in _OUTCOMES else "unavailable"

    def finish(self) -> None:
        latency_ms = int((time.perf_counter() - self._t0) * 1000)
        outcome = self.outcome if self.outcome in _OUTCOMES else "unavailable"
        logger.info(
            "miniapp_guideshop route=%s outcome=%s latency_ms=%d",
            self._route,
            outcome,
            latency_ms,
        )
