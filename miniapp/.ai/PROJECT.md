# Guide OS Mini App — Project State

**Owner validation — 2026-10-29:** владелец сообщил, что ручная проверка закрыта: функция работает корректно. Functional manual validation считается **PASS по подтверждению владельца**; это не новый автоматический прогон и не отдельная аттестация каждого устройства. По прямому поручению владельца агент выполняет Git commit/push и production source-pin alignment; статус операции обновляется в `docs/REMINDER_MINIAPP_LINK.md`.

**Release update 2026-10-29:** Чаевые Mini App-first выпущены в production 2026-10-27; «Открыть в приложении» в новых напоминаниях — 2026-10-29. Текущие production deployments: backend `5dd8037d-97e8-48ad-890a-c04cb0cb6683`, frontend `3d307e26-3378-4171-8f13-aa6fa7e3379c`. Technical smoke прошёл; functional manual validation закрыта владельцем 2026-10-29. Релизы выполнены из изолированных артефактов; Git HEAD остаётся `24b3cad`, старые source pins не включают новые функции. Текущая задача: по прямому поручению владельца агент выполняет Git/source alignment перед новой выкладкой из Git. Новая coding-задача не активирована.

> Сводка обновлена 2026-10-29 по записанным release evidence: [реализация и окружения](../../docs/CURRENT_STATE.md). Исторические PASS относятся к своим датам; эта docs-правка не является новым live-аудитом.

> Обновлено: 2026-10-29

## Статус

Этапы **MA0–MA10** — завершённые исторические этапы. **MA9** complete (staging smoke + production gate docs). **MA10** complete — local Telegram E2E PASS (2026-08-30). Post-MA10 UX checkpoint complete (2026-08-31).

**Public production pilot — ACTIVE, owner-validated** (2026-09-01). Mini App доступен через production Guide OS bot (`MenuButtonWebApp`). Owner explicitly approved leaving pilot enabled. **Formal general production release** not separately declared.

**MA11** hosted closed staging — **not** the active next step; owner authorized reversible public production pilot instead.

**GuideShop GSMA0–GSMA10 complete for the public pilot**; no active GuideShop coding task. Guide Operator is the fourth module with consent, assignments, version decisions and protected calendar projections. Canonical plan: `../../docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`.

**Google Calendar** утверждён как будущий отдельный workstream: read-only import в Guide OS с последующим ручным преобразованием external event в полноценный native tour. Реализация не начата. Канонический план: `../../docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md`.

**Дневные чаевые**: Mini App-first; staging 2026-10-22 и production 2026-10-27. Одна сумма пользователя/даты, replace/zero-delete, общий backend/API и отдельные tips/totalEarnings в Итогах. Telegram bot tips UX/statistics отложены. План: `../../docs/TIPS_ROADMAP.md`.

Не описывать планируемую архитектуру как существующий код.

## Цель

Создать быстрый профессиональный календарь туристического гида внутри Telegram. Главный сценарий `проверить дату → добавить тур` должен занимать 10–15 секунд.

## Утверждено

- пользователь — только гид;
- бот и Mini App — равноценные интерфейсы общих данных;
- четыре вкладки: `Календарь`, `Итоги`, `GuideShop`, `Guide Operator`;
- настройки через шестерёнку;
- day/week/month;
- tour/day off;
- single/multi-day;
- optional start/end time;
- non-overlap same day допустим, overlap блокируется;
- legacy/no-time tour считается full-day;
- status `reserved/confirmed`;
- payment `paid/unpaid`;
- USD и русский язык;
- reports, filters, free-date client text;
- copy text with fully free dates only;
- guide types/geography and visible Telegram ID;
- Telegram-driven theme;
- official logo without redraw.

Полный record: `../../docs/mini_app/DECISIONS.md`.

## Текущая архитектура Guide OS

Действующий бот:

```text
handlers -> services -> database
```

Production Mini App (pilot):

```text
hosted frontend -> production Web API -> те же services -> production database
```

Production bot и Mini App используют общий Guide OS data layer. Two-account isolation validated in production pilot (2026-09-01).

GuideShop remains optional read-only through existing Guide OS client.

## Critical constraints

- не создавать вторую calendar business logic;
- не давать frontend direct DB/GuideShop access;
- не доверять frontend user ID/initDataUnsafe;
- не запускать два независимых SQLite writers на одном volume;
- staging и production изолированы;
- public production pilot reversible via feature flags — rollback only on owner request;
- formal production gate docs retained — not a claim every gate item is complete.

## Canonical documents

1. `../AGENTS.md`
2. `../GuideOS_miniapp_Development_Operating_System.md`
3. `../GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md`
4. `../../docs/mini_app/DECISIONS.md`
5. `NEXT_TASK.md`
6. `../../docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md` — future Google Calendar stages GC0–GC13
7. `../../docs/TIPS_ROADMAP.md` — future tips stages TIP0–TIP10
8. `../../docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md` — active GuideShop Mini App stages GSMA0–GSMA10

## Current implementation inventory

- Product docs: present.
- Mini App AGENTS: present.
- Official external SVG source: present in Tourism OS marketing folder.
- Frontend manifest/source/tests: present in `miniapp/` (mock default locally; production hosted frontend operating in pilot).
- Web API: present (`web_api/`, `guide_os_miniapp_api.py`); **operating in production pilot** with real initData auth.
- Telegram Mini App auth: initData validation + SQLite sessions; dev stub gated by flag (not production path).
- Time/daily-location schema: present (MA4 migrations).
- Production Mini App frontend + API + auth: **present and owner-validated in public pilot**.
- Production bot `MenuButtonWebApp`: **enabled** (owner-approved pilot).
- Two-account data isolation: **validated** in production pilot.
- Hosted closed staging (MA11): not the active deployment path; separate staging stack may exist historically but pilot runs on production bot.

## Scope discipline

Start only the task in `NEXT_TASK.md`. Update this file when actual project state changes, not for speculative plans.
