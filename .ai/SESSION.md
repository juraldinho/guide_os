# Guide OS — Current Development Session

> Обновлено: 2026-08-07

## Текущий фокус

Подготовка Guide OS к будущей интеграции с GuideShop до начала изменений GuideShop.

## Завершённые этапы

- Stage 0 — закрыт Product Owner;
- Stage 1A — stable UUID4 `guide_os_id`;
- Stage 1B — secure one-time linking requests;
- Stage 2A — strict GuideShop DTO and event contract baseline.

## Проверенное состояние

- raw linking tokens не сохраняются;
- atomic consume учитывает status и expiration;
- Decimal values не принимаются из `float`/`int`;
- timestamps принимаются только в UTC;
- event type, subject type, typed payload и object ID согласованы;
- contract suite: `40 passed`;
- Stage 1 regression: `13 passed`;
- full suite: `85 passed`;
- GuideShop network connection, Telegram integration UI и event processing отсутствуют.

## Следующее действие

Подготовить и выполнить Stage 3A согласно `.ai/NEXT_TASK.md`: default-off feature flags и mockable read-only client boundary.

## Открытые решения

1. Service authentication: OAuth2 client credentials или signed JWT.
2. Event delivery: webhook endpoint или очередь.
3. Retention для link requests, event inbox/outbox и audit log.
4. Формальное сопоставление Guide OS DTO с GuideShop OpenAPI/JSON Schema.
5. Право принудительного unlink/relink.

## Production gate

Shared staging, end-to-end, recovery/reconciliation и live production-safety evidence обязательны до production activation.

## Ограничения сессии

- Исходный код изменяет только Cursor.
- Этот чат анализирует, проектирует, проверяет и обновляет Markdown-документацию.
- Все изменения выполняются по Minimal Change без несвязанного рефакторинга.
