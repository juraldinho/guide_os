# Guide OS Mini App — продуктовая и архитектурная документация

Текущий release 2026-10-29: чаевые и переход из новых напоминаний в точную карточку работают в production. [Технические проверки и текущие deployment IDs](../REMINDER_MINIAPP_LINK.md). Manual Telegram E2E и owner Git/source alignment остаются отдельными follow-up.

> Сводка обновлена 2026-10-29 по записанным release evidence: [реализация и окружения](../CURRENT_STATE.md). Исторические PASS относятся к своим датам; эта docs-правка не является новым live-аудитом.

> **Статус: MA0–MA10 и GSMA0–GSMA10 complete**. Public pilot owner-validated; Guide Operator staging closure recorded. Новый rollout требует отдельной авторизации.

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

Bot и Mini App используют shared services/database. Public pilot ранее оставлен включённым владельцем; это не разрешение на Guide Operator production rollout.

## Связанные документы

- [`../../miniapp/.ai/NEXT_TASK.md`](../../miniapp/.ai/NEXT_TASK.md) — актуальный следующий scope
- [`../../miniapp/README.md`](../../miniapp/README.md) — quick start
- [`GOOGLE_CALENDAR_ROADMAP.md`](GOOGLE_CALENDAR_ROADMAP.md) — утверждённая будущая односторонняя интеграция Google Calendar; реализация не начата
- [`../TIPS_ROADMAP.md`](../TIPS_ROADMAP.md) — выпущенные Mini App-first чаевые: production 2026-10-27; bot UX отложен
- [`GUIDESHOP_MINIAPP_ROADMAP.md`](GUIDESHOP_MINIAPP_ROADMAP.md) — завершённые GSMA0–GSMA10 для public pilot
