from __future__ import annotations

import json

from aiohttp import web

from utils.constants import DAY_OFF_LABEL, ENTRY_TYPE_DAY_OFF, STATUS_CONFIRMED

from services.tour_service import (
    TourEntryDraft,
    check_entry_conflicts,
    create_day_off_entry,
    create_tour_entry,
    copy_tour_entry,
    delete_tour,
    get_entry,
    list_entries,
    update_day_locations,
    update_tour_entry,
)
from web_api.auth import idempotency_lookup, idempotency_store, read_json_body
from web_api.dto import (
    conflict_to_error,
    entry_to_api,
    parse_entry_id,
    normalize_day_locations,
    tour_draft_from_body,
    validate_date_range,
)
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error


def _entry_id_not_found_response(rid: str) -> web.Response:
    return error_response("not_found", "Запись не найдена.", rid, 404)


def _resolve_entry_id(request: web.Request, rid: str) -> tuple[str | None, web.Response | None]:
    parsed = parse_entry_id(request.match_info["entry_id"])
    if parsed is None:
        return None, _entry_id_not_found_response(rid)
    return str(parsed), None


def _parse_date_range(request: web.Request) -> tuple[str, str] | None:
    from_date = request.rel_url.query.get("from")
    to_date = request.rel_url.query.get("to")
    if not from_date or not to_date:
        return None
    try:
        return validate_date_range(from_date, to_date)
    except ValueError:
        return None


async def _idempotent(
    request: web.Request,
    user_id: int,
    endpoint: str,
    body_bytes: bytes,
    build_response,
) -> web.Response:
    key = request.headers.get("Idempotency-Key")
    if key:
        stored = idempotency_lookup(user_id, endpoint, key.strip(), body_bytes)
        if stored and stored.get("replay_conflict"):
            rid = request["request_id"]
            return error_response(
                "idempotency_replay",
                "Idempotency-Key уже использован с другим телом запроса.",
                rid,
                409,
            )
        if stored:
            return web.Response(
                body=stored["response_body"],
                status=stored["status_code"],
                content_type="application/json",
            )

    response = await build_response()
    if key and response.body:
        idempotency_store(
            user_id,
            endpoint,
            key.strip(),
            body_bytes,
            response.status,
            response.body.decode("utf-8"),
        )
    return response


