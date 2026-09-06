# Guide OS — инструкции для AI-агентов

Этот файл — **первичная карта проекта** для Cursor/Codex. Читай его в начале задачи, чтобы не сканировать весь репозиторий и не тратить контекст.

При конфликте приоритет: **текущий код и тесты** > этот файл > `.ai/*` > прочие Markdown-документы.

---

## Цель и приоритет

Guide OS — Telegram-бот для гидов: календарь туров, доход, статистика, профиль, напоминания, личные места/записи и опциональный read-only GuideShop.

**Главная цель:** рабочий MVP.

**Приоритет:** рабочий MVP > простая архитектура > стабильный код > минимальные изменения > быстрый запуск.

**Обязательный порядок работы:** ANALYZE → PLAN → CODE. Не писать код сразу.

---

## Архитектура (не менять без запроса)

```text
handlers/   -> Telegram UX, FSM, callback routing
services/   -> бизнес-логика
database/   -> SQLite schema + SQL queries
utils/      -> форматирование, валидация, helpers
states/     -> FSM states
keyboards/  -> Telegram keyboards
```

- Handlers **не содержат** SQL и сложную бизнес-логику.
- Services **не отправляют** Telegram-сообщения.
- SQL живёт в `database/queries.py` и `database/db.py`.

GuideShop integration path:

```text
Telegram update -> handlers/guide_shop.py
  -> services/guide_shop_runtime.py (request-scoped client)
  -> services/guide_shop_client.py (HTTP / in-memory)
  -> GuideShop /integration/v1 API
```

Отдельный API-only entrypoint для linking provider: `guide_shop_link_api.py`.

---

## PROJECT MAP

### Entry points

| Файл | Назначение |
|------|------------|
| `bot.py` | Основной Telegram runtime (long polling), wiring routers, startup tasks |
| `guide_shop_link_api.py` | API-only GuideShop link provider (без Telegram polling) |
| `guide_operator_integration_api.py` | API-only Guide Operator inbound events + discovery/availability (GO8D1–GO8D2; без Telegram/Mini App) |
| `guide_operator_outbound_worker.py` | CLI-only Guide Operator outbound delivery worker (GO8F2B; без bot/Mini App/GO8D) |

### Handlers / routers (`handlers/`)

| Модуль | Зона ответственности |
|--------|---------------------|
| `start.py` | `/start`, главное меню |
| `add_tour.py` | создание тура / выходного |
| `calendar.py` | календарь, навигация по месяцам |
| `check_date.py` | проверка свободной даты |
| `tour_cards.py`, `tour_edits.py` | карточка тура, редактирование, удаление |
| `income.py` | сводка дохода |
| `stats.py` | статистика (месяц / all-time) |
| `profile.py` | профиль пользователя |
| `notifications.py` | настройки напоминаний |
| `personal_places.py` | личные места и связанные записи |
| `guide_shop.py` | read-only GuideShop UI |
| `admin_report.py` | admin report, `/backup` SQLite |
| `broadcast.py` | admin broadcast |
| `help.py`, `errors.py` | помощь и global error handler |

**Middleware:** отдельного слоя middleware нет. Cross-cutting logic — в `bot.py` startup, `handlers/errors.py`, background tasks (`reminder_service`, `admin_report`).

### Services (`services/`)

Core calendar/tours:

