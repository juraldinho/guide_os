# Guide OS Mini App

React frontend + disposable MA2 prototype + Web API backend (**MA0–MA10 complete** on local E2E). Telegram-бот не изменён; production rollout не включён.

## Status (2026-08-30)

| Этап | Статус | Описание |
|------|--------|----------|
| MA0 | ✅ | Product docs, DECISIONS, AGENTS |
| MA1 | ✅ | Low-fi UX prototype |
| MA2 | ✅ | High-fi prototype (approved) |
| MA3 | ✅ | React + Vite, all MVP screens on **mocks** |
| MA4 | ✅ | Shared services + DB migrations + API contract |
| MA5 | ✅ | `web_api/` transport layer |
| MA6 | ✅ | Telegram initData HMAC + session bearer tokens |
| **MA7** | ✅ | React HTTP client → API (mock default) |
| **MA8** | ✅ | Reports + free-dates via API (HTTP mode) |
| **MA9** | ✅ | Staging smoke + production gate docs |
| **MA10** | ✅ | **Local Telegram E2E PASS** (real initData, local stack) |
| **MA11** | ⏸ | Hosted closed staging deploy — **deferred until owner approval** |

## Quick start — React UI (mock mode, default)

```sh
cd miniapp
npm install
npm run dev
```

Open `http://localhost:5173/`.

## Quick start — React UI + local API

```sh
# terminal 1 — backend
MINI_APP_API_ENABLED=true MINI_APP_API_DEV_AUTH=true python guide_os_miniapp_api.py

# terminal 2 — frontend (dev auth stub)
cd miniapp
VITE_USE_MOCK_API=false VITE_DEV_USER_ID=123456789 npm run dev
```

Vite proxies `/app/v1` → `http://127.0.0.1:8083`. In Telegram WebView use real `initData` (no `VITE_DEV_USER_ID`).

## Local Telegram E2E (MA10 validated)

Use a **dedicated test bot** (not production), **local SQLite**, and **real initData** (`MINI_APP_API_DEV_AUTH=false`). Do not commit tokens, Telegram IDs, or tunnel URLs.

**Terminal 1 — API** (listens on `127.0.0.1:8083`):

```sh
MINI_APP_API_ENABLED=true \
MINI_APP_API_DEV_AUTH=false \
MINI_APP_API_ALLOWLIST=<owner_telegram_user_id> \
python guide_os_miniapp_api.py
```

Set `BOT_TOKEN` for the test bot in env (see `.env.example`). Optional: `DATABASE_PATH` for an isolated local DB file.

**Terminal 2 — frontend** (`127.0.0.1:5173`, HTTP mode):

```sh
cd miniapp
VITE_USE_MOCK_API=false npm run dev
```

Vite proxies `/app/v1` → API. `index.html` loads `telegram-web-app.js`; `vite.config.ts` allows `.trycloudflare.com` hosts.

**Terminal 3 — HTTPS tunnel** (Telegram WebView requires HTTPS):

```sh
cloudflared tunnel --url http://127.0.0.1:5173
```

Copy the printed `https://*.trycloudflare.com` URL (**disposable** — do not store in repo). Set the test bot **Web App URL** to that HTTPS origin in BotFather.

**Reports year period:** selected year = full calendar year (`January 1`–`December 31`), including planned future tours in that year. A year after the current calendar year is not selectable.

Railway and production were **not** used for MA10 validation. Hosted staging is **MA11** (deferred) — see [STAGING_SMOKE_MA9.md](../docs/mini_app/STAGING_SMOKE_MA9.md).

```sh
npm test
npm run build
```

## Quick start — Web API

**Production auth path** (real `BOT_TOKEN` in env):

```sh
MINI_APP_API_ENABLED=true python guide_os_miniapp_api.py
```

```sh
curl -X POST http://127.0.0.1:8083/app/v1/session \
  -H 'Content-Type: application/json' \
  -d '{"init_data":"<Telegram.WebApp.initData>"}'
# → use data.session_token as Authorization: Bearer <token>
```

