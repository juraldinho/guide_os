# Guide OS Mini App — Next Task

> Обновлено: 2026-09-03

## Единственная следующая задача

**GSMA9 — security matrix and full regression.**

GSMA8 complete (timeouts/cancellation, safe GET retry, sanitized logs, isolation, rollback runbook). GuideShop sales remain withdrawn from Mini App. Do not start GSMA9 coding until the owner explicitly asks.

Канонический план GSMA0–GSMA10: [`../../docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`](../../docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md).

Rollback/resilience runbook: [`../../docs/mini_app/GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md`](../../docs/mini_app/GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md).

Канонический contract GSMA7: [`../../docs/mini_app/GUIDESHOP_SUBMODULES_CONTRACT_GSMA7.md`](../../docs/mini_app/GUIDESHOP_SUBMODULES_CONTRACT_GSMA7.md).

GSMA9 focus (from roadmap): security review / threat matrix for Mini App GuideShop surfaces; full targeted + broader regression — only when owner requests.

## Утверждённый будущий roadmap — Google Calendar

Владелец утвердил будущую одностороннюю интеграцию `Google Calendar → Guide OS`, включая преобразование импортированного события в полноценный тур после дополнения стоимости и других полей. Реализация не начата и не является активной задачей до отдельной команды владельца.

Канонический поэтапный план GC0–GC13: [`../../docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md`](../../docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md).

## Утверждённый будущий roadmap — чаевые

Владелец утвердил bot-first функцию дневных чаевых: одна общая сумма на пользователя и календарную дату, независимо от туров; сначала Telegram bot, затем общий Web API и Mini App. Реализация не начата и не является активной задачей до отдельной команды владельца.

Канонический план TIP0–TIP10: [`../../docs/TIPS_ROADMAP.md`](../../docs/TIPS_ROADMAP.md).

## Public production pilot — ACTIVE

Public production pilot remains owner-validated and active. Do not disable pilot, redeploy, or flip production flags without a new explicit owner request. Rollback remains reversible via `MINI_APP_ENABLED=false` (+ `MINI_APP_API_ENABLED=false` if needed).
