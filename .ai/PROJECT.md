# Guide OS — Project State

> Обновлено: 2026-08-28

> **Канонический roadmap:** `integration_foundation.md`, раздел 18. Историческая декомпозиция ниже сохранена только как архитектурная справка.

## Текущий статус

Интеграционные Stages 0–18 завершены с PASS и активированы в production. Финальная production-архитектура: GuideShop transactional outbox и authenticated event feed → Guide OS durable inbox, identity isolation и deduplication → bounded Telegram notification delivery с существующим safe deep link.

GuideShop остаётся источником истины для официальных Visits и points. GuideShop производит и публикует domain events, но не доставляет Telegram-уведомления: GuideShop events включены, а его notifications выключены. Guide OS потребляет события, хранит inbox/checkpoint/watermark и выполняет Telegram-доставку; Guide OS events и notifications включены.

GuideShop остаётся источником истины для официальных компаний, Visits/Sales и points. Guide OS является источником истины для будущих личных мест гида и самостоятельно внесённых внешних продаж. Guide OS не получает прямой доступ к базе GuideShop: актуальное business state читается через read-only API, а события используются только как сигнал для inbox и уведомления.

Stage 19 выбран владельцем и начат в Guide OS: личные места и личные записи гида создаются только в профиле Guide OS. Stage 19B persistence/ownership уже committed/pushed на branch `stage19-personal-records` (`22fb924`). Stage 19C Telegram CRUD для `📍 Мои места` реализован локально, но ещё не закоммичен и ожидает local Telegram smoke.

## Цель интеграции

Дать авторизованному гиду доступ внутри Guide OS только к собственным данным GuideShop: компаниям, Visits, Sales, балансу и истории points, а также к идемпотентным уведомлениям о новых и изменённых объектах.

## Архитектурные границы

- Каждому гиду назначается стабильный и неизменяемый `guide_os_id`.
- Связь профилей Guide OS и GuideShop является отдельной аудируемой сущностью.
- Один профиль гида GuideShop нельзя одновременно связать с несколькими профилями Guide OS.
- Автоматическое связывание допустимо только по надёжному уникальному идентификатору.
- Имя и телефон без подтверждения не являются достаточным основанием для автоматического связывания.
- GuideShop остаётся источником истины для официальных Visits/Sales и всех официальных points transactions.
- Guide OS остаётся источником истины для личных, видимых только владельцу мест и self-reported external sales; эти записи не являются компаниями GuideShop.
- Guide OS использует сервисный API и события, но не прямое подключение к базе GuideShop.
- Все пользовательские чтения должны проверять принадлежность данных текущему `guide_os_id`.
- Интеграция должна отключаться feature flag без нарушения основных функций Guide OS.
- Изменения выполняются по принципу Minimal Change, без несвязанного рефакторинга.

## Историческая декомпозиция Guide OS

Раздел ниже сохраняется как техническая история реализации Guide OS и не определяет актуальную нумерацию следующих Stages. Для планирования использовать только master roadmap Stages 0–20.

### Stage 0 — Readiness и владельцы данных

Цель: подтвердить, что обе системы готовы к проектированию интеграции.

Задачи:

1. Зафиксировать владельца данных для Guide, Company, Visit, Sale, points transaction и integration link.
2. Проверить завершение Phase 2 и наличие production-safety проверки.
3. Определить минимально необходимые персональные и платёжные поля для Guide OS.
4. Подготовить staging обеих систем и набор тестовых данных со всеми требуемыми статусами.
5. Назначить ответственных за API, события, безопасность, мониторинг и reconciliation.

Результат: согласованный readiness checklist без открытых блокирующих вопросов.

### Stage 1 — Identity и безопасное связывание гидов

Цель: создать надёжную основу идентификации до подключения бизнес-данных.

Задачи:

1. Утвердить формат, генерацию, уникальность и неизменяемость `guide_os_id`.
2. Спроектировать сервисную авторизацию Guide OS ↔ GuideShop отдельно для staging и production.
3. Определить модель integration link и историю её изменений.
4. Описать операции `link`, `unlink` и `relink`, права на них и обязательный audit trail.
5. Разрешить автоматическое сопоставление только по надёжному уникальному идентификатору.
6. Направлять спорные совпадения на ручное подтверждение.
7. Обеспечить ограничение: один гид GuideShop связан не более чем с одним профилем Guide OS.
8. Определить сценарии конфликтов, восстановления и поддержки.

