# Guide OS Mini App — GuideShop module roadmap

> Зафиксировано: 2026-09-02  
> Статус: **GSMA0–GSMA8 complete** (optional submodules + resilience/observability 2026-09-03; Mini App sales withdrawn); следующий этап — **GSMA9** security/full regression
> Порядок: navigation → personal companies/commissions → official GuideShop → unified UX → optional official submodules → security/E2E

## 1. Цель

Добавить в Mini App третий основной раздел `GuideShop` после `Календарь` и `Итоги`. Раздел объединяет два независимых источника:

1. официальные компании GuideShop — только чтение;
2. личные компании/места пользователя Guide OS — создание и учёт комиссий.

Существующие Telegram-бот, Mini App и Web API должны работать с общими Guide OS данными. Нельзя создавать отдельную frontend-базу компаний или комиссий.

## 2. Нижняя навигация

Порядок модулей:

```text
Календарь → Итоги → GuideShop → будущие разделы
```

Правила:

- панель закреплена снизу и учитывает Telegram safe area;
- список кнопок горизонтально прокручивается;
- активная кнопка автоматически попадает в видимую область;
- использовать touch-friendly scroll и `scroll-snap`;
- кнопки сохраняют минимальный touch target 44px;
- `Календарь` всегда первый, `Итоги` второй, `GuideShop` третий;
- добавление четвёртого модуля не требует перестройки навигации;
- свайп применяется к панели кнопок, а не ко всему содержимому страницы, чтобы не конфликтовать с iOS back gesture, календарём и вложенными горизонтальными элементами;
- выбор раздела выполняется нажатием; состояние active передаётся не только цветом;
- header для GuideShop: logo/Today behavior по утверждённым правилам, центр `GuideShop`, справа settings.

## 3. Два источника компаний

### 3.1 Официальные компании GuideShop

- источник: существующий request-scoped GuideShop client/runtime;
- данные read-only;
- карточка показывает официальный badge, название, категорию/тип, город/адрес, телефон, описание и status, если доступны по контракту;
- официальный company ID остаётся opaque;
- frontend не получает GuideShop credentials и не обращается к GuideShop напрямую;
- GuideShop outage даёт degraded state, но не блокирует личные компании и core Mini App.

### 3.2 Личные компании пользователя

- источник: существующие `personal_places`;
- каждая запись принадлежит текущему `user_id`;
- пользователь может создать, открыть, изменить и деактивировать запись;
- текущие поля переиспользуются: name, category, general location, landmark, note, status;
- hard delete не добавляется: сохраняется существующая deactivation model;
- в UI допустимо название «Мои компании», но backend entity остаётся `personal_places`, пока audit не докажет необходимость переименования.

### 3.3 Комиссии

- источник: существующие `personal_place_entries` и `ExternalSalesService`;
- запись может содержать дату, сумму покупки, полученную комиссию, баллы, валюту и заметку;
- self-reported комиссия не превращается в official GuideShop points/sale;
- официальный и личный денежные контуры не смешиваются;
- суммы хранятся в minor units и с ISO 4217 currency по существующим правилам;
- будущие дневные чаевые из `docs/TIPS_ROADMAP.md` являются отдельной сущностью и не смешиваются с комиссиями.

## 4. Информационная архитектура экрана

### 4.1 Главная GuideShop

Рекомендуемый первый экран — единая страница с двумя группами:

```text
GuideShop

[Поиск компаний]

Официальные компании
✓ Silk Road Souvenirs
✓ Samarkand Ceramics

Мои компании
Бухара Арт                 135$ комиссии
Restaurant Platan          80$ комиссии

[+ Добавить свою компанию]
```

При росте каталога добавить filters/chips: `Все`, `GuideShop`, `Мои`, город, категория. Источник всегда показывается текстом/badge, не только цветом.

### 4.2 Официальная карточка

- badge `✓ GuideShop`;
- display name;
- тип/категория;
- адрес/город;
- телефон и описание;
- официальный status;
- доступные read-only визиты, продажи, points/history — только если текущий GuideShop contract и права пользователя это разрешают;
- никаких edit/create/delete действий над official data.

### 4.3 Личная карточка

- badge `Моя компания`;
- name/category/location/landmark/note;
- сумма полученных комиссий;
- последние записи;
- действия: `Добавить комиссию`, `История`, `Изменить`, `Деактивировать`.

### 4.4 Добавление комиссии

Переиспользовать существующий external-sale contract:

- дата операции;
- сумма покупки;
- полученная комиссия;
- полученные баллы;
- валюта;
- заметка.

Нужна client-side помощь ввода, но server-side validation остаётся авторитетной.

