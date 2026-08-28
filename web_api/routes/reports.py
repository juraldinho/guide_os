from __future__ import annotations

import re

from aiohttp import web

from services.reports_service import get_reports_summary
from web_api.dto import reports_summary_to_api
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def register_reports_routes(app: web.Application) -> None:
    async def summary_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure

        from_date = request.rel_url.query.get("from")
        to_date = request.rel_url.query.get("to")
        if (
            not from_date
            or not to_date
            or _DATE_RE.fullmatch(from_date) is None
            or _DATE_RE.fullmatch(to_date) is None
            or from_date > to_date
        ):
            return error_response("validation_error", "Укажите корректные from и to.", rid, 400)

        status = request.rel_url.query.get("status", "all")
        payment = request.rel_url.query.get("payment", "all")
        if status not in ("all", "reserved", "confirmed"):
            return error_response("validation_error", "Некорректный status.", rid, 400)
        if payment not in ("all", "paid", "unpaid"):
            return error_response("validation_error", "Некорректный payment.", rid, 400)

        filters = {
            "status": status,
            "payment": payment,
            "company": request.rel_url.query.get("company", "") or "",
            "location": request.rel_url.query.get("location", "") or "",
        }
        summary = get_reports_summary(user_id, from_date, to_date, filters)
        return success_response(reports_summary_to_api(summary), rid)

    app.router.add_get("/app/v1/reports/summary", summary_handler)