Результат: утверждённый identity/linking contract и безопасный процесс миграции существующих гидов.

### Stage 2 — API и event contract

Цель: согласовать версионируемый контракт между системами до реализации экранов и уведомлений.

Задачи:

1. Зафиксировать форматы всех идентификаторов и правила их стабильности.
2. Определить обязательные и необязательные поля по каждой сущности.
3. Утвердить справочники статусов и категорий.
4. Передавать timestamps в UTC в формате ISO 8601.
5. Передавать деньги как decimal-значение либо целое число минимальных единиц с явной валютой; не использовать float.
6. Определить версионирование API и event schema.
7. Описать удалённые, отменённые, исправленные и пересчитанные записи.
8. Определить read-only endpoints для companies, Visits, Sales, balance и points history.
9. Определить события `visit.created`, `sale.created`, `points.recalculated`, `points.credited`.
10. Включить в каждое событие `event_id`, `guide_os_id`, тип и ID объекта, время, deep link или параметры маршрута и версию схемы.
11. Описать ошибки, pagination, rate limits, timeouts и retry policy.

Результат: согласованная версия API/event contract и тестовые примеры payload.

### Stage 3 — Каркас GuideShop внутри Guide OS

Цель: подготовить стабильные пользовательские маршруты до подключения реальных данных.

Задачи:

1. Определить навигацию раздела GuideShop в Guide OS.
2. Подготовить базовые read-only экраны: компании, Visits, Visit details, Sales, Sale details, баланс, pending/credited points, история начислений и пересчётов.
3. Утвердить устойчивые deep links:
   - `/guideshop/visits/{visit_id}`;
   - `/guideshop/sales/{sale_id}`;
   - `/guideshop/points/{transaction_id}`.
4. Определить состояния loading, empty, unavailable, forbidden и not found.
5. Проверить, что маршрут никогда не позволяет прочитать данные другого гида.

Результат: готовые и проверяемые маршруты и базовые экраны без зависимости от уведомлений.

### Stage 4 — Read-only интеграция

Цель: показать гиду его актуальные данные GuideShop через API.

Задачи:

1. Подключить API-клиент GuideShop с минимальными правами.
2. Получать список компаний, Visits, Sales, баланс и points history.
3. Применять серверную проверку доступа по `guide_os_id` для каждого объекта.
4. Добавить ограниченные retries, timeouts, обработку rate limits и безопасные пользовательские ошибки.
5. Добавить feature flag интеграции.
6. Покрыть контрактными, авторизационными и негативными тестами.

Результат: гид видит только собственные read-only данные, а недоступность GuideShop не нарушает основные функции Guide OS.

### Stage 5 — События и уведомления

Цель: доставлять уведомления с переходом к устойчивому deep link.

Задачи:

1. Реализовать приём согласованных событий.
2. Обеспечить идемпотентность по `event_id`.
3. Создавать не более одного уведомления при повторной доставке.
4. Проверять `guide_os_id`, schema version и связанный объект.
5. Добавить ограниченные retries и dead-letter механизм.
6. Связать уведомления с маршрутами Visit, Sale и points transaction.

Результат: повторная доставка безопасна, а уведомление открывает корректный объект текущего гида.

### Stage 6 — Reconciliation и эксплуатационная готовность

Цель: обеспечить обнаружение и восстановление пропущенных или рассинхронизированных данных.

Задачи:

1. Описать reconciliation между API-данными и обработанными событиями.
2. Реализовать восстановление после пропущенных событий.
3. Добавить audit log для связывания и интеграционных операций.
4. Настроить метрики задержки, ошибок, retries, dead-letter и конфликтов linking.
5. Подготовить runbook отключения feature flag и восстановления интеграции.
6. Провести security, privacy и production-readiness проверки.

Результат: интеграция наблюдаема, восстанавливаема и безопасно отключается.

### Stage 7 — Поэтапный запуск

Цель: выпустить интеграцию с контролируемым риском.

