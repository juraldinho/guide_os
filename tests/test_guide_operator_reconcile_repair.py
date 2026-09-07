"""GO11B2B: safe local Guide Operator calendar projection repair."""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

import jwt
import pytest
from aiohttp.test_utils import TestClient, TestServer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from database.db import get_connection, init_db
from database.queries import (
    count_guide_operator_projections,
    create_tour,
    get_guide_os_id,
    get_tour_by_id,
    get_user_id_by_guide_os_id,
    register_user,
)
from services import guide_operator_reconcile_repair_service as repair_service
from services.guide_operator_assignment_service import (
    AssignmentCancellationIntake,
    AssignmentOfferIntake,
    AssignmentVersionPublishedIntake,
    accept_assignment,
    apply_assignment_cancellation,
    get_assignment_for_guide,
    intake_critical_assignment_version,
    receive_assignment_offer,
)
from services.guide_operator_connection_service import (
    ensure_confirmed_connection_for_tests,
)
from services.guide_operator_reconcile_repair_service import (
    get_projection_repair_inbox,
    list_projection_repair_audits,
    repair_local_projection,
)
from services.guide_operator_reconcile_service import get_local_assignment
from services.guide_operator_service_auth_settings import (
    GuideOperatorServiceAuthSettings,
    reset_guide_operator_service_auth_for_tests,
)
from services.guide_operator_service_jwt import (
    ALGORITHM,
    INBOUND_AUDIENCE,
    INBOUND_ISSUER,
    INBOUND_SUBJECT,
    INBOUND_TOKEN_TYPE,
    MAX_TTL_SECONDS,
    SCOPE_CONNECTIONS_WRITE,
    SCOPE_OPERATOR_RECONCILE,
)
from utils.constants import SOURCE_GUIDE_OPERATOR, STATUS_CONFIRMED
from web_api.guide_operator_integration import create_guide_operator_integration_app

FIXED_NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
NOW_TS = int(FIXED_NOW.timestamp())
INBOUND_KID = "guide-operator-test-key"
OUTBOUND_KID = "guide-os-test-key-01"
API_USER = 811201
OTHER_USER = 811202
PRIVACY_MARKERS = (
    "telegram",
    "working_package",
    "operator_message",
    "phone",
    "BEGIN PRIVATE",
    "income",
)


