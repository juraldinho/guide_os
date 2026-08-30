from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from database.db import get_connection, run_write_with_retry
from services.miniapp_api_settings import MiniAppApiSettings

_MAX_SQLITE_INTEGER = 2**63 - 1
_DEV_USER_HEADER = "X-Dev-User-Id"
_BEARER_DEV = re.compile(r"^dev:(\d{1,20})\Z")


class MiniAppAuthError(Exception):
    pass


class MiniAppForbiddenError(Exception):
    pass


def _parse_user_id(value: str) -> int:
    try:
        user_id = int(value)
    except (TypeError, ValueError):
        raise MiniAppAuthError
    if not 0 < user_id <= _MAX_SQLITE_INTEGER:
        raise MiniAppAuthError
    return user_id


def _utc_now_timestamp() -> int:
    return int(time.time())


def _format_expires_at(expires_timestamp: int) -> str:
    return datetime.fromtimestamp(expires_timestamp, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _extract_bearer_token(request) -> str | None:
    auth_values = request.headers.getall("Authorization", [])
    if len(auth_values) != 1:
        return None
    token = auth_values[0].strip()
    if not token.startswith("Bearer "):
        return None
    bearer = token[7:].strip()
    return bearer or None


def check_allowlist(settings: MiniAppApiSettings, user_id: int) -> None:
    if settings.allowlist and user_id not in settings.allowlist:
        raise MiniAppForbiddenError


def create_miniapp_session(
    user_id: int,
    ttl_seconds: int,
    now_timestamp: int | None = None,
) -> tuple[str, str]:
    now = now_timestamp if now_timestamp is not None else _utc_now_timestamp()
    token = secrets.token_urlsafe(32)
    token_hash = _hash_session_token(token)
    expires_timestamp = now + ttl_seconds
    expires_at = _format_expires_at(expires_timestamp)

    def operation(conn):
        conn.execute(
            """
            INSERT INTO miniapp_sessions (token_hash, user_id, expires_at)
            VALUES (?, ?, ?)
            """,
            (token_hash, user_id, expires_at),
        )

    run_write_with_retry(operation)
    return token, expires_at


def resolve_session_user_id(token: str, now_timestamp: int | None = None) -> int | None:
    now = now_timestamp if now_timestamp is not None else _utc_now_timestamp()
    now_iso = _format_expires_at(now)
    token_hash = _hash_session_token(token)
    conn = get_connection()
    row = conn.execute(
        """
        SELECT user_id, expires_at
        FROM miniapp_sessions
        WHERE token_hash = ?
        LIMIT 1
        """,
        (token_hash,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    expires_at = row["expires_at"]
    if expires_at <= now_iso:
        revoke_miniapp_session(token)
        return None
    return int(row["user_id"])


def revoke_miniapp_session(token: str) -> bool:
    token_hash = _hash_session_token(token)

    def operation(conn):
        cursor = conn.execute(
            "DELETE FROM miniapp_sessions WHERE token_hash = ?",
            (token_hash,),
        )
        return cursor.rowcount > 0

    return run_write_with_retry(operation)


def resolve_user_id_from_request(
    request,
    settings: MiniAppApiSettings,
    now_timestamp: int | None = None,
) -> int:
    bearer = _extract_bearer_token(request)
    if bearer is not None:
        dev_match = _BEARER_DEV.fullmatch(bearer)
        if dev_match is not None:
            if not settings.dev_auth:
                raise MiniAppAuthError
            user_id = _parse_user_id(dev_match.group(1))
            check_allowlist(settings, user_id)
            return user_id

        session_user_id = resolve_session_user_id(bearer, now_timestamp=now_timestamp)
        if session_user_id is not None:
            check_allowlist(settings, session_user_id)
            return session_user_id
        raise MiniAppAuthError

    if settings.dev_auth:
        header_values = request.headers.getall(_DEV_USER_HEADER, [])
        if len(header_values) == 1:
            user_id = _parse_user_id(header_values[0].strip())
            check_allowlist(settings, user_id)
            return user_id

    raise MiniAppAuthError


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
