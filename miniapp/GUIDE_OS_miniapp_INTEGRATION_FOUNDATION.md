# Guide OS Mini App — Integration Foundation

> Версия: 1.0  
> Дата: 2026-08-28  
> Статус: целевая архитектура; реализация ещё не начата

## 1. Цель

Определить безопасную техническую границу между Telegram Mini App, Guide OS Web API, существующей бизнес-логикой Guide OS и read-only GuideShop integration.

Документ не разрешает production activation и не является готовым API contract. Конкретные schemas фиксируются отдельным versioned contract перед реализацией MA5.

## 2. System context

```text
┌────────────────────┐
│ Telegram client    │
│ Mini App WebView   │
└─────────┬──────────┘
          │ HTTPS + initData/session
          v
┌────────────────────┐
│ Guide OS Web API   │
│ auth + transport   │
└─────────┬──────────┘
          │ typed calls
          v
┌────────────────────┐
│ Guide OS services  │<──────── Telegram bot handlers
│ business rules     │
└──────┬────────┬────┘
       │        │ existing authenticated client
       v        v
 Guide OS DB   GuideShop /integration/v1
```

## 3. Ownership

### Guide OS owns

- Telegram user mapping;
- immutable `guide_os_id`;
- display name;
- guide professional types/geography;
- personal calendar;
- tours and day offs;
- time intervals added for Mini App;
- daily location overrides;
- income/payment status;
- notification settings;
- personal places and self-reported records.

### GuideShop owns

- Partner Company;
- official Visit;
- official Sale;
- PTS and payout history;
- official company-guide relationship.

Mini App does not become owner of any domain data. It is a presentation and interaction surface.

## 4. Runtime boundary

### Initial production-safe shape

Guide OS Telegram bot and Web API should run in one coordinated Guide OS runtime while SQLite remains the database. This avoids two independent services writing the same SQLite volume.

Acceptable internal models:

- one process hosting bot tasks and HTTP server with controlled lifecycle; or
- another single-runtime composition proven safe for the existing deployment.

Not acceptable:

- independent bot service and API service sharing one SQLite volume;
- frontend reading a DB file;
- Mini App backend duplicating production data;
- copying production DB into staging.

Migration to PostgreSQL is a separate approved workstream with backup, restore, reconciliation and rollback evidence.

## 5. Layer responsibilities

### Frontend

- render UI;
- collect form input;
- Telegram WebApp adapter;
- theme, viewport and safe area;
- typed API calls;
- local ephemeral UI state;
- validation hints for convenience;
- no authoritative identity or business decisions.

### Web API

- validate auth/session;
- parse and validate request DTO;
- resolve current user server-side;
- call Guide OS services;
- map domain result/errors to API envelope;
- apply rate limits, idempotency and safe logging;
- no direct business calculations in routes.

### Services

- create/update/copy/delete tours;
- conflict detection;
- time overlap;
- calendar projection;
- reports;
- availability text inputs/ranges;
- profile rules;
- ownership boundary before query/mutation.

### Database

- persistence;
- constraints/indexes/migrations;
- transactional writes;
- user-scoped queries;
- no HTTP/Telegram concerns.

## 6. Telegram authentication

### 6.1 Bootstrap

1. Telegram opens Mini App and provides `Telegram.WebApp.initData`.
2. Frontend sends raw initData to Guide OS auth endpoint over HTTPS.
3. Server validates signature using the test/production bot token for the current environment.
4. Server validates required fields and `auth_date` freshness.
5. Server derives Telegram user identity only from verified data.
6. Server creates a short-lived authenticated session.
7. Subsequent requests use the approved session transport.

### 6.2 Never trust

- `initDataUnsafe`;
- `user_id` in URL/body/header;
- frontend role/profile claims;
- unsigned launch parameters;
- stale initData;
- signature made with another environment bot.

### 6.3 Session requirements

Exact cookie/token choice is fixed in MA5/MA6. Requirements:

- short TTL;
- rotation/renewal policy;
- server-resolved current user;
- logout/expiry handling;
- CSRF protection if cookie-based;
- secure, HttpOnly and SameSite settings where applicable;
- no session material in logs or analytics;
- staging allowlist enforced after authentication;
- revoked/disabled access fails closed.

