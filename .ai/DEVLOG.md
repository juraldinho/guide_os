# Guide OS — Development Log

## 2026-08-06 — Сформирован первичный план интеграции Guide OS ↔ GuideShop

Выполнено:

- определены архитектурные границы read-only MVP;
- интеграция разделена на последовательные этапы от readiness до production rollout;
- зафиксированы требования к identity, linking, API, событиям, deep links, безопасности, идемпотентности, мониторингу и reconciliation;
- установлена первая следующая задача: Stage 0 — readiness и владельцы данных;
- Cursor Prompt намеренно отложен до завершения readiness-проверки.

Код проекта не изменялся. Автоматические и ручные тесты не запускались, поскольку этап был исключительно документальным.

## 2026-08-07 — Stage 0 закрыт, Stage 1A завершён

Выполнено:

- Stage 0 закрыт решением Product Owner;
- shared-staging и live production-safety evidence сохранены как production activation gate;
- в `users` добавлен стабильный UUID4 `guide_os_id`;
- существующие пользователи получают ID через идемпотентный backfill;
- повторная регистрация сохраняет исходный ID;
- добавлен read-only lookup без побочного создания пользователя.

Проверка: focused suite — `5 passed`; полный suite — `37 passed`; `git diff --check` clean.

## 2026-08-07 — Stage 1B завершён

Выполнено:

- добавлено временное хранилище GuideShop linking requests;
- реализованы URL-safe tokens с 256 битами криптографической случайности;
- сохраняется только SHA-256 hash;
- зафиксированы audience `guideshop-link` и TTL 10 минут UTC;
- новый запрос отзывает предыдущий issued-запрос;
- consume выполняется однократно через атомарный условный UPDATE;
- expiration включён в атомарное SQL-условие;
- добавлены доменные ошибки для unknown, expired, consumed, revoked и wrong audience.

Проверка: Stage 1B — `8 passed`; Stage 1A — `5 passed`; полный suite — `45 passed`; `git diff --check` clean.

Остаточный риск: автоматическая очистка link-request history отложена до утверждения retention policy.

## 2026-08-07 — Stage 2A завершён

Выполнено:

- добавлены строгие DTO для Company, Visit, Sale и points transaction;
- добавлены pagination, API list/detail envelopes и безопасные API errors;
- деньги и points ограничены Decimal-строками без numeric coercion;
- timestamps ограничены UTC ISO 8601;
- неизвестные поля и неподдерживаемые версии отклоняются;
- добавлены четыре типизированных event payload v1;
- event type, subject type, typed data и object ID проверяются совместно;
- `subject.id` обязан совпадать с ID основного объекта внутри event data;
- доказано отсутствие DB/network side effects при валидации.

Проверка: contract suite — `40 passed`; Stage 1 regression — `13 passed`; полный suite — `85 passed`; `git diff --check` clean.

Следующее действие: Stage 3A — feature flags и mockable GuideShop client boundary без реальной сети.

## 2026-08-07 — Stage 3A завершён

Выполнено:

- добавлены независимые default-off flags для reads, linking, events и notifications;
- добавлен async read-only GuideShop client protocol;
- identity scope исключён из user-controlled method arguments;
- disabled client не выполняет сеть и SQLite;
- production factory не включает fake при reads-enabled;
- explicit in-memory fake возвращает только валидированные Stage 2A DTO;
- реализованы deep-copy isolation, deterministic ordering, filtering, details, history и opaque scoped pagination.

Проверка: Stage 3A — `27 passed`; Stage 1/2 regression — `53 passed`; полный suite — `112 passed`; `git diff --check` clean.

Остаточный риск: reads-enabled намеренно неработоспособен до реализации реального authenticated client.
