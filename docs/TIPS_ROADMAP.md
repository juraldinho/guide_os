# Guide OS — дневные чаевые: Mini App-first

> Owner activation 2026-10-22: shared persistence/services → authenticated Web API → Mini App и отчёты.
> Staging deployed 2026-10-22; owner-authorized production deployed 2026-10-27.
> Telegram bot UX/statistics и manual Telegram E2E остаются отложенными.
> Evidence: [implementation/release handoff](DAILY_TIPS_IMPLEMENTATION.md). Новый порядок заменяет прежние bot-first gates.
> Current environment update 2026-10-29: tips retained by [production reminder-link release](REMINDER_MINIAPP_LINK.md); see [current deployment IDs](CURRENT_STATE.md).

## 1. Цель

Гид может открыть любой календарный день и указать общую сумму полученных в этот день чаевых. Чаевые не привязаны к конкретному туру: их можно добавить для свободного дня, выходного, дня с одним или несколькими турами и дня внутри многодневного тура.

Первым интерфейсом является Mini App. Telegram-бот позднее подключается к тем же данным и сервису; его реализация и validation не блокируют Mini App.

## 2. Утверждённые правила MVP

- чаевые принадлежат комбинации `user_id + calendar_date`;
- на одну дату хранится одна общая сумма чаевых пользователя;
- сумма не связана с tour ID или `tour_group_id`;
- наличие, количество и продолжительность туров не имеют значения;
- чаевые можно добавить на любой валидный календарный день;
- валюта — USD, значение — целое неотрицательное число;
- `0` удаляет чаевые за выбранную дату;
- ввод суммы означает, что чаевые фактически получены; отдельный payment status не добавляется;
- создание, изменение, копирование или удаление тура не меняет дневные чаевые;
- day off не запрещает добавить чаевые;
- отчёты показывают отдельно: «Доход от туров», «Чаевые», «Общий доход»;
- чаевые входят в отчёт по своей календарной дате;
- status/payment filters применяются к турам, но не скрывают чаевые выбранного периода;
- бот и Mini App используют один service/query path;
- все операции строго user-scoped.

## 3. Модель данных

Хранить чаевые отдельно от `tours`, в таблице `daily_tips`:

- `id`;
- `user_id`;
- `tip_date` в ISO `YYYY-MM-DD`;
- `amount` — целое USD, `amount >= 0`;
- `created_at`;
- `updated_at`.

Уникальность: `UNIQUE(user_id, tip_date)`. Положительное значение выполняет upsert, `0` удаляет строку. Отдельная таблица исключает двойной подсчёт multi-day и позволяет хранить чаевые в день без туров.

## 4. Этапы реализации

### TIP0 — product contract и audit

- проверить day view/calendar navigation в боте и Mini App;
- утвердить schema/API names (`daily_tips`, `amount`);
- утвердить максимальную сумму и допустимый диапазон дат;
- обновить API/report contracts;
- отделить сущность от GuideShop income и tour payment status.

**Готово, когда:** дневные чаевые однозначно отделены от туров, оплат и транзакций.

### TIP1 — database migration

- создать additive таблицу `daily_tips`;
- добавить ownership relation и уникальность `user_id + tip_date`;
- сделать migration идемпотентной;
- не изменять существующие tours/users;
- проверить backup/restore новой таблицы.

**Готово, когда:** разные пользователи независимо хранят суммы на одну дату, повторный `init_db()` безопасен.

### TIP2 — queries и shared service

Добавить user-scoped операции:

- получить чаевые за дату и диапазон;
- установить сумму за дату через upsert;
- удалить чаевые за дату;
- получить сумму за период.

Service валидирует реальную ISO-дату, integer amount без bool/float coercion и диапазон `0…1_000_000_000` (USD). Максимум выбран так, чтобы сумма по всем 3 652 059 допустимым календарным датам помещалась в JavaScript safe integer; SQLite хранит INTEGER. Tour services никогда не изменяют `daily_tips`; multi-day не требует специальной логики.

