# Guide OS Integration Foundation

**Статус:** Stage 0 closed; Stage 1 authorized; production activation gated  
**Назначение:** единый документ подготовки Phase 3 — Guide OS Integration MVP  
**Правило запуска:** разработку на mock/staging можно начинать до закрытия Stage 0; подключение production запрещено до подтверждения Phase 2 и production-safety.
**Владелец и утверждающий:** Отабек Джураев  
**Дата утверждения:** 2026-08-07  
**Область утверждения:** архитектура, data ownership, минимальный состав данных, linking, API/events, Telegram UX, план тестирования и начало implementation preparation.

---

## 1. Цель MVP

Guide OS показывает авторизованному гиду его данные из GuideShop:

- компании;
- Visits;
- Sales в USD;
- начисленные, ожидающие и зачисленные баллы;
- историю операций.

Guide получает Telegram-уведомления о создании Visit, добавлении Sale, пересчёте и зачислении баллов. Каждое уведомление открывает соответствующий сценарий в Telegram-интерфейсе Guide OS.

Интеграция read-only со стороны гида: Guide OS не изменяет Visits, Sales и points в GuideShop.

## 2. Неподвижные архитектурные решения

| Сущность / процесс | Система записи | Комментарий |
|---|---|---|
| Guide identity | Guide OS | Выдаёт стабильный `guide_os_id`; Telegram user ID остаётся каналом аутентификации |
| Company | GuideShop | Guide OS получает только данные, необходимые для отображения |
| Visit | GuideShop | Изменения выполняются только в GuideShop |
| Sale | GuideShop | Денежные значения передаются без вычислений в Guide OS |
| Points transaction | GuideShop | GuideShop рассчитывает сумму и управляет статусом |
| Guide linking | Совместный процесс | Guide OS подтверждает личность; GuideShop хранит внешнюю связь и аудит |
| Notifications | Guide OS | Создаются из событий GuideShop, доставка идемпотентна |

Фраза «GuideShop остаётся системой записи» относится к Company, Visit, Sale и points, но не к профилю Guide.

## 3. Что уже подтверждено в GuideShop

- В локальной таблице `guides` предусмотрен `guide_os_id`.
- Поддерживаются локальный Guide OS ID и временный гид без live API sync.
- Visits связаны с гидами.
- Sales имеют сумму, валюту, категорию, способ оплаты и timestamps.
- Комиссии/points рассчитываются в GuideShop и имеют состояния ожидания и выплаты.
- GuideShop использует Telegram, Python, aiogram и SQLite.

Это база для интеграции, но существующее поле `guide_os_id` само по себе не обеспечивает безопасное linking, уникальность, аудит или синхронизацию.

## 4. Stage 0 — readiness checklist

**Текущий вывод:** Stage 0 закрыт решением Product Owner Отабека Джураева 2026-08-07, переход к Stage 1 разрешён. Архитектурная, repository-level и организационная части утверждены. Локальный Guide OS development staging candidate на текущем Mac подтверждён. GuideShop development staging candidate и Phase 2 integration baseline dataset подтверждены отдельно на Mac Neo в разделах 4.3–4.4. Shared staging, end-to-end, recovery и live production-safety evidence остаются обязательными условиями production activation, но не блокируют Stage 1.

| Проверка | Текущий статус | Условие закрытия |
|---|---|---|
| Phase 2 завершена | Подтверждено на уровне репозитория | Реализация Phase 2.1–2.8 присутствует; 1191 тест прошёл 2026-08-07; product approval: Отабек Джураев |
| Production-safety пройдена | Частично подтверждено | Repository-level controls и тесты подтверждены; live Railway/DR/smoke evidence остаётся production gate |
| Владельцы сущностей назначены | Подтверждено | Отабек Джураев назначен владельцем всех направлений до делегирования |
| Источники истины | Утверждены | Утверждены Отабеком Джураевым 2026-08-07 |
| Минимальный набор данных | Утверждён с ограничением | Утверждён; `payment_method` по умолчанию не передаётся до отдельного включения |
| Staging Guide OS | Local development staging candidate и отдельный local bot подтверждены | Репозиторий на текущем Mac доступен по `/Users/otabekdjuraev/guide_os`; Python 3.13.1, зависимости и импорт приложения проверены; `32 passed`; локальный `.env` указывает на `@Guideosbot`, identity подтверждён через `getMe`; отдельный shared staging deployment ещё требуется |
| Staging GuideShop | Development staging candidate подтверждён | Тестовый бот и локальная development DB доступны; отдельный Railway staging ещё не привязан/не проверен |
| Тестовые данные | Phase 2 baseline загружен и проверен | Dataset v1.0.0 загружен локально; linking/outbox extension добавляется после соответствующих миграций |
| API/event contract | Утверждён как implementation baseline | Формальные OpenAPI/JSON Schema и контрактные тесты должны проходить в CI |
| Recovery/reconciliation | Спроектировано | Runbook проверен на staging |

### Ответственные

| Направление | Ответственный | Статус |
|---|---|---|
| Product acceptance | Отабек Джураев | Назначен 2026-08-07 |
| Guide identity | Отабек Джураев | Назначен 2026-08-07 |
| GuideShop API | Отабек Джураев | Назначен 2026-08-07 |
| Events/outbox | Отабек Джураев | Назначен 2026-08-07 |
| Guide OS Telegram UX | Отабек Джураев | Назначен 2026-08-07 |
| Security/privacy | Отабек Джураев | Назначен 2026-08-07; техническая проверка обязательна перед production |
| Monitoring | Отабек Джураев | Назначен 2026-08-07 |
| Reconciliation/recovery | Отабек Джураев | Назначен 2026-08-07 |

### 4.1 Evidence, проверенное 2026-08-07

