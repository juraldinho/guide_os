import pytest

from services.date_parser import parse_date_input, parse_single_date


def test_single_date_slash():
    result = parse_date_input("23/03")

    assert len(result) == 1
    assert "start_date" in result[0]
    assert "end_date" in result[0]


def test_single_date_dot():
    result = parse_date_input("23.03")

    assert len(result) == 1


def test_iso_date():
    result = parse_date_input("2026-03-23")

    assert result[0]["start_date"] == "2026-03-23"
    assert result[0]["end_date"] == "2026-03-23"


def test_short_range():
    result = parse_date_input("1-2/06")

    assert result[0]["start_date"] <= result[0]["end_date"]


def test_full_range():
    result = parse_date_input("7.03-9.03")

    assert result[0]["start_date"] <= result[0]["end_date"]


def test_multiple_dates():
    result = parse_date_input("1-2/06, 4/06")

    assert len(result) == 2


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "abc",
        "32/06",
        "99.99",
        "10-1/06"
    ]
)
def test_invalid_dates(bad):
    with pytest.raises(ValueError):
        parse_date_input(bad)


def test_parse_single_date():
    result = parse_single_date("23/03")
    assert isinstance(result, str)
