import asyncio
import inspect
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from pydantic import ValidationError

import database.db as db_module
from database.db import get_connection
import scripts.guide_shop_event_reconciliation as reconciliation_cli
import scripts.guide_shop_event_recovery as recovery_cli
from services.guide_shop_auth import (
    GuideShopJWTAccessTokenProvider,
    GuideShopJWTEventAccessTokenProvider,
)
from services.guide_shop_client import (
    GuideShopAuthenticationError,
    GuideShopClientError,
)
from services.guide_shop_contracts import EventEnvelopeDTO, EventListResponseDTO
from services.guide_shop_event_client import HTTPGuideShopEventFeedClient
from services.guide_shop_event_inbox import (
    EventInboxConflictError,
    GuideShopEventInboxService,
)
from services.guide_shop_event_notifications import (
    GuideShopEventNotificationService,
)
from services.guide_shop_event_pull import (
    EventCheckpoint,
    EventCheckpointRepository,
    GuideShopEventPullService,
)
from services.guide_shop_event_worker import (
    GuideShopEventRuntimeConfigurationError,
    build_guide_shop_event_worker,
)
from services.guide_shop_navigation import resolve_navigation_token
from services.guide_shop_settings import GuideShopHTTPSettings, GuideShopSettingsError
from tests.test_guide_shop_auth import key_pair, signing_settings
from tests.test_guide_shop_event_notifications import Clock, Sender
from tests.test_guide_shop_event_pull import (
    GUIDE_ID,
    OTHER_ID,
    NOW,
    Response,
    Session,
    Tokens,
    error,
    event,
    page,
)


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

RECOVERY_SCRIPT = Path(recovery_cli.__file__)
RECONCILIATION_SCRIPT = Path(reconciliation_cli.__file__)
SENSITIVE = "private-token-cursor-identity-payload-sql-path"


def run(value):
    return asyncio.run(value)


def http_client(responses, *, tokens=None, retries=1):
    session = Session(responses)
    provider = tokens or Tokens()
    client = HTTPGuideShopEventFeedClient(
        GuideShopHTTPSettings(
            "https://api.guideshop.example", "test", 5, retries, 2
        ),
        GUIDE_ID,
        provider,
        session=session,
        owns_session=False,
        sleep=AsyncMock(),
    )
    return client, session, provider


def parsed_event(**changes):
    value = event(**{key: changes.pop(key) for key in tuple(changes) if key in {"event_id", "version", "guide_id"}})
    value.update(changes)
    return EventEnvelopeDTO.model_validate(value)


def feed_page(events, cursor="cursor_security_01"):
    return EventListResponseDTO.model_validate(page(events, cursor, False))


class Feed:
    def __init__(self, response):
        self.response = response

    async def fetch_events(self, *, cursor=None, limit=20):
        return self.response


def pull_service(response, identity=GUIDE_ID):
    return GuideShopEventPullService(
        client=Feed(response),
        inbox=GuideShopEventInboxService(clock=lambda: NOW),
        checkpoint=EventCheckpointRepository(),
        expected_guide_os_id=identity,
        clock=lambda: NOW,
    )


# JWT and HTTP boundary (10 cases)


def test_security_event_scope_is_fixed_separate_and_not_caller_selectable(
    signing_settings,
):
    event_provider = GuideShopJWTEventAccessTokenProvider(signing_settings)
    read_provider = GuideShopJWTAccessTokenProvider(signing_settings)
    event_claims = jwt.decode(
        run(event_provider.get_access_token(GUIDE_ID)),
        options={"verify_signature": False},
    )
    read_claims = jwt.decode(
        run(read_provider.get_access_token(GUIDE_ID)),
        options={"verify_signature": False},
    )
    assert event_claims["scope"] == "guideshop:events"
    assert read_claims["scope"] == "guideshop:read"
    assert "scope" not in inspect.signature(
        GuideShopJWTEventAccessTokenProvider
    ).parameters
    with pytest.raises(TypeError):
        GuideShopJWTEventAccessTokenProvider(
            signing_settings, scope="guideshop:read"
        )