## 7. API conventions

Base path:

```text
/app/v1
```

Rules:

- JSON UTF-8;
- ISO 8601 dates/timestamps;
- business timezone `Asia/Tashkent` for calendar meaning;
- server timestamps UTC where timestamp is required;
- money as integer/Decimal-safe representation, never binary float;
- currency explicit even while MVP is USD-only;
- opaque public IDs at API boundary;
- consistent success/error envelope;
- machine-readable error code + safe Russian message;
- unknown internal exception maps to generic safe error;
- no database IDs, stack traces or secrets in response.

Candidate envelope:

```json
{
  "data": {},
  "meta": {
    "request_id": "opaque"
  }
}
```

Candidate error:

```json
{
  "error": {
    "code": "tour_time_conflict",
    "message": "Время тура пересекается с существующей записью.",
    "details": {}
  },
  "meta": {
    "request_id": "opaque"
  }
}
```

`details` содержит только безопасную информацию, необходимую для исправления формы.

## 8. Candidate endpoints

Окончательные DTO фиксируются до кодирования.

### Session and current user

```text
POST  /app/v1/session
DELETE /app/v1/session
GET   /app/v1/me
PATCH /app/v1/me
GET   /app/v1/settings
PATCH /app/v1/settings
```

### Calendar

```text
GET /app/v1/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD
GET /app/v1/days/{date}
GET /app/v1/availability?from=...&to=...
```

### Tours and day offs

```text
POST   /app/v1/tours
GET    /app/v1/tours/{tour_id}
PATCH  /app/v1/tours/{tour_id}
DELETE /app/v1/tours/{tour_id}
POST   /app/v1/tours/{tour_id}/copy
PATCH  /app/v1/tours/{tour_id}/days/{date}

POST   /app/v1/day-offs
DELETE /app/v1/day-offs/{entry_id}
```

### Reports

```text
GET /app/v1/reports/summary?from=...&to=...&status=...&payment_status=...
GET /app/v1/reports/workload?from=...&to=...
GET /app/v1/reports/free-dates?from=...&to=...
```

Free-date endpoint should return structured dates/ranges; frontend may format preview using localized shared/contract-tested rules. If exact client text is server-generated, the server remains canonical and localization must be explicit. Choose one approach at MA5 and test it; do not maintain two differing formatters.

## 9. Tour data contract — target fields

Conceptual shape:

```text
Tour
├── public_id
├── group_public_id
├── title
├── company?
├── default_location?
├── start_date
├── end_date
├── start_time?
├── end_time?
├── status: reserved | confirmed
├── payment_status: paid | unpaid
├── daily_income_usd?
├── note?
├── source
├── day_overrides[]
│   ├── date
│   └── location?
├── created_at
└── updated_at
```

The current schema does not yet contain all target fields. Any migration must be additive, idempotent where project conventions require, backed up and tested against legacy tours.

## 10. Time model

Store local calendar time with explicit timezone interpretation `Asia/Tashkent`.

Invariant:

```text
timed tour: start_time != null AND end_time != null
full-day tour: start_time == null AND end_time == null
invalid: only one time is null
```

For MVP, same-day intervals are expected:

```text
00:00 <= start_time < end_time <= 24:00 boundary representation
```

If overnight tours are later required, design them explicitly; do not infer them from end < start.

Overlap for two timed intervals:

```text
new_start < existing_end AND existing_start < new_end
```

Touching boundaries such as `09:00–12:00` and `12:00–15:00` do not overlap.

Full-day entry conflicts with every entry on that date. A day off is full-day. Legacy/bot-created tour without time is full-day.

## 11. Conflict policy transition

Current Guide OS detects date conflicts and allows override after warning. Mini App introduces stricter time semantics:

- duplicate date with non-overlapping times: warn, then allow;
- overlapping time/full-day/day-off: block until corrected.

This must be implemented as one shared service rule. The bot may keep a simpler form, but all writes must remain valid under the common model.

Backward compatibility:

- legacy records receive null times and behave as full-day;
- no automatic invented times;
- existing bot flows remain usable;
- API clearly distinguishes `date_warning` from blocking `time_conflict`.

