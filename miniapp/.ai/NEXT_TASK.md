# Guide OS Mini App — Next Task

> Обновлено: 2026-09-04

## Единственная следующая задача

**Нет активной GuideShop Mini App coding-задачи.**

GSMA0–GSMA10 complete for the current public production **pilot**. Owner two-account E2E: **PASS** (2026-09-04, sanitized record in [`../../docs/mini_app/GUIDESHOP_MINIAPP_E2E_GSMA10.md`](../../docs/mini_app/GUIDESHOP_MINIAPP_E2E_GSMA10.md)).

- Public production pilot: **REMAINS ENABLED**
- Formal general Mini App release: **NOT** separately declared
- Official GuideShop data: remains **read-only**
- Mini App GuideShop sales: remain **withdrawn**

Ждать явной активации следующего roadmap владельцем. Не кодировать, не деплоить и не объявлять general release без нового запроса.

Канонический план: [`../../docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`](../../docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md).

Security matrix: [`../../docs/mini_app/GUIDESHOP_MINIAPP_SECURITY_GSMA9.md`](../../docs/mini_app/GUIDESHOP_MINIAPP_SECURITY_GSMA9.md).

Rollback: [`../../docs/mini_app/GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md`](../../docs/mini_app/GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md).

## Утверждённый будущий roadmap — Google Calendar

Владелец утвердил будущую одностороннюю интеграцию `Google Calendar → Guide OS`. Реализация не начата и **не** активируется автоматически. План: [`../../docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md`](../../docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md).

## Утверждённый будущий roadmap — чаевые

Bot-first дневные чаевые не начаты и **не** активируются автоматически. План: [`../../docs/TIPS_ROADMAP.md`](../../docs/TIPS_ROADMAP.md).

## Public production pilot — ACTIVE

Do not disable pilot, redeploy, or flip production flags without a new explicit owner request. Rollback: `MINI_APP_ENABLED=false` (+ `MINI_APP_API_ENABLED=false` if needed).
