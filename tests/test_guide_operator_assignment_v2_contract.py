"""Strict v2 DTO fixtures; intentionally independent of HTTP and live configuration."""

import copy
from uuid import uuid4

import pytest

from services.guide_operator_assignment_service import AssignmentValidationError
from services.guide_operator_assignment_v2_contract import (
    OFFER,
    VERSION,
    validate_event,
)

NOW = "2026-11-07T10:00:00+00:00"


def offered(*, guide=None, company=None, connection=None, tour=None, role="main_guide"):
    identity = str(uuid4())
    package = {
        "schema_version": "assignment.working_package.v2",
        "company_id": company or str(uuid4()),
        "source_tour_revision": 1,
        "tour": {
            "id": tour or str(uuid4()),
            "reference": None,
            "title": "Silk Road",
            "start_date": "2026-11-10",
            "end_date": "2026-11-14",
            "timezone": "Asia/Samarkand",
            "city_or_route": "Samarkand",
            "language": "ru",
            "tourist_count": 10,
            "customer_or_agency": None,
        },
        "assignment": {
            "id": identity,
            "guide_os_id": guide or str(uuid4()),
            "role": role,
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            "recipient_instructions": None,
        },
        "days": [
            {
                "tour_day_id": str(uuid4()),
                "date": value,
                "title": None,
                "city_or_route": "Samarkand",
                "instructions": None,
                "events": [],
            }
            for value in ("2026-11-10", "2026-11-12")
        ],
        "drivers": [],
        "contacts": [],
        "group_summary": None,
        "working_conditions": None,
        "remuneration": None,
    }
    payload = {
        "assignment_id": identity,
        "guide_os_id": package["assignment"]["guide_os_id"],
        "company_id": package["company_id"],
        "company_name": "Operator",
        "guide_connection_id": connection or str(uuid4()),
        "response_deadline": None,
        "operator_message": None,
        "version_number": 1,
        "working_package": package,
        "offered_at": NOW,
    }
    payload.update(
        {k: package["assignment"][k] for k in ("role", "start_date", "end_date")}
    )
    return {
        "event_id": str(uuid4()),
        "event_type": OFFER,
        "occurred_at": NOW,
        "payload": payload,
    }


def published(offer, *, number=2, previous=1, severity="ordinary"):
    package = copy.deepcopy(offer["payload"]["working_package"])
    package["working_conditions"] = dict.fromkeys(
        (
            "allowance_text",
            "meals_text",
            "entrance_tickets_text",
            "transport_text",
            "additional_instructions",
        )
    )
    package["working_conditions"]["additional_instructions"] = f"Updated {number}"
    package["source_tour_revision"] = number
    return {
        "event_id": str(uuid4()),
        "event_type": VERSION,
        "occurred_at": NOW,
        "payload": {
            "assignment_id": offer["payload"]["assignment_id"],
            "guide_os_id": offer["payload"]["guide_os_id"],
            "version_number": number,
            "previous_active_version_number": previous,
            "severity": severity,
            "working_package": package,
            "change_summary": [
                {
                    "code": "working_conditions",
                    "severity": severity,
                    "path": "working_conditions.additional_instructions",
                    "change": "updated",
                    "before": None,
                    "after": f"Updated {number}",
                }
            ],
            "published_at": NOW,
        },
    }


def check(event):
    return validate_event(
        event, assignment_id=event["payload"].get("assignment_id", str(uuid4()))
    )


def test_exact_valid_offer_and_version():
    event = offered()
    assert check(event) == event
    assert check(published(event))["event_type"] == VERSION
    p = event["payload"]["working_package"]
    ids = [d["tour_day_id"] for d in p["days"]]
    p["drivers"] = [
        {
            "day_ids": ids,
            "name": "Driver",
            "phone": "+998123",
            "city_or_route": None,
            "instructions": None,
            "information_status": "confirmed",
        }
    ]
    p["contacts"] = [
        {
            "day_ids": ids[:1],
            "name": "Contact",
            "role": "emergency",
            "phone": "123",
            "instructions": None,
        }
    ]
    p["group_summary"] = {
        "name_or_code": None,
        "tourist_count": 0,
        "recipient_information": None,
    }
    p["working_conditions"] = dict.fromkeys(
        (
            "allowance_text",
            "meals_text",
            "entrance_tickets_text",
            "transport_text",
            "additional_instructions",
        )
    )
    assert check(event) == event


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("payload",),
        ("payload", "working_package"),
        ("payload", "working_package", "tour"),
        ("payload", "working_package", "assignment"),
        ("payload", "working_package", "days", 0),
    ],
)
@pytest.mark.parametrize("change", ["extra", "missing"])
def test_exact_keys_at_every_level(path, change):
    event = offered()
    target = event
    for part in path:
        target = target[part]
    if change == "extra":
        target["private_comment"] = "must not pass"
    else:
        target.pop(next(iter(target)))
    with pytest.raises(AssignmentValidationError):
        check(event)


