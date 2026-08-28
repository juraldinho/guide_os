from __future__ import annotations

import re

from aiohttp import web

from services.availability_service import build_availability_preview
from web_api.dto import availability_preview_to_api
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def register_availability_routes(app: web.Application) -> None:
    async def preview_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure

        try:
            data = await request.json()
        except Exception:
            return error_response("validation_error", "Некорректный JSON.", rid, 400)
        if not isinstance(data, dict):
            return error_response("validation_error", "Некорректный JSON.", rid, 400)

        from_date = data.get("from")
        to_date = data.get("to")
        if (
            not isinstance(from_date, str)
            or not isinstance(to_date, str)
            or _DATE_RE.fullmatch(from_date) is None
            or _DATE_RE.fullmatch(to_date) is None
            or from_date > to_date
        ):
            return error_response("validation_error", "Укажите корректные from и to.", rid, 400)

        preview = build_availability_preview(user_id, from_date, to_date)
        return success_response(availability_preview_to_api(preview), rid)

    app.router.add_post("/app/v1/availability/preview", preview_handler)
