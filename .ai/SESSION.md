# Guide OS — Current Development Session

> Обновлено: 2026-08-07

## Текущий фокус

Подготовка Guide OS к будущей интеграции с GuideShop до начала изменений GuideShop.

## Текущий этап

Stage 1 завершён на стороне Guide OS:

- Stage 1A — stable `guide_os_id`: завершён;
- Stage 1B — secure temporary linking requests: завершён;
- следующий этап — Stage 2A, Guide OS-side contract и mock payloads.

## Проверенное состояние

- Stage 0 закрыт Product Owner;
- stable identity использует UUID4;
- raw linking tokens не сохраняются;
- linking token TTL — 10 минут UTC;
- atomic consume учитывает status и expiration;
- Stage 1B tests: `8 passed`;
- Stage 1A tests: `5 passed`;
- full suite: `45 passed`;
- GuideShop, HTTP API, Telegram integration UI и события ещё не подключены.

## Следующее действие

Подготовить Cursor Prompt для Stage 2A согласно `.ai/NEXT_TASK.md`.

## Открытые решения

1. Service authentication: OAuth2 client credentials или signed JWT.
2. Event delivery: webhook endpoint или очередь.
3. Retention для link requests, event inbox/outbox и audit log.
4. Правило отображения corrected/reversed points.
5. Право принудительного unlink/relink.

## Production gate

Shared staging, end-to-end, recovery/reconciliation и live production-safety evidence обязательны до production activation. Завершение Stage 1 не является разрешением production rollout.

## Ограничения сессии

- Исходный код изменяет только Cursor.
- Этот чат анализирует, проектирует, проверяет и обновляет Markdown-документацию.
- Все изменения выполняются по Minimal Change без несвязанного рефакторинга.
