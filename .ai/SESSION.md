# Guide OS — Current Development Session

> Обновлено: 2026-08-09

## Текущий фокус

Подключение mock-backed GuideShop presentation к локальному Telegram UX через default-off feature gate.

## Завершённые этапы

- Stage 0 — закрыт Product Owner;
- Stage 1A — stable UUID4 identity;
- Stage 1B — secure linking requests;
- Stage 2A — strict DTO/event contract;
- Stage 3A — flags и mockable client boundary;
- Stage 3B — typed routes и navigation tokens;
- Stage 3C1 — presentation layer и tokenized keyboards.

## Проверенное состояние

- HTML external values экранируются;
- Decimal values не пересчитываются;
- list buttons различимы без object IDs;
- callbacks содержат только `gs_` tokens;
- navigation suite: `50 passed`;
- UI suite: `18 passed`;
- full suite: `180 passed`;
- handlers/main menu ещё не подключены.

## Следующее действие

Stage 3C2 согласно `.ai/NEXT_TASK.md`: feature-gated handler, menu entry и callback dispatch.

## Открытые решения

1. Service authentication: OAuth2 client credentials или signed JWT.
2. Event delivery: webhook endpoint или очередь.
3. Общая retention policy для temporary/audit rows.
4. Формальное сопоставление DTO с GuideShop OpenAPI/JSON Schema.
5. Реальный staging client composition после подготовки GuideShop API.

## Production gate

Shared staging, end-to-end, recovery/reconciliation и live production-safety evidence обязательны до production activation.

## Ограничения сессии

- Исходный код изменяет только Cursor.
- Этот чат анализирует, проектирует, проверяет и обновляет Markdown-документацию.
- Все изменения выполняются по Minimal Change без несвязанного рефакторинга.
