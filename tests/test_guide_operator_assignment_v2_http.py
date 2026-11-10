"""Real isolated v2 intake HTTP. Public guide lifecycle wiring stays a separate gate."""

import asyncio
import copy
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from aiohttp.test_utils import TestClient, TestServer

from services.guide_operator_integration_settings import (
    GuideOperatorIntegrationConfigurationError,
    GuideOperatorIntegrationSettings,
)
from services.guide_operator_service_auth_settings import (
    GuideOperatorServiceAuthSettings,
)
from services.guide_operator_service_jwt import SCOPE_OFFERS_WRITE, SCOPE_VERSIONS_WRITE
from tests.test_guide_operator_assignment_v2_contract import published
from tests.test_guide_operator_assignment_v2_intake import decide, fingerprint, seed
from tests.test_guide_operator_daily_projections import rows, state
from tests.test_guide_operator_integration_http import (
    _pem_pair,
    _reset_db_and_auth,
    auth_settings,
    clock,
    keys,
    mint_token,
    outbound_private,
)
from web_api.guide_operator_integration import (
    MAX_REQUEST_BODY_BYTES,
    create_guide_operator_integration_app,
)

# Re-export the existing pytest fixtures without creating another auth harness.
__all__ = ["_reset_db_and_auth", "auth_settings", "clock", "keys", "outbound_private"]

FLAG = "GUIDE_OS_GUIDE_OPERATOR_ASSIGNMENT_EXPLICIT_DAYS_V2_RECEIVE_ENABLED"
ENABLED = GuideOperatorIntegrationSettings(
    enabled=True, assignment_explicit_days_v2_receive_enabled=True
)


def path(event, *, version=False, assignment_id=None):
    identity = assignment_id or event["payload"]["assignment_id"]
    return (
        f"/integration/v2/assignments/{identity}/{'versions' if version else 'offered'}"
    )


async def request(client, target, event, *, token, raw=None, headers=None):
    values = {"Content-Type": "application/json"}
    if token is not None:
        values["Authorization"] = f"Bearer {token}"
    values.update(headers or {})
    if raw is None:
        response = await client.post(target, json=event, headers=values)
    else:
        response = await client.post(target, data=raw, headers=values)
    return response.status, await response.json()


def post(auth_settings, clock, event, *, token, config=ENABLED, target=None, **kwargs):
    async def run():
        app = create_guide_operator_integration_app(
            auth_settings=auth_settings, clock=clock, integration_settings=config
        )
        async with TestClient(TestServer(app)) as client:
            return await request(
                client, target or path(event), event, token=token, **kwargs
            )

    return asyncio.run(run())


@pytest.mark.parametrize("version", [False, True])
@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "invalid",
        "wrong_key",
        "wrong_scope",
        "expired",
        "jti_replay",
        "disabled_auth",
    ],
)
def test_authentication_before_intake(auth_settings, clock, keys, version, failure):
    event = seed()
    if version:
        event = published(event)
    expected_scope = SCOPE_VERSIONS_WRITE if version else SCOPE_OFFERS_WRITE
    token = mint_token(keys[0], scope=expected_scope)
    expected = 401
    if failure == "missing":
        token = None
    elif failure == "invalid":
        token = "not-a-jwt"
    elif failure == "wrong_key":
        token = mint_token(_pem_pair()[0], scope=expected_scope)
    elif failure == "wrong_scope":
        token = mint_token(
            keys[0], scope=SCOPE_OFFERS_WRITE if version else SCOPE_VERSIONS_WRITE
        )
    elif failure == "expired":
        token = mint_token(
            keys[0], scope=expected_scope, issued_at=int(clock().timestamp()) - 120
        )
    elif failure == "disabled_auth":
        auth_settings = GuideOperatorServiceAuthSettings.disabled()
        expected = 503
    elif failure == "jti_replay":
        # Consume this JWT in an authenticated request rejected by the body parser.
        status, _ = post(
            auth_settings,
            clock,
            event,
            token=token,
            target=path(event, version=version),
            raw="{}",
        )
        assert status == 400
    before = fingerprint()
    status, _ = post(
        auth_settings, clock, event, token=token, target=path(event, version=version)
    )
    assert status == expected
    assert fingerprint() == before


