# GuideShop official submodules — contract GSMA7

> Дата: 2026-09-03  
> Статус: **GSMA7 optional submodules complete** (Visits + Points summary + Sales + Payout/history); next = **GSMA8**  
> Назначение: product/API audit for optional official visits / sales / points / payout-history in Mini App

При конфликте приоритет: текущий код и тесты → этот файл → `GUIDESHOP_MINIAPP_CONTRACT_GSMA0.md` → roadmap → прочие docs.

---

## 1. Context and invariants

### Already shipped (GSMA0–GSMA6B)

- Unified GuideShop page: shared search, **Официальные компании** (read-only), **Мои компании** + commissions.
- Official companies: `GET /app/v1/guideshop/companies` and `GET /app/v1/guideshop/companies/{companyId}` via request-scoped GuideShop provider (same pattern as Telegram GuideShop UI).
- Frontend never receives GuideShop JWT/credentials; never calls GuideShop upstream directly.
- Official failure must not hide personal companies; personal failure must not hide official companies.
- Official and personal records are never merged by name.

### Explicitly deferred by GSMA0

Visits, sales, points, and payout/history were **out of the first Mini App release**. They remain optional. Existing upstream methods must **not** be exposed in Mini App only because the client already implements them.

### Composition pattern to reuse (names only — do not implement in GSMA7A)

Follow `web_api/routes/guideshop_companies.py`:

1. Mini App bearer session via `_auth_or_error()`.
2. `telegram_user_id` only from session.
3. `configure_miniapp_guideshop_provider` / `provider.service_for(user_id)`.
4. Call existing `GuideShopClient` / thin `GuideShopUIService` read helpers.
5. Map approved DTO fields to Mini App camelCase JSON.
6. Stable Mini App errors: `401 auth_*`, `403 access_denied`, `404 not_found`, `503 integration_disabled`, `503 temporarily_unavailable`.
7. Opaque IDs never in user-facing errors or logs; Russian messages; no HTTP 500 for expected GuideShop failures.
8. Close request-scoped client after success and failure.

---

## 2. Inventory — existing GuideShop client (read-only)

Upstream base: `/integration/v1/me/...` (via `HTTPGuideShopClient` / `InMemoryGuideShopClient`).

| Client method | Upstream path | Envelope | Notes |
|---|---|---|---|
| `list_companies()` | `GET .../companies` | `APIListResponseDTO[CompanyDTO]` | Already composed for Mini App (GSMA5) |
| `list_visits(cursor?)` | `GET .../visits` | list + `page.next_cursor` / `has_more` | Cursor opaque |
| `get_visit(visit_id)` | `GET .../visits/{id}` | `APIDetailResponseDTO[VisitDTO]` | Exact opaque ID |
| `list_sales(cursor?)` | `GET .../sales` | list + page | |
| `get_sale(sale_id)` | `GET .../sales/{id}` | detail | |
| `list_points(status?, cursor?, visit_id?)` | `GET .../points` | list + page | Optional filters |
| `get_points_summary()` | `GET .../points/summary` | `PointsSummaryDTO` | Totals + per-company |
| `get_points_transaction(id)` | `GET .../points/{id}` | detail accrual | |
| `list_history(cursor?)` | `GET .../history` | list `PointsPayoutDTO` + page | Payout history |

There is **no** upstream create/update/delete for these resources in the Guide OS client protocol. Guide OS remains read-only.

### DTO field inventory (authoritative: `services/guide_shop_contracts.py`)

**VisitDTO**

- `visit_id`, `company_id`, `guide_membership_id` (opaque)
- `visit_at` (UTC)
- `status`: `active` \| `completed` \| `cancelled`
- `tourist_count` (≥ 0)
- `customer_payment_status`: `unpaid` \| `paid`
- `customer_paid_at` (nullable; required when paid)
- `created_at`, `updated_at`

**SaleDTO**

- `sale_id`, `visit_id`, `company_id` (opaque)
- `amount` (exact decimal string, USD), `currency` = `USD`
- `status`: `active`
- `payment_method`: `cash` \| `card` \| `transfer` \| `unknown`
- `comment` (optional string)
- `category_id` (nullable opaque), `category_name`
- `created_at`, `updated_at`

**PointsAccrualDTO**

