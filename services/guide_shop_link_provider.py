from datetime import timezone
import json
import re
import secrets

from aiohttp import web

from services.guide_shop_inbound_auth import (
    GuideShopAuthenticationError,
    GuideShopInboundJWTVerifier,
)
from services.guide_shop_link_exchange_service import (
    EvidenceNotReadyError,
    GUIDE_SHOP_LINK_AUDIENCE,
    GUIDE_SHOP_LINK_SERVICE_SUBJECT,
    GuideShopLinkExchangeService,
    InvalidLinkExchangeTransitionError,
    LinkExchangeError,
    LinkExchangeNotFoundError,
    LinkExchangeTokenError,
)
from services.guide_shop_settings import (
    GuideShopInboundJWTSettings,
    GuideShopLinkProviderSettings,
)


MAX_REQUEST_BODY_BYTES = 4096
_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{8,128}\Z")
_OPAQUE_ID = re.compile(r"(?![0-9]+\Z)[A-Za-z0-9._:-]{8,128}\Z")
_RAW_TOKEN = re.compile(r"[A-Za-z0-9._~-]{24,256}\Z")


def _utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _exchange_payload(exchange, request_id):
    return {
        "schema_version": "1.0.0",
        "request_id": request_id,
        "link_exchange_id": exchange.link_exchange_id,
        "guide_os_id": exchange.guide_os_id,
        "status": exchange.status,
        "token_expires_at": _utc(exchange.token_expires_at),
        "exchange_expires_at": _utc(exchange.exchange_expires_at),
        "created_at": _utc(exchange.created_at),
        "updated_at": _utc(exchange.updated_at),
    }


def _error(request_id, status, code, message, *, retry_after=None):
    payload = {
        "schema_version": "1.0.0",
        "request_id": request_id,
        "code": code,
        "message": message,
    }
    headers = {}
    if retry_after is not None:
        payload["retry_after_seconds"] = retry_after
        headers["Retry-After"] = str(retry_after)
    return web.json_response(payload, status=status, headers=headers)


