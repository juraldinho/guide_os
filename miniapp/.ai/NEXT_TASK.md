# Guide OS Mini App — Next Task

> Обновлено: 2026-09-03

## Единственная следующая задача

**GSMA8 — resilience, caching и observability.**

GSMA7 optional submodules are complete (Visits with visit-detail points, Points summary, Payout/history). **GuideShop sales withdrawn from Mini App** by owner. Do not add further GuideShop submodule screens unless owner reopens scope.

Канонический план GSMA0–GSMA10: [`../../docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`](../../docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md).

Канонический contract GSMA7: [`../../docs/mini_app/GUIDESHOP_SUBMODULES_CONTRACT_GSMA7.md`](../../docs/mini_app/GUIDESHOP_SUBMODULES_CONTRACT_GSMA7.md).

GSMA8 focus (from roadmap):

- request timeout and cancellation;
- safe short-lived cache only if needed;
- retry without duplicate personal mutations;
- sanitized logs without JWT/tokens/opaque IDs/PII;
- metrics for latency/error/degraded state;
- GuideShop outage isolated to official section;
- feature flags and rollback runbook.

Do **not** start GSMA8 coding until the owner explicitly asks for that task.

## Утверждённый будущий roadmap — Google Calendar

Владелец утвердил будущую одностороннюю интеграцию `Google Calendar → Guide OS`, включая преобразование импортированного события в полноценный тур после дополнения стоимости и других полей. Реализация не начата и не является активной задачей до отдельной команды владельца.

Канонический поэтапный план GC0–GC13: [`../../docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md`](../../docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md).

## Утверждённый будущий roadmap — чаевые

Владелец утвердил bot-first функцию дневных чаевых: одна общая сумма на пользователя и календарную дату, независимо от туров; сначала Telegram bot, затем общий Web API и Mini App. Реализация не начата и не является активной задачей до отдельной команды владельца.

Канонический план TIP0–TIP10: [`../../docs/TIPS_ROADMAP.md`](../../docs/TIPS_ROADMAP.md).

## Public production pilot — ACTIVE

**Guide OS Mini App public production pilot — ACTIVE and owner-validated** (2026-09-01).

Do not treat pilot as incomplete unless the owner reopens it.

## Do not

- No GuideShop writes; no official↔personal merge.
- No bot/handler/schema/Railway/production flag changes without release scope.
- Do not mix GuideShop USD sales or PTS with personal commission money/points.
- Do not start GSMA8 until owner requests it.
