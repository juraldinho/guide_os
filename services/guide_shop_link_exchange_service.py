from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets

from database.queries import (
    create_guide_shop_link_exchange_atomic,
    get_guide_shop_link_exchange_evidence_scoped,
    get_guide_shop_link_exchange_scoped,
    transition_guide_shop_link_exchange,
)
from utils.guide_os_identity import validate_guide_os_id


GUIDE_SHOP_LINK_AUDIENCE = "guideshop-link"
GUIDE_SHOP_LINK_SERVICE_SUBJECT = "guideshop:link-service"
CONFIRMATION_WINDOW = timedelta(minutes=10)
_OPAQUE_ID = re.compile(r"(?![0-9]+\Z)[A-Za-z0-9._:-]{8,128}\Z")


class LinkExchangeError(Exception):
    pass


class LinkExchangeTokenError(LinkExchangeError):
    pass


class LinkExchangeNotFoundError(LinkExchangeError):
    pass


class InvalidLinkExchangeTransitionError(LinkExchangeError):
    pass


class EvidenceNotReadyError(LinkExchangeError):
    pass


@dataclass(frozen=True)
class LinkExchange:
    link_exchange_id: str
    guide_os_id: str
    status: str
    token_expires_at: datetime
    exchange_expires_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class LinkLifecycleEvidence:
    link_exchange_id: str
    guide_os_id: str
    status: str
    evidence_ref: str
    occurred_at: datetime


