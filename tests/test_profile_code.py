from database.queries import get_guide_os_id, register_user
from handlers.profile import _format_profile_card
from utils.guide_os_identity import is_canonical_guide_os_id


def test_profile_card_displays_existing_stable_guide_os_id():
    register_user(555)
    code = get_guide_os_id(555)

    assert is_canonical_guide_os_id(code)
    card = _format_profile_card(555, "Гид", code)
    assert f"Код профиля Guide OS: {code}" in card
    assert (
        "Покажите этот код владельцу или менеджеру GuideShop "
        "для привязки профиля." in card
    )
    assert "Имя: Гид" in card


def test_repeated_profile_views_display_the_same_code():
    register_user(556)
    first = get_guide_os_id(556)
    register_user(556)
    second = get_guide_os_id(556)

    assert first == second
    assert _format_profile_card(556, None, first) == _format_profile_card(
        556, None, second
    )


def test_profile_card_without_code_keeps_existing_layout():
    card = _format_profile_card(557, None)
    assert card == "👤 Профиль\n\nИмя: не указано\nTelegram ID: 557"
    assert "Код профиля Guide OS" not in card
