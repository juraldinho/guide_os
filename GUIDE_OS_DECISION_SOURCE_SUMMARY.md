# Guide OS — Decision Source Summary

Concise summary derived from the **current codebase**, tests, README, folder structure, and existing documentation (`docs/project_context.md`, `.cursor/rules/`). Intended as input for a future `DECISION_LOG.md`.

**Evidence date:** inferred from repository state; no git history was used for this document.

---

## 1. Project purpose

Guide OS is a **Telegram bot MVP for tourist guides** to plan tours, view a personal calendar, track income and payment status, and review workload statistics.

| Aspect | Summary |
|---|---|
| **Problem** | Guides need a simple tool to manage bookings, availability, and earnings without CRM/marketplace complexity |
| **Users** | Individual guides (Telegram private chats); one optional admin (`ADMIN_ID`) |
| **Explicit non-goals** | Marketplace, AI, Google Calendar sync, CRM, user roles, shared calendars, multi-language, multi-currency (`docs/project_context.md`, `.cursor/rules/guide_os_rules.mdc`) |

---

## 2. Current architecture

Flat Python layout with strict layering:

```
bot.py          → entry, router registration, background tasks
config.py       → env vars
handlers/       → Telegram UX only (no SQL / heavy logic)
services/       → business logic
database/       → db.py (connection, init) + queries.py (SQL)
keyboards/      → reply & inline keyboards
states/         → FSM state groups
utils/          → constants, dates, formatters, validators, logging
tests/          → pytest, isolated SQLite per test
```

**Workflow rule (documented):** ANALYZE → PLAN → CODE; working MVP over perfect architecture (`.cursor/rules/guide-os.mdc`).

---

## 3. Main technology decisions

### D-T01: Python + aiogram 3 for the bot

| Field | Detail |
|---|---|
| **Decision** | Telegram bot on **Python** with **aiogram 3.26.0** |
| **Why (inferred)** | Async Telegram API; aiogram 3 is standard for new bots; minimal stack |
| **Evidence** | `requirements.txt`, `bot.py`, all `handlers/*.py` |
| **Consequences** | Long polling only; no web framework in repo |
| **Open questions** | Unknown whether webhook was considered |

---

### D-T02: SQLite as sole database

| Field | Detail |
|---|---|
| **Decision** | **SQLite** via stdlib `sqlite3`; no ORM |
| **Why (inferred)** | MVP simplicity; single-file DB; fits Railway/single-process deploy |
| **Evidence** | `database/db.py`, `database/queries.py`, `docs/project_context.md`, `.gitignore` (`*.db`) |
| **Consequences** | Schema migrations done inline in `init_db()`; scaling limited to one writer |
| **Open questions** | Persistence on Railway depends on volume config (mentioned in `master plan.rtf`, not in repo config) |

---

### D-T03: Raw SQL in `database/queries.py`

| Field | Detail |
|---|---|
| **Decision** | All SQL in `queries.py`; services call query functions |
| **Why (inferred)** | Matches documented architecture; avoids ORM overhead |
| **Evidence** | `.cursor/rules/guide_os_rules.mdc` (handlers must not contain SQL), `database/queries.py` (~890 lines) |
| **Consequences** | Clear boundary; large queries file |
| **Open questions** | Unknown if query splitting by domain is planned |

---

### D-T04: Minimal dependencies

| Field | Detail |
|---|---|
| **Decision** | Core deps: **aiogram**, **python-dotenv**, **pytest**; pinned versions in `requirements.txt` |
| **Why (inferred)** | Cursor rules forbid adding dependencies without approval |
| **Evidence** | `requirements.txt`, `.cursor/rules/guide-os.mdc` ("добавлять зависимости" forbidden) |
| **Consequences** | `pydantic` appears in lockfile but **is not imported anywhere** in app code — likely transitive from aiogram |
| **Open questions** | Whether to document/remove unused transitive deps |

---

### D-T05: Config via `.env` and simple `config.py`

| Field | Detail |
|---|---|
| **Decision** | `python-dotenv` + module-level constants (`BOT_TOKEN`, `TIMEZONE`, `ADMIN_ID`) |
| **Why (inferred)** | Fast setup; no Pydantic Settings layer |
| **Evidence** | `config.py`, `.gitignore` (`.env`) |
| **Consequences** | Fail-fast if `BOT_TOKEN` missing; no typed settings object |
| **Open questions** | Unknown production secret management beyond Railway env vars |

