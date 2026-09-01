# Guide OS Mini App — Next Task

> Обновлено: 2026-09-01

## Единственная следующая задача

**Нет активной coding или deployment задачи.** Следующий product, security, release или rollback task определяется владельцем.

## Public production pilot — ACTIVE

**Guide OS Mini App public production pilot — ACTIVE and owner-validated** (2026-09-01).

Owner explicitly approved **оставить pilot enabled** в production Guide OS bot. Mini App доступен через Telegram `MenuButtonWebApp`.

**Не** отключать, **не** redeploy для rollback и **не** продвигать к formal general release автоматически. Не трактовать pilot как temporary-disabled, staging-only, local-only или unauthorized.

### Reversible rollback (only when owner requests hide)

1. `MINI_APP_ENABLED=false`
2. `MINI_APP_API_ENABLED=false` — только если Mini App API тоже нужно остановить и нет shared-runtime requirement
3. Redeploy production bot service
4. Refresh `/start` или Telegram menu state as required

**Не выполнять rollback сейчас** — owner решил оставить pilot enabled.

## MA11 — not the active next step

**MA11 — hosted closed staging deployment** — deferred; owner instead authorized reversible **public production pilot**. Use [STAGING_SMOKE_MA9.md](../../docs/mini_app/STAGING_SMOKE_MA9.md) and [PRODUCTION_GATE_MA9.md](../../docs/mini_app/PRODUCTION_GATE_MA9.md) only when owner explicitly approves a future hosted staging or formal release path.

## Post-MA10 checkpoint closed

**Owner-approved Mini App MVP UX checkpoint — complete** (2026-08-31).

Commit `57405f4` (`Complete Guide OS Mini App prototype UX`) on `main`. Owner manual review PASS in dedicated local Telegram test bot.

## MA10 closed

**MA10 complete — local Telegram E2E PASS** (2026-08-30).

Validated locally: dedicated test bot, real initData, API on `127.0.0.1:8083`, Vite on `127.0.0.1:5173`, temporary Cloudflare Quick Tunnel, local SQLite, owner-only allowlist.

See `miniapp/.ai/SESSION.md` and `miniapp/README.md` § Local Telegram E2E.

## Stop

- No coding/deployment authorized without new owner request.
- Public production pilot **remains enabled** by owner decision.
- Formal general production release **not** separately declared.
- Production gate docs retained for future review — not a claim that every gate item is complete.
