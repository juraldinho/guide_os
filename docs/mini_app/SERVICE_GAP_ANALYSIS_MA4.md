# Guide OS Mini App — MA4 Service Gap Analysis

> Maps MA3 mock client → API Contract v1 → Python services.
> **MA4 Step 2 closed** (services + migrations). **MA5 closed** (`web_api/` routes).
> Last updated: 2026-08-29

## 1. Summary (post MA5)

| Area | Step 1 gap | After MA4 Step 2 | After MA5 |
|------|------------|------------------|-----------|
| Calendar reads | extend | ✅ `list_entries` / mapper | ✅ GET `/entries` |
| Tour CRUD | extend | ✅ unified entry CRUD | ✅ REST routes |
| Day off | ready | ✅ | ✅ |
| Day locations | missing | ✅ `update_day_locations` | ✅ PATCH day-locations |
| Profile | extend | ✅ read/update partial | ✅ GET/PATCH profile |
| Reports summary | extend | ✅ `reports_service` | ✅ GET `/reports/summary` |
| Availability text | extend | ✅ `availability_service` | ✅ POST `/availability/preview` |
| Time conflicts | extend | ✅ `check_entry_conflicts` | ✅ 409 envelope |
| Auth/session | missing | — | ⏳ dev stub; **MA6** initData |
| Copy tour | missing | ✅ `copy_tour_entry` | ✅ POST `.../copy` |
| Idempotency | missing | — | ✅ `miniapp_idempotency` table |

## 2. Mock client → endpoint → service mapping

| Mock client method | API v1 endpoint | Existing service(s) | Gap |
|--------------------|-----------------|----------------------|-----|
| `listEntries()` | `GET /app/v1/entries?from&to` | `get_tours_in_range` (`queries`), `get_tours_for_month` | **extend** — map rows to `CalendarEntry`; collapse `tour_group_id`; no times/title/source/dayLocations |
| `getEntry(id)` | `GET /app/v1/entries/{id}` | `get_tour` (`tour_service`) | **extend** — integer id vs public id; same field gaps |
| `createTour(form)` | `POST /app/v1/tours` | `save_tour` (`tour_service`) | **extend** — no title, times, `useTime`, separate start/end dates in one call, payment on create, `source`; conflict is date-only |
| `updateTour(id, form)` | `PATCH /app/v1/entries/{id}` | `edit_tour_*` field functions | **extend** — no unified update; no times/title; dates via `edit_tour_dates` only single interval |
| `createDayOff(form)` | `POST /app/v1/day-offs` | `save_day_off` | **ready** — multi-day day off via `parse_date_input` in `save_tour` path; verify range UX |
| `deleteEntry(id)` | `DELETE /app/v1/entries/{id}` | `delete_tour` | **ready** — group delete by `tour_group_id` |
| `updateDayLocations(id, locs)` | `PATCH .../day-locations` | — | **missing** — no service/query |
| `getProfile()` | `GET /app/v1/profile` | `get_user_profile`, `get_user_notification_settings` (`queries`) | **extend** — no `types[]`; telegram id from session |
| `updateProfile(patch)` | `PATCH /app/v1/profile` | `update_user_display_name`, `set_notifications_enabled`, `set_notification_time` | **extend** — partial; no types |
| *(Reports UI)* | `GET /app/v1/reports/summary` | `get_stats_summary`, `get_all_time_stats_summary` (`stats_service`) | **extend** — no arbitrary `from/to`; no year mode; `working_days` not unique; no status/payment filters; field names differ |
| *(Free-dates UI)* | `POST /app/v1/availability/preview` | `get_free_days` (`calendar_service`) | **extend** — returns day integers for one month only; no cross-month text; no timed partial rules |
| *(Copy tour UI)* | `POST /app/v1/entries/{id}/copy` | — | **missing** — compose from `get_tour` + `save_tour` with new dates |

## 3. Service function inventory

### 3.1 `services/tour_service.py`