---

## 4. Main product decisions

### D-P01: MVP feature set

| Field | Detail |
|---|---|
| **Decision** | MVP includes: **Calendar**, **Add Tour**, **Income**, **Stats**, **Delete Tour**, **Day Off** |
| **Why (inferred)** | Documented scope in `docs/project_context.md` and cursor rules |
| **Evidence** | `docs/project_context.md`, `.cursor/rules/guide_os_rules.mdc`, `keyboards/main_menu.py` |
| **Consequences** | Additional features exist beyond core menu (notifications, check date, profile, admin tools) |
| **Open questions** | Which extras are officially MVP vs post-MVP |

---

### D-P02: `income` = daily rate × days

| Field | Detail |
|---|---|
| **Decision** | Tour `income` field stores **daily rate**; total = `daily_rate × number_of_days` |
| **Why (inferred)** | Documented business rule; SQL uses `julianday` for day count |
| **Evidence** | `.cursor/rules/guide_os_rules.mdc`, `database/queries.get_total_income`, `services/stats_service.py` |
| **Consequences** | Multi-day tours multiply income; day-offs use `income=0` |
| **Open questions** | UI label "Доход в день" vs user mental model |

---

### D-P03: Tour statuses — `reserved` and `confirmed` only

| Field | Detail |
|---|---|
| **Decision** | Active statuses: **`reserved`**, **`confirmed`**; no `cancelled` in MVP — delete instead |
| **Why (inferred)** | Documented in cursor rules; simplified state machine |
| **Evidence** | `utils/constants.py`, `.cursor/rules/guide_os_rules.mdc`, `init_db()` migrates old Russian labels |
| **Consequences** | Both statuses block dates; reminders include both |
| **Open questions** | Unknown why two blocking statuses vs one |

---

### D-P04: Payment tracking is manual flag only

| Field | Detail |
|---|---|
| **Decision** | `payment_status`: **`paid`** / **`unpaid`**; user toggles in tour edit UI |
| **Why (inferred)** | No payment gateway; guide tracks client payment offline |
| **Evidence** | `utils/constants.py`, `handlers/tour_edits.py`, `keyboards/tour_management.py` |
| **Consequences** | Stats count paid/unpaid tours; not legal/financial proof of payment |
| **Open questions** | Unknown currency assumption (UI shows `$` in `handlers/income.py`) |

---

### D-P05: Overlapping tours — warn, do not block

| Field | Detail |
|---|---|
| **Decision** | Date conflicts detected; user can **confirm and save anyway** |
| **Why (inferred)** | Guides may intentionally double-book; flexibility over strict enforcement |
| **Evidence** | `.cursor/rules/guide_os_rules.mdc`, `services/tour_service.get_conflicting_dates`, `handlers/add_tour.py` (`conflict_confirm` state) |
| **Consequences** | Calendar can show "несколько туров" on same day |
| **Open questions** | Unknown if strict mode was rejected explicitly |

---

### D-P06: Day off as special tour row

| Field | Detail |
|---|---|
| **Decision** | Day off stored as tour with `entry_type=day_off`, fixed label, no income/working-day stats |
| **Why (inferred)** | Reuses same date-blocking model without separate table |
| **Evidence** | `utils/constants.py`, `services/tour_service.save_day_off`, `services/stats_service._filter_work_tours` |
| **Consequences** | Same CRUD/calendar pipeline; excluded from income stats |
| **Open questions** | Unknown |

---

### D-P07: Multi-day / multi-interval tours via `tour_group_id`

| Field | Detail |
|---|---|
| **Decision** | Each date interval → row in `tours`; shared **`tour_group_id`** (UUID) for one logical tour |
| **Why (inferred)** | SQLite rows are single date ranges; group edits/deletes apply to all intervals |
| **Evidence** | `services/tour_service.save_tour`, `database/queries.update_*_by_group`, `handlers/tour_cards.py` |
| **Consequences** | Delete/edit by group; card title built from group rows |
| **Open questions** | Unknown max intervals per save |