- `tour_service.py` — save/edit/delete tours, conflict detection; operator-managed projections are protected
- `guide_operator_assignment_service.py` — GO6A offer intake, accept/decline, calendar projection, outbox; GO7B1 cancellation apply + projection release; GO7D1 ordinary version apply; GO7D2 ordinary unread acknowledgement; GO7E1 critical version intake (pending only); GO7E2 critical confirm/reject + occupancy projection update; GO7E3 critical decision API/UX surfaces
- `guide_operator_connection_service.py` — GO8C2 connection consent: invite/disconnect intake, guide confirm/decline + decided outbox; offer gate requires confirmed connection
- `guide_operator_service_auth_settings.py` / `guide_operator_service_jwt.py` — GO8B Ed25519/EdDSA service JWT verify (Guide Operator → Guide OS) and sign (Guide OS → Guide Operator); feature-flagged, fail-closed; hashed JTI replay
- `guide_operator_integration_settings.py` + `web_api/guide_operator_integration.py` — GO8D1 authenticated inbound event HTTP (connections/offers/versions/cancellations) + GO8D2 discovery/availability reads; API-only entrypoint `guide_operator_integration_api.py`
- `guide_operator_discovery_service.py` — GO8D2 minimal guide discovery + range availability (`free|busy|partial|unavailable`) from calendar domain
- `guide_operator_outbound_settings.py` / `guide_operator_outbound_delivery.py` — GO8F2A `deliver_one()` claim + frozen envelope + EdDSA-signed POST to GO8F1 routes; feature-flagged, fail-closed
- `guide_operator_outbound_worker.py` — GO8F2B bounded batch worker (`--once` / poll loop); separate process only; default off; uses `deliver_one()` only
- `guide_operator_notification_outbox.py` — GO10A1 durable guide-notification outbox rows written atomically with successful GO intake
- `guide_operator_notification_delivery_settings.py` / `guide_operator_notification_delivery.py` — GO10A2A `deliver_one_notification()` Telegram send for one claimed pending notification; feature-flagged, fail-closed
- `guide_operator_notification_worker.py` — GO10A2B bounded drain task inside `bot.py` only; reuses `deliver_one_notification()`; default off; isolated from update polling
- `date_parser.py` — парсинг дат и multi-day intervals
- `calendar_service.py`, `day_view_service.py`, `day_card_service.py`, `month_day_map.py`
- `tour_card_formatter.py` — текст карточек тура
- `income_service.py`, `stats_service.py`
- `reminder_service.py` — tour reminders
- `personal_places_service.py`, `external_sales_service.py`

GuideShop (`services/guide_shop_*`):

- `client.py`, `contracts.py`, `ui.py`, `navigation.py`, `runtime.py`, `auth.py`, `settings.py`
- linking/events: `link_service.py`, `link_exchange_service.py`, `link_provider.py`, `event_*`

### Database (`database/`)

- `db.py` — schema, migrations, WAL, indexes, backup helper
- `queries.py` — все SQL-операции (tours, users, events, personal places, GuideShop linking/navigation)

Основные таблицы: `tours`, `users`, `events`, `personal_places`, `personal_place_entries`, GuideShop linking/navigation tables.

### FSM (`states/`)

- `add_tour_state.py`, `tour_edit.py`, `check_date_state.py`, `profile_state.py`, `personal_places.py`

### Keyboards (`keyboards/`)

- `main_menu.py`, `calendar.py`, `tour_management.py`, `stats.py`, `guide_shop.py`

### Utils / config

- `config.py` — `BOT_TOKEN`, `TIMEZONE`, `ADMIN_ID`
- `.env.example` — шаблон env (feature flags default off)
- `services/guide_shop_settings.py` — typed GuideShop settings
- `utils/constants.py`, `validators.py`, `formatters.py`, `date_utils.py`, `guide_os_identity.py`

### Reports / export

- **Admin report:** `handlers/admin_report.py` — ежедневный отчёт метрик (`/admin_report`)
- **Backup:** `/backup` — SQLite backup через `database.db.create_sqlite_backup`
- **User stats:** `handlers/stats.py` + `services/stats_service.py`
- **CSV export:** в репозитории **нет** отдельного CSV export; не добавлять без явного scope

### Future Google Calendar roadmap

- Утверждён будущий one-way flow `Google Calendar → Guide OS`: external event → editable draft → полноценный Guide OS tour.
- Реализация **не начата** и не является активной задачей без нового явного запроса владельца.
- Канонический план GC0–GC13: `docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md`.
- Обратная запись в Google и Apple/iCloud integration не входят в утверждённый первый scope.

### Future tips roadmap

- Утверждена будущая bot-first функция дневных чаевых: одна общая сумма на `user_id + calendar_date`, независимо от туров.
- Сначала shared storage/service и Telegram bot UX, после owner validation — Web API и Mini App на тех же данных.
- Реализация **не начата** без нового явного запроса владельца.
- Канонический план TIP0–TIP10: `docs/TIPS_ROADMAP.md`.

### Active Guide Operator assignment roadmap (GO6)