def test_security_retry_uses_fresh_token_and_jti(signing_settings):
    provider = GuideShopJWTEventAccessTokenProvider(signing_settings)
    client, session, _ = http_client(
        [
            Response(503, error("temporarily_unavailable", 1)),
            Response(payload=page([], None, False)),
        ],
        tokens=provider,
    )
    run(client.fetch_events())
    tokens = [
        request[2]["headers"]["Authorization"].removeprefix("Bearer ")
        for request in session.requests
    ]
    claims = [jwt.decode(token, options={"verify_signature": False}) for token in tokens]
    assert len(set(tokens)) == 2
    assert len({claim["jti"] for claim in claims}) == 2
    assert {claim["scope"] for claim in claims} == {"guideshop:events"}


@pytest.mark.parametrize("token", ["", None, "bad token\nvalue"])
def test_security_invalid_event_token_fails_before_http(token):
    provider = SimpleNamespace(get_access_token=AsyncMock(return_value=token))
    client, session, _ = http_client([], tokens=provider)
    with pytest.raises(GuideShopAuthenticationError):
        run(client.fetch_events())
    assert session.requests == []


@pytest.mark.parametrize("status", [400, 401, 403, 429, 503])
def test_security_error_envelopes_do_not_expose_body_token_or_cursor(
    status, caplog
):
    payload = error(
        "rate_limited" if status == 429 else
        "temporarily_unavailable" if status == 503 else
        "unauthenticated" if status == 401 else
        "link_not_active" if status == 403 else "invalid_request",
        1 if status in {429, 503} else None,
    )
    payload["message"] = SENSITIVE
    responses = [Response(status, payload)] * (2 if status in {429, 503} else 1)
    client, _, _ = http_client(responses)
    with pytest.raises(GuideShopClientError) as caught:
        run(client.fetch_events(cursor="cursor_security_01"))
    combined = str(caught.value) + caplog.text
    assert SENSITIVE not in combined
    assert "cursor_security_01" not in combined
    assert "event-token" not in combined


def test_security_redirects_are_never_followed_or_cross_hosted():
    redirect = Response(302, error("invalid_request"))
    redirect.headers["Location"] = "https://attacker.example/steal"
    client, session, _ = http_client([redirect])
    with pytest.raises(GuideShopClientError):
        run(client.fetch_events())
    assert len(session.requests) == 1
    assert session.requests[0][2]["allow_redirects"] is False
    assert session.requests[0][1].startswith("https://api.guideshop.example/")


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_security_https_is_required_for_deployed_environments(environment):
    with pytest.raises(GuideShopSettingsError):
        GuideShopHTTPSettings("http://api.guideshop.example", environment)


@pytest.mark.parametrize("limit", [0, 51, True, "20"])
def test_security_event_limit_is_strict_and_rejected_before_http(limit):
    client, session, _ = http_client([])
    with pytest.raises(GuideShopClientError):
        run(client.fetch_events(limit=limit))
    assert session.requests == []


@pytest.mark.parametrize(
    "cursor",
    ["", "short", "cursor value", "cursor%0d%0aInjected", "x" * 257],
)
def test_security_injection_cursor_is_rejected_before_http(cursor):
    client, session, _ = http_client([])
    with pytest.raises(GuideShopClientError) as caught:
        run(client.fetch_events(cursor=cursor))
    assert session.requests == []
    if cursor:
        assert cursor not in str(caught.value)


def test_security_oversized_malformed_and_unknown_responses_fail_closed():
    oversized = Response(payload=page([], None, False))
    oversized.content_length = 1_000_001
    malformed = Response(payload=page([], None, False))
    malformed.content.body = b"{" + SENSITIVE.encode()
    unknown = page([], None, False)
    unknown["unexpected"] = SENSITIVE
    for response in (oversized, malformed, Response(payload=unknown)):
        client, _, _ = http_client([response])
        with pytest.raises(GuideShopClientError) as caught:
            run(client.fetch_events())
        assert SENSITIVE not in str(caught.value)