## 12. Multi-day model

Existing `tour_group_id` remains the group identity.

Common fields update by group:

- title/company;
- date range when supported;
- status/payment;
- daily income;
- time default;
- note.

Per-day location override is stored separately or through an additive representation chosen in data design. Do not split a multi-day tour into unrelated tours merely to support route cities.

Deletion removes the whole group. Single-day deletion inside the group is not in MVP.

## 13. Report calculation contract

For selected date range and filters:

- `tour_count`: matching tour instances/groups according to agreed display semantics; contract must state exact counting for multi-day;
- `working_days`: distinct dates with ≥1 matching tour;
- `free_days`: dates with no tour/reserved/confirmed/day_off;
- `day_off_days`: distinct day-off dates;
- `planned_income`: sum of applicable daily rates per covered tour day;
- `paid_income`: same calculation limited to `paid`;
- `unpaid_income`: planned minus paid for the same filtered scope.

Avoid deriving totals from rendered cards. Calculations live in services and receive boundary tests for partial months and multi-day ranges.

## 14. Availability contract

A date is fully free only when it has no:

- reserved tour;
- confirmed tour;
- timed tour;
- full-day tour;
- day off;
- future official blocking event when such source is approved.

Partial availability is derived from gaps between timed tours for guide-facing UI only. It is not included in client copy.

Free dates are compressed into consecutive ranges after canonical calculation.

## 15. Profile extension

Conceptual model:

```text
GuideProfessionalProfile
├── display_name
├── guide_types[]
│   ├── type: local | route | escort
│   ├── all_uzbekistan: boolean
│   └── geography_codes[]
└── updated_at
```

Rules:

- at least one type when professional profile is completed;
- local: exactly one location, not all Uzbekistan;
- route/escort: one or more locations or all Uzbekistan;
- geography stored as stable code + localized label, not mutable display text alone;
- types can be selected independently;
- geography lists are owner-scoped profile data.

Initial catalog is documented in the Product Operating System and must remain extendable.

## 16. Idempotency and concurrency

Write requests must be protected from repeated submission caused by slow connections, retries or double taps.

Candidate approach:

- client-generated idempotency key per create/copy action;
- server stores/reconciles result for bounded period;
- duplicate key with same request returns same logical result;
- duplicate key with different request fails safely;
- update uses version/updated_at precondition if concurrent edits become material.

Exact persistence is selected in MA5. UI disabling alone is insufficient.

## 17. Ownership and authorization

For every object route:

1. resolve authenticated current user;
2. query object scoped to that user;
3. return generic not-found/forbidden behavior that does not leak existence;
4. mutate only after ownership validation;
5. never accept ownership reassignment from request DTO.

Required negative tests:

- user A reads/updates/deletes user B tour;
- guessed public/internal ID;
- group/day override of another user;
- report filters attempting another user ID;
- replayed session after expiry.

## 18. XSS and free text

Untrusted fields:

- title;
- company;
- location;
- note;
- display name.

Requirements:

- render as text, not HTML;
- backend length/format validation;
- frontend convenience validation does not replace backend;
- no raw HTML preview;
- API and logs redact/limit unsafe values;
- Telegram bot formatting continues to escape text.

## 19. GuideShop integration

MVP core does not depend on GuideShop. Later read-only events may be projected into calendar after existing integration gate.

Rules:

- Mini App calls Guide OS only;
- Guide OS uses existing authenticated GuideShop client;
- source is visible;
- official data read-only;
- personal calendar remains usable on outage;
- outage shows calm unavailable message;
- official data is never replaced with mock/local approximation;
- feature flag default off;
- no direct GuideShop browser credentials.

## 20. Environment isolation

### Local

- mock Telegram adapter;
- deterministic user;
- mock API/GuideShop;
- no production token/DB;
- local HTTPS only when Telegram runtime test requires it.

### Staging

- separate test bot;
- separate bot token;
- separate DB;
- separate keys and URL;
- allowlisted Telegram IDs;
- synthetic data;
- no production GuideShop unless separately approved.

### Production before rollout