- Owner activated **GO6A**: Guide OS backend foundation for assignment offer intake, guide accept/decline, conflict validation, atomic calendar projection + transactional outbox, and protected operator-managed tours.
- **GO6A complete** (local service/SQL). **GO6B1 complete**: authenticated Mini App API + typed frontend client for pending list, assignment+v1 working package read, accept, and decline (session → immutable `guide_os_id`; no body identity trust).
- **GO6B2 complete**: fourth bottom-nav item `Guide Operator`, pending-offers UI, assignment detail with version 1 working package, Russian accept/decline with confirmation, conflict/error/loading/empty states, and realistic mock data.
- **GO6B3 complete**: accepted Guide Operator projections appear in the normal Mini App calendar with stable assignment/version metadata, read-only labeling, deep-link into assignment detail (focused day), and Back restores calendar context. Direct accepted-detail load works without pending-list membership.
- **GO6B4 complete**: Guide Operator projections count as occupancy/working days but contribute no income and are excluded from paid/unpaid filters/counts; API preserves null fee/payment; calendar UI does not show `$0` or paid/unpaid for them.
- **GO6B5 complete**: guide-facing lifecycle lists (`Ожидают ответа` / `Предстоящие` / `В процессе` / `Завершённые`) derived server-side in Asia/Tashkent; pending endpoint kept; shared detail with accept/decline only for offered.
- **GO7B1 complete**: local idempotent application of `assignment.cancelled.v1` (cancellation inbox, terminal `cancelled` status, protected projection release via allowlist, retained version/decision history, exactly-one `assignment.cancellation.ack.v1` outbox). No guide approval; duplicate-safe; conflicting event IDs fail closed.
- **GO7B2 complete**: fifth lifecycle section `Отменённые` (server-side cancelled-only, newest `cancelled_at` first), retained working-package detail with `Тур отменён оператором` banner, no accept/decline/edit/restore/calendar actions, excluded from other sections and calendar.
- **GO7D1 complete**: local idempotent application of ordinary `assignment.version.published.v1` (version inbox, next monotonic version, independent occupancy rejection, immutable snapshot, unread flag, metadata-only projection update, retained history, exactly-one `assignment.version.applied.ack.v1` outbox). Duplicate-safe; conflicting event IDs fail closed.
- **GO7D2 complete**: ordinary unread UX + guide acknowledgement (`activeVersionUnread` on lists/calendar, structured `Что изменилось` / history, `Ознакомился` bound to session guide + active ordinary version, idempotent evidence + exactly-one `assignment.version.acknowledged.v1` outbox, clears unread without changing occupancy/package).
- **GO7E1 complete**: local idempotent intake of critical `assignment.version.published.v1` without applying (accepted non-cancelled + next monotonic + matching previous active; reject if pending critical exists; validate snapshot/summary; reject no-op; immutable pending snapshot; `pending_critical_version_number`; active version/package/projection/dates/unread unchanged; inbox + exactly-one `assignment.version.received.ack.v1` outbox; cancellation terminal and clears pending without applying).
- **GO7E2 complete**: guide-authored idempotent `confirm_critical` / `reject_critical` for one pending critical version (bind decision event ID + session guide + exact pending version; reject keeps prior active/projection and clears pending; confirm conflicts against proposed occupancy excluding current projection and retains pending on conflict; conflict-free confirm activates version, updates assignment scope + exactly one protected projection via occupancy allowlist, clears pending, sets seen/no ordinary unread ack, exactly-one `assignment.critical_version.decided.v1` outbox; duplicate-safe; cancel race remains terminal).
- **GO7E3 complete**: authenticated Mini App API + typed client/mock for pending critical detail (`pendingCriticalVersion` with snapshot/summary/conflictDates), list/calendar `Требуется подтверждение изменений` indicators, Russian confirm/reject with explicit confirmation, conflict retention UX, refresh of lists/detail/calendar; reuses GO7E2 service (no React-side conflict rules).
- **GO8B complete**: compatible service-auth foundation — verify inbound Guide Operator Ed25519/EdDSA JWTs; sign outbound Guide OS tokens; strict `iss`/`aud`/`sub`/`scope`/`iat`/`nbf`/`exp`/`jti` + allowlisted `kid`; TTL≤60s; skew 10s; separate env keys (never GuideShop); flag default off + fail-closed; hashed JTI SQLite replay + expiry cleanup; test clock/key DI.
- **GO8C2 complete**: local connection-consent domain — idempotent `guide_connection.invited.v1` / `disconnected.v1` intake; guide confirm/decline with exactly-one `guide_connection.decided.v1` outbox; expired invitations non-confirmable; disconnect terminal for new offers while retaining historical assignments; `assignment.offered.v1` requires matching confirmed `guide_connection_id` + company + guide.
- **GO8C3 complete**: authenticated Mini App connection API + Guide Operator tab UX — list connections/invitations (session `guide_os_id` only), `Подтвердить`/`Отклонить` with explicit confirmation, pending invitations above assignment lists, confirmed as `Подключено`, declined/expired/disconnected read-only, refresh after decision; reuses GO8C2 service.
- **GO8D1 complete**: authenticated inbound HTTP event routes (API-only `guide_operator_integration_api.py`) for connection invited/disconnected, assignment offered, version published (ordinary vs critical dispatch), and assignment cancelled; EdDSA JWT + exact inbound scopes; frozen envelope; path/payload ID consistency; stable applied/replayed/error; feature off by default.
- **GO8D2 complete**: authenticated read-only discovery (`guide-operator:connections:write`) and availability (`guide-operator:availability:read`) on the same API-only surface; canonical `guide_os_id` binding; minimum discovery (`canReceiveInvitation`); range status `free|busy|partial|unavailable` from calendar domain; bounded ranges; no Telegram/profile/calendar-entry leakage.
- **GO8F2A complete**: reusable `deliver_one()` for authenticated single-event Guide OS → Guide Operator delivery of the seven decision/ack outbox types to exact GO8F1 routes/scopes; atomic claim; frozen envelope; EdDSA sign; retryable vs permanent failure classification; feature off by default.
- **GO8F2B complete**: bounded outbound delivery worker (separate CLI process); batch size + poll interval; capped exponential backoff with injectable jitter; max attempts; expired-claim recovery; SQLite-safe concurrent claims; in-process cycle lock; SIGINT/SIGTERM after current event; `--once`; safe operational logs only; default off / fail-closed. Never started from bot, Mini App, or GO8D integration API.
- **GO9A complete**: deterministic local two-service HTTP E2E harness (canonical pytest in sibling Guide Operator `tests/test_guide_os_shared_e2e.py`; Guide OS test-only servers in `tests/go9a_guide_os_servers.py` + skip-if-missing wrapper). Real loopback routes, ephemeral Ed25519 keys, isolated DBs, outbox workers, idempotent replay, privacy asserts, one queued-retry/unavailability scenario. Flags remain off outside the harness.
- **GO10A1 complete**: durable guide-notification outbox foundation — one idempotent notification row per successful intake of connection invited/disconnected, assignment offered, ordinary/critical version published, and assignment cancelled; bound to `guide_os_id`; minimal safe rendering fields + deep-link target; pending/delivered/failed columns for later delivery; atomic with intake transaction; no Telegram send in this stage.
- **GO10A2A complete**: reusable `deliver_one_notification()` claims one pending guide notification, resolves Telegram recipient from `guide_os_id`, sends concise Russian text + Mini App WebApp button (approved HTTPS `MINI_APP_PUBLIC_URL`; Guide Operator tab deep-link not invented), classifies retryable vs permanent Telegram failures, keeps failed rows inspectable; feature off by default. No getUpdates, webhook, or second bot instance.
- **GO10A2B complete**: bounded notification-outbox drain as one background task inside the existing `bot.py` process; batch size + poll interval; capped exponential backoff with jitter; max attempts; expired-claim recovery; in-process cycle lock; graceful shutdown with bounded timeout; delivery failures never stop update polling; default off / fail-closed.
- **GO11A complete**: authenticated read-only reconciliation snapshot endpoints on the API-only Guide Operator integration surface (`guide-operator:reconcile`); local connection/assignment/calendar-projection state only; no comparison/repair/UI.
- **STOP before GO11B comparison/repair, operator-facing notifications UI, or deployment**.
- Official GuideShop remains read-only / unchanged. Google Calendar and tips roadmaps remain inactive until explicitly activated.
- Cross-project product contract (non-authoritative vs Guide OS code/tests): Guide Operator `docs/guide_os/GUIDE_OS_ASSIGNMENT_CONTRACT.md`.

