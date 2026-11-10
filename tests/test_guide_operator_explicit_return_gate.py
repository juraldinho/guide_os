"""Default-off explicit return delivery, using the frozen compatible v1 envelopes."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from database.db import get_db_connection
from services.guide_operator_outbound_delivery import deliver_one
from services.guide_operator_outbound_settings import (
    GuideOperatorOutboundConfigurationError,
    GuideOperatorOutboundSettings,
)
from tests.test_guide_operator_daily_projections import apply, seed
from tests.test_guide_operator_outbound_delivery import (
    FakeHttp,
    _ack,
)
from tests.test_guide_operator_outbound_delivery import (
    auth_settings as auth_settings,  # noqa: PLC0414
)
from tests.test_guide_operator_outbound_delivery import (
    keys as keys,  # noqa: PLC0414
)
from tests.test_guide_operator_outbound_delivery import (
    outbound_settings as outbound_settings,  # noqa: PLC0414
)


def test_default_hold_and_opt_in_preserve_wire(outbound_settings):
    fixture = seed()
    apply(fixture)
    with get_db_connection() as conn:
        before = dict(
            conn.execute(
                "SELECT * FROM guide_operator_outbox WHERE aggregate_id=?",
                (fixture[1],),
            ).fetchone()
        )
    client = FakeHttp()

    def now():
        return datetime(2026, 11, 5, tzinfo=UTC)

    assert (
        deliver_one(
            settings=outbound_settings,
            http_client=client,
            clock=now,
            event_id=before["event_id"],
        )
        is None
    )
    assert client.calls == []
    with get_db_connection() as conn:
        assert (
            dict(
                conn.execute(
                    "SELECT * FROM guide_operator_outbox WHERE event_id=?",
                    (before["event_id"],),
                ).fetchone()
            )
            == before
        )
    client.responses = [_ack(before["event_id"], before["event_type"])]
    enabled = replace(outbound_settings, explicit_days_return_enabled=True)
    result = deliver_one(
        settings=enabled, http_client=client, clock=now, event_id=before["event_id"]
    )
    assert result.outcome == "delivered" and result.attempt_count == 1
    assert len(client.calls) == 1
    with get_db_connection() as conn:
        row = dict(
            conn.execute(
                "SELECT * FROM guide_operator_outbox WHERE event_id=?",
                (before["event_id"],),
            ).fetchone()
        )
        assert row["payload_json"] == before["payload_json"]
    assert (
        deliver_one(
            settings=enabled, http_client=client, clock=now, event_id=before["event_id"]
        )
        is None
    )


def test_settings_default_and_explicit_env_gate(auth_settings):
    values = {
        "APP_ENV": "test",
        "GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_ENABLED": "true",
        "GUIDE_OS_GUIDE_OPERATOR_BASE_URL": "http://127.0.0.1:9000",
    }
    assert not GuideOperatorOutboundSettings.from_env(
        values, auth_settings=auth_settings
    ).explicit_days_return_enabled
    values["GUIDE_OS_GUIDE_OPERATOR_EXPLICIT_DAYS_RETURN_ENABLED"] = "true"
    assert GuideOperatorOutboundSettings.from_env(
        values, auth_settings=auth_settings
    ).explicit_days_return_enabled
    values["GUIDE_OS_GUIDE_OPERATOR_EXPLICIT_DAYS_RETURN_ENABLED"] = "unknown"
    with pytest.raises(GuideOperatorOutboundConfigurationError):
        GuideOperatorOutboundSettings.from_env(values, auth_settings=auth_settings)
