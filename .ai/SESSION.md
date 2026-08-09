# Guide OS — Current Development Session

> Обновлено: 2026-08-09

## Текущий фокус

Подготовка request-scoped композиции GuideShop client для изоляции гидов без production activation.

## Завершённые этапы

- Stage 0;
- Stage 1A/1B — identity и linking requests;
- Stage 2A — DTO/event contract;
- Stage 3A — flags/client boundary;
- Stage 3B — navigation tokens;
- Stage 3C1 — presentation/keyboards;
- Stage 3C2 — feature-gated mock Telegram UI.
- Stage 3D — user-bound `/start` deep links и development smoke helper.
- Stage 4A — authenticated identity-bound read-only HTTP client foundation.

## Проверенное состояние

- HTTP settings fail-closed при env и direct construction;
- HTTP client использует только `/integration/v1/me/...` и Bearer auth;
- guide identity связан с экземпляром клиента и не передаётся через route;
- transient retries и response size строго ограничены;
- Stage 4A/regression: `169 passed`;
- full suite: `380 passed`.

## Следующее действие

Stage 4B согласно `.ai/NEXT_TASK.md`: request-scoped client/UI composition по доверенному `guide_os_id`.

## Production gate

GuideShop API, shared staging, E2E, recovery и live production-safety evidence обязательны до production activation.

## Ограничения сессии

- Исходный код изменяет только Cursor.
- Этот чат анализирует, проектирует, проверяет и обновляет Markdown.
- Minimal Change; никаких несвязанных изменений.
