import asyncio
import copy
import socket

import pytest

from keyboards.guide_shop import build_guide_shop_keyboard
from services.guide_shop_client import (
    GuideShopAccessDeniedError,
    GuideShopClientError,
    GuideShopIntegrationDisabledError,
    GuideShopObjectNotFoundError,
    GuideShopTemporarilyUnavailableError,
    InMemoryGuideShopClient,
)
from services.guide_shop_contracts import (
    CompanyDTO,
    PointsAccrualDTO,
    PointsPayoutDTO,
    PointsStatus,
    SaleDTO,
    VisitDTO,
)
from services.guide_shop_navigation import (
    GuideShopRoute,
    NavigationTokenAccessDeniedError,
    resolve_navigation_token,
)
from services.guide_shop_ui import (
    GuideShopAction,
    GuideShopScreen,
    GuideShopUIService,
    guide_shop_error_screen,
)


UTC = "2026-08-07T12:00:00Z"


def run(awaitable):
    return asyncio.run(awaitable)


def company(company_id="company-1", name="Silk Road", status="active"):
    return CompanyDTO.model_validate(
        {"company_id": company_id, "display_name": name, "status": status}
    )


def visit(visit_id="visit-01", company_id="company-1"):
    return VisitDTO.model_validate(
        {
            "visit_id": visit_id,
            "company_id": company_id,
            "guide_membership_id": "gmem-0001",
            "visit_at": UTC,
            "status": "active",
            "tourist_count": 3,
            "customer_payment_status": "unpaid",
            "created_at": UTC,
            "updated_at": UTC,
        }
    )


def sale(sale_id="sale-001", category="Textiles"):
    payload = {
        "sale_id": sale_id,
        "visit_id": "visit-01",
        "company_id": "company-1",
        "amount": "125.40",
        "currency": "USD",
        "status": "active",
        "payment_method": "card",
        "category_id": "category1",
        "category_name": category,
        "created_at": UTC,
        "updated_at": UTC,
    }
    return SaleDTO.model_validate(payload)


def points(points_id="points-01", status="pending"):
    payload = {
        "points_accrual_id": points_id,
        "company_id": "company-1",
        "visit_id": "visit-01",
        "amount": "16.00",
        "unit": "PTS",
        "status": status,
        "calculated_at": UTC,
        "updated_at": UTC,
    }
    if status == "credited":
        payload["credited_at"] = UTC
        payload["payout_id"] = "payout-01"
    return PointsAccrualDTO.model_validate(payload)


def payout(payout_id="payout-01", accrual_id="points-01"):
    return PointsPayoutDTO.model_validate(
        {
            "payout_id": payout_id,
            "points_accrual_id": accrual_id,
            "company_id": "company-1",
            "visit_id": "visit-01",
            "amount": "16.00",
            "unit": "PTS",
            "paid_at": UTC,
            "created_at": UTC,
        }
    )


class NoCallClient:
    def __getattribute__(self, name):
        if name.startswith("list_") or name.startswith("get_"):
            raise AssertionError("client operation attempted")
        return super().__getattribute__(name)


def test_home_does_not_call_client_and_has_six_ordered_actions():
    screen = run(GuideShopUIService(NoCallClient()).home())
    assert screen.parse_mode == "HTML"
    assert [action.label for action in screen.actions] == [
        "Компании",
        "Визиты",
        "Продажи",
        "Ожидающие баллы",
        "Зачисленные баллы",
        "История",
    ]
    assert [action.route.kind for action in screen.actions] == [
        "companies",
        "visits",
        "sales",
        "points",
        "points",
        "history",
    ]
    assert screen.actions[3].route.points_status == PointsStatus.PENDING
    assert screen.actions[4].route.points_status == PointsStatus.CREDITED
    assert "баланс" not in screen.text.lower()


def test_presentation_models_are_immutable_and_strict():
    action = GuideShopAction("Home", GuideShopRoute(kind="home"))
    screen = GuideShopScreen("Text", (action,))
    with pytest.raises(Exception):
        action.label = "Changed"
    with pytest.raises(Exception):
        screen.text = "Changed"
    with pytest.raises(TypeError):
        GuideShopScreen("Text", [action])
    with pytest.raises(TypeError):
        GuideShopAction("Home", {"kind": "home"})


