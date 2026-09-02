# Guide OS Mini App — Production Gate (MA9)

> Версия: 1.0
> Дата: 2026-08-29
> Аудитория: owner / release approver
> Статус: **gate checklist** — все пункты должны быть отмечены до любого production Mini App enable.

## Purpose

Prevent unsafe production activation of Guide OS Mini App Web API and static frontend. This gate is **documentation only** until owner explicitly approves **MA11+** hosted staging deploy work.

**Out of scope until approved:** Railway service changes, `bot.py` polling changes, production bot Menu/WebApp button, copying production DB to staging, enabling `MINI_APP_API_ENABLED` on production without sign-off below.

## Related documents

- [STAGING_SMOKE_MA9.md](STAGING_SMOKE_MA9.md) — must PASS before production consideration
- [API_CONTRACT_v1.md](API_CONTRACT_v1.md)
- [miniapp/GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md](../../miniapp/GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md) §4, §20–24

---

## 1. Environment isolation

| # | Requirement | Verified | Notes |
|---|-------------|----------|-------|
| 1.1 | Production `BOT_TOKEN` ≠ staging token; stored only in secrets manager / host env | ☐ | |
| 1.2 | Production SQLite volume/path ≠ staging; no copy of prod DB into staging for dev | ☐ | |
| 1.3 | Production Mini App static host URL ≠ staging URL | ☐ | |
| 1.4 | GuideShop keys/URLs for prod ≠ staging (if reads enabled) | ☐ | |
| 1.5 | `APP_ENV` or equivalent clearly marks production vs staging in operator runbooks | ☐ | |

---

## 2. API security and auth

| # | Requirement | Verified | Notes |
|---|-------------|----------|-------|
| 2.1 | All Mini App traffic **HTTPS** only (TLS on reverse proxy / platform) | ☐ | |
| 2.2 | `POST /app/v1/session` validates Telegram initData HMAC with **production** bot token | ☐ | |
| 2.3 | `MINI_APP_INITDATA_MAX_AGE` set (default 86400s); expired initData → `401 auth_invalid` | ☐ | |
| 2.4 | `MINI_APP_SESSION_TTL_SECONDS` set (e.g. 3600); short-lived bearer tokens | ☐ | |
| 2.5 | Only token **hash** stored in `miniapp_sessions`; opaque bearer returned once | ☐ | |
| 2.6 | **`MINI_APP_API_DEV_AUTH=false`** in production (no `dev_user_id`, no `Bearer dev:*`) | ☐ | |
| 2.7 | `MINI_APP_API_ALLOWLIST` reviewed if used; empty = all authenticated users | ☐ | |
| 2.8 | Protected routes never accept client `user_id`; session-only authorization | ☐ | |
| 2.9 | Cross-user resource IDs return `not_found`, not `forbidden` leakage | ☐ | |

---

## 3. Runtime and data safety

| # | Requirement | Verified | Notes |
|---|-------------|----------|-------|
| 3.1 | **No dual SQLite writers** on same volume (bot long-polling + separate `guide_os_miniapp_api.py` on same file) unless single coordinated runtime proven (Integration Foundation §4) | ☐ | |
| 3.2 | `MINI_APP_API_ENABLED=false` remains safe default in repo `.env.example` | ☐ | |
| 3.3 | Production enable uses explicit env on host only, not committed `.env` | ☐ | |
| 3.4 | Additive DB migrations applied with backup before enable | ☐ | |
| 3.5 | Bot handlers unchanged unless separate approved release; shared services only | ☐ | |
| 3.6 | Frontend build: `VITE_USE_MOCK_API=false`, correct `VITE_API_BASE_URL` for prod API | ☐ | |

---

## 4. Observability and logging

| # | Requirement | Verified | Notes |
|---|-------------|----------|-------|
| 4.1 | Logs exclude: raw initData, session tokens, BOT_TOKEN, JWT/PEM, full profile notes | ☐ | |
| 4.2 | Error responses use contract envelope; Russian user messages; no stack traces to client | ☐ | |
| 4.3 | Metrics/alerts: auth failure rate, 5xx rate, latency — without PII in labels | ☐ | |
| 4.4 | No production tokens or user content in CI logs or issue attachments | ☐ | |

---

## 5. Backup, rollback, and kill switch

| # | Requirement | Verified | Notes |
|---|-------------|----------|-------|
| 5.1 | SQLite backup procedure documented and tested (`/backup` bot command or host snapshot) | ☐ | |
| 5.2 | Rollback: set `MINI_APP_API_ENABLED=false` stops API; hide Web App menu button | ☐ | |
| 5.3 | Rollback: redeploy previous static `dist/` if frontend regression | ☐ | |
| 5.4 | Forward-fix vs restore decision documented if migration fails | ☐ | |
| 5.5 | Existing Telegram bot polling remains operational if Mini App disabled | ☐ | |

---

## 6. Staging evidence

| # | Requirement | Verified | Notes |
|---|-------------|----------|-------|
| 6.1 | [STAGING_SMOKE_MA9.md](STAGING_SMOKE_MA9.md) completed with overall **PASS** | ☐ | Date: __________ |
| 6.2 | Staging smoke used real initData in WebView (not dev auth stub) | ☐ | |
| 6.3 | Allowlist tested if production will use allowlist | ☐ | |
| 6.4 | Reports + availability verified server-side (MA8 HTTP paths) | ☐ | |

---

## 7. Automated regression (repo CI)

Before production enable, latest CI / local full suite green on release branch:

| Check | Command | Pass |
|-------|---------|------|
| Python full suite | `.venv/bin/python -m pytest -q` | ☐ |
| Mini App unit tests | `cd miniapp && npm test` | ☐ |
| Mini App build | `cd miniapp && npm run build` | ☐ |
| Mini App API tests | `.venv/bin/python -m pytest -q tests/test_miniapp_api.py tests/test_miniapp_telegram_auth.py` | ☐ |

---

## 8. Explicitly out of scope (until separate approval)

- Wiring Mini App button into **production** bot menu / `bot.py`
- Railway new service or port exposure without architecture review
- `MINI_APP_API_DEV_AUTH=true` on any production host
- Sharing one SQLite file between two independent Railway processes
- Production GuideShop write paths
- Copying production user data into tickets or docs

---

## 9. Owner sign-off

Production Mini App Web API and static deploy are **not authorized** until all applicable sections above are checked and signed.

| Field | Value |
|-------|-------|
| Release scope (staging only / production Mini App) | __________ |
| Target date | __________ |
| Staging smoke reference (date, PASS) | __________ |
| Approver name | __________ |
| Sign-off | ☐ **APPROVED** for deploy work (MA11+) ☐ **NOT APPROVED** |

**Approver statement (optional):** I confirm staging smoke passed, secrets are isolated, dev auth is disabled for production, and rollback/kill switch is understood.

---

## 10. Post-enable verification (production smoke, minimal)

After **MA11+** hosted staging deploy only, repeat subset of staging smoke on **production** with allowlisted operator account:

1. Session via real initData
2. One tour create + delete
3. Reports summary one month
4. Availability preview
5. DELETE session

Record pass/fail privately; do not commit evidence with tokens.

## Future roadmap note

Daily tips are not covered by this historical MA9 gate. Before their release, complete the bot/API/Mini App security and E2E gates defined in `../TIPS_ROADMAP.md`.

GuideShop Mini App is also outside this historical gate. Use the GSMA9/GSMA10 gates in `GUIDESHOP_MINIAPP_ROADMAP.md` before its release.
