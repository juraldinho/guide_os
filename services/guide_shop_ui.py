from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from html import escape
from typing import Literal
from zoneinfo import ZoneInfo

from config import TIMEZONE

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
    PointsSummaryDTO,
    SaleDTO,
    SalePaymentMethod,
    VisitDTO,
)
from services.guide_shop_navigation import GuideShopRoute

UI_TZ = ZoneInfo(TIMEZONE)
UNKNOWN_COMPANY = "Компания не найдена"
NOT_SPECIFIED = "Не указано"


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


def _company_status_label(status: object) -> str:
    return {
        "active": "Активна",
        "inactive": "Неактивна",
    }.get(getattr(status, "value", status), "Неизвестно")


def _visit_status_label(status: object) -> str:
    return {
        "active": "Активен",
        "completed": "Завершен",
        "cancelled": "Отменен",
    }.get(getattr(status, "value", status), "Неизвестно")


def _sale_status_label(status: object) -> str:
    return {
        "active": "Активна",
    }.get(getattr(status, "value", status), "Неизвестно")


def _points_status_label(status: object) -> str:
    return {
        "pending": "Ожидает выплаты",
        "credited": "Выплачено",
    }.get(getattr(status, "value", status), "Неизвестно")


def _positive_pts(value: str) -> bool:
    return Decimal(value) > Decimal("0.00")


def _timestamp(value: object) -> str:
    if not isinstance(value, datetime):
        raise TypeError("timestamp value must be datetime")
    localized = value.astimezone(UI_TZ)
    return _safe(localized.strftime("%d.%m.%Y %H:%M"))


def _company_name(company_id: str, company_names: dict[str, str]) -> str:
    return company_names.get(company_id, UNKNOWN_COMPANY)


async def _company_name_map(client: GuideShopClient) -> dict[str, str]:
    response = await client.list_companies()
    return {
        company.company_id: company.display_name
        for company in response.data
    }


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
        f"Статус: {_company_status_label(company.status)}"
    )


def _optional_company_value(value: str | None) -> str:
    if value is None:
        return NOT_SPECIFIED
    if not value.strip():
        return NOT_SPECIFIED
    return value


def _visit_text(visit: VisitDTO, company_names: dict[str, str]) -> str:
    return (
        f"🏢 Компания: {_safe(_company_name(visit.company_id, company_names))}\n"
        f"Дата визита: {_timestamp(visit.visit_at)}\n"
        f"Туристов: {_safe(visit.tourist_count)}\n"
        f"Статус: {_visit_status_label(visit.status)}"
    )


def _sale_payment_line(sale: SaleDTO) -> str:
    if sale.payment_method is SalePaymentMethod.UNKNOWN:
        return "Способ оплаты: не указан"
    return f"Оплата: {_safe(sale.payment_method)}"


def _sale_text(sale: SaleDTO) -> str:
    return (
        f"💵 Сумма: {_safe(sale.amount)} {_safe(sale.currency)}\n"
        f"Категория: {_safe(sale.category_name)}\n"
        f"{_sale_payment_line(sale)}\n"
        f"Статус: {_sale_status_label(sale.status)}\n"
        f"Создано: {_timestamp(sale.created_at)}"
    )


def _points_text(transaction: PointsAccrualDTO, company_names: dict[str, str]) -> str:
    lines = [
        f"🏢 Компания: {_safe(_company_name(transaction.company_id, company_names))}",
        f"Баллы: {_safe(transaction.amount)} {_safe(transaction.unit)}",
        f"Статус: {_points_status_label(transaction.status)}",
        f"Рассчитано: {_timestamp(transaction.calculated_at)}",
    ]
    return "\n".join(lines)


def _history_text(transaction: PointsPayoutDTO, company_names: dict[str, str]) -> str:
    return (
        f"🏢 Компания: {_safe(_company_name(transaction.company_id, company_names))}\n"
        f"Баллы: {_safe(transaction.amount)} {_safe(transaction.unit)}\n"
        f"Выплачено: {_timestamp(transaction.paid_at)}"
    )


def _company_breakdown_lines(
    companies, *, amount_attr: str
) -> list[str]:
    lines = []
    for company in companies:
        amount = getattr(company, amount_attr)
        if _positive_pts(amount):
            lines.append(f"{_safe(company.display_name)}: {_safe(amount)} PTS")
    return lines


def _points_operations_block(
    items: list[PointsAccrualDTO], company_names: dict[str, str]
) -> str:
    if not items:
        return ""
    return "\n\n".join(_points_text(item, company_names) for item in items)


def _pending_points_text(
    summary: PointsSummaryDTO,
    items: list[PointsAccrualDTO],
    company_names: dict[str, str],
) -> str:
    if not _positive_pts(summary.pending_total):
        return "Ожидающих выплат нет"
    parts = [f"Ожидает выплаты: {_safe(summary.pending_total)} PTS"]
    breakdown = _company_breakdown_lines(
        summary.companies, amount_attr="pending_total"
    )
    if breakdown:
        parts.append("\n".join(breakdown))
    operations = _points_operations_block(items, company_names)
    if operations:
        parts.append(operations)
    return "\n\n".join(parts)


def _credited_points_text(
    summary: PointsSummaryDTO,
    items: list[PointsAccrualDTO],
    company_names: dict[str, str],
) -> str:
    if not _positive_pts(summary.credited_total):
        return "Выплаченных баллов пока нет"
    parts = [f"Выплачено: {_safe(summary.credited_total)} PTS"]
    breakdown = _company_breakdown_lines(
        summary.companies, amount_attr="credited_total"
    )
    if breakdown:
        parts.append("\n".join(breakdown))
    operations = _points_operations_block(items, company_names)
    if operations:
        parts.append(operations)
    return "\n\n".join(parts)