def test_lists_render_safe_external_text_exact_decimals_and_preserve_order():
    companies = [company("company1", "<b>First</b>", "active"), company("company2", "Second")]
    visits = [visit("visit-v2", "company-2"), visit("visit-v1", "company-1")]
    sales = [sale("sale-s02", "<Textiles>"), sale("sale-s01", "Ceramics")]
    transactions = [points("points-02"), points("points-01")]
    payouts = [payout("payout-02", "points-02"), payout("payout-01", "points-01")]
    snapshots = [item.model_dump() for item in companies + visits + sales + transactions]
    client = InMemoryGuideShopClient(
        companies=companies,
        visits=visits,
        sales=sales,
        points=transactions,
        points_history=payouts,
    )
    service = GuideShopUIService(client)

    company_screen = run(service.companies())
    visit_screen = run(service.visits())
    sale_screen = run(service.sales())
    points_screen = run(service.points())
    history_screen = run(service.history())

    assert "&lt;b&gt;First&lt;/b&gt;" in company_screen.text
    assert "active" in company_screen.text
    assert company_screen.text.index("First") < company_screen.text.index("Second")
    assert "company-2" in visit_screen.text
    assert [a.label for a in visit_screen.actions[:-1]] == [
        "Открыть визит 1",
        "Открыть визит 2",
    ]
    assert [a.route.object_id for a in visit_screen.actions[:-1]] == ["visit-v2", "visit-v1"]
    assert "125.40 USD" in sale_screen.text
    assert "&lt;Textiles&gt;" in sale_screen.text
    assert [a.label for a in sale_screen.actions[:-1]] == [
        "Открыть продажу 1",
        "Открыть продажу 2",
    ]
    assert [a.route.object_id for a in sale_screen.actions[:-1]] == ["sale-s02", "sale-s01"]
    assert "16.00" in points_screen.text
    assert [a.label for a in points_screen.actions[:-1]] == [
        "Открыть операцию 1",
        "Открыть операцию 2",
    ]
    assert [a.label for a in history_screen.actions[:-1]] == [
        "Открыть операцию 1",
        "Открыть операцию 2",
    ]
    assert [a.route.object_id for a in history_screen.actions[:-1]] == ["payout-02", "payout-01"]
    assert [item.model_dump() for item in companies + visits + sales + transactions] == snapshots


def test_pagination_routes_are_opaque_and_points_preserve_filter():
    client = InMemoryGuideShopClient(
        visits=[visit("visit-v1"), visit("visit-v2")],
        sales=[sale("sale-s01"), sale("sale-s02")],
        points=[points("points-01"), points("points-02")],
        points_history=[payout("payout-h1"), payout("payout-h2")],
        page_size=1,
    )
    service = GuideShopUIService(client)

    visit_next = run(service.visits()).actions[-2].route
    sale_next = run(service.sales()).actions[-2].route
    points_next = run(service.points(PointsStatus.PENDING)).actions[-2].route
    history_next = run(service.history()).actions[-2].route

    assert visit_next.kind == "visits" and visit_next.cursor
    assert visit_next.object_id is None and visit_next.points_status is None
    assert sale_next.kind == "sales" and sale_next.cursor
    assert points_next.kind == "points" and points_next.cursor
    assert points_next.points_status == PointsStatus.PENDING
    assert history_next.kind == "history" and history_next.cursor
    assert all(cursor not in run(service.home()).text for cursor in [visit_next.cursor, sale_next.cursor, points_next.cursor, history_next.cursor])


