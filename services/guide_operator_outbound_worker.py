"""GO8F2B: bounded Guide OS → Guide Operator outbound delivery worker.

Separate process only. Never started from bot, Mini App, or GO8D integration API.
Uses GO8F2A deliver_one() exclusively; does not rewrite payloads or invent domain events.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from services.guide_operator_outbound_delivery import (
    GuideOperatorOutboundHttpClient,
    OutboundDeliveryResult,
    deliver_one,
)
from services.guide_operator_outbound_settings import (
    GuideOperatorOutboundConfigurationError,
    GuideOperatorOutboundSettings,
)
from services.guide_operator_service_auth_settings import (
    GuideOperatorServiceAuthConfigurationError,
)

logger = logging.getLogger("guide_os.guide_operator_outbound_worker")

DEFAULT_POLL_INTERVAL_SECONDS = 5.0
MIN_POLL_INTERVAL_SECONDS = 1.0
MAX_POLL_INTERVAL_SECONDS = 300.0
DEFAULT_BATCH_SIZE = 10
MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 50

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})


class GuideOperatorOutboundWorkerConfigurationError(ValueError):
    """Raised when the outbound worker is enabled with incomplete or invalid settings."""


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_VALUES:
            return True
        if lowered in _FALSE_VALUES:
            return False
    raise GuideOperatorOutboundWorkerConfigurationError(
        "Guide Operator outbound worker configuration is invalid"
    )


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        raise GuideOperatorOutboundWorkerConfigurationError(
            "Guide Operator outbound worker configuration is invalid"
        )
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            pass
    raise GuideOperatorOutboundWorkerConfigurationError(
        "Guide Operator outbound worker configuration is invalid"
    )


def _as_int(value: object) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise GuideOperatorOutboundWorkerConfigurationError(
            "Guide Operator outbound worker configuration is invalid"
        )
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = int(value.strip())
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed
    raise GuideOperatorOutboundWorkerConfigurationError(
        "Guide Operator outbound worker configuration is invalid"
    )


def _validated_poll_interval(value: float) -> float:
    if (
        not isinstance(value, float | int)
        or isinstance(value, bool)
        or value < MIN_POLL_INTERVAL_SECONDS
        or value > MAX_POLL_INTERVAL_SECONDS
    ):
        raise GuideOperatorOutboundWorkerConfigurationError(
            "Guide Operator outbound worker configuration is invalid"
        )
    return float(value)


def _validated_batch_size(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GuideOperatorOutboundWorkerConfigurationError(
            "Guide Operator outbound worker configuration is invalid"
        )
    if value < MIN_BATCH_SIZE or value > MAX_BATCH_SIZE:
        raise GuideOperatorOutboundWorkerConfigurationError(
            "Guide Operator outbound worker configuration is invalid"
        )
    return value


@dataclass(frozen=True)
class GuideOperatorOutboundWorkerSettings:
    enabled: bool
    once: bool
    poll_interval_seconds: float
    batch_size: int

    @classmethod
    def disabled(cls) -> GuideOperatorOutboundWorkerSettings:
        return cls(
            enabled=False,
            once=False,
            poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS,
            batch_size=DEFAULT_BATCH_SIZE,
        )

    @classmethod
    def enabled_with(
        cls,
        *,
        once: bool = False,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        batch_size: int = DEFAULT_BATCH_SIZE,
        outbound: GuideOperatorOutboundSettings,
    ) -> GuideOperatorOutboundWorkerSettings:
        if not outbound.enabled:
            raise GuideOperatorOutboundWorkerConfigurationError(
                "Guide Operator outbound worker configuration is invalid"
            )
        return cls(
            enabled=True,
            once=once,
            poll_interval_seconds=_validated_poll_interval(poll_interval_seconds),
            batch_size=_validated_batch_size(batch_size),
        )

    @classmethod
    def from_env(
        cls,
        values: Mapping[str, str] | None = None,
        *,
        outbound: GuideOperatorOutboundSettings | None = None,
    ) -> GuideOperatorOutboundWorkerSettings:
        source: Mapping[str, str] = os.environ if values is None else values
        enabled = _as_bool(
            source.get("GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ENABLED", "false")
        )
        if not enabled:
            return cls.disabled()
        once = _as_bool(
            source.get("GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ONCE", "false")
        )
        poll_interval_seconds = _as_float(
            source.get(
                "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_POLL_INTERVAL_SECONDS",
                str(DEFAULT_POLL_INTERVAL_SECONDS),
            )
        )
        batch_size = _as_int(
            source.get(
                "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_BATCH_SIZE",
                str(DEFAULT_BATCH_SIZE),
            )
        )
        try:
            outbound_settings = (
                outbound
                if outbound is not None
                else GuideOperatorOutboundSettings.from_env(values)
            )
        except (
            GuideOperatorOutboundConfigurationError,
            GuideOperatorServiceAuthConfigurationError,
        ) as exc:
            raise GuideOperatorOutboundWorkerConfigurationError(
                "Guide Operator outbound worker configuration is invalid"
            ) from exc
        return cls.enabled_with(
            once=once,
            poll_interval_seconds=poll_interval_seconds,
            batch_size=batch_size,
            outbound=outbound_settings,
        )


_hooks_settings: GuideOperatorOutboundWorkerSettings | None = None


def configure_guide_operator_outbound_worker_for_tests(
    *, settings: GuideOperatorOutboundWorkerSettings
) -> None:
    global _hooks_settings
    _hooks_settings = settings


def reset_guide_operator_outbound_worker_for_tests() -> None:
    global _hooks_settings
    _hooks_settings = None


def load_guide_operator_outbound_worker_settings() -> GuideOperatorOutboundWorkerSettings:
    if _hooks_settings is not None:
        return _hooks_settings
    return GuideOperatorOutboundWorkerSettings.from_env()


class GuideOperatorOutboundDeliveryWorker:
    """Bounded batch poller that claims/delivers via deliver_one()."""

    def __init__(
        self,
        *,
        settings: GuideOperatorOutboundWorkerSettings,
        outbound_settings: GuideOperatorOutboundSettings,
        http_client: GuideOperatorOutboundHttpClient | None = None,
        clock: Callable[[], datetime] | None = None,
        jitter_unit: float | Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        random_bytes: Callable[[int], bytes] | None = None,
    ) -> None:
        if settings.enabled and not outbound_settings.enabled:
            raise GuideOperatorOutboundWorkerConfigurationError(
                "Guide Operator outbound worker configuration is invalid"
            )
        self.settings = settings
        self._outbound_settings = outbound_settings
        self._http_client = http_client
        self._clock = clock
        self._jitter_unit = jitter_unit
        self._sleep = sleep
        self._random_bytes = random_bytes
        self._stop = threading.Event()
        self._cycle_lock = threading.Lock()

    def request_stop(self) -> None:
        logger.info("Guide Operator outbound worker stopping")
        self._stop.set()

    def run_once(self) -> list[OutboundDeliveryResult]:
        return self.run_cycle()

    def run_cycle(self) -> list[OutboundDeliveryResult]:
        if not self.settings.enabled:
            logger.warning("Guide Operator outbound worker is disabled")
            return []
        with self._cycle_lock:
            return self._run_cycle_locked()

    def run_forever(self) -> None:
        if not self.settings.enabled:
            logger.warning("Guide Operator outbound worker is disabled")
            return
        while not self._stop.is_set():
            self.run_cycle()
            if self._stop.is_set():
                break
            self._sleep_for(self.settings.poll_interval_seconds)

    def _run_cycle_locked(self) -> list[OutboundDeliveryResult]:
        results: list[OutboundDeliveryResult] = []
        for _ in range(self.settings.batch_size):
            if self._stop.is_set():
                break
            started = time.perf_counter()
            result = deliver_one(
                settings=self._outbound_settings,
                clock=self._clock,
                http_client=self._http_client,
                random_bytes=self._random_bytes,
                jitter_unit=self._jitter_unit,
            )
            if result is None:
                break
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            _log_result(result, elapsed_ms)
            results.append(result)
        return results

    def _sleep_for(self, seconds: float) -> None:
        if self._sleep is not None:
            self._sleep(seconds)
            return
        self._stop.wait(timeout=seconds)


def _log_result(result: OutboundDeliveryResult, elapsed_ms: int) -> None:
    error_code = result.error_code if result.error_code is not None else "-"
    logger.info(
        "outbound delivery event_id=%s event_type=%s attempt=%s "
        "outcome=%s error_code=%s elapsed_ms=%s",
        result.event_id,
        result.event_type,
        result.attempt_count,
        result.outcome,
        error_code,
        elapsed_ms,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Guide OS Guide Operator outbound delivery worker"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one bounded batch and exit",
    )
    return parser.parse_args(argv)


def install_signal_handlers(worker: GuideOperatorOutboundDeliveryWorker) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda _signum, _frame: worker.request_stop())
        except (ValueError, OSError):
            continue


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        worker_settings = load_guide_operator_outbound_worker_settings()
        if not worker_settings.enabled:
            logger.warning("Guide Operator outbound worker is disabled")
            return 0
        outbound_settings = GuideOperatorOutboundSettings.from_env()
        if not outbound_settings.enabled:
            raise GuideOperatorOutboundWorkerConfigurationError(
                "Guide Operator outbound worker configuration is invalid"
            )
    except (
        GuideOperatorOutboundWorkerConfigurationError,
        GuideOperatorOutboundConfigurationError,
        GuideOperatorServiceAuthConfigurationError,
    ):
        logger.warning("Guide Operator outbound worker configuration is invalid")
        return 1

    from database.db import init_db

    init_db()
    worker = GuideOperatorOutboundDeliveryWorker(
        settings=worker_settings,
        outbound_settings=outbound_settings,
    )
    install_signal_handlers(worker)
    if args.once or worker_settings.once:
        worker.run_once()
        return 0
    worker.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
