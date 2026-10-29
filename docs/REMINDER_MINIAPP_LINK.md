# Reminder → Mini App tour detail

**Closure — 2026-10-29:** ручная функциональная проверка закрыта владельцем (owner-reported PASS). Код зафиксирован и отправлен в GitHub: `569e8906c04a5380c96dc6a142b3cdd264b1f806`; оба production-сервиса Railway закреплены на этом commit. Backend `cfe3ab97-25e5-4952-a488-779e264bb52e` и frontend `3142566b-e4cb-4c6c-8632-f290f361ab5c` — SUCCESS; live smoke PASS, staging не изменён. Отдельно открыт CI defect: standalone Mini App API import требует BOT_TOKEN через analytics/config (1 failed, 1882 passed, 3 skipped); integration workflows PASS. Подробности: `docs/REMINDER_MINIAPP_LINK.md`.

Implemented; staging deployed 2026-10-28 and production promotion completed
2026-10-29. Technical rollout checks passed; functional manual validation was
closed by the owner on 2026-10-29. Git/pin closure is recorded below. No manual
Telegram test messages were sent by the agent. Prior features are retained.

## Behavior

Newly sent tour/day-off reminders keep “Открыть тур” (the existing bot callback)
and add “Открыть в приложении” when Mini App is enabled with a valid HTTPS URL.
The additional inline button uses Telegram WebAppInfo and opens the configured
Mini App with `reminder_entry` and `reminder_date` query parameters. No Telegram
identity, session token, tour text or personal information is added to the URL.
Existing already-sent reminders are not retroactively edited.

Mini App validates both parameters and requests the record through the existing
session-authenticated, owner-scoped getEntry endpoint. Parameters select a target;
they never establish authorization. A raw reminder row ID may resolve to a canonical
multi-day entry ID; the returned entry is used for detail and calendar context.
The target is loaded even if absent from the initial calendar list. A failed list
load does not block the authenticated detail when the list request rejects.

The focused date is the reminder date if still inside the tour's current range;
otherwise it is the current start date. Closing a normal detail returns to that
day. Operator-managed entries use the existing assignment detail/read-only rules
and retain a focused-day return context. No assignment decision rules change.

Missing/deleted/foreign records show “Тур не найден”. Malformed/duplicate targets
are ignored; API failures show a safe retry instruction and retain the URL so a
reload/reopen can retry. Successful/not-found navigation consumes only the two
navigation query parameters, preserving unrelated query fields and Telegram hash.
Async request caching and cleanup support React StrictMode without duplicate entry
loads or automatic reopening after closing the detail.

When disabled/misconfigured or without a valid entry ID, reminders retain only
the original bot action. Schedule, reminder text, recipient and deduplication remain
unchanged. Settings and URL normalization reuse existing MiniAppMenuSettings.

## Files changed for this task

- `services/reminder_service.py`
- `miniapp/src/features/calendar/CalendarContext.tsx` (earlier tips edits retained)
- `tests/test_reminder_miniapp_link.py` (new)
- `miniapp/tests/reminderLink.test.tsx` (new)
- `docs/REMINDER_MINIAPP_LINK.md` (new)

## Verification

```sh
.venv/bin/python -m pytest -q tests/test_reminder_miniapp_link.py
# 16 passed
npm --prefix miniapp test -- --run tests/reminderLink.test.tsx tests/dailyTipsCalendar.test.tsx
# 14 passed
.venv/bin/python -m pytest -q
# 1885 passed, 1 skipped; 65.27 seconds
npm --prefix miniapp test
# 375 passed, 20 files
npm --prefix miniapp run build
# TypeScript and Vite successful
git diff --check
# clean
```

Backend full run used a synthetic test-only BOT_TOKEN and existing isolated DB
fixtures. Known aiohttp/deprecation and frontend React act warnings remain; no
unrelated warning cleanup was attempted. The single skip belongs to the existing
suite; no new skipped tests were added. Focused tests cover actual reminder send
arguments, unsafe/missing config, distinct per-tour targets, owner isolation,
multi-day canonical resolution, moved/missing targets, one-time navigation,
operator return context, malformed params and API failure.

## Manual checks in the deployed staging environment

Deploy matching backend and frontend together, preserving the currently deployed
production daily-tips/runtime/identity changes rather than reverting to old Git
pins. Old frontend does not understand the new navigation parameters.

