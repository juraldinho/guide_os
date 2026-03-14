import re


def validate_company(text: str) -> str:
    value = text.strip()

    if not value:
        raise ValueError("Название компании не может быть пустым")

    if len(value) > 100:
        raise ValueError("Название компании слишком длинное")

    return value


def validate_city(text: str) -> str:
    value = text.strip()

    if not value:
        raise ValueError("Город не может быть пустым")

    if len(value) > 100:
        raise ValueError("Название города слишком длинное")

    return value


def validate_income(text: str) -> int:
    value = text.strip()

    if not value.isdigit():
        raise ValueError("Введите число")

    income = int(value)

    if income < 0:
        raise ValueError("Доход не может быть отрицательным")

    if income > 10000:
        raise ValueError("Слишком большое значение")

    return income


def validate_note(text: str) -> str:
    value = text.strip()

    if len(value) > 500:
        raise ValueError("Заметка слишком длинная")

    return value
