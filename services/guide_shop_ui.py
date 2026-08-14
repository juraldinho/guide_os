from dataclasses import dataclass, field
from html import escape
from typing import Literal

from services.guide_shop_client import (
    GuideShopAccessDeniedError,
    GuideShopClient,
    GuideShopClientError,
    GuideShopIntegrationDisabledError,
    GuideShopObjectNotFoundError,
    GuideShopTemporarilyUnavailableError,
)
from services.guide_shop_contracts import (
    CompanyDTO,
    PointsAccrualDTO,
    PointsPayoutDTO,
    PointsStatus,
    SaleDTO,
    VisitDTO,
)
from services.guide_shop_navigation import GuideShopRoute


@dataclass(frozen=True)
class GuideShopAction:
    label: str
    route: GuideShopRoute

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("Action label must not be empty")
        if not isinstance(self.route, GuideShopRoute):
            raise TypeError("Action route must be a GuideShopRoute")


@dataclass(frozen=True)
class GuideShopScreen:
    text: str
    actions: tuple[GuideShopAction, ...]
    parse_mode: Literal["HTML"] = field(default="HTML", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Screen text must not be empty")
        if not isinstance(self.actions, tuple) or not all(
            isinstance(action, GuideShopAction) for action in self.actions
        ):
            raise TypeError("Screen actions must be GuideShopAction tuple")


def _safe(value: object) -> str:
    raw_value = value.value if hasattr(value, "value") else value
    return escape(str(raw_value))


def _timestamp(value: object) -> str:
    return _safe(value.isoformat())


def _back_home() -> GuideShopAction:
    return GuideShopAction("⬅️ Назад в GuideShop", GuideShopRoute(kind="home"))


def _screen(text: str, actions: list[GuideShopAction]) -> GuideShopScreen:
    return GuideShopScreen(text=text, actions=tuple(actions))


def guide_shop_error_screen(error: GuideShopClientError) -> GuideShopScreen:
    if isinstance(error, GuideShopIntegrationDisabledError):
        text = "Раздел GuideShop временно отключён."
    elif isinstance(error, GuideShopTemporarilyUnavailableError):
        text = "GuideShop временно недоступен. Попробуйте позже."
    elif isinstance(error, GuideShopAccessDeniedError):
        text = "Нет доступа к данным GuideShop."
    elif isinstance(error, GuideShopObjectNotFoundError):
        text = "Объект GuideShop не найден или недоступен."
    else:
        text = "Не удалось загрузить данные GuideShop."
    return GuideShopScreen(text=text, actions=(_back_home(),))


def _company_text(company: CompanyDTO) -> str:
    return (
        f"🏢 <b>{_safe(company.display_name)}</b>\n"
        f"Статус: {_safe(company.status)}"
    )


def _visit_text(visit: VisitDTO) -> str:
    return (
        f"🏢 Компания: {_safe(visit.company_id)}\n"
        f"Дата визита: {_timestamp(visit.visit_at)}\n"
        f"Туристов: {_safe(visit.tourist_count)}\n"
        f"Статус: {_safe(visit.status)}"
    )


def _sale_text(sale: SaleDTO) -> str:
    return (
        f"💵 Сумма: {_safe(sale.amount)} {_safe(sale.currency)}\n"
        f"Категория: {_safe(sale.category_name)}\n"
        f"Оплата: {_safe(sale.payment_method)}\n"
        f"Статус: {_safe(sale.status)}\n"
        f"Создано: {_timestamp(sale.created_at)}"
    )


def _points_text(transaction: PointsAccrualDTO) -> str:
    lines = [
        f"Баллы: {_safe(transaction.amount)} {_safe(transaction.unit)}",
        f"Статус: {_safe(transaction.status)}",
        f"Рассчитано: {_timestamp(transaction.calculated_at)}",
    ]
    return "\n".join(lines)


def _history_text(transaction: PointsPayoutDTO) -> str:
    return (
        f"Баллы: {_safe(transaction.amount)} {_safe(transaction.unit)}\n"
        f"Выплачено: {_timestamp(transaction.paid_at)}"
    )


class GuideShopUIService:
    def __init__(self, client: GuideShopClient) -> None:
        self._client = client

    async def home(self) -> GuideShopScreen:
        return GuideShopScreen(
            text="<b>GuideShop</b>",
            actions=(
                GuideShopAction("Компании", GuideShopRoute(kind="companies")),
                GuideShopAction("Визиты", GuideShopRoute(kind="visits")),
                GuideShopAction("Продажи", GuideShopRoute(kind="sales")),
                GuideShopAction(
                    "Ожидающие баллы",
                    GuideShopRoute(
                        kind="points", points_status=PointsStatus.PENDING
                    ),
                ),
                GuideShopAction(
                    "Зачисленные баллы",
                    GuideShopRoute(
                        kind="points", points_status=PointsStatus.CREDITED
                    ),
                ),
                GuideShopAction("История", GuideShopRoute(kind="history")),
            ),
        )

    async def companies(self) -> GuideShopScreen:
        try:
            response = await self._client.list_companies()
        except GuideShopClientError as error:
            return guide_shop_error_screen(error)

        text = (
            "\n\n".join(_company_text(company) for company in response.data)
            if response.data
            else "Компании пока отсутствуют."
        )
        return _screen(text, [_back_home()])

    async def visits(self, cursor: str | None = None) -> GuideShopScreen:
        try:
            response = await self._client.list_visits(cursor)
        except GuideShopClientError as error:
            return guide_shop_error_screen(error)

        actions = [
            GuideShopAction(
                f"Открыть визит {position}",
                GuideShopRoute(kind="visit_detail", object_id=visit.visit_id),
            )
            for position, visit in enumerate(response.data, start=1)
        ]
        if response.page.next_cursor is not None:
            actions.append(
                GuideShopAction(
                    "Далее",
                    GuideShopRoute(
                        kind="visits", cursor=response.page.next_cursor
                    ),
                )
            )
        actions.append(_back_home())
        text = (
            "\n\n".join(_visit_text(visit) for visit in response.data)
            if response.data
            else "Визиты пока отсутствуют."
        )
        return _screen(text, actions)

    async def visit_detail(self, visit_id: str) -> GuideShopScreen:
        try:
            visit = (await self._client.get_visit(visit_id)).data
        except GuideShopClientError as error:
            return guide_shop_error_screen(error)

        text = (
            f"🏢 Компания: {_safe(visit.company_id)}\n"
            f"Дата визита: {_timestamp(visit.visit_at)}\n"
            f"Туристов: {_safe(visit.tourist_count)}\n"
            f"Статус: {_safe(visit.status)}\n"
            f"Создано: {_timestamp(visit.created_at)}\n"
            f"Обновлено: {_timestamp(visit.updated_at)}"
        )
        return _screen(
            text,
            [GuideShopAction("⬅️ Назад к визитам", GuideShopRoute(kind="visits"))],
        )

    async def sales(self, cursor: str | None = None) -> GuideShopScreen:
        try:
            response = await self._client.list_sales(cursor)
        except GuideShopClientError as error:
            return guide_shop_error_screen(error)

        actions = [
            GuideShopAction(
                f"Открыть продажу {position}",
                GuideShopRoute(kind="sale_detail", object_id=sale.sale_id),
            )
            for position, sale in enumerate(response.data, start=1)
        ]
        if response.page.next_cursor is not None:
            actions.append(
                GuideShopAction(
                    "Далее",
                    GuideShopRoute(kind="sales", cursor=response.page.next_cursor),
                )
            )
        actions.append(_back_home())
        text = (
            "\n\n".join(_sale_text(sale) for sale in response.data)
            if response.data
            else "Продажи пока отсутствуют."
        )
        return _screen(text, actions)

    async def sale_detail(self, sale_id: str) -> GuideShopScreen:
        try:
            sale = (await self._client.get_sale(sale_id)).data
        except GuideShopClientError as error:
            return guide_shop_error_screen(error)

        lines = [
            f"💵 Сумма: {_safe(sale.amount)} {_safe(sale.currency)}",
            f"Категория: {_safe(sale.category_name)}",
            f"Оплата: {_safe(sale.payment_method)}",
            f"Статус: {_safe(sale.status)}",
            f"Создано: {_timestamp(sale.created_at)}",
            f"Обновлено: {_timestamp(sale.updated_at)}",
        ]
        return _screen(
            "\n".join(lines),
            [GuideShopAction("⬅️ Назад к продажам", GuideShopRoute(kind="sales"))],
        )

    async def points(
        self,
        status: PointsStatus | None = None,
        cursor: str | None = None,
    ) -> GuideShopScreen:
        try:
            response = await self._client.list_points(status, cursor)
        except GuideShopClientError as error:
            return guide_shop_error_screen(error)

        actions = [
            GuideShopAction(
                f"Открыть операцию {position}",
                GuideShopRoute(
                    kind="points_detail",
                    object_id=transaction.points_accrual_id,
                ),
            )
            for position, transaction in enumerate(response.data, start=1)
        ]
        if response.page.next_cursor is not None:
            actions.append(
                GuideShopAction(
                    "Далее",
                    GuideShopRoute(
                        kind="points",
                        cursor=response.page.next_cursor,
                        points_status=status,
                    ),
                )
            )
        actions.append(_back_home())
        text = (
            "\n\n".join(_points_text(item) for item in response.data)
            if response.data
            else "Операции с баллами пока отсутствуют."
        )
        return _screen(text, actions)

    async def points_detail(
        self, points_transaction_id: str
    ) -> GuideShopScreen:
        try:
            transaction = (
                await self._client.get_points_transaction(points_transaction_id)
            ).data
        except GuideShopClientError as error:
            return guide_shop_error_screen(error)

        lines = [
            f"Баллы: {_safe(transaction.amount)} {_safe(transaction.unit)}",
            f"Статус: {_safe(transaction.status)}",
        ]
        lines.append(f"Рассчитано: {_timestamp(transaction.calculated_at)}")
        if transaction.credited_at is not None:
            lines.append(f"Зачислено: {_timestamp(transaction.credited_at)}")
        lines.append(f"Обновлено: {_timestamp(transaction.updated_at)}")
        return _screen(
            "\n".join(lines),
            [GuideShopAction("⬅️ Назад к баллам", GuideShopRoute(kind="points"))],
        )

    async def history(self, cursor: str | None = None) -> GuideShopScreen:
        try:
            response = await self._client.list_history(cursor)
        except GuideShopClientError as error:
            return guide_shop_error_screen(error)

        actions = [
            GuideShopAction(
                f"Открыть операцию {position}",
                GuideShopRoute(
                    kind="points_detail",
                    object_id=transaction.payout_id,
                ),
            )
            for position, transaction in enumerate(response.data, start=1)
        ]
        if response.page.next_cursor is not None:
            actions.append(
                GuideShopAction(
                    "Далее",
                    GuideShopRoute(kind="history", cursor=response.page.next_cursor),
                )
            )
        actions.append(_back_home())
        text = (
            "\n\n".join(_history_text(item) for item in response.data)
            if response.data
            else "История операций пока отсутствует."
        )
        return _screen(text, actions)