| Область | Подтверждение | Результат |
|---|---|---|
| Phase 2 implementation | Тесты и модули Phase 2.1–2.8 в GuideShop | Подтверждено на уровне репозитория |
| Regression suite | `.venv/bin/pytest -q` | `1191 passed in 16.58s` |
| Tenant isolation | `SAAS_ISOLATION_AUDIT.md`, company-aware services и security tests | Реализована базовая company isolation; Phase 3 требует отдельной cross-guide проверки API |
| Startup safety | `app/core/startup_checks.py` и тесты | Проверки директорий/конфигурации присутствуют |
| Deployment foundation | `railway.json`, production configuration и Railway runbook в `README.md` | Конфигурация существует; живое окружение не проверялось |
| Backup foundation | Full DB и company-scoped backup services/tests | Код и тесты подтверждены; фактический off-box backup/restore drill не подтверждён |
| Audit | Audit log для критических CRM-операций | Реализован; linking/outbox audit добавляется в Phase 3 |
| Guide OS repository/staging | Проверено на текущем Mac в `/Users/otabekdjuraev/guide_os`: Python 3.13.1, зависимости исправны, импорт приложения успешен, `32 passed`; локальный bot identity `@Guideosbot` подтверждён через Telegram `getMe` | Local development staging candidate подтверждён; GitHub/Railway bot `@Guide_os_bot` зафиксирован со слов владельца и требует deployment evidence |

### 4.1.1 Границы окружений evidence

- Guide OS в текущем рабочем окружении находится на этом Mac по пути `/Users/otabekdjuraev/guide_os`.
- Evidence Guide OS (`32 passed`, Python 3.13.1 и проверка импорта) относится к текущему Mac.
- Локальный `.env` текущего Mac содержит token отдельного бота `@Guideosbot`; 2026-08-07 его identity подтверждён через Telegram `getMe` без вывода token и без запуска polling.
- `@Guide_os_bot` является ботом Guide OS, который, по подтверждению владельца, запускается через GitHub deployment в Railway. Его Railway runtime и commit в текущем окружении ещё не проверены.
- GuideShop разрабатывается и проверяется на другом Mac — Mac Neo. Пути репозиториев на Mac Neo отличаются от пути текущего workspace и не должны использоваться как доказательство отсутствия Guide OS на этом Mac.
- Evidence GuideShop, включая `1191 passed`, development database, Telegram test bot и integration dataset, относится к проверке на Mac Neo.
- Наличие локальных development staging candidates на двух разных Mac не заменяет shared staging deployment и end-to-end проверку связи между системами.

### 4.2 Решение о начале работ

Отабек Джураев официально утверждает решения этого документа и разрешает начать Track A и подготовительные работы Track B. Это утверждение не заменяет live production-safety evidence. До появления staging разрешены mock API, схемы, миграции, feature flags и автоматические тесты. Production activation остаётся запрещённой до выполнения production gate из раздела 14.1.

### 4.3 Актуальный GuideShop development staging candidate

Проверено 2026-08-07:

| Параметр | Актуальное значение / статус |
|---|---|
| Repository | `git@github.com:juraldinho/guideshop.git` |
| Рабочая ветка | `develop` |
| Commit | `f3c25c762bf70a8794f8cf44274cf45acfa4298b` |
| Commit date | `2026-08-07T13:23:46+05:00` |
| Telegram test bot | `@Guide_storebot` (`Guidestore`) |
| Telegram bot ID | `8845113446` |
| Bot identity check | Успешно через Telegram `getMe` 2026-08-07; token не сохраняется в документе |
| Environment mode | `development` |
| Runtime | Telegram long polling, `python -m app.bot.main` |
| Local database | SQLite DB присутствует |
| Current database totals | 3 companies, 4 guides, 14 visits, 12 sales, 10 commissions после загрузки synthetic dataset; содержимое/PII не фиксируется |
| Regression tests | `1191 passed in 16.58s` |
| Railway config | `railway.json` присутствует; start command подтверждён |
| Railway staging link | Отсутствует в текущем checkout (`No linked project found`) |
| Staging classification | Пригоден для локальной GuideShop-проверки и mock/contract development; не считается подтверждённым shared Railway staging |

Секреты (`BOT_TOKEN`, database credentials и другие environment values) намеренно не включены. Запуск второго poller для этого bot token запрещён: перед локальным запуском необходимо убедиться, что бот не запущен в другом процессе/окружении.

### 4.4 Загруженный integration test dataset

Проверено 2026-08-07:

| Параметр | Результат |
|---|---|
| Dataset | `guide-os-integration-staging-v1` |
| Version | `1.0.0` |
| Classification | Synthetic-only, Phase 2 baseline |
| Fixture | `tests/fixtures/guide_os_integration_staging_v1.json` |
| Loader/validator | `scripts/seed_integration_staging.py` |
| Target | Локальная development SQLite DB из раздела 4.3 |
| Companies | 2 |
| Guides | 3: Guide A, Guide B и временный гид без Guide OS ID |
| Company guides | 2 |
| Sale categories | 2 |
| Visits | 4: active, completed, cancelled и отдельный Company/Guide B isolation case |
| Sales | 4: cash, card, transfer и unknown payment method |
| Points/commissions | 3: pending, paid/credited mapping и reversed scenario |
| Payouts | 1 |
| Legacy events | 4, включая повторный logical sale event для deduplication test preparation |
| Audit records | 1 dataset load marker |
| Initial load | 26 synthetic records inserted; `Validation: PASSED` |
| Idempotency check | Повторный запуск: 0 inserted во всех таблицах; `Validation: PASSED` |
| Automated tests | 7 dataset safety/validation tests; входят в `1191 passed` |
| Owner | Отабек Джураев |

Команды воспроизведения:

```bash
.venv/bin/python -m scripts.seed_integration_staging --confirm-staging
.venv/bin/python -m scripts.seed_integration_staging --confirm-staging --validate-only
```

Safety guarantees:

- loader разрешён только при `APP_ENV=development` или `APP_ENV=staging`;
- `APP_ENV=production` всегда блокируется;
- требуется явный `--confirm-staging`;
- существующие записи не удаляются и не обновляются;
- совпадающий ID с отличающимися данными вызывает отказ и rollback;
- повторная загрузка идемпотентна;
- fixture не содержит реальных телефонов, Telegram IDs, credentials или production PII.

До реализации Phase 3 остаются расширения dataset: состояния `guide_os_links` (`pending`, `active`, `revoked`, `conflict`), transactional outbox со стабильным `event_id`, inbox/out-of-order metadata и полноценная история void/correction. Loader явно сообщает эти четыре пункта как pending и будет расширен вместе с соответствующими миграциями.

