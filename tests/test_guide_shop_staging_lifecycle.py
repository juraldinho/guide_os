import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import jwt
import pytest

from database.db import get_connection
from database.queries import get_guide_os_id, get_user_id_by_guide_os_id, register_user
from services.guide_shop_inbound_auth import GuideShopInboundJWTVerifier
from services.guide_shop_link_exchange_service import GuideShopLinkExchangeService
from services.guide_shop_link_provider import create_guide_shop_link_provider_app
from services.guide_shop_settings import (
    GuideShopInboundJWTSettings,
    GuideShopStagingLifecycleSettings,
    GuideShopStagingLifecycleSettingsError,
)
from services.guide_shop_staging_lifecycle_auth import (
    AUDIENCE,
    ISSUER,
    SCOPE_CONFIRM,
    SCOPE_ISSUE,
    SCOPE_REVOKE,
    TOKEN_TYPE,
    GuideShopStagingLifecycleJWTVerifier,
)
from tests.test_guide_shop_link_provider import DirectClient, bearer, post_body, run
from utils.guide_os_identity import new_guide_os_id


NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
LINK_KID = "link-key-2026"
LIFE_KID = "life-key-2026"


def _pem_pair():
    key = Ed25519PrivateKey.generate()
    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return key, pem


@pytest.fixture
def keys():
    link_key, link_pem = _pem_pair()
    life_key, life_pem = _pem_pair()
    return {
        "link_key": link_key,
        "link_pem": link_pem,
        "life_key": life_key,
        "life_pem": life_pem,
    }


def _components(keys, *, lifecycle=True):
    inbound = GuideShopInboundJWTSettings("test", {LINK_KID: keys["link_pem"]})
    verifier = GuideShopInboundJWTVerifier(inbound, clock=lambda: NOW)
    service = GuideShopLinkExchangeService(clock=lambda: NOW)
    lifecycle_verifier = None
    if lifecycle:
        settings = GuideShopStagingLifecycleSettings(
            True, "staging", {LIFE_KID: keys["life_pem"]}
        )
        lifecycle_verifier = GuideShopStagingLifecycleJWTVerifier(
            settings, clock=lambda: NOW
        )
    app = create_guide_shop_link_provider_app(
        verifier, service, lifecycle_verifier=lifecycle_verifier
    )
    return app, service


def life_bearer(keys, scope, jti, guide_os_id, **changes):
    issued_at = int(NOW.timestamp())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": guide_os_id,
        "scope": scope,
        "iat": issued_at,
        "exp": issued_at + 60,
        "jti": jti,
    }
    claims.update(changes)
    token = jwt.encode(
        claims,
        keys["life_key"],
        algorithm="EdDSA",
        headers={"kid": LIFE_KID, "typ": TOKEN_TYPE},
    )
    return {"Authorization": f"Bearer {token}"}


def test_lifecycle_settings_default_off_and_production_impossible():
    assert GuideShopStagingLifecycleSettings.from_env({}) == (
        GuideShopStagingLifecycleSettings()
    )
    assert GuideShopStagingLifecycleSettings.from_env(
        {"GUIDESHOP_STAGING_LIFECYCLE_ENABLED": "false"}
    ).enabled is False
    with pytest.raises(GuideShopStagingLifecycleSettingsError):
        GuideShopStagingLifecycleSettings.from_env(
            {
                "GUIDESHOP_STAGING_LIFECYCLE_ENABLED": "true",
                "APP_ENV": "production",
                "GUIDESHOP_STAGING_LIFECYCLE_JWT_PUBLIC_KEYS": "{}",
            }
        )
    with pytest.raises(GuideShopStagingLifecycleSettingsError):
        GuideShopStagingLifecycleSettings.from_env(
            {
                "GUIDESHOP_STAGING_LIFECYCLE_ENABLED": "true",
                "APP_ENV": "staging",
                "GUIDESHOP_STAGING_LIFECYCLE_JWT_PUBLIC_KEYS": "{}",
            }
        )
    with pytest.raises(GuideShopStagingLifecycleSettingsError):
        GuideShopStagingLifecycleSettings.from_env(
            {
                "GUIDESHOP_STAGING_LIFECYCLE_ENABLED": "true",
                "APP_ENV": "test",
                "GUIDESHOP_STAGING_LIFECYCLE_JWT_PUBLIC_KEYS": json.dumps(
                    {"life-key-2026": "not-a-pem"}
                ),
            }
        )