@pytest.mark.parametrize("version", [False, True])
@pytest.mark.parametrize(
    "config",
    [
        GuideOperatorIntegrationSettings.disabled(),
        GuideOperatorIntegrationSettings(enabled=True),
        GuideOperatorIntegrationSettings(
            assignment_explicit_days_v2_receive_enabled=True
        ),
        replace(ENABLED, assignment_explicit_days_v2_receive_enabled="true"),
    ],
)
def test_disabled_receive_is_503_without_domain_writes(
    auth_settings, clock, keys, version, config
):
    event = seed()
    if version:
        event = published(event)
    before = fingerprint()
    status, body = post(
        auth_settings,
        clock,
        event,
        config=config,
        target=path(event, version=version),
        token=mint_token(
            keys[0], scope=SCOPE_VERSIONS_WRITE if version else SCOPE_OFFERS_WRITE
        ),
    )
    assert status == 503
    assert body["error"]["code"] == "assignment_v2_receive_disabled"
    assert fingerprint() == before


def test_authentication_precedes_capability_error(auth_settings, clock):
    event = seed()
    status, body = post(
        auth_settings,
        clock,
        event,
        config=GuideOperatorIntegrationSettings.disabled(),
        token=None,
        raw="not-json",
    )
    assert status == 401 and body["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize(
    "values",
    [
        {},
        {FLAG: "true"},
        {"GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED": "true"},
        {"GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED": "true", FLAG: "false"},
    ],
)
def test_receive_config_defaults_off(values):
    assert (
        GuideOperatorIntegrationSettings.from_env(
            values
        ).assignment_explicit_days_v2_receive_enabled
        is False
    )


def test_receive_config_explicitly_enabled_and_invalid_values():
    values = {"GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED": "true", FLAG: "true"}
    assert (
        GuideOperatorIntegrationSettings.from_env(
            values
        ).assignment_explicit_days_v2_receive_enabled
        is True
    )
    for value in ("unknown", "null", None, 1):
        with pytest.raises(GuideOperatorIntegrationConfigurationError):
            GuideOperatorIntegrationSettings.from_env({**values, FLAG: value})


@pytest.mark.parametrize(
    "failure", ["default", "invalid_flag", "invalid_port", "invalid_host"]
)
def test_factory_env_default_and_incomplete_config_fail_closed(
    monkeypatch, auth_settings, clock, keys, failure
):
    monkeypatch.delenv(FLAG, raising=False)
    monkeypatch.setenv("GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED", "true")
    monkeypatch.setenv("GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_HOST", "127.0.0.1")
    monkeypatch.setenv("GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_PORT", "8084")
    if failure != "default":
        monkeypatch.setenv(FLAG, "true")
    if failure == "invalid_flag":
        monkeypatch.setenv(FLAG, "unknown")
    elif failure == "invalid_port":
        monkeypatch.setenv("GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_PORT", "not-a-port")
    elif failure == "invalid_host":
        monkeypatch.setenv(
            "GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_HOST", "https://invalid/"
        )
    event = seed()
    before = fingerprint()
    status, _ = post(
        auth_settings,
        clock,
        event,
        config=None,
        token=mint_token(keys[0], scope=SCOPE_OFFERS_WRITE),
    )
    assert status == 503
    assert fingerprint() == before


