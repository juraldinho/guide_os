from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
import sqlite3

from database.queries import (
    create_guide_shop_link_exchange_atomic,
    create_or_activate_guide_profile_link_exchange,
    get_guide_shop_link_exchange_evidence_for_guide,
    get_guide_shop_link_exchange_evidence_scoped,
    get_guide_shop_link_exchange_for_guide,
    get_guide_shop_link_exchange_for_service,
    get_guide_shop_link_exchange_scoped,
    transition_guide_shop_link_exchange,
    transition_guide_shop_link_exchange_for_guide,
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


class LinkExchangeConflictError(LinkExchangeError):
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

    def create_active_for_verified_profile(
        self, guide_os_id, audience, guide_membership_ref,
        service_subject=GUIDE_SHOP_LINK_SERVICE_SUBJECT,
    ) -> tuple[LinkExchange, bool]:
        """Create and activate one exchange for an Owner/Manager verified
        profile code. Returns (exchange, created) where created is False for
        an idempotent retry of the exact same binding."""
        self._scope(service_subject, guide_membership_ref)
        if audience != GUIDE_SHOP_LINK_AUDIENCE:
            raise LinkExchangeTokenError("Link exchange token rejected")
        try:
            identity = validate_guide_os_id(guide_os_id)
        except Exception:
            raise LinkExchangeNotFoundError("Link exchange not found") from None
        now = self._now()
        # Internal single-use token: only its hash ever leaves this scope.
        token_hash = hashlib.sha256(
            secrets.token_urlsafe(32).encode()
        ).hexdigest()
        try:
            result, row = create_or_activate_guide_profile_link_exchange(
                guide_os_id=identity,
                audience=audience,
                token_hash=token_hash,
                link_exchange_id=self._opaque("lex_"),
                evidence_ref=self._opaque("evd_"),
                service_subject=service_subject,
                guide_membership_ref=guide_membership_ref,
                now_iso=now.isoformat(),
                token_expires_at=(now + CONFIRMATION_WINDOW).isoformat(),
                exchange_expires_at=(now + CONFIRMATION_WINDOW).isoformat(),
            )
        except LinkExchangeError:
            raise
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if result == "conflict":
            raise LinkExchangeConflictError("Link exchange conflict")
        if result in {"existing", "created"} and row is not None:
            return self._exchange(row), result == "created"
        raise LinkExchangeError("Link exchange operation failed")

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
            ("awaiting_guide_confirmation", "revoked"),
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

    def _membership_for_service(self, link_exchange_id, service_subject):
        if service_subject != GUIDE_SHOP_LINK_SERVICE_SUBJECT:
            raise LinkExchangeNotFoundError("Link exchange not found")
        if not isinstance(link_exchange_id, str) or _OPAQUE_ID.fullmatch(link_exchange_id) is None:
            raise LinkExchangeNotFoundError("Link exchange not found")
        try:
            row = get_guide_shop_link_exchange_for_service(
                link_exchange_id, service_subject
            )
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if row is None:
            raise LinkExchangeNotFoundError("Link exchange not found")
        return row["guide_membership_ref"]

    def get_status_for_service(self, link_exchange_id, service_subject):
        membership = self._membership_for_service(link_exchange_id, service_subject)
        return self.get_status(link_exchange_id, membership, service_subject)

    def get_evidence_for_service(self, link_exchange_id, service_subject):
        membership = self._membership_for_service(link_exchange_id, service_subject)
        return self.get_evidence(link_exchange_id, membership, service_subject)

    def _load_for_guide(self, link_exchange_id, guide_os_id):
        try:
            identity = validate_guide_os_id(guide_os_id)
        except Exception:
            raise LinkExchangeNotFoundError("Link exchange not found") from None
        if not isinstance(link_exchange_id, str) or _OPAQUE_ID.fullmatch(link_exchange_id) is None:
            raise LinkExchangeNotFoundError("Link exchange not found")
        try:
            row = get_guide_shop_link_exchange_for_guide(link_exchange_id, identity)
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if row is None:
            raise LinkExchangeNotFoundError("Link exchange not found")
        return row, identity

    def _expire_awaiting_for_guide(self, row, identity, now):
        if row["status"] != "awaiting_guide_confirmation":
            return row
        try:
            expired = now >= datetime.fromisoformat(row["exchange_expires_at"])
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if not expired:
            return row
        try:
            result, current = transition_guide_shop_link_exchange_for_guide(
                link_exchange_id=row["link_exchange_id"],
                guide_os_id=identity,
                expected_status="awaiting_guide_confirmation",
                new_status="expired",
                transitioned_at=now.isoformat(),
                evidence_ref=None,
            )
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if result == "transitioned":
            return current
        reloaded = get_guide_shop_link_exchange_for_guide(
            row["link_exchange_id"], identity
        )
        if reloaded is None:
            raise LinkExchangeNotFoundError("Link exchange not found")
        return reloaded

    def confirm_for_guide(self, link_exchange_id, guide_os_id) -> LinkExchange:
        row, identity = self._load_for_guide(link_exchange_id, guide_os_id)
        now = self._now()
        row = self._expire_awaiting_for_guide(row, identity, now)
        return self._guide_transition(
            row=row,
            identity=identity,
            new_status="active",
            allowed_from={"awaiting_guide_confirmation"},
            now=now,
        )

    def revoke_for_guide(self, link_exchange_id, guide_os_id) -> LinkExchange:
        row, identity = self._load_for_guide(link_exchange_id, guide_os_id)
        now = self._now()
        row = self._expire_awaiting_for_guide(row, identity, now)
        return self._guide_transition(
            row=row,
            identity=identity,
            new_status="revoked",
            allowed_from={"awaiting_guide_confirmation", "active"},
            now=now,
        )

    def _guide_transition(self, *, row, identity, new_status, allowed_from, now):
        current = row["status"]
        if current == new_status:
            return self._exchange(row)
        if current not in allowed_from:
            raise InvalidLinkExchangeTransitionError("Invalid link exchange transition")
        evidence_ref = (
            self._opaque("evd_")
            if new_status in {"active", "revoked", "conflict"}
            else None
        )
        try:
            result, updated = transition_guide_shop_link_exchange_for_guide(
                link_exchange_id=row["link_exchange_id"],
                guide_os_id=identity,
                expected_status=current,
                new_status=new_status,
                transitioned_at=now.isoformat(),
                evidence_ref=evidence_ref,
            )
        except sqlite3.IntegrityError:
            raise InvalidLinkExchangeTransitionError(
                "Invalid link exchange transition"
            ) from None
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if result == "identical" and updated is not None:
            return self._exchange(updated)
        if result != "transitioned" or updated is None:
            raise InvalidLinkExchangeTransitionError("Invalid link exchange transition")
        return self._exchange(updated)

    def get_evidence_for_guide(self, link_exchange_id, guide_os_id) -> LinkLifecycleEvidence:
        row, identity = self._load_for_guide(link_exchange_id, guide_os_id)
        now = self._now()
        row = self._expire_awaiting_for_guide(row, identity, now)
        if row["status"] not in {"active", "revoked", "conflict"}:
            raise EvidenceNotReadyError("Lifecycle evidence is not ready")
        try:
            evidence = get_guide_shop_link_exchange_evidence_for_guide(
                row["link_exchange_id"], identity
            )
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
        if evidence is None:
            raise EvidenceNotReadyError("Lifecycle evidence is not ready")
        try:
            return LinkLifecycleEvidence(
                link_exchange_id=evidence["link_exchange_id"],
                guide_os_id=validate_guide_os_id(evidence["guide_os_id"]),
                status=evidence["status"],
                evidence_ref=evidence["evidence_ref"],
                occurred_at=datetime.fromisoformat(evidence["occurred_at"]),
            )
        except Exception:
            raise LinkExchangeError("Link exchange operation failed") from None
