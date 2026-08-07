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
    StrictInt,
    StrictStr,
    model_validator,
)


def _non_empty(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be empty")
    return value


def _decimal_string(value: str) -> str:
    if re.fullmatch(r"-?\d+\.\d{2}", value) is None:
        raise ValueError("value must use plain decimal notation with two digits")
    return value


def _non_negative_decimal_string(value: str) -> str:
    if re.fullmatch(r"\d+\.\d{2}", value) is None:
        raise ValueError("value must be a non-negative decimal string")
    return value


def _utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO 8601 string")
    if not (value.endswith("Z") or value.endswith("+00:00")):
        raise ValueError("timestamp must use UTC")
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError as exc:
        raise ValueError("timestamp must be ISO 8601") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("timestamp must use UTC")
    return parsed.astimezone(timezone.utc)


NonEmptyString = Annotated[StrictStr, AfterValidator(_non_empty)]
DecimalString = Annotated[StrictStr, AfterValidator(_decimal_string)]
NonNegativeDecimalString = Annotated[
    StrictStr, AfterValidator(_non_negative_decimal_string)
]
UTCTimestamp = Annotated[datetime, BeforeValidator(_utc_timestamp)]


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisitStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SaleStatus(str, Enum):
    ACTIVE = "active"
    VOIDED = "voided"


class PointsStatus(str, Enum):
    PENDING = "pending"
    CREDITED = "credited"
    REVERSED = "reversed"


class APIErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNAUTHENTICATED = "unauthenticated"
    LINK_NOT_ACTIVE = "link_not_active"
    NOT_FOUND = "not_found"
    LINK_CONFLICT = "link_conflict"
    RATE_LIMITED = "rate_limited"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


class CompanyDTO(StrictDTO):
    company_id: NonEmptyString
    display_name: NonEmptyString
    status: NonEmptyString


class VisitDTO(StrictDTO):
    visit_id: NonEmptyString
    company_id: NonEmptyString
    guide_os_id: NonEmptyString
    visit_at: UTCTimestamp
    status: VisitStatus
    tourist_count: Annotated[StrictInt, Field(ge=0)]
    created_at: UTCTimestamp
    updated_at: UTCTimestamp


class SaleDTO(StrictDTO):
    sale_id: NonEmptyString
    visit_id: NonEmptyString
    amount_usd: NonNegativeDecimalString
    currency: Literal["USD"]
    status: SaleStatus
    category_id: NonEmptyString
    category_name: NonEmptyString
    created_at: UTCTimestamp
    updated_at: UTCTimestamp
    voided_at: UTCTimestamp | None = None

    @model_validator(mode="after")
    def validate_voided_at(self) -> "SaleDTO":
        if self.status == SaleStatus.VOIDED and self.voided_at is None:
            raise ValueError("voided sales require voided_at")
        if self.status == SaleStatus.ACTIVE and "voided_at" in self.model_fields_set:
            raise ValueError("active sales must not include voided_at")
        return self


class PointsTransactionDTO(StrictDTO):
    points_transaction_id: NonEmptyString
    sale_id: NonEmptyString | None = None
    visit_id: NonEmptyString | None = None
    amount: DecimalString
    status: PointsStatus
    reason: NonEmptyString | None = None
    calculated_at: UTCTimestamp
    credited_at: UTCTimestamp | None = None
    updated_at: UTCTimestamp

    @model_validator(mode="after")
    def validate_references_and_credit(self) -> "PointsTransactionDTO":
        if self.sale_id is None and self.visit_id is None:
            raise ValueError("sale_id or visit_id is required")
        if self.status == PointsStatus.CREDITED and self.credited_at is None:
            raise ValueError("credited points require credited_at")
        if (
            self.status == PointsStatus.PENDING
            and "credited_at" in self.model_fields_set
        ):
            raise ValueError("pending points must not include credited_at")
        return self


class PageDTO(StrictDTO):
    next_cursor: NonEmptyString | None = None


T = TypeVar("T")


class APIListResponseDTO(StrictDTO, Generic[T]):
    schema_version: Literal["1.0"]
    request_id: NonEmptyString
    data: list[T]
    page: PageDTO


class APIDetailResponseDTO(StrictDTO, Generic[T]):
    schema_version: Literal["1.0"]
    request_id: NonEmptyString
    data: T


class APIErrorDTO(StrictDTO):
    schema_version: Literal["1.0"]
    request_id: NonEmptyString
    code: APIErrorCode
    message: NonEmptyString
    retry_after_seconds: Annotated[StrictInt, Field(gt=0)] | None = None

    @model_validator(mode="after")
    def validate_retry_after(self) -> "APIErrorDTO":
        if self.code == APIErrorCode.RATE_LIMITED:
            if self.retry_after_seconds is None:
                raise ValueError("rate_limited errors require retry_after_seconds")
        elif "retry_after_seconds" in self.model_fields_set:
            raise ValueError("retry_after_seconds is only valid for rate_limited")
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
    amount_usd: NonNegativeDecimalString
    currency: Literal["USD"]


class PointsRecalculatedDataDTO(StrictDTO):
    points_transaction_id: NonEmptyString
    old_amount: DecimalString
    new_amount: DecimalString
    status: PointsStatus


class PointsCreditedDataDTO(StrictDTO):
    points_transaction_id: NonEmptyString
    amount: DecimalString
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
    schema_version: Literal["1.0"]

    @model_validator(mode="after")
    def validate_event_shape(self) -> "EventEnvelopeDTO":
        expected = {
            "visit.created.v1": ("visit", VisitCreatedDataDTO),
            "sale.created.v1": ("sale", SaleCreatedDataDTO),
            "points.recalculated.v1": (
                "points_transaction",
                PointsRecalculatedDataDTO,
            ),
            "points.credited.v1": (
                "points_transaction",
                PointsCreditedDataDTO,
            ),
        }
        subject_type, data_type = expected[self.event_type]
        if self.subject.type != subject_type:
            raise ValueError("event subject does not match event_type")
        if not isinstance(self.data, data_type):
            raise ValueError("event data does not match event_type")
        return self