@pytest.mark.parametrize(
    "failure",
    [
        "extra_envelope",
        "extra_payload",
        "extra_package",
        "missing_key",
        "duplicate_envelope",
        "duplicate_nested",
        "non_json",
        "oversized",
        "content_type",
        "noncanonical_id",
        "path",
        "guide",
        "company",
        "connection",
        "money",
        "sparse_minmax",
        "day_id",
        "event_type",
        "timestamp_coercion",
        "nonfinite",
    ],
)
def test_invalid_offer_is_atomic(auth_settings, clock, keys, failure):
    event = seed()
    target = path(event)
    payload = event["payload"]
    package = payload["working_package"]
    kwargs = {}
    if failure == "extra_envelope":
        event["schema_version"] = "v2"
    elif failure == "extra_payload":
        payload["guideId"] = str(uuid4())
    elif failure == "extra_package":
        package["private_comment"] = "hidden"
    elif failure == "missing_key":
        package.pop("remuneration")
    elif failure == "duplicate_envelope":
        kwargs["raw"] = json.dumps(event).replace(
            '"event_type":', '"event_type":"assignment.offered.v2","event_type":', 1
        )
    elif failure == "duplicate_nested":
        kwargs["raw"] = json.dumps(event).replace(
            '"remuneration": null', '"remuneration":null,"remuneration":null'
        )
    elif failure == "non_json":
        kwargs["raw"] = "not json"
    elif failure == "oversized":
        kwargs["raw"] = " " * (MAX_REQUEST_BODY_BYTES + 1)
    elif failure == "content_type":
        kwargs["headers"] = {"Content-Type": "text/plain"}
    elif failure == "noncanonical_id":
        target = path(event, assignment_id=payload["assignment_id"].upper())
    elif failure == "path":
        target = path(event, assignment_id=str(uuid4()))
    elif failure == "guide":
        package["assignment"]["guide_os_id"] = str(uuid4())
    elif failure == "company":
        payload["company_id"] = package["company_id"] = str(uuid4())
    elif failure == "connection":
        payload["guide_connection_id"] = str(uuid4())
    elif failure == "money":
        package["remuneration"] = {"currency": "USD", "default_daily_usd": 0}
    elif failure == "sparse_minmax":
        package["assignment"]["end_date"] = "2026-11-11"
    elif failure == "day_id":
        package["days"][1]["tour_day_id"] = package["days"][0]["tour_day_id"]
    elif failure == "event_type":
        event["event_type"] = "assignment.offered.v1"
    elif failure == "timestamp_coercion":
        event["occurred_at"] = " " + event["occurred_at"] + " "
    elif failure == "nonfinite":
        kwargs["raw"] = json.dumps(event).replace(
            '"source_tour_revision": 1', '"source_tour_revision": NaN'
        )
    before = fingerprint()
    status, body = post(
        auth_settings,
        clock,
        event,
        target=target,
        token=mint_token(keys[0], scope=SCOPE_OFFERS_WRITE),
        **kwargs,
    )
    assert status == (403 if failure in {"company", "connection"} else 400)
    assert "hidden" not in json.dumps(body)
    assert fingerprint() == before


def test_sparse_offer_version_http_workflow(auth_settings, clock, keys):
    event = seed()
    identity = event["payload"]["assignment_id"]

    async def run():
        app = create_guide_operator_integration_app(
            auth_settings=auth_settings, clock=clock, integration_settings=ENABLED
        )
        async with TestClient(TestServer(app)) as client:

            async def send(value, version=False):
                return await request(
                    client,
                    path(value, version=version),
                    value,
                    token=mint_token(
                        keys[0],
                        scope=SCOPE_VERSIONS_WRITE if version else SCOPE_OFFERS_WRITE,
                    ),
                )

            status, body = await send(event)
            assert status == 200 and body["data"] == {
                "status": "applied",
                "eventId": event["event_id"],
                "eventType": "assignment.offered.v2",
                "replayed": False,
            }
            assert not rows(identity)
            before = fingerprint()
            assert (await send(event))[1]["data"]["status"] == "replayed"
            assert fingerprint() == before
            reused = copy.deepcopy(event)
            reused["payload"]["company_name"] = "Changed"
            assert (await send(reused))[0] == 409
            assert fingerprint() == before
            # Reuse proven local decisions only to prepare HTTP version fixtures;
            # these are intentionally not public guide API evidence.
            decide(event)
            assert [r["calendar_date"] for r in rows(identity)] == [
                "2026-11-10",
                "2026-11-12",
            ]
            ordinary = published(event)
            assert (await send(ordinary, True))[0] == 200
            assert state(identity)["active_version_number"] == 2
            before = fingerprint()
            assert (await send(ordinary, True))[1]["data"]["replayed"]
            assert fingerprint() == before
            gap = published(event, number=4, previous=2)
            assert (await send(gap, True))[0] == 400
            assert fingerprint() == before
            critical = published(event, number=3, previous=2, severity="critical")
            critical["payload"]["working_package"]["days"][1]["date"] = "2026-11-13"
            critical["payload"]["working_package"]["assignment"]["end_date"] = (
                "2026-11-13"
            )
            assert (await send(critical, True))[0] == 200
            assert state(identity)["active_version_number"] == 2
            assert state(identity)["pending_critical_version_number"] == 3
            assert [r["calendar_date"] for r in rows(identity)] == [
                "2026-11-10",
                "2026-11-12",
            ]
            decide(event, "reject_critical", 3)
            critical["event_id"] = str(uuid4())
            critical["payload"]["version_number"] = 4
            assert (await send(critical, True))[0] == 200
            decide(event, "confirm_critical", 4)
            assert [r["calendar_date"] for r in rows(identity)] == [
                "2026-11-10",
                "2026-11-13",
            ]
            decide(event, "cancel", 4)
            assert not rows(identity)
            before = fingerprint()
            assert (await send(critical, True))[1]["data"]["replayed"]
            assert fingerprint() == before
            assert (await send(published(event, number=5, previous=4), True))[0] == 409
            assert fingerprint() == before

    asyncio.run(run())


