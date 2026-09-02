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

- `tour_service.py` — save/edit/delete tours, conflict detection
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

### Active GuideShop Mini App roadmap

- Владелец активировал добавление третьего раздела `GuideShop` в Mini App после `Календарь` и `Итоги`.
- Нижняя навигация проектируется как горизонтально прокручиваемая панель будущих модулей; full-page swipe не входит в первый scope.
- Official GuideShop companies остаются read-only; личные компании переиспользуют `personal_places`, комиссии — `personal_place_entries`/`ExternalSalesService`.
- Следующий этап — GSMA0 product/API audit; application code ещё не изменён.
- Канонический план GSMA0–GSMA10: `docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`.

### Tests (`tests/`)

- `conftest.py` — isolated temp DB per test (`DATABASE_PATH`)
- domain tests: `test_tour_service.py`, `test_stats_service.py`, `test_personal_*`, `test_guide_shop_*`, etc.
- env/docs guard: `test_environment_documentation.py`

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