### Active GuideShop Mini App roadmap

- Владелец активировал добавление третьего раздела `GuideShop` в Mini App после `Календарь` и `Итоги`.
- Нижняя навигация проектируется как горизонтально прокручиваемая панель будущих модулей; full-page swipe не входит в первый scope.
- Official GuideShop companies остаются read-only; личные компании переиспользуют `personal_places`, комиссии — `personal_place_entries`/`ExternalSalesService`.
- GSMA0–GSMA10 complete for the public production pilot. Mini App GuideShop sales withdrawn. GSMA10 two-account owner E2E PASS on 2026-09-04 (`docs/mini_app/GUIDESHOP_MINIAPP_E2E_GSMA10.md`).
- Public production pilot remains enabled. Formal general release was **not** separately declared. No active GuideShop coding task.
- Future Google Calendar and tips roadmaps remain inactive until explicitly activated by the owner.
- Security matrix: `docs/mini_app/GUIDESHOP_MINIAPP_SECURITY_GSMA9.md`.
- Канонический план GSMA0–GSMA10: `docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`.

### Tests (`tests/`)

- `conftest.py` — isolated temp DB per test (`DATABASE_PATH`)
- domain tests: `test_tour_service.py`, `test_stats_service.py`, `test_personal_*`, `test_guide_shop_*`, etc.
- env/docs guard: `test_environment_documentation.py`
- GO9A wrapper: `tests/test_guide_operator_shared_e2e.py` (skips unless sibling Guide Operator is present)

