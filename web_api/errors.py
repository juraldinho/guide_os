from __future__ import annotations

import secrets
from typing import Any

from aiohttp import web


def request_id(request: web.Request, random_bytes=secrets.token_bytes) -> str:
    values = request.headers.getall("X-Request-Id", [])
    if values:
        value = values[0].strip()
        if 8 <= len(value) <= 128:
            return value
    return "req_" + random_bytes(16).hex()


def success_response(data: Any, request_id_value: str, status: int = 200) -> web.Response:
    payload = {
        "data": data,
        "meta": {"request_id": request_id_value},
    }
    return web.json_response(payload, status=status)


def error_response(
    code: str,
    message: str,
    request_id_value: str,
    status: int,
    details: dict[str, Any] | None = None,
) -> web.Response:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "meta": {"request_id": request_id_value},
    }
    return web.json_response(payload, status=status)
