# Daily tips — implementation handoff (2026-10-22)

**Closure — 2026-10-29:** ручная функциональная проверка закрыта владельцем (owner-reported PASS). Код зафиксирован и отправлен в GitHub: `569e8906c04a5380c96dc6a142b3cdd264b1f806`; оба production-сервиса Railway закреплены на этом commit. Backend `cfe3ab97-25e5-4952-a488-779e264bb52e` и frontend `3142566b-e4cb-4c6c-8632-f290f361ab5c` — SUCCESS; live smoke PASS, staging не изменён. Отдельно открыт CI defect: standalone Mini App API import требует BOT_TOKEN через analytics/config (1 failed, 1882 passed, 3 skipped); integration workflows PASS. Подробности: `docs/REMINDER_MINIAPP_LINK.md`.

Latest environment update 2026-10-29: daily tips are retained by the subsequent reminder-link release. Current production backend `5dd8037d-97e8-48ad-890a-c04cb0cb6683`, frontend `3d307e26-3378-4171-8f13-aa6fa7e3379c`; current staging IDs/evidence: [reminder handoff](REMINDER_MINIAPP_LINK.md). Deployment IDs below describe the original tips rollout and its rollback history.

**Current status: DEPLOYED TO PRODUCTION — 2026-10-27.**
Owner authorized promotion. Backend and matching production HTTP frontend are
SUCCESS; additive migration and technical smoke passed. See the production
release record below. Earlier staging/BLOCKED sections are historical.

Implemented locally: selected date → Добавить → Тур / Выходной / Чаевые;
read, replace, edit and zero/remove the received daily USD total; persistent shared
storage, authenticated HTTP API, mock parity and reports with tour income, tips
and combined income. Existing `income`, tour/payment counts, availability,
Guide Operator and GuideShop commission semantics are preserved.

Dates remain literal Asia/Tashkent calendar dates. One total per user/date;
integer USD 0…1,000,000,000; tips are independent of tours and their lifecycle.
All-time income uses the full calendar domain and includes tips-only dates.
Telegram bot tips UX/statistics remain deferred. Initial local implementation was
subsequently deployed to owner-authorized staging and production.
Telegram/device authenticated manual checks are not claimed by the technical release.

## Exact files touched for this feature

Backend:

- `database/db.py`
- `database/queries.py`
- `services/daily_tips_service.py` (new)
- `services/reports_service.py`
- `web_api/app.py`
- `web_api/dto.py`
- `web_api/routes/daily_tips.py` (new)
- `web_api/routes/reports.py`
- `tests/test_daily_tips.py` (new)
- `tests/test_daily_tips_api.py` (new)

Frontend:

- `miniapp/src/api/types.ts`
- `miniapp/src/api/client.ts`
- `miniapp/src/api/httpClient.ts`
- `miniapp/src/api/mock/store.ts`
- `miniapp/src/features/calendar/CalendarContext.tsx`
- `miniapp/src/features/calendar/components/CalendarOverlays.tsx`
- `miniapp/src/features/calendar/components/DayDetail.tsx`
- `miniapp/src/features/calendar/components/DailyTipsSheet.tsx` (new)
- `miniapp/src/features/reports/ReportsPage.tsx`
- `miniapp/src/features/reports/lib/periods.ts`
- `miniapp/src/i18n/strings.ts`
- `miniapp/tests/dailyTips.test.ts` (new)
- `miniapp/tests/dailyTipsCalendar.test.tsx` (new)
- `miniapp/tests/dailyTipsReports.test.tsx` (new)
- `miniapp/tests/reports.test.tsx`

Documentation (existing unrelated edits retained):

- `AGENTS.md`
- `miniapp/AGENTS.md`
- `docs/TIPS_ROADMAP.md`
- `docs/mini_app/API_CONTRACT_v1.md`
- `docs/CURRENT_STATE.md` (already untracked before this task)
- `docs/DAILY_TIPS_IMPLEMENTATION.md` (new)

## Executed verification

