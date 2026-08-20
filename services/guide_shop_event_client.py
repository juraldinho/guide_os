import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

import aiohttp
from pydantic import ValidationError

from services.guide_shop_client import (
    GuideShopAccessDeniedError,
    GuideShopAuthenticationError,
    GuideShopClientError,
    GuideShopTemporarilyUnavailableError,
)
from services.guide_shop_contracts import APIErrorDTO, EventListResponseDTO
from services.guide_shop_settings import GuideShopHTTPSettings
from utils.guide_os_identity import validate_guide_os_id


_MAX_RESPONSE_BYTES = 1_000_000
_CURSOR_PATTERN = re.compile(r"^[A-Za-z0-9._~=-]+$")
_BEARER_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9\-._~+/]+=*\Z")
_TRANSIENT_STATUSES = {429, 503}


@runtime_checkable
class GuideShopEventAccessTokenProvider(Protocol):
    async def get_access_token(self, guide_os_id: str) -> str: ...


@runtime_checkable
class GuideShopEventFeedClient(Protocol):
    async def fetch_events(
        self, *, cursor: str | None = None, limit: int = 20
    ) -> EventListResponseDTO: ...


class HTTPGuideShopEventFeedClient:
    def __init__(
        self,
        settings: GuideShopHTTPSettings,
        guide_os_id: str,
        token_provider: GuideShopEventAccessTokenProvider,
        *,
        session: Any | None = None,
        owns_session: bool | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not isinstance(settings, GuideShopHTTPSettings):
            raise TypeError("Validated GuideShopHTTPSettings required")
        self._guide_os_id = validate_guide_os_id(guide_os_id)
        if not isinstance(token_provider, GuideShopEventAccessTokenProvider):
            raise TypeError("GuideShopEventAccessTokenProvider required")
        if session is None and owns_session is False:
            raise ValueError("A lazily created session must be client-owned")
        self._settings = settings
        self._token_provider = token_provider
        self._session = session
        self._owns_session = session is None or owns_session is True
        self._sleep = sleep
        self._closed = False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_session and self._session is not None:
            await self._session.close()

    async def _get_session(self):
        if self._closed:
            raise GuideShopClientError("GuideShop event client is closed")
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(
                    total=self._settings.request_timeout_seconds
                )
            )
        return self._session

    @staticmethod
    def _validate_cursor(cursor: str | None) -> str | None:
        if cursor is None:
            return None
        if (
            not isinstance(cursor, str)
            or not 8 <= len(cursor) <= 256
            or _CURSOR_PATTERN.fullmatch(cursor) is None
        ):
            raise GuideShopClientError("Invalid event cursor")
        return cursor

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise GuideShopClientError("Invalid event limit")
        return limit

    async def _token(self) -> str:
        token = await self._token_provider.get_access_token(self._guide_os_id)
        if (
            not isinstance(token, str)
            or not token
            or _BEARER_TOKEN_PATTERN.fullmatch(token) is None
        ):
            raise GuideShopAuthenticationError("GuideShop authentication failed")
        return token

    @staticmethod
    async def _body(response) -> bytes:
        if isinstance(response.content_length, int) and response.content_length > _MAX_RESPONSE_BYTES:
            raise GuideShopClientError("Invalid GuideShop response")
        body = bytearray()
        while len(body) <= _MAX_RESPONSE_BYTES:
            chunk = await response.content.read(
                min(65_536, _MAX_RESPONSE_BYTES + 1 - len(body))
            )
            if not chunk:
                return bytes(body)
            body.extend(chunk)
            if len(body) > _MAX_RESPONSE_BYTES:
                raise GuideShopClientError("Invalid GuideShop response")
        raise GuideShopClientError("Invalid GuideShop response")

    def _retry_delay(self, response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value is not None and value.isdigit():
            return min(float(value), self._settings.max_retry_after_seconds)
        return min(0.25 * (2 ** (attempt - 1)), self._settings.max_retry_after_seconds)

    @staticmethod
    def _raise_error(status: int, body: bytes) -> None:
        try:
            APIErrorDTO.model_validate(json.loads(body.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError):
            raise GuideShopClientError("Invalid GuideShop error response") from None
        if status == 401:
            raise GuideShopAuthenticationError("GuideShop authentication failed")
        if status == 403:
            raise GuideShopAccessDeniedError("GuideShop access denied")
        if status in {429, 503}:
            raise GuideShopTemporarilyUnavailableError(
                "GuideShop is temporarily unavailable"
            )
        if status == 400:
            raise GuideShopClientError("GuideShop request failed")
        raise GuideShopClientError("GuideShop request failed")

    async def fetch_events(
        self, *, cursor: str | None = None, limit: int = 20
    ) -> EventListResponseDTO:
        cursor = self._validate_cursor(cursor)
        limit = self._validate_limit(limit)
        params = {"limit": str(limit)}
        if cursor is not None:
            params["cursor"] = cursor
        session = await self._get_session()
        url = f"{self._settings.base_url}/integration/v1/me/events"
        for attempt in range(self._settings.max_retries + 1):
            response = None
            try:
                response = await session.request(
                    "GET",
                    url,
                    params=params,
                    headers={
                        "Authorization": f"Bearer {await self._token()}",
                        "Accept": "application/json",
                    },
                    allow_redirects=False,
                )
                body = await self._body(response)
                if 200 <= response.status < 300:
                    try:
                        return EventListResponseDTO.model_validate(
                            json.loads(body.decode("utf-8"))
                        )
                    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError):
                        raise GuideShopClientError("Invalid GuideShop response") from None
                if response.status in _TRANSIENT_STATUSES and attempt < self._settings.max_retries:
                    await self._sleep(self._retry_delay(response, attempt + 1))
                    continue
                self._raise_error(response.status, body)
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                if attempt < self._settings.max_retries:
                    await self._sleep(
                        min(0.25 * (2**attempt), self._settings.max_retry_after_seconds)
                    )
                    continue
                raise GuideShopTemporarilyUnavailableError(
                    "GuideShop is temporarily unavailable"
                ) from exc
            finally:
                if response is not None:
                    response.release()
        raise GuideShopTemporarilyUnavailableError(
            "GuideShop is temporarily unavailable"
        )