class FrozenClock:
    def __init__(self, now: datetime = FIXED_NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _pem_pair() -> tuple[str, str]:
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return private_pem, public_pem


def mint_token(private_pem: str, *, scope: str, jti: str | None = None) -> str:
    claims = {
        "iss": INBOUND_ISSUER,
        "aud": INBOUND_AUDIENCE,
        "sub": INBOUND_SUBJECT,
        "scope": scope,
        "iat": NOW_TS,
        "nbf": NOW_TS,
        "exp": NOW_TS + MAX_TTL_SECONDS,
        "jti": jti or f"jti-{uuid4().hex}",
    }
    key = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
    return jwt.encode(
        claims,
        key,
        algorithm=ALGORITHM,
        headers={"alg": ALGORITHM, "typ": INBOUND_TOKEN_TYPE, "kid": INBOUND_KID},
    )


@pytest.fixture
def keys() -> tuple[str, str]:
    return _pem_pair()


@pytest.fixture
def outbound_private() -> str:
    return _pem_pair()[0]


@pytest.fixture
def auth_settings(
    keys: tuple[str, str], outbound_private: str
) -> GuideOperatorServiceAuthSettings:
    return GuideOperatorServiceAuthSettings.enabled_with(
        app_env="test",
        public_keys={INBOUND_KID: keys[1]},
        signing_kid=OUTBOUND_KID,
        signing_private_key_pem=outbound_private,
    )


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture(autouse=True)
def _reset_db_and_auth() -> Iterator[None]:
    reset_guide_operator_service_auth_for_tests()
    init_db()
    yield
    reset_guide_operator_service_auth_for_tests()


def run(awaitable):
    return asyncio.run(awaitable)


def _seed_guide(user_id: int = API_USER) -> str:
    register_user(user_id)
    guide_os_id = get_guide_os_id(user_id)
    assert guide_os_id is not None
    return guide_os_id


async def _with_client(auth_settings, clock, coro):
    app = create_guide_operator_integration_app(
        auth_settings=auth_settings,
        clock=clock,
    )
    client = TestClient(TestServer(app))
    async with client:
        return await coro(client)


def api_post(auth_settings, clock, path: str, *, token: str | None, body: dict):
    async def _call(client):
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        response = await client.post(path, headers=headers, json=body)
        response._body_text = await response.text()
        return response

    return run(_with_client(auth_settings, clock, _call))


def response_json(response):
    return json.loads(response._body_text)


def _repair_path(guide_os_id: str, assignment_id: str) -> str:
    return (
        f"/integration/v1/reconcile/guides/{guide_os_id}"
        f"/assignments/{assignment_id}/repair"
    )


def _seed_accepted_assignment(guide_os_id: str) -> str:
    connection = ensure_confirmed_connection_for_tests(guide_os_id)
    assignment_id = str(uuid4())
    offer = AssignmentOfferIntake(
        event_id=str(uuid4()),
        assignment_id=assignment_id,
        guide_connection_id=connection["connection_id"],
        company_id=connection["company_id"],
        company_name="Operator Co",
        guide_os_id=guide_os_id,
        role="main_guide",
        start_date="2026-09-14",
        end_date="2026-09-16",
        response_deadline=None,
        operator_message="hidden operator note",
        offered_at="2026-09-05T10:00:00+00:00",
        working_package={
            "tour": {"title": "Hidden", "city_or_route": "Samarkand"},
            "assignment": {
                "id": assignment_id,
                "role": "main_guide",
                "start_date": "2026-09-14",
                "end_date": "2026-09-16",
            },
            "days": [
                {
                    "date": "2026-09-14",
                    "title": "Day 1",
                    "city_or_route": "Samarkand",
                }
            ],
        },
    )
    receive_assignment_offer(offer)
    accept_assignment(
        guide_os_id,
        assignment_id,
        decision_event_id=str(uuid4()),
        decided_at="2026-09-05T11:00:00+00:00",
    )
    return assignment_id


def _observed_body(guide_os_id: str, assignment_id: str, *, request_id: str | None = None) -> dict:
    snap = get_local_assignment(guide_os_id, assignment_id)
    return {
        "repair_request_id": request_id or str(uuid4()),
        "expected_status": snap["status"],
        "expected_active_version_number": snap["active_version_number"],
        "expected_projection": snap["calendar_projection"],
    }


def _drop_projection(assignment_id: str, tour_id: int) -> None:
    conn = get_connection()
    conn.execute(
        """
        UPDATE guide_operator_assignments
        SET projection_tour_id = NULL
        WHERE assignment_id = ?
        """,
        (assignment_id,),
    )
    conn.execute(
        "INSERT INTO go_operator_projection_release (tour_id) VALUES (?)",
        (tour_id,),
    )
    conn.execute("DELETE FROM tours WHERE id = ?", (tour_id,))
    conn.execute(
        "DELETE FROM go_operator_projection_release WHERE tour_id = ?",
        (tour_id,),
    )
    conn.commit()
    conn.close()


def _corrupt_projection_dates(tour_id: int, start_date: str, end_date: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO go_operator_projection_occupancy_update (tour_id) VALUES (?)",
        (tour_id,),
    )
    conn.execute(
        "UPDATE tours SET start_date = ?, end_date = ? WHERE id = ?",
        (start_date, end_date, tour_id),
    )
    conn.execute(
        "DELETE FROM go_operator_projection_occupancy_update WHERE tour_id = ?",
        (tour_id,),
    )
    conn.commit()
    conn.close()


def _insert_stray_projection(assignment_id: str, user_id: int) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """
        INSERT INTO tours (
            user_id, company, city, start_date, end_date, status,
            income, payment_status, note, entry_type, tour_group_id,
            title, start_time, end_time, source, day_locations_json
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
        """,
        (
            user_id,
            "Operator Co",
            "Samarkand",
            "2026-09-14",
            "2026-09-16",
            STATUS_CONFIRMED,
            "unpaid",
            f"go_assignment:{assignment_id}",
            "tour",
            assignment_id,
            "Stray Hidden",
            SOURCE_GUIDE_OPERATOR,
            None,
        ),
    )
    tour_id = int(cursor.lastrowid)
    conn.execute(
        """
        UPDATE guide_operator_assignments
        SET projection_tour_id = ?
        WHERE assignment_id = ?
        """,
        (tour_id, assignment_id),
    )
    conn.commit()
    conn.close()
    return tour_id