### Deployment / CI

- `.python-version` — pinned Python **3.13.14**
- `.github/workflows/ci.yml` — full pytest + `git diff --check`
- `.github/workflows/integration-contracts.yml` — pinned integration contracts
- `.github/workflows/shared-event-e2e.yml` — shared event E2E
- Production Railway: `python bot.py`; staging link API: `python guide_shop_link_api.py` (конфигурация вне repo)

### Operational docs (не primary map)

- `.ai/PROJECT.md`, `.ai/SESSION.md`, `.ai/NEXT_TASK.md` — текущее operational state
- `docs/project_context.md` — расширенный контекст (может отставать от HEAD)

---

## BUSINESS RULES

### Tours и calendar

- Поддерживаются **однодневные и многодневные** туры; multi-day создаётся через `date_parser` intervals и общий `tour_group_id`.
- `status`: `reserved` | `confirmed` — оба **блокируют даты**.
- `payment_status`: `paid` | `unpaid`.
- `income` — **daily rate** (ставка за день). В stats: `total_income += daily_income * days_in_month`.
- `entry_type`: `tour` | `day_off`.
- **Day off:** не tour, `income=0`, не считается рабочим днём в stats, но блокирует даты.
- **Cancelled** status не используется — отмена = удаление тура.
- **Conflict detection:** `services/tour_service.get_conflicting_dates()` находит пересечения; при сохранении показывается **warning**, сохранение **не блокируется** (`handlers/add_tour.py`, `handlers/tour_edits.py`).
- Редактирование/удаление multi-day группы идёт через `tour_group_id` (by-group updates/deletes в `tour_service.py`).

### Timezone

- Business timezone: **`Asia/Tashkent`** (`config.TIMEZONE`, `utils/date_utils.today_tz()`).
- Admin report и reminders используют `ZoneInfo(TIMEZONE)`.

### User / data isolation

- Все tour/calendar/personal queries фильтруются по Telegram `user_id`.
- GuideShop reads/resolution — через immutable `guide_os_id`; cross-user lookup must **fail closed**.
- `guide_os_id` — lowercase UUIDv4, **immutable** (`utils/guide_os_identity.py`).

### Telegram message editing

- При `edit_text` ловить `TelegramBadRequest` с `"message is not modified"` и игнорировать (см. `handlers/stats.py::safe_edit_text`).
- Не ломать callback UX повторными edit с тем же содержимым.

### Personal places / records

- Owner-scoped через `user_id`; hard delete запрещён триггерами SQLite (`database/db.py`).
- Validation/conflict errors — через service exceptions, не через silent fallback.

### GuideShop integration

- Official GuideShop data в Guide OS — **read-only** unless explicitly approved.
- Feature flags **default off**; incomplete config **fail closed**.
- Не логировать JWT, PEM, raw tokens, opaque IDs в user-facing output.
- Core Guide OS должен работать при отключённой/недоступной интеграции.

### UX language

- Основной Telegram UX — **русский**. Не менять тексты/labels без явного запроса.

---

## CONTEXT EFFICIENCY RULES

