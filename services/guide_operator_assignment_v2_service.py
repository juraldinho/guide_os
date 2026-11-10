"""Default-off v2 intake domain adapter. No HTTP, sender, UI or repair activation."""

import json
from collections import Counter

from database.db import ensure_db_ready, run_write_with_retry
from services import guide_operator_assignment_service as domain
from services.guide_operator_assignment_v2_contract import (
    OFFER,
    uuid,
    validate_event,
    validate_package,
)
from services.guide_operator_notification_outbox import (
    insert_guide_operator_guide_notification,
)


class AssignmentV2ReceiveDisabled(domain.AssignmentNotActionableError):
    code = "assignment_v2_receive_disabled"


def _snapshot(conn, assignment_id, version):
    row = conn.execute(
        "SELECT * FROM guide_operator_assignment_versions WHERE assignment_id=? AND version_number=?",
        (assignment_id, version),
    ).fetchone()
    if row is None:
        raise domain.AssignmentValidationError("Missing immutable snapshot.")
    return domain._load_working_package_json(row["working_package_json"])


def _result(conn, assignment_id, *, replayed=False):
    row = conn.execute(
        "SELECT assignment_id,status,active_version_number,pending_critical_version_number "
        "FROM guide_operator_assignments WHERE assignment_id=?",
        (assignment_id,),
    ).fetchone()
    return {**dict(row), "replayed": replayed}


def _reserve_event(conn, event_id):
    # Incoming and local decisions share one identity namespace. A version ACK is
    # created only after this check, in the same write transaction as its inbox.
    for table, column in (
        ("guide_operator_offer_inbox", "event_id"),
        ("guide_operator_version_inbox", "event_id"),
        ("guide_operator_cancellation_inbox", "event_id"),
        ("guide_operator_assignment_lifecycle_inbox", "event_id"),
        ("guide_operator_outbox", "event_id"),
        ("guide_operator_daily_operation_inbox", "event_id"),
        ("guide_operator_assignment_versions", "source_event_id"),
    ):
        if conn.execute(
            f"SELECT 1 FROM {table} WHERE {column}=?", (event_id,)
        ).fetchone():
            raise domain.AssignmentConflictError("Event identity is already reserved.")


def _connection(conn, company_id, guide_os_id, connection_id):
    connection = conn.execute(
        "SELECT * FROM guide_operator_connections WHERE connection_id=?",
        (connection_id,),
    ).fetchone()
    if (
        connection is None
        or connection["status"] != "confirmed"
        or connection["company_id"] != company_id
        or connection["guide_os_id"] != guide_os_id
    ):
        raise domain.AssignmentForbiddenError(
            "A matching confirmed connection is required."
        )


def _effective_set(conn, assignment, package, user_id):
    """Intake cannot repair malformed or stray effective calendar state."""
    scope = domain._explicit_scope(assignment, package)
    links = domain._daily_links(conn, assignment["assignment_id"])
    ids = {
        r[0]
        for r in conn.execute(
            "SELECT id FROM tours WHERE source='guide_operator' AND note=?",
            (f"go_assignment:{assignment['assignment_id']}",),
        )
    }
    if ids != {r["projection_tour_id"] for r in links} or {
        (r["tour_day_id"], r["calendar_date"]) for r in links
    } != set(scope):
        raise domain.AssignmentValidationError(
            "Inconsistent effective daily set; repair is gated."
        )
    for link in links:
        row = conn.execute(
            "SELECT * FROM tours WHERE id=?", (link["projection_tour_id"],)
        ).fetchone()
        if (
            row is None
            or row["user_id"] != user_id
            or row["source"] != "guide_operator"
            or row["note"] != f"go_assignment:{assignment['assignment_id']}"
            or row["tour_group_id"]
            != f"{assignment['assignment_id']}:{link['tour_day_id']}"
            or row["entry_type"] != "tour"
            or row["status"] != "confirmed"
            or row["start_time"] is not None
            or row["end_time"] is not None
            or row["start_date"] != link["calendar_date"]
            or row["end_date"] != link["calendar_date"]
            or link["active_version_number"] != assignment["active_version_number"]
        ):
            raise domain.AssignmentValidationError("Inconsistent effective daily row.")
    return scope