## 5. Поиск, совпадения и идентичность

- поиск может работать одновременно по official и personal sections, но результаты остаются сгруппированными;
- нельзя объединять записи только по совпадению названия;
- похожее название может дать ненавязчивую подсказку о возможной official company;
- автоматическое linking official↔personal запрещено без надёжного подтверждения;
- personal public ID и GuideShop opaque company ID имеют разные namespaces;
- любые будущие связи должны быть явными, user-confirmed и reversible.

## 6. Архитектура

```text
Mini App GuideShop tab
        ↓ authenticated Guide OS Web API
        ├── request-scoped GuideShop client → official data (read-only)
        └── PersonalPlacesService
              └── ExternalSalesService → personal commissions
```

Инварианты:

- frontend не вызывает SQLite или GuideShop напрямую;
- Web API не содержит SQL/business calculations;
- official data не копируется в `personal_places` автоматически;
- all personal reads/writes user-scoped;
- cross-user lookup fail closed;
- GuideShop disabled/unavailable не ломает personal section;
- не запускать второй независимый SQLite writer;
- feature flags и incomplete config fail closed.

## 7. Этапы реализации

### GSMA0 — product/API audit и contract

- подтвердить текущий `TabId`, shell/header/bottom-nav behavior;
- сопоставить UI с `PersonalPlacesService`, `ExternalSalesService` и GuideShop DTOs;
- решить точный первый экран, pagination/search/filter scope;
- зафиксировать API endpoints/schemas/errors/idempotency;
- определить, какие official visits/sales/points экраны входят в первый Mini App release;
- зафиксировать degraded/empty/loading/offline states;
- подготовить targeted test matrix и file scope для GSMA1.

**Готово, когда:** контракт не создаёт новую business model и нет открытых решений, блокирующих navigation foundation.

**Статус: complete (2026-09-02).** Результат аудита и утверждённый контракт: [`GUIDESHOP_MINIAPP_CONTRACT_GSMA0.md`](GUIDESHOP_MINIAPP_CONTRACT_GSMA0.md).

### GSMA1 — масштабируемая нижняя навигация

- расширить canonical `TabId` значением GuideShop;
- добавить третью кнопку и icon/label;
- сделать horizontally scrollable/snap nav с auto-scroll active item;
- добавить GuideShop shell/page placeholder с корректным header;
- сохранить Calendar/Reports state и scroll behavior при переключении;
- проверить 320–768px, light/dark, safe areas, keyboard/focus;
- не подключать API данных на этом этапе.

**Готово, когда:** три раздела стабильно переключаются, панель готова к будущим модулям, старые UX tests green.

**Статус: complete (2026-09-02).** Добавлены canonical `guideshop` tab, GuideShop placeholder, header title и горизонтально масштабируемая/snap нижняя навигация. Data API не подключался.

### GSMA2 — Personal Places Web API

- зарегистрировать authenticated routes для list/get/create/update/deactivate;
- использовать существующий `PersonalPlacesService`;
- DTO validation соответствует service limits;
- mutation idempotency и standard error envelope;
- exact IDOR/BOLA tests для каждого route;
- никакого hard delete.

**Готово, когда:** Mini App client может безопасно управлять только личными компаниями текущего пользователя.

### GSMA3 — «Мои компании» frontend

- canonical API types, HTTP client и mock parity;
- список, empty state и карточка;
- create/edit/deactivate forms;
- category/location/landmark/note;
- optimistic writes не использовать: UI обновляется server response;
- error/retry/draft preservation;
- search только если он утверждён в GSMA0.

**Готово, когда:** bot ↔ Mini App personal-place parity подтверждён.

### GSMA4 — комиссии и история

- Web API для `personal_place_entries` через `ExternalSalesService`;
- list/get/create/update/deactivate;
- minor units/currency mapping без float;
- форма комиссии и history UI;
- summary per personal company;
- future timestamps, empty outcomes и invalid currencies отклоняются существующими rules;
- tips остаются отдельными.

**Готово, когда:** комиссия, созданная в одном интерфейсе, корректно видна в другом.

### GSMA5 — official GuideShop companies API composition

- зарегистрировать authenticated read-only list/detail routes;
- composition через request-scoped GuideShop provider;
- DTO только утверждённые company fields;
- stable Mini App errors; personal routes независимы.

**Готово, когда:** Mini App client может читать официальный каталог без credentials на frontend.

**Статус: complete (2026-09-03).**

### GSMA6 — объединённый GuideShop экран

- две группы на одной главной странице;
- source badges и раздельные empty/error states;
- общий или раздельный поиск согласно GSMA0;
- official failure не скрывает personal results;
- duplicate-looking names не объединяются автоматически;
- сумма комиссии отображается только для personal company, если official contract не даёт отдельную авторитетную метрику.