### 4.5 Проверенный Guide OS local staging candidate

Проверено на текущем Mac 2026-08-07 в `/Users/otabekdjuraev/guide_os`:

| Проверка | Результат |
|---|---|
| Repository | Доступен локально, ветка `main` |
| Runtime | Python 3.13.1 |
| Project environment | `venv` присутствует и работоспособен |
| Dependencies | `pip check`: broken requirements отсутствуют |
| `python-dotenv` | Версия 1.2.2 доступна в `venv` и системном Python |
| Application import | Успешно с безопасным placeholder token без запуска polling |
| Regression tests через `venv` | `32 passed in 1.17s` |
| Regression tests через системный Python | `32 passed in 0.95s` после установки `python-dotenv` |
| Secret file | `.env` присутствует; содержимое и значения не читались и не фиксировались |
| Deployment files | `railway.json`, `Procfile` и `Dockerfile` отсутствуют |
| Telegram polling | Не запускался: назначение текущего token как staging не подтверждено, риск второго poller исключён |
| Local Telegram bot | `@Guideosbot`, bot ID `8546334725`; identity подтверждён через `getMe` без запуска polling |
| Railway Telegram bot | `@Guide_os_bot`; назначение и GitHub → Railway deployment подтверждены владельцем, но runtime evidence из текущего окружения не получено |
| Classification | `@Guideosbot` пригоден для локальной staging-проверки после подтверждения отсутствия другого poller; `@Guide_os_bot` рассматривается как Railway-deployed Guide OS bot, но не заменяет отдельный shared staging без проверки среды |

Проверка не подтверждает доступность Telegram staging bot, Railway deployment, persistent volume, отдельный staging token или end-to-end связь с GuideShop.

### 4.6 Guide OS shared staging readiness runbook

#### Внешние prerequisites

Владелец должен предоставить без записи секретов в этот документ:

1. Подтвердить, что локальный `@Guideosbot` предназначен только для Guide OS staging и не используется другим окружением.
2. Использовать его существующий `BOT_TOKEN` только из локального `.env`; не переносить значение в документ, логи или Git.
3. Staging deployment target и доступ к его runtime logs.
4. Отдельный staging `DATABASE_PATH` на persistent volume.
5. `ADMIN_ID` тестового администратора либо явное решение оставить admin-функции отключёнными.
6. Подтверждение, что staging token не используется другим poller.

Production token запрещено использовать для staging. Значения token, credentials и Telegram user IDs запрещено добавлять в Markdown, Git, логи тестов или screenshots.

#### Pre-deploy checklist

- зафиксирован commit Guide OS для staging;
- полный локальный regression suite проходит;
- staging и production используют разные credentials;
- `TIMEZONE` задан явно;
- `DATABASE_PATH` указывает на staging volume, а не на repository filesystem;
- существует резервная копия staging DB перед повторным deployment;
- используется ровно один poller для staging token;
- feature flags будущей интеграции по умолчанию выключены;
- в runtime logs отсутствуют token, `.env` values и пользовательские данные.

#### Smoke test после deployment

1. Проверить Telegram identity staging-бота через безопасный `getMe`, не выводя token.
2. Убедиться, что процесс стартовал один раз и polling не завершается конфликтом.
3. Отправить `/start` тестовым пользователем.
4. Проверить главное меню и `/help`.
5. Создать тестовый тур на будущую дату.
6. Открыть календарь и карточку созданного тура.
7. Изменить безопасное тестовое поле и проверить сохранение.
8. Проверить статистику и профиль.
9. Перезапустить staging deployment и убедиться, что данные сохранились.
10. Проверить отсутствие повторной отправки фоновых уведомлений после рестарта.
11. Проверить, что второй тестовый пользователь не видит данные первого.
12. Удалить созданные тестовые данные через обычный пользовательский сценарий.

#### Evidence для закрытия пункта Staging Guide OS

В Approval Record фиксируются только несекретные сведения:

- дата и принимающий;
- staging bot username без token;
- commit SHA;
- deployment environment и region;
- результат startup/smoke проверки;
- результат persistence-after-restart;
- результат user isolation проверки;
- ссылка на защищённые runtime logs или отчёт;
- известные риски и ответственный за каждый риск.

### 4.7 Оставшиеся условия закрытия Stage 0

| Условие | Кто может выполнить | Текущий статус |
|---|---|---|
| Guide OS local repository validation | Этот чат | Выполнено, раздел 4.5 |
| Guide OS local staging bot identity | Этот чат | Выполнено: `@Guideosbot`, bot ID `8546334725`, `getMe` successful |
| Guide OS shared staging deployment | Владелец Railway / Cursor по отдельной задаче | `@Guide_os_bot` и GitHub → Railway flow заявлены владельцем; требуются commit/runtime/persistence evidence |
| GuideShop local development candidate | Mac Neo | Выполнено по evidence раздела 4.3 |
| GuideShop Railway staging | Владелец Railway на Mac Neo | Не подтверждено |
| Phase 2 baseline dataset | Mac Neo | Выполнено, раздел 4.4 |
| Linking/outbox dataset extension | Cursor после реализации соответствующих моделей | Не начато в рамках Stage 0 |
| Guide OS ↔ GuideShop end-to-end | Обе staging-системы | Заблокировано shared staging и credentials |
| Recovery/reconciliation drill | Обе staging-системы | Заблокировано реализацией и shared staging |

Stage 0 помечен `Closed` решением Product Owner для перехода к Stage 1. Невыполненные shared staging, end-to-end и recovery проверки сохраняются как явные обязательства и должны быть закрыты до production activation. Разрешение Stage 1 и Track A не является production approval.

## 5. Рекомендуемая схема интеграции

Для MVP используется pull + event notification:

1. Guide OS читает актуальные данные через read-only API GuideShop.
2. GuideShop публикует события через transactional outbox.
3. Guide OS принимает события идемпотентно и отправляет Telegram-уведомления.
4. При открытии карточки Guide OS запрашивает актуальное состояние у GuideShop, а не доверяет payload уведомления как источнику истины.
5. Периодическая reconciliation сверяет пропущенные или зависшие события.

