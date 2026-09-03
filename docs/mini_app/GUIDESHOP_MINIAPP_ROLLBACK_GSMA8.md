# GuideShop Mini App — rollback & resilience runbook (GSMA8)

> Дата: 2026-09-03  
> Scope: official GuideShop reads in Mini App only. Sales remain **withdrawn** from Mini App. Do not reintroduce `/app/v1/guideshop/sales`.

## 1. How official reads degrade

When GuideShop upstream is slow/down or Mini App GuideShop reads are disabled:

| Layer | Behavior |
|---|---|
| Official companies / visits / points / history | Section-local loading → Russian error or «раздел временно отключён» + optional **Повторить** |
| Personal companies / commissions | Keep working; loaded independently |
| Calendar / Reports | Untouched; no GuideShop dependency |

User-facing Mini App codes (stable): `integration_disabled`, `access_denied`, `not_found`, `temporarily_unavailable`. No opaque IDs / tokens in UI.

## 2. Timeouts (bounded waits)

| Hop | Setting | Default | Notes |
|---|---|---|---|
| Guide OS → GuideShop upstream | `GUIDESHOP_API_TIMEOUT_SECONDS` | **10.0** s | `HTTPGuideShopClient` `aiohttp.ClientTimeout(total=…)` |
| Upstream transient retry | `GUIDESHOP_API_MAX_RETRIES` | **2** | Transient HTTP / network only (existing client) |
| Upstream Retry-After cap | `GUIDESHOP_API_MAX_RETRY_AFTER_SECONDS` | **10.0** s | |
| Mini App browser → Guide OS API (GuideShop GETs) | Frontend constant `GUIDESHOP_GET_TIMEOUT_MS` | **12_000** ms | AbortController timeout; maps to `temporarily_unavailable` |

No unbounded waits on GuideShop composition paths used by Mini App.

## 3. Frontend retry policy (safe)

- Official GuideShop **GET** only: **at most one** automatic retry on network failure, request timeout, or HTTP **503** with `temporarily_unavailable`.
- **No** automatic retry on `401` / `403` / `404` / `integration_disabled`.
- Personal places/commissions **POST/PATCH/DELETE**: **no** automatic retry (Idempotency-Key remains the write safety net). Manual **Повторить** only.
- AbortSignal: official company list/detail cancel on unmount / company change; sheets keep mount-cancel flags + HTTP timeout.

## 4. Cache decision

**No Mini App GuideShop response cache** in GSMA8. Prefer isolation and retries over short-lived cache complexity. Revisit only if owner reports flicker that cannot be fixed cheaper.

## 5. Observability (sanitized)

Backend logger `web_api.guideshop` emits:

```text
miniapp_guideshop route=<static_label> outcome=<ok|access_denied|integration_disabled|unavailable|not_found> latency_ms=<int>
```

Never log: JWT, session tokens, initData, opaque IDs, phone, display names, or other PII.

## 6. Kill switches (existing env — no new production flags)

| Flag | Effect |
|---|---|
| `GUIDESHOP_READS_ENABLED=false` | GuideShop reads disabled (bot + Mini App composition fail closed / integration_disabled) |
| `MINI_APP_API_ENABLED=false` | Mini App API process not served / disabled |
| `MINI_APP_ENABLED=false` | Hide Mini App MenuButton / bot entry (pilot rollback) |
| Incomplete GuideShop HTTP config | Fail closed (existing settings) |

Defaults are **off** for GuideShop reads and Mini App API in `.env.example`.

## 7. Rollback steps (owner-run)

1. To hide official GuideShop data only: set `GUIDESHOP_READS_ENABLED=false`, redeploy bot/API as usual. Personal companies remain.
2. To hide entire Mini App: set `MINI_APP_ENABLED=false` and `MINI_APP_API_ENABLED=false`, redeploy.
3. Do **not** re-enable Mini App sales routes or UI.
4. Confirm Calendar and Reports still load after rollback.

## 8. Related docs

- Contract: [`GUIDESHOP_SUBMODULES_CONTRACT_GSMA7.md`](GUIDESHOP_SUBMODULES_CONTRACT_GSMA7.md)
- Roadmap: [`GUIDESHOP_MINIAPP_ROADMAP.md`](GUIDESHOP_MINIAPP_ROADMAP.md)
- Env template: repo root `.env.example`