# Event authenticity and isolation (7 cases)


def test_security_mixed_principal_page_has_no_inbox_or_checkpoint_writes():
    response = feed_page(
        [parsed_event(), parsed_event(event_id="evt_00000002", guide_id=OTHER_ID)]
    )
    with pytest.raises(ValueError, match="event identity mismatch"):
        run(pull_service(response).pull_once())
    conn = get_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM guide_shop_event_inbox").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM guide_shop_event_checkpoints").fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize(
    "mutation",
    [
        {"producer": "forged"},
        {"event_version": "v2"},
        {"schema_version": "2.0.0"},
        {"event_type": "sale.created"},
        {"event_type": "points.credited"},
        {"data": {"amount": "999.00"}},
    ],
)
def test_security_forged_event_contract_fields_fail_closed(mutation):
    value = event()
    value.update(mutation)
    with pytest.raises(ValidationError):
        EventEnvelopeDTO.model_validate(value)


def test_security_identical_retry_and_changed_content_conflict():
    inbox = GuideShopEventInboxService(clock=lambda: NOW)
    original = parsed_event()
    assert inbox.ingest(original, expected_guide_os_id=GUIDE_ID).outcome.value == "inserted"
    assert inbox.ingest(original, expected_guide_os_id=GUIDE_ID).outcome.value == "duplicate"
    with pytest.raises(EventInboxConflictError):
        inbox.ingest(parsed_event(version=2), expected_guide_os_id=GUIDE_ID)
    conn = get_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM guide_shop_event_inbox").fetchone()[0] == 1
    finally:
        conn.close()


def test_security_inbox_watermark_and_checkpoint_are_principal_isolated():
    inbox = GuideShopEventInboxService(clock=lambda: NOW)
    first = parsed_event()
    second = parsed_event(event_id="evt_00000002", guide_id=OTHER_ID)
    inbox.ingest(first, expected_guide_os_id=GUIDE_ID)
    inbox.ingest(second, expected_guide_os_id=OTHER_ID)
    repo = EventCheckpointRepository()
    assert repo.advance(GUIDE_ID, expected=repo.load(GUIDE_ID), next_cursor="cursor_guide_a01", updated_at=NOW)
    assert repo.advance(OTHER_ID, expected=repo.load(OTHER_ID), next_cursor="cursor_guide_b01", updated_at=NOW)
    assert inbox.get_watermark(guide_os_id=GUIDE_ID, subject_type="visit", subject_id="vis_00000001").event_id == first.event_id
    assert inbox.get_watermark(guide_os_id=OTHER_ID, subject_type="visit", subject_id="vis_00000001").event_id == second.event_id
    assert repo.load(GUIDE_ID).cursor == "cursor_guide_a01"
    assert repo.load(OTHER_ID).cursor == "cursor_guide_b01"