Прямой доступ Guide OS к SQLite/production database GuideShop запрещён. Общая база данных между продуктами не используется.

## 6. Guide Identity и безопасное linking

### 6.1 Идентификаторы

- `guide_os_id`: непрозрачная, стабильная, неизменяемая строка, созданная Guide OS.
- `telegram_user_id`: идентификатор канала входа, не публичный integration ID.
- `guideshop_guide_id`: локальный ID GuideShop.
- Имена, телефон и username не являются надёжными ключами связывания.

Guide OS не должен переиспользовать освобождённый `guide_os_id` для другого человека.

### 6.2 Модель связи в GuideShop

Рекомендуется отдельная таблица вместо расширения одного nullable-поля:

```sql
CREATE TABLE guide_os_links (
    id INTEGER PRIMARY KEY,
    guideshop_guide_id INTEGER NOT NULL,
    guide_os_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'active', 'revoked', 'conflict')),
    verification_method TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    verified_at TEXT,
    revoked_at TEXT,
    verified_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (guide_os_id)
);
```

Для активных связей должна действовать уникальность `guideshop_guide_id`. Если SQLite не позволяет выразить это обычным constraint с условием, используется partial unique index:

```sql
CREATE UNIQUE INDEX uq_active_guideshop_guide_link
ON guide_os_links(guideshop_guide_id)
WHERE status = 'active';
```

Все переходы записываются в audit log. Старое `guides.guide_os_id` временно остаётся совместимым полем, но после миграции не используется как единственное доказательство связи.

### 6.3 Безопасный flow

1. Гид в Guide OS выбирает «Подключить GuideShop».
2. Guide OS создаёт одноразовый link token с TTL 10 минут, `guide_os_id`, nonce и intended audience.
3. Пользователь передаёт token менеджеру либо открывает защищённую ссылку/код в GuideShop.
4. GuideShop проверяет подпись/обменивает token server-to-server, создаёт `pending` link.
5. Guide OS показывает гиду компанию и запрос подтверждения.
6. После явного подтверждения link становится `active`.
7. Обе системы сохраняют audit event без полного token.

Автоматическое linking только по имени, телефону или Telegram username запрещено. Существующие совпадения можно использовать как подсказку, но они требуют подтверждения владельцем Guide OS identity.

### 6.4 Unlink/relink

- Unlink требует повторного подтверждения гида или уполномоченного администратора.
- Удаление не физическое: статус `revoked`, причина и timestamp сохраняются.
- Relink создаёт новую запись; старая история не переписывается.
- При конфликте данные гиду не показываются до ручного разрешения.

## 7. Авторизация и изоляция

- Guide OS аутентифицирует пользователя через Telegram user ID и собственную таблицу identity.
- API GuideShop принимает только service credentials Guide OS; пользовательские Telegram credentials не передаются.
- В каждом запросе GuideShop независимо разрешает `guide_os_id -> active link -> guideshop_guide_id`.
- Клиент не может передать произвольный `guideshop_guide_id` и получить данные другого гида.
- Все list/detail endpoints применяют одинаковый guide scope и company visibility rules.
- Для service-to-service MVP: HTTPS + короткоживущий подписанный JWT или OAuth2 client credentials. Статический API key допустим только как временная staging-мера с rotation и хранением в secrets manager.
- Claims: `iss`, `aud`, `sub`, `iat`, `exp`, `jti`, scopes.
- Минимальные scopes: `guideshop:read`, `guideshop:events:consume`, `guideshop:link`.

## 8. Минимальный состав данных

Передаются только поля, необходимые для Telegram UI.

### Guide

`guide_os_id`, `display_name` при необходимости сверки, `link_status`, `linked_at`.

### Company

`company_id`, `display_name`, `status`. Контакты, банковские данные и внутренние настройки не передаются.

### Visit

`visit_id`, `company_id`, `guide_os_id`, `visit_at`, `status`, `tourist_count`, `created_at`, `updated_at`.

### Sale

`sale_id`, `visit_id`, `amount_usd`, `category_id`, `category_name`, `payment_method` только если одобрено privacy/product, `created_at`, `updated_at`, `voided_at`.

### Points transaction

`points_transaction_id`, `sale_id`/`visit_id`, `amount`, `status`, `reason`, `calculated_at`, `credited_at`, `updated_at`.

### Общие правила

- Денежные суммы и points передаются JSON-строкой decimal с двумя знаками: `"125.40"`; `float` в контракте запрещён.
- Валюта Sales в MVP — `USD`; поле `currency` всё равно передаётся для явности.
- Время — UTC, ISO 8601, например `2026-08-07T09:15:00Z`.
- ID передаются как строки, даже если внутри GuideShop они integer.
- Телефон, Telegram user ID и платёжные реквизиты не входят в read API.
- Payment method включается только после явного product/privacy решения; default — не передавать.

## 9. Статусы и терминология

### Visit

`active`, `completed`, `cancelled`.

### Sale

`active`, `voided`. Исправление значимой суммы должно менять `updated_at` и создавать событие, а не незаметно переписывать историю.

### Points

Канонические статусы интеграции:

- `pending` — рассчитаны, но ещё не зачислены;
- `credited` — зачислены/выплачены;
- `reversed` — отменены после корректировки.

Если внутренняя модель GuideShop использует `pending_payment` и `paid`, adapter отображает их как `pending` и `credited`. Guide OS не воспроизводит расчёт points.

## 10. Read-only API GuideShop v1

Base path: `/integration/v1`. Все ответы содержат `request_id` и `schema_version`.

```text
GET /integration/v1/me/companies
GET /integration/v1/me/visits?cursor=&limit=&status=&from=&to=
GET /integration/v1/me/visits/{visit_id}
GET /integration/v1/me/sales?cursor=&limit=&from=&to=
GET /integration/v1/me/sales/{sale_id}
GET /integration/v1/me/points?cursor=&limit=&status=&from=&to=
GET /integration/v1/me/points/{points_transaction_id}
GET /integration/v1/me/history?cursor=&limit=&from=&to=
```