def _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, body, *, scope=SCOPE_OPERATOR_RECONCILE):
    return api_post(
        auth_settings,
        clock,
        _repair_path(guide_os_id, assignment_id),
        token=mint_token(keys[0], scope=scope),
        body=body,
    )


def test_recreates_missing_protected_projection(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id = _seed_accepted_assignment(guide_os_id)
    stored = get_assignment_for_guide(guide_os_id, assignment_id)
    tour_id = stored["projection_tour_id"]
    assert tour_id is not None
    _drop_projection(assignment_id, tour_id)
    assert count_guide_operator_projections(assignment_id) == 0

    body = _observed_body(guide_os_id, assignment_id)
    response = _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, body)
    assert response.status == 200
    payload = response_json(response)["data"]
    assert payload["status"] == "applied"
    assert payload["replayed"] is False
    assert payload["repairRequestId"] == body["repair_request_id"]
    assert count_guide_operator_projections(assignment_id) == 1
    repaired = get_assignment_for_guide(guide_os_id, assignment_id)
    assert repaired["status"] == "accepted"
    assert repaired["active_version_number"] == 1
    assert repaired["pending_critical_version_number"] is None
    assert repaired["projection_tour_id"] is not None
    tour = get_tour_by_id(get_user_id_by_guide_os_id(guide_os_id), repaired["projection_tour_id"])
    assert tour["start_date"] == "2026-09-14"
    assert tour["end_date"] == "2026-09-16"
    assert tour["source"] == SOURCE_GUIDE_OPERATOR
    assert get_projection_repair_inbox(body["repair_request_id"])["action"] == "recreate"


def test_repairs_mismatched_protected_projection(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id = _seed_accepted_assignment(guide_os_id)
    stored = get_assignment_for_guide(guide_os_id, assignment_id)
    tour_id = stored["projection_tour_id"]
    _corrupt_projection_dates(tour_id, "2026-10-01", "2026-10-02")
    body = _observed_body(guide_os_id, assignment_id)
    response = _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, body)
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "applied"
    tour = get_tour_by_id(get_user_id_by_guide_os_id(guide_os_id), tour_id)
    assert tour["start_date"] == "2026-09-14"
    assert tour["end_date"] == "2026-09-16"
    after = get_assignment_for_guide(guide_os_id, assignment_id)
    assert after["start_date"] == "2026-09-14"
    assert after["end_date"] == "2026-09-16"
    assert after["active_version_number"] == 1
    assert get_projection_repair_inbox(body["repair_request_id"])["action"] == "repair_mismatch"


def test_removes_cancelled_stray_projection(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    assignment_id = _seed_accepted_assignment(guide_os_id)
    apply_assignment_cancellation(
        AssignmentCancellationIntake(
            event_id=str(uuid4()),
            assignment_id=assignment_id,
            guide_os_id=guide_os_id,
            version_number=1,
            cancelled_at="2026-09-06T08:00:00+00:00",
        )
    )
    stray_id = _insert_stray_projection(assignment_id, user_id)
    assert count_guide_operator_projections(assignment_id) == 1
    body = _observed_body(guide_os_id, assignment_id)
    response = _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, body)
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "applied"
    assert count_guide_operator_projections(assignment_id) == 0
    assert get_tour_by_id(user_id, stray_id) is None
    stored = get_assignment_for_guide(guide_os_id, assignment_id)
    assert stored["status"] == "cancelled"
    assert stored["projection_tour_id"] is None
    assert get_projection_repair_inbox(body["repair_request_id"])["action"] == "release_stray"


