# GO13J1 Guide OS production consolidated runtime

> Сводка обновлена 2026-10-29 по записанным release evidence: [реализация и окружения](CURRENT_STATE.md). Исторические PASS относятся к своим датам; эта docs-правка не является новым live-аудитом.

Status update 2026-10-29: this launcher is already used by the production Guide OS runtime. Latest artifact release and pre/post checks are recorded in [reminder handoff](REMINDER_MINIAPP_LINK.md). The phased gates below remain a rollout reference, not permission for new changes or a full GO production E2E claim.

## Runtime and command

The proposed GO13J1 topology keeps one Guide OS runtime Railway service with exactly
one replica and one SQLite volume mounted at `/data`. After explicit rollout approval, the candidate command is:

```sh
python guide_os_production_runtime.py
```

The launcher runs `bot.main(polling_handle_signals=False)` exactly once. The
existing bot lifecycle continues to own Telegram polling, the Mini App API, the
Guide Operator notification worker, GuideShop tasks, reminders and cleanup.
The launcher never starts another poller or notification worker.

The Guide Operator integration API and outbound worker reuse their existing
implementations and share the same `DATABASE_PATH`. The launcher owns
SIGINT/SIGTERM, requests component shutdown, cancels the bot task so its existing
cleanup runs, and stops the whole runtime if an enabled component exits.

## Required production variable names

Core runtime:

- `APP_ENV`
- `DATABASE_PATH`
- `GUIDE_OS_CONSOLIDATED_PRODUCTION_RUNTIME_ENABLED`
- `GUIDE_OS_CONSOLIDATED_PRODUCTION_REPLICA_COUNT`
- `GUIDE_OS_CONSOLIDATED_PRODUCTION_SHUTDOWN_TIMEOUT_SECONDS`
- `MINI_APP_API_ENABLED`
- `MINI_APP_API_HOST`
- `MINI_APP_API_PORT`

Guide Operator intake:

- `GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED`
- `GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_HOST`
- `GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_PORT`
- `GUIDE_OS_SERVICE_AUTH_ENABLED`
- `GUIDE_OS_GUIDE_OPERATOR_JWT_PUBLIC_KEYS`
- `GUIDE_OS_SIGNING_KID`
- `GUIDE_OS_SIGNING_PRIVATE_KEY_PEM`

Guide Operator outbound:

- `GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_ENABLED`
- `GUIDE_OS_GUIDE_OPERATOR_BASE_URL`
- `GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ENABLED`
- `GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ONCE`
- `GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_POLL_INTERVAL_SECONDS`
- `GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_BATCH_SIZE`

Existing bot, Mini App, GuideShop and notification variables remain governed by
their existing settings. Do not store values in documentation.

## Phased matrix

| Gate | Integration API | Outbound delivery | Outbound worker |
| --- | --- | --- | --- |
| Initial production runtime | off | off | off |
| Authenticated intake/read validation | on | off | off |
| Controlled bidirectional pilot | on | on | on |

All new Guide Operator integration flags default off. Outbound delivery and its
worker must be enabled together. The worker cannot run without the integration
API and `--once` is rejected. Enabled components require complete service-auth,
trust-map, signing and HTTPS outbound configuration before the poller starts.

## Invariants and rollout gates

- Railway replica count and the declared replica count must both equal one.
- The existing production SQLite volume stays mounted at `/data`.
- `DATABASE_PATH` must be an absolute direct child of `/data`.
- Mini App and integration HTTP ports must differ when integration is enabled.
- No separate integration or worker service may attach the SQLite volume.
- Startup does not run repair or reconciliation. Existing `bot.py` database
  initialization behavior remains unchanged; the launcher adds no migration.

Before rollout:

1. Create and verify a recoverable SQLite backup.
2. Record the current runtime deployment for rollback.
3. Run `PRAGMA quick_check` and require `ok`.
4. Deploy with all Guide Operator integration/outbound flags off.
5. Verify one poller, existing Mini App behavior and notification-worker count.
6. Enable authenticated integration API only under a separate owner gate.
7. Enable outbound delivery/worker only with empty queues and a separate gate.

Rollback must restore the previous runtime deployment and its start command.
After rollback, verify one poller, Mini App health, SQLite `quick_check`, and
unchanged queue/business counts. Schema compatibility changes require retaining
the pre-rollout backup even when application rollback succeeds.
