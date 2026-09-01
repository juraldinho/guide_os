# Guide OS Mini App — Session

> Обновлено: 2026-09-01

## Public production pilot validation — **ACTIVE, owner-validated**

| Item | Status |
|------|--------|
| Date | 2026-09-01 |
| Environment | Production Guide OS bot + production Mini App (hosted frontend/API on production stack) |
| Access | Telegram `MenuButtonWebApp` on production bot |
| Accounts | Two real Telegram accounts (primary + second new user) |
| Bot ↔ Mini App sync | **PASS** |
| Cross-account isolation | **PASS** (IDOR manual verification) |
| Pilot status | **ACTIVE** — owner explicitly approved leaving pilot enabled |
| Formal general release | **Not** separately declared |

No Telegram IDs, bot tokens, session tokens, Railway variable values, raw `initData`, private URLs, or other secrets recorded in this file.

### Owner-validated production scenarios — primary account (PASS)

- Production bot opens Mini App successfully
- Telegram signed `initData` authentication succeeds
- Existing bot tours appear in Mini App
- Tours created in Mini App appear in bot
- Bot and Mini App share production data through shared services/database
- Tour create, edit, delete, day off, reports, profile, calendar operate correctly

### Owner-validated production scenarios — second account (PASS)

- New user `/start` and Mini App open
- Second account receives own empty/personal calendar state
- Second account does **not** see first account tours, reports, profile, or other private data
- Mini App tours and day-offs appear in bot for same second account
- Bot-created tours appear in Mini App for same second account
- Edit and delete synchronize both directions
- Return to first account confirms second-account data not visible
- Cross-account ownership isolation / IDOR manual verification passed

### Automated security evidence (latest verified on `main`)

| Suite | Result |
|-------|--------|
| Mini App security/API targeted tests | **133 passed** |
| Full backend suite | **1167 passed, 1 skipped** |
| Frontend month-picker tests | **32 passed** |
| Frontend feed tests | **32 passed** |
| Production frontend builds | successful |
| `git diff --check` | clean |

Relevant committed checkpoints on `main`:

- `2eb02f2` — Harden Mini App API authentication and validation
- `e8aed0b` — Color Mini App month cells by availability status
- `0076101` — Color Mini App calendar feed by day status

### Reversibility

Pilot remains reversible when owner later requests hide: `MINI_APP_ENABLED=false`, optionally `MINI_APP_API_ENABLED=false`, redeploy production bot, refresh menu/`/start`. **Not performed** — owner decided to keep pilot enabled.

---

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

## MA10 status: **complete — local Telegram E2E PASS** (historical)

### What was validated (local only — MA10)

| Layer | Setup |
|-------|--------|
| Bot | Dedicated local test bot (not production) |
| Auth | Real Telegram `initData` → session bearer (`MINI_APP_API_DEV_AUTH=false`) |
| API | `python guide_os_miniapp_api.py` on `127.0.0.1:8083` |
| Frontend | Vite dev server on `127.0.0.1:5173`, `VITE_USE_MOCK_API=false` |
| HTTPS for WebView | Temporary Cloudflare Quick Tunnel → local Vite (disposable URL; **not recorded**) |
| Database | Local development SQLite |
| Access control | Owner-only `MINI_APP_API_ALLOWLIST` |

At MA10 time Railway deployment was deferred and production was unchanged. **Subsequent 2026-09-01 public production pilot supersedes “production unchanged” for current operational state** — see section above.

### Owner-verified scenarios (MA10 local PASS)

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

### Railway note (historical)

Earlier MA10 attempt targeted Railway staging (`guide-os-staging-api`). Hosted closed staging checklist remains available for future owner-approved paths; **MA11 is not the active next step**.

### Next

No coding or deployment authorized until owner defines next product, security, release, or rollback task. Public production pilot **remains enabled** by owner approval.