**Готово, когда:** пользователь всегда понимает источник и доступные действия.

**Статус: complete (2026-09-03).** GSMA6A client types/HTTP/mock; GSMA6B `OfficialCompaniesSection` + unified page.

### GSMA7 — optional official submodules

После отдельного подтверждения подключить уже существующие read-only GuideShop capabilities:

- visits;
- sales;
- points;
- payout/history.

Не включать автоматически всё только потому, что endpoints существуют. Каждому экрану нужны product need, DTO scope, permissions и tests.

**GSMA7A (docs): complete (2026-09-03).** Audit/contract: [`GUIDESHOP_SUBMODULES_CONTRACT_GSMA7.md`](GUIDESHOP_SUBMODULES_CONTRACT_GSMA7.md). Recommended first slice: **visits**.

**GSMA7B (Visits): complete (2026-09-03).** Owner chose Visits. Mini App Web API list/detail + official company detail entry. Sales / points / history still deferred.

**GSMA7C (Points summary): complete (2026-09-03).** Owner chose Points summary after Visits. `GET /app/v1/guideshop/points/summary` + «Баллы GuideShop» UI (summary-only). Sales / payout history still deferred.

**GSMA7D (Sales): complete (2026-09-03).** Owner chose Sales after Visits + Points summary. `GET /app/v1/guideshop/sales` list/detail + «Продажи GuideShop» UI. Payout history still deferred.

**GSMA7E (Payout/history): complete (2026-09-03).** Owner chose history after Visits + Points + Sales. `GET /app/v1/guideshop/history` list-only + «История выплат» from Points sheet. **GSMA7 optional submodule set complete.**

**Готово, когда:** утверждённые подмодули имеют безопасную навигацию и back behavior.

### GSMA8 — resilience, caching и observability

**Complete (2026-09-03).** Upstream timeouts documented/reused; Mini App GuideShop GET timeout 12s + AbortSignal; one safe GET retry; no mutation auto-retry; no response cache; sanitized `miniapp_guideshop` logs; isolation preserved; runbook [`GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md`](GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md). Sales remain withdrawn from Mini App.

**Готово, когда:** сбой внешнего сервиса локализован в official section.

### GSMA9 — security и full regression

- IDOR/BOLA для personal places/entries;
- forged/foreign opaque IDs;
- input limits, HTML/script text as inert data;
- auth/session tests;
- official read-only guarantee;
- no GuideShop direct frontend requests;
- bot/Mini App parity;
- full backend/frontend suites, build и `git diff --check`.

**Готово, когда:** security tests не принимают HTTP 500 и все user-scoped paths fail closed.

### GSMA10 — two-account E2E и release

- два Telegram accounts с разными personal companies/commissions;
- official catalog visibility согласно GuideShop identity/link/access;
- cross-account isolation;
- GuideShop unavailable smoke;
- iPhone/Android/Desktop navigation and layouts;
- explicit owner production approval;
- staged/reversible rollout без изменения GuideShop write ownership.

**Готово, когда:** owner подтверждает navigation, data parity, isolation и degraded behavior.

## 8. Порядок поставки

```text
GSMA0  Product/API audit and contract
GSMA1  Horizontal scalable bottom navigation
GSMA2  Personal Places Web API
GSMA3  My Companies frontend
GSMA4  Commissions/history
GSMA5  Official GuideShop companies
GSMA6  Unified grouped screen
GSMA7  Optional official submodules
GSMA8  Resilience/observability
GSMA9  Security/full regression
GSMA10 Two-account E2E/release
```

## 9. Первый полезный release slice

Минимальная полезная вертикаль:

1. GSMA0 contract;
2. GSMA1 navigation;
3. GSMA2 personal API;
4. GSMA3 personal companies;
5. GSMA4 commissions;
6. owner validation;
7. затем GSMA5 official catalog.

Так личные компании продолжают работать независимо от готовности/доступности GuideShop.

## 10. Out of scope без отдельного approval

- изменение official GuideShop companies из Guide OS;
- создание official sales/points;
- автоматическое linking official и personal records;
- объединение одинаковых названий;
- перенос personal records в GuideShop;
- marketplace/booking/payment checkout;
- отдельная новая таблица личных компаний вместо существующих `personal_places`;
- full-page horizontal swipe navigation;
- изменение GuideShop source-of-truth ownership.

## 11. Активный следующий шаг

GSMA0–GSMA8 завершены. **Следующий coding этап — GSMA9** (security/full regression). Не начинать без явного запроса владельца. Rollback: [`GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md`](GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md).
