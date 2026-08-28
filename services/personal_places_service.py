from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import sqlite3
from typing import Callable
from uuid import uuid4

from database.queries import (
    create_personal_place,
    deactivate_personal_place,
    get_personal_place,
    list_personal_places,
    update_personal_place,
)


_PLACE_ID_RE = re.compile(r"place_[0-9a-f]{32}")


class PersonalPlaceValidationError(ValueError):
    pass


class PersonalPlaceConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class PersonalPlace:
    public_id: str
    user_id: int
    name: str
    category: str | None
    general_location: str | None
    landmark: str | None
    note: str | None
    status: str
    created_at: str
    updated_at: str


def _validate_user_id(user_id: int) -> int:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise PersonalPlaceValidationError("Invalid personal place owner")
    return user_id


def _required_text(value: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise PersonalPlaceValidationError("Invalid personal place data")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise PersonalPlaceValidationError("Invalid personal place data")
    return normalized


def _optional_text(value: str | None, *, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PersonalPlaceValidationError("Invalid personal place data")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise PersonalPlaceValidationError("Invalid personal place data")
    return normalized


def _public_id(value: str) -> str:
    if not isinstance(value, str) or _PLACE_ID_RE.fullmatch(value) is None:
        raise PersonalPlaceValidationError("Invalid personal place identifier")
    return value


def _utc_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise PersonalPlaceValidationError("Invalid personal place timestamp")
    offset = value.utcoffset()
    if offset is None:
        raise PersonalPlaceValidationError("Invalid personal place timestamp")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _from_row(row: dict) -> PersonalPlace:
    return PersonalPlace(**row)


class PersonalPlacesService:
    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (lambda: f"place_{uuid4().hex}")

    def create(
        self,
        *,
        user_id: int,
        name: str,
        category: str | None = None,
        general_location: str | None = None,
        landmark: str | None = None,
        note: str | None = None,
    ) -> PersonalPlace:
        owner = _validate_user_id(user_id)
        public_id = _public_id(self._id_factory())
        timestamp = _utc_timestamp(self._clock())
        values = self._validated_fields(
            name=name,
            category=category,
            general_location=general_location,
            landmark=landmark,
            note=note,
        )
        try:
            create_personal_place(
                public_id=public_id,
                user_id=owner,
                timestamp=timestamp,
                **values,
            )
        except sqlite3.IntegrityError as exc:
            raise PersonalPlaceConflictError(
                "Personal place could not be created"
            ) from exc
        result = get_personal_place(owner, public_id)
        if result is None:
            raise PersonalPlaceConflictError("Personal place could not be created")
        return _from_row(result)

    def get(self, *, user_id: int, public_id: str) -> PersonalPlace | None:
        row = get_personal_place(
            _validate_user_id(user_id),
            _public_id(public_id),
        )
        return _from_row(row) if row else None

    def list(
        self,
        *,
        user_id: int,
        include_inactive: bool = False,
    ) -> list[PersonalPlace]:
        if not isinstance(include_inactive, bool):
            raise PersonalPlaceValidationError("Invalid personal place filter")
        return [
            _from_row(row)
            for row in list_personal_places(
                _validate_user_id(user_id),
                include_inactive=include_inactive,
            )
        ]

    def update(
        self,
        *,
        user_id: int,
        public_id: str,
        name: str,
        category: str | None = None,
        general_location: str | None = None,
        landmark: str | None = None,
        note: str | None = None,
    ) -> PersonalPlace | None:
        owner = _validate_user_id(user_id)
        identifier = _public_id(public_id)
        values = self._validated_fields(
            name=name,
            category=category,
            general_location=general_location,
            landmark=landmark,
            note=note,
        )
        changed = update_personal_place(
            user_id=owner,
            public_id=identifier,
            timestamp=_utc_timestamp(self._clock()),
            **values,
        )
        if not changed:
            return None
        row = get_personal_place(owner, identifier)
        return _from_row(row) if row else None

    def deactivate(self, *, user_id: int, public_id: str) -> bool:
        return deactivate_personal_place(
            _validate_user_id(user_id),
            _public_id(public_id),
            _utc_timestamp(self._clock()),
        )

    @staticmethod
    def _validated_fields(
        *,
        name: str,
        category: str | None,
        general_location: str | None,
        landmark: str | None,
        note: str | None,
    ) -> dict:
        return {
            "name": _required_text(name, maximum=100),
            "category": _optional_text(category, maximum=100),
            "general_location": _optional_text(
                general_location,
                maximum=200,
            ),
            "landmark": _optional_text(landmark, maximum=200),
            "note": _optional_text(note, maximum=500),
        }