1. Use a staging account with two tours on the reminder date and receive real new
   reminders via the existing runtime; do not start a second poller.
2. Each “Открыть в приложении” opens that specific tour card, not just the day list.
3. Close the card: the reminder date remains selected. Existing “Открыть тур” still
   opens the bot day card.
4. Repeat for an interior day of a multi-day tour and an operator-managed projection.
5. Move/delete a tour before opening an old link; verify the current date/fallback.
6. With a second account, a copied URL must not expose another user's tour.
7. Check iPhone, Android and Desktop WebApp launch/auth and Back/close behavior.

Telegram/device E2E is not claimed PASS. Staging technical rollout evidence is
recorded below; production rollout of this feature has not been performed.
Telegram API reference: https://core.telegram.org/bots/api#inlinekeyboardbutton
and https://core.telegram.org/bots/api#webappinfo .

## Owner-run Git preparation

Existing working-tree work is not automatically included. CalendarContext already
contains the separate daily-tips implementation: stage only this feature's hunks
unless intentionally preparing a combined commit with its required dependencies.
Review the existing daily-tips handoff before source/pin alignment.

```sh
git add -- services/reminder_service.py tests/test_reminder_miniapp_link.py miniapp/tests/reminderLink.test.tsx docs/REMINDER_MINIAPP_LINK.md
git add -p -- miniapp/src/features/calendar/CalendarContext.tsx
git diff --cached --check
git diff --cached
# After reviewing the exact staged feature and dependencies:
git commit -m "Add Mini App tour links to reminders"
git push
```

## Staging deployment — 2026-10-28 13:48 UTC / 18:48 Asia/Samarkand

Continuation scope: staging preparation for owner testing after «далее». No
production mutations were performed. Frontend was deployed before backend because
there is no new schema and newly emitted buttons need a ready link receiver.

- Candidate: `reminder-staging-99591ebba5d7e48d`, baseline `53b3985` + exact
  existing daily-tips staging files + four reminder code/test files listed above.
- All 118 existing runtime Python file hashes matched the live staging baseline
  before upload; the new deployment matched that baseline with only reminder
  service updated. Daily tips and integration runtime implementations were kept.
- Candidate: `/tmp/guide-os-reminder-staging-20261028`; clean upload:
  `/tmp/guide-os-reminder-staging-upload-20261028`. Archive:
  `/tmp/guide-os-reminder-staging-20261028.tar.gz`, SHA-256
  `5a0cb4baa3a2051165de850932667004116754551b60bfba51be0da9f15a1ebb`.
- `REMINDER_STAGING_ARTIFACT.json` records changed/preserved file hashes.
  No unrelated source changes, secrets, DB or dependency tree were uploaded.
- Focused candidate backend/reminder + staging runtime: **34 passed**.
- Candidate reminder navigation + tips calendar frontend tests: **14 passed**.
- Staging HTTP TypeScript/Vite build: PASS. Full local suite results remain above;
  full suites were not repeated for this unchanged feature.

### Environment and backup

Project `0d1f772c-a9ac-43a0-82bb-0272e9b32fef`, staging environment
`693c345d-6a4f-4ca9-a9ca-b06e4f91de61`. Bot username verified with getMe:
@Guideosbot. Original staging DB `/data/guide_os_staging.db` and volume
`6f933c10-fd1b-454a-9cb2-711184ddba16` retained.

Online backup through existing create_sqlite_backup: `/data/backups/pre_reminder_miniapp_20261028T133728Z.db`,
610304 bytes, mode 0600, full integrity `ok`, SHA-256
`c5e15987b49628e99fdacdb42f548708dd4e3eae84d74fac7c8c1b93a7cde39d`. Hash was rechecked after deployment.

Preflight found MINI_APP_ENABLED absent on the staging runtime. The existing
MINI_APP_PUBLIC_URL already pointed to the verified staging frontend. Set only
MINI_APP_ENABLED=true on that staging service, with skipDeploys=true before the
planned backend upload. This enables the new reminder button and existing WebApp
menu; no service-auth, GuideShop or Guide Operator flags were changed.

### Deployments and technical checks

- Frontend service `3aecd3b6-9343-4e13-a5ac-5eac9e6314ed`:
  `346e539b-36c7-4524-adb8-28af77e14a80`, SUCCESS.