def test_disabled_lifecycle_surface_is_not_found(keys):
    app, _service = _components(keys, lifecycle=False)
    guide_os_id = new_guide_os_id()

    async def exercise(client):
        response = await client.post(
            "/integration/v1/staging/link-tokens",
            json={"schema_version": "1.0.0"},
            headers=life_bearer(
                keys, SCOPE_ISSUE, "disabled-issue-jti-01", guide_os_id
            ),
        )
        assert response.status == 404

    run(_with(app, exercise))


def _with(app, action):
    return action(DirectClient(app))


def test_issue_confirm_revoke_and_idempotent_evidence(keys):
    app, service = _components(keys)
    register_user(101)
    guide_os_id = get_guide_os_id(101)

    async def exercise(client):
        issued = await client.post(
            "/integration/v1/staging/link-tokens",
            json={"schema_version": "1.0.0"},
            headers=life_bearer(keys, SCOPE_ISSUE, "life-issue-jti-000001", guide_os_id),
        )
        body = await issued.json()
        assert issued.status == 201
        raw_token = body["raw_link_token"]
        assert 24 <= len(raw_token) <= 256
        assert body["guide_os_id"] == guide_os_id
        assert body["audience"] == "guideshop-link"
        assert "BEGIN" not in json.dumps(body)

        created = await client.post(
            "/integration/v1/link-exchanges",
            json=post_body(raw_link_token=raw_token),
            headers=bearer(
                keys["link_key"], "guideshop:link:exchange", "life-exch-jti-000001"
            ),
        )
        exchange = await created.json()
        assert created.status == 201
        assert exchange["status"] == "awaiting_guide_confirmation"
        exchange_id = exchange["link_exchange_id"]

        replay = await client.post(
            "/integration/v1/link-exchanges",
            json=post_body(raw_link_token=raw_token),
            headers=bearer(
                keys["link_key"], "guideshop:link:exchange", "life-exch-jti-000002"
            ),
        )
        assert replay.status == 422

        confirmed = await client.post(
            f"/integration/v1/staging/link-exchanges/{exchange_id}/confirm",
            json={"schema_version": "1.1.0"},
            headers=life_bearer(
                keys, SCOPE_CONFIRM, "life-confirm-jti-0001", guide_os_id
            ),
        )
        active = await confirmed.json()
        assert confirmed.status == 200
        assert active["status"] == "active"
        evidence = service.get_evidence_for_guide(exchange_id, guide_os_id)
        assert evidence.status == "active"
        assert evidence.occurred_at == NOW
        first_ref = evidence.evidence_ref

        again = await client.post(
            f"/integration/v1/staging/link-exchanges/{exchange_id}/confirm",
            json={"schema_version": "1.1.0"},
            headers=life_bearer(
                keys, SCOPE_CONFIRM, "life-confirm-jti-0002", guide_os_id
            ),
        )
        assert again.status == 200
        assert (await again.json())["status"] == "active"
        again_evidence = service.get_evidence_for_guide(exchange_id, guide_os_id)
        assert again_evidence.evidence_ref == first_ref
        assert again_evidence.occurred_at == NOW

        revoked = await client.post(
            f"/integration/v1/staging/link-exchanges/{exchange_id}/revoke",
            json={"schema_version": "1.1.0"},
            headers=life_bearer(
                keys, SCOPE_REVOKE, "life-revoke-jti-00001", guide_os_id
            ),
        )
        assert revoked.status == 200
        assert (await revoked.json())["status"] == "revoked"
        rev_evidence = service.get_evidence_for_guide(exchange_id, guide_os_id)
        assert rev_evidence.status == "revoked"
        assert rev_evidence.occurred_at == NOW
        assert rev_evidence.evidence_ref != first_ref

        revoked_again = await client.post(
            f"/integration/v1/staging/link-exchanges/{exchange_id}/revoke",
            json={"schema_version": "1.1.0"},
            headers=life_bearer(
                keys, SCOPE_REVOKE, "life-revoke-jti-00002", guide_os_id
            ),
        )
        assert revoked_again.status == 200
        assert service.get_evidence_for_guide(exchange_id, guide_os_id) == rev_evidence

        conn = get_connection()
        dump = " ".join(
            str(value)
            for table in (
                "guide_shop_link_requests",
                "guide_shop_link_exchanges",
                "guide_shop_link_exchange_evidence",
            )
            for row in conn.execute(f"SELECT * FROM {table}")
            for value in row
        )
        token_count = conn.execute(
            "SELECT COUNT(*) FROM guide_shop_link_requests"
        ).fetchone()[0]
        evidence_count = conn.execute(
            "SELECT COUNT(*) FROM guide_shop_link_exchange_evidence"
        ).fetchone()[0]
        conn.close()
        assert raw_token not in dump
        assert token_count == 1
        assert evidence_count == 2
        return raw_token

    run(_with(app, exercise))
    assert get_user_id_by_guide_os_id(guide_os_id) == 101


