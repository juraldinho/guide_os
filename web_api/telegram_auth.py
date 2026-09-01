from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qsl

_MAX_SQLITE_INTEGER = 2**63 - 1
MAX_FUTURE_CLOCK_SKEW_SECONDS = 30
_SENSITIVE_INIT_DATA_KEYS = frozenset({"hash", "auth_date", "user"})


class InitDataValidationError(Exception):
    pass


def _build_data_check_string(fields: dict[str, str]) -> str:
    return "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))


def _telegram_secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


def _parse_init_data_pairs(init_data: str) -> tuple[str, dict[str, str]]:
    pairs = parse_qsl(init_data, keep_blank_values=True)
    counts = {key: 0 for key in _SENSITIVE_INIT_DATA_KEYS}
    received_hash: str | None = None
    fields: dict[str, str] = {}

    for key, value in pairs:
        if key in _SENSITIVE_INIT_DATA_KEYS:
            counts[key] += 1
            if counts[key] > 1:
                raise InitDataValidationError
        if key == "hash":
            received_hash = value
        else:
            fields[key] = value

    if counts["hash"] != 1 or counts["auth_date"] != 1 or counts["user"] != 1:
        raise InitDataValidationError
    if received_hash is None or not received_hash:
        raise InitDataValidationError

    return received_hash, fields


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int,
    now_timestamp: int,
) -> tuple[int, str]:
    if not isinstance(init_data, str) or not init_data.strip():
        raise InitDataValidationError
    if not bot_token:
        raise InitDataValidationError

    received_hash, parsed = _parse_init_data_pairs(init_data)

    data_check_string = _build_data_check_string(parsed)
    secret_key = _telegram_secret_key(bot_token)
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise InitDataValidationError

    auth_date_raw = parsed.get("auth_date")
    try:
        auth_date = int(auth_date_raw)
    except (TypeError, ValueError):
        raise InitDataValidationError
    if auth_date <= 0:
        raise InitDataValidationError
    if auth_date > now_timestamp + MAX_FUTURE_CLOCK_SKEW_SECONDS:
        raise InitDataValidationError
    if now_timestamp - auth_date > max_age_seconds:
        raise InitDataValidationError

    user_raw = parsed.get("user")
    if not isinstance(user_raw, str) or not user_raw:
        raise InitDataValidationError
    try:
        user_payload = json.loads(user_raw)
    except json.JSONDecodeError:
        raise InitDataValidationError
    if not isinstance(user_payload, dict):
        raise InitDataValidationError

    try:
        user_id = int(user_payload.get("id"))
    except (TypeError, ValueError):
        raise InitDataValidationError
    if not 0 < user_id <= _MAX_SQLITE_INTEGER:
        raise InitDataValidationError

    first_name = user_payload.get("first_name")
    last_name = user_payload.get("last_name")
    display_parts = []
    if isinstance(first_name, str) and first_name.strip():
        display_parts.append(first_name.strip())
    if isinstance(last_name, str) and last_name.strip():
        display_parts.append(last_name.strip())
    display_name = " ".join(display_parts)
    return user_id, display_name


def build_synthetic_init_data(
    bot_token: str,
    user_id: int,
    auth_date: int,
    **extra_fields: str,
) -> str:
    user_json = json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":"))
    fields = {
        "auth_date": str(auth_date),
        "user": user_json,
    }
    for key, value in extra_fields.items():
        fields[key] = value
    data_check_string = _build_data_check_string(fields)
    secret_key = _telegram_secret_key(bot_token)
    fields["hash"] = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return "&".join(f"{key}={value}" for key, value in fields.items())
