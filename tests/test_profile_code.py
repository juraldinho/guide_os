from database.queries import get_guide_os_id, register_user
from handlers.profile import _format_profile_card
from utils.guide_os_identity import is_canonical_guide_os_id


def test_profile_card_restores_previous_layout_without_internal_identity():
    register_user(555)
    guide_os_id = get_guide_os_id(555)

    card = _format_profile_card(555, "Гид")
    assert card == (
        "👤 Профиль\n\n"
        "Имя: Гид\n"
        "Telegram ID: 555"
    )
    assert guide_os_id not in card
    assert "GuideShop" not in card


def test_existing_internal_guide_os_id_remains_stable():
    register_user(556)
    first = get_guide_os_id(556)
    register_user(556)
    second = get_guide_os_id(556)

    assert is_canonical_guide_os_id(first)
    assert first == second


def test_profile_card_without_name_keeps_previous_layout():
    card = _format_profile_card(557, None)
    assert card == "👤 Профиль\n\nИмя: не указано\nTelegram ID: 557"
