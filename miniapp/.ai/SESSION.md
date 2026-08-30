# Guide OS Mini App — Session

> Обновлено: 2026-08-30

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