- Backend service `1e75957a-7b28-40e7-9bf6-fcc03780ecdd`:
  `4f2df896-9a08-43a1-88f4-da86da2fde47`, SUCCESS.
- Frontend https://guide-os-staging-miniapp-staging.up.railway.app/ → 200;
  JS `/assets/index-B5h9fUTM.js`, SHA-256 `bcf1db38c578c149831aa9981d6391d205b865841f963d886ec9e7b080c66f44`,
  exactly matches the tested local staging HTTP build and contains the two
  navigation parameters plus https://api.staging.guideos.uz.
- VITE_USE_MOCK_API=false and staging VITE_API_BASE_URL verified unchanged.
- Backend /health → 200; entry detail, daily-tips and reports routes → 401
  without a session. Authenticated manual Telegram checks remain pending.
- Deployed function generated both original callback and correct WebApp URL for
  a synthetic test ID/date without sending a Telegram message.
- Telegram getChatMenuButton confirmed type web_app.
- One configured backend replica, one consolidated runtime process and one
  polling startup observed. No traceback/duplicate-getUpdates conflict in the
  inspected startup window. Full SQLite integrity `ok`, daily_tips retained.

Previous staging application builds for rollback: backend
`a8c31d29-ffa2-479d-aa05-c157d0c62586`, frontend
`e1abb938-ca1b-4e10-94f6-8f4da2e40ce2`. Exact config rollback also restores the
previous absence of staging MINI_APP_ENABLED; do not drop tables or overwrite DB
merely to roll back application code.

Production remained on backend `90574365-28da-4a0a-bf2e-5685742c93dc` and frontend
`df876e09-381c-44f5-a92a-37bda7d49cb8`, SUCCESS before/after.

Owner can now test a newly generated reminder in @Guideosbot. Previously sent
messages retain their original keyboard. The ordinary per-date reminder
deduplication is unchanged; no sent-date reset, schedule manipulation or manual
message send was used to force a test.

## Production promotion — 2026-10-28 (historical delay; completed 2026-10-29)

Owner continuation «отлично — далее» after staging rollout. No owner Telegram
manual PASS is inferred; this is a technical promotion of the staging-tested code.

- Candidate: `reminder-prod-50672bcfac857f8e`, current daily-tips production artifact
  plus the same four reminder code/test files verified against staging.
- Candidate `/tmp/guide-os-reminder-production-20261028`; clean upload
  `/tmp/guide-os-reminder-production-upload-20261028`; source archive
  `/tmp/guide-os-reminder-production-20261028.tar.gz`, SHA-256
  `ced32202d106a3cbd3eae0a47ba4b48a2c670c0489e015678d9e6c3653a7742a`.
- Manifest: `REMINDER_PRODUCTION_ARTIFACT.json`. All 119 existing runtime Python
  source hashes matched production before upload. Existing daily tips, identity
  API overrides, consolidated launcher, volume and integration flags are retained.
- Bot verified via getMe: @Guide_os_bot. MINI_APP_ENABLED already true; no
  production variable changes are required. Dev auth remains false.
- Fresh online backup: `/data/backups/pre_reminder_production_20261028T180932Z.db`, 2203648 bytes, mode 0600,
  SHA-256 `7b3787d2f2ce97fd45b4697523c9c0d7b5cd9a6a6b75dc22fe8f116f5beae7ad`, full integrity `ok`. No new migration.
- Current production application rollback targets: backend
  `90574365-28da-4a0a-bf2e-5685742c93dc`; frontend
  `df876e09-381c-44f5-a92a-37bda7d49cb8`.
- Focused reminder + production-runtime tests: **37 passed**. Production HTTP
  TypeScript/Vite build: PASS, expected JS `index-BZ2Xoudl.js`, SHA-256
  `b7be409966920d98d7a73fd9d46f204221ae0a5b52a9d2b5f33ba4a40bacd329`.
- Full suites were already passed for the feature; no repeat full-suite run.
- Frontend-first sequence: frontend deployment
  `3d307e26-3378-4171-8f13-aa6fa7e3379c` is BUILDING. Backend upload waits for
  frontend SUCCESS and public bundle verification. No duplicate deployment submitted.

### Provider delay and continuation — 2026-10-28 18:19 UTC

