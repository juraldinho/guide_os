# GO13C2 consolidated Guide OS staging runtime

Status: locally implemented and verified. Deployment and integration enablement are deferred to GO13C3.

## Topology

One Railway staging service, exactly one replica and one mounted `/data` volume run:

- one Telegram long poller;
- the guide-facing Guide OS Mini App API on port `8083`;
- the service-authenticated Guide Operator integration API on port `8084`;
- one Guide Operator outbound delivery worker;
- one notification drain owned only by the existing bot lifecycle.

The HTTP applications remain separate. `/app/v1/*` routes are not mounted on the integration application, and `/integration/v1/*` routes are not mounted on the guide Mini App application. Guide Operator remains browser-web-only for the MVP; an operator-facing Telegram Mini App is deferred.

## Command

```sh
python guide_os_staging_runtime.py
```

Production continues to use `python bot.py`.

## Required staging configuration

The launcher fails closed unless all of the following are true:

- `APP_ENV=staging`
- `GUIDE_OS_CONSOLIDATED_STAGING_RUNTIME_ENABLED=true`
- `GUIDE_OS_CONSOLIDATED_STAGING_REPLICA_COUNT=1`
- `DATABASE_PATH=/data/guide_os.db`
- `MINI_APP_API_ENABLED=true`
- `MINI_APP_API_HOST=0.0.0.0`
- `MINI_APP_API_PORT=8083`
- `GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_ENABLED=true`
- `GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_HOST=0.0.0.0`
- `GUIDE_OS_GUIDE_OPERATOR_INTEGRATION_PORT=8084`
- `GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_ENABLED=true`
- `GUIDE_OS_GUIDE_OPERATOR_OUTBOUND_WORKER_ENABLED=true`
- `GUIDESHOP_LINK_PROVIDER_ENABLED=false`

`GUIDE_OS_CONSOLIDATED_STAGING_SHUTDOWN_TIMEOUT_SECONDS` is optional (`30`, allowed `1..120`). Existing Mini App, service-auth, outbound, notification and Telegram variables remain required by their own fail-closed settings when those features are enabled. Do not record their values in this document.

## Railway gate for GO13C3

Before deployment, manually verify the Railway service has exactly one replica. Set the declared replica count variable to `1`; it is a startup guard and does not replace checking the Railway replica setting. Mount one staging-only volume at `/data`. Configure separate domains/routing targets for ports `8083` and `8084`. Do not share production keys, bot credentials, volume or database.

## Shutdown and failure behavior

The launcher owns SIGINT/SIGTERM. It requests integration API and outbound-worker shutdown, cancels the single bot/poller task so its existing cleanup runs, and bounds completion. An unexpected exit of any required component stops the entire runtime. It uses no subprocesses, shell composition, detached processes, second notification drain or second poller.

## Manual smoke for GO13C3

1. Confirm one Railway replica and `/data` READY.
2. Confirm one Telegram polling startup and one notification-worker startup at most.
3. Check Mini App health through its port/domain and integration health through its separate port/domain.
4. Confirm integration routes are absent from the Mini App surface.
5. Confirm an enabled outbound worker stays active without leaking identifiers.
6. Send SIGTERM and verify every component stops within the configured timeout.
7. Restart once and verify SQLite `PRAGMA quick_check=ok` through an approved operational procedure.

Do not create staging bot credentials, service keys or enable integrations until GO13C3 is separately authorized.
