# Guide OS — Current Development Session

> Обновлено: 2026-08-09

## Текущий фокус

Подготовка реального read-only GuideShop API client без production activation.

## Завершённые этапы

- Stage 0;
- Stage 1A/1B — identity и linking requests;
- Stage 2A — DTO/event contract;
- Stage 3A — flags/client boundary;
- Stage 3B — navigation tokens;
- Stage 3C1 — presentation/keyboards;
- Stage 3C2 — feature-gated mock Telegram UI.
- Stage 3D — user-bound `/start` deep links и development smoke helper.

## Проверенное состояние

- callbacks и `/start` deep links user-bound и single-use;
- GuideShop deep-link handler не перехватывает обычный `/start`;
- development helper не доступен через Telegram и запрещён вне development;
- Stage 3D/helper regression: `58 passed`;
- full suite: `278 passed`;
- ручной smoke test в `@Guideosbot` успешен.

## Следующее действие

Stage 4A согласно `.ai/NEXT_TASK.md`: authenticated read-only HTTP client foundation, default-off и без production activation.

## Production gate

GuideShop API, shared staging, E2E, recovery и live production-safety evidence обязательны до production activation.

## Ограничения сессии

- Исходный код изменяет только Cursor.
- Этот чат анализирует, проектирует, проверяет и обновляет Markdown.
- Minimal Change; никаких несвязанных изменений.