---

### D-P08: Flexible human date input

| Field | Detail |
|---|---|
| **Decision** | Custom parser accepts `23/03`, ranges, comma-separated dates, ISO |
| **Why (inferred)** | Mobile UX; guides type quickly in chat |
| **Evidence** | `services/date_parser.py`, `handlers/add_tour.py` (`DATE_INPUT_HINT`), `tests/test_date_parser.py` |
| **Consequences** | Year inferred via `resolve_year()` (current or next year); timezone-aware "today" |
| **Open questions** | Ambiguous dates behavior not fully documented for users |

---

## 5. Database / storage decisions

### D-DB01: Single `tours` table for tours and day-offs

| Field | Detail |
|---|---|
| **Decision** | One table with `entry_type` discriminator |
| **Evidence** | `database/db.py` schema, `ENTRY_TYPE_TOUR` / `ENTRY_TYPE_DAY_OFF` |
| **Consequences** | Queries filter by `entry_type` where needed |
| **Open questions** | Unknown |

---

### D-DB02: Inline schema evolution in `init_db()`

| Field | Detail |
|---|---|
| **Decision** | `CREATE TABLE IF NOT EXISTS` + `PRAGMA table_info` + `ALTER TABLE` for new columns; data migration for Russian status values |
| **Evidence** | `database/db.py` (`entry_type`, `tour_group_id`, notification columns; `Бронь`→`reserved`) |
| **Consequences** | No Alembic; migrations run on every startup |
| **Open questions** | Unknown rollback strategy |

---

### D-DB03: SQLite concurrency hardening

| Field | Detail |
|---|---|
| **Decision** | WAL mode, `busy_timeout`, `run_write_with_retry` (3 attempts) for writes |
| **Evidence** | `database/db.py` |
| **Consequences** | Safer under polling + background tasks; reads don't use retry wrapper |
| **Open questions** | Unknown load testing results |

---

### D-DB04: Per-user data isolation by `user_id`

| Field | Detail |
|---|---|
| **Decision** | All tour queries scoped by Telegram `user_id` |
| **Evidence** | Every function in `database/queries.py` for tours |
| **Consequences** | No shared calendars; simple security model |
| **Open questions** | Unknown |

---

### D-DB05: Analytics `events` table

| Field | Detail |
|---|---|
| **Decision** | Append-only `events(user_id, event_name, created_at)` for product analytics |
| **Evidence** | `database/db.py`, `track_event()` in `queries.py`, `handlers/admin_report.py` |
| **Consequences** | Admin report funnels (start → calendar → add tour) |
| **Open questions** | Unknown retention/cleanup policy |

---

### D-DB06: Lightweight `users` table

| Field | Detail |
|---|---|
| **Decision** | `users` tracks `first_seen`, `last_seen`, notifications, optional `display_name` — not full auth |
| **Evidence** | `database/db.py`, `register_user()`, `handlers/profile.py`, `handlers/notifications.py` |
| **Consequences** | Open bot; no login/password |
| **Open questions** | Unknown |

---

## 6. Bot interaction decisions

### D-B01: Long polling, not webhook

| Field | Detail |
|---|---|
| **Decision** | `dp.start_polling(bot, skip_updates=True)` |
| **Evidence** | `bot.py` |
| **Consequences** | Single long-running process; `skip_updates` drops backlog on restart |
| **Open questions** | Unknown if Railway runs one replica only |

---

### D-B02: Reply keyboard main menu + inline for navigation

| Field | Detail |
|---|---|
| **Decision** | Primary actions via **reply keyboard**; calendar/stats/tour cards via **inline callbacks** |
| **Evidence** | `keyboards/main_menu.py`, `handlers/calendar.py`, `keyboards/tour_management.py` |
| **Consequences** | Callback naming convention: `cal_month:`, `day_card:`, `tour_edit_menu:` |
| **Open questions** | Unknown |

---

### D-B03: FSM for multi-step flows

| Field | Detail |
|---|---|
| **Decision** | Aiogram FSM for add tour, edit tour, check date, profile, notifications, broadcast |
| **Evidence** | `states/*.py`, `handlers/add_tour.py`, etc. |
| **Consequences** | Default in-memory FSM storage (not configured in `bot.py`) — state lost on restart |
| **Open questions** | Unknown if persistent FSM was deferred intentionally |

