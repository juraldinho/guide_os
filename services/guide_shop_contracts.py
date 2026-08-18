from datetime import datetime, timezone
from enum import Enum
import re
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)


_OPAQUE_ID_PATTERN = re.compile(r"^(?![0-9]+$)[A-Za-z0-9._:-]+$")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
_CURSOR_PATTERN = re.compile(r"^[A-Za-z0-9._~=-]+$")
_AMOUNT_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.[0-9]{2}$")
_UNRESOLVED_CATEGORY = "Category unavailable"


def _non_empty(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be empty")
    return value


def _opaque_id(value: str) -> str:
    if not 8 <= len(value) <= 128 or _OPAQUE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid opaque id")
    return value


def _request_id(value: str) -> str:
    if not 8 <= len(value) <= 128 or _REQUEST_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid request id")
    return value


def _cursor(value: str) -> str:
    if not 8 <= len(value) <= 256 or _CURSOR_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid cursor")
    return value


def _amount_string(value: str) -> str:
    if _AMOUNT_PATTERN.fullmatch(value) is None:
        raise ValueError("value must be an exact decimal string with two digits")
    return value


def _bounded_name(value: str) -> str:
    if not 1 <= len(value) <= 128:
        raise ValueError("value length is invalid")
    return value


def _utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO 8601 string")
    if not value.endswith("Z") or "+00:00" in value:
        raise ValueError("timestamp must use UTC Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("timestamp must be ISO 8601") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("timestamp must use UTC")
    return parsed.astimezone(timezone.utc)


NonEmptyString = Annotated[StrictStr, AfterValidator(_non_empty)]
OpaqueId = Annotated[StrictStr, AfterValidator(_opaque_id)]
RequestId = Annotated[StrictStr, AfterValidator(_request_id)]
CursorString = Annotated[StrictStr, AfterValidator(_cursor)]
AmountUsd = Annotated[StrictStr, AfterValidator(_amount_string)]
AmountPts = Annotated[StrictStr, AfterValidator(_amount_string)]
BoundedName = Annotated[StrictStr, AfterValidator(_bounded_name)]
UTCTimestamp = Annotated[datetime, BeforeValidator(_utc_timestamp)]
SchemaVersion = Literal["1.0.0"]


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompanyStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class VisitStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CustomerPaymentStatus(str, Enum):
    UNPAID = "unpaid"
    PAID = "paid"


class SalePaymentMethod(str, Enum):
    CASH = "cash"
    CARD = "card"
    TRANSFER = "transfer"
    UNKNOWN = "unknown"


class SaleStatus(str, Enum):
    ACTIVE = "active"


class PointsStatus(str, Enum):
    PENDING = "pending"
    CREDITED = "credited"


class APIErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNAUTHENTICATED = "unauthenticated"
    LINK_NOT_ACTIVE = "link_not_active"
    NOT_FOUND = "not_found"
    LINK_CONFLICT = "link_conflict"
    INVALID_TRANSITION = "invalid_transition"
    RATE_LIMITED = "rate_limited"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


class CompanyDTO(StrictDTO):
    company_id: OpaqueId
    display_name: BoundedName
    status: CompanyStatus


class VisitDTO(StrictDTO):
    visit_id: OpaqueId
    company_id: OpaqueId
    guide_membership_id: OpaqueId
    visit_at: UTCTimestamp
    status: VisitStatus
    tourist_count: Annotated[StrictInt, Field(ge=0)]
    customer_payment_status: CustomerPaymentStatus
    customer_paid_at: UTCTimestamp | None = None
    created_at: UTCTimestamp
    updated_at: UTCTimestamp

    @model_validator(mode="after")
    def validate_customer_payment(self) -> "VisitDTO":
        if self.customer_payment_status == CustomerPaymentStatus.PAID:
            if self.customer_paid_at is None:
                raise ValueError("paid visits require customer_paid_at")
        elif (
            "customer_paid_at" in self.model_fields_set
            and self.customer_paid_at is not None
        ):
            raise ValueError("unpaid visits must not include customer_paid_at")
        return self


class SaleDTO(StrictDTO):
    sale_id: OpaqueId
    visit_id: OpaqueId
    company_id: OpaqueId
    amount: AmountUsd
    currency: Literal["USD"]
    status: SaleStatus
    payment_method: SalePaymentMethod
    comment: Annotated[StrictStr, Field(min_length=1, max_length=500)] | None = None
    category_id: OpaqueId | None
    category_name: BoundedName
    created_at: UTCTimestamp
    updated_at: UTCTimestamp

    @model_validator(mode="after")
    def validate_category(self) -> "SaleDTO":
        unresolved = self.category_name == _UNRESOLVED_CATEGORY
        if unresolved and self.category_id is not None:
            raise ValueError("unresolved category requires null category_id")
        if not unresolved and self.category_id is None:
            raise ValueError("resolved category requires category_id")
        return self


class PointsAccrualDTO(StrictDTO):
    points_accrual_id: OpaqueId
    company_id: OpaqueId
    visit_id: OpaqueId
    amount: AmountPts
    unit: Literal["PTS"]
    status: PointsStatus
    calculated_at: UTCTimestamp
    credited_at: UTCTimestamp | None = None
    updated_at: UTCTimestamp
    payout_id: OpaqueId | None = None

    @model_validator(mode="after")
    def validate_credit_and_payout(self) -> "PointsAccrualDTO":
        if self.status == PointsStatus.CREDITED:
            if self.credited_at is None or self.payout_id is None:
                raise ValueError("credited accruals require credited_at and payout_id")
        elif self.credited_at is not None or self.payout_id is not None:
            raise ValueError("pending accruals must not include credited_at or payout_id")
        return self


class PointsPayoutDTO(StrictDTO):
    payout_id: OpaqueId
    points_accrual_id: OpaqueId
    company_id: OpaqueId
    visit_id: OpaqueId
    amount: AmountPts
    unit: Literal["PTS"]
    paid_at: UTCTimestamp
    created_at: UTCTimestamp


class PageDTO(StrictDTO):
    next_cursor: CursorString | None = None
    has_more: StrictBool


T = TypeVar("T")


class APIListResponseDTO(StrictDTO, Generic[T]):
    schema_version: SchemaVersion
    request_id: RequestId
    data: list[T]
    page: PageDTO


class APIDetailResponseDTO(StrictDTO, Generic[T]):
    schema_version: SchemaVersion
    request_id: RequestId
    data: T


class APIErrorDTO(StrictDTO):
    schema_version: SchemaVersion
    request_id: RequestId
    code: APIErrorCode
    message: Annotated[StrictStr, Field(min_length=1, max_length=256)]
    retry_after_seconds: Annotated[StrictInt, Field(ge=1, le=120)] | None = None

    @model_validator(mode="after")
    def validate_retry_after(self) -> "APIErrorDTO":
        if self.code == APIErrorCode.RATE_LIMITED:
            if self.retry_after_seconds is None:
                raise ValueError("rate_limited errors require retry_after_seconds")
        elif self.code != APIErrorCode.TEMPORARILY_UNAVAILABLE:
            if "retry_after_seconds" in self.model_fields_set:
                raise ValueError("retry_after_seconds is only valid for retryable errors")
        return self


class EventSubjectDTO(StrictDTO):
    type: Literal["visit", "sale", "points_transaction"]
    id: NonEmptyString


class VisitCreatedDataDTO(StrictDTO):
    visit_id: NonEmptyString
    company_id: NonEmptyString


class SaleCreatedDataDTO(StrictDTO):
    sale_id: NonEmptyString
    visit_id: NonEmptyString
    amount_usd: AmountUsd
    currency: Literal["USD"]


class PointsRecalculatedDataDTO(StrictDTO):
    points_transaction_id: NonEmptyString
    old_amount: AmountPts
    new_amount: AmountPts
    status: PointsStatus


class PointsCreditedDataDTO(StrictDTO):
    points_transaction_id: NonEmptyString
    amount: AmountPts
    status: Literal["credited"]


EventDataDTO = (
    VisitCreatedDataDTO
    | SaleCreatedDataDTO
    | PointsRecalculatedDataDTO
    | PointsCreditedDataDTO
)


class EventEnvelopeDTO(StrictDTO):
    event_id: NonEmptyString
    event_type: Literal[
        "visit.created.v1",
        "sale.created.v1",
        "points.recalculated.v1",
        "points.credited.v1",
    ]
    occurred_at: UTCTimestamp
    producer: Literal["guideshop"]
    subject: EventSubjectDTO
    guide_os_id: NonEmptyString
    data: EventDataDTO
    schema_version: SchemaVersion

    @model_validator(mode="after")
    def validate_event_shape(self) -> "EventEnvelopeDTO":
        expected = {
            "visit.created.v1": ("visit", VisitCreatedDataDTO, "visit_id"),
            "sale.created.v1": ("sale", SaleCreatedDataDTO, "sale_id"),
            "points.recalculated.v1": (
                "points_transaction",
                PointsRecalculatedDataDTO,
                "points_transaction_id",
            ),
            "points.credited.v1": (
                "points_transaction",
                PointsCreditedDataDTO,
                "points_transaction_id",
            ),
        }
        subject_type, data_type, data_id_field = expected[self.event_type]
        if self.subject.type != subject_type:
            raise ValueError("event subject does not match event_type")
        if not isinstance(self.data, data_type):
            raise ValueError("event data does not match event_type")
        if self.subject.id != getattr(self.data, data_id_field):
            raise ValueError("event subject id does not match event data id")
        return self