@pytest.mark.parametrize(
    "case",
    [
        "money",
        "bool_revision",
        "bool_version",
        "foreign_guide",
        "company",
        "assignment",
        "minmax",
        "outside",
        "duplicate_date",
        "duplicate_id",
        "unsorted",
        "unknown_role",
        "uuid_upper",
        "bad_date",
        "naive_time",
        "timezone",
        "too_many_days",
        "instructions",
        "foreign_driver_day",
        "duplicate_contact_day",
        "wrong_type",
        "nan",
        "body_bound",
    ],
)
def test_invalid_offer_has_no_coercion(case):
    event = offered()
    p = event["payload"]
    package = p["working_package"]
    if case == "money":
        package["remuneration"] = {"default_daily_usd": 0}
    elif case == "bool_revision":
        package["source_tour_revision"] = True
    elif case == "bool_version":
        p["version_number"] = True
    elif case == "foreign_guide":
        package["assignment"]["guide_os_id"] = str(uuid4())
    elif case == "company":
        package["company_id"] = str(uuid4())
    elif case == "assignment":
        package["assignment"]["id"] = str(uuid4())
    elif case == "minmax":
        package["assignment"]["end_date"] = "2026-11-11"
    elif case == "outside":
        package["tour"]["end_date"] = "2026-11-11"
    elif case == "duplicate_date":
        package["days"][1]["date"] = package["days"][0]["date"]
    elif case == "duplicate_id":
        package["days"][1]["tour_day_id"] = package["days"][0]["tour_day_id"]
    elif case == "unsorted":
        package["days"].reverse()
    elif case == "unknown_role":
        package["assignment"]["role"] = "boss"
    elif case == "uuid_upper":
        event["event_id"] = event["event_id"].upper()
    elif case == "bad_date":
        package["days"][0]["date"] = "2026-02-30"
    elif case == "naive_time":
        event["occurred_at"] = "2026-11-07T10:00:00"
    elif case == "timezone":
        package["tour"]["timezone"] = "Mars/Unknown"
    elif case == "too_many_days":
        package["days"] *= 184
    elif case == "instructions":
        package["days"][0]["instructions"] = "x" * 4001
    elif case in {"foreign_driver_day", "duplicate_contact_day"}:
        ids = (
            [str(uuid4())]
            if case == "foreign_driver_day"
            else [package["days"][0]["tour_day_id"]] * 2
        )
        package["contacts"] = [
            {
                "day_ids": ids,
                "name": "A",
                "role": "emergency",
                "phone": "123",
                "instructions": None,
            }
        ]
    elif case == "wrong_type":
        package["drivers"] = {}
    elif case == "nan":
        package["tour"]["tourist_count"] = float("nan")
    elif case == "body_bound":
        p["company_name"] = "x" * 262144
    with pytest.raises(AssignmentValidationError):
        check(event)


@pytest.mark.parametrize(
    "case",
    [
        "path",
        "event_type",
        "summary_extra",
        "summary_empty",
        "severity",
        "version",
        "summary_downgrade",
        "event_extra",
        "event_time",
        "event_kind",
    ],
)
def test_invalid_version_and_nested_event(case):
    event = published(offered())
    p = event["payload"]
    path = p["assignment_id"]
    if case == "path":
        path = str(uuid4())
    elif case == "event_type":
        event["event_type"] = "assignment.offered.v1"
    elif case == "summary_extra":
        p["change_summary"][0]["secret"] = 1
    elif case == "summary_empty":
        p["change_summary"] = []
    elif case == "severity":
        p["severity"] = []
    elif case == "version":
        p["version_number"] = "2"
    elif case == "summary_downgrade":
        p["change_summary"][0]["severity"] = "critical"
    else:
        e = {
            "start_time": "10:00",
            "end_time": "11:00",
            "event_type": "visit",
            "title": "A",
            "place": None,
            "description": None,
            "important_instruction": None,
        }
        if case == "event_extra":
            e["comment"] = "hidden"
        elif case == "event_time":
            e["end_time"] = "09:00"
        else:
            e["event_type"] = "hotel_booking"
        p["working_package"]["days"][0]["events"] = [e]
    with pytest.raises(AssignmentValidationError):
        validate_event(event, assignment_id=path)
