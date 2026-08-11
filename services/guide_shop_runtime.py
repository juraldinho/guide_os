from collections.abc import Callable
from contextlib import asynccontextmanager
from inspect import iscoroutinefunction
from typing import AsyncContextManager, Protocol, runtime_checkable

from services.guide_shop_client import GuideShopClient
from services.guide_shop_ui import GuideShopUIService
from utils.guide_os_identity import GuideOsIdentityError, validate_guide_os_id


class GuideShopRuntimeError(Exception):
    pass


class GuideShopIdentityUnavailableError(GuideShopRuntimeError):
    pass


class GuideShopRuntimeConfigurationError(GuideShopRuntimeError):
    pass


class GuideShopClientLifecycleError(GuideShopRuntimeConfigurationError):
    pass


@runtime_checkable
class GuideShopUIServiceProvider(Protocol):
    def service_for(
        self, telegram_user_id: int
    ) -> AsyncContextManager[GuideShopUIService]: ...


class StaticGuideShopUIServiceProvider:
    def __init__(self, service: GuideShopUIService) -> None:
        if service is None:
            raise GuideShopRuntimeConfigurationError(
                "GuideShop runtime is not configured"
            )
        self._service = service

    @asynccontextmanager
    async def service_for(self, telegram_user_id: int):
        yield self._service


class RequestScopedGuideShopUIServiceProvider:
    def __init__(
        self,
        identity_lookup: Callable[[int], str | None],
        client_factory: Callable[[str], GuideShopClient],
    ) -> None:
        if not callable(identity_lookup) or not callable(client_factory):
            raise GuideShopRuntimeConfigurationError(
                "GuideShop runtime is not configured"
            )
        self._identity_lookup = identity_lookup
        self._client_factory = client_factory

    @staticmethod
    def _validate_user_id(telegram_user_id: int) -> None:
        if (
            isinstance(telegram_user_id, bool)
            or not isinstance(telegram_user_id, int)
            or telegram_user_id <= 0
        ):
            raise GuideShopIdentityUnavailableError(
                "GuideShop identity is unavailable"
            )

    @staticmethod
    def _validate_identity(guide_os_id: object) -> str:
        try:
            return validate_guide_os_id(guide_os_id)
        except GuideOsIdentityError as exc:
            raise GuideShopIdentityUnavailableError(
                "GuideShop identity is unavailable"
            ) from exc

    @staticmethod
    async def _reject_invalid_client(close: object) -> None:
        if callable(close) and iscoroutinefunction(close):
            try:
                await close()
            except BaseException as exc:
                raise GuideShopClientLifecycleError(
                    "GuideShop client cleanup failed"
                ) from exc
        raise GuideShopRuntimeConfigurationError(
            "GuideShop runtime is not configured"
        )

    @asynccontextmanager
    async def service_for(self, telegram_user_id: int):
        self._validate_user_id(telegram_user_id)
        try:
            guide_os_id = self._identity_lookup(telegram_user_id)
        except Exception as exc:
            raise GuideShopIdentityUnavailableError(
                "GuideShop identity is unavailable"
            ) from exc
        guide_os_id = self._validate_identity(guide_os_id)

        try:
            client = self._client_factory(guide_os_id)
        except Exception as exc:
            raise GuideShopClientLifecycleError(
                "GuideShop client creation failed"
            ) from exc
        try:
            close = getattr(client, "close", None)
            valid_client = isinstance(client, GuideShopClient)
        except Exception as exc:
            raise GuideShopRuntimeConfigurationError(
                "GuideShop runtime is not configured"
            ) from exc
        if (
            not valid_client
            or not callable(close)
            or not iscoroutinefunction(close)
        ):
            await self._reject_invalid_client(close)

        body_error: BaseException | None = None
        try:
            yield GuideShopUIService(client)
        except BaseException as exc:
            body_error = exc
            raise
        finally:
            try:
                await close()
            except BaseException as exc:
                if body_error is None:
                    raise GuideShopClientLifecycleError(
                        "GuideShop client cleanup failed"
                    ) from exc