- `points_accrual_id`, `company_id`, `visit_id`
- `amount` (PTS decimal string), `unit` = `PTS`
- `status`: `pending` \| `credited`
- `calculated_at`, `credited_at?`, `updated_at`, `payout_id?`

**PointsPayoutDTO** (history)

- `payout_id`, `points_accrual_id`, `company_id`, `visit_id`
- `amount`, `unit` = `PTS`
- `paid_at`, `created_at`

**PointsSummaryDTO**

- `unit` = `PTS`
- `pending_total`, `credited_total`
- `companies[]`: `company_id`, `display_name`, `pending_total`, `credited_total`

**PageDTO** (lists)

- `next_cursor` (opaque string \| null), `has_more`

Mini App list envelopes should continue to expose only `{ nextCursor }` (as GSMA5), without decoding cursors.

---

## 3. Proposed Guide OS Web API composition (names only)

All under `/app/v1/guideshop/...`, Mini App bearer required, GET-only, same provider as companies.

| Method | Proposed path | Maps from | Purpose |
|---|---|---|---|
| `GET` | `/app/v1/guideshop/visits` | `list_visits` | Official visits list |
| `GET` | `/app/v1/guideshop/visits/{visitId}` | `get_visit` | Visit detail |
| `GET` | `/app/v1/guideshop/sales` | `list_sales` | Official sales list |
| `GET` | `/app/v1/guideshop/sales/{saleId}` | `get_sale` | Sale detail |
| `GET` | `/app/v1/guideshop/points/summary` | `get_points_summary` | Points summary |
| `GET` | `/app/v1/guideshop/points` | `list_points` | Points accruals list |
| `GET` | `/app/v1/guideshop/points/{pointsAccrualId}` | `get_points_transaction` | Accrual detail |
| `GET` | `/app/v1/guideshop/history` | `list_history` | Payout history |

**Optional query params (decide in GSMA7B for the chosen submodule only):**

- opaque `cursor` passthrough;
- for points: `status`, `visitId` if product needs filters;
- **do not** invent company-scoped upstream filters unless the client already supports them (visits/sales lists are guide-scoped today; UI may filter client-side by `companyId` after load, or defer company-scoped lists).

**Not proposed:** POST/PUT/PATCH/DELETE, commission routes on official entities, linking to `personal_places`.

---

## 4. Per-submodule product analysis

### 4.1 Visits — **recommended first submodule**

| Topic | Contract |
|---|---|
| User value | See when the guide brought tourists to official partners; foundational for understanding sales/points later. |
| Entry point | Prefer **from official company detail** (“Визиты”) + optional compact list on GuideShop official area later. Not a new bottom-nav tab. |
| List UI fields | Date/time (`visit_at`), tourist count, visit status (RU labels), customer payment status; company display name resolved from official companies map when available — **never show opaque IDs**. |
| Detail UI fields | Same + paid-at when paid; no edit actions. |
| Degraded states | Same as companies: `integration_disabled`, `access_denied`, `temporarily_unavailable`, section-local; personal companies remain available. |
| Risks | `guide_membership_id` must not surface; tourist_count is operational not PII names; do not invent tourist names. |
| Why first | Sales and points reference `visit_id`; lowest confusion with personal commissions; clear read-only story. |

### 4.2 Points summary (+ optional accruals)

| Topic | Contract |
|---|---|
| User value | Pending vs credited PTS across official partners — high engagement, but easy to confuse with personal commission “баллы” history. |
| Entry point | Official company detail and/or a read-only “Баллы GuideShop” block under official section — **separate label** from personal commissions. |
| List/summary UI | Summary: pending/credited totals; per-company breakdown by `display_name`. Accrual list only if summary alone is insufficient. |
| Detail UI | Accrual: amount PTS, status, dates; link conceptually to visit without exposing opaque IDs in copy. |
| Degraded states | Same envelope codes; empty summary ≠ error. |
| Risks | **High:** naming collision with personal commissions / former “points” UX. Must say “баллы GuideShop” / official PTS and never sum with personal commission money. |
| Order | Second after visits (needs visit context for accruals). |

### 4.3 Sales

