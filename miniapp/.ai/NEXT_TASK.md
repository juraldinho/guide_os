# Guide OS Mini App — Next Task

> Обновлено: 2026-08-29

## Единственная следующая задача

**MA6 — Telegram Mini App session auth** (replace MA5 dev stub in `web_api/auth.py` with initData validation).

## Scope MA6

1. Validate Telegram `init_data` on `POST /app/v1/session` using bot token HMAC (no secrets in repo; tests with synthetic initData).
2. Issue short-lived session token (or signed session) for subsequent `/app/v1/*` requests.
3. Remove or gate `MINI_APP_API_DEV_AUTH` behind explicit test-only flag; document dev workflow.
4. Contract tests for auth success/failure paths per `API_CONTRACT_v1.md`.

## Inputs

- `docs/mini_app/API_CONTRACT_v1.md` (auth section)
- `web_api/auth.py`, `web_api/routes/session.py`
- `miniapp/GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md`

## Constraints

- Mini App React **stays on mocks** until MA7.
- Bot handlers unchanged.
- No production rollout.

## Definition of Done (MA6)

- Real initData auth on session create; dev stub documented for local tests only.
- Unauthorized requests return `auth_required` / `auth_invalid` per contract.
- Pytest auth suite passes.
- No secrets in repo.

## Stop

Do not wire Mini App HTTP client (MA7) until MA6 reviewed.
