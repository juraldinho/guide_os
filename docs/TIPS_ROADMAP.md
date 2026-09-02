# Guide OS — дневные чаевые: bot-first roadmap

> Зафиксировано: 2026-09-02  
> Статус: утверждённая будущая функция; реализация не начата  
> Порядок: shared foundation → Telegram bot → Web API → Mini App

## 1. Цель

Гид может открыть любой календарный день и указать общую сумму полученных в этот день чаевых. Чаевые не привязаны к конкретному туру: их можно добавить для свободного дня, выходного, дня с одним или несколькими турами и дня внутри многодневного тура.

Сначала функция появляется в Telegram-боте. После owner validation Web API и Mini App подключаются к тем же данным и общим расчётам.

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

Service валидирует реальную ISO-дату, integer amount без bool/float coercion и диапазон `0…SQLite int max`. Tour services никогда не изменяют `daily_tips`; multi-day не требует специальной логики.

**Готово, когда:** tests покрывают create, replace, zero/delete, range totals, invalid values и isolation.

### TIP3 — Telegram bot UX

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

### TIP4 — bot income и statistics

Добавить:

- `tour_income` — существующий доход от туров;
- `tips` — сумма `daily_tips.amount` по датам периода;
- `total_earnings = tour_income + tips`.

Status/payment filters ограничивают только туры. Дневные чаевые считаются по выбранному периоду независимо от tour filters. Проверить месяц, год, весь период и граничные даты.

**Готово, когда:** bot statistics показывают три проверяемые суммы.

### TIP5 — bot-first owner validation

Проверить чаевые на дне без туров, day off, дне с несколькими турами и внутри multi-day; изменение и удаление; независимость от copy/delete tour; month/year/all-time totals; второй Telegram account и cross-user isolation.

**Готово, когда:** targeted/full backend tests и owner bot smoke PASS. Только после этого начинать Mini App delivery.

### TIP6 — Web API contract

Добавить authenticated day-scoped API, например:

- `GET /app/v1/daily-tips?from=…&to=…`;
- `PUT /app/v1/daily-tips/{date}` с `{ "amount": 20 }`;
- `DELETE /app/v1/daily-tips/{date}` или канонический `amount: 0` flow.

Точные URL утвердить в API contract. Дата и сумма валидируются до DB write; malformed/negative/overflow возвращают `400 validation_error`; user ID берётся только из auth session; mutations идемпотентны. Reports получают отдельные `tips` и `totalEarnings`, не меняя скрыто смысл старого `income`.

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

**Готово, когда:** изменение в Mini App сразу видно в боте и наоборот.

### TIP9 — Mini App calendar и reports

- ненавязчиво показывать наличие чаевых в feed/day detail без изменения статуса занятости;
- добавить «Доход от туров», «Чаевые», «Общий доход»;
- month/year/all-time используют backend results;
- tour filters не скрывают чаевые периода;
- сохранить loading/empty/error states.

**Готово, когда:** бот и Mini App показывают одинаковые totals.

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
TIP0  Contract/audit
TIP1  daily_tips migration
TIP2  Shared queries/services
TIP3  Telegram day-view UX
TIP4  Bot income/statistics
TIP5  Bot-first validation
TIP6  Web API
TIP7  Frontend contract/mocks
TIP8  Mini App day UX
TIP9  Mini App reports
TIP10 Security, E2E and release
```

## 6. In scope первой версии

- одна редактируемая сумма чаевых на пользователя и дату;
- добавление в любой календарный день;
- bot-first, затем API/Mini App parity;
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

Документ не активирует разработку. Начинать с TIP0 только после отдельной команды владельца. Не объединять migration, bot UX, API и frontend в один большой change.

## 9. Смежный активный roadmap

GuideShop Mini App и комиссии personal companies являются отдельным workstream и не смешиваются с дневными чаевыми. GSMA0–GSMA10: `mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`.
