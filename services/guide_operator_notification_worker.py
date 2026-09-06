"""GO10A2B: bounded guide-notification drain inside the existing bot process.

Reuses GO10A2A deliver_one_notification() only. Never starts getUpdates,
webhooks, or a second bot instance. Delivery failures are isolated from
Telegram update polling.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from services.guide_operator_notification_delivery import (
    GuideOperatorNotificationTelegramClient,
    NotificationDeliveryResult,
    deliver_one_notification,
)
from services.guide_operator_notification_delivery_settings import (
    GuideOperatorNotificationDeliveryConfigurationError,
    GuideOperatorNotificationDeliverySettings,
)

logger = logging.getLogger("guide_os.guide_operator_notification_worker")

DEFAULT_POLL_INTERVAL_SECONDS = 5.0
MIN_POLL_INTERVAL_SECONDS = 1.0
MAX_POLL_INTERVAL_SECONDS = 300.0
DEFAULT_BATCH_SIZE = 10
MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 50
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 15.0
MIN_SHUTDOWN_TIMEOUT_SECONDS = 1.0
MAX_SHUTDOWN_TIMEOUT_SECONDS = 120.0

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})


class GuideOperatorNotificationWorkerConfigurationError(ValueError):
    """Raised when the notification worker is enabled with incomplete settings."""


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_VALUES:
            return True
        if lowered in _FALSE_VALUES:
            return False
    raise GuideOperatorNotificationWorkerConfigurationError(
        "Guide Operator notification worker configuration is invalid"
    )


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        raise GuideOperatorNotificationWorkerConfigurationError(
            "Guide Operator notification worker configuration is invalid"
        )
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            pass
    raise GuideOperatorNotificationWorkerConfigurationError(
        "Guide Operator notification worker configuration is invalid"
    )


def _as_int(value: object) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise GuideOperatorNotificationWorkerConfigurationError(
            "Guide Operator notification worker configuration is invalid"
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
    raise GuideOperatorNotificationWorkerConfigurationError(
        "Guide Operator notification worker configuration is invalid"
    )


def _validated_poll_interval(value: float) -> float:
    if (
        not isinstance(value, float | int)
        or isinstance(value, bool)
        or value < MIN_POLL_INTERVAL_SECONDS
        or value > MAX_POLL_INTERVAL_SECONDS
    ):
        raise GuideOperatorNotificationWorkerConfigurationError(
            "Guide Operator notification worker configuration is invalid"
        )
    return float(value)


def _validated_batch_size(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GuideOperatorNotificationWorkerConfigurationError(
            "Guide Operator notification worker configuration is invalid"
        )
    if value < MIN_BATCH_SIZE or value > MAX_BATCH_SIZE:
        raise GuideOperatorNotificationWorkerConfigurationError(
            "Guide Operator notification worker configuration is invalid"
        )
    return value


def _validated_shutdown_timeout(value: float) -> float:
    if (
        not isinstance(value, float | int)
        or isinstance(value, bool)
        or value < MIN_SHUTDOWN_TIMEOUT_SECONDS
        or value > MAX_SHUTDOWN_TIMEOUT_SECONDS
    ):
        raise GuideOperatorNotificationWorkerConfigurationError(
            "Guide Operator notification worker configuration is invalid"
        )
    return float(value)


@dataclass(frozen=True)
class GuideOperatorNotificationWorkerSettings:
    enabled: bool
    poll_interval_seconds: float
    batch_size: int
    shutdown_timeout_seconds: float

    @classmethod
    def disabled(cls) -> GuideOperatorNotificationWorkerSettings:
        return cls(
            enabled=False,
            poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS,
            batch_size=DEFAULT_BATCH_SIZE,
            shutdown_timeout_seconds=DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
        )

    @classmethod
    def enabled_with(
        cls,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        batch_size: int = DEFAULT_BATCH_SIZE,
        shutdown_timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
        delivery: GuideOperatorNotificationDeliverySettings,
    ) -> GuideOperatorNotificationWorkerSettings:
        if not delivery.enabled:
            raise GuideOperatorNotificationWorkerConfigurationError(
                "Guide Operator notification worker configuration is invalid"
            )
        return cls(
            enabled=True,
            poll_interval_seconds=_validated_poll_interval(poll_interval_seconds),
            batch_size=_validated_batch_size(batch_size),
            shutdown_timeout_seconds=_validated_shutdown_timeout(
                shutdown_timeout_seconds
            ),
        )

    @classmethod
    def from_env(
        cls,
        values: Mapping[str, str] | None = None,
        *,
        delivery: GuideOperatorNotificationDeliverySettings | None = None,
    ) -> GuideOperatorNotificationWorkerSettings:
        source: Mapping[str, str] = os.environ if values is None else values
        enabled = _as_bool(
            source.get(
                "GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_WORKER_ENABLED", "false"
            )
        )
        if not enabled:
            return cls.disabled()
        poll_interval_seconds = _as_float(
            source.get(
                "GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_WORKER_POLL_INTERVAL_SECONDS",
                str(DEFAULT_POLL_INTERVAL_SECONDS),
            )
        )
        batch_size = _as_int(
            source.get(
                "GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_WORKER_BATCH_SIZE",
                str(DEFAULT_BATCH_SIZE),
            )
        )
        shutdown_timeout_seconds = _as_float(
            source.get(
                "GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_WORKER_SHUTDOWN_TIMEOUT_SECONDS",
                str(DEFAULT_SHUTDOWN_TIMEOUT_SECONDS),
            )
        )
        try:
            delivery_settings = (
                delivery
                if delivery is not None
                else GuideOperatorNotificationDeliverySettings.from_env(values)
            )
        except GuideOperatorNotificationDeliveryConfigurationError as exc:
            raise GuideOperatorNotificationWorkerConfigurationError(
                "Guide Operator notification worker configuration is invalid"
            ) from exc
        return cls.enabled_with(
            poll_interval_seconds=poll_interval_seconds,
            batch_size=batch_size,
            shutdown_timeout_seconds=shutdown_timeout_seconds,
            delivery=delivery_settings,
        )


class GuideOperatorNotificationWorker:
    """Bounded batch drain that calls deliver_one_notification() only."""

    def __init__(
        self,
        *,
        settings: GuideOperatorNotificationWorkerSettings,
        delivery_settings: GuideOperatorNotificationDeliverySettings,
        http_client: GuideOperatorNotificationTelegramClient | None = None,
        clock: Callable[[], datetime] | None = None,
        jitter_unit: float | Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        deliver_one: Callable[..., NotificationDeliveryResult | None] | None = None,
    ) -> None:
        if settings.enabled and not delivery_settings.enabled:
            raise GuideOperatorNotificationWorkerConfigurationError(
                "Guide Operator notification worker configuration is invalid"
            )
        self.settings = settings
        self._delivery_settings = delivery_settings
        self._http_client = http_client
        self._clock = clock
        self._jitter_unit = jitter_unit
        self._sleep = sleep
        self._deliver_one = deliver_one or deliver_one_notification
        self._stop = asyncio.Event()
        self._cycle_lock = asyncio.Lock()

    def request_stop(self) -> None:
        logger.info("Guide Operator notification worker stopping")
        self._stop.set()

    async def run_once(self) -> list[NotificationDeliveryResult]:
        """Injectable one-cycle runner for tests and manual operation."""
        return await self.run_cycle()

    async def run_cycle(self) -> list[NotificationDeliveryResult]:
        if not self.settings.enabled:
            logger.warning("Guide Operator notification worker is disabled")
            return []
        async with self._cycle_lock:
            return await self._run_cycle_locked()

    async def run_forever(self) -> None:
        if not self.settings.enabled:
            logger.warning("Guide Operator notification worker is disabled")
            return
        while not self._stop.is_set():
            try:
                await self.run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Never escalate into the update poller lifecycle.
                logger.warning(
                    "Guide Operator notification worker cycle failed"
                )
            if self._stop.is_set():
                break
            await self._sleep_for(self.settings.poll_interval_seconds)

    async def _run_cycle_locked(self) -> list[NotificationDeliveryResult]:
        results: list[NotificationDeliveryResult] = []
        for _ in range(self.settings.batch_size):
            if self._stop.is_set():
                break
            started = time.perf_counter()
            try:
                result = await asyncio.to_thread(
                    self._deliver_one,
                    settings=self._delivery_settings,
                    clock=self._clock,
                    http_client=self._http_client,
                    jitter_unit=self._jitter_unit,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Guide Operator notification delivery call failed"
                )
                break
            if result is None:
                break
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            _log_result(result, elapsed_ms)
            results.append(result)
        return results

    async def _sleep_for(self, seconds: float) -> None:
        if self._sleep is not None:
            await self._sleep(seconds)
            return
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except TimeoutError:
            return


def _log_result(result: NotificationDeliveryResult, elapsed_ms: int) -> None:
    error_code = result.error_code if result.error_code is not None else "-"
    notification_id = (
        result.notification_id
        if result.notification_id is not None
        else result.source_event_id
    )
    logger.info(
        "notification delivery notification_id=%s event_type=%s attempt=%s "
        "outcome=%s error_code=%s elapsed_ms=%s",
        notification_id,
        result.notification_type,
        result.attempt_count,
        result.outcome,
        error_code,
        elapsed_ms,
    )


def build_guide_operator_notification_worker(
    values: Mapping[str, str] | None = None,
) -> GuideOperatorNotificationWorker | None:
    """Return a worker when enabled and complete; None when disabled.

    Incomplete enabled configuration fails closed by raising.
    """
    try:
        worker_settings = GuideOperatorNotificationWorkerSettings.from_env(values)
    except GuideOperatorNotificationWorkerConfigurationError:
        logger.warning(
            "Guide Operator notification worker configuration is invalid"
        )
        raise
    if not worker_settings.enabled:
        return None
    delivery_settings = GuideOperatorNotificationDeliverySettings.from_env(values)
    return GuideOperatorNotificationWorker(
        settings=worker_settings,
        delivery_settings=delivery_settings,
    )


async def start_guide_operator_notification_worker(
    values: Mapping[str, str] | None = None,
) -> tuple[asyncio.Task | None, GuideOperatorNotificationWorker | None]:
    worker = build_guide_operator_notification_worker(values)
    if worker is None:
        return None, None
    task = asyncio.create_task(
        worker.run_forever(),
        name="guide_operator_notification_worker",
    )
    return task, worker


async def stop_guide_operator_notification_worker(
    task: asyncio.Task | None,
    worker: GuideOperatorNotificationWorker | None,
    *,
    timeout_seconds: float | None = None,
) -> None:
    if worker is not None:
        worker.request_stop()
    if task is None:
        return
    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else (
            worker.settings.shutdown_timeout_seconds
            if worker is not None
            else DEFAULT_SHUTDOWN_TIMEOUT_SECONDS
        )
    )
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except TimeoutError:
        logger.warning(
            "Guide Operator notification worker shutdown timed out"
        )
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    except asyncio.CancelledError:
        pass
