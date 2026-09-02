# Guide OS — Project Context for AI

> Обновлено: 2026-08-16. Навигационный контекст по фактическому репозиторию. При конфликте приоритет имеют текущий код, тесты и `.ai/`.

## 1. Продукт

Guide OS — персональный Telegram-инструмент туристического гида: календарь туров и выходных, проверка занятости, карточки поездок, доход, статистика, профиль и напоминания.

Guide OS также становится пользовательской точкой входа в экосистему GuideShop: гид должен видеть только собственные официальные компании, визиты, продажи, баланс PTS и историю начислений GuideShop. Интеграция не меняет владельцев данных:

- GuideShop — источник истины для официальных Partner, Visits, Sales и PTS;
- Guide OS — источник истины для профиля гида, личного календаря и будущих self-reported external sales;
- прямой доступ между SQLite-базами запрещён;
- интеграция работает через versioned HTTPS API, подписанные service JWT и lifecycle evidence.

## 2. Снимок репозитория

- Репозиторий: `DEVELOPMENT/guide_os`
- Candidate-ветка: `staging-guide-user-lifecycle-api`
- HEAD: `b89562294461b925755255ac48e9a53d65d0b071`
- Последний коммит: `Use attested Python runtime for Railpack builds` от 2026-08-16
- Основной runtime: Aiogram long polling, `python bot.py`
- Staging provider runtime: отдельный API-only entrypoint, без Telegram polling
- Хранилище: SQLite, WAL
- Python: 3.13; зафиксированный runtime — 3.13.14
- Business timezone: `Asia/Tashkent`

На момент проверки runtime/config/tests clean. Изменены только Markdown-файлы `.ai/*`, `docs/project_context.md` и новый `docs/GUIDE_OS_PROJECT_OVERVIEW_EN.md`. Это project state; не откатывать и не перезаписывать без необходимости.

Последнее зафиксированное evidence для candidate: full suite `632 passed`; commit `b895622` прошёл GitHub CI `31942628286` и Integration Contracts `31942628273`. Staging deployment `a79abd94…` успешно установил Python 3.13.14 с включённой GitHub artifact attestation verification.

## 3. Состояние интеграции

Завершено:

- canonical immutable `guide_os_id` как lowercase UUIDv4;
- additive/idempotent backfill legacy users и защита identity от изменения;
- одноразовые linking requests без хранения raw token;
- contract DTO/envelopes/errors и event payloads;
- pinned authoritative integration contract `v1.1.0` с CI validation;
- default-off feature flags и fail-closed runtime composition;
- typed internal routes, user-bound single-use navigation tokens и `/start` deep links;
- безопасный presentation layer и mock-backed Telegram UI;
- identity-bound HTTP client и EdDSA service authentication;
- Guide OS-side link exchange provider, lifecycle evidence и atomic JTI replay protection;
- API-only isolated Railway staging runtime.

Isolated Railway staging активен:

- service deployment основан на exact candidate commit `b895622`;
- отдельный volume `/data` готов;
- HTTPS health endpoint подтверждён;
- production credentials, volume и activation не используются;
- mise attestation bypass удалён; staging build повторно доказан с включённой verification.

GuideShop staging E2E завершён: lifecycle Gate 4A `44/44 PASS`, reads Gate 4B `PASS`, auth/query/cursor `26/26`, FA/IC `0 FAIL`. Production activation, events и notifications пока запрещены; текущая работа ограничена release-candidate safety gates.

## 4. Активные возможности Guide OS

- однодневные и многодневные туры;
- выходные;
- календарь и карточка дня;
- проверка свободной даты и conflict warning;
- редактирование/удаление тура или группы;
- доход и статистика;
- профиль пользователя;
- уведомления о турах;
- admin report, broadcast и backup;
- integration identity/link foundation;
- feature-gated GuideShop presentation/navigation/client/provider layers.

## 5. Runtime и архитектура

### Telegram path

```text
Telegram update
  -> handlers/
  -> services/
  -> database/queries.py
  -> database/db.py
  -> SQLite
```

### GuideShop integration path

```text
Guide OS user / deep link
  -> user-bound route/navigation token
  -> request-scoped GuideShop client
  -> EdDSA service JWT
  -> GuideShop /integration/v1 API

GuideShop linking request
  -> Guide OS API-only HTTPS provider
  -> JWT/JTI validation
  -> link exchange + lifecycle evidence
  -> SQLite
```

