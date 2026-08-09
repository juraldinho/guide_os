# Guide OS — Project State

> Обновлено: 2026-08-09

## Текущий статус

Guide OS работает как отдельный Telegram-инструмент гида. Stage 0–4A завершены и проверены. Identity, linking-token foundation, contracts, typed routes, mock Telegram UI, одноразовые `/start` deep links и production-safe read-only HTTP client foundation готовы; production composition с GuideShop ещё отсутствует.

GuideShop должен оставаться источником истины для компаний, Visits, Sales и points. Guide OS не должен получать прямой доступ к базе данных GuideShop. Целевая модель MVP: read-only API GuideShop для чтения данных и события GuideShop для уведомлений.

## Цель интеграции

Дать авторизованному гиду доступ внутри Guide OS только к собственным данным GuideShop: компаниям, Visits, Sales, балансу и истории points, а также к идемпотентным уведомлениям о новых и изменённых объектах.

## Архитектурные границы

- Каждому гиду назначается стабильный и неизменяемый `guide_os_id`.
- Связь профилей Guide OS и GuideShop является отдельной аудируемой сущностью.
- Один профиль гида GuideShop нельзя одновременно связать с несколькими профилями Guide OS.
- Автоматическое связывание допустимо только по надёжному уникальному идентификатору.
- Имя и телефон без подтверждения не являются достаточным основанием для автоматического связывания.
- GuideShop остаётся источником истины для Visits, Sales и points.
- Guide OS использует сервисный API и события, но не прямое подключение к базе GuideShop.
- Все пользовательские чтения должны проверять принадлежность данных текущему `guide_os_id`.
- Интеграция должна отключаться feature flag без нарушения основных функций Guide OS.
- Изменения выполняются по принципу Minimal Change, без несвязанного рефакторинга.

## Этапы интеграции

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
- Stage 4A: реализован identity-bound authenticated async HTTP client для `/integration/v1/me/...` с typed validation, bounded retries и bounded response reading.
- Реальный access-token provider, GuideShop API availability, события и production activation ещё не реализованы.

## Readiness checklist перед production-интеграцией

- [x] Phase 2 подтверждена на repository level; live production-safety остаётся activation gate.
- [x] Определены владельцы данных по каждой сущности.
- [x] Guide OS выдаёт стабильный `guide_os_id`.
- [x] Утверждён linking contract и реализована Guide OS-side token foundation.
- [ ] Guide OS contract baseline реализован; требуется формальное сопоставление и согласование с GuideShop.
- [x] Готовы внутренние маршруты, callbacks и Telegram `/start` deep-link entry.
- [ ] Настроены staging-окружения обеих систем.
- [ ] Есть тестовые Guides, Visits, Sales и разные статусы points.
- [ ] Реализованы авторизация, аудит, идемпотентность и мониторинг.
- [ ] Описаны reconciliation и восстановление после пропущенных событий.
