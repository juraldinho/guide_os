from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StrictStr, model_validator

from database.queries import (
    consume_guide_shop_navigation_token,
    create_guide_shop_navigation_token,
    get_guide_shop_navigation_token,
    revoke_guide_shop_navigation_tokens,
)
from services.guide_shop_contracts import PointsStatus


NAVIGATION_TOKEN_TTL = timedelta(hours=24)


class NavigationError(Exception):
    pass


class NavigationTokenUnknownError(NavigationError):
    pass


class NavigationTokenExpiredError(NavigationError):
    pass


class NavigationTokenConsumedError(NavigationError):
    pass


class NavigationTokenRevokedError(NavigationError):
    pass


class NavigationTokenAccessDeniedError(NavigationError):
    pass


class NavigationRouteInvalidError(NavigationError):
    pass


def _non_empty(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be empty")
    return value


NonEmptyString = Annotated[StrictStr, AfterValidator(_non_empty)]


class GuideShopRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal[
        "home",
        "companies",
        "visits",
        "visit_detail",
        "sales",
        "sale_detail",
        "points",
        "points_detail",
        "history",
    ]
    object_id: NonEmptyString | None = None
    cursor: NonEmptyString | None = None
    points_status: PointsStatus | None = None

    @model_validator(mode="after")
    def validate_route_fields(self) -> "GuideShopRoute":
        detail_kinds = {"visit_detail", "sale_detail", "points_detail"}
        cursor_kinds = {"visits", "sales", "points", "history"}

        if self.kind in detail_kinds:
            if self.object_id is None:
                raise ValueError("detail route requires object_id")
        elif "object_id" in self.model_fields_set:
            raise ValueError("non-detail route must not contain object_id")

        if self.kind not in cursor_kinds and "cursor" in self.model_fields_set:
            raise ValueError("route kind must not contain cursor")

        if self.kind != "points" and "points_status" in self.model_fields_set:
            raise ValueError("route kind must not contain points_status")
        return self


@dataclass(frozen=True)
class NavigationToken:
    raw_token: str
    expires_at: datetime


def _validate_user_id(telegram_user_id: int) -> None:
    if (
        isinstance(telegram_user_id, bool)
        or not isinstance(telegram_user_id, int)
        or telegram_user_id <= 0
    ):
        raise ValueError("telegram_user_id must be a positive integer")


def _resolve_now(now: datetime | None) -> datetime:
    value = datetime.now(timezone.utc) if now is None else now
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("now must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _route_from_row(row: dict) -> GuideShopRoute:
    payload = {
        "kind": row["route_kind"],
        "object_id": row["object_id"],
        "cursor": row["cursor"],
        "points_status": row["points_status"],
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    try:
        return GuideShopRoute.model_validate(payload)
    except Exception as exc:
        raise NavigationRouteInvalidError(
            "Stored navigation route is invalid"
        ) from exc


def _raise_for_unavailable(row: dict, telegram_user_id: int, now: datetime) -> None:
    if row["telegram_user_id"] != telegram_user_id:
        raise NavigationTokenAccessDeniedError("Navigation token access denied")
    if row["status"] == "consumed":
        raise NavigationTokenConsumedError("Navigation token was already consumed")
    if row["status"] == "revoked":
        raise NavigationTokenRevokedError("Navigation token was revoked")
    try:
        expires_at = datetime.fromisoformat(row["expires_at"])
    except (TypeError, ValueError) as exc:
        raise NavigationRouteInvalidError(
            "Stored navigation route is invalid"
        ) from exc
    if expires_at.tzinfo is None:
        raise NavigationRouteInvalidError("Stored navigation route is invalid")
    if now >= expires_at:
        raise NavigationTokenExpiredError("Navigation token has expired")


def create_navigation_token(
    telegram_user_id: int,
    route: GuideShopRoute,
    *,
    now: datetime | None = None,
) -> NavigationToken:
    _validate_user_id(telegram_user_id)
    if not isinstance(route, GuideShopRoute):
        raise NavigationRouteInvalidError("Validated GuideShopRoute required")

    created_at = _resolve_now(now)
    expires_at = created_at + NAVIGATION_TOKEN_TTL
    raw_token = f"gs_{secrets.token_urlsafe(24)}"
    create_guide_shop_navigation_token(
        token_hash=_token_hash(raw_token),
        telegram_user_id=telegram_user_id,
        route_kind=route.kind,
        object_id=route.object_id,
        cursor=route.cursor,
        points_status=(route.points_status.value if route.points_status else None),
        created_at=created_at.isoformat(),
        expires_at=expires_at.isoformat(),
    )
    return NavigationToken(raw_token=raw_token, expires_at=expires_at)


def resolve_navigation_token(
    raw_token: str,
    telegram_user_id: int,
    *,
    now: datetime | None = None,
) -> GuideShopRoute:
    _validate_user_id(telegram_user_id)
    resolved_at = _resolve_now(now)
    if not isinstance(raw_token, str) or not raw_token:
        raise NavigationTokenUnknownError("Navigation token is unknown")

    token_hash = _token_hash(raw_token)
    row = get_guide_shop_navigation_token(token_hash)
    if row is None:
        raise NavigationTokenUnknownError("Navigation token is unknown")
    _raise_for_unavailable(row, telegram_user_id, resolved_at)
    route = _route_from_row(row)

    consumed = consume_guide_shop_navigation_token(
        token_hash, telegram_user_id, resolved_at.isoformat()
    )
    if not consumed:
        current = get_guide_shop_navigation_token(token_hash)
        if current is None:
            raise NavigationTokenUnknownError("Navigation token is unknown")
        _raise_for_unavailable(current, telegram_user_id, resolved_at)
        raise NavigationTokenUnknownError("Navigation token is unavailable")
    return route


def revoke_navigation_tokens(
    telegram_user_id: int,
    *,
    now: datetime | None = None,
) -> int:
    _validate_user_id(telegram_user_id)
    revoked_at = _resolve_now(now)
    return revoke_guide_shop_navigation_tokens(
        telegram_user_id, revoked_at.isoformat()
    )