---

### D-B04: No global auth middleware

| Field | Detail |
|---|---|
| **Decision** | Any Telegram user can use the bot; admin commands gated by `ADMIN_ID` check inline |
| **Evidence** | `handlers/broadcast.py`, `handlers/admin_report.py`; no middleware in `bot.py` |
| **Consequences** | Simple onboarding; admin ID must be kept secret |
| **Open questions** | Unknown |

---

### D-B05: Bot commands menu

| Field | Detail |
|---|---|
| **Decision** | `/start`, `/help`, `/profile` for all users; extra admin commands scoped to `ADMIN_ID` chat |
| **Evidence** | `bot.py` → `setup_bot_commands()` |
| **Consequences** | Discoverability without reading reply keyboard |
| **Open questions** | Unknown |

---

### D-B06: Global error handler with user-friendly message

| Field | Detail |
|---|---|
| **Decision** | `@router.errors()` sends generic Russian message + main menu; logs exception; tracks `error_occurred` |
| **Evidence** | `handlers/errors.py` |
| **Consequences** | Users not exposed to stack traces |
| **Open questions** | Unknown |

---

### D-B07: Background asyncio tasks for admin report and reminders

| Field | Detail |
|---|---|
| **Decision** | `asyncio.create_task()` for daily admin report (midnight TZ) and minute-polling reminders |
| **Evidence** | `bot.py`, `handlers/admin_report.py`, `services/reminder_service.py` |
| **Consequences** | Same process as bot; reminder loop checks user-local `notification_time` |
| **Open questions** | Unknown behavior with multiple bot instances |

---

### D-B08: Russian UI, English code identifiers

| Field | Detail |
|---|---|
| **Decision** | User-facing strings in Russian; DB/code enums in English (`reserved`, `paid`) |
| **Evidence** | Handlers, `utils/constants.py`, migration away from Russian DB statuses |
| **Consequences** | `init_db()` migrates legacy Russian status strings |
| **Open questions** | Unknown target locales |

---

### D-B09: Default timezone `Asia/Tashkent`

| Field | Detail |
|---|---|
| **Decision** | `TIMEZONE` env default for today, reminders, admin report midnight |
| **Evidence** | `config.py`, `utils/date_utils.py`, `services/reminder_service.py` |
| **Consequences** | Date parser year resolution uses TZ-aware today |
| **Open questions** | Unknown per-user timezone support |

---

## 7. AI-related decisions

### D-AI01: No AI in MVP (explicit exclusion)

| Field | Detail |
|---|---|
| **Decision** | **No AI features** in scope |
| **Why (inferred)** | Focus on manual guide workflow; avoid complexity |
| **Evidence** | `docs/project_context.md` ("No … AI"), `.cursor/rules/guide_os_rules.mdc` |
| **Consequences** | No LLM deps, prompts, or AI handlers in codebase |
| **Open questions** | Unknown future AI roadmap (mentioned as excluded in planning RTF only) |

---

## 8. Testing decisions

### D-TEST01: pytest with isolated temp database

| Field | Detail |
|---|---|
| **Decision** | pytest + `conftest.py` autouse fixture: `DATABASE_PATH` → temp file, `init_db()` per test |
| **Evidence** | `tests/conftest.py`, all test files |
| **Consequences** | Tests don't touch production `guide_os.db` |
| **Open questions** | Unknown CI setup (no `.github/workflows` in repo) |

---

### D-TEST02: Service-layer unit tests, not handler integration tests

| Field | Detail |
|---|---|
| **Decision** | Tests cover `tour_service`, `date_parser`, `validators`, `stats_service`, notification queries/migrations |
| **Evidence** | `tests/test_*.py` (5 files) |
| **Consequences** | Handlers/calendar UX largely untested automatically |
| **Open questions** | Unknown coverage targets |

---

### D-TEST03: Migration behavior tested

| Field | Detail |
|---|---|
| **Decision** | Test verifies Russian status values migrated to English on init |
| **Evidence** | `tests/test_notifications_and_migrations.py` → `test_status_migration_converts_old_russian_values` |
| **Consequences** | Regression guard for inline migrations |
| **Open questions** | Unknown |