```sh
.venv/bin/python -m pytest -q tests/test_daily_tips.py
# 21 passed

.venv/bin/python -m pytest -q tests/test_daily_tips.py tests/test_daily_tips_api.py tests/test_reports_service.py
# 35 passed before two extra service regressions were added;
# those regressions subsequently passed targeted (21 service tests) and full suite.

.venv/bin/python -m pytest -q
# 1869 passed, 1 skipped; 66.04s; aiohttp/deprecation warnings

cd miniapp
npm test
# 364 passed, 19 test files
npm run build
# TypeScript and Vite successful
cd ..
git diff --check
# clean
```

HTTP tests required sandbox permission for test-only localhost binds; all databases
were isolated by the existing pytest fixture. Full backend ran once. Frontend was
rerun after async report-test fixes; the final complete run passed all 364 tests.

## Remaining manual checks

- Real Telegram HTTP mode: save/edit/remove → reload; second-account isolation.
- iPhone, Android, Telegram Desktop; 320–430 px light/dark, keyboard, focus and safe areas.
- Smoke selected-date and calendar-position retention after closing the editor.

These are pending; no real Telegram E2E, CI, staging or production PASS is claimed.

## Owner-run Git commands

Run from the repository root. Code/test paths below had no unrelated changes at
start. Documentation already contained unrelated edits: use interactive staging
and select only this feature's hunks. For `CURRENT_STATE.md`, review the pre-existing
untracked document separately; do not accidentally stage the earlier documentation
work as part of this feature. No Git mutation commands were run by the agent.

```sh
git add -- \
  database/db.py database/queries.py \
  services/daily_tips_service.py services/reports_service.py \
  web_api/app.py web_api/dto.py web_api/routes/daily_tips.py web_api/routes/reports.py \
  tests/test_daily_tips.py tests/test_daily_tips_api.py \
  miniapp/src/api/types.ts miniapp/src/api/client.ts miniapp/src/api/httpClient.ts miniapp/src/api/mock/store.ts \
  miniapp/src/features/calendar/CalendarContext.tsx \
  miniapp/src/features/calendar/components/CalendarOverlays.tsx \
  miniapp/src/features/calendar/components/DayDetail.tsx \
  miniapp/src/features/calendar/components/DailyTipsSheet.tsx \
  miniapp/src/features/reports/ReportsPage.tsx miniapp/src/features/reports/lib/periods.ts \
  miniapp/src/i18n/strings.ts \
  miniapp/tests/dailyTips.test.ts miniapp/tests/dailyTipsCalendar.test.tsx \
  miniapp/tests/dailyTipsReports.test.tsx miniapp/tests/reports.test.tsx \
  docs/DAILY_TIPS_IMPLEMENTATION.md

git add -p -- AGENTS.md miniapp/AGENTS.md docs/TIPS_ROADMAP.md docs/mini_app/API_CONTRACT_v1.md

git diff --cached --check
git diff --cached
# After reviewing staged content:
git commit -m "Add daily tips to Mini App calendar and income reports"
# Only when ready to publish the current branch:
git push
```

`docs/CURRENT_STATE.md` is deliberately excluded from automatic staging because
its creation predates this feature. Its updated tips section is preserved locally;
include it with the separate existing documentation work after owner review.


## Authorized staging deployment attempt — 2026-10-22 (BLOCKED)

**Not ready for daily-tips owner testing yet.** Owner authorized staging backend,
frontend and additive migration. Railway rejected the feature-only backend upload
with `Deploys have been paused due to an upstream issue`. No new deployment ID or
queued work was created. Frontend deployment was therefore not attempted; no
application rollback was needed. The old applications remain online, and the
additive migration has **not** run. `daily_tips` is still absent in staging.

Railway's [official status](https://status.railway.com/) reported an active platform
outage on 2026-10-22, with builds resumed for Pro/Enterprise but not all other tiers.
No billing, account plan, source pin, topology, integration flags or domain changes
were made to work around this platform restriction.

### Live target verification

