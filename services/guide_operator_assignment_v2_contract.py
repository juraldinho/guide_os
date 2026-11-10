"""Strict, additive assignment v2 contract. No database or transport side effects."""

import json
import re
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.guide_operator_assignment_service import AssignmentValidationError

SCHEMA = "assignment.working_package.v2"
ROLES = {"main_guide", "accompanying_guide", "local_guide", "meet_and_greet", "other"}
OFFER = "assignment.offered.v2"
VERSION = "assignment.version.published.v2"
MAX_BODY = 256 * 1024


def fail(field):
    raise AssignmentValidationError(f"Invalid v2 {field}.")


def keys(value, names, field):
    if type(value) is not dict or set(value) != set(names.split()):
        fail(field)
    return value


def text(value, field, limit=None, *, nullable=False):
    if value is None and nullable:
        return
    if (
        type(value) is not str
        or (not nullable and not value.strip())
        or (limit and len(value) > limit)
    ):
        fail(field)


def integer(value, field, minimum=1, maximum=None, *, nullable=False):
    if value is None and nullable:
        return
    if (
        type(value) is not int
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        fail(field)


def uuid(value, field):
    try:
        parsed = UUID(value) if type(value) is str else None
    except ValueError:
        fail(field)
    if parsed is None or parsed.version != 4 or str(parsed) != value:
        fail(field)


def day(value, field):
    try:
        parsed = date.fromisoformat(value) if type(value) is str else None
    except ValueError:
        fail(field)
    if parsed is None or parsed.isoformat() != value:
        fail(field)


def timestamp(value, field, *, nullable=False):
    if value is None and nullable:
        return
    try:
        parsed = datetime.fromisoformat(value) if type(value) is str else None
    except ValueError:
        fail(field)
    if parsed is None or "T" not in value or parsed.utcoffset() != timedelta(0):
        fail(field)


def array(value, field, maximum, minimum=0):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        fail(field)


def optional_texts(obj, fields, limit=None):
    for field in fields.split():
        text(obj[field], field, limit, nullable=True)


def validate_package(package):
    p = keys(
        package,
        "schema_version company_id source_tour_revision tour assignment days drivers contacts group_summary working_conditions remuneration",
        "package keys",
    )
    if p["schema_version"] != SCHEMA or p["remuneration"] is not None:
        fail("schema or unsupported remuneration")
    uuid(p["company_id"], "company_id")
    integer(p["source_tour_revision"], "source_tour_revision")
    tour = keys(
        p["tour"],
        "id reference title start_date end_date timezone city_or_route language tourist_count customer_or_agency",
        "tour keys",
    )
    uuid(tour["id"], "tour.id")
    text(tour["title"], "tour.title", 240)
    text(tour["timezone"], "tour.timezone", 80)
    try:
        ZoneInfo(tour["timezone"])
    except (ValueError, ZoneInfoNotFoundError):
        fail("tour.timezone")
    for field, limit in (
        ("reference", 80),
        ("city_or_route", 500),
        ("language", 80),
        ("customer_or_agency", 240),
    ):
        text(tour[field], f"tour.{field}", limit, nullable=True)
    integer(tour["tourist_count"], "tour.tourist_count", 0, 10000, nullable=True)
    a = keys(
        p["assignment"],
        "id guide_os_id role start_date end_date recipient_instructions",
        "assignment keys",
    )
    uuid(a["id"], "assignment.id")
    uuid(a["guide_os_id"], "assignment.guide_os_id")
    if type(a["role"]) is not str or a["role"] not in ROLES:
        fail("role")
    optional_texts(a, "recipient_instructions", 4000)
    for obj in (tour, a):
        for field in ("start_date", "end_date"):
            day(obj[field], field)
        if obj["start_date"] > obj["end_date"]:
            fail("date order")
    array(p["days"], "days", 366, 1)
    identities, dates = [], []
    for d in p["days"]:
        keys(d, "tour_day_id date title city_or_route instructions events", "day keys")
        uuid(d["tour_day_id"], "tour_day_id")
        day(d["date"], "day.date")
        if not tour["start_date"] <= d["date"] <= tour["end_date"]:
            fail("day outside tour")
        identities.append(d["tour_day_id"])
        dates.append(d["date"])
        optional_texts(d, "title", 240)
        optional_texts(d, "city_or_route", 500)
        optional_texts(d, "instructions", 4000)
        array(d["events"], "events", 100)
        for e in d["events"]:
            keys(
                e,
                "start_time end_time event_type title place description important_instruction",
                "event keys",
            )
            for field in ("start_time", "end_time"):
                if e[field] is not None and (
                    type(e[field]) is not str
                    or re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", e[field]) is None
                ):
                    fail(field)
            if (
                e["start_time"] is not None
                and e["end_time"] is not None
                and e["start_time"] >= e["end_time"]
            ):
                fail("event times")
            if type(e["event_type"]) is not str or e["event_type"] not in {
                "meeting",
                "excursion",
                "visit",
                "transfer",
                "train",
                "flight",
                "meal",
                "free_time",
                "other",
            }:
                fail("event_type")
            text(e["title"], "event.title", 240)
            optional_texts(e, "place", 300)
            optional_texts(e, "description")
            optional_texts(e, "important_instruction", 4000)
    if (
        len(set(identities)) != len(identities)
        or len(set(dates)) != len(dates)
        or list(zip(dates, identities)) != sorted(zip(dates, identities))
    ):
        fail("duplicate or noncanonical days")
    if (a["start_date"], a["end_date"]) != (dates[0], dates[-1]):
        fail("assignment min/max")
    for section in ("drivers", "contacts"):
        array(p[section], section, 100)
        for item in p[section]:
            names = (
                "day_ids name phone city_or_route instructions information_status"
                if section == "drivers"
                else "name role phone instructions day_ids"
            )
            keys(item, names, f"{section} keys")
            array(item["day_ids"], "day_ids", 366, 1)
            for value in item["day_ids"]:
                uuid(value, "day_ids")
            if len(set(item["day_ids"])) != len(item["day_ids"]) or not set(
                item["day_ids"]
            ) <= set(identities):
                fail("day_ids membership")
            optional_texts(item, "instructions", 4000)
            required = (
                section == "contacts" or item["information_status"] == "confirmed"
            )
            text(item["name"], "name", 160, nullable=not required)
            text(item["phone"], "phone", 40, nullable=not required)
            if section == "drivers":
                optional_texts(item, "city_or_route", 500)
                if type(item["information_status"]) is not str or item[
                    "information_status"
                ] not in {"pending", "confirmed"}:
                    fail("information_status")
            elif type(item["role"]) is not str or item["role"] not in {
                "responsible_operator",
                "coordinator",
                "director",
                "emergency",
                "other",
            }:
                fail("contact.role")
    if p["group_summary"] is not None:
        g = keys(
            p["group_summary"],
            "name_or_code tourist_count recipient_information",
            "group_summary keys",
        )
        optional_texts(g, "name_or_code", 120)
        optional_texts(g, "recipient_information", 4000)
        integer(g["tourist_count"], "group tourist_count", 0, 10000, nullable=True)
    if p["working_conditions"] is not None:
        fields = "allowance_text meals_text entrance_tickets_text transport_text additional_instructions"
        w = keys(p["working_conditions"], fields, "working_conditions keys")
        optional_texts(w, fields, 4000)
    return p


def validate_event(envelope, *, assignment_id):
    """Validate a parsed event, preserving all values for canonical idempotency hashing."""
    keys(envelope, "event_id event_type occurred_at payload", "envelope keys")
    try:
        encoded = json.dumps(
            envelope, allow_nan=False, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    except (ValueError, TypeError, RecursionError, UnicodeError):
        fail("JSON")
    if len(encoded) > MAX_BODY:
        fail("body limit")
    uuid(envelope["event_id"], "event_id")
    timestamp(envelope["occurred_at"], "occurred_at")
    uuid(assignment_id, "path assignment_id")
    kind = envelope["event_type"]
    if type(kind) is not str or kind not in {OFFER, VERSION}:
        fail("event_type")
    fields = (
        "assignment_id guide_os_id company_id company_name guide_connection_id role start_date end_date response_deadline operator_message version_number working_package offered_at"
        if kind == OFFER
        else "assignment_id guide_os_id version_number previous_active_version_number severity working_package change_summary published_at"
    )
    p = keys(envelope["payload"], fields, "payload keys")
    uuid(p["assignment_id"], "assignment_id")
    uuid(p["guide_os_id"], "guide_os_id")
    if assignment_id != p["assignment_id"]:
        fail("path identity")
    package = validate_package(p["working_package"])
    a = package["assignment"]
    if a["id"] != assignment_id or a["guide_os_id"] != p["guide_os_id"]:
        fail("package identity")
    integer(p["version_number"], "version_number", 1 if kind == OFFER else 2)
    if kind == OFFER:
        uuid(p["company_id"], "company_id")
        uuid(p["guide_connection_id"], "guide_connection_id")
        text(p["company_name"], "company_name")
        timestamp(p["offered_at"], "offered_at")
        timestamp(p["response_deadline"], "response_deadline", nullable=True)
        optional_texts(p, "operator_message", 4000)
        if (
            p["version_number"] != 1
            or p["company_id"] != package["company_id"]
            or any(p[k] != a[k] for k in ("role", "start_date", "end_date"))
        ):
            fail("offer binding")
    else:
        integer(p["previous_active_version_number"], "previous_active_version_number")
        if type(p["severity"]) is not str or p["severity"] not in {
            "ordinary",
            "critical",
        }:
            fail("severity")
        timestamp(p["published_at"], "published_at")
        array(p["change_summary"], "change_summary", MAX_BODY, 1)
        for change in p["change_summary"]:
            keys(
                change, "code severity path change before after", "change_summary keys"
            )
            text(change["code"], "change code")
            text(change["path"], "change path")
            if (
                type(change["severity"]) is not str
                or change["severity"] not in {"ordinary", "critical", "uncertain"}
                or type(change["change"]) is not str
                or change["change"] not in {"added", "removed", "updated"}
            ):
                fail("change summary values")
            if p["severity"] == "ordinary" and change["severity"] != "ordinary":
                fail("ordinary summary severity")
    return envelope