def test_calendar_conflict_does_not_mutate(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    assignment_id = _seed_accepted_assignment(guide_os_id)
    stored = get_assignment_for_guide(guide_os_id, assignment_id)
    _drop_projection(assignment_id, stored["projection_tour_id"])
    personal_id = create_tour(
        user_id=user_id,
        company="Personal Co",
        city="Bukhara",
        start_date="2026-09-15",
        end_date="2026-09-15",
        status=STATUS_CONFIRMED,
        income=120,
    )
    body = _observed_body(guide_os_id, assignment_id)
    response = _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, body)
    assert response.status == 409
    payload = response_json(response)
    assert payload["error"]["code"] == "conflict"
    assert payload["error"]["details"]["status"] == "conflict"
    assert count_guide_operator_projections(assignment_id) == 0
    personal = get_tour_by_id(user_id, personal_id)
    assert personal["company"] == "Personal Co"
    assert personal["income"] == 120
    assert personal["source"] != SOURCE_GUIDE_OPERATOR


def test_stale_evidence_is_no_op(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id = _seed_accepted_assignment(guide_os_id)
    stored = get_assignment_for_guide(guide_os_id, assignment_id)
    stale = _observed_body(guide_os_id, assignment_id)
    _drop_projection(assignment_id, stored["projection_tour_id"])
    response = _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, stale)
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "no-op"
    assert count_guide_operator_projections(assignment_id) == 0
    assert get_assignment_for_guide(guide_os_id, assignment_id)["projection_tour_id"] is None


def test_pending_critical_is_not_repaired(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id = _seed_accepted_assignment(guide_os_id)
    stored = get_assignment_for_guide(guide_os_id, assignment_id)
    conn = get_connection()
    try:
        package = copy.deepcopy(
            json.loads(
                conn.execute(
                    """
                    SELECT working_package_json
                    FROM guide_operator_assignment_versions
                    WHERE assignment_id = ? AND version_number = 1
                    """,
                    (assignment_id,),
                ).fetchone()["working_package_json"]
            )
        )
    finally:
        conn.close()
        package["assignment"]["guide_os_id"] = guide_os_id
        package["assignment"]["start_date"] = "2026-09-17"
    package["assignment"]["end_date"] = "2026-09-19"
    package["days"][0]["date"] = "2026-09-17"
    intake_critical_assignment_version(
        AssignmentVersionPublishedIntake(
            event_id=str(uuid4()),
            assignment_id=assignment_id,
            guide_os_id=guide_os_id,
            version_number=2,
            previous_active_version_number=1,
            severity="critical",
            working_package=package,
            change_summary=[
                {
                    "code": "start_date_changed",
                    "severity": "critical",
                    "path": "assignment.start_date",
                }
            ],
            published_at="2026-09-06T09:00:00+00:00",
        )
    )
    _drop_projection(assignment_id, stored["projection_tour_id"])
    body = _observed_body(guide_os_id, assignment_id)
    response = _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, body)
    assert response.status == 200
    assert response_json(response)["data"]["status"] == "no-op"
    after = get_assignment_for_guide(guide_os_id, assignment_id)
    assert after["pending_critical_version_number"] == 2
    assert after["active_version_number"] == 1
    assert after["status"] == "accepted"
    assert count_guide_operator_projections(assignment_id) == 0