def create_guide_shop_link_provider_app(
    verifier: GuideShopInboundJWTVerifier,
    service: GuideShopLinkExchangeService,
    *,
    random_bytes=secrets.token_bytes,
):
    app = web.Application(client_max_size=MAX_REQUEST_BODY_BYTES)

    def request_id(request):
        values = request.headers.getall("X-Correlation-ID", [])
        if not values:
            value = random_bytes(16)
            if not isinstance(value, bytes) or len(value) != 16:
                raise ValueError
            return "req_" + value.hex()
        if len(values) != 1 or _REQUEST_ID.fullmatch(values[0]) is None:
            raise ValueError
        return values[0]

    def authenticate(request, scope):
        values = request.headers.getall("Authorization", [])
        if len(values) != 1 or not values[0].startswith("Bearer "):
            raise GuideShopAuthenticationError
        token = values[0][7:]
        if not token or token != token.strip() or any(c.isspace() for c in token):
            raise GuideShopAuthenticationError
        return verifier.verify(token, scope)

    async def prepare(request, scope):
        try:
            rid = request_id(request)
        except Exception:
            rid = "req_invalid_request"
            return rid, None, _error(rid, 400, "invalid_request", "Invalid request")
        try:
            principal = authenticate(request, scope)
        except GuideShopAuthenticationError:
            return rid, None, _error(rid, 401, "unauthenticated", "Authentication failed")
        return rid, principal, None

    async def create_exchange(request):
        rid, principal, failure = await prepare(request, "guideshop:link:exchange")
        if failure is not None:
            return failure
        if request.content_type != "application/json":
            return _error(rid, 400, "invalid_request", "Invalid request")
        try:
            body = await request.read()
            if len(body) > MAX_REQUEST_BODY_BYTES:
                raise ValueError
            def unique_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError
                    result[key] = value
                return result
            data = json.loads(body, object_pairs_hook=unique_object)
            if (
                not isinstance(data, dict)
                or set(data) != {"schema_version", "raw_link_token", "audience", "guide_membership_ref"}
                or data["schema_version"] != "1.0.0"
                or data["audience"] != GUIDE_SHOP_LINK_AUDIENCE
                or not isinstance(data["raw_link_token"], str)
                or _RAW_TOKEN.fullmatch(data["raw_link_token"]) is None
                or not isinstance(data["guide_membership_ref"], str)
                or _OPAQUE_ID.fullmatch(data["guide_membership_ref"]) is None
            ):
                raise ValueError
            exchange = service.create(
                data["raw_link_token"],
                data["audience"],
                data["guide_membership_ref"],
                principal.subject,
            )
            return web.json_response(_exchange_payload(exchange, rid), status=201)
        except (ValueError, UnicodeError, json.JSONDecodeError, web.HTTPRequestEntityTooLarge):
            return _error(rid, 400, "invalid_request", "Invalid request")
        except LinkExchangeTokenError:
            return _error(rid, 422, "invalid_transition", "Link exchange is unavailable")
        except LinkExchangeError:
            return _error(rid, 503, "temporarily_unavailable", "Service unavailable", retry_after=10)

    async def status(request):
        rid, principal, failure = await prepare(request, "guideshop:link:status")
        if failure is not None:
            return failure
        try:
            exchange = service.get_status_for_service(
                request.match_info["link_exchange_id"], principal.subject
            )
            return web.json_response(_exchange_payload(exchange, rid))
        except LinkExchangeNotFoundError:
            return _error(rid, 404, "not_found", "Entity not found")
        except LinkExchangeError:
            return _error(rid, 503, "temporarily_unavailable", "Service unavailable", retry_after=10)

    async def evidence(request):
        rid, principal, failure = await prepare(request, "guideshop:link:status")
        if failure is not None:
            return failure
        try:
            item = service.get_evidence_for_service(
                request.match_info["link_exchange_id"], principal.subject
            )
            return web.json_response({
                "schema_version": "1.1.0",
                "request_id": rid,
                "link_exchange_id": item.link_exchange_id,
                "guide_os_id": item.guide_os_id,
                "status": item.status,
                "evidence_ref": item.evidence_ref,
                "occurred_at": _utc(item.occurred_at),
            })
        except LinkExchangeNotFoundError:
            return _error(rid, 404, "not_found", "Entity not found")
        except EvidenceNotReadyError:
            return _error(
                rid, 422, "invalid_transition",
                "Lifecycle evidence is not available for the current exchange status."
            )
        except (InvalidLinkExchangeTransitionError, LinkExchangeError):
            return _error(rid, 503, "temporarily_unavailable", "Service unavailable", retry_after=10)

    async def health(_request):
        return web.json_response({"schema_version": "1.0.0", "status": "ok"})

    app.router.add_get("/health", health, allow_head=False)
    app.router.add_post("/integration/v1/link-exchanges", create_exchange)
    app.router.add_get(
        "/integration/v1/link-exchanges/{link_exchange_id}", status, allow_head=False
    )
    app.router.add_get(
        "/integration/v1/link-exchanges/{link_exchange_id}/evidence",
        evidence,
        allow_head=False,
    )
    return app


async def start_guide_shop_link_provider(values=None, *, clock=None):
    runtime = GuideShopLinkProviderSettings.from_env(values)
    if not runtime.enabled:
        return None
    settings = GuideShopInboundJWTSettings.from_env(values)
    verifier = GuideShopInboundJWTVerifier(settings, clock=clock)
    service = GuideShopLinkExchangeService(clock=clock)
    runner = web.AppRunner(create_guide_shop_link_provider_app(verifier, service))
    try:
        await runner.setup()
        site = web.TCPSite(runner, runtime.host, runtime.port)
        await site.start()
        return runner
    except BaseException:
        await runner.cleanup()
        raise