def _ordinary_safe(assignment, previous, package):
    # The sender's severity is not authority to change obligations. Reuse the
    # established envelope classifier, plus stable IDs and conservative routes.
    if domain._ordinary_occupancy_violations(
        assignment=assignment, previous_package=previous, next_package=package
    ):
        raise domain.AssignmentValidationError("Ordinary change modifies occupancy.")
    if (
        previous["tour"] != package["tour"]
        or previous["assignment"] != package["assignment"]
        or [{k: v for k, v in d.items() if k != "events"} for d in previous["days"]]
        != [{k: v for k, v in d.items() if k != "events"} for d in package["days"]]
    ):
        raise domain.AssignmentValidationError(
            "Ordinary change needs critical confirmation."
        )
    for old, new in zip(previous["days"], package["days"], strict=True):

        def identities(events):
            return Counter(
                tuple(
                    e[k]
                    for k in (
                        "event_type",
                        "title",
                        "place",
                        "description",
                        "important_instruction",
                    )
                )
                for e in events
            )

        if identities(old["events"]) != identities(new["events"]):
            raise domain.AssignmentValidationError(
                "Unknown event content change needs confirmation."
            )


def receive_assignment_event_v2(envelope, *, assignment_id, receive_enabled=False):
    """Local adapter; only a future authenticated route may supply parsed wire data.

    Capability is explicit and default-off. Existing guide decisions remain usable
    independently of this flag. No replacement scope or calendar content is accepted
    by a decision operation.
    """
    if receive_enabled is not True:
        raise AssignmentV2ReceiveDisabled("Explicit-day intake capability is disabled.")
    # Detach caller-owned dictionaries before validation and the transaction.
    try:
        event = json.loads(json.dumps(envelope, allow_nan=False))
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise domain.AssignmentValidationError("Invalid v2 JSON.") from exc
    validate_event(event, assignment_id=assignment_id)
    payload = event["payload"]
    package = payload["working_package"]
    offer = event["event_type"] == OFFER
    digest = domain._canonical_hash(event)
    event_id = event["event_id"]
    guide = payload["guide_os_id"]
    table = "guide_operator_offer_inbox" if offer else "guide_operator_version_inbox"
    ensure_db_ready()

    def operation(conn):
        prior = conn.execute(
            f"SELECT * FROM {table} WHERE event_id=?", (event_id,)
        ).fetchone()
        if prior:
            if (
                prior["payload_hash"] != digest
                or prior["assignment_id"] != assignment_id
                or prior["guide_os_id"] != guide
            ):
                raise domain.AssignmentConflictError("Conflicting v2 event replay.")
            return _result(conn, assignment_id, replayed=True)
        _reserve_event(conn, event_id)
        user = conn.execute(
            "SELECT user_id FROM users WHERE guide_os_id=?", (guide,)
        ).fetchone()
        if user is None:
            raise domain.AssignmentNotFoundError("Guide was not found.")
        now = domain._utc_now()
        if offer:
            _connection(
                conn, payload["company_id"], guide, payload["guide_connection_id"]
            )
            if conn.execute(
                "SELECT 1 FROM guide_operator_assignments WHERE assignment_id=?",
                (assignment_id,),
            ).fetchone():
                raise domain.AssignmentConflictError(
                    "Assignment identity already exists."
                )
            conn.execute(
                "INSERT INTO guide_operator_assignments(assignment_id,guide_os_id,company_id,"
                "company_name,guide_connection_id,role,start_date,end_date,response_deadline,"
                "operator_message,status,offer_event_id,offered_at,projection_mode,operator_tour_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,'offered',?,?,'explicit_days',?)",
                tuple(
                    payload[k]
                    for k in (
                        "assignment_id",
                        "guide_os_id",
                        "company_id",
                        "company_name",
                        "guide_connection_id",
                        "role",
                        "start_date",
                        "end_date",
                        "response_deadline",
                        "operator_message",
                    )
                )
                + (event_id, payload["offered_at"], package["tour"]["id"]),
            )
            conn.execute(
                "INSERT INTO guide_operator_offer_inbox(event_id,assignment_id,guide_os_id,"
                "payload_hash,received_at,result_status) VALUES (?,?,?,?,?,'applied')",
                (event_id, assignment_id, guide, digest, now),
            )
            severity, notification = "initial", "assignment_offer"
        else:
            raw = conn.execute(
                "SELECT * FROM guide_operator_assignments WHERE assignment_id=? AND guide_os_id=?",
                (assignment_id, guide),
            ).fetchone()
            if raw is None:
                raise domain.AssignmentNotFoundError("Assignment was not found.")
            assignment = dict(raw)
            if assignment["company_id"] != package["company_id"]:
                raise domain.AssignmentForbiddenError("Company identity mismatch.")
            _connection(
                conn, assignment["company_id"], guide, assignment["guide_connection_id"]
            )
            if (
                assignment["status"] != "accepted"
                or assignment["pending_critical_version_number"] is not None
            ):
                raise domain.AssignmentNotActionableError(
                    "Accepted assignment without pending change required."
                )
            numbers = [
                r[0]
                for r in conn.execute(
                    "SELECT version_number FROM guide_operator_assignment_versions WHERE assignment_id=? ORDER BY version_number",
                    (assignment_id,),
                )
            ]
            if (
                not numbers
                or numbers != list(range(1, numbers[-1] + 1))
                or payload["version_number"] != numbers[-1] + 1
                or payload["previous_active_version_number"]
                != assignment["active_version_number"]
            ):
                raise domain.AssignmentValidationError(
                    "Version gap or stale active version."
                )
            previous = _snapshot(
                conn, assignment_id, assignment["active_version_number"]
            )
            severity = payload["severity"]
            if assignment["projection_mode"] == "explicit_days":
                validate_package(previous)
                domain._explicit_scope(assignment, package)
                _effective_set(conn, assignment, previous, user["user_id"])
            elif (
                assignment["projection_mode"] == "legacy_range"
                and severity == "critical"
            ):
                domain._require_legacy_package(previous)
                tour_id = previous.get("tour", {}).get("id")
                uuid(tour_id, "legacy immutable tour identity")
                domain._explicit_scope(
                    {
                        **assignment,
                        "projection_mode": "explicit_days",
                        "operator_tour_id": tour_id,
                    },
                    package,
                )
            else:
                raise domain.AssignmentValidationError(
                    "Unsupported projection mode/transition."
                )
            if {k: v for k, v in previous.items() if k != "source_tour_revision"} == {
                k: v for k, v in package.items() if k != "source_tour_revision"
            }:
                raise domain.AssignmentValidationError(
                    "A new version must change the working package."
                )
            if severity == "ordinary":
                _ordinary_safe(assignment, previous, package)
                scope = domain._explicit_scope(assignment, package)
                # Occupancy is unchanged and its integrity was checked above.
                domain._replace_daily_projections(
                    conn,
                    assignment,
                    package,
                    payload["version_number"],
                    user["user_id"],
                    scope,
                )
                conn.execute(
                    "UPDATE guide_operator_assignments SET active_version_number=?,active_version_unread=1,updated_at=? WHERE assignment_id=?",
                    (payload["version_number"], now, assignment_id),
                )
                notification = "ordinary_version_change"
            else:
                conn.execute(
                    "UPDATE guide_operator_assignments SET pending_critical_version_number=?,updated_at=? WHERE assignment_id=?",
                    (payload["version_number"], now, assignment_id),
                )
                notification = "critical_confirmation_required"
            conn.execute(
                "INSERT INTO guide_operator_version_inbox(event_id,assignment_id,guide_os_id,version_number,payload_hash,received_at,result_status) VALUES (?,?,?,?,?,?,'applied')",
                (
                    event_id,
                    assignment_id,
                    guide,
                    payload["version_number"],
                    digest,
                    now,
                ),
            )
            ack = {
                k: payload[k]
                for k in (
                    "assignment_id",
                    "guide_os_id",
                    "version_number",
                    "previous_active_version_number",
                    "severity",
                    "published_at",
                )
            }
            ack.update(
                source_event_id=event_id,
                **(
                    {"applied_at": now}
                    if severity == "ordinary"
                    else {"received_at": now}
                ),
            )
            conn.execute(
                "INSERT INTO guide_operator_outbox(event_id,event_type,aggregate_type,aggregate_id,guide_os_id,payload_json,created_at,attempt_count) VALUES (?,?,'guide_assignment',?,?,?,?,0)",
                (
                    event_id,
                    domain.ORDINARY_VERSION_ACK_EVENT_TYPE
                    if severity == "ordinary"
                    else domain.CRITICAL_VERSION_RECEIVED_ACK_EVENT_TYPE,
                    assignment_id,
                    guide,
                    json.dumps(ack, sort_keys=True),
                    now,
                ),
            )
        conn.execute(
            "INSERT INTO guide_operator_assignment_versions(assignment_id,version_number,severity,working_package_json,published_at,change_summary_json,source_event_id) VALUES (?,?,?,?,?,?,?)",
            (
                assignment_id,
                payload["version_number"],
                severity,
                json.dumps(package, sort_keys=True),
                payload["offered_at"] if offer else payload["published_at"],
                None
                if offer
                else json.dumps(payload["change_summary"], sort_keys=True),
                event_id,
            ),
        )
        company_name = payload["company_name"] if offer else assignment["company_name"]
        insert_guide_operator_guide_notification(
            conn,
            source_event_id=event_id,
            guide_os_id=guide,
            notification_type=notification,
            company_name=company_name,
            assignment_id=assignment_id,
            version_number=payload["version_number"],
            created_at=now,
        )
        hook = (
            domain._OFFER_INTAKE_FAILURE_HOOK
            if offer
            else (
                domain._ORDINARY_VERSION_FAILURE_HOOK
                if severity == "ordinary"
                else domain._CRITICAL_VERSION_INTAKE_FAILURE_HOOK
            )
        )
        if hook:
            hook()
        return _result(conn, assignment_id)

    return run_write_with_retry(operation)
