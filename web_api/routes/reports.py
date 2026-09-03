from __future__ import annotations

import re

from aiohttp import web

from services.reports_service import (
    get_commission_reports_summary,
    get_reports_summary,
)
from web_api.dto import (
    commission_reports_summary_to_api,
    reports_summary_to_api,
    validate_date_range,
)
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COMMISSION_QUERY_KEYS = frozenset({"from", "to"})
_MSG_COMMISSION_RANGE = "Укажите корректные from и to."


def _single_query_value(request: web.Request, key: str) -> str | None:
    values = request.rel_url.query.getall(key, [])
    if len(values) != 1:
        return None
    return values[0]


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

    async def commissions_summary_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure

        query_keys = set(request.rel_url.query.keys())
        if query_keys - _COMMISSION_QUERY_KEYS:
            return error_response(
                "validation_error",
                _MSG_COMMISSION_RANGE,
                rid,
                400,
            )

        from_date = _single_query_value(request, "from")
        to_date = _single_query_value(request, "to")
        if from_date is None or to_date is None:
            return error_response(
                "validation_error",
                _MSG_COMMISSION_RANGE,
                rid,
                400,
            )

        try:
            from_date, to_date = validate_date_range(from_date, to_date)
            summary = get_commission_reports_summary(user_id, from_date, to_date)
        except ValueError:
            return error_response(
                "validation_error",
                _MSG_COMMISSION_RANGE,
                rid,
                400,
            )

        return success_response(commission_reports_summary_to_api(summary), rid)

    app.router.add_get("/app/v1/reports/summary", summary_handler)
    app.router.add_get("/app/v1/reports/commissions", commissions_summary_handler)