def test_wrong_guide_and_scope(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    other = _seed_guide(OTHER_USER)
    assignment_id = _seed_accepted_assignment(guide_os_id)
    stored = get_assignment_for_guide(guide_os_id, assignment_id)
    _drop_projection(assignment_id, stored["projection_tour_id"])
    body = _observed_body(guide_os_id, assignment_id)
    cross = _post_repair(auth_settings, clock, keys, other, assignment_id, body)
    assert cross.status == 404
    assert count_guide_operator_projections(assignment_id) == 0
    scoped = _post_repair(
        auth_settings,
        clock,
        keys,
        guide_os_id,
        assignment_id,
        body,
        scope=SCOPE_CONNECTIONS_WRITE,
    )
    assert scoped.status == 401
    assert "not_found" == response_json(cross)["error"]["code"]


def test_personal_tour_is_not_mutated(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    user_id = get_user_id_by_guide_os_id(guide_os_id)
    assignment_id = _seed_accepted_assignment(guide_os_id)
    stored = get_assignment_for_guide(guide_os_id, assignment_id)
    personal_id = create_tour(
        user_id=user_id,
        company="Keep Me",
        city="Khiva",
        start_date="2026-11-01",
        end_date="2026-11-01",
        status=STATUS_CONFIRMED,
        income=80,
    )
    _corrupt_projection_dates(stored["projection_tour_id"], "2026-10-01", "2026-10-02")
    body = _observed_body(guide_os_id, assignment_id)
    response = _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, body)
    assert response.status == 200
    personal = get_tour_by_id(user_id, personal_id)
    assert personal["company"] == "Keep Me"
    assert personal["income"] == 80
    assert personal["start_date"] == "2026-11-01"
    repaired = get_tour_by_id(user_id, stored["projection_tour_id"])
    assert repaired["start_date"] == "2026-09-14"


def test_replay_and_conflicting_request_id(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id = _seed_accepted_assignment(guide_os_id)
    stored = get_assignment_for_guide(guide_os_id, assignment_id)
    _drop_projection(assignment_id, stored["projection_tour_id"])
    body = _observed_body(guide_os_id, assignment_id)
    first = _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, body)
    assert response_json(first)["data"]["status"] == "applied"
    projection_id = get_assignment_for_guide(guide_os_id, assignment_id)["projection_tour_id"]
    replay = _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, body)
    assert replay.status == 200
    payload = response_json(replay)["data"]
    assert payload["status"] == "replayed"
    assert payload["replayed"] is True
    assert count_guide_operator_projections(assignment_id) == 1
    assert get_assignment_for_guide(guide_os_id, assignment_id)["projection_tour_id"] == projection_id

    conflict_body = dict(body)
    conflict_body["expected_status"] = "cancelled"
    conflict = _post_repair(
        auth_settings, clock, keys, guide_os_id, assignment_id, conflict_body
    )
    assert conflict.status == 409
    assert response_json(conflict)["error"]["code"] == "conflict"
    assert count_guide_operator_projections(assignment_id) == 1
    assert get_assignment_for_guide(guide_os_id, assignment_id)["status"] == "accepted"


def test_failed_repair_rolls_back(monkeypatch):
    guide_os_id = _seed_guide()
    assignment_id = _seed_accepted_assignment(guide_os_id)
    stored = get_assignment_for_guide(guide_os_id, assignment_id)
    _drop_projection(assignment_id, stored["projection_tour_id"])
    body = _observed_body(guide_os_id, assignment_id)

    def boom():
        raise RuntimeError("forced repair failure")

    monkeypatch.setattr(repair_service, "_REPAIR_FAILURE_HOOK", boom)
    with pytest.raises(RuntimeError, match="forced repair failure"):
        repair_local_projection(
            guide_os_id,
            assignment_id,
            repair_request_id=body["repair_request_id"],
            expected_status=body["expected_status"],
            expected_active_version_number=body["expected_active_version_number"],
            expected_projection=body["expected_projection"],
        )
    assert count_guide_operator_projections(assignment_id) == 0
    assert get_projection_repair_inbox(body["repair_request_id"]) is None
    assert list_projection_repair_audits(assignment_id) == []
    assert get_assignment_for_guide(guide_os_id, assignment_id)["projection_tour_id"] is None
    assert get_assignment_for_guide(guide_os_id, assignment_id)["status"] == "accepted"