| Function | Used by bot | Mini App need | Gap |
|----------|-------------|---------------|-----|
| `get_conflicting_dates` | `handlers/add_tour.py` | date overlap only | **extend** → time-aware `check_entry_conflicts` returning `date_warning` vs block |
| `save_tour` | add tour handlers | create | **extend** — times, title, payment, source, explicit end date |
| `save_day_off` | add tour handlers | create day off | **ready** |
| `get_tour` | tour cards/edits | get entry | **extend** — mapper |
| `delete_tour` | tour edits | delete | **ready** |
| `edit_tour_company/city/income/note/status/payment_status/dates` | tour edits | partial update | **extend** — bundle into `update_tour_entry` DTO for API |
| `get_current_month_tours` | calendar handlers | optional | **ready** — bot-specific month window |

### 3.2 `services/stats_service.py`

| Function | Gap |
|----------|-----|
| `get_stats_summary(user, year, month)` | Month only; no filters; `working_days` sums overlap days per tour instead of unique dates |
| `get_all_time_stats_summary` | No `from/to`; same counting issues |

**Needed:** `get_reports_summary(user_id, from, to, filters)` aligned with `miniapp/src/features/reports/lib/summary.ts`.

### 3.3 `services/income_service.py`

| Function | Gap |
|----------|-----|
| `get_income_summary` | Bot income screen only; not MA3 Reports five-metric layout — **do not reuse** for Mini App reports tab |

### 3.4 `services/calendar_service.py`

| Function | Gap |
|----------|-----|
| `build_month_calendar` | Bot month grid + labels — **keep in handlers** |
| `get_free_days` | Month-scoped integers — **extend** for range + fully-free semantics |
| `get_month_tours` | Bot — OK for handlers |

**Needed:** `build_availability_preview(user_id, from, to)` + Russian text formatter (port `availability.ts` rules).

### 3.5 `database/queries.py`

| Area | Gap |
|------|-----|
| `create_tour` | No title, times, source columns |
| Reads | Return `city` not `location`; integer `id` |
| Notifications | `get_user_notification_settings`, setters — **ready** |
| Profile | `get_user_profile`, `update_user_display_name` — **ready** |

## 4. Bot-only formatting (keep in handlers, not API)

Do **not** duplicate in Web API or services:

| Location | Responsibility |
|----------|----------------|
| `handlers/calendar.py`, `handlers/tour_cards.py` | Month grid labels, `MONTH_NAMES_RU`, day cell text (`FREE_LABEL`, company name) |
| `handlers/tour_cards.py`, `services/tour_card_formatter.py` | Telegram tour card prose |
| `handlers/stats.py` | Stats screen wording and keyboard navigation |
| `handlers/income.py` | Income summary Telegram layout |
| `handlers/add_tour.py` | FSM steps, conflict confirm keyboard (`add_tour_conflict_save`) |
| `handlers/profile.py` | `_format_profile_card`, emoji labels |
| `services/calendar_service.build_month_calendar` | `days_map` human labels for bot calendar |
| `keyboards/*` | All Telegram keyboards |

API returns structured `CalendarEntry`, `ReportsSummary`, `AvailabilityPreviewResponse`; Mini App renders UI.

## 5. Schema gaps (migrations — Step 2)

### 5.1 `tours` table additive columns (proposed)

| Column | Type | Notes |
|--------|------|-------|
| `title` | TEXT | Tour display name; legacy: fallback `company` or empty |
| `start_time` | TEXT NULL | `HH:MM` |
| `end_time` | TEXT NULL | `HH:MM`; both null = full-day |
| `source` | TEXT NOT NULL DEFAULT `guide_os_bot` | `guide_os_bot` \| `mini_app` |
| `day_locations_json` | TEXT NULL | JSON object date→location, or normalized child table |

Constraint: `(start_time IS NULL AND end_time IS NULL) OR (start_time IS NOT NULL AND end_time IS NOT NULL)`.

### 5.2 Profile / guide types (later MA9)

| Need | Status |
|------|--------|
| `guide_types` + geography | **missing** — mock only; read-only in API v1 |
| `users.display_name` | exists |
| `users.notifications_enabled`, `notification_time` | exist |

### 5.3 Idempotency store (MA5)

✅ Implemented: `miniapp_idempotency` table in `database/db.py`; used by `web_api/` write routes.

