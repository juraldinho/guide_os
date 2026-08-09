# Guide OS — Current Development Session

> Обновлено: 2026-08-07

## Текущий фокус

Подготовка feature-gated Telegram GuideShop UI на mock data без реального GuideShop connection.

## Завершённые этапы

- Stage 0 — закрыт Product Owner;
- Stage 1A — stable UUID4 `guide_os_id`;
- Stage 1B — secure one-time linking requests;
- Stage 2A — strict DTO/event contract baseline;
- Stage 3A — default-off flags и mockable client boundary;
- Stage 3B — typed routes и user-bound navigation tokens.

## Проверенное состояние

- navigation token: `gs_...`, 35 символов, 192 bits entropy;
- raw token и public route payload не сохраняются;
- TTL 24 часа, atomic single-use consume;
- cross-user resolution безопасно отклоняется;
- Stage 3B: `50 passed`;
- previous integration regression: `80 passed`;
- full suite: `162 passed`;
- Telegram integration UI и реальный HTTP client отсутствуют.

## Следующее действие

Stage 3C согласно `.ai/NEXT_TASK.md`: feature-gated Telegram entry и mock-backed screens.

## Открытые решения

1. Service authentication: OAuth2 client credentials или signed JWT.
2. Event delivery: webhook endpoint или очередь.
3. Retention для linking/navigation requests, event inbox/outbox и audit log.
4. Формальное сопоставление DTO с GuideShop OpenAPI/JSON Schema.
5. Финальная UX-политика TTL/single-use для notification deep links.

## Production gate

Shared staging, end-to-end, recovery/reconciliation и live production-safety evidence обязательны до production activation.

## Ограничения сессии

- Исходный код изменяет только Cursor.
- Этот чат анализирует, проектирует, проверяет и обновляет Markdown-документацию.
- Все изменения выполняются по Minimal Change без несвязанного рефакторинга.
