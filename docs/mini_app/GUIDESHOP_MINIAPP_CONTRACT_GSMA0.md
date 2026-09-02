# GuideShop в Guide OS Mini App — контракт GSMA0

> Дата: 2026-09-02  
> Статус: GSMA0 complete; следующий этап — GSMA1  
> Назначение: зафиксировать продуктовые границы, API и безопасный порядок реализации до изменения application code

## 1. Решение первого релиза

В Mini App появляется третий основной раздел:

```text
Календарь → Итоги → GuideShop → будущие разделы
```

Первый полезный релиз GuideShop состоит из двух независимых групп на одной странице:

1. **Официальные компании GuideShop** — только чтение через Guide OS Web API.
2. **Мои компании** — существующие личные `personal_places` текущего пользователя с учётом комиссий через `personal_place_entries`.

Личные и официальные записи не объединяются автоматически, даже если у них одинаковые названия. Отказ официального GuideShop не должен скрывать или блокировать «Мои компании».

## 2. Результат аудита существующей системы

### 2.1 Frontend shell

- текущий `TabId`: `calendar | reports`;
- `AppShell` напрямую выбирает между `CalendarPage` и `ReportsPage`;
- `BottomNav` содержит две фиксированные кнопки;
- `AppHeader` знает только календарь и итоги;
- API client пока не содержит GuideShop или personal-place методов.

Каноническое расширение GSMA1:

```ts
type TabId = 'calendar' | 'reports' | 'guideshop';
```

Полноэкранный горизонтальный свайп между страницами не вводится. Горизонтально прокручивается только дорожка нижней навигации — это не конфликтует с календарной лентой и iOS back gesture.

### 2.2 Личные компании

Новая таблица не нужна. `PersonalPlacesService` уже обеспечивает:

- create/get/list/update/deactivate;
- строгую привязку к Telegram `user_id`;
- публичные ID вида `place_<32 hex>`;
- поля `name`, `category`, `general_location`, `landmark`, `note`, `status`;
- лимиты: name 100, category 100, location/landmark 200, note 500 символов;
- модель деактивации вместо hard delete.

### 2.3 Комиссии

Новая таблица не нужна. `ExternalSalesService` и `personal_place_entries` уже обеспечивают:

- create/get/list/update/deactivate;
- owner-scoped связь с активной личной компанией;
- дату операции, сумму покупки, денежный доход/комиссию, баллы, валюту и заметку;
- целые minor units без float;
- ISO 4217 currency;
- запрет будущей даты;
- требование хотя бы одного ненулевого результата: покупка, комиссия или баллы.

Денежная комиссия и баллы остаются разными показателями. Суммы разных валют нельзя складывать в одно число: summary группируется по валюте, а баллы показываются отдельно. Дневные чаевые из `docs/TIPS_ROADMAP.md` — отдельная сущность.

### 2.4 Официальные компании GuideShop

Существующий request-scoped `GuideShopClient` предоставляет `list_companies()` с `CompanyDTO`:

- `company_id` — opaque ID;
- `display_name`;
- `status`;
- optional `phone`, `address`, `description`, `type`.

Отдельного `get_company()` в protocol нет. На первом релизе detail разрешено получать через server-side list + exact ID lookup, как уже делает существующий GuideShop UI service. Frontend не получает access token и не обращается в GuideShop напрямую.

Visits, sales, points и payout/history существуют в integration client, но **не входят в первый Mini App release**. Они остаются GSMA7 и требуют отдельного owner approval.

## 3. UX-контракт

### 3.1 Нижняя навигация

- порядок всегда: `Календарь`, `Итоги`, `GuideShop`;
- нижняя панель фиксирована и учитывает safe area;
- внутри панели — горизонтально прокручиваемая дорожка;
- каждая кнопка имеет touch target не менее 44px, `flex: 0 0 auto` и scroll snap;
- выбранная кнопка автоматически возвращается в видимую область;
- active state передаётся визуально и через `aria-current="page"`;
- scrollbar визуально скрыт, но touch/trackpad/keyboard scrolling сохраняется;
- добавление четвёртого раздела не требует изменения layout-модели.