- Mini App feature flag false;
- no public bot button;
- no public startapp link;
- routes fail closed when disabled;
- migration deployed only with backup/rollback plan;
- existing bot stays operational.

## 21. Feature flags

Candidate flags, exact names fixed with configuration work:

- Mini App globally enabled;
- Mini App staging allowlist enforced;
- timed tours enabled;
- reports enabled;
- GuideShop calendar projection enabled.

Defaults are off for production-sensitive incomplete features. Incomplete config fails closed, never silently switches to mock.

## 22. Observability

Safe operational signals:

- request count/status/latency;
- auth failures by fixed reason code;
- API error code counts;
- conflict counts;
- idempotency duplicate counts;
- DB busy/retry metrics;
- session expiry counts;
- GuideShop dependency status;
- frontend error release/version.

Never log:

- raw initData;
- bot token;
- session/JWT/cookies;
- PEM/private keys;
- notes, names, companies or complete profile;
- opaque IDs in public diagnostics unless necessary and redacted.

## 23. Rate limits

Apply bounded limits at least to:

- session/bootstrap;
- write endpoints;
- report/free-date generation;
- repeated failed auth;
- expensive range queries.

Limits are per authenticated user and/or safe network dimension. Error response includes retry semantics without disclosing configuration secrets.

## 24. Backup, migration and rollback

Before schema-changing stage:

1. verified backup;
2. restore rehearsal on isolated copy;
3. additive migration;
4. legacy data assertions;
5. targeted tests;
6. staging proof;
7. production feature remains off;
8. rollback/forward-fix decision documented.

Do not delete legacy columns/data merely to normalize the first Mini App version.

## 25. API error taxonomy

Candidate stable codes:

- `auth_required`;
- `auth_invalid`;
- `auth_expired`;
- `access_forbidden`;
- `resource_not_found`;
- `validation_failed`;
- `tour_date_warning`;
- `tour_time_conflict`;
- `day_off_conflict`;
- `stale_update`;
- `duplicate_request`;
- `rate_limited`;
- `dependency_unavailable`;
- `service_unavailable`.

Frontend maps codes to approved Russian messages and recovery action. It does not parse arbitrary backend text to determine behavior.

## 26. Contract tests

Minimum:

- request/response schema examples;
- enum/status compatibility;
- dates/time/money serialization;
- unknown/missing fields policy;
- error envelope;
- user-scoped path;
- idempotency;
- frontend mock fixtures validated against contract;
- backend provider/consumer compatibility.

## 27. Parity tests

```text
Created in bot      -> visible in Mini App
Created in Mini App -> visible in bot
Edited in Mini App  -> bot reflects change
Deleted in bot      -> absent in Mini App
```

Include:

- single/multi-day;
- status/payment;
- income;
- location/day override;
- legacy no-time record;
- timed non-overlap;
- blocking overlap;
- timezone boundaries;
- two users.

The bot may not offer time input, but it must safely display or tolerate the common record.

## 28. Security acceptance gate

Before closed pilot:

- forged initData rejected;
- expired initData rejected;
- signature from other bot rejected;
- missing fields rejected;
- session expiry/reuse behavior verified;
- cross-user CRUD/report access rejected;
- XSS payloads rendered safely;
- rate limits verified;
- secrets/PII absent from logs;
- staging allowlist verified;
- direct URL without auth rejected;
- GuideShop outage does not break core calendar.

## 29. Production activation gate

Production exposure requires separate explicit approval after:

- all MVP and parity tests;
- verified backup/restore;
- migration evidence;
- monitoring and error tracking;
- rollback/kill switch;
- privacy policy;
- pilot completion;
- iPhone/Android/Desktop smoke;
- light/dark smoke;
- security review;
- owner smoke while general audience remains disabled.

No health endpoint alone is sufficient evidence.

## 30. Open technical decisions

Resolve only at their stage:

- frontend package choices;
- session cookie vs short bearer pattern;
- internal HTTP server/runtime composition;
- exact public ID strategy for legacy tours;
- storage for idempotency keys;
- representation of per-day overrides;
- server vs frontend free-date text formatter;
- pagination/caching details.

Each decision needs smallest viable option, tests and compatibility analysis. Do not use open items to expand MVP.