**Готово, когда:** tests покрывают create, replace, zero/delete, range totals, invalid values и isolation.

### TIP3 — Telegram bot UX (отложено)

В просмотре любого календарного дня добавить:

```text
Чаевые за день: 20$
```

и действие `💵 Добавить чаевые` / `💵 Изменить чаевые`.

Поток:

1. пользователь открывает дату;
2. нажимает кнопку чаевых;
3. видит текущую сумму;
4. вводит целое значение USD;
5. `0` удаляет сумму;
6. «Назад»/«Отмена» ничего не меняют;
7. бот возвращает обновлённый день.

Функция не добавляется в wizard тура.

**Готово, когда:** чаевые добавляются на свободный день, выходной и день с любым количеством туров.

### TIP4 — bot income и statistics (отложено)

Добавить:

- `tour_income` — существующий доход от туров;
- `tips` — сумма `daily_tips.amount` по датам периода;
- `total_earnings = tour_income + tips`.

Status/payment filters ограничивают только туры. Дневные чаевые считаются по выбранному периоду независимо от tour filters. Проверить месяц, год, весь период и граничные даты.

**Готово, когда:** bot statistics показывают три проверяемые суммы.

### TIP5 — bot validation (отложено)

Проверить чаевые на дне без туров, day off, дне с несколькими турами и внутри multi-day; изменение и удаление; независимость от copy/delete tour; month/year/all-time totals; второй Telegram account и cross-user isolation.

**Готово, когда:** targeted/full backend tests и owner bot smoke PASS. Это будущая проверка бота; Mini App delivery больше от неё не зависит.

### TIP6 — Web API contract

Добавить authenticated day-scoped API, например:

- `GET /app/v1/daily-tips?from=…&to=…`;
- `PUT /app/v1/daily-tips/{date}` с `{ "amount": 20 }`;
- Удаление — канонический PUT `amount: 0`; отдельного DELETE нет.

Точные URL зафиксированы в API contract. Дата и сумма валидируются до DB write; malformed/negative/overflow возвращают `400 validation_error`; user ID берётся только из auth session; mutations идемпотентны. Reports получают отдельные `tips` и `totalEarnings`, не меняя скрыто смысл старого `income`.

**Готово, когда:** API parity, validation и IDOR tests проходят.

### TIP7 — frontend types, HTTP client и mocks

- добавить canonical daily-tips/report types;
- поддержать range load и day mutation в HTTP client;
- обеспечить mock parity для upsert/delete/reports;
- не переносить production calculations в React;
- предусмотреть безопасный rolling-deploy fallback только при необходимости.

**Готово, когда:** HTTP/mock tests и production build проходят.

### TIP8 — Mini App day UX

В подробном экране любого дня добавить блок «Чаевые» с суммой и действием «Добавить»/«Изменить».

Редактор показывает дату, принимает целое значение USD, предзаполняет текущую сумму, трактует `0` как удаление, блокирует двойной Save и сохраняет draft при ошибке. Он работает независимо от туров/day off и поддерживает light/dark, 320–430 px, keyboard/focus и safe areas.

**Mini App реализован локально:** Добавить → Тур / Выходной / Чаевые; дневная сумма, редактор, replace/delete, retry и сохранение выбранной даты. Bot parity остаётся отложенной.

### TIP9 — Mini App calendar и reports

- ненавязчиво показывать наличие чаевых в feed/day detail без изменения статуса занятости;
- добавить «Доход от туров», «Чаевые», «Общий доход»;
- month/year/all-time используют backend results;
- tour filters не скрывают чаевые периода;
- сохранить loading/empty/error states.

**Mini App реализован локально:** totals приходят из shared backend; bot totals/UX отложены.

### TIP10 — security, E2E и release

- validation и atomic-write tests;
- IDOR/BOLA для get/range/update/delete/reports;
- unique-per-day и concurrency tests;
- независимость от tour copy/delete;
- bot ↔ Mini App two-account E2E;
- migration/backup tests;
- full backend/frontend suites и production build;
- отдельный owner approval на deploy и post-deploy smoke.

