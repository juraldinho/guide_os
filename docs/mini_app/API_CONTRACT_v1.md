# Guide OS Mini App — API Contract v1

> Version: **v1**
> Base path: `/app/v1`
> Status: **implemented (MA5–MA6)** — routes + initData session auth; dev stub gated by flag
> Last updated: 2026-08-29

## Implementation notes (MA5–MA6)

- Entrypoint: `guide_os_miniapp_api.py`
- Feature flag: `MINI_APP_API_ENABLED=false` by default
- **MA6 auth:** `POST /app/v1/session` with `init_data` → `session_token` (HMAC-SHA256 + `auth_date`)
- Dev auth (tests only): `MINI_APP_API_DEV_AUTH=true` + `dev_user_id`
- Sessions: `miniapp_sessions` table; `Authorization: Bearer <session_token>`
- Optional staging allowlist: `MINI_APP_API_ALLOWLIST`
- Frontend: mocks in `miniapp/src/` until **MA7**

## 1. Scope

This contract maps the MA3 React mock client (`miniapp/src/api/client.ts`, `miniapp/src/api/types.ts`) to a future Guide OS Web API. All business rules execute in **shared Python services**; routes validate auth, DTOs, idempotency, and map service results to this envelope.

**Out of scope for v1:** GuideShop mutations, personal places CRUD via Mini App, CSV export, multi-currency.

## 2. Transport

| Rule | Value |
|------|--------|
| Protocol | HTTPS only in production/staging |
| Encoding | JSON, UTF-8 |
| Calendar dates | `YYYY-MM-DD` (business timezone `Asia/Tashkent`) |
| Calendar times | `HH:MM` (24h, local Tashkent) |
| Money | integer USD minor units not used; **integer daily rate in USD** (`income_usd`) matching current bot |
| Public IDs | opaque strings at API boundary (never raw SQLite `INTEGER` ids) |
| Timestamps | ISO 8601 UTC where required (`created_at`, `updated_at`) |

### 2.1 Success envelope

```json
{
  "data": {},
  "meta": {
    "request_id": "req_opaque_string"
  }
}
```

### 2.2 Error envelope

```json
{
  "error": {
    "code": "time_conflict",
    "message": "Время тура пересекается с существующей записью.",
    "details": {}
  },
  "meta": {
    "request_id": "req_opaque_string"
  }
}
```

`message` — safe Russian user-facing text. `details` — machine-readable, form-safe fields only (no stack traces, internal ids, tokens).

### 2.3 Standard error codes

| Code | HTTP | When |
|------|------|------|
| `auth_required` | 401 | No session / expired session |
| `auth_invalid` | 401 | Bad initData signature, stale `auth_date`, wrong bot env |
| `forbidden` | 403 | Authenticated but not allowlisted (staging) or cross-user access |
| `not_found` | 404 | Entry/profile not found for current user |
| `validation_error` | 400 | DTO/schema violation |
| `date_warning` | 409 | Same date, non-overlapping times — save allowed after ack |
| `time_conflict` | 409 | Blocking overlap (time, full-day, day off) |
| `day_off_conflict` | 409 | Day off blocks date |
| `idempotency_replay` | 409 | Same `Idempotency-Key` replay with different body |
| `internal_error` | 500 | Unhandled failure (generic Russian message) |

### 2.4 Conflict response `details` (409)

**`date_warning`**

```json
{
  "conflict_kind": "date_warning",
  "date": "2026-08-28",
  "existing_entry": { /* CalendarEntry */ },
  "ack_field": "ack_date_warning"
}
```

Client retries write with `ack_date_warning: true` in body.

**`time_conflict` / `day_off_conflict`**

```json
{
  "conflict_kind": "time_conflict",
  "date": "2026-08-28",
  "existing_entry": { /* CalendarEntry */ },
  "reason_code": "time_overlap"
}
```

No save until user changes time or date.

## 3. Authentication and session

### 3.1 Bootstrap (no implementation in Step 1)

1. Telegram WebView provides `Telegram.WebApp.initData` (raw query string).
2. Mini App sends **raw** initData to `POST /app/v1/session` (not `initDataUnsafe`).
3. Server validates HMAC with environment bot token, checks `auth_date` freshness window.
4. Server derives `telegram_user_id` only from verified payload.
5. Server resolves Guide OS `user_id` via existing user registration (`register_user`).
6. Server issues short-lived session (HttpOnly cookie **or** bearer token — fixed at implementation; contract accepts either via `Authorization: Bearer` or session cookie).
7. Staging: after auth, enforce allowlist; fail closed if not allowed.

### 3.2 Session endpoints

#### `POST /app/v1/session`

Request:

```json
{
  "init_data": "query_id=...&user=...&auth_date=...&hash=..."
}
```

Response `data`:

```json
{
  "session_expires_at": "2026-08-29T12:00:00Z",
  "user": {
    "telegram_id": "3847291056",
    "display_name": "Алишер Каримов"
  }
}
```

#### `DELETE /app/v1/session`

Response `data`: `{}`

### 3.3 Request auth

All endpoints below require valid session. Missing/invalid → `auth_required` / `auth_invalid`. **Never** accept `user_id` from client body/query for authorization.

## 4. Idempotency (writes)

Mutating endpoints accept header:

```http
Idempotency-Key: <opaque-client-generated-uuid>
```

| Rule | Behavior |
|------|----------|
| Scope | Per user + endpoint + key |
| TTL | ≥ 24h (implementation detail) |
| Same key + same body | Return original success response |
| Same key + different body | `idempotency_replay` 409 |
| Applies to | `POST /tours`, `POST /day-offs`, `POST /tours/{id}/copy`, `PATCH` writes, `DELETE` |

## 5. Shared enums

```text
entry_type:     tour | day_off
status:         reserved | confirmed
payment_status: paid | unpaid
source:         guide_os_bot | mini_app
reports_period: month | year | all   (query helper; server uses from/to)
filter_status:  all | reserved | confirmed
filter_payment: all | paid | unpaid
```

## 6. Core schemas

### 6.1 `CalendarEntry` (response)

Maps mock `CalendarEntry`; field names **camelCase in JSON** to match frontend types.

