from aiohttp import web

from services.daily_tips_service import get_daily_tip, get_daily_tips, set_daily_tip
from web_api.errors import error_response, success_response
from web_api.routes.session import _auth_or_error


def register_daily_tips_routes(app: web.Application) -> None:
    async def read(request):
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        try:
            if 'date' in request.match_info:
                result = get_daily_tip(user_id, request.match_info['date'])
            else:
                query = request.rel_url.query
                if set(query) != {'from', 'to'} or any(len(query.getall(k)) != 1 for k in query):
                    raise ValueError('Укажите корректные from и to.')
                result = {'tips': get_daily_tips(user_id, query['from'], query['to'])}
        except ValueError as exc:
            return error_response('validation_error', str(exc), rid, 400)
        return success_response(result, rid)

    async def write(request):
        rid, user_id, failure = _auth_or_error(request)
        if failure is not None:
            return failure
        try:
            data = await request.json()
        except Exception:
            return error_response('validation_error', 'Некорректный JSON.', rid, 400)
        try:
            if not isinstance(data, dict) or set(data) != {'amount'}:
                raise ValueError('Укажите только сумму чаевых amount.')
            result = set_daily_tip(user_id, request.match_info['date'], data['amount'])
        except ValueError as exc:
            return error_response('validation_error', str(exc), rid, 400)
        return success_response(result, rid)

    app.router.add_get('/app/v1/daily-tips', read)
    app.router.add_get('/app/v1/daily-tips/{date}', read)
    app.router.add_put('/app/v1/daily-tips/{date}', write)
