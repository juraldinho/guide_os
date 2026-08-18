import asyncio
import json
import re
import secrets
from collections.abc import Sequence
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any, Protocol, TypeVar, runtime_checkable
from urllib.parse import quote

import aiohttp
from pydantic import ValidationError

from services.guide_shop_contracts import (
    APIDetailResponseDTO,
    APIListResponseDTO,
    CompanyDTO,
    PageDTO,
    PointsAccrualDTO,
    PointsPayoutDTO,
    PointsStatus,
    PointsSummaryDTO,
    SaleDTO,
    VisitDTO,
)
from services.guide_shop_settings import GuideShopFeatureFlags, GuideShopHTTPSettings


class GuideShopClientError(Exception):
    pass


class GuideShopIntegrationDisabledError(GuideShopClientError):
    pass


class GuideShopObjectNotFoundError(GuideShopClientError):
    pass


class GuideShopAccessDeniedError(GuideShopClientError):
    pass


class GuideShopTemporarilyUnavailableError(GuideShopClientError):
    pass


class GuideShopAuthenticationError(GuideShopClientError):
    pass


@runtime_checkable
class GuideShopAccessTokenProvider(Protocol):
    async def get_access_token(self, guide_os_id: str) -> str: ...


@runtime_checkable
class GuideShopClient(Protocol):
    async def list_companies(self) -> APIListResponseDTO[CompanyDTO]: ...

    async def list_visits(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[VisitDTO]: ...

    async def get_visit(
        self, visit_id: str
    ) -> APIDetailResponseDTO[VisitDTO]: ...

    async def list_sales(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[SaleDTO]: ...

    async def get_sale(
        self, sale_id: str
    ) -> APIDetailResponseDTO[SaleDTO]: ...

    async def list_points(
        self,
        status: PointsStatus | None = None,
        cursor: str | None = None,
        visit_id: str | None = None,
    ) -> APIListResponseDTO[PointsAccrualDTO]: ...

    async def get_points_summary(self) -> PointsSummaryDTO: ...

    async def get_points_transaction(
        self, points_transaction_id: str
    ) -> APIDetailResponseDTO[PointsAccrualDTO]: ...

    async def list_history(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[PointsPayoutDTO]: ...


class DisabledGuideShopClient:
    @staticmethod
    def _disabled() -> None:
        raise GuideShopIntegrationDisabledError(
            "GuideShop integration is disabled"
        )

    async def list_companies(self) -> APIListResponseDTO[CompanyDTO]:
        self._disabled()

    async def list_visits(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[VisitDTO]:
        self._disabled()

    async def get_visit(
        self, visit_id: str
    ) -> APIDetailResponseDTO[VisitDTO]:
        self._disabled()

    async def list_sales(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[SaleDTO]:
        self._disabled()

    async def get_sale(
        self, sale_id: str
    ) -> APIDetailResponseDTO[SaleDTO]:
        self._disabled()

    async def list_points(
        self,
        status: PointsStatus | None = None,
        cursor: str | None = None,
        visit_id: str | None = None,
    ) -> APIListResponseDTO[PointsAccrualDTO]:
        self._disabled()

    async def get_points_summary(self) -> PointsSummaryDTO:
        self._disabled()

    async def get_points_transaction(
        self, points_transaction_id: str
    ) -> APIDetailResponseDTO[PointsAccrualDTO]:
        self._disabled()

    async def list_history(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[PointsPayoutDTO]:
        self._disabled()


_MAX_RESPONSE_BYTES = 1_000_000
_TRANSIENT_STATUSES = {429, 503}
_BEARER_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9\-._~+/]+=*\Z")
_CURSOR_PATTERN = re.compile(r"^[A-Za-z0-9._~=-]+$")


class HTTPGuideShopClient:
    def __init__(
        self,
        settings: GuideShopHTTPSettings,
        guide_os_id: str,
        token_provider: GuideShopAccessTokenProvider,
        *,
        session: Any | None = None,
        owns_session: bool | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not isinstance(settings, GuideShopHTTPSettings):
            raise TypeError("Validated GuideShopHTTPSettings required")
        if not isinstance(guide_os_id, str) or not guide_os_id.strip():
            raise GuideShopClientError("Invalid GuideShop client identity")
        if not isinstance(token_provider, GuideShopAccessTokenProvider):
            raise TypeError("GuideShopAccessTokenProvider required")
        if session is None and owns_session is False:
            raise ValueError("A lazily created session must be client-owned")

        self._settings = settings
        self._guide_os_id = guide_os_id
        self._token_provider = token_provider
        self._session = session
        self._owns_session = session is None or owns_session is True
        self._sleep = sleep
        self._closed = False

    async def __aenter__(self) -> "HTTPGuideShopClient":
        if self._closed:
            raise GuideShopClientError("GuideShop client is closed")
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_session and self._session is not None:
            await self._session.close()

    async def _get_session(self):
        if self._closed:
            raise GuideShopClientError("GuideShop client is closed")
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(
                    total=self._settings.request_timeout_seconds
                )
            )
        return self._session

    @staticmethod
    def _required_string(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise GuideShopClientError(f"Invalid {name}")
        return value

    @staticmethod
    def _optional_cursor(cursor: str | None) -> str | None:
        if cursor is None:
            return None
        value = HTTPGuideShopClient._required_string(cursor, "cursor")
        if not 8 <= len(value) <= 256 or _CURSOR_PATTERN.fullmatch(value) is None:
            raise GuideShopClientError("Invalid pagination cursor")
        return value

    async def _access_token(self) -> str:
        token = await self._token_provider.get_access_token(self._guide_os_id)
        if (
            not isinstance(token, str)
            or not token
            or _BEARER_TOKEN_PATTERN.fullmatch(token) is None
        ):
            raise GuideShopAuthenticationError("GuideShop authentication failed")
        return token

    def _retry_delay(self, response, retry_number: int) -> float:
        raw_value = response.headers.get("Retry-After")
        if raw_value is not None and raw_value.isdigit():
            return min(float(raw_value), self._settings.max_retry_after_seconds)
        return min(
            0.25 * (2 ** (retry_number - 1)),
            self._settings.max_retry_after_seconds,
        )

    @staticmethod
    def _raise_status(status: int) -> None:
        if status == 401:
            raise GuideShopAuthenticationError("GuideShop authentication failed")
        if status in {403, 409}:
            raise GuideShopAccessDeniedError("GuideShop access denied")
        if status == 404:
            raise GuideShopObjectNotFoundError("GuideShop object was not found")
        if status == 429 or status in {500, 502, 503, 504}:
            raise GuideShopTemporarilyUnavailableError(
                "GuideShop is temporarily unavailable"
            )
        raise GuideShopClientError("GuideShop request failed")

    @staticmethod
    async def _read_bounded_response(response) -> bytes:
        content_length = response.content_length
        if (
            isinstance(content_length, int)
            and not isinstance(content_length, bool)
            and content_length > _MAX_RESPONSE_BYTES
        ):
            raise GuideShopClientError("Invalid GuideShop response")

        body = bytearray()
        while len(body) <= _MAX_RESPONSE_BYTES:
            remaining_with_detection = _MAX_RESPONSE_BYTES + 1 - len(body)
            chunk = await response.content.read(
                min(65_536, remaining_with_detection)
            )
            if not chunk:
                return bytes(body)
            body.extend(chunk)
            if len(body) > _MAX_RESPONSE_BYTES:
                raise GuideShopClientError("Invalid GuideShop response")
        raise GuideShopClientError("Invalid GuideShop response")

    async def _request(
        self,
        path: str,
        params: dict[str, str] | None,
        response_type,
    ):
        url = f"{self._settings.base_url}{path}"
        session = await self._get_session()

        for attempt in range(self._settings.max_retries + 1):
            token = await self._access_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
            response = None
            try:
                response = await session.request(
                    "GET",
                    url,
                    params=params,
                    headers=headers,
                    allow_redirects=False,
                )
                if 200 <= response.status < 300:
                    body = await self._read_bounded_response(response)
                    try:
                        payload = json.loads(body.decode("utf-8"))
                        return response_type.model_validate(payload)
                    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
                        raise GuideShopClientError(
                            "Invalid GuideShop response"
                        ) from exc

                if (
                    response.status in _TRANSIENT_STATUSES
                    and attempt < self._settings.max_retries
                ):
                    await self._sleep(self._retry_delay(response, attempt + 1))
                    continue
                self._raise_status(response.status)
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                if attempt < self._settings.max_retries:
                    await self._sleep(
                        min(
                            0.25 * (2**attempt),
                            self._settings.max_retry_after_seconds,
                        )
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

    async def list_companies(self) -> APIListResponseDTO[CompanyDTO]:
        return await self._request(
            "/integration/v1/me/companies",
            None,
            APIListResponseDTO[CompanyDTO],
        )

    async def list_visits(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[VisitDTO]:
        cursor = self._optional_cursor(cursor)
        params = {"cursor": cursor} if cursor is not None else None
        return await self._request(
            "/integration/v1/me/visits", params, APIListResponseDTO[VisitDTO]
        )

    async def get_visit(
        self, visit_id: str
    ) -> APIDetailResponseDTO[VisitDTO]:
        visit_id = self._required_string(visit_id, "visit ID")
        return await self._request(
            f"/integration/v1/me/visits/{quote(visit_id, safe='')}",
            None,
            APIDetailResponseDTO[VisitDTO],
        )

    async def list_sales(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[SaleDTO]:
        cursor = self._optional_cursor(cursor)
        params = {"cursor": cursor} if cursor is not None else None
        return await self._request(
            "/integration/v1/me/sales", params, APIListResponseDTO[SaleDTO]
        )

    async def get_sale(
        self, sale_id: str
    ) -> APIDetailResponseDTO[SaleDTO]:
        sale_id = self._required_string(sale_id, "sale ID")
        return await self._request(
            f"/integration/v1/me/sales/{quote(sale_id, safe='')}",
            None,
            APIDetailResponseDTO[SaleDTO],
        )

    async def list_points(
        self,
        status: PointsStatus | None = None,
        cursor: str | None = None,
        visit_id: str | None = None,
    ) -> APIListResponseDTO[PointsAccrualDTO]:
        if status is not None and not isinstance(status, PointsStatus):
            raise GuideShopClientError("Invalid points status")
        cursor = self._optional_cursor(cursor)
        params: dict[str, str] = {}
        if cursor is not None:
            params["cursor"] = cursor
        if visit_id is not None:
            params["visit_id"] = self._required_string(visit_id, "visit ID")
        return await self._request(
            "/integration/v1/me/points",
            params or None,
            APIListResponseDTO[PointsAccrualDTO],
        )

    async def get_points_summary(self) -> PointsSummaryDTO:
        return await self._request(
            "/integration/v1/me/points/summary",
            None,
            PointsSummaryDTO,
        )

    async def get_points_transaction(
        self, points_transaction_id: str
    ) -> APIDetailResponseDTO[PointsAccrualDTO]:
        points_transaction_id = self._required_string(
            points_transaction_id, "points transaction ID"
        )
        return await self._request(
            "/integration/v1/me/points/"
            f"{quote(points_transaction_id, safe='')}",
            None,
            APIDetailResponseDTO[PointsAccrualDTO],
        )

    async def list_history(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[PointsPayoutDTO]:
        cursor = self._optional_cursor(cursor)
        params = {"cursor": cursor} if cursor is not None else None
        return await self._request(
            "/integration/v1/me/history",
            params,
            APIListResponseDTO[PointsPayoutDTO],
        )


GuideShopHTTPClient = HTTPGuideShopClient


DTO = TypeVar(
    "DTO", CompanyDTO, VisitDTO, SaleDTO, PointsAccrualDTO, PointsPayoutDTO
)


class InMemoryGuideShopClient:
    def __init__(
        self,
        *,
        companies: Sequence[CompanyDTO] = (),
        visits: Sequence[VisitDTO] = (),
        sales: Sequence[SaleDTO] = (),
        points: Sequence[PointsAccrualDTO] = (),
        points_history: Sequence[PointsPayoutDTO] = (),
        page_size: int = 50,
    ) -> None:
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size <= 0:
            raise GuideShopClientError("Invalid page size")

        self._companies = self._validated_copy(companies, CompanyDTO)
        self._visits = self._validated_copy(visits, VisitDTO)
        self._sales = self._validated_copy(sales, SaleDTO)
        self._points = self._validated_copy(points, PointsAccrualDTO)
        self._points_history = self._validated_copy(
            points_history, PointsPayoutDTO
        )
        self._page_size = page_size
        self._request_number = 0
        self._cursors: dict[str, tuple[str, int]] = {}

    @staticmethod
    def _validated_copy(values: Sequence[DTO], dto_type: type[DTO]) -> tuple[DTO, ...]:
        if isinstance(values, (str, bytes)):
            raise TypeError("Validated DTO sequence required")
        copied = []
        for value in values:
            if not isinstance(value, dto_type):
                raise TypeError("Validated DTO sequence required")
            copied.append(value.model_copy(deep=True))
        return tuple(copied)

    def _request_id(self) -> str:
        self._request_number += 1
        return f"fake-request-{self._request_number}"

    def _new_cursor(self, scope: str, position: int) -> str:
        cursor = secrets.token_urlsafe(24)
        while cursor in self._cursors:
            cursor = secrets.token_urlsafe(24)
        self._cursors[cursor] = (scope, position)
        return cursor

    def _cursor_position(self, scope: str, cursor: str | None) -> int:
        if cursor is None:
            return 0
        if not isinstance(cursor, str) or not cursor:
            raise GuideShopClientError("Invalid pagination cursor")
        stored = self._cursors.get(cursor)
        if stored is None or stored[0] != scope:
            raise GuideShopClientError("Invalid pagination cursor")
        return stored[1]

    def _list_response(
        self,
        values: Sequence[DTO],
        dto_type: type[DTO],
        scope: str,
        cursor: str | None,
        *,
        paginate: bool = True,
    ) -> APIListResponseDTO[DTO]:
        position = self._cursor_position(scope, cursor)
        end = min(position + self._page_size, len(values)) if paginate else len(values)
        next_cursor = (
            self._new_cursor(scope, end) if paginate and end < len(values) else None
        )
        data = [value.model_copy(deep=True) for value in values[position:end]]
        envelope_type = APIListResponseDTO[dto_type]
        return envelope_type(
            schema_version="1.0.0",
            request_id=self._request_id(),
            data=data,
            page=PageDTO(
                next_cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
        )

    def _detail_response(
        self, values: Sequence[DTO], dto_type: type[DTO], id_field: str, object_id: str
    ) -> APIDetailResponseDTO[DTO]:
        for value in values:
            if getattr(value, id_field) == object_id:
                envelope_type = APIDetailResponseDTO[dto_type]
                return envelope_type(
                    schema_version="1.0.0",
                    request_id=self._request_id(),
                    data=value.model_copy(deep=True),
                )
        raise GuideShopObjectNotFoundError("GuideShop object was not found")

    async def list_companies(self) -> APIListResponseDTO[CompanyDTO]:
        return self._list_response(
            self._companies, CompanyDTO, "companies", None, paginate=False
        )

    async def list_visits(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[VisitDTO]:
        return self._list_response(self._visits, VisitDTO, "visits", cursor)

    async def get_visit(
        self, visit_id: str
    ) -> APIDetailResponseDTO[VisitDTO]:
        return self._detail_response(
            self._visits, VisitDTO, "visit_id", visit_id
        )

    async def list_sales(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[SaleDTO]:
        return self._list_response(self._sales, SaleDTO, "sales", cursor)

    async def get_sale(
        self, sale_id: str
    ) -> APIDetailResponseDTO[SaleDTO]:
        return self._detail_response(self._sales, SaleDTO, "sale_id", sale_id)

    async def list_points(
        self,
        status: PointsStatus | None = None,
        cursor: str | None = None,
        visit_id: str | None = None,
    ) -> APIListResponseDTO[PointsAccrualDTO]:
        if status is not None and not isinstance(status, PointsStatus):
            raise GuideShopClientError("Invalid points status")
        values = (
            self._points
            if status is None
            else tuple(item for item in self._points if item.status == status)
        )
        if visit_id is not None:
            if not isinstance(visit_id, str) or not visit_id.strip():
                raise GuideShopClientError("Invalid visit ID")
            values = tuple(item for item in values if item.visit_id == visit_id)
        scope = f"points:{status.value if status is not None else 'all'}"
        return self._list_response(values, PointsAccrualDTO, scope, cursor)

    async def get_points_transaction(
        self, points_transaction_id: str
    ) -> APIDetailResponseDTO[PointsAccrualDTO]:
        return self._detail_response(
            self._points,
            PointsAccrualDTO,
            "points_accrual_id",
            points_transaction_id,
        )

    @staticmethod
    def _amount_pts(value: Decimal) -> str:
        quantized = value.quantize(Decimal("0.01"))
        text = format(quantized, "f")
        if "." not in text:
            text = f"{text}.00"
        return text

    async def get_points_summary(self) -> PointsSummaryDTO:
        names = {
            company.company_id: company.display_name
            for company in self._companies
        }
        buckets: dict[str, dict[str, Decimal | str]] = {}
        for item in self._points:
            bucket = buckets.get(item.company_id)
            if bucket is None:
                buckets[item.company_id] = {
                    "display_name": names.get(item.company_id, item.company_id),
                    "pending": Decimal("0.00"),
                    "credited": Decimal("0.00"),
                }
                bucket = buckets[item.company_id]
            amount = Decimal(item.amount)
            if item.status == PointsStatus.PENDING:
                bucket["pending"] = bucket["pending"] + amount
            elif item.status == PointsStatus.CREDITED:
                bucket["credited"] = bucket["credited"] + amount
        companies = [
            {
                "company_id": company_id,
                "display_name": bucket["display_name"],
                "pending_total": self._amount_pts(bucket["pending"]),
                "credited_total": self._amount_pts(bucket["credited"]),
            }
            for company_id, bucket in sorted(buckets.items(), key=lambda item: item[0])
        ]
        pending_total = self._amount_pts(
            sum(
                (Decimal(item["pending_total"]) for item in companies),
                Decimal("0.00"),
            )
        )
        credited_total = self._amount_pts(
            sum(
                (Decimal(item["credited_total"]) for item in companies),
                Decimal("0.00"),
            )
        )
        return PointsSummaryDTO.model_validate(
            {
                "schema_version": "1.0.0",
                "request_id": self._request_id(),
                "unit": "PTS",
                "pending_total": pending_total,
                "credited_total": credited_total,
                "companies": companies,
            }
        )

    async def list_history(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[PointsPayoutDTO]:
        return self._list_response(
            self._points_history,
            PointsPayoutDTO,
            "history",
            cursor,
        )


def build_guide_shop_client(flags: GuideShopFeatureFlags) -> GuideShopClient:
    if not flags.reads_enabled:
        return DisabledGuideShopClient()
    raise GuideShopClientError("GuideShop read client is not configured")
