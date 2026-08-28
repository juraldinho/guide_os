from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from database.db import get_connection, run_write_with_retry

_MAX_SQLITE_INTEGER = 2**63 - 1
_DEV_USER_HEADER = "X-Dev-User-Id"
_BEARER_DEV = re.compile(r"^dev:(\d{1,20})\Z")


class MiniAppAuthError(Exception):
    pass


def _parse_user_id(value: str) -> int:
    try:
        user_id = int(value)
    except (TypeError, ValueError):
        raise MiniAppAuthError
    if not 0 < user_id <= _MAX_SQLITE_INTEGER:
        raise MiniAppAuthError
    return user_id


def resolve_user_id_from_request(request, dev_auth_enabled: bool) -> int:
    if dev_auth_enabled:
        header_values = request.headers.getall(_DEV_USER_HEADER, [])
        if len(header_values) == 1:
            return _parse_user_id(header_values[0].strip())

    auth_values = request.headers.getall("Authorization", [])
    if len(auth_values) != 1:
        raise MiniAppAuthError
    token = auth_values[0].strip()
    if not token.startswith("Bearer "):
        raise MiniAppAuthError
    bearer = token[7:].strip()
    match = _BEARER_DEV.fullmatch(bearer)
    if match is None:
        raise MiniAppAuthError
    return _parse_user_id(match.group(1))


def dev_session_token(user_id: int) -> str:
    return f"dev:{user_id}"


def idempotency_lookup(
    user_id: int,
    endpoint: str,
    key: str,
    body_bytes: bytes,
) -> dict[str, Any] | None:
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    conn = get_connection()
    row = conn.execute(
        """
        SELECT body_hash, status_code, response_body
        FROM miniapp_idempotency
        WHERE user_id = ? AND endpoint = ? AND idempotency_key = ?
        LIMIT 1
        """,
        (user_id, endpoint, key),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    if row["body_hash"] != body_hash:
        return {"replay_conflict": True}
    return {
        "status_code": int(row["status_code"]),
        "response_body": row["response_body"],
    }


def idempotency_store(
    user_id: int,
    endpoint: str,
    key: str,
    body_bytes: bytes,
    status_code: int,
    response_body: str,
) -> None:
    body_hash = hashlib.sha256(body_bytes).hexdigest()

    def operation(conn):
        conn.execute(
            """
            INSERT INTO miniapp_idempotency (
                user_id, endpoint, idempotency_key, body_hash, status_code, response_body
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, endpoint, idempotency_key) DO UPDATE SET
                body_hash = excluded.body_hash,
                status_code = excluded.status_code,
                response_body = excluded.response_body
            """,
            (user_id, endpoint, key, body_hash, status_code, response_body),
        )

    run_write_with_retry(operation)


async def read_json_body(request, max_bytes: int) -> dict[str, Any]:
    if request.content_type != "application/json":
        raise ValueError("invalid content type")
    body = await request.read()
    if len(body) > max_bytes:
        raise ValueError("body too large")
    if not body:
        return {}
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("invalid json object")
    return data