Railway [official status](https://status.railway.com/) reports an active
“Deployments stuck in initializing” partial outage (identified 17:49 UTC), which
describes delayed builds/deployments. Our frontend deployment remains BUILDING;
last available build output is “image push” at 18:14:58 UTC. No duplicate upload,
source/pin change, plan change, production variable change or backend upload was
performed to work around the platform delay.

Public production checks: API health 200, Mini App 200, still serving previous JS
`/assets/index-BHXQTwgX.js`, SHA-256
`9d6a489fbdf562652599099848e1c65c298749745851fad91abe5acd41908c51`.
Daily tips remain present; reminder navigation is not yet in the public bundle.
Backend remains `90574365-28da-4a0a-bf2e-5685742c93dc`, SUCCESS. No DB migration
was necessary or applied. Fresh backup and verified candidate remain available.

The accepted frontend deployment may finish automatically after Railway recovers.
Do NOT re-upload it while pending. Existing owner authorization covers continuation.

Resume procedure:

1. Inspect deployment `3d307e26-3378-4171-8f13-aa6fa7e3379c`. Wait for SUCCESS;
   investigate a terminal failure before considering a single replacement deploy.
2. Run `python3 /tmp/verify_reminder_production_frontend.py` (read-only public check).
   Require exact expected JS/hash, production API and reminder parameters.
3. Verify production backend still matches the recorded baseline and config.
   Refresh backup if needed. Then upload the already tested backend candidate:

```sh
cd /tmp/guide-os-reminder-production-upload-20261028
railway up --project 0d1f772c-a9ac-43a0-82bb-0272e9b32fef --environment ebc5799e-60ca-4c44-8a63-47dd796d8d83 --service 75ed4bee-cf0f-4e03-8519-71805a00874a --detach --message 'reminder-prod-50672bcfac857f8e backend; exact tour WebApp button; production promotion'
```

4. After backend SUCCESS, run
   `python3 /tmp/verify_reminder_production.py <new-backend-deployment-id>`.
   Require all 119 expected source hashes, original flags, DB integrity, retained
   tips, one runtime, unchanged backup hash and correct generated keyboard/menu.
5. Check public /health=200, unauthenticated entry/tips/reports routes=401, one
   polling startup and no traceback/getUpdates conflict. Verify staging unchanged.
6. Record final IDs/results and hand back real-new-reminder manual steps. No
   real Telegram test messages or reminder deduplication resets are authorized
   merely by this technical deployment step.

At the 2026-10-28 checkpoint the feature was not yet released to production.
The successful continuation below supersedes that pending state. No authenticated
manual Telegram/device PASS is claimed. Tests/build must not be repeated unless
candidate changes or deployment failures justify them.

## Production promotion complete — 2026-10-29 03:34 UTC / 08:34 Asia/Samarkand

Resumed under the existing owner authorization. The previously accepted frontend
deployment finished without a duplicate upload. No source changes, rebuild or
repeat test-suite run were needed; the candidate hashes were reverified.

- Frontend: `3d307e26-3378-4171-8f13-aa6fa7e3379c`, SUCCESS.
- Backend: `5dd8037d-97e8-48ad-890a-c04cb0cb6683`, SUCCESS.
- Frontend verified first: production Mini App HTTP 200; public
  `/assets/index-BZ2Xoudl.js`, SHA-256
  `b7be409966920d98d7a73fd9d46f204221ae0a5b52a9d2b5f33ba4a40bacd329`,
  exactly matches the tested production build and contains reminder navigation
  and the production API.
- Before backend upload, all 119 current production runtime source hashes still
  matched the recorded baseline and bot @Guide_os_bot was confirmed again.
- Refreshed online backup: `/data/backups/pre_reminder_production_20261029T033257Z.db`, 2203648 bytes,
  mode 0600, SHA-256 `21830425cbf579e09a8762d813856da17ed09ab4126070d4b70e166eb0244edb`, full integrity `ok`.
  Backup hash matched after rollout. Earlier backups were retained.
- Backend uploaded only after frontend readiness and fresh backup. No new schema
  migration. Existing daily_tips storage was retained.
- Post-deploy all 119 expected runtime file hashes matched; consolidated runtime
  count was one. Startup logs showed one polling start and no traceback or
  duplicate-getUpdates conflict in the inspected window.
- Full production SQLite integrity `ok`. Original Mini App/dev-auth/service-auth/
  integration/outbound/replica flags matched preflight; no variable change.
- Deployed build_open_tour_keyboard generated the original bot callback plus
  “Открыть в приложении” with the correct production URL for a synthetic ID/date.
  This check sent no message and modified no tour/reminder records. Telegram
  getChatMenuButton confirmed the existing web_app menu.
- Public /health → 200; entry detail, daily tips range and reports → 401 without
  a session. No real-user session was obtained for an authenticated smoke.
- Staging remained on backend `4f2df896-9a08-43a1-88f4-da86da2fde47` and frontend
  `346e539b-36c7-4524-adb8-28af77e14a80`, both SUCCESS.
- Existing rollback builds remain recorded above. Roll back application builds
  only if needed; do not restore/drop production data for an application rollback.

Owner check: in a newly generated reminder from @Guide_os_bot, select “Открыть
в приложении”; verify the correct tour card, selected date after closing, and the
existing “Открыть тур” bot action. Historical messages retain their old keyboard.
Telegram/device and authenticated manual E2E are not claimed PASS by this release.

Release provenance remains local artifact `reminder-prod-50672bcfac857f8e`.
No Git commit/push or source-pin alignment was performed. Old configured Git pins
do not contain the daily-tips/reminder features; owner source alignment remains a
follow-up before a later deployment from Git. Current artifact manifests and
source archives preserve the exact promoted code.


## Git / production source-pin closure — 2026-10-29

Owner explicitly authorized agent commit/push and Railway source alignment, and
reported functional manual validation PASS. Earlier pending/manual/Git statements
in dated continuation sections above are historical and superseded here.

- Application commit: `569e8906c04a5380c96dc6a142b3cdd264b1f806`, pushed normally to `origin/main`; 31 code/test files plus 44 Markdown files. No force push; analytics/media/QR assets excluded.
- Production backend: `cfe3ab97-25e5-4952-a488-779e264bb52e` — SUCCESS.
- Production frontend: `3142566b-e4cb-4c6c-8632-f290f361ab5c` — SUCCESS.
- Both Git source pins: `juraldinho/guide_os`, main, exact application SHA above; frontend root `/miniapp` preserved. All non-source config and variable names unchanged; safe runtime flags verified unchanged.
- Fresh online backup: `/data/backups/pre_git_alignment_20261029T082726Z.db`, 2207744 bytes, SHA256 `f138d03b2465291ff93a4fb044e35e512135a542a9a0de2d09930b9732b1777f`, mode 0600, integrity ok; hash rechecked after deploy. Existing production SQLite `/data/guide_os.db` and volume retained.
- Live smoke: 119 runtime source hashes match prior tested artifact; daily_tips table retained; full SQLite integrity ok; one runtime process and one polling startup, no traceback/getUpdates conflict in inspected logs. Generated new reminder button and legacy callback correct; Telegram menu remains web_app. No test messages sent.
- Public frontend HTTP 200; `/assets/index-BZ2Xoudl.js`, SHA256 `b7be409966920d98d7a73fd9d46f204221ae0a5b52a9d2b5f33ba4a40bacd329`, identical to prior tested production bundle; production API target and reminder query handling present.
- API: `/health` 200; unauthenticated `/app/v1/entries/17`, `/app/v1/daily-tips/2026-10-29`, `/app/v1/reports/summary` 401.
- Staging remains backend `4f2df896-9a08-43a1-88f4-da86da2fde47`, frontend `346e539b-36c7-4524-adb8-28af77e14a80`, SUCCESS.
- GitHub Integration Contracts and Shared GuideShop Event E2E PASS. Main CI [run 40842230363](https://github.com/juraldinho/guide_os/actions/runs/40842230363) has **1 failed, 1882 passed, 3 skipped**: `test_entrypoint_import_without_bot_modules` fails without BOT_TOKEN because `services/miniapp_analytics.py` imports `config.TIMEZONE`. Analytics import predates this release (`2b4b3fa`); the local .env can mask this failure in earlier local runs. This separate defect remains open and was not silently changed during source alignment.

A subsequent documentation-only commit records this evidence. Production pins stay
on the application SHA above; no additional deployment is required for docs.
