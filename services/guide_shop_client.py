import secrets
from collections.abc import Sequence
from typing import Protocol, TypeVar, runtime_checkable

from services.guide_shop_contracts import (
    APIDetailResponseDTO,
    APIListResponseDTO,
    CompanyDTO,
    PageDTO,
    PointsStatus,
    PointsTransactionDTO,
    SaleDTO,
    VisitDTO,
)
from services.guide_shop_settings import GuideShopFeatureFlags


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
    ) -> APIListResponseDTO[PointsTransactionDTO]: ...

    async def get_points_transaction(
        self, points_transaction_id: str
    ) -> APIDetailResponseDTO[PointsTransactionDTO]: ...

    async def list_history(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[PointsTransactionDTO]: ...


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
    ) -> APIListResponseDTO[PointsTransactionDTO]:
        self._disabled()

    async def get_points_transaction(
        self, points_transaction_id: str
    ) -> APIDetailResponseDTO[PointsTransactionDTO]:
        self._disabled()

    async def list_history(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[PointsTransactionDTO]:
        self._disabled()


DTO = TypeVar("DTO", CompanyDTO, VisitDTO, SaleDTO, PointsTransactionDTO)


class InMemoryGuideShopClient:
    def __init__(
        self,
        *,
        companies: Sequence[CompanyDTO] = (),
        visits: Sequence[VisitDTO] = (),
        sales: Sequence[SaleDTO] = (),
        points: Sequence[PointsTransactionDTO] = (),
        points_history: Sequence[PointsTransactionDTO] = (),
        page_size: int = 50,
    ) -> None:
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size <= 0:
            raise GuideShopClientError("Invalid page size")

        self._companies = self._validated_copy(companies, CompanyDTO)
        self._visits = self._validated_copy(visits, VisitDTO)
        self._sales = self._validated_copy(sales, SaleDTO)
        self._points = self._validated_copy(points, PointsTransactionDTO)
        self._points_history = self._validated_copy(
            points_history, PointsTransactionDTO
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
            schema_version="1.0",
            request_id=self._request_id(),
            data=data,
            page=PageDTO(next_cursor=next_cursor),
        )

    def _detail_response(
        self, values: Sequence[DTO], dto_type: type[DTO], id_field: str, object_id: str
    ) -> APIDetailResponseDTO[DTO]:
        for value in values:
            if getattr(value, id_field) == object_id:
                envelope_type = APIDetailResponseDTO[dto_type]
                return envelope_type(
                    schema_version="1.0",
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
    ) -> APIListResponseDTO[PointsTransactionDTO]:
        if status is not None and not isinstance(status, PointsStatus):
            raise GuideShopClientError("Invalid points status")
        values = (
            self._points
            if status is None
            else tuple(item for item in self._points if item.status == status)
        )
        scope = f"points:{status.value if status is not None else 'all'}"
        return self._list_response(values, PointsTransactionDTO, scope, cursor)

    async def get_points_transaction(
        self, points_transaction_id: str
    ) -> APIDetailResponseDTO[PointsTransactionDTO]:
        return self._detail_response(
            self._points,
            PointsTransactionDTO,
            "points_transaction_id",
            points_transaction_id,
        )

    async def list_history(
        self, cursor: str | None = None
    ) -> APIListResponseDTO[PointsTransactionDTO]:
        return self._list_response(
            self._points_history,
            PointsTransactionDTO,
            "history",
            cursor,
        )


def build_guide_shop_client(flags: GuideShopFeatureFlags) -> GuideShopClient:
    if not flags.reads_enabled:
        return DisabledGuideShopClient()
    raise GuideShopClientError("GuideShop read client is not configured")