`me` определяется из подтверждённого `guide_os_id` в service request context. Guide OS не передаёт чужой ID в URL.

### Пример ответа списка

```json
{
  "schema_version": "1.0",
  "request_id": "req_01...",
  "data": [
    {
      "visit_id": "418",
      "company": {"company_id": "12", "display_name": "Silk Road Shop"},
      "visit_at": "2026-08-07T08:00:00Z",
      "status": "completed",
      "tourist_count": 14,
      "sales_usd": "320.00",
      "points": {"amount": "16.00", "status": "pending"},
      "updated_at": "2026-08-07T09:15:00Z"
    }
  ],
  "page": {"next_cursor": null}
}
```

### Ошибки

| HTTP | Code | Значение |
|---|---|---|
| 400 | `invalid_request` | Неверный фильтр или формат |
| 401 | `unauthenticated` | Service token отсутствует/невалиден |
| 403 | `link_not_active` | Нет активной подтверждённой связи |
| 404 | `not_found` | Объект отсутствует либо не принадлежит гиду |
| 409 | `link_conflict` | Обнаружен конфликт identity |
| 429 | `rate_limited` | Превышен лимит; используется `Retry-After` |
| 503 | `temporarily_unavailable` | Временная недоступность |

Для защиты от enumeration чужой объект возвращается как `404`, без раскрытия факта существования.

## 11. События

Обязательные типы:

- `visit.created.v1`;
- `sale.created.v1`;
- `points.recalculated.v1`;
- `points.credited.v1`.

Дополнительно для целостности рекомендуется `sale.voided.v1`, `visit.cancelled.v1`, `guide_link.revoked.v1`.

### Envelope

```json
{
  "event_id": "evt_01...",
  "event_type": "points.credited.v1",
  "occurred_at": "2026-08-07T09:15:00Z",
  "producer": "guideshop",
  "subject": {"type": "points_transaction", "id": "991"},
  "guide_os_id": "guide_01...",
  "data": {
    "points_transaction_id": "991",
    "amount": "16.00",
    "status": "credited",
    "company_id": "12",
    "visit_id": "418"
  },
  "schema_version": "1.0"
}
```

### Доставка

- Событие создаётся в outbox в той же DB transaction, что и бизнес-изменение.
- Worker доставляет события с exponential backoff и jitter.
- Guide OS сохраняет `event_id` до отправки уведомления; повторная доставка не создаёт повторное сообщение.
- После лимита попыток событие попадает в dead-letter state и создаёт alert.
- Порядок между разными объектами не гарантируется; `occurred_at` и актуальный API используются для разрешения состояния.
- Payload не содержит секретов и лишних персональных данных.

## 12. Telegram UX в Guide OS

Так как Guide OS не имеет отдельного web UI, «экран» означает состояние Telegram-бота: сообщение/карточка + inline keyboard.

### Меню

```text
GuideShop
├── Компании
├── Визиты
├── Продажи
├── Баллы
│   ├── Ожидают
│   └── Зачислены
└── История
```

### Внутренние маршруты callback

```text
gs:home
gs:companies:{cursor}
gs:visits:{cursor}
gs:visit:{visit_id}
gs:sales:{cursor}
gs:sale:{sale_id}
gs:points:{status}:{cursor}
gs:point:{points_transaction_id}
gs:history:{cursor}
```

Callback data Telegram ограничена по размеру, поэтому длинные opaque ID должны заменяться коротким server-side navigation token с TTL. Нельзя помещать service tokens или персональные данные в callback/deep link.

### Deep links из уведомлений

Рекомендуемая форма:

```text
https://t.me/<guide_os_bot>?start=gs_<short_navigation_token>
```

Token одноразовый или короткоживущий, привязан к Telegram user ID и указывает на тип/ID объекта на сервере. При открытии Guide OS повторно проверяет активный link и запрашивает объект из GuideShop.

### Состояния UI

Каждый экран должен поддерживать:

- loading/повтор запроса;
- пустой список;
- временную недоступность;
- link revoked;
- объект отменён/исправлен;
- pagination;
- «Назад» и возврат в GuideShop home.

## 13. Уведомления

| Event | Текст по умолчанию | Кнопка |
|---|---|---|
| `visit.created.v1` | «Создан новый визит в {company}.» | «Открыть визит» |
| `sale.created.v1` | «К визиту добавлена продажа на {amount} USD.» | «Открыть продажу» |
| `points.recalculated.v1` | «Баллы пересчитаны: {old_amount} → {new_amount}.» | «Открыть начисление» |
| `points.credited.v1` | «Зачислено {amount} баллов.» | «Открыть начисление» |

Правила:

- уведомление не считается источником текущего статуса;
- при нескольких быстрых пересчётах допустима агрегация;
- ошибки Telegram (`blocked`, invalid chat) фиксируются без бесконечных retries;
- содержание lock screen должно быть privacy-safe;
- уведомления можно отключить пользователем по типу, кроме security-сообщений о linking.

## 14. Production safety

Обязательные меры до production:

- отдельные staging/production credentials;
- TLS и проверка audience/issuer service token;
- secret rotation и отсутствие secrets в логах;
- deny-by-default guide scoping;
- audit linking и административных действий;
- rate limit, connect/read timeout, circuit breaker;
- bounded retries только для безопасных операций;
- transactional outbox и idempotent consumer;
- feature flags: API reads, events, notifications, linking;
- kill switch отдельно для delivery и чтения;
- structured logs с `request_id`, `event_id`, но без PII;
- метрики latency/error rate/outbox lag/DLQ/link conflicts;
- backup и проверенное восстановление;
- retention policy для events, logs и link audit;
- privacy review минимального payload;
- security tests на cross-guide и cross-company data access.

Рекомендуемые SLO для MVP staging, затем пересмотреть по факту:

- API availability: 99.5%;
- p95 read latency: до 1 секунды;
- 95% уведомлений обработаны за 2 минуты;
- ноль допустимых случаев cross-guide data exposure.

### 14.1 Production activation gate

Repository-level approval не разрешает production rollout. Перед включением production Отабек Джураев должен приложить к Approval Record следующие фактические evidence:

- успешный staging end-to-end run Guide OS ↔ GuideShop;
- результаты cross-guide и cross-company isolation tests;
- Railway startup logs без повторяющихся ошибок;
- подтверждение volume и production `SQLITE_DB_PATH`;
- актуальный полный off-box backup и успешный restore drill на отдельном окружении;
- подтверждение единственного poller для каждого production Telegram token;
- проверку secret storage и rotation procedure;
- результаты replay/DLQ/reconciliation drill;
- pilot smoke test с тестовыми Guide A и Guide B;
- зафиксированное решение go/no-go с датой.

Пока хотя бы один пункт отсутствует, допустимый статус — `production activation gated`.

## 15. Reconciliation и recovery

Ежедневная reconciliation:

1. Guide OS получает watermark/cursor изменений за период.
2. Сверяет известные IDs и `updated_at`.
3. Повторно запрашивает отсутствующие/изменённые объекты.
4. Не отправляет старые уведомления повторно без отдельного recovery-флага.
5. Формирует отчёт: checked, repaired, conflicts, failures.

Runbook должен описывать:

- повторную доставку одного event ID;
- replay безопасного диапазона событий;
- восстановление после недоступности Guide OS;
- rotation скомпрометированного credential;
- остановку уведомлений без остановки GuideShop;
- разрешение identity conflict;
- ручную проверку конкретного Guide/Visit/Sale.

## 16. Тестовые данные и сценарии

На staging нужны минимум:

- Guide A с активным link и данными двух компаний;
- Guide B для проверки изоляции;
- временный гид без link;
- pending link, revoked link и conflict link;
- Visit: active, completed, cancelled;
- Sale: active, corrected, voided;
- points: pending, credited, recalculated, reversed;
- Sale без payment method и с каждым разрешённым методом;
- timestamps на границе суток и часовых поясов;
- повторно доставленное событие;
- события, пришедшие не по порядку;
- недоступность GuideShop и Telegram.

### Acceptance criteria

- Guide A никогда не получает объекты Guide B, включая прямой запрос по ID.
- Повтор одного `event_id` создаёт не более одного уведомления.
- Открытие уведомления показывает актуальное состояние объекта.
- Revoked/conflict link немедленно прекращает выдачу данных.
- Деньги и points не теряют точность при сериализации.
- Все списки имеют pagination и стабильный порядок.
- Временная ошибка не создаёт бесконечный retry loop.
- Reconciliation обнаруживает искусственно пропущенное событие.
- Feature flag полностью выключает integration path.

## 17. План реализации

### Stage 1A — stable Guide OS identity

**Статус:** Completed and verified 2026-08-07.

- Guide OS создаёт непрозрачный UUID4 `guide_os_id` для каждого нового пользователя.
- Существующие пользователи получают ID через additive idempotent migration.
- Повторная регистрация и повторный `init_db()` сохраняют исходный ID.
- Уникальность обеспечивается индексом `idx_users_guide_os_id`.
- Все существующие application paths создания пользователя назначают ID.
- Добавлен read-only lookup `get_guide_os_id(user_id)` без побочного создания пользователя.
- Изменения ограничены `database/db.py`, `database/queries.py` и `tests/test_guide_os_identity.py`.
- Проверка: focused suite `5 passed`; full suite `37 passed`; `git diff --check` clean.
- GuideShop linking, API, events, Telegram UI и deployment не затронуты.

Принятый остаточный риск: колонка остаётся nullable для совместимости с additive SQLite migration, поэтому прямой out-of-band SQL технически может вставить `NULL`. Application paths назначают ID, а startup migration исправляет `NULL` и пустые значения.

### Stage 1B — secure GuideShop linking requests

**Статус:** Completed and verified 2026-08-07.

- Guide OS создаёт URL-safe одноразовые linking tokens с 256 битами криптографической случайности.
- В SQLite хранится только SHA-256 hash; raw token возвращается только при создании и не логируется.
- Запрос привязан к стабильному `guide_os_id`, audience `guideshop-link` и TTL 10 минут в UTC.
- Временные состояния запроса ограничены `issued`, `consumed` и `revoked`; authoritative GuideShop link status не дублируется.
- Новый запрос атомарно отзывает предыдущие issued-запросы того же гида и audience.
- Consume выполняется условным атомарным UPDATE и может успешно пройти только один раз.
- Проверка `expires_at > consumed_at` включена непосредственно в атомарное SQL-условие, исключая TTL race между предварительной проверкой и записью.
- Неизвестные, истёкшие, использованные, отозванные токены и неверный audience различаются доменными ошибками.
- Повторный `init_db()` сохраняет link-request history.
- Проверка: Stage 1B suite `8 passed`; Stage 1A suite `5 passed`; full suite `45 passed`; `git diff --check` clean.
- GuideShop, HTTP API, Telegram UI, events и deployment не затронуты.

Принятый остаточный риск: временные link-request rows сохраняются без автоматической очистки. Retention/cleanup policy должна быть утверждена и реализована отдельной минимальной задачей после определения требований audit retention.

### Stage 2A — Guide OS integration DTO contract

**Статус:** Completed and verified 2026-08-07.

- Добавлены строгие DTO для Company, Visit, Sale, points transaction, pagination, API envelopes и API errors.
- ID принимаются только как непустые строки без числового coercion.
- Деньги и points принимаются только как plain decimal strings с двумя знаками; `float`, exponent notation, NaN и Infinity отклоняются.
- Timestamps принимаются только как timezone-aware UTC ISO 8601 (`Z` или `+00:00`).
- Неизвестные поля и неподдерживаемая schema version отклоняются.
- Зафиксированы Visit, Sale и points statuses, а также cancelled/voided/reversed invariants.
- Реализованы типизированные payload для четырёх событий v1.
- `event_type`, `subject.type`, typed data и object ID обязаны согласовываться; `subject.id` равен ID объекта внутри event data.
- Контрактная валидация не выполняет сетевых запросов и операций с базой данных.
- Проверка: contract suite `40 passed`; Stage 1 regression `13 passed`; full suite `85 passed`; `git diff --check` clean.
- GuideShop connection, Telegram UI, persistence, event processing и deployment не затронуты.