Задачи:

1. Провести end-to-end проверку в staging на тестовых гидах и всех статусах.
2. Запустить ограниченный pilot.
3. Проверить доступ, дубликаты уведомлений, задержки, reconciliation и audit trail.
4. Расширять rollout только после успешных критериев pilot.

Результат: контролируемый production rollout с возможностью быстрого отключения.

## Порядок реализации

Строгая последовательность: readiness → identity/linking → API/event contract → маршруты и базовые экраны → read-only данные → события и уведомления → reconciliation/operations → rollout.

Следующий этап не начинается, пока не выполнены критерии готовности предыдущего этапа.

## Реализованная основа интеграции

- Production read-only UI обновлён: company details показывают optional public contacts, Visit details показывают связанные points, Sales скрыт из guide-facing menu.
- GuideShop API commit `94e8761` и Guide OS UI commit `4549938` успешно выпущены; owner smoke `Company Visit UI smoke PASS`.
- Final points summary выпущен: GuideShop commit `cd3895d` предоставляет complete-scope totals, Guide OS commit `0d67289` показывает pending/credited totals и per-company breakdown без opaque IDs.
- Final owner smoke: `Final points UX smoke PASS`.

- Stage 1A: каждому пользователю назначается стабильный уникальный UUID4 `guide_os_id`.
- Существующие пользователи получают ID через additive idempotent migration.
- Stage 1B: реализованы временные одноразовые GuideShop linking requests.
- Raw linking token не хранится; сохраняется только SHA-256 hash.
- Token имеет 256 бит энтропии, audience `guideshop-link` и TTL 10 минут UTC.
- Consume является атомарным, однократным и учитывает expiration в SQL-условии.
- Stage 2A: реализованы строгие GuideShop DTO, API envelopes/errors и четыре типизированных event payload v1.
- Decimal values, UTC timestamps, schema versions, unknown fields и event object identity валидируются до использования данных.
- Stage 3A: добавлены default-off integration flags и async read-only client protocol.
- Disabled client и explicit in-memory fake не выполняют network/database operations; production factory не включает fake автоматически.
- Stage 3B: реализованы typed internal routes и короткие user-bound navigation tokens с server-side payload.
- Navigation resolution является single-use, TTL-aware и защищено от cross-user доступа.
- Stage 3C1: реализован безопасный presentation layer и tokenized inline keyboards для mock-backed экранов.
- HTML экранируется, Decimal values не пересчитываются, list actions различимы ordinal labels.
- Stage 3C2: mock-backed Telegram entry и callback dispatch доступны через explicit development flags.
- Stage 3D: реализованы строгие user-bound single-use `/start` deep links и development-only smoke helper.
- Stage 4A: реализованы identity-bound HTTP client, request-scoped composition, Ed25519/EdDSA auth contract, async token provider и default-off real runtime composition.
- Stage 4A закрыт: `470 passed`, локальный fake smoke test ранее подтверждён владельцем.
- Stage 4B GuideShop staging reads завершён; production events и activation ещё не включены.
- Reproducible-environment quality gate завершён; текущий runtime pin — attested Python `3.13.14`.
- Continuous-integration quality gate завершён: clean GitHub Actions runner устанавливает pinned dependencies и выполняет полный suite без secrets, Telegram polling, GuideShop network calls или deployment; CI run `31408186374` успешен, `472 passed`.
- Contract `v1.1.0` закреплён на commit `c071fd45d4ec684f5ac32e8e9e71bc26d4014283` и проверяется отдельным hosted workflow.
- Guide OS Stage 5D provider завершён: реализованы link exchange persistence, authoritative lifecycle evidence, inbound GuideShop EdDSA verifier, atomic JTI replay protection и три `/integration/v1/link-exchanges...` routes.
- Provider имеет отдельные default-off flags и явный isolated Railway staging runtime path; production activation остаётся fail-closed.
- Проверка Stage 5D: focused provider `30 passed`; полный suite `584 passed`; GitHub CI run `31622573211` и Integration Contracts run `31622573278` — success.
- API-only staging entrypoint commit `ac779b417b6adb50f43494cf4c0d25e6e292d646`: focused `117 passed`, полный suite `601 passed`, CI `31743087618` и contracts `31743087697` — success.
- Isolated Railway staging deployment активен на exact candidate commit `b895622`; volume `/data` READY.
- Staging HTTPS base URL: `https://guide-os-staging-api-staging.up.railway.app`; `GET /health` независимо подтверждён с HTTP 200 и безопасным JSON payload.
- Staging-only mise bypass удалён; deployment `a79abd94…` успешно verified GitHub artifact attestations для Python `3.13.14`.
- GuideShop staging E2E закрыт: Gate 4A lifecycle `44/44 PASS`, Gate 4B reads `PASS`, auth/query/cursor `26/26`, FA/IC `0 FAIL`, contract `v1.1.0`.
- Исторический default-off production gate был успешно закрыт последующими Stages 12–18.
- Production lifecycle absence audit PASS: staging lifecycle variables, integration flags и mise bypass отсутствуют во всех production-effective scopes.
- Candidate `b895622` прошёл full suite `632`, GitHub CI и Integration Contracts; production-safe staging proof завершён без attestation bypass.
- Fresh production SQLite backup PASS: age-encrypted off-platform artifact verified by restore; production unchanged. Railway native snapshot отсутствует, но owner отдельно утвердил local-only recovery copy.