def test_bootstrap_creates_staging_user_without_telegram_id(keys):
    app, _service = _components(keys)
    guide_os_id = new_guide_os_id()

    async def exercise(client):
        response = await client.post(
            "/integration/v1/staging/link-tokens",
            headers=life_bearer(
                keys, SCOPE_ISSUE, "life-bootstrap-jti-01", guide_os_id
            ),
        )
        body = await response.json()
        assert response.status == 201
        assert body["guide_os_id"] == guide_os_id
        user_id = get_user_id_by_guide_os_id(guide_os_id)
        assert user_id is not None and user_id < 0

    run(_with(app, exercise))


@pytest.mark.parametrize(
    "mutate",
    [
        {"iss": "guideshop-integration"},
        {"aud": "guide-os-integration"},
        {"scope": SCOPE_CONFIRM},
        {"sub": "not-a-uuid"},
        {"exp": int(NOW.timestamp()) - 11, "iat": int(NOW.timestamp()) - 40},
        {"iat": int(NOW.timestamp()) + 120, "exp": int(NOW.timestamp()) + 150},
    ],
)
def test_lifecycle_jwt_fail_closed_before_issue(keys, mutate):
    app, _service = _components(keys)
    guide_os_id = new_guide_os_id()
    issued_scope = mutate.get("scope", SCOPE_ISSUE)
    claim_overrides = {key: value for key, value in mutate.items() if key != "scope"}

    async def exercise(client):
        headers = life_bearer(
            keys,
            issued_scope,
            "life-neg-jti-" + hashlib.sha256(
                json.dumps(mutate, sort_keys=True).encode()
            ).hexdigest()[:16],
            guide_os_id,
            **claim_overrides,
        )
        response = await client.post(
            "/integration/v1/staging/link-tokens", headers=headers
        )
        assert response.status == 401
        assert get_user_id_by_guide_os_id(guide_os_id) is None

    run(_with(app, exercise))