### 3.2 Header и состояние страниц

- Calendar: существующий динамический месяц/год;
- Reports: `Итоги`;
- GuideShop: `GuideShop`;
- справа остаются настройки;
- логотип сохраняет утверждённое действие «вернуться в Календарь на сегодня»;
- переключение разделов не сбрасывает calendar position, открытый отчёт или загруженные данные без необходимости.

### 3.3 Главная GuideShop

Порядок блоков:

1. заголовок/поиск;
2. `Официальные компании`;
3. `Мои компании`;
4. `Добавить свою компанию`.

На первом релизе:

- поиск выполняется по уже загруженным данным отдельно в каждой группе;
- server-side search и сложные filters не требуются;
- источник обозначается текстовым badge, не только цветом;
- две группы имеют независимые loading, empty и error states;
- официальный error не заменяет всю страницу общей ошибкой;
- personal actions никогда не показываются на official cards.

## 4. Guide OS Web API contract

Все endpoints находятся под `/app/v1`, требуют текущую Mini App bearer session и возвращают существующий response/error envelope. Mutation requests используют `Idempotency-Key` по действующему Mini App pattern.

### 4.1 Personal places — GSMA2

| Method | Endpoint | Назначение |
|---|---|---|
| `GET` | `/app/v1/personal-places?includeInactive=false` | список пользователя |
| `POST` | `/app/v1/personal-places` | создать |
| `GET` | `/app/v1/personal-places/{placeId}` | открыть |
| `PUT` | `/app/v1/personal-places/{placeId}` | полная безопасная замена editable fields |
| `POST` | `/app/v1/personal-places/{placeId}/deactivate` | деактивировать |

`PersonalPlace` response:

```json
{
  "id": "place_<opaque>",
  "name": "Название",
  "category": null,
  "generalLocation": null,
  "landmark": null,
  "note": null,
  "status": "active",
  "createdAt": "UTC ISO timestamp",
  "updatedAt": "UTC ISO timestamp"
}
```

Create/replace body содержит только `name`, `category`, `generalLocation`, `landmark`, `note`. `id`, owner, status и timestamps server-owned. `PUT` выбран потому, что существующий service update принимает полный набор editable fields; частичный PATCH не следует имитировать до появления атомарного partial-update service.

### 4.2 Personal commissions — GSMA4

| Method | Endpoint | Назначение |
|---|---|---|
| `GET` | `/app/v1/personal-places/{placeId}/commissions?includeInactive=false` | история компании |
| `POST` | `/app/v1/personal-places/{placeId}/commissions` | добавить запись |
| `GET` | `/app/v1/personal-commissions/{commissionId}` | открыть запись |
| `PUT` | `/app/v1/personal-commissions/{commissionId}` | заменить editable fields |
| `POST` | `/app/v1/personal-commissions/{commissionId}/deactivate` | деактивировать |

`PersonalCommission` response:

```json
{
  "id": "entry_<opaque>",
  "placeId": "place_<opaque>",
  "occurredAt": "UTC ISO timestamp",
  "purchaseAmountMinor": 10000,
  "receivedIncomeMinor": 1000,
  "receivedPoints": 5,
  "currency": "USD",
  "note": null,
  "status": "active",
  "createdAt": "UTC ISO timestamp",
  "updatedAt": "UTC ISO timestamp"
}
```

Summary личной компании строится из этих записей:

```json
{
  "moneyByCurrency": [{"currency": "USD", "amountMinor": 1000}],
  "receivedPoints": 5
}
```

Summary может вычисляться frontend на первом объёме данных или отдельным server endpoint позднее. Нельзя суммировать разные валюты.

### 4.3 Official GuideShop — GSMA5

| Method | Endpoint | Назначение |
|---|---|---|
| `GET` | `/app/v1/guideshop/companies` | официальный read-only список |
| `GET` | `/app/v1/guideshop/companies/{companyId}` | официальный read-only detail |

`OfficialCompany` содержит только поля текущего `CompanyDTO`:

```json
{
  "id": "opaque GuideShop company ID",
  "displayName": "Название",
  "status": "<contract status>",
  "phone": null,
  "address": null,
  "description": null,
  "type": null
}
```

GuideShop pagination metadata/cursor, если он присутствует в upstream response, передаётся как opaque значение без разбора frontend. Никаких official mutations в этом contract нет.

## 5. Errors и degraded behavior

| Ситуация | HTTP / code | UX |
|---|---|---|
| Нет/истёкшая Mini App session | `401 auth_required/auth_invalid` | существующий session recovery |
| Невалидный body/query/ID format | `400 validation_error` | поле/форма сохраняет draft |
| Чужой или отсутствующий personal ID | `404 not_found` | одинаковый fail-closed ответ |
| Duplicate/idempotency conflict | `409 conflict` | безопасный retry без дубля |
| GuideShop выключен | `503 integration_disabled` | official section unavailable; personal работает |
| Нет активной GuideShop связи/прав | `403 access_denied` | объяснение только в official section |
| GuideShop timeout/outage | `503 temporarily_unavailable` | retry official section; personal работает |
| Offline/network error | client offline state | сохранённый draft, повторить |

Точные code names должны быть согласованы с существующим Mini App error mapper при реализации; HTTP 500 не является допустимым validation/ownership результатом.

## 6. Security invariants

- каждый personal service call получает `user_id` только из bearer session;
- `user_id` никогда не принимается из body/query/path;
- foreign и malformed IDs fail closed;
- деактивированная компания не принимает новые комиссии;
- `placeId` комиссии проверяется вместе с владельцем;
- official GuideShop остаётся read-only;
- frontend bundle не содержит GuideShop credentials/tokens;
- opaque IDs и PII не пишутся в user-facing errors или production logs;
- CORS остаётся exact-origin по существующему Mini App middleware;
- HTML/script-like strings возвращаются как inert JSON data;
- mutation routes покрываются idempotency tests.

## 7. Targeted test matrix

### GSMA1

- три canonical tab ID и правильный порядок;
- horizontal overflow/snap contract и active auto-scroll;
- click/keyboard navigation и `aria-current`;
- header title для трёх tabs;
- Calendar/Reports не регрессируют;
- widths 320/390/430/768, safe area, light/dark.

### GSMA2/GSMA4

- happy path list/get/create/update/deactivate;
- exact validation errors и limits;
- idempotency replay и mismatch;
- account A не читает/меняет IDs account B;
- malformed IDs не дают 500;
- inactive filters и inactive-parent commission rejection;
- minor units, currency, future timestamp, empty outcome;
- bot ↔ Mini App parity.

### GSMA5/GSMA6

- no direct frontend GuideShop URL/token;
- official list/detail mapping;
- disabled/access-denied/not-found/timeout mapping;
- official failure не скрывает personal data;
- source badges и отсутствие official edit actions;
- одинаковые названия не объединяются.

## 8. Утверждённый scope GSMA1

GSMA1 меняет только navigation foundation:

1. расширить `TabId`;
2. добавить `GuideShopPage` placeholder без data API;
3. расширить `AppShell` и `AppHeader`;
4. сделать `BottomNav` горизонтально масштабируемым;
5. добавить/обновить frontend tests и styles.

GSMA1 не добавляет backend routes, базы, GuideShop calls, personal forms, commissions или deployment changes. Если реализация требует более пяти application files, перед кодом нужен явный approval владельца согласно `AGENTS.md`.

## 9. Решения GSMA0

- новый storage/domain model не создаётся;
- personal backend entity остаётся `personal_places`;
- UI использует название «Мои компании»;
- official catalog — read-only и независимый;
- первый official scope — companies list/detail;
- visits/sales/points/history отложены до GSMA7;
- поиск первого релиза — client-side по загруженным данным;
- filters/pagination расширяются только при подтверждённой необходимости;
- full-page swipe не используется;
- API сначала добавляется в Guide OS Web API, не во frontend напрямую;
- GSMA1 может начинаться без открытых продуктовых решений.