## Финальный integration closure

- [x] Phase 2 и production-safety подтверждены.
- [x] Определены владельцы данных по каждой сущности.
- [x] Guide OS выдаёт стабильный `guide_os_id`.
- [x] Утверждён linking contract и реализована Guide OS-side token foundation.
- [x] Contracts обеих систем закреплены и совместимы на `v1.2.0`.
- [x] Готовы внутренние маршруты, callbacks и Telegram `/start` deep-link entry.
- [x] Staging и production окружения обеих систем проверены.
- [x] Авторизация, isolation, идемпотентность, recovery и monitoring проверены.
- [x] Reconciliation, backup/restore, security и load gates завершены.
- [x] Owner notification/deep-link и Visit back-navigation smoke — PASS.

Guide OS production работает на commit `930759340a867113c6a78da64552936f5428597d`, deployment `9da4811d-8987-467d-bcd8-8f667f6fd081`, events/notifications ON. GuideShop production работает на commit `c6cbbf48a7d0c0a6d133e724db2c39ce28a5ab3b`, deployment `cfd82638-bc76-4a87-b7db-dd0f6886a593`, events ON и notifications OFF.

Финальное состояние: одна active link; GuideShop outbox `2`, один aggregate subject version `2`; Guide OS inbox stale `1`, delivered `1`, pending/processing/dead-letter `0`; checkpoint generation `2`; watermark version `2`; notification attempts/successes `1/1`; duplicates `0`; reconciliation `CLEAN`. Stage 17 observation завершён за `10m11s`: `22` cycles, HTTP `200×22`, failures/retries/duplicates/DLQ `0`. Stage 18 runtime/data/security/operations closure — PASS. Реализационных gates не осталось; текущая деятельность — только routine monitoring и incident response.

## Отдельный будущий workstream — личные места и внешние продажи

Этот workstream не входит в текущий read-only MVP и не меняет последовательность Stage 4B–7. Его проектирование начинается после готовности базовой GuideShop-side интеграции.

- Гид один раз создаёт личное место в Guide OS и затем выбирает его из собственного списка.
- Личное название, общая локация, ориентир, категория, заметка, сумма покупки и фактически полученный наличный доход принадлежат Guide OS и видны только владельцу.
- Guide OS не формирует глобальный каталог неофициальных магазинов и не пытается объединять записи разных гидов.
- GuideShop получает только минимальную идемпотентную заявку на points по уникальному `external_sale_id`, если такая программа будет отдельно утверждена.
- GuideShop остаётся единственным владельцем официального points balance и принимает решение `pending`, `credited`, `rejected`, `reversed` либо rate-limit/anti-abuse outcome.
- Название личного места не обязано передаваться в GuideShop.
- Автоматическая связь с официальной компанией запрещена; возможна только после надёжного подтверждения.
- Юридическая, налоговая, anti-fraud и redemption-модель баллов должна быть утверждена до реализации write API или начисления доступных баллов.