```json
{
  "id": "ent_abc123",
  "type": "tour",
  "title": "Обзорный Самарканд",
  "startDate": "2026-08-28",
  "endDate": "2026-08-28",
  "startTime": "09:00",
  "endTime": "14:00",
  "status": "reserved",
  "payment": "unpaid",
  "income": 100,
  "company": "Silk Road Travel",
  "location": "Самарканд",
  "note": "Группа 8 человек",
  "source": "Guide OS bot",
  "dayLocations": {
    "2026-08-22": "Ташкент",
    "2026-08-23": "Самарканд"
  },
  "groupId": "grp_uuid",
  "createdAt": "2026-08-28T10:00:00Z",
  "updatedAt": "2026-08-28T10:00:00Z"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Public entry id |
| `type` | enum | `tour` \| `day_off` |
| `title` | string | Tour display name (**DB gap** — see §12) |
| `startDate`, `endDate` | string | ISO date |
| `startTime`, `endTime` | string \| null | Both null = full-day |
| `status` | enum | Tours only |
| `payment` | enum | Tours only |
| `income` | integer | Daily rate USD; `0` for day off |
| `company` | string? | |
| `location` | string? | Default location (`city` in DB) |
| `note` | string? | |
| `source` | string | `guide_os_bot` \| `mini_app` |
| `dayLocations` | object? | `date → location` overrides (**DB gap**) |
| `groupId` | string? | Multi-day group (`tour_group_id`) |

Day off: `title` may be `"Выходной"`; `status`/`payment` omitted or null.

### 6.2 `TourWriteBody` (create / full update)

Maps mock `TourFormValues`. Server derives `startTime`/`endTime` from `useTime`.

```json
{
  "title": "Обзорный Самарканд",
  "startDate": "2026-08-28",
  "endDate": "2026-08-28",
  "useTime": true,
  "startTime": "09:00",
  "endTime": "14:00",
  "company": "Silk Road Travel",
  "location": "Самарканд",
  "income": 100,
  "status": "reserved",
  "payment": "unpaid",
  "note": "",
  "ack_date_warning": false
}
```

Validation:

- `title` required, non-empty trim
- `endDate` ≥ `startDate`
- if `useTime`: `startTime` < `endTime`, both required
- if not `useTime`: times stored as null (full-day)
- `income` ≥ 0

### 6.3 `DayOffWriteBody`

```json
{
  "startDate": "2026-08-10",
  "endDate": "2026-08-10",
  "ack_date_warning": false
}
```

### 6.4 `DayLocationsPatch`

```json
{
  "locations": {
    "2026-08-22": "Ташкент",
    "2026-08-23": "Самарканд"
  }
}
```

Keys must be dates within the entry's group span.

### 6.5 `GuideProfile`

```json
{
  "name": "Алишер Каримов",
  "telegramId": "3847291056",
  "types": [
    { "type": "local", "label": "Локальный гид", "geo": ["Самарканд"] }
  ],
  "notifications": { "enabled": true, "time": "08:00" }
}
```

`types` — **read-only in v1** until schema exists (§12).

### 6.6 `ProfilePatch`

```json
{
  "name": "Алишер Каримов",
  "notifications": { "enabled": true, "time": "08:00" }
}
```

### 6.7 `ReportsSummary`

Matches MA3 `calcSummary` output (five metrics).

```json
{
  "tourCount": 4,
  "workDays": 12,
  "income": 490,
  "paidTours": 1,
  "unpaidTours": 3,
  "period": {
    "from": "2026-08-01",
    "to": "2026-08-28"
  }
}
```

Rules:

- Exclude `day_off` from tour counts and income
- `workDays` = **unique** dates with ≥1 matching tour day in range (not sum of per-tour days)
- `income` = Σ (`daily income` × overlapping days in range) per matching tour
- `paidTours` / `unpaidTours` = count of **tour records/groups** with any overlap in range (per MA3: one row per DB tour row / mock entry — document Step 2 alignment for multi-day groups)

### 6.8 `AvailabilityPreviewRequest`

```json
{
  "from": "2026-09-01",
  "to": "2026-09-30",
  "format": "text"
}
```

`format`: `text` (default) | `structured`

### 6.9 `AvailabilityPreviewResponse`

```json
{
  "heading": "Свободные даты в сентябре:",
  "text": "Свободные даты в сентябре: 1–3 сентября, 5 сентября и 7–10 сентября.",
  "freeDates": ["2026-09-01", "2026-09-02"],
  "ranges": [{ "start": "2026-09-01", "end": "2026-09-03" }]
}
```

Only **fully free** dates (no tour, reserved, confirmed, day off, timed partial). Partial-day gaps excluded from export text (D-029).

## 7. Time and conflict semantics

| Case | Rule |
|------|------|
| Full-day | `startTime` and `endTime` both null |
| Timed | both non-null, same calendar day in MVP |
| Invalid | exactly one time null → `validation_error` |
| Legacy bot tour | null times → full-day |
| Day off | always full-day; blocks entire date |
| Same date, non-overlapping times | `date_warning` 409; save after `ack_date_warning` |
| Overlapping times | `time_conflict` 409 |
| Full-day vs anything on date | `time_conflict` 409 |
| Day off on date | `day_off_conflict` 409 |

Overlap test (timed): `new_start < existing_end AND existing_start < new_end`. Touching boundaries (09–12 and 12–15) **do not** overlap.

**Logic lives in service layer** (`tour_service` extension), not handlers or routes.

## 8. User scoping (fail closed)

- Every query/mutation filters by session `user_id`.
- Public id lookup must include `user_id` constraint.
- Cross-user id → `not_found` (not `forbidden` leakage).
- GuideShop cross-user resolution pattern applies where relevant.

## 9. Endpoints

### 9.1 Calendar entries — `listEntries()`

#### `GET /app/v1/entries`

Query:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `from` | date | yes | Range start |
| `to` | date | yes | Range end inclusive |

Response `data`:

```json
{
  "entries": [ /* CalendarEntry[] */ ]
}
```

Includes tours and day offs overlapping range. Multi-day groups returned as one logical entry per group row strategy — **Step 2 must align**: prefer one `CalendarEntry` per `tour_group_id` with span min/max dates, or per-day rows with shared `groupId` (mock uses single row per group when created via Mini App; bot may have per-day rows).

**Recommendation for v1:** collapse by `groupId` in read mapper when rows share group + common fields.

### 9.2 Single entry — `getEntry(id)`

#### `GET /app/v1/entries/{entry_id}`

Response `data`: `CalendarEntry`

### 9.3 Create tour — `createTour(form)`

#### `POST /app/v1/tours`

Body: `TourWriteBody`  
Headers: `Idempotency-Key`  
Response `data`: `CalendarEntry`

On multi-day (`startDate` ≠ `endDate`), response includes full span; client may open day-location refinement flow.

### 9.4 Update tour — `updateTour(id, form)`

#### `PATCH /app/v1/entries/{entry_id}`

Body: `TourWriteBody` (partial allowed for PATCH semantics in implementation; mock sends full form)  
Headers: `Idempotency-Key`  
Response `data`: `CalendarEntry`

Group updates apply to whole `tour_group_id` where applicable (company, status, payment, income, note, times default).

### 9.5 Create day off — `createDayOff(form)`

#### `POST /app/v1/day-offs`

Body: `DayOffWriteBody`  
Headers: `Idempotency-Key`  
Response `data`: `CalendarEntry`

### 9.6 Delete — `deleteEntry(id)`

#### `DELETE /app/v1/entries/{entry_id}`

Headers: `Idempotency-Key`  
Response `data`: `{}`

Deletes entire multi-day group when entry belongs to group.

### 9.7 Copy tour (Mini App flow; not in `GuideOsClient` interface)

#### `POST /app/v1/entries/{entry_id}/copy`

Body:

```json
{
  "startDate": "2026-09-01",
  "endDate": "2026-09-01",
  "ack_date_warning": false
}
```

Headers: `Idempotency-Key`  
Response `data`: `CalendarEntry` (new entry)

Equivalent to mock `copyTour` → `createTour` with prefilled fields.

### 9.8 Day locations — `updateDayLocations(id, locations)`

#### `PATCH /app/v1/entries/{entry_id}/day-locations`

Body: `DayLocationsPatch`  
Headers: `Idempotency-Key`  
Response `data`: `CalendarEntry`

### 9.9 Profile — `getProfile()` / `updateProfile(patch)`

#### `GET /app/v1/profile`

Response `data`: `GuideProfile`

#### `PATCH /app/v1/profile`

Body: `ProfilePatch`  
Headers: `Idempotency-Key`  
Response `data`: `GuideProfile`

Maps to `get_user_profile`, `update_user_display_name`, `get_user_notification_settings`, `set_notifications_enabled`, `set_notification_time`.

### 9.10 Reports summary (MA3 client-side today)

#### `GET /app/v1/reports/summary`

Query:

| Param | Type | Description |
|-------|------|-------------|
| `from` | date | Period start |
| `to` | date | Period end |
| `status` | enum | `all` \| `reserved` \| `confirmed` |
| `payment` | enum | `all` \| `paid` \| `unpaid` |
| `company` | string? | Substring filter (optional v1) |
| `location` | string? | Substring filter (optional v1) |

Response `data`: `ReportsSummary`

Client maps `reportsPeriod` month/year/all to `from`/`to` locally. A selected year always uses January 1 through December 31 so planned future tours within that year are included.

### 9.11 Availability preview (MA3 client-side today)

#### `POST /app/v1/availability/preview`

Body: `AvailabilityPreviewRequest`  
Response `data`: `AvailabilityPreviewResponse`

Server uses shared formatter (port from `miniapp/src/features/reports/lib/availability.ts` to Python service in Step 2) so bot and Mini App do not diverge.

## 10. `GuideOsClient` → HTTP mapping

| Mock method | HTTP |
|-------------|------|
| `listEntries()` | `GET /app/v1/entries?from=&to=` (client picks range from UI context) |
| `getEntry(id)` | `GET /app/v1/entries/{id}` |
| `createTour(form)` | `POST /app/v1/tours` |
| `updateTour(id, form)` | `PATCH /app/v1/entries/{id}` |
| `createDayOff(form)` | `POST /app/v1/day-offs` |
| `deleteEntry(id)` | `DELETE /app/v1/entries/{id}` |
| `updateDayLocations(id, locs)` | `PATCH /app/v1/entries/{id}/day-locations` |
| `getProfile()` | `GET /app/v1/profile` |
| `updateProfile(patch)` | `PATCH /app/v1/profile` |
| *(Reports UI)* | `GET /app/v1/reports/summary` |
| *(Free-dates UI)* | `POST /app/v1/availability/preview` |
| *(Copy tour UI)* | `POST /app/v1/entries/{id}/copy` |

Future `GuideOsClient` extension (MA7): add `getReportsSummary`, `previewAvailability`, `copyEntry` without breaking existing methods.

## 11. Bot parity notes (non-API)

Telegram bot keeps date-level conflict **warnings** with user confirm. Mini App uses time-level blocking. Both must call the same write service; bot handler may map `date_warning` to Telegram confirm UX without exposing HTTP.

## 12. Explicit schema gaps (not in current DB)

Current `tours` table (`database/db.py`): `id`, `user_id`, `company`, `city`, `start_date`, `end_date`, `status`, `income`, `payment_status`, `note`, `entry_type`, `tour_group_id`, `created_at`.

**Not present today — required for Mini App parity:**

| Field / table | Purpose |
|---------------|---------|
| `title` (or agreed mapping) | Tour display name in Mini App |
| `start_time`, `end_time` | Timed tours |
| `source` | `guide_os_bot` vs `mini_app` |
| `day_locations` storage | Per-day location overrides (JSON column or child table) |
| `guide_types` / geography | Profile `types[]` (read-only mock today) |

**Naming mapping:** API `location` ↔ DB `city`.

Step 2 migrations must be additive, backup-tested, default null for legacy rows.

## 13. Versioning

- Breaking changes → `/app/v2`
- v1 additive fields allowed in JSON responses
- Clients ignore unknown fields

## 14. References

- `miniapp/GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md`
- `docs/mini_app/DECISIONS.md` (D-007, D-009, D-029)
- `miniapp/src/api/types.ts`
- `miniapp/src/features/reports/lib/summary.ts`
- `miniapp/src/features/reports/lib/availability.ts`