def test_wrong_signing_key_and_jti_replay_fail_closed(keys):
    app, _service = _components(keys)
    guide_os_id = new_guide_os_id()
    other_key, _pem = _pem_pair()

    async def exercise(client):
        issued_at = int(NOW.timestamp())
        token = jwt.encode(
            {
                "iss": ISSUER,
                "aud": AUDIENCE,
                "sub": guide_os_id,
                "scope": SCOPE_ISSUE,
                "iat": issued_at,
                "exp": issued_at + 60,
                "jti": "life-wrong-key-jti-01",
            },
            other_key,
            algorithm="EdDSA",
            headers={"kid": LIFE_KID, "typ": TOKEN_TYPE},
        )
        wrong = await client.post(
            "/integration/v1/staging/link-tokens",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert wrong.status == 401
        first = await client.post(
            "/integration/v1/staging/link-tokens",
            headers=life_bearer(
                keys, SCOPE_ISSUE, "life-replay-jti-00001", guide_os_id
            ),
        )
        second = await client.post(
            "/integration/v1/staging/link-tokens",
            headers=life_bearer(
                keys, SCOPE_ISSUE, "life-replay-jti-00001", guide_os_id
            ),
        )
        assert first.status == 201
        assert second.status == 401

    run(_with(app, exercise))


def test_foreign_guide_cannot_confirm_or_revoke(keys):
    app, _service = _components(keys)
    register_user(101)
    register_user(202)
    owner = get_guide_os_id(101)
    foreign = get_guide_os_id(202)

    async def exercise(client):
        issued = await (
            await client.post(
                "/integration/v1/staging/link-tokens",
                headers=life_bearer(keys, SCOPE_ISSUE, "life-own-issue-jti-01", owner),
            )
        ).json()
        created = await (
            await client.post(
                "/integration/v1/link-exchanges",
                json=post_body(raw_link_token=issued["raw_link_token"]),
                headers=bearer(
                    keys["link_key"], "guideshop:link:exchange", "life-own-exch-jti-01"
                ),
            )
        ).json()
        exchange_id = created["link_exchange_id"]
        confirm = await client.post(
            f"/integration/v1/staging/link-exchanges/{exchange_id}/confirm",
            headers=life_bearer(
                keys, SCOPE_CONFIRM, "life-foreign-confirm-01", foreign
            ),
        )
        revoke = await client.post(
            f"/integration/v1/staging/link-exchanges/{exchange_id}/revoke",
            headers=life_bearer(
                keys, SCOPE_REVOKE, "life-foreign-revoke-001", foreign
            ),
        )
        assert confirm.status == revoke.status == 404
        status = await client.get(
            f"/integration/v1/link-exchanges/{exchange_id}",
            headers=bearer(
                keys["link_key"], "guideshop:link:status", "life-own-status-jti"
            ),
        )
        assert (await status.json())["status"] == "awaiting_guide_confirmation"

    run(_with(app, exercise))


def test_conflicting_terminal_confirm_after_revoke_fails_closed(keys):
    app, service = _components(keys)
    register_user(101)
    guide_os_id = get_guide_os_id(101)

    async def exercise(client):
        issued = await (
            await client.post(
                "/integration/v1/staging/link-tokens",
                headers=life_bearer(
                    keys, SCOPE_ISSUE, "life-conflict-issue-01", guide_os_id
                ),
            )
        ).json()
        created = await (
            await client.post(
                "/integration/v1/link-exchanges",
                json=post_body(raw_link_token=issued["raw_link_token"]),
                headers=bearer(
                    keys["link_key"],
                    "guideshop:link:exchange",
                    "life-conflict-exch-01",
                ),
            )
        ).json()
        exchange_id = created["link_exchange_id"]
        await client.post(
            f"/integration/v1/staging/link-exchanges/{exchange_id}/revoke",
            headers=life_bearer(
                keys, SCOPE_REVOKE, "life-conflict-revoke-01", guide_os_id
            ),
        )
        confirm = await client.post(
            f"/integration/v1/staging/link-exchanges/{exchange_id}/confirm",
            headers=life_bearer(
                keys, SCOPE_CONFIRM, "life-conflict-confirm-01", guide_os_id
            ),
        )
        assert confirm.status == 422
        assert service.get_evidence_for_guide(exchange_id, guide_os_id).status == "revoked"

    run(_with(app, exercise))


def test_concurrent_confirm_writes_one_evidence_row(keys):
    app, service = _components(keys)
    register_user(101)
    guide_os_id = get_guide_os_id(101)

    async def exercise(client):
        issued = await (
            await client.post(
                "/integration/v1/staging/link-tokens",
                headers=life_bearer(
                    keys, SCOPE_ISSUE, "life-conc-issue-jti-01", guide_os_id
                ),
            )
        ).json()
        created = await (
            await client.post(
                "/integration/v1/link-exchanges",
                json=post_body(raw_link_token=issued["raw_link_token"]),
                headers=bearer(
                    keys["link_key"], "guideshop:link:exchange", "life-conc-exch-jti"
                ),
            )
        ).json()
        exchange_id = created["link_exchange_id"]
        responses = await asyncio.gather(
            *[
                client.post(
                    f"/integration/v1/staging/link-exchanges/{exchange_id}/confirm",
                    headers=life_bearer(
                        keys,
                        SCOPE_CONFIRM,
                        f"life-conc-confirm-jti{index}",
                        guide_os_id,
                    ),
                )
                for index in range(2)
            ]
        )
        statuses = sorted(response.status for response in responses)
        assert statuses[0] == 200
        assert statuses[1] in {200, 422}
        conn = get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM guide_shop_link_exchange_evidence"
        ).fetchone()[0]
        conn.close()
        assert count == 1
        assert service.get_evidence_for_guide(exchange_id, guide_os_id).status == "active"

    run(_with(app, exercise))