- Project: `radiant-expression` / `0d1f772c-a9ac-43a0-82bb-0272e9b32fef`.
- Environment: `staging` / `693c345d-6a4f-4ca9-a9ca-b06e4f91de61`.
- Backend: `guide-os-staging-api` / `1e75957a-7b28-40e7-9bf6-fcc03780ecdd`.
- Frontend: `guide-os-staging-miniapp` / `3aecd3b6-9343-4e13-a5ac-5eac9e6314ed`.
- Telegram `getMe` confirmed public bot username `@Guideosbot`; no token exposed.
- Mini App: https://guide-os-staging-miniapp-staging.up.railway.app (HTTP 200).
- Guide API: https://api.staging.guideos.uz (port 8083; `/health` HTTP 200).
- Existing integration domain routes to port 8084 and remains unchanged.
- Startup command: `python guide_os_staging_runtime.py`; one configured/running
  replica, one runtime process (one bot poller owned by the consolidated launcher).
- Staging-only volume: `6f933c10-fd1b-454a-9cb2-711184ddba16`, mounted `/data`.
- **Live DB path is `/data/guide_os_staging.db`**, rather than the older runbook's
  example `/data/guide_os.db`; it was preserved.
- Frontend has `VITE_USE_MOCK_API=false` and
  `VITE_API_BASE_URL=https://api.staging.guideos.uz`.

### Current staging revisions / application rollback targets

- Backend: `ed1944a2-d1b9-4903-ab2e-a9cdafc0564e`, SUCCESS,
  source `53b3985a7dcad8fa7becf4f076026e5dbc850137`.
- Frontend: `72efc530-2822-407d-b48c-c401615658f7`, SUCCESS,
  original local-upload artifact (no Git SHA metadata). Its live JS
  `index-DwLWttiQ.js` has SHA-256
  `40ceff1fc580c50629fd54e6cdb0e47e7471d3ef8e12ae5d7fbd2c661b8f7474`.
- Both builds were reported rollback-capable before the attempted deployment.
  Retain these as application rollback targets after a future successful upload.
  Never restore the pre-migration DB destructively merely to roll back application code.

### Exact candidate and baseline comparison

- Ready directory: `/tmp/guide-os-daily-tips-staging-20261022`.
- Artifact ID: `daily-tips-b0b5cae44200f3b0`.
- Feature-manifest SHA-256: `b0b5cae44200f3b09a9549e3da4c57e0cc2d45f0fcda0c14f76a263c6afd0cc3`.
- Recoverable source archive: `/tmp/guide-os-daily-tips-staging-20261022.tar.gz`.
- Archive SHA-256: `5a8a46bd5184c44d11ca981b2d1b5bf74be8979fc78814fa2658d1b1cfaa11af` (874147 bytes).
- `DAILY_TIPS_ARTIFACT.json` inside the candidate lists all 25 feature code/test
  paths with hashes. The baseline is the live backend SHA above, from `git archive`.
  No Git branch/add/commit/push operations were performed.
- All 116 live backend Python file hashes matched that baseline. Building the
  baseline Mini App in HTTP mode reproduced the deployed JS hash exactly.
  Therefore the candidate changes only daily-tips code/tests relative to live staging.
- Excluded HEAD differences: `guide_os_production_runtime.py`,
  `guide_os_staging_runtime.py`, `services/guide_operator_integration_settings.py`,
  `tests/test_guide_os_production_runtime.py`, and its production-runtime doc.
  In particular, the **existing staging launcher/settings were retained**.
- Unrelated dirty documentation, analytics, media and Guide Operator identity work
  were excluded. No `.env`, credentials, DB, dependency tree or generated caches
  were copied into the upload source. Existing local changes remain intact.

### Backup / migration readiness

- Created through the deployed existing `database.db.create_sqlite_backup` online
  procedure on the persistent staging volume: `/data/backups/pre_daily_tips_20261022T141836Z.db`.