---

## 9. Deployment / runtime decisions

### D-DEP01: Railway as intended hosting platform

| Field | Detail |
|---|---|
| **Decision** | MVP deployment target: **Railway** |
| **Why (inferred)** | Stated in project docs |
| **Evidence** | `docs/project_context.md`; `master plan.rtf` (not executable config) |
| **Consequences** | **No** `Dockerfile`, `Procfile`, or Railway config in repository — deployment details **Unknown** from code alone |
| **Open questions** | Start command, persistent volume for SQLite, env var list on Railway |

---

### D-DEP02: Entry point `python bot.py`

| Field | Detail |
|---|---|
| **Decision** | Single script `bot.py` starts bot + DB + background tasks |
| **Evidence** | `bot.py`, `if __name__ == "__main__"` |
| **Consequences** | No separate worker process for reminders |
| **Open questions** | Unknown |

---

### D-DEP03: Rotating file logs

| Field | Detail |
|---|---|
| **Decision** | Logs to `logs/app.log` and `logs/error.log` + console |
| **Evidence** | `utils/logger.py`, `.gitignore` (`logs/`) |
| **Consequences** | Local/Railway disk usage; `BUILD_MARKER` in `bot.py` for deploy verification |
| **Open questions** | Unknown log aggregation on Railway |

---

### D-DEP04: Admin DB backup via Telegram

| Field | Detail |
|---|---|
| **Decision** | `/backup` sends SQLite file to admin (copy via `shutil` before send) |
| **Evidence** | `handlers/admin_report.py` |
| **Consequences** | Manual backup path; no automated off-site backup in code |
| **Open questions** | Unknown backup schedule |

---

## 10. Known limitations

| Limitation | Evidence |
|---|---|
| **Income screen not in main menu** | `handlers/income.py` listens for `💰 Оплата` but `keyboards/main_menu.py` has no such button |
| **FSM state lost on restart** | No `MemoryStorage`/Redis configured in `bot.py` |
| **Single SQLite file** | Write contention; multi-instance deploy risky |
| **No automated handler tests** | Tests focus on services/queries |
| **No deployment config in repo** | Railway mentioned in docs only |
| **Open registration** | No rate limiting or abuse controls |
| **Currency not modeled** | Hardcoded `$` in income message |
| **README empty** | `README.md` is only `# guide-os` |
| **Handler size rule may be violated** | Cursor rules say 150 lines max; several handlers exceed (e.g. `add_tour.py`, `tour_edits.py`) — likely accepted for MVP |
| **Cancelled tours** | Documented as "delete instead"; no `cancelled` status in constants |

---

## 11. Important files and what they do