def register_entries_routes(app: web.Application) -> None:
    async def list_entries_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        parsed = _parse_date_range(request)
        if parsed is None:
            return error_response("validation_error", "Укажите корректные from и to.", rid, 400)
        from_date, to_date = parsed
        entries = list_entries(user_id, from_date, to_date)
        return success_response(
            {"entries": [entry_to_api(entry) for entry in entries]},
            rid,
        )

    async def get_entry_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        entry_id, entry_failure = _resolve_entry_id(request, rid)
        if entry_failure is not None:
            return entry_failure
        entry = get_entry(user_id, entry_id)
        if entry is None:
            return _entry_id_not_found_response(rid)
        return success_response(entry_to_api(entry), rid)

    async def create_tour_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        body_bytes = await request.read()

        async def build():
            try:
                data = json.loads(body_bytes or b"{}")
                if not isinstance(data, dict):
                    raise ValueError
                draft = tour_draft_from_body(data)
            except (ValueError, TypeError, json.JSONDecodeError):
                return error_response("validation_error", "Некорректные данные тура.", rid, 400)

            conflict = check_entry_conflicts(user_id, draft)
            if conflict and conflict.get("block"):
                code, message, details = conflict_to_error(conflict)
                return error_response(code, message, rid, 409, details)
            if conflict and conflict.get("warn") and not data.get("ack_date_warning"):
                code, message, details = conflict_to_error(conflict)
                return error_response(code, message, rid, 409, details)

            try:
                created = create_tour_entry(user_id, draft)
            except ValueError as exc:
                return error_response("validation_error", str(exc), rid, 400)
            return success_response(entry_to_api(created), rid, status=201)

        return await _idempotent(request, user_id, "POST /app/v1/tours", body_bytes, build)

    async def update_entry_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        entry_id, entry_failure = _resolve_entry_id(request, rid)
        if entry_failure is not None:
            return entry_failure
        body_bytes = await request.read()
        endpoint = f"PATCH /app/v1/entries/{entry_id}"

        async def build():
            if get_entry(user_id, entry_id) is None:
                return _entry_id_not_found_response(rid)
            try:
                data = json.loads(body_bytes or b"{}")
                if not isinstance(data, dict):
                    raise ValueError
                draft = tour_draft_from_body(data)
            except (ValueError, TypeError, json.JSONDecodeError):
                return error_response("validation_error", "Некорректные данные тура.", rid, 400)

            conflict = check_entry_conflicts(user_id, draft, exclude_id=entry_id)
            if conflict and conflict.get("block"):
                code, message, details = conflict_to_error(conflict)
                return error_response(code, message, rid, 409, details)
            if conflict and conflict.get("warn") and not data.get("ack_date_warning"):
                code, message, details = conflict_to_error(conflict)
                return error_response(code, message, rid, 409, details)

            try:
                updated = update_tour_entry(user_id, entry_id, draft)
            except ValueError as exc:
                return error_response("validation_error", str(exc), rid, 400)
            if updated is None:
                return _entry_id_not_found_response(rid)
            return success_response(entry_to_api(updated), rid)

        return await _idempotent(request, user_id, endpoint, body_bytes, build)

    async def create_day_off_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        body_bytes = await request.read()

        async def build():
            try:
                data = json.loads(body_bytes or b"{}")
                if not isinstance(data, dict):
                    raise ValueError
                start_date = data.get("startDate")
                end_date = data.get("endDate") or start_date
                if not isinstance(start_date, str) or not isinstance(end_date, str):
                    raise ValueError
                start_date, end_date = validate_date_range(start_date, end_date)
            except (ValueError, TypeError, json.JSONDecodeError):
                return error_response("validation_error", "Некорректные даты выходного.", rid, 400)

            draft_probe = TourEntryDraft(
                title="Выходной",
                company=DAY_OFF_LABEL,
                location="—",
                start_date=start_date,
                end_date=end_date,
                status=STATUS_CONFIRMED,
                income=0,
                entry_type=ENTRY_TYPE_DAY_OFF,
            )
            conflict = check_entry_conflicts(user_id, draft_probe)
            if conflict and conflict.get("block"):
                code, message, details = conflict_to_error(conflict)
                return error_response(code, message, rid, 409, details)
            if conflict and conflict.get("warn") and not data.get("ack_date_warning"):
                code, message, details = conflict_to_error(conflict)
                return error_response(code, message, rid, 409, details)

            created = create_day_off_entry(user_id, start_date, end_date)
            return success_response(entry_to_api(created), rid, status=201)

        return await _idempotent(request, user_id, "POST /app/v1/day-offs", body_bytes, build)

    async def delete_entry_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        entry_id, entry_failure = _resolve_entry_id(request, rid)
        if entry_failure is not None:
            return entry_failure
        body_bytes = b""
        endpoint = f"DELETE /app/v1/entries/{entry_id}"

        async def build():
            if get_entry(user_id, entry_id) is None:
                return _entry_id_not_found_response(rid)
            deleted = delete_tour(user_id, int(entry_id))
            if not deleted:
                return _entry_id_not_found_response(rid)
            return success_response({}, rid)

        return await _idempotent(request, user_id, endpoint, body_bytes, build)

    async def copy_entry_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        entry_id, entry_failure = _resolve_entry_id(request, rid)
        if entry_failure is not None:
            return entry_failure
        body_bytes = await request.read()
        endpoint = f"POST /app/v1/entries/{entry_id}/copy"

        async def build():
            try:
                data = json.loads(body_bytes or b"{}")
                if not isinstance(data, dict):
                    raise ValueError
                new_start = data.get("startDate")
                new_end = data.get("endDate") or new_start
                if not isinstance(new_start, str) or not isinstance(new_end, str):
                    raise ValueError
                new_start, new_end = validate_date_range(new_start, new_end)
            except (ValueError, TypeError, json.JSONDecodeError):
                return error_response("validation_error", "Некорректные даты.", rid, 400)

            source = get_entry(user_id, entry_id)
            if source is None:
                return _entry_id_not_found_response(rid)

            draft = tour_draft_from_body(
                {
                    "title": source["title"],
                    "company": source.get("company") or "",
                    "location": source.get("location") or "",
                    "startDate": new_start,
                    "endDate": new_end,
                    "useTime": bool(source.get("start_time") and source.get("end_time")),
                    "startTime": source.get("start_time"),
                    "endTime": source.get("end_time"),
                    "status": source.get("status"),
                    "payment": source.get("payment"),
                    "income": source.get("income") or 0,
                    "note": source.get("note") or "",
                }
            )
            conflict = check_entry_conflicts(user_id, draft)
            if conflict and conflict.get("block"):
                code, message, details = conflict_to_error(conflict)
                return error_response(code, message, rid, 409, details)
            if conflict and conflict.get("warn") and not data.get("ack_date_warning"):
                code, message, details = conflict_to_error(conflict)
                return error_response(code, message, rid, 409, details)

            copied = copy_tour_entry(user_id, entry_id, new_start, new_end)
            if copied is None:
                return _entry_id_not_found_response(rid)
            return success_response(entry_to_api(copied), rid, status=201)

        return await _idempotent(request, user_id, endpoint, body_bytes, build)

    async def patch_day_locations_handler(request: web.Request) -> web.Response:
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        request["request_id"] = rid
        entry_id, entry_failure = _resolve_entry_id(request, rid)
        if entry_failure is not None:
            return entry_failure
        body_bytes = await request.read()
        endpoint = f"PATCH /app/v1/entries/{entry_id}/day-locations"

        async def build():
            if get_entry(user_id, entry_id) is None:
                return _entry_id_not_found_response(rid)
            try:
                data = json.loads(body_bytes or b"{}")
                locations = data.get("locations")
                normalized = normalize_day_locations(locations)
            except (ValueError, TypeError, json.JSONDecodeError):
                return error_response(
                    "validation_error",
                    "Некорректный формат locations.",
                    rid,
                    400,
                )

            updated = update_day_locations(user_id, entry_id, normalized)
            if updated is None:
                return _entry_id_not_found_response(rid)
            return success_response(entry_to_api(updated), rid)

        return await _idempotent(request, user_id, endpoint, body_bytes, build)

    app.router.add_get("/app/v1/entries", list_entries_handler)
    app.router.add_get("/app/v1/entries/{entry_id}", get_entry_handler)
    app.router.add_post("/app/v1/tours", create_tour_handler)
    app.router.add_patch("/app/v1/entries/{entry_id}", update_entry_handler)
    app.router.add_post("/app/v1/day-offs", create_day_off_handler)
    app.router.add_delete("/app/v1/entries/{entry_id}", delete_entry_handler)
    app.router.add_post("/app/v1/entries/{entry_id}/copy", copy_entry_handler)
    app.router.add_patch(
        "/app/v1/entries/{entry_id}/day-locations",
        patch_day_locations_handler,
    )