def test_audit_is_written_once_on_apply(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id = _seed_accepted_assignment(guide_os_id)
    stored = get_assignment_for_guide(guide_os_id, assignment_id)
    _drop_projection(assignment_id, stored["projection_tour_id"])
    body = _observed_body(guide_os_id, assignment_id)
    _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, body)
    _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, body)
    audits = list_projection_repair_audits(assignment_id)
    assert len(audits) == 1
    assert audits[0]["action"] == "recreate"
    assert audits[0]["result_status"] == "applied"
    assert audits[0]["repair_request_id"] == body["repair_request_id"]
    blob = json.dumps(audits)
    for marker in PRIVACY_MARKERS:
        assert marker not in blob
    assert "Hidden" not in blob


def test_privacy_and_rejected_replacement_fields(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    assignment_id = _seed_accepted_assignment(guide_os_id)
    stored = get_assignment_for_guide(guide_os_id, assignment_id)
    _drop_projection(assignment_id, stored["projection_tour_id"])
    body = _observed_body(guide_os_id, assignment_id)
    ok = _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, body)
    blob = ok._body_text
    for marker in PRIVACY_MARKERS:
        assert marker not in blob
    assert "Hidden" not in blob
    assert "hidden operator note" not in blob

    rejected = dict(body)
    rejected["start_date"] = "2026-12-01"
    rejected["working_package"] = {"tour": {"title": "Injected"}}
    bad = _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, rejected)
    assert bad.status == 400


def test_offered_and_version_gap_are_not_repaired(auth_settings, clock, keys):
    guide_os_id = _seed_guide()
    connection = ensure_confirmed_connection_for_tests(guide_os_id)
    offered_id = str(uuid4())
    receive_assignment_offer(
        AssignmentOfferIntake(
            event_id=str(uuid4()),
            assignment_id=offered_id,
            guide_connection_id=connection["connection_id"],
            company_id=connection["company_id"],
            company_name="Operator Co",
            guide_os_id=guide_os_id,
            role="main_guide",
            start_date="2026-09-20",
            end_date="2026-09-21",
            working_package={
                "tour": {"title": "Offered Hidden", "city_or_route": "Tashkent"},
                "assignment": {
                    "id": offered_id,
                    "role": "main_guide",
                    "start_date": "2026-09-20",
                    "end_date": "2026-09-21",
                },
                "days": [{"date": "2026-09-20", "city_or_route": "Tashkent"}],
            },
        )
    )
    offered_body = {
        "repair_request_id": str(uuid4()),
        "expected_status": "accepted",
        "expected_active_version_number": 1,
        "expected_projection": {
            "exists": False,
            "start_date": None,
            "end_date": None,
            "version_number": None,
        },
    }
    offered = _post_repair(
        auth_settings, clock, keys, guide_os_id, offered_id, offered_body
    )
    assert offered.status == 200
    assert response_json(offered)["data"]["status"] == "no-op"
    assert get_assignment_for_guide(guide_os_id, offered_id)["status"] == "offered"
    assert count_guide_operator_projections(offered_id) == 0

    assignment_id = _seed_accepted_assignment(guide_os_id)
    conn = get_connection()
    conn.execute(
        """
        UPDATE guide_operator_assignments
        SET active_version_number = 2
        WHERE assignment_id = ?
        """,
        (assignment_id,),
    )
    conn.commit()
    conn.close()
    gap_body = _observed_body(guide_os_id, assignment_id)
    gap = _post_repair(auth_settings, clock, keys, guide_os_id, assignment_id, gap_body)
    assert gap.status == 200
    assert response_json(gap)["data"]["status"] == "no-op"
    assert count_guide_operator_projections(assignment_id) == 1
    assert get_assignment_for_guide(guide_os_id, assignment_id)["active_version_number"] == 2