| File | Role |
|---|---|
| `bot.py` | Entry: logging, DB init, bot commands, register routers, start polling, background tasks |
| `config.py` | `BOT_TOKEN`, `TIMEZONE`, `ADMIN_ID` from environment |
| `database/db.py` | SQLite connection, WAL, write retry, schema create/migrate |
| `database/queries.py` | All SQL: tours CRUD, users, events, notifications, stats queries |
| `handlers/start.py` | `/start`, register user, track event, welcome + main menu |
| `handlers/add_tour.py` | Add tour / day-off FSM, conflict confirmation |
| `handlers/calendar.py` | Month picker, calendar view, free days |
| `handlers/tour_cards.py` | Day cards, multi-entry days, create tour from free day |
| `handlers/tour_edits.py` | View/edit/delete tour, status, payment, dates |
| `handlers/stats.py` | Monthly and all-time statistics UI |
| `handlers/check_date.py` | Quick date lookup FSM |
| `handlers/notifications.py` | Enable/disable reminders, set time |
| `handlers/profile.py` | Display name edit |
| `handlers/income.py` | Income summary (orphaned from main menu) |
| `handlers/admin_report.py` | Daily admin metrics, `/backup` |
| `handlers/broadcast.py` | Admin broadcast with confirm FSM |
| `handlers/errors.py` | Global exception handler |
| `handlers/help.py` | `/help` static text |
| `services/tour_service.py` | Tour save/edit/delete, conflicts, grouping |
| `services/date_parser.py` | Natural language date parsing |
| `services/calendar_service.py` | Month calendar data, free days |
| `services/month_day_map.py` | Expand tours across calendar days |
| `services/day_view_service.py` | Day list labels for month tour view |
| `services/day_card_service.py` | Single-day card payload |
| `services/tour_card_formatter.py` | Tour/day card message text |
| `services/stats_service.py` | Income/working days aggregation |
| `services/income_service.py` | Total income + unpaid count |
| `services/reminder_service.py` | Tomorrow tour reminder loop |
| `utils/constants.py` | Statuses, labels, Russian month names |
| `utils/date_utils.py` | Month bounds, shift, TZ today |
| `utils/validators.py` | Input validation for tour fields |
| `utils/formatters.py` | Month calendar text formatting |
| `utils/logger.py` | Rotating file + console logging |
| `keyboards/main_menu.py` | Reply keyboard main menu |
| `keyboards/calendar.py` | Inline month picker |
| `keyboards/stats.py` | Stats month picker |
| `keyboards/tour_management.py` | Tour card/edit/delete inline keyboards |
| `states/*.py` | FSM state definitions |
| `tests/conftest.py` | Test DB isolation |
| `docs/project_context.md` | MVP scope and stack summary |
| `.cursor/rules/guide-os.mdc` | Dev process constraints (RU) |
| `.cursor/rules/guide_os_rules.mdc` | Architecture + business rules (EN) |

---

## 12. Decisions to record in DECISION_LOG.md

Below are **recommended DECISION_LOG entries** with the standard fields. Copy/adapt into formal log entries.

---

### LOG-001: MVP scope boundary

| Field | Content |
|---|---|
| **Decision** | Ship calendar, tours, income, stats, delete, day-off only; explicitly exclude AI, marketplace, CRM, Google Calendar |
| **Why** | Fast launch for guides; avoid platform scope creep |
| **Evidence** | `docs/project_context.md`, `.cursor/rules/guide_os_rules.mdc` |
| **Consequences** | Feature requests outside list require explicit scope change |
| **Open questions** | Are notifications/profile/check-date official MVP extensions? |

---

### LOG-002: Layered architecture (handlers / services / database)

| Field | Content |
|---|---|
| **Decision** | Enforce UX vs business logic vs SQL separation |
| **Why** | Maintainability under "max 5 files per change" rule |
| **Evidence** | `.cursor/rules/guide-os.mdc`, `.cursor/rules/guide_os_rules.mdc`, project layout |
| **Consequences** | Handlers should stay thin; logic belongs in services |
| **Open questions** | Enforcement is convention-only (no linter) |

---

### LOG-003: SQLite + inline migrations

| Field | Content |
|---|---|
| **Decision** | Single SQLite file; schema changes in `init_db()` without migration tool |
| **Why** | MVP speed; zero migration infrastructure |
| **Evidence** | `database/db.py`, tests for status migration |
| **Consequences** | Production DB evolves on deploy; backup critical |
| **Open questions** | Railway persistent volume configuration |

---

### LOG-004: Tour grouping with `tour_group_id`

| Field | Content |
|---|---|
| **Decision** | Multi-interval tours stored as multiple rows linked by UUID group |
| **Why** | Model arbitrary date ranges and comma-separated input |
| **Evidence** | `services/tour_service.save_tour`, group update/delete queries |
| **Consequences** | Edit/delete operates on whole group; calendar shows multiple rows per day |
| **Open questions** | Partial group edit UX edge cases |

---

### LOG-005: Conflict warning without hard block

| Field | Content |
|---|---|
| **Decision** | Overlapping tours allowed after user confirmation |
| **Why** | Real guides may overlap bookings intentionally |
| **Evidence** | `.cursor/rules/guide_os_rules.mdc`, `AddTourState.conflict_confirm` |
| **Consequences** | "несколько туров" days; stats still count all tours |
| **Open questions** | Unknown user research backing |

---

### LOG-006: Income semantics (daily rate)