Additive таблицу нельзя разрушительно откатывать. Отдельный feature flag добавлять только при подтверждённой необходимости rollout.

## 5. Порядок поставки

```text
TIP0 / TIP1 / TIP2  Contract + shared storage/services (local implementation)
TIP6 / TIP7        Authenticated API + HTTP/mock parity (local implementation)
TIP8 / TIP9        Mini App calendar/editor + reports (local implementation)
TIP10             Automated verification; manual Telegram/device E2E pending
TIP3 / TIP4 / TIP5 Telegram UX/statistics/owner validation (deferred)
```

## 6. In scope первой версии

- одна редактируемая сумма чаевых на пользователя и дату;
- добавление в любой календарный день;
- Mini App-first, затем отложенная bot parity;
- отдельные tips и total earnings;
- USD integer model;
- user isolation и tests.

## 7. Out of scope

- привязка к конкретному туру;
- отдельные чаевые по каждому туру одного дня;
- приём денег через карту/Telegram Payments;
- QR/платёжные ссылки;
- валюты и конвертация;
- распределение между гидами;
- transaction/refund records;
- GuideShop mutations;
- налоги.

## 8. Условие старта

Владелец активировал shared foundation, API и Mini App 2026-10-22. Локальная реализация поставлена этапами. Telegram UX и deployment требуют отдельного scope.

## 9. Смежный активный roadmap

GuideShop Mini App и комиссии personal companies являются отдельным workstream и не смешиваются с дневными чаевыми. GSMA0–GSMA10: `mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`.


## 10. Реализованный контракт (2026-10-22)

- `daily_tips`: unique `(user_id, tip_date)`, FK users, integer CHECK `0…1_000_000_000`, timestamps; additive/idempotent migration.
- Shared service `services/daily_tips_service.py`: strict real ISO dates `0001-01-01…9999-12-31`, integer without bool/float/string coercion, user ownership, atomic replacement/deletion.
- GET `/app/v1/daily-tips/{date}` returns `{date, amount}` (absent → 0).
- GET `/app/v1/daily-tips?from=…&to=…` returns `{tips: [{date, amount}]}`; inclusive valid ordered range, no per-day expansion, only stored rows.
- PUT `/app/v1/daily-tips/{date}` body exactly `{amount: integer}`; zero deletes, repeated same request has the same data effect. PUT uses natural replacement idempotence; no separate idempotency-key inbox.
- Identity comes exclusively from Mini App auth session. Unknown body/query fields are rejected on range/mutation routes.
- Reports keep `income` as tour income and add `tips`, `totalEarnings`. All-time income range is `0001-01-01…9999-12-31`; availability/commission ranges remain separate.
- Tour filters affect tours only; tips use the date period. Tips never affect occupancy, paid/unpaid counts or GuideShop commissions.
- Automated service/API/client/UI tests cover the feature; actual final command results are reported in the implementation handoff. Manual Telegram reload/two-account and device/theme smoke are still pending.


## 11. Automated verification (local, 2026-10-22)

- `.venv/bin/python -m pytest -q tests/test_daily_tips.py` → 21 passed.
- `.venv/bin/python -m pytest -q tests/test_daily_tips.py tests/test_daily_tips_api.py tests/test_reports_service.py` → 35 passed before two additional service regressions; those two then passed in targeted and full runs.
- `.venv/bin/python -m pytest -q` → 1869 passed, 1 skipped (66.04s).
- `cd miniapp && npm test` → 364 passed, 19 files.
- `cd miniapp && npm run build` → TypeScript + Vite successful.
- `git diff --check` → clean.

Local HTTP tests used loopback listeners and isolated temporary databases. No CI,
staging, production or real Telegram/device E2E PASS is claimed. Manual checks:
HTTP-mode reload persistence with two real accounts, iPhone/Android/Telegram Desktop,
light/dark, 320–430 px, safe area and keyboard behavior. See implementation handoff
for the complete file list and owner-run Git commands.
