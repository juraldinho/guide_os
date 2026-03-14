import pytest

from utils.validators import (
    validate_company,
    validate_city,
    validate_income,
    validate_note
)


def test_validate_company():
    assert validate_company("OrexCA") == "OrexCA"


def test_company_empty():
    with pytest.raises(ValueError):
        validate_company("")


def test_validate_city():
    assert validate_city("Самарканд") == "Самарканд"


def test_city_empty():
    with pytest.raises(ValueError):
        validate_city("")


def test_validate_income():
    assert validate_income("100") == 100


def test_income_not_number():
    with pytest.raises(ValueError):
        validate_income("abc")


def test_income_negative():
    with pytest.raises(ValueError):
        validate_income("-5")


def test_note():
    assert validate_note("test note") == "test note"