- Size: 598016 bytes; SHA-256 `0a04dee51efe80b869bb907238b2b6483a610a9b41e303c616122beaea3a4f9f`.
- Source and backup full `PRAGMA integrity_check`: `ok`.
- Backup hash rechecked after the rejected deployment: unchanged.
- Backup mode: owner-only `0600`; recoverable across application deployments.
- Migration was not manually applied. It will run through normal backend startup
  only after Railway accepts the new application deployment.

### Checks against this candidate / current staging

- With a synthetic test-only BOT_TOKEN (no real bot started), from candidate root:
  `.venv` interpreter from the original checkout executed
  `python -m pytest -q tests/test_daily_tips.py tests/test_daily_tips_api.py tests/test_reports_service.py tests/test_guide_os_staging_runtime.py`
  → **55 passed**. No full-suite repeat was needed.
- From candidate `miniapp/`:
  `npm test -- --run tests/dailyTips.test.ts tests/dailyTipsCalendar.test.tsx tests/dailyTipsReports.test.tsx tests/reports.test.tsx`
  → **42 passed**.
- `VITE_USE_MOCK_API=false VITE_API_BASE_URL=https://api.staging.guideos.uz npm run build`
  → TypeScript/Vite successful, candidate JS `index-3EejKgV3.js`.
- Final public checks: Mini App/API health HTTP 200; existing calendar and reports
  auth gates HTTP 401; frontend bundle hash unchanged. The **old** tips route
  returns 404; a deployed new-route 401 smoke cannot yet be claimed. Candidate
  tests verified unauthenticated 401 and session-isolated mutations/reports.
- No authorized browser/session bearer was supplied or available in this task.
  No owner credentials were obtained; live authenticated tips smoke is pending.
- Production revisions checked before and after and **unchanged**:
  backend `926d0f29-f9be-4f61-96ea-a5b8e3d6a99c` at
  `24b3cad7ff2cb121134f96c0b701573a71c05614`, frontend
  `28d227f7-a719-4ea1-a008-d331d37d29a8` at
  `f3c3806d328332fb0ff0a40987d582a4f0d09316`.
  These are fresh readings, not an assumption from older pin documentation.

### Resume once Railway restores builds

Existing owner authorization covers the staging deploy; no repeat approval is
needed. Recheck active deployment IDs, production isolation and candidate manifest
first. Take a fresh online backup if the existing one is no longer current.
Then upload the exact candidate below (not the dirty working directory):

```sh
cd /tmp/guide-os-daily-tips-staging-20261022
railway up --project 0d1f772c-a9ac-43a0-82bb-0272e9b32fef --environment 693c345d-6a4f-4ca9-a9ca-b06e4f91de61 --service 1e75957a-7b28-40e7-9bf6-fcc03780ecdd --detach --message 'daily-tips-b0b5cae44200f3b0 backend; baseline 53b3985; feature-only staging'
# WAIT: backend SUCCESS, health 200, daily_tips schema, integrity ok, exactly one poller.
# Only after those backend checks succeed:
cd miniapp
railway up --project 0d1f772c-a9ac-43a0-82bb-0272e9b32fef --environment 693c345d-6a4f-4ca9-a9ca-b06e4f91de61 --service 3aecd3b6-9343-4e13-a5ac-5eac9e6314ed --detach --message 'daily-tips-b0b5cae44200f3b0 frontend; verified staging HTTP API'
```

If `/tmp` is cleaned, recover from the source archive above, or reconstruct the
baseline + 25 files after verifying their recorded hashes. After deployment:
record both new IDs, verify bundled staging API/tips action, unauthenticated 401,
calendar/reports auth gates, single poller, integrity and unchanged production.
When an authorized test session exists, perform save/read/replace/zero with prior
amount restoration. On application failure, redeploy the recorded old builds;
retain the additive table and all staging data.

Owner steps **after readiness is confirmed**: open @Guideosbot → any date →
Добавить → Чаевые; save → reload → edit → remove; check tour/tips/total reports and
a second account. Telegram/device E2E is not yet performed and is not claimed PASS.