## 6. Conflict rules delta

| Scenario | Bot today (`get_conflicting_dates` + handler) | Mini App (MA3 `conflicts.ts`) | Target service behavior |
|----------|-----------------------------------------------|--------------------------------|-------------------------|
| Same date, any tour | Warning; user can confirm save | If times don't overlap → `date_warning`; else block | **Single `evaluate_conflicts(entry, exclude_id)`** |
| Timed overlap | Treated as date conflict (full-day legacy) | Block with `time_conflict` | Time overlap check when both sides have times |
| Full-day vs timed | Date conflict | Block | Full-day blocks entire date |
| Day off on date | Date conflict | `day_off_conflict` block | Block |
| Legacy bot tour (no times) | Full-day | Full-day | null/null times |
| Save after warning | Handler `add_tour_conflict_save` | Client `ack_date_warning` | API `ack_date_warning: true` on retry |

**Where logic must live:** new module functions in `services/tour_service.py` (or `services/entry_conflict_service.py` if split), called by:

- Web API write routes (future)
- Bot handlers (gradual — Step 2+ may keep date warning UX while calling shared evaluator)
- **Not** in `handlers/add_tour.py` SQL or Mini App production client

## 7. Field mapping: mock ↔ DB ↔ API

| Mock / API | DB today | Notes |
|------------|----------|-------|
| `title` | — | migration |
| `company` | `company` | |
| `location` | `city` | rename at API boundary only |
| `payment` | `payment_status` | |
| `type` | `entry_type` | `tour` / `day_off` |
| `id` (string) | `id` (int) | public id mapper |
| `groupId` | `tour_group_id` | |
| `startTime`/`endTime` | — | migration |
| `dayLocations` | — | migration |
| `source` | — | migration |

## 8. MA4 Step 2 test plan (pytest)

Extend **existing** files where possible; add new files only when needed.

| Test file | Step 2 focus |
|-----------|----------------|
| `tests/test_tour_service.py` | Time overlap boundaries; full-day vs timed; `date_warning` vs block; day off block; group exclude |
| `tests/test_stats_service.py` | `get_reports_summary` unique `workDays`; year/month/all ranges; status/payment filters; multi-day income |
| `tests/test_environment_documentation.py` | Guard if new env vars for Mini App API |
| **New:** `tests/test_entry_conflict_service.py` (if split) | Matrix from §6 |
| **New:** `tests/test_availability_service.py` | Free-date ranges, cross-month headings, empty period |
| **New:** `tests/test_reports_summary_ma.py` | Parity fixtures vs `miniapp/tests/summary.test.ts` cases |
| `tests/conftest.py` | Temp DB already isolated — reuse |

Mini App Vitest (keep in sync):

- `miniapp/tests/summary.test.ts`
- `miniapp/tests/availability.test.ts`

Contract conformance (MA5): API route tests against golden JSON fixtures from `API_CONTRACT_v1.md`.

## 9. Parallel development sequence (post MA5)

1. ~~**Step 2:** migrations + service extensions + pytest~~ ✅
2. ~~**MA5:** `web_api/` routes~~ ✅
3. **MA6:** real initData session auth (replace dev stub).
4. **MA7:** replace `api/mock/store` with HTTP client in Mini App.
5. **MA8–MA10:** reports/availability parity E2E, staging bot, allowlist.

## 10. Risks accepted for Step 2

| Risk | Mitigation |
|------|------------|
| `working_days` bot stats ≠ Mini App | New summary function; do not change bot stats handler until owner approves |
| Multi-day row model (per-day vs group) | Read mapper collapses groups for API; document counting rules |
| `title` vs `company` | Add `title` column; legacy rows use `company` as fallback in mapper |
| SQLite single-writer | Keep bot + API in one runtime per Integration Foundation |

## 11. References

- `docs/mini_app/API_CONTRACT_v1.md`
- `miniapp/src/api/client.ts`
- `services/tour_service.py`, `stats_service.py`, `calendar_service.py`
- `database/db.py` (schema)
- `handlers/add_tour.py` (date conflict UX)