def _unfiltered_points_text(
    summary: PointsSummaryDTO,
    items: list[PointsAccrualDTO],
    company_names: dict[str, str],
) -> str:
    if not _positive_pts(summary.pending_total) and not _positive_pts(
        summary.credited_total
    ):
        return "Операции с баллами пока отсутствуют."
    sections: list[str] = []
    if _positive_pts(summary.pending_total):
        pending_lines = [f"Ожидает выплаты: {_safe(summary.pending_total)} PTS"]
        breakdown = _company_breakdown_lines(
            summary.companies, amount_attr="pending_total"
        )
        if breakdown:
            pending_lines.append("\n".join(breakdown))
        sections.append("\n\n".join(pending_lines))
    if _positive_pts(summary.credited_total):
        credited_lines = [f"Выплачено: {_safe(summary.credited_total)} PTS"]
        breakdown = _company_breakdown_lines(
            summary.companies, amount_attr="credited_total"
        )
        if breakdown:
            credited_lines.append("\n".join(breakdown))
        sections.append("\n\n".join(credited_lines))
    operations = _points_operations_block(items, company_names)
    if operations:
        sections.append(operations)
    return "\n\n".join(sections)


class GuideShopUIService:
    def __init__(self, client: GuideShopClient) -> None:
        self._client = client

    async def home(self) -> GuideShopScreen:
        return GuideShopScreen(
            text="<b>GuideShop</b>",
            actions=(
                GuideShopAction("Компании", GuideShopRoute(kind="companies")),
                GuideShopAction("Визиты", GuideShopRoute(kind="visits")),
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

        actions = [
            GuideShopAction(
                company.display_name,
                GuideShopRoute(kind="company_detail", object_id=company.company_id),
            )
            for company in response.data
        ]
        actions.append(_back_home())
        text = (
            "\n\n".join(_company_text(company) for company in response.data)
            if response.data
            else "Компании пока отсутствуют."
        )
        return _screen(text, actions)

    async def company_detail(self, company_id: str) -> GuideShopScreen:
        try:
            response = await self._client.list_companies()
        except GuideShopClientError as error:
            return guide_shop_error_screen(error)

        company = next(
            (item for item in response.data if item.company_id == company_id),
            None,
        )
        if company is None:
            text = f"🏢 <b>{UNKNOWN_COMPANY}</b>"
        else:
            text = (
                f"🏢 <b>{_safe(company.display_name)}</b>\n"
                f"Тип: {_safe(_optional_company_value(company.type))}\n"
                f"Телефон: {_safe(_optional_company_value(company.phone))}\n"
                f"Адрес: {_safe(_optional_company_value(company.address))}\n"
                f"Описание: {_safe(_optional_company_value(company.description))}\n"
                f"Статус: {_company_status_label(company.status)}"
            )
        return _screen(
            text,
            [GuideShopAction("⬅️ Назад к компаниям", GuideShopRoute(kind="companies"))],
        )

    async def visits(self, cursor: str | None = None) -> GuideShopScreen:
        try:
            response = await self._client.list_visits(cursor)
            company_names = (
                await _company_name_map(self._client) if response.data else {}
            )
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
            "\n\n".join(
                _visit_text(visit, company_names) for visit in response.data
            )
            if response.data
            else "Визиты пока отсутствуют."
        )
        return _screen(text, actions)

    async def visit_detail(self, visit_id: str) -> GuideShopScreen:
        try:
            visit = (await self._client.get_visit(visit_id)).data
            points_response = await self._client.list_points(visit_id=visit_id)
            company_names = await _company_name_map(self._client)
        except GuideShopClientError as error:
            return guide_shop_error_screen(error)

        if points_response.data:
            points_block = "Баллы за визит:\n" + "\n".join(
                f"{_safe(item.amount)} {_safe(item.unit)} — {_points_status_label(item.status)}"
                for item in points_response.data
            )
        else:
            points_block = "Баллы за визит: не начислены"
        text = (
            f"🏢 Компания: {_safe(_company_name(visit.company_id, company_names))}\n"
            f"Дата визита: {_timestamp(visit.visit_at)}\n"
            f"Туристов: {_safe(visit.tourist_count)}\n"
            f"Статус: {_visit_status_label(visit.status)}\n"
            f"Создано: {_timestamp(visit.created_at)}\n"
            f"Обновлено: {_timestamp(visit.updated_at)}\n"
            + points_block
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
            _sale_payment_line(sale),
            f"Статус: {_sale_status_label(sale.status)}",
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
            summary = await self._client.get_points_summary()
            response = await self._client.list_points(status, cursor)
            company_names = await _company_name_map(self._client)
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
        if status is PointsStatus.PENDING:
            text = _pending_points_text(
                summary, response.data, company_names
            )
        elif status is PointsStatus.CREDITED:
            text = _credited_points_text(
                summary, response.data, company_names
            )
        else:
            text = _unfiltered_points_text(
                summary, response.data, company_names
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
            f"Статус: {_points_status_label(transaction.status)}",
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
            company_names = await _company_name_map(self._client)
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
            "\n\n".join(_history_text(item, company_names) for item in response.data)
            if response.data
            else "История операций пока отсутствует."
        )
        return _screen(text, actions)