**Dev stub only** (explicit flag, tests/local):

```sh
MINI_APP_API_ENABLED=true MINI_APP_API_DEV_AUTH=true python guide_os_miniapp_api.py
```

Env: `MINI_APP_SESSION_TTL_SECONDS`, `MINI_APP_INITDATA_MAX_AGE`, optional `MINI_APP_API_ALLOWLIST` — see `.env.example`.

Feature flag **`MINI_APP_API_ENABLED=false`** by default.

## Staging smoke and production gate (MA9)

Before any production Mini App enable:

1. Execute [docs/mini_app/STAGING_SMOKE_MA9.md](../docs/mini_app/STAGING_SMOKE_MA9.md) on **isolated staging** (separate bot, DB, HTTPS).
2. Complete [docs/mini_app/PRODUCTION_GATE_MA9.md](../docs/mini_app/PRODUCTION_GATE_MA9.md) and obtain owner sign-off.

Staging requirements (summary):

| Variable / setting | Staging value |
|--------------------|---------------|
| `BOT_TOKEN` | Staging bot only (secrets manager) |
| `MINI_APP_API_ENABLED` | `true` |
| `MINI_APP_API_DEV_AUTH` | **`false`** (real initData) |
| `MINI_APP_API_ALLOWLIST` | Tester Telegram IDs (optional) |
| `VITE_USE_MOCK_API` | `false` at build time |
| `VITE_API_BASE_URL` | Public staging API base URL |

Kill switch: `MINI_APP_API_ENABLED=false` or remove Web App button on bot.

**MA10 (2026-08-30):** Local Telegram E2E PASS — see § Local Telegram E2E above and `miniapp/.ai/SESSION.md`. **Not** a staging or production deployment PASS.

**MA11 (deferred):** Hosted closed staging on Railway — use [STAGING_SMOKE_MA9.md](../docs/mini_app/STAGING_SMOKE_MA9.md) only after owner approval.

## Architecture

```text
Telegram Mini App (miniapp/src/)     [mock default; full HTTP stack MA7–MA8]
        |
        |  HTTPS + initData → session bearer
        v
Guide OS Web API (web_api/)          [MA5–MA6, flag off]
  telegram_auth.py — initData HMAC
  auth.py — miniapp_sessions
        |
        v
shared services (MA4)
        |
        v
Guide OS SQLite
```

## Documentation

- [AGENTS.md](AGENTS.md)
- [GuideOS_miniapp_Development_Operating_System.md](GuideOS_miniapp_Development_Operating_System.md)
- [GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md](GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md)
- [docs/mini_app/API_CONTRACT_v1.md](../docs/mini_app/API_CONTRACT_v1.md)
- [docs/mini_app/STAGING_SMOKE_MA9.md](../docs/mini_app/STAGING_SMOKE_MA9.md)
- [docs/mini_app/PRODUCTION_GATE_MA9.md](../docs/mini_app/PRODUCTION_GATE_MA9.md)
- [.ai/NEXT_TASK.md](.ai/NEXT_TASK.md) — **MA11** (deferred)

## Constraints

- Russian UI, USD only
- Bot handlers unchanged
- No production Mini App until staging gate (**MA11+** when approved)

## Future daily tips roadmap

Owner approved a not-yet-implemented bot-first daily tips feature: one amount per user and calendar date, independent of tours. After bot validation, the shared API will expose it to this Mini App. See [`../docs/TIPS_ROADMAP.md`](../docs/TIPS_ROADMAP.md).

## Active GuideShop Mini App roadmap

Owner activated the GuideShop Mini App workstream. The planned third bottom module combines user-owned personal companies/commissions with the official read-only GuideShop catalog through the Guide OS API. Current stage is GSMA0 contract/audit; implementation has not started. See [`../docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`](../docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md).
