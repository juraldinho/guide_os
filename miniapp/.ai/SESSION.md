# Guide OS Mini App — Session

> Обновлено: 2026-08-31

## Post-MA10 UX checkpoint: **Owner-approved Mini App MVP UX — complete**

| Item | Status |
|------|--------|
| Commit | `57405f4` on `origin/main` — `Complete Guide OS Mini App prototype UX` |
| Validation | Owner manual review in dedicated local Telegram test bot |
| Interface | Current React Mini App UX approved as working MVP |
| Blocking UX issues | None known |

### Owner-verified UX (2026-08-31)

- Telegram Calendar–style sticky header; centered dynamic month/year; logo → Today
- Continuous forward calendar feed; precise month-boundary title switching
- Responsive seven-column month picker; picker anchored below sticky header at current feed position
- Reports: single `Итоги` title (header only); bottom action reachable above fixed navigation
- Automatic `Telegram.WebApp.ready()` + `expand()` on startup (owner device PASS)

Further UX refinements may be requested; no active coding task until owner defines next step.

## MA10 status: **complete — local Telegram E2E PASS**

### What was validated (local only)

| Layer | Setup |
|-------|--------|
| Bot | Dedicated local test bot (not production) |
| Auth | Real Telegram `initData` → session bearer (`MINI_APP_API_DEV_AUTH=false`) |
| API | `python guide_os_miniapp_api.py` on `127.0.0.1:8083` |
| Frontend | Vite dev server on `127.0.0.1:5173`, `VITE_USE_MOCK_API=false` |
| HTTPS for WebView | Temporary Cloudflare Quick Tunnel → local Vite (disposable URL; **not recorded**) |
| Database | Local development SQLite |
| Access control | Owner-only `MINI_APP_API_ALLOWLIST` |

Railway deployment was **explicitly deferred**. Production was **unchanged**.

No secrets, Telegram IDs, tokens, tunnel URLs, or raw initData are stored in this documentation.

### Owner-verified scenarios (PASS)

- Mini App opens from test bot; real session bootstrap
- Settings; Telegram ID displayed
- Tour create / persist after reopen / edit
- Overlapping-time blocking conflict; return to populated form; non-conflicting correction
- Day-off create and persist
- Delete confirmation `Нет` / confirmed deletion `Да`
- Multi-day tour; per-day locations
- Reports: by month, by selected year, all time; status/payment filters
- Reports year range: full calendar year (`January 1`–`December 31`), including planned future tours within that year; years after the current calendar year remain unavailable
- Availability (August and September); clipboard copy
- Profile/settings; light/dark theme

### Not claimed

- **No** staging deployment PASS
- **No** production deployment PASS
- **No** Railway frontend service created for this validation

### Railway note (historical, not part of MA10 PASS)

Earlier MA10 attempt targeted Railway staging (`guide-os-staging-api`). That path was recovered with Mini App flag off and is **out of scope** for the MA10 local E2E result. Hosted staging remains **MA11**, deferred.

### Next

1. Owner approval required before **MA11** (hosted closed staging on Railway).
2. When approved: follow [STAGING_SMOKE_MA9.md](../../docs/mini_app/STAGING_SMOKE_MA9.md), then production gate still **not** approved until separate sign-off.
3. No coding or deployment authorized until owner defines next product task.
