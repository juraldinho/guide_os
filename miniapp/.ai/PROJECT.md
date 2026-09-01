# Guide OS Mini App — Project State

> Обновлено: 2026-09-01

## Статус

Этапы **MA0–MA10** — завершённые исторические этапы. **MA9** complete (staging smoke + production gate docs). **MA10** complete — local Telegram E2E PASS (2026-08-30). Post-MA10 UX checkpoint complete (2026-08-31).

**Public production pilot — ACTIVE, owner-validated** (2026-09-01). Mini App доступен через production Guide OS bot (`MenuButtonWebApp`). Owner explicitly approved leaving pilot enabled. **Formal general production release** not separately declared.

**MA11** hosted closed staging — **not** the active next step; owner authorized reversible public production pilot instead. **No active coding/deployment task** — next step defined by owner only.

Не описывать планируемую архитектуру как существующий код.

## Цель

Создать быстрый профессиональный календарь туристического гида внутри Telegram. Главный сценарий `проверить дату → добавить тур` должен занимать 10–15 секунд.

## Утверждено

- пользователь — только гид;
- бот и Mini App — равноценные интерфейсы общих данных;
- две вкладки: `Календарь`, `Итоги`;
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