## Resume attempt — 2026-10-22 14:36 UTC / 19:36 Asia/Samarkand (BLOCKED)

- Revalidated candidate `daily-tips-b0b5cae44200f3b0`: all 25 feature file hashes
  match the manifest; archive SHA-256 remains
  `5a8a46bd5184c44d11ca981b2d1b5bf74be8979fc78814fa2658d1b1cfaa11af`.
- Verified the recorded persistent staging backup via SSH: exists, 598016 bytes,
  SHA-256 `0a04dee51efe80b869bb907238b2b6483a610a9b41e303c616122beaea3a4f9f`,
  full backup integrity `ok`, remote `APP_ENV=staging`.
- Staging deployment IDs still exactly match the recorded baseline; no drift or
  pending work. Backend remains configured with one replica and the same volume.
- Official Railway status still reports an active outage with builds restored for
  Pro/Enterprise and restoration pending for other tiers. One backend upload was
  attempted using the exact prepared candidate and recorded continuation command.
  Railway rejected it: `Deploys have been paused due to an upstream issue`.
- No further upload was attempted. Frontend was not deployed; migration did not
  run. No new deployment ID or pending work appeared; no application rollback was
  needed. Both staging deployment IDs remain unchanged after the refusal.
- Production deployment IDs remain `926d0f29-f9be-4f61-96ea-a5b8e3d6a99c` and
  `28d227f7-a719-4ea1-a008-d331d37d29a8`, unchanged before/after.
- Existing tests/build were not repeated; artifact contents are unchanged.
- Daily tips remain unavailable for owner staging testing. Telegram/device E2E and
  authenticated smoke remain pending. Existing deployment authorization persists.
- Public post-attempt checks: Mini App HTTP 200, API `/health` HTTP 200,
  daily-tips range route HTTP 404 on the unchanged old backend, as expected.

## Successful staging continuation — 2026-10-22 18:56 UTC

**Ready for owner testing in @Guideosbot.** Existing authorization was reused.
No Git operations, new application code, rebuild of the local candidate, or repeat
test-suite runs were needed. Railway performed its normal remote builds.

### Artifact and deployments

- Candidate: `daily-tips-b0b5cae44200f3b0`; all 25 feature-file hashes matched the
  recorded manifest before upload. Existing unrelated local work was excluded.
- Staging backend: `a8c31d29-ffa2-479d-aa05-c157d0c62586`, SUCCESS.
- Staging frontend: `e1abb938-ca1b-4e10-94f6-8f4da2e40ce2`, SUCCESS.
- Backend was deployed first. Frontend upload began only after backend SUCCESS,
  schema/integrity/process checks and public auth/health checks passed.
- Environment/project/services/volume and staging launcher were preserved.
- Previous staging application rollback targets remain recorded above.

### Fresh backup and migration evidence

- Online backup made through existing `create_sqlite_backup` before new backend
  startup: `/data/backups/pre_daily_tips_resume_20261022T184543Z.db`, mode `0600`.
- SHA-256: `5107344f9524563b4478677559cc0c36c68126765800f22025e8676762d47659`;
  full backup integrity `ok`; hash unchanged after backend startup.
- Migration ran via normal startup against `/data/guide_os_staging.db`.
  `daily_tips` columns confirmed: id, user_id, tip_date, amount, created_at, updated_at.
- Deployed SQLite full integrity `ok`; exactly one consolidated runtime process.
- Backend deployment logs contained one polling startup and no traceback or
  duplicate-getUpdates conflict in the inspected startup window.
- Deployed daily-tips service SHA-256 matched the candidate:
  `2a87d92a1b0ca71970023cb8a6707e625bc3edc273ce6d162a06ed5f2e2b116f`.

### Public smoke

- Mini App https://guide-os-staging-miniapp-staging.up.railway.app/ → HTTP 200.
- Public JS `/assets/index-3EejKgV3.js`, SHA-256
  `e297efe7dd11fca2fa4bd7da7b15467432db86755ef3fe712a91348e6d682f67`,
  contains the tips labels/routes and `https://api.staging.guideos.uz`.