@pytest.mark.parametrize(
    "failure",
    [
        "company",
        "tour",
        "guide",
        "role",
        "scope",
        "stale",
        "version_gap",
        "money",
        "wrong_event",
        "duplicate_json",
        "conflicting_reuse",
    ],
)
def test_version_http_validation_has_no_partial_writes(
    auth_settings, clock, keys, failure
):
    event = seed()
    status, _ = post(
        auth_settings, clock, event, token=mint_token(keys[0], scope=SCOPE_OFFERS_WRITE)
    )
    assert status == 200
    decide(event)
    version = published(event)
    p = version["payload"]
    package = p["working_package"]
    kwargs = {}
    expected = 400
    if failure == "company":
        package["company_id"] = str(uuid4())
        expected = 403
    elif failure == "tour":
        package["tour"]["id"] = str(uuid4())
    elif failure == "guide":
        package["assignment"]["guide_os_id"] = p["guide_os_id"] = str(uuid4())
        expected = 404
    elif failure == "role":
        package["assignment"]["role"] = "other"
    elif failure == "scope":
        package["days"][1]["date"] = package["assignment"]["end_date"] = "2026-11-13"
    elif failure == "stale":
        p["previous_active_version_number"] = 2
    elif failure == "version_gap":
        p["version_number"] = 3
    elif failure == "money":
        package["remuneration"] = 0
    elif failure == "wrong_event":
        version["event_type"] = "assignment.version.published.v1"
    elif failure == "duplicate_json":
        kwargs["raw"] = json.dumps(version).replace(
            '"version_number": 2', '"version_number":2,"version_number":2', 1
        )
    elif failure == "conflicting_reuse":
        status, _ = post(
            auth_settings,
            clock,
            version,
            target=path(version, version=True),
            token=mint_token(keys[0], scope=SCOPE_VERSIONS_WRITE),
        )
        assert status == 200
        package["working_conditions"]["additional_instructions"] = "Different reuse"
        expected = 409
    before = fingerprint()
    status, _ = post(
        auth_settings,
        clock,
        version,
        target=path(version, version=True),
        token=mint_token(keys[0], scope=SCOPE_VERSIONS_WRITE),
        **kwargs,
    )
    assert status == expected
    assert fingerprint() == before


def test_factory_reads_explicit_test_env_capability(
    monkeypatch, auth_settings, clock, keys
):
    monkeypatch.setenv("GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED", "true")
    monkeypatch.setenv("GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_HOST", "127.0.0.1")
    monkeypatch.setenv("GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_PORT", "8084")
    monkeypatch.setenv(FLAG, "true")
    event = seed()
    status, body = post(
        auth_settings,
        clock,
        event,
        config=None,
        token=mint_token(keys[0], scope=SCOPE_OFFERS_WRITE),
    )
    assert status == 200 and body["data"]["status"] == "applied"


def test_authenticated_legacy_to_v2_critical_intake(auth_settings, clock, keys):
    from tests.test_guide_operator_assignment_v2_intake import legacy_fixture

    legacy, event = legacy_fixture()
    critical = published(event, severity="critical")
    status, body = post(
        auth_settings,
        clock,
        critical,
        target=path(critical, version=True),
        token=mint_token(keys[0], scope=SCOPE_VERSIONS_WRITE),
    )
    assert status == 200 and body["data"]["status"] == "applied"
    assert state(legacy.assignment_id)["projection_mode"] == "legacy_range"
    assert state(legacy.assignment_id)["active_version_number"] == 1
    assert state(legacy.assignment_id)["pending_critical_version_number"] == 2
    assert not rows(legacy.assignment_id)
    decide(event, "confirm_critical", 2)
    assert state(legacy.assignment_id)["projection_mode"] == "explicit_days"
    assert [r["calendar_date"] for r in rows(legacy.assignment_id)] == [
        "2026-11-10",
        "2026-11-12",
    ]