def test_detail_screens_include_required_and_optional_fields_safely():
    client = InMemoryGuideShopClient(
        visits=[visit()],
        sales=[sale(category="<Textiles>")],
        points=[points(status="credited")],
    )
    service = GuideShopUIService(client)

    visit_screen = run(service.visit_detail("visit-01"))
    sale_screen = run(service.sale_detail("sale-001"))
    points_screen = run(service.points_detail("points-01"))

    for label in ["Компания", "Дата визита", "Туристов", "Статус", "Создано", "Обновлено"]:
        assert label in visit_screen.text
    assert "Оплата" in sale_screen.text
    assert "125.40 USD" in sale_screen.text
    assert "&lt;Textiles&gt;" in sale_screen.text
    assert "Зачислено" in points_screen.text

    absent_client = InMemoryGuideShopClient(
        sales=[sale()], points=[points()]
    )
    absent_service = GuideShopUIService(absent_client)
    assert "Аннулировано" not in run(absent_service.sale_detail("sale-001")).text
    absent_points = run(absent_service.points_detail("points-01")).text
    assert "Зачислено" not in absent_points


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("companies", "Компании пока отсутствуют."),
        ("visits", "Визиты пока отсутствуют."),
        ("sales", "Продажи пока отсутствуют."),
        ("points", "Операции с баллами пока отсутствуют."),
        ("history", "История операций пока отсутствует."),
    ],
)
def test_empty_states_keep_back_action(method, expected):
    screen = run(getattr(GuideShopUIService(InMemoryGuideShopClient()), method)())
    assert screen.text == expected
    assert screen.actions[-1].route.kind == "home"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (GuideShopIntegrationDisabledError("secret"), "Раздел GuideShop временно отключён."),
        (GuideShopTemporarilyUnavailableError("secret"), "GuideShop временно недоступен. Попробуйте позже."),
        (GuideShopAccessDeniedError("secret"), "Нет доступа к данным GuideShop."),
        (GuideShopObjectNotFoundError("secret"), "Объект GuideShop не найден или недоступен."),
        (GuideShopClientError("secret"), "Не удалось загрузить данные GuideShop."),
    ],
)
def test_client_errors_map_to_exact_safe_screens(error, expected):
    screen = guide_shop_error_screen(error)
    assert screen.text == expected
    assert "secret" not in screen.text
    assert screen.actions == (GuideShopAction("⬅️ Назад в GuideShop", GuideShopRoute(kind="home")),)


class RaisingClient:
    def __init__(self, error):
        self.error = error

    async def list_companies(self):
        raise self.error


def test_service_maps_domain_errors_but_does_not_swallow_programming_errors():
    screen = run(GuideShopUIService(RaisingClient(GuideShopAccessDeniedError("private"))).companies())
    assert screen.text == "Нет доступа к данным GuideShop."
    with pytest.raises(TypeError, match="programming"):
        run(GuideShopUIService(RaisingClient(TypeError("programming"))).companies())


def test_keyboard_creates_one_user_bound_opaque_token_per_ordered_action():
    user_id = 987654321
    actions = (
        GuideShopAction("Первое действие", GuideShopRoute(kind="visit_detail", object_id="sensitive-object-id")),
        GuideShopAction("Второе действие", GuideShopRoute(kind="visits", cursor="opaque-next-cursor")),
    )
    keyboard = build_guide_shop_keyboard(user_id, actions)

    assert [row[0].text for row in keyboard.inline_keyboard] == [a.label for a in actions]
    callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert len(callbacks) == len(actions)
    for callback in callbacks:
        assert callback.startswith("gs_")
        assert len(callback) <= 48
        for private_value in ["sensitive-object-id", "opaque-next-cursor", str(user_id), "Первое", "Второе"]:
            assert private_value not in callback

    with pytest.raises(NavigationTokenAccessDeniedError):
        resolve_navigation_token(callbacks[0], user_id + 1)
    assert resolve_navigation_token(callbacks[0], user_id) == actions[0].route
    assert resolve_navigation_token(callbacks[1], user_id) == actions[1].route


def test_empty_keyboard_is_valid_and_keyboard_creation_has_no_network(monkeypatch):
    assert build_guide_shop_keyboard(101, ()).inline_keyboard == []

    def unexpected(*args, **kwargs):
        raise AssertionError("network operation attempted")

    monkeypatch.setattr(socket, "socket", unexpected)
    keyboard = build_guide_shop_keyboard(
        101,
        (GuideShopAction("Home", GuideShopRoute(kind="home")),),
    )
    assert keyboard.inline_keyboard[0][0].callback_data.startswith("gs_")
