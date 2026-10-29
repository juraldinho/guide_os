"""Daily received tips, independent of calendar occupancy and tour filters."""
from datetime import date

from database import queries

# At most 3,652,059 valid calendar dates: even their combined tips fit JS safe int.
MAX_DAILY_TIPS = 1_000_000_000


def validate_tip_date(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Укажите корректную дату YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Укажите корректную дату YYYY-MM-DD.") from exc
    if parsed.isoformat() != value:
        raise ValueError("Укажите корректную дату YYYY-MM-DD.")
    return value


def validate_tip_amount(amount: int) -> int:
    if type(amount) is not int or not 0 <= amount <= MAX_DAILY_TIPS:
        raise ValueError(f"Введите целое число USD от 0 до {MAX_DAILY_TIPS}.")
    return amount


def _validate_owner(user_id: int) -> None:
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("Некорректный пользователь.")


def get_daily_tips(user_id: int, from_date: str, to_date: str) -> list[dict]:
    _validate_owner(user_id)
    validate_tip_date(from_date)
    validate_tip_date(to_date)
    if from_date > to_date:
        raise ValueError("Начало периода должно быть не позже окончания.")
    return queries.list_daily_tips(user_id, from_date, to_date)


def get_daily_tip(user_id: int, tip_date: str) -> dict:
    rows = get_daily_tips(user_id, tip_date, tip_date)
    return rows[0] if rows else {"date": tip_date, "amount": 0}


def set_daily_tip(user_id: int, tip_date: str, amount: int) -> dict:
    _validate_owner(user_id)
    validate_tip_date(tip_date)
    validate_tip_amount(amount)
    queries.set_daily_tips(user_id, tip_date, amount)
    return {"date": tip_date, "amount": amount}