| Topic | Contract |
|---|---|
| User value | Official USD sales attributed to the guide’s visits — money visibility. |
| Entry point | From visit detail and/or official company detail; not a new nav tab. |
| List UI | Amount + USD, category name, payment method, created date; company name when resolvable. |
| Detail UI | Same + comment when present; no mutations. |
| Degraded states | Same as companies. |
| Risks | **High money confusion** with personal commission income; must badge “GuideShop” and never mix currencies/totals with personal commissions. Amounts are upstream decimal strings, not personal minor units. |
| Order | Third — after visits (sales require `visit_id`). |

### 4.4 Payout / history

| Topic | Contract |
|---|---|
| User value | When PTS were paid out — closes the points loop. |
| Entry point | From points summary (“История выплат”) only after points summary exists. |
| List UI | Paid amount PTS, paid_at, company display name when resolvable. |
| Detail UI | Optional; list may be enough for v1 of this submodule. |
| Degraded states | Same as companies. |
| Risks | Confuse with personal commission history; must stay official-only and PTS-only. |
| Order | Fourth — depends on points product language being settled. |

---

## 5. Recommended implementation order

Default proposal (owner may override via §8):

```text
1. Visits (list + detail)     ← recommended GSMA7B first slice
2. Points summary (+ accruals if needed)
3. Sales (list + detail)
4. Payout / history
```

Each slice = Web API composition + frontend client/types/mock + official-section/detail UX + targeted tests — **one submodule per coding task**, ≤5 application files unless owner approves more.

---

## 6. Shared Mini App UX / error rules (all submodules)

- Reuse official section isolation: failures stay inside official GuideShop UI; Calendar / Reports / personal companies stay up.
- Source badge text `GuideShop` (not color alone).
- No official edit / deactivate / delete / “add commission”.
- Opaque IDs never rendered; never logged in user-facing strings.
- Status labels in Russian for known enums; unknown future enum values shown neutrally (same pattern as official company status).
- Pagination: preserve opaque `nextCursor`; no decode.
- HTML/script-like strings remain inert JSON text.
- Do not auto-open submodule screens when companies load; user navigates deliberately.

---

## 7. Explicit OUT OF SCOPE (GSMA7A and first GSMA7B slice)

- GuideShop writes (create visit/sale/points/payout).
- Linking or merging official ↔ personal companies by name or ID.
- Changing Telegram bot GuideShop UX or menu.
- New database tables / schema.
- Railway / production / feature-flag flips for submodule exposure without owner release scope.
- Enabling all four submodules in one task.
- Changing personal places or personal commissions behavior.
- Direct frontend → GuideShop HTTP.

---

## 8. Owner decision — approve exactly one first submodule for GSMA7B

Check **exactly one**:

- [x] **Visits** (recommended) — list + detail via proposed `/app/v1/guideshop/visits`  
  Owner approved 2026-09-03 → implemented as **GSMA7B**.
- [x] **Points summary** — `/app/v1/guideshop/points/summary` (± accruals list later)  
  Owner approved 2026-09-03 (after Visits) → implemented as **GSMA7C** (summary-only; no accruals/history).
- [x] **Sales** — list + detail via `/app/v1/guideshop/sales`  
  Owner approved 2026-09-03 (after Visits + Points summary) → implemented as **GSMA7D**.
- [x] **Payout / history** — `/app/v1/guideshop/history`  
  Owner approved 2026-09-03 (after Visits + Points + Sales) → implemented as **GSMA7E** (list-only).
- [ ] **None yet** — keep submodules deferred; next coding stays elsewhere

**GSMA7 optional submodule set complete** for owner-approved slices (visits, points summary, sales, history).

Owner notes (optional):

```text
_________________________________________________________________
_________________________________________________________________
```

After a single checkbox is chosen, the next coding task is **GSMA7B** for that submodule only, using this contract and the GSMA5 companies composition pattern.

---

## 9. GSMA7B readiness checklist (for the chosen submodule)

When owner picks one module, GSMA7B must deliver at least:

1. Thin read helpers on `GuideShopUIService` (or equivalent) without parsing Telegram screen HTML.
2. Web API GET routes + DTO mapping + stable errors + provider config reuse.
3. Frontend types + `GuideOsClient` methods + HTTP + mock parity.
4. Official UI entry from existing official company detail / section — no new bottom tab.
5. Targeted tests: auth, mapping, null/unknown status, cursor opacity, isolation from personal, no mutation routes, 401 recovery.
6. No schema/Railway/production changes unless separately approved.
