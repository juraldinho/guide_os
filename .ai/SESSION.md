# Guide OS — Current Development Session

> Обновлено: 2026-08-07

## Текущий фокус

Подготовка Guide OS routes и Telegram-safe navigation foundation до создания GuideShop UI.

## Завершённые этапы

- Stage 0 — закрыт Product Owner;
- Stage 1A — stable UUID4 `guide_os_id`;
- Stage 1B — secure one-time linking requests;
- Stage 2A — strict DTO/event contract baseline;
- Stage 3A — default-off flags и mockable read-only client boundary.

## Проверенное состояние

- integration flags выключены по умолчанию;
- disabled/fake clients не выполняют сеть или SQLite;
- fake возвращает только валидированные DTO;
- production factory не использует fake fallback;
- Stage 3A: `27 passed`;
- Stage 1/2 regression: `53 passed`;
- full suite: `112 passed`;
- реальный HTTP client и Telegram integration UI отсутствуют.

## Следующее действие

Stage 3B согласно `.ai/NEXT_TASK.md`: typed internal routes и user-bound navigation tokens.

## Открытые решения

1. Service authentication: OAuth2 client credentials или signed JWT.
2. Event delivery: webhook endpoint или очередь.
3. Retention для linking/navigation requests, event inbox/outbox и audit log.
4. Формальное сопоставление DTO с GuideShop OpenAPI/JSON Schema.
5. Финальный TTL и single-use policy для notification deep links.

## Production gate

Shared staging, end-to-end, recovery/reconciliation и live production-safety evidence обязательны до production activation.

## Ограничения сессии

- Исходный код изменяет только Cursor.
- Этот чат анализирует, проектирует, проверяет и обновляет Markdown-документацию.
- Все изменения выполняются по Minimal Change без несвязанного рефакторинга.