- Frontend build variables verified: `VITE_USE_MOCK_API=false`,
  `VITE_API_BASE_URL=https://api.staging.guideos.uz`.
- API `/health` → 200; unauthenticated daily-tips range/day routes → 401.
- Existing calendar entries and reports summary routes → 401 without a session.
- Final Railway staging state: both deployments SUCCESS, no pending work, one
  backend replica with the original staging volume.

### Production isolation observation

This continuation issued no production mutations. However, production was not
static due to a separately initiated deployment already visible at the first
preflight read: `2353031d-b49d-4caf-bb9a-befe725fa5f0`, created 18:43:50 UTC,
was INITIALIZING before this task's staging upload and later reached SUCCESS.
The tool metadata did not establish its source revision/initiator; this task does
not attribute it or claim all production deployment IDs stayed unchanged.
Production Mini App stayed on `28d227f7-a719-4ea1-a008-d331d37d29a8`.

### Owner validation still pending

Open @Guideosbot → Mini App → select a date → Добавить → Чаевые. Save, close/reopen
the Mini App, verify the amount, edit it, then remove with zero. Check reports
including a tips-only date/period, tour/tips/total breakdown, and a second account.
Check device sizes, themes, keyboard and retained selected date/calendar position.
No authorized live user session was available; authenticated mutation smoke and
Telegram/device E2E are not claimed PASS. Fully reopen the Mini App if Telegram
still shows the cached old interface.

## Owner-authorized production release — 2026-10-27

Owner request: «деплоим в production». Applied only daily tips and its reporting
UI/API, preserving the existing production runtime, integrations, bot and data.
No Git branch/add/commit/push or production credential/flag changes were performed.

### Targets, candidate and source provenance

- Project/environment: `radiant-expression` / production
  (`0d1f772c-a9ac-43a0-82bb-0272e9b32fef` /
  `ebc5799e-60ca-4c44-8a63-47dd796d8d83`).
- Runtime `guide_os`: `75ed4bee-cf0f-4e03-8519-71805a00874a`.
- Frontend `guide-os-miniapp`: `ba9af48a-f36e-44b3-ac6e-b4d6c6025e5d`.
- Bot confirmed through getMe: @Guide_os_bot.
- Staging /tmp source/archive had been cleaned. Recovered its exact manifest from
  the deployed staging backend and verified all 25 local feature files against it.
- Production preflight checked 117 runtime Python files against `24b3cad`. Two
  already-deployed overrides were detected, verified against local hashes and
  retained: `services/guide_operator_connection_service.py` and
  `web_api/guide_operator_integration.py`. Identity API was not rolled back.
- Candidate `daily-tips-prod-9708e7f933b8108a`, baseline
  `24b3cad7ff2cb121134f96c0b701573a71c05614` + those live overrides + the
  25 staging-verified daily-tips files. Existing identity HTTP regression tests
  were included as coverage for the preserved live implementation.
- Candidate directory `/tmp/guide-os-daily-tips-production-20261027`; clean upload
  `/tmp/guide-os-daily-tips-production-upload-20261027`. Source archive
  `/tmp/guide-os-daily-tips-production-20261027.tar.gz`, SHA-256
  `dcdb6fb4cd9eaec9dbdda3c8aa7dab883d63fa867c7c40d01e549060a2903e5a`.
- `DAILY_TIPS_PRODUCTION_ARTIFACT.json` records all promoted and retained hashes.
  Unrelated working-tree documentation/analytics/media were excluded; no secrets,
  DB, dependency tree or generated build caches were in the clean upload.

### Verification before upload

From candidate root, with a synthetic test-only BOT_TOKEN and the checkout .venv:

```sh
python -m pytest -q tests/test_daily_tips.py tests/test_daily_tips_api.py tests/test_reports_service.py tests/test_guide_os_production_runtime.py tests/test_guide_os_staging_runtime.py tests/test_guide_operator_discovery_http.py
# 112 passed; existing aiohttp NotAppKey warnings
```