Ключевые компоненты:

- `bot.py` — Telegram startup и router wiring;
- `database/db.py` — схема, migrations и concurrency boundaries;
- `database/queries.py` — основной persistence календаря;
- `guide_shop_link_api.py` — API-only provider для link exchange;
- `services/guide_shop_*` — client, contracts, presentation, routes и orchestration;
- `utils/guide_os_identity.py` — canonical identity;
- `.github/workflows/integration-contracts.yml` — immutable contract validation;
- `.ai/` — актуальный project/session/next-task operational state.

## 6. Фактическая SQLite-схема

Основные таблицы:

- `tours` — пользовательские туры и выходные;
- `users` — Telegram user, настройки и immutable `guide_os_id`;
- `events` — продуктовые события.

Интеграционные таблицы:

- `guide_shop_link_requests` — одноразовые запросы связи;
- `guide_shop_link_exchanges` — lifecycle exchange;
- `guide_shop_link_exchange_evidence` — authoritative evidence;
- `guide_shop_link_jti_replay` — replay protection входящих JWT;
- `guide_shop_navigation_tokens` — короткие user-bound single-use routes.

Все пользовательские операции календаря фильтруются по Telegram `user_id`. Все интеграционные чтения и маршруты связываются с текущим `guide_os_id`; cross-user resolution должен fail closed.

## 7. Security-инварианты

- `guide_os_id` стабилен, уникален и неизменяем.
- Raw linking token, private key и JWT не сохраняются и не логируются.
- Service JWT: EdDSA, короткий TTL, строгие audience/scope/identity/kid checks.
- JTI consumption атомарный; replay запрещён.
- Navigation/deep-link tokens user-bound, TTL-aware и single-use.
- Identity lookup выполняется до token consumption.
- Client/service создаются request-scoped и очищаются при success, error и cancellation.
- Feature flags default off; неполная конфигурация fail closed.
- Staging и production keys, URLs, volumes и processes полностью разделены.
- Не выводить в Markdown/chat JWT, PEM, raw token, membership reference или персональные данные.

## 8. Продуктовые границы

- Не переносить GuideShop CRM-операции в Guide OS без утверждённого contract/workstream.
- Официальные данные GuideShop в Guide OS read-only до отдельного approval.
- Будущие личные места и внешние продажи принадлежат только гиду и не формируют глобальный каталог.
- Возможный external-sale points claim — отдельный post-MVP write workstream с anti-fraud, legal и redemption решениями.
- Core Guide OS должен работать при отключённой или недоступной интеграции.
- Русский язык остаётся основным Telegram UX.

## 9. Правила работы AI

Перед изменением:

1. прочитать `.ai/PROJECT.md`, `.ai/SESSION.md`, `.ai/NEXT_TASK.md` и этот файл;
2. проверить `git status` и provenance текущего commit/deployment;
3. определить Telegram, provider или consumer path;
4. проверить identity, token, scope, replay, timeout, retry и cleanup boundaries;
5. не менять GuideShop, contracts, Railway или production из этого репозитория без отдельного scope.

После изменения:

1. запустить focused tests, затем full suite;
2. проверить `git diff --check`;
3. отдельно фиксировать local, CI, staging и production evidence;
4. не объявлять gate PASS без sanitized positive/negative evidence;
5. не коммитить `.env`, DB/WAL/SHM, logs, backups, keys, tokens, caches и archives.

## 10. Источники истины

1. текущий код и тесты;
2. `.ai/SESSION.md` и `.ai/NEXT_TASK.md` для operational state;
3. `database/db.py` для схемы;
4. authoritative pinned contract для integration semantics;
5. CI/staging evidence с exact commit;
6. этот файл как краткая карта проекта;
7. README, roadmap и старые документы только как исторический контекст.

## Future daily tips roadmap

Утверждена, но не реализована модель дневных чаевых: одна сумма на `user_id + calendar_date`, независимо от туров; сначала Telegram-бот, затем общий API и Mini App. Канонический план: `TIPS_ROADMAP.md`.

## Active GuideShop Mini App roadmap

GSMA0 активирован владельцем. Official GuideShop остаётся read-only; personal companies/commissions переиспользуют существующий Guide OS data layer. План: `mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`.
