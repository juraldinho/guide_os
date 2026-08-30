# Guide OS Mini App — продуктовая и архитектурная документация

> **Статус: MA0–MA10 complete** (2026-08-30). Следующий: **MA11** (hosted closed staging — deferred until owner approval).

Канонический корень Mini App: [`../../miniapp/`](../../miniapp/README.md).

## Что реализовано

| Слой | Статус | Где |
|------|--------|-----|
| Product docs + DECISIONS | ✅ | эта папка + `miniapp/` |
| MA2 HTML prototype | ✅ | `miniapp/prototype/` |
| React UI | ✅ | `miniapp/src/` (mock default; HTTP MA7–MA8) |
| Shared services | ✅ | `services/*_service.py` |
| Web API `/app/v1` | ✅ | `web_api/` |
| Telegram initData auth | ✅ | MA6 |
| React → API | ✅ | MA7–MA8 |

Telegram-бот (handlers) **не изменён**. Production rollout **выключен**.

## Связанные документы

- [`../../miniapp/.ai/NEXT_TASK.md`](../../miniapp/.ai/NEXT_TASK.md) — **MA11** (deferred)
- [`../../miniapp/README.md`](../../miniapp/README.md) — quick start