From candidate miniapp/:

```sh
npm test -- --run tests/dailyTips.test.ts tests/dailyTipsCalendar.test.tsx tests/dailyTipsReports.test.tsx tests/reports.test.tsx
# 42 passed; React act warnings
VITE_USE_MOCK_API=false VITE_API_BASE_URL=https://guideos-production.up.railway.app npm run build
# TypeScript/Vite successful
```

The full suites were not repeated: existing full verification is recorded above;
focused production-runtime/identity compatibility was checked for this promotion.

### Backup and application rollback targets

- Fresh online SQLite backup created before upload through existing
  `database.db.create_sqlite_backup`: `/data/backups/pre_daily_tips_production_20261027T182720Z.db`.
- 2142208 bytes, mode 0600, SHA-256
  `1bf6183b151b9b25c4450f4a1d0db1ae654e531d0f3496812219f393920426d0`; full backup integrity `ok`.
- Live DB `/data/guide_os.db`; original production volume
  `a5584f2a-f420-4d25-84d5-baacb29a11b3` at `/data` retained.
- Previous backend build: `2353031d-b49d-4caf-bb9a-befe725fa5f0`.
- Previous frontend build: `28d227f7-a719-4ea1-a008-d331d37d29a8`.
- Both previous builds were rollback/redeploy-capable at preflight. For application
  rollback use those exact builds; do not destructively restore the pre-release DB
  or drop daily_tips. Keep the backup for recovery if separately needed.

### Successful deployments and smoke

- Backend `90574365-28da-4a0a-bf2e-5685742c93dc`: SUCCESS.
- Frontend `df876e09-381c-44f5-a92a-37bda7d49cb8`: SUCCESS.
- Backend-first sequence; frontend uploaded only after backend migration/process/
  integrity/auth checks passed. No pending work at final status check.
- Source configuration retained one production replica and
  `python guide_os_production_runtime.py`; runtime process check found exactly one
  consolidated runtime. Startup logs showed one polling start and no traceback
  or duplicate-getUpdates conflict in the inspected window.
- Normal startup created daily_tips with expected columns. Production full SQLite
  integrity `ok`; backup hash unchanged; all 10 promoted/preserved runtime Python
  file hashes matched the manifest. Existing service auth, integration/outbound,
  Mini App and dev-auth flags matched preflight; no integration was newly enabled.
- API https://guideos-production.up.railway.app/health → 200.
- Daily tips range/day, reports summary and calendar entries → 401 without session.
- Mini App https://guide-os-miniapp-production.up.railway.app/ → 200.
- JS `/assets/index-BHXQTwgX.js`, SHA-256
  `9d6a489fbdf562652599099848e1c65c298749745851fad91abe5acd41908c51`,
  exactly matches the local production build and contains tips labels/routes plus
  the production API URL. HTTP mode / VITE_USE_MOCK_API=false preserved.
- Staging deployment IDs remain `a8c31d29-ffa2-479d-aa05-c157d0c62586` and
  `e1abb938-ca1b-4e10-94f6-8f4da2e40ce2`.

### Persistent source follow-up and owner smoke

This release uses a verified local-upload artifact, not a new Git commit. Railway
Git source pins were preserved (backend `24b3cad`, frontend `f3c3806`). They do not
yet contain daily tips. A later deploy from those Git sources would remove the
feature from application code. Owner-run feature commit/push and explicit pin
alignment are a separate follow-up; do not blindly redeploy the pinned old sources.
The artifact manifest/archive and existing exact file list support that follow-up.

No live user session was obtained and no real user's tips were modified for smoke.
Authenticated save/reload/edit/zero, two-account isolation and device/theme/keyboard
verification remain owner checks; no new manual Telegram E2E PASS is claimed.
Open @Guide_os_bot → Mini App → select a date → Добавить → Чаевые; save, reopen,
edit/remove and verify tour/tips/combined reports. Telegram bot tips UX is deferred.