Оставшееся условие: Guide OS DTO являются утверждённым implementation baseline, но должны быть сопоставлены с формальным GuideShop OpenAPI/JSON Schema до staging connection.

### Stage 3A — feature flags and mockable client boundary

**Статус:** Completed and verified 2026-08-07.

- Добавлены четыре независимых immutable feature flags: reads, linking, events и notifications.
- Все flags выключены по умолчанию; неизвестные и пустые явно заданные значения отклоняются.
- Добавлен runtime-checkable async read-only GuideShop client protocol без user-controlled guide identity parameters.
- Disabled client безопасно отклоняет все операции без сети и базы данных.
- Production factory при выключенных reads возвращает disabled client, а при включённых reads отказывает до появления реального authenticated client; fake fallback отсутствует.
- In-memory fake принимает и возвращает только Stage 2A DTO, использует deep-copy isolation и не сохраняет данные.
- Fake поддерживает deterministic ordering, status filtering, detail lookup, history и opaque scoped pagination.
- Проверка: Stage 3A suite `27 passed`; Stage 1/2 regression `53 passed`; full suite `112 passed`; `git diff --check` clean.
- HTTP, credentials, Telegram UI, persistence, events и deployment не затронуты.

Оставшееся условие: включение reads намеренно завершается configuration error до реализации authenticated HTTP client на одном из следующих этапов.

### Stage 3B — typed routes and navigation tokens

**Статус:** Completed and verified 2026-08-07.

- Добавлена immutable typed route model для home, lists и Visit/Sale/points details.
- Route invariants ограничивают object ID, cursor и points status только допустимыми route kinds.
- Navigation token содержит 192 бита случайности, имеет формат `gs_...`, длину 35 символов и не содержит route payload или identity.
- В SQLite сохраняются только SHA-256 hash, Telegram user binding, server-side route columns и audit timestamps.
- Token имеет TTL 24 часа, является single-use и атомарно проверяет token hash, Telegram user, status и expiration.
- Cross-user попытка отклоняется без consume/revoke.
- Route повторно валидируется после чтения; повреждённая запись не возвращает частичный маршрут.
- Linking и navigation используют отдельные таблицы и сервисы.
- Проверка: Stage 3B suite `50 passed`; previous integration regression `80 passed`; full suite `162 passed`; `git diff --check` clean.
- Telegram handlers, callbacks, `/start`, GuideShop calls и feature activation не добавлены.

Остаточный риск: consumed/revoked navigation rows сохраняются бессрочно до утверждения общей audit retention policy.

### Stage 3C1 — GuideShop presentation layer

**Статус:** Completed and verified 2026-08-09.

- Добавлены immutable screen/action presentation models и async UI service с client injection.
- Реализованы home, companies, Visits, Sales, points, history и detail screens на Stage 2A DTO.
- Все внешние DTO values экранируются для HTML; Decimal values отображаются без вычислений.
- Реализованы pagination, empty, disabled, unavailable, forbidden и not-found состояния.
- Detail actions имеют детерминированные ordinal labels без object IDs или внешних данных.
- Inline keyboard создаёт по одному user-bound Stage 3B token на action; callback содержит только `gs_...`.
- Flaky Stage 3B opacity test исправлен deterministic randomness injection без изменений production-кода.
- Проверка: navigation suite `50 passed`; UI suite `18 passed`; full suite `180 passed`; `git diff --check` clean.
- Telegram handlers, main menu, router registration, HTTP и GuideShop connection не добавлены.

Остаточный риск: создание keyboard выпускает tokens до отправки сообщения; неотправленные tokens остаются issued до TTL/revocation и будущей cleanup policy.

### Stage 3C2 — feature-gated Telegram mock UI

**Статус:** Completed and verified 2026-08-09.

- Добавлена отдельная development/test-only fake setting; fake запрещён в staging/production.
- Main menu сохраняет default-off совместимость и показывает `🛍 GuideShop` только при reads-enabled.
- Добавлены feature-gated entry handler и typed route callback dispatch.
- Callback token разрешается только для `callback.from_user.id`; raw route parameters не используются.
- Disabled state не consumes token; expired/consumed/revoked/access-denied/invalid-route состояния отображаются безопасно.
- Explicit local fake создаётся только в разрешённом environment и содержит пустые synthetic collections.
- GuideShop router зарегистрирован до global errors router.
- Environment-sensitive test изолирован от локального `.env`.
- Проверка: Stage 3C2 suite `40 passed`; full suite `220 passed`; `git diff --check` clean.
- Локальный `@Guideosbot` показывает feature-gated GuideShop entry при explicit development flags.

Остаточный риск: navigation token consumes до Telegram message edit; при неожиданной ошибке edit пользователь должен заново открыть GuideShop.

### Stage 3D — Telegram `/start` deep links

**Статус:** Completed and verified 2026-08-09.

- Добавлен строгий builder Telegram deep link, содержащий только opaque `gs_` token.
- GuideShop handler принимает только точный navigation payload и зарегистрирован до generic `/start`.
- Разрешение использует существующие typed routes и user-bound single-use token semantics.
- Disabled integration не consumes token; stale, denied и invalid состояния не раскрывают внутренние данные.
- Plain `/start` и unrelated payload сохраняют прежний flow.
- Development-only helper создаёт локальную тестовую ссылку и недоступен через Telegram или вне development.
- Проверка: deep-link/helper regression `58 passed`; full suite `278 passed`; `git diff --check` clean.
- Ручной smoke test в `@Guideosbot`: первое открытие показало Visits, повторное открытие той же ссылки показало stale-link state.

Остаточный риск: navigation token consumes до отправки Telegram screen; при ошибке доставки требуется выпустить новую ссылку или заново открыть GuideShop.

### Track A — можно начать немедленно

1. Утвердить этот документ и заполнить owners.
2. Зафиксировать OpenAPI 3.1 и JSON Schema событий.
3. Создать миграцию `guide_os_links` и audit events.
4. Реализовать link service и тесты переходов статусов.
5. Реализовать read adapter/repositories GuideShop.
6. Подготовить Guide OS Telegram menu на mock API.
7. Реализовать event consumer и notification deduplication на mock events.
8. Создать contract и security tests.

