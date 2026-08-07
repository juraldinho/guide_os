from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from database.queries import (
    consume_guide_shop_link_request,
    create_guide_shop_link_request,
    get_guide_os_id,
    get_guide_shop_link_request,
    revoke_guide_shop_link_requests,
)


GUIDE_SHOP_LINK_AUDIENCE = "guideshop-link"
LINK_REQUEST_TTL = timedelta(minutes=10)


class GuideShopLinkError(Exception):
    pass


class UnknownUserError(GuideShopLinkError):
    pass


class UnknownTokenError(GuideShopLinkError):
    pass


class ExpiredTokenError(GuideShopLinkError):
    pass


class ConsumedTokenError(GuideShopLinkError):
    pass


class RevokedTokenError(GuideShopLinkError):
    pass


class WrongAudienceError(GuideShopLinkError):
    pass


@dataclass(frozen=True)
class LinkRequest:
    token: str
    expires_at: datetime


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_valid_request(raw_token: str, audience: str) -> dict:
    if audience != GUIDE_SHOP_LINK_AUDIENCE:
        raise WrongAudienceError("Unexpected token audience")

    request = get_guide_shop_link_request(_token_hash(raw_token))
    if request is None:
        raise UnknownTokenError("Unknown link token")
    if request["audience"] != audience:
        raise WrongAudienceError("Unexpected token audience")
    if request["status"] == "consumed":
        raise ConsumedTokenError("Link token was already consumed")
    if request["status"] == "revoked":
        raise RevokedTokenError("Link token was revoked")

    expires_at = datetime.fromisoformat(request["expires_at"])
    if _utc_now() >= expires_at:
        raise ExpiredTokenError("Link token has expired")
    return request


def create_link_request(user_id: int) -> LinkRequest:
    guide_os_id = get_guide_os_id(user_id)
    if not guide_os_id:
        raise UnknownUserError("User has no Guide OS identity")

    raw_token = secrets.token_urlsafe(32)
    now = _utc_now()
    expires_at = now + LINK_REQUEST_TTL
    create_guide_shop_link_request(
        guide_os_id=guide_os_id,
        token_hash=_token_hash(raw_token),
        audience=GUIDE_SHOP_LINK_AUDIENCE,
        created_at=now.isoformat(),
        expires_at=expires_at.isoformat(),
    )
    return LinkRequest(token=raw_token, expires_at=expires_at)


def validate_link_token(raw_token: str, audience: str) -> str:
    request = _load_valid_request(raw_token, audience)
    return request["guide_os_id"]


def consume_link_token(raw_token: str, audience: str) -> str:
    request = _load_valid_request(raw_token, audience)
    consumed_at = _utc_now()
    consumed = consume_guide_shop_link_request(
        request["id"], consumed_at.isoformat()
    )
    if not consumed:
        current = get_guide_shop_link_request(_token_hash(raw_token))
        if current and current["status"] == "consumed":
            raise ConsumedTokenError("Link token was already consumed")
        if current and current["status"] == "revoked":
            raise RevokedTokenError("Link token was revoked")
        if current and consumed_at >= datetime.fromisoformat(current["expires_at"]):
            raise ExpiredTokenError("Link token has expired")
        raise UnknownTokenError("Link token is no longer available")
    return request["guide_os_id"]


def revoke_link_requests(user_id: int) -> int:
    guide_os_id = get_guide_os_id(user_id)
    if not guide_os_id:
        raise UnknownUserError("User has no Guide OS identity")
    return revoke_guide_shop_link_requests(
        guide_os_id,
        GUIDE_SHOP_LINK_AUDIENCE,
        _utc_now().isoformat(),
    )
