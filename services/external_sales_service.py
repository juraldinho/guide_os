from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import sqlite3
from typing import Callable
from uuid import uuid4

from database.queries import (
    create_personal_place_entry,
    deactivate_personal_place_entry,
    get_personal_place_entry,
    list_personal_place_entries,
    update_personal_place_entry,
)
from services.personal_places_service import (
    PersonalPlaceValidationError,
    _optional_text,
    _public_id as _place_public_id,
    _utc_timestamp,
    _validate_user_id,
)


_ENTRY_ID_RE = re.compile(r"entry_[0-9a-f]{32}")

# Active ISO 4217 currency and fund codes. Values are stored explicitly per
# self-reported entry and never shared with official GuideShop points.
ISO_4217_CODES = frozenset(
    """
    AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD
    BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUC CUP
    CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP
    GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR
    ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD
    LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN
    NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD
    RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL
    THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VED VES VND
    VUV WST XAF XCD XOF XPF YER ZAR ZMW ZWG
    """.split()
)


class ExternalSaleValidationError(ValueError):
    pass


class ExternalSaleConflictError(RuntimeError):
    pass


class ExternalSalePlaceNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class ExternalSale:
    public_id: str
    user_id: int
    personal_place_id: str
    occurred_at: str
    purchase_amount_minor: int | None
    received_income_minor: int | None
    received_points: int | None
    currency: str | None
    note: str | None
    status: str
    created_at: str
    updated_at: str


def _entry_public_id(value: str) -> str:
    if not isinstance(value, str) or _ENTRY_ID_RE.fullmatch(value) is None:
        raise ExternalSaleValidationError("Invalid external sale identifier")
    return value


def _optional_non_negative(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExternalSaleValidationError("Invalid external sale value")
    return value


def _optional_positive(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ExternalSaleValidationError("Invalid received points")
    return value


def _currency(
    value: str | None,
    *,
    has_monetary_value: bool,
) -> str | None:
    if not has_monetary_value:
        if value is not None:
            raise ExternalSaleValidationError("Unexpected external sale currency")
        return None
    if not isinstance(value, str):
        raise ExternalSaleValidationError("External sale currency is required")
    normalized = value.strip().upper()
    if normalized not in ISO_4217_CODES:
        raise ExternalSaleValidationError("Invalid external sale currency")
    return normalized


def _from_row(row: dict) -> ExternalSale:
    return ExternalSale(**row)


def _external_timestamp(value: datetime) -> str:
    try:
        return _utc_timestamp(value)
    except PersonalPlaceValidationError as exc:
        raise ExternalSaleValidationError("Invalid external sale timestamp") from exc


class ExternalSalesService:
    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (lambda: f"entry_{uuid4().hex}")

    def create(
        self,
        *,
        user_id: int,
        personal_place_id: str,
        occurred_at: datetime,
        purchase_amount_minor: int | None = None,
        received_income_minor: int | None = None,
        received_points: int | None = None,
        currency: str | None = None,
        note: str | None = None,
    ) -> ExternalSale:
        owner = self._owner(user_id)
        identifier = _entry_public_id(self._id_factory())
        place_id = self._place_id(personal_place_id)
        now = self._clock()
        values = self._validated_values(
            occurred_at=occurred_at,
            now=now,
            purchase_amount_minor=purchase_amount_minor,
            received_income_minor=received_income_minor,
            received_points=received_points,
            currency=currency,
            note=note,
        )
        try:
            created = create_personal_place_entry(
                public_id=identifier,
                user_id=owner,
                personal_place_id=place_id,
                timestamp=self._timestamp(now),
                **values,
            )
        except sqlite3.IntegrityError as exc:
            raise ExternalSaleConflictError(
                "External sale could not be created"
            ) from exc
        if not created:
            raise ExternalSalePlaceNotFoundError("Personal place not found")
        result = get_personal_place_entry(owner, identifier)
        if result is None:
            raise ExternalSaleConflictError("External sale could not be created")
        return _from_row(result)

    def get(self, *, user_id: int, public_id: str) -> ExternalSale | None:
        row = get_personal_place_entry(
            self._owner(user_id),
            _entry_public_id(public_id),
        )
        return _from_row(row) if row else None

    def list(
        self,
        *,
        user_id: int,
        personal_place_id: str | None = None,
        include_inactive: bool = False,
    ) -> list[ExternalSale]:
        if not isinstance(include_inactive, bool):
            raise ExternalSaleValidationError("Invalid external sale filter")
        place_id = (
            self._place_id(personal_place_id)
            if personal_place_id is not None
            else None
        )
        return [
            _from_row(row)
            for row in list_personal_place_entries(
                self._owner(user_id),
                personal_place_id=place_id,
                include_inactive=include_inactive,
            )
        ]

    def update(
        self,
        *,
        user_id: int,
        public_id: str,
        occurred_at: datetime,
        purchase_amount_minor: int | None = None,
        received_income_minor: int | None = None,
        received_points: int | None = None,
        currency: str | None = None,
        note: str | None = None,
    ) -> ExternalSale | None:
        owner = self._owner(user_id)
        identifier = _entry_public_id(public_id)
        now = self._clock()
        values = self._validated_values(
            occurred_at=occurred_at,
            now=now,
            purchase_amount_minor=purchase_amount_minor,
            received_income_minor=received_income_minor,
            received_points=received_points,
            currency=currency,
            note=note,
        )
        changed = update_personal_place_entry(
            user_id=owner,
            public_id=identifier,
            timestamp=self._timestamp(now),
            **values,
        )
        if not changed:
            return None
        row = get_personal_place_entry(owner, identifier)
        return _from_row(row) if row else None

    def deactivate(self, *, user_id: int, public_id: str) -> bool:
        return deactivate_personal_place_entry(
            self._owner(user_id),
            _entry_public_id(public_id),
            self._timestamp(self._clock()),
        )

    @staticmethod
    def _validated_values(
        *,
        occurred_at: datetime,
        now: datetime,
        purchase_amount_minor: int | None,
        received_income_minor: int | None,
        received_points: int | None,
        currency: str | None,
        note: str | None,
    ) -> dict:
        purchase = _optional_non_negative(purchase_amount_minor)
        income = _optional_non_negative(received_income_minor)
        points = _optional_positive(received_points)
        occurred = _external_timestamp(occurred_at)
        _external_timestamp(now)
        if occurred_at.astimezone(timezone.utc) > now.astimezone(timezone.utc):
            raise ExternalSaleValidationError("External sale is not completed")
        if not any((purchase or 0, income or 0, points or 0)):
            raise ExternalSaleValidationError("External sale outcome is required")
        try:
            normalized_note = _optional_text(note, maximum=500)
        except PersonalPlaceValidationError as exc:
            raise ExternalSaleValidationError("Invalid external sale note") from exc
        return {
            "occurred_at": occurred,
            "purchase_amount_minor": purchase,
            "received_income_minor": income,
            "received_points": points,
            "currency": _currency(
                currency,
                has_monetary_value=purchase is not None or income is not None,
            ),
            "note": normalized_note,
        }

    @staticmethod
    def _owner(user_id: int) -> int:
        try:
            return _validate_user_id(user_id)
        except PersonalPlaceValidationError as exc:
            raise ExternalSaleValidationError("Invalid external sale owner") from exc

    @staticmethod
    def _place_id(value: str) -> str:
        try:
            return _place_public_id(value)
        except PersonalPlaceValidationError as exc:
            raise ExternalSaleValidationError(
                "Invalid personal place identifier"
            ) from exc

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return _external_timestamp(value)