| Field | Content |
|---|---|
| **Decision** | `tours.income` = daily rate; totals multiply by days in range |
| **Why** | Matches guide pricing mental model per cursor rules |
| **Evidence** | `.cursor/rules/guide_os_rules.mdc`, `get_total_income` SQL |
| **Consequences** | Stats/income must use same formula everywhere |
| **Open questions** | Document in user-facing `/help`? |

---

### LOG-007: Manual payment status only

| Field | Content |
|---|---|
| **Decision** | `paid`/`unpaid` flag; no payment processor |
| **Why** | MVP tracks guide bookkeeping only |
| **Evidence** | `payment_status` column, `handlers/tour_edits.py` |
| **Consequences** | Not suitable as financial system of record |
| **Open questions** | Currency and tax handling |

---

### LOG-008: Open bot + single admin

| Field | Content |
|---|---|
| **Decision** | No user authentication; `ADMIN_ID` for admin commands only |
| **Why** | Minimal friction for guide onboarding |
| **Evidence** | `config.py`, admin handlers, no auth middleware |
| **Consequences** | Data scoped by Telegram ID only; trust Telegram account security |
| **Open questions** | Account recovery if user changes Telegram account |

---

### LOG-009: Event analytics for admin funnel

| Field | Content |
|---|---|
| **Decision** | Track named events in DB for daily admin report |
| **Why** | Product metrics without external analytics SDK |
| **Evidence** | `events` table, `track_event`, `handlers/admin_report.py` |
| **Consequences** | Privacy: stores user_id + action names |
| **Open questions** | GDPR/consent, retention period |

---

### LOG-010: Long polling + in-process schedulers

| Field | Content |
|---|---|
| **Decision** | Polling bot with embedded reminder and admin-report loops |
| **Why** | Single deployable unit on Railway |
| **Evidence** | `bot.py`, `reminder_service.py`, `admin_report.py` |
| **Consequences** | Not horizontally scalable without duplicate reminders |
| **Open questions** | Single replica assumption on Railway |

---

### LOG-011: Default timezone Asia/Tashkent

| Field | Content |
|---|---|
| **Decision** | All "today" and midnight scheduling use configurable TZ defaulting to Tashkent |
| **Why** | Inferred primary user geography |
| **Evidence** | `config.py`, `date_utils.py`, reminder/admin report |
| **Consequences** | Users outside TZ may see off-by-one date edge cases |
| **Open questions** | Per-user timezone needed? |

---

### LOG-012: Explicit no-AI policy

| Field | Content |
|---|---|
| **Decision** | No AI/LLM in MVP codebase |
| **Why** | Scope control per project context |
| **Evidence** | `docs/project_context.md`, cursor rules |
| **Consequences** | Future AI requires new decision log entry + dependency approval |
| **Open questions** | None from code |

---

### LOG-013: Development governance (5-file / no-refactor rule)

| Field | Content |
|---|---|
| **Decision** | Changes limited to ≤5 files; no refactor/rename without request; ANALYZE→PLAN→CODE |
| **Why** | Protect working MVP during rapid iteration |
| **Evidence** | `.cursor/rules/guide-os.mdc` |
| **Consequences** | Technical debt may accumulate (large handlers, monolithic queries.py) |
| **Open questions** | When to relax rule post-MVP |

---

### LOG-014: Income handler vs main menu mismatch

| Field | Content |
|---|---|
| **Decision** | **Unknown** — income feature implemented but not exposed in main menu |
| **Why** | **Unknown** — possibly incomplete UI wiring or intentional deferral |
| **Evidence** | `handlers/income.py` vs `keyboards/main_menu.py`; income listed in MVP docs |
| **Consequences** | Feature unreachable via normal UX unless user types button text manually |
| **Open questions** | Bug or intentional? Should menu include `💰 Оплата`? |

---

## Appendix: Documentation sources used

| Source | Reliability for decisions |
|---|---|
| Python source + tests | **High** — primary evidence |
| `docs/project_context.md` | **High** — explicit MVP/stack |
| `.cursor/rules/*.mdc` | **High** — architecture and business rules |
| `README.md` | **Low** — placeholder only |
| `master plan.rtf`, `backlog.rtf` | **Medium** — planning intent; not enforced in code |
| Git history | **Not used** |

---

*Generated for Decision Log intake. Do not treat inferred "why" as confirmed team history unless validated by maintainers.*