def test_security_concurrent_duplicate_race_has_one_insert_and_one_duplicate():
    barrier = threading.Barrier(2)
    outcomes = []

    def ingest():
        barrier.wait()
        result = GuideShopEventInboxService(clock=lambda: NOW).ingest(
            parsed_event(), expected_guide_os_id=GUIDE_ID
        )
        outcomes.append(result.outcome.value)

    threads = [threading.Thread(target=ingest) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive()
    assert sorted(outcomes) == ["duplicate", "inserted"]


def test_security_concurrent_conflict_race_has_one_safe_winner():
    barrier = threading.Barrier(2)
    outcomes = []

    def ingest(version):
        barrier.wait()
        try:
            result = GuideShopEventInboxService(clock=lambda: NOW).ingest(
                parsed_event(version=version), expected_guide_os_id=GUIDE_ID
            )
            outcomes.append(result.outcome.value)
        except EventInboxConflictError:
            outcomes.append("conflict")

    threads = [threading.Thread(target=ingest, args=(version,)) for version in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive()
    assert sorted(outcomes) == ["conflict", "inserted"]


# Notification safety (4 cases)


def _map_user(user_id, guide_id):
    conn = get_connection()
    conn.execute("INSERT INTO users (user_id, guide_os_id) VALUES (?, ?)", (user_id, guide_id))
    conn.commit()
    conn.close()


def test_security_notification_recipient_text_and_subject_navigation_are_isolated():
    clock = Clock()
    inbox = GuideShopEventInboxService(clock=clock)
    sender = Sender()
    _map_user(7001, GUIDE_ID)
    _map_user(7002, OTHER_ID)
    value = event()
    value["subject"]["id"] = "vis_sensitive_object_01"
    envelope = EventEnvelopeDTO.model_validate(value)
    inbox.ingest(envelope, expected_guide_os_id=GUIDE_ID)
    service = GuideShopEventNotificationService(
        inbox=inbox, sender=sender, bot_username="GuideOSBot", clock=clock
    )
    assert run(service.process_one()).outcome == "delivered"
    recipient, text, link = sender.calls[0]
    assert recipient == 7001
    for forbidden in (GUIDE_ID, OTHER_ID, "vis_sensitive_object_01", "999.00", "Private Name", SENSITIVE):
        assert forbidden not in text
    token = link.split("?start=", 1)[1]
    route = resolve_navigation_token(token, 7001, now=clock())
    assert (route.kind, route.object_id) == ("visit_detail", "vis_sensitive_object_01")


def test_security_deep_link_and_sender_exception_are_never_logged(caplog):
    clock = Clock()
    inbox = GuideShopEventInboxService(clock=clock)
    sender = Sender(RuntimeError(SENSITIVE))
    _map_user(7001, GUIDE_ID)
    inbox.ingest(parsed_event(), expected_guide_os_id=GUIDE_ID)
    service = GuideShopEventNotificationService(
        inbox=inbox, sender=sender, bot_username="GuideOSBot", clock=clock
    )
    run(service.process_one())
    token = sender.calls[0][2].split("?start=", 1)[1]
    assert token not in caplog.text
    assert SENSITIVE not in caplog.text
    assert GUIDE_ID not in caplog.text


def test_security_stale_worker_cannot_deliver_newer_attempt():
    clock = Clock()
    inbox = GuideShopEventInboxService(clock=clock)
    inbox.ingest(parsed_event(), expected_guide_os_id=GUIDE_ID)
    first = inbox.claim_due()
    assert inbox.mark_failed(first).transitioned is True
    clock.advance()
    second = inbox.claim_due()
    assert inbox.mark_delivered(first) is False
    assert inbox.get_event(first.event.event_id).state == "processing"
    assert inbox.mark_delivered(second) is True


def test_security_event_controlled_text_cannot_enter_known_presentations():
    source = inspect.getsource(GuideShopEventNotificationService.process_one)
    assert "event.event_type" in source
    assert "presentation[0]" in source
    assert "event.subject_id" not in source.split("self._sender.send", 1)[1]


# Operational command safety (6 cases)


@pytest.mark.parametrize(
    ("parser", "argv"),
    [
        (recovery_cli._parser, ["unknown-" + SENSITIVE]),
        (recovery_cli._parser, ["recover-abandoned", "--unknown=" + SENSITIVE]),
    ],
)
def test_security_recovery_rejects_unknown_input_with_fixed_output(parser, argv, capsys):
    with pytest.raises(SystemExit) as caught:
        parser().parse_args(argv)
    output = capsys.readouterr()
    assert caught.value.code == 2
    assert output.out == ""
    assert output.err == "action=EXECUTION_FAILURE\n"


@pytest.mark.parametrize("limit", ["0", "101", "-1", SENSITIVE])
def test_security_recovery_limit_is_strict_and_sanitized(limit, capsys):
    with pytest.raises(SystemExit):
        recovery_cli._parser().parse_args(["recover-abandoned", "--limit", limit])
    captured = capsys.readouterr()
    assert captured.err == "action=EXECUTION_FAILURE\n"
    assert limit not in captured.err


def test_security_recovery_defaults_to_dry_run_and_has_only_two_actions():
    parser = recovery_cli._parser()
    for action in ("recover-abandoned", "replay-dead-letter"):
        args = parser.parse_args([action])
        assert args.apply is False
        assert args.limit == 100
    with pytest.raises(SystemExit):
        parser.parse_args(["delete"])


def test_security_reconciliation_has_no_mutation_or_argument_surface(monkeypatch, capsys):
    monkeypatch.setattr(reconciliation_cli.sys, "argv", ["reconciliation", "--apply"])
    assert reconciliation_cli.main() == 1
    assert capsys.readouterr().out == "verdict=EXECUTION_FAILURE\n"
    source = RECONCILIATION_SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("--apply", "replay", "reset", "delete"):
        assert forbidden not in source


def test_security_commands_accept_no_shell_or_sql_and_import_no_runtime_network():
    sources = [
        RECOVERY_SCRIPT.read_text(encoding="utf-8"),
        RECONCILIATION_SCRIPT.read_text(encoding="utf-8"),
    ]
    combined = "\n".join(sources)
    for forbidden in (
        "subprocess", "os.system", "shell=True", "import bot", "import config",
        "aiogram", "aiohttp", "BOT_TOKEN",
    ):
        assert forbidden not in combined
    assert set(inspect.signature(recovery_cli.main).parameters) == {"argv"}
    assert inspect.signature(reconciliation_cli.main).parameters == {}


def test_security_command_failures_hide_identifiers_paths_sql_and_exceptions(
    monkeypatch, capsys
):
    class FailingService:
        def __init__(self, **kwargs):
            pass

        def recover_abandoned(self, **kwargs):
            raise RuntimeError(SENSITIVE)

    monkeypatch.setattr(recovery_cli, "GuideShopEventInboxService", FailingService)
    assert recovery_cli.main(["recover-abandoned"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "action=recover-abandoned failure_count=1\n"
    assert SENSITIVE not in captured.err


# Default-off boundary (4 cases)


def test_security_default_off_builds_no_worker_client_or_network(monkeypatch):
    bot = SimpleNamespace(get_me=AsyncMock(side_effect=AssertionError("telegram")))
    monkeypatch.setattr(
        "aiohttp.ClientSession", Mock(side_effect=AssertionError("network"))
    )
    assert run(build_guide_shop_event_worker(bot, {
        "GUIDESHOP_EVENTS_ENABLED": "false",
        "GUIDESHOP_NOTIFICATIONS_ENABLED": "false",
    })) is None
    bot.get_me.assert_not_awaited()


def test_security_notifications_without_events_fail_closed():
    with pytest.raises(GuideShopEventRuntimeConfigurationError):
        run(build_guide_shop_event_worker(SimpleNamespace(), {
            "GUIDESHOP_EVENTS_ENABLED": "false",
            "GUIDESHOP_NOTIFICATIONS_ENABLED": "true",
        }))


def test_security_api_only_entrypoint_has_no_event_worker_import_or_start():
    source = Path("guide_shop_link_api.py").read_text(encoding="utf-8")
    assert "guide_shop_event_worker" not in source
    assert "build_guide_shop_event_worker" not in source
    assert "start_guide_shop_event_worker" not in source


def test_security_normal_read_provider_remains_read_scoped(signing_settings):
    provider = GuideShopJWTAccessTokenProvider(signing_settings)
    claims = jwt.decode(
        run(provider.get_access_token(GUIDE_ID)),
        options={"verify_signature": False},
    )
    assert claims["scope"] == "guideshop:read"
    assert not hasattr(provider, "fetch_events")