1. Использовать **этот AGENTS.md** как первичную карту; не начинать с full-repo scan.
2. Сначала определить **минимальный scope** задачи (1–3 файла, если возможно).
3. Читать только связанные handlers/services/queries/tests и **непосредственные** зависимости.
4. Расширять scope только если информации недостаточно.
5. **Не делать unrelated refactoring** и не чинить попутно найденные проблемы.
6. **Не менять архитектуру**, не переименовывать/перемещать файлы, не добавлять зависимости без запроса.
7. Переиспользовать существующие helpers/services/patterns; не создавать параллельные реализации.
8. **Не менять >5 файлов** за одну задачу без явного approval.
9. Не менять пользовательский UX/тексты без требования задачи.
10. Не запускать широкие exploratory searches после того, как нужная реализация уже найдена.
11. Не трогать `.ai/*.md`, secrets, production/Railway/GuideShop вне scope задачи.

---

## TESTING STRATEGY

### Принцип

- Во время разработки — **только targeted tests** по изменённой области.
- **Не запускать full pytest после каждого мелкого edit.**
- После завершения задачи: один раз full suite, если изменение значимое или этого требует workflow.
- Для trivial/local-only правок — не гонять дорогие проверки без причины.
- CI всегда: `python -m pytest -q` + `git diff --check`.

### Команды (использовать `.venv` проекта)

Один test:

```sh
.venv/bin/python -m pytest -q tests/test_tour_service.py::test_save_tour_creates_group
```

Один test file:

```sh
.venv/bin/python -m pytest -q tests/test_tour_service.py
```

Связанные tests (несколько файлов):

```sh
.venv/bin/python -m pytest -q tests/test_tour_service.py tests/test_guide_shop_ui.py
```

Focused env/docs guard:

```sh
.venv/bin/python -m pytest -q tests/test_environment_documentation.py
```

Full suite:

```sh
.venv/bin/python -m pytest -q
```

Whitespace check:

```sh
git diff --check
```

`tests/conftest.py` автоматически подменяет `DATABASE_PATH` на temp DB — не полагаться на локальный `guide_os.db` в tests.

---

## DEFAULT WORKFLOW

Для каждой задачи:

1. Прочитать релевантные секции **AGENTS.md** (+ `.ai/NEXT_TASK.md` если задача operational).
2. Определить минимальный scope и затронутые слои (handler/service/query).
3. Найти **существующую реализацию похожего поведения** (grep/read 1–3 файла, не весь repo).
4. Составить короткий план: что менять, риски, файлы (≤5).
5. Сделать **минимальное** изменение.
6. Добавить/обновить tests, если менялась логика.
7. Запустить **targeted tests**.
8. Исправить ошибки.
9. При необходимости один раз — **full pytest** + `git diff --check`.
10. Остановиться; не расширять scope.

Git branch, add, commit and push commands are owner-run Terminal operations by default. Do not spend Cursor/Codex coding time on routine Git actions; provide exact copy-paste commands instead. Never use `git add .`.

Перед кодом (если задача нетривиальная) показать:

- ANALYSIS
- FILES TO CHANGE
- RISKS
- PLAN

---

## FINAL RESPONSE FORMAT

После выполнения задачи достаточно кратко сообщить:

1. **Что изменено** (1–3 предложения)
2. **Изменённые файлы**
3. **Какие tests запущены**
4. **Результат** (pass/fail)
5. **Что проверить вручную** (если нужно)
6. **Известные риски** — только если реально есть

Не писать длинный пересказ исследования, не дублировать diff построчно.

---

## Запрещено (red flags)

- refactor / rewrite working code без запроса
- менять архитектуру, структуру проекта, имена файлов
- добавлять зависимости
- менять >5 файлов
- добавлять функциональность вне текущей задачи
- коммитить `.env`, DB/WAL/SHM, keys, tokens, logs
- объявлять production/staging PASS без sanitized evidence

Остановиться и спросить, если:

- handler > ~150 строк и растёт
- SQL или business logic попадает в handler
- нужен новый dependency или архитектурный сдвиг

---

## MVP scope reminder

**In scope:** calendar, add/edit/delete tour, day off, income, stats, profile, notifications, personal places, feature-gated GuideShop reads.

**Out of scope unless activated by owner:** AI features, marketplace, CRM, roles, shared calendars, multi-language, multi-currency, complex analytics, новые external integrations. Google Calendar зафиксирован как отдельный будущий roadmap в `docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md`, но не активен автоматически.

---

## Security / secrets

- Never output JWT, PEM, bot tokens, raw linking tokens, or PII in chat/logs/markdown.
- Staging и production: отдельные keys, URLs, volumes, processes.
- GuideShop mutations, Railway changes, production data — **только по явному release scope**.