class GuideShopLinkExchangeService:
    def __init__(self, *, clock=None, random_bytes=secrets.token_bytes) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._random_bytes = random_bytes

    def _now(self) -> datetime:
        try:
            value = self._clock()
            valid = (
                isinstance(value, datetime)
                and value.tzinfo is not None
                and value.utcoffset() == timedelta(0)
            )
        except Exception:
            valid = False
        if not valid:
            raise LinkExchangeError("Link exchange operation failed")
        return value

    @staticmethod
    def _scope(service_subject, guide_membership_ref) -> tuple[str, str]:
        if service_subject != GUIDE_SHOP_LINK_SERVICE_SUBJECT:
            raise LinkExchangeError("Link exchange operation failed")
        if (
            not isinstance(guide_membership_ref, str)
            or _OPAQUE_ID.fullmatch(guide_membership_ref) is None
        ):
            raise LinkExchangeError("Link exchange operation failed")
        return service_subject, guide_membership_ref

    def _opaque(self, prefix: str) -> str:
        try:
            value = self._random_bytes(16)
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if not isinstance(value, bytes) or len(value) != 16:
            raise LinkExchangeError("Link exchange operation failed")
        encoded = value.hex()
        if prefix == "evd_":
            encoded = ":".join(
                encoded[offset:offset + 8]
                for offset in range(0, len(encoded), 8)
            )
        return prefix + encoded

    @staticmethod
    def _exchange(row: dict) -> LinkExchange:
        try:
            identity = validate_guide_os_id(row["guide_os_id"])
            return LinkExchange(
                link_exchange_id=row["link_exchange_id"],
                guide_os_id=identity,
                status=row["status"],
                token_expires_at=datetime.fromisoformat(row["token_expires_at"]),
                exchange_expires_at=datetime.fromisoformat(
                    row["exchange_expires_at"]
                ),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None

    def create(self, raw_link_token, audience, guide_membership_ref,
               service_subject=GUIDE_SHOP_LINK_SERVICE_SUBJECT) -> LinkExchange:
        self._scope(service_subject, guide_membership_ref)
        if (
            not isinstance(raw_link_token, str)
            or not 24 <= len(raw_link_token) <= 256
            or re.fullmatch(r"[A-Za-z0-9._~-]+", raw_link_token) is None
        ):
            raise LinkExchangeTokenError("Link exchange token rejected")
        now = self._now()
        try:
            result, row = create_guide_shop_link_exchange_atomic(
                token_hash=hashlib.sha256(raw_link_token.encode()).hexdigest(),
                audience=audience,
                link_exchange_id=self._opaque("lex_"),
                service_subject=service_subject,
                guide_membership_ref=guide_membership_ref,
                transitioned_at=now.isoformat(),
                exchange_expires_at=(now + CONFIRMATION_WINDOW).isoformat(),
            )
        except LinkExchangeError:
            raise
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if result != "created" or row is None:
            raise LinkExchangeTokenError("Link exchange token rejected")
        return self._exchange(row)

    def _load(self, link_exchange_id, service_subject, guide_membership_ref):
        self._scope(service_subject, guide_membership_ref)
        if not isinstance(link_exchange_id, str) or _OPAQUE_ID.fullmatch(link_exchange_id) is None:
            raise LinkExchangeNotFoundError("Link exchange not found")
        try:
            row = get_guide_shop_link_exchange_scoped(
                link_exchange_id, service_subject, guide_membership_ref
            )
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if row is None:
            raise LinkExchangeNotFoundError("Link exchange not found")
        return row

    def get_status(self, link_exchange_id, guide_membership_ref,
                   service_subject=GUIDE_SHOP_LINK_SERVICE_SUBJECT) -> LinkExchange:
        row = self._load(link_exchange_id, service_subject, guide_membership_ref)
        now = self._now()
        try:
            expired = now >= datetime.fromisoformat(row["exchange_expires_at"])
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if row["status"] == "awaiting_guide_confirmation" and expired:
            try:
                result, current = transition_guide_shop_link_exchange(
                    link_exchange_id=link_exchange_id,
                    service_subject=service_subject,
                    guide_membership_ref=guide_membership_ref,
                    expected_status="awaiting_guide_confirmation",
                    new_status="expired",
                    transitioned_at=now.isoformat(),
                    evidence_ref=None,
                )
            except Exception:
                raise LinkExchangeError("Link exchange operation failed") from None
            if result == "transitioned":
                row = current
            else:
                row = self._load(link_exchange_id, service_subject, guide_membership_ref)
        return self._exchange(row)

    def transition(self, link_exchange_id, guide_membership_ref, new_status,
                   service_subject=GUIDE_SHOP_LINK_SERVICE_SUBJECT) -> LinkExchange:
        row = self._load(link_exchange_id, service_subject, guide_membership_ref)
        now = self._now()
        current = row["status"]
        allowed = {
            ("awaiting_guide_confirmation", "active"),
            ("awaiting_guide_confirmation", "conflict"),
            ("awaiting_guide_confirmation", "expired"),
            ("active", "revoked"),
        }
        if (current, new_status) not in allowed:
            raise InvalidLinkExchangeTransitionError("Invalid link exchange transition")
        try:
            expired = now >= datetime.fromisoformat(row["exchange_expires_at"])
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if current == "awaiting_guide_confirmation" and expired:
            new_status = "expired"
        evidence_ref = self._opaque("evd_") if new_status in {"active", "revoked", "conflict"} else None
        try:
            result, updated = transition_guide_shop_link_exchange(
                link_exchange_id=link_exchange_id,
                service_subject=service_subject,
                guide_membership_ref=guide_membership_ref,
                expected_status=current,
                new_status=new_status,
                transitioned_at=now.isoformat(),
                evidence_ref=evidence_ref,
            )
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if result != "transitioned" or updated is None:
            raise InvalidLinkExchangeTransitionError("Invalid link exchange transition")
        return self._exchange(updated)

    def get_evidence(self, link_exchange_id, guide_membership_ref,
                     service_subject=GUIDE_SHOP_LINK_SERVICE_SUBJECT) -> LinkLifecycleEvidence:
        status = self.get_status(link_exchange_id, guide_membership_ref, service_subject)
        if status.status not in {"active", "revoked", "conflict"}:
            raise EvidenceNotReadyError("Lifecycle evidence is not ready")
        try:
            row = get_guide_shop_link_exchange_evidence_scoped(
                link_exchange_id, service_subject, guide_membership_ref
            )
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if row is None:
            raise EvidenceNotReadyError("Lifecycle evidence is not ready")
        try:
            return LinkLifecycleEvidence(
                link_exchange_id=row["link_exchange_id"],
                guide_os_id=validate_guide_os_id(row["guide_os_id"]),
                status=row["status"],
                evidence_ref=row["evidence_ref"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
            )
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