### Track B — после готовности staging обеих систем

1. Выпустить service credentials.
2. Подключить Guide OS к staging GuideShop API.
3. Включить outbox delivery.
4. Загрузить тестовые данные.
5. Пройти end-to-end и recovery tests.
6. Провести privacy/security review.

### Track C — только после Phase 2 и production-safety approval

1. Провести миграцию существующих гидов в `pending`, без автоактивации.
2. Включить linking для pilot group.
3. Включить read API через feature flag.
4. Включить события и уведомления по одному типу.
5. Наблюдать метрики и reconciliation.
6. Расширять rollout только при отсутствии data isolation и delivery incidents.

## 18. Definition of Done Phase 3 MVP

- Guide OS является владельцем Guide identity и выдаёт стабильный `guide_os_id`.
- Существующие гиды связаны подтверждённым и аудируемым способом.
- Гид видит только свои Company, Visits, Sales и points.
- Значения совпадают с GuideShop; расчётов points в Guide OS нет.
- Четыре обязательных уведомления доставляются идемпотентно.
- Каждое уведомление открывает правильную Telegram-карточку.
- Reconciliation и recovery проверены на staging.
- Security/privacy checklist подписан.
- Phase 2 и production-safety подтверждены.
- Pilot rollout завершён без критических инцидентов.

## 19. Открытые решения

До coding freeze должны быть закрыты:

1. Формат стабильного `guide_os_id`: **закрыто 2026-08-07 — UUID4 opaque string, владельцем является Guide OS**.
2. Способ service authentication: OAuth2 client credentials или signed JWT.
3. Механизм доставки событий: webhook endpoint Guide OS либо очередь.
4. Нужно ли показывать payment method гиду. Default: нет.
5. Нужны ли названия sale categories или достаточно category ID. Рекомендация: передавать ID и display name snapshot.
6. Правило показа corrected/reversed points в истории.
7. Срок хранения event inbox/outbox и audit log.
8. Кто имеет право принудительно unlink/relink.

## 20. Cursor Prompt для реализации

Использовать только после предоставления обоих репозиториев или точного указания, в каком из них выполняется каждый блок.

```text
Implement the Guide OS Integration MVP foundation according to
GUIDE_OS_INTEGRATION_FOUNDATION.md.

Constraints:
- Do not enable production integration or modify production credentials.
- Guide OS owns Guide identity. GuideShop owns Company, Visit, Sale and points.
- Guide OS is read-only for GuideShop business data.
- Never auto-link by name, phone or Telegram username.
- Preserve all existing behavior and migrations.
- Apply tenant/guide scope to every list and detail query.
- Use Decimal-compatible string serialization for money and points.
- Use UTC ISO 8601 timestamps at the integration boundary.
- Implement changes behind feature flags, disabled by default.
- Do not place secrets or PII in logs, callback data or deep links.

GuideShop tasks:
1. Add an additive migration for guide_os_links with pending, active, revoked and
   conflict states, uniqueness for active links, timestamps and audit support.
2. Implement a link domain service with explicit state transitions and tests.
3. Add read-only integration adapters/endpoints under /integration/v1 for
   companies, visits, sales, points and history.
4. Resolve guide_os_id from authenticated service context; never accept an
   arbitrary guideshop_guide_id from the client.
5. Add a transactional outbox for visit.created.v1, sale.created.v1,
   points.recalculated.v1 and points.credited.v1.
6. Add bounded retry, dead-letter state, structured logging and metrics hooks.
7. Add OpenAPI 3.1 and JSON Schemas plus contract, isolation and idempotency tests.

Guide OS tasks:
1. Add GuideShop menu, list/detail Telegram handlers and keyboards using a mockable
   API client.
2. Add short server-side navigation tokens for callbacks/deep links.
3. Add an idempotent event inbox keyed by event_id.
4. Add notification formatting and delivery for the four required event types.
5. Re-fetch current object state when a notification is opened.
6. Handle empty, unavailable, revoked, conflict and corrected states.
7. Add reconciliation command/job and tests.

Verification:
- Run the existing test suite first and after changes.
- Add tests proving cross-guide and cross-company access is impossible.
- Add tests for duplicate and out-of-order events.
- Add tests for decimal precision, UTC timestamps and revoked links.
- Report changed files, migration behavior, test results, remaining risks and all
  decisions that still require product/security approval.
- Stop before any production deployment or external credential creation.
```

## 21. Approval record

| Решение | Имя | Дата | Результат |
|---|---|---|---|
| Product scope | Отабек Джураев | 2026-08-07 | Approved |
| Data ownership | Отабек Джураев | 2026-08-07 | Approved согласно разделу 2 |
| API/event contract | Отабек Джураев | 2026-08-07 | Approved as implementation baseline; изменения версионируются |
| Security/privacy | Отабек Джураев | 2026-08-07 | Approved for preparation; payment method excluded by default; production review pending |
| Staging readiness | Отабек Джураев | 2026-08-07 | Guide OS local candidate and `@Guideosbot` identity confirmed on current Mac; `@Guide_os_bot` GitHub/Railway role confirmed by owner, runtime evidence pending; GuideShop candidate confirmed on Mac Neo |
| Phase 2 evidence | Отабек Джураев | 2026-08-07 | Approved at repository level; 1191 tests passed |
| Production-safety | Отабек Джураев | 2026-08-07 | Repository controls accepted; live operational checks pending |
| Stage 0 closure | Отабек Джураев | 2026-08-07 | Approved; Stage 1 authorized; unresolved shared-staging evidence transferred to production activation gate |
| Production rollout | Отабек Джураев | 2026-08-07 | Not approved; blocked by section 14.1 gate |

### Sign-off statement

Я, Отабек Джураев, подтверждаю предложенные в этом документе product и architecture решения, принимаю ответственность по перечисленным направлениям и разрешаю начать подготовку и реализацию интеграции Guide OS ↔ GuideShop в пределах Track A и доступной части Track B. Это подтверждение не разрешает production activation до получения и фиксации evidence из раздела 14.1.
