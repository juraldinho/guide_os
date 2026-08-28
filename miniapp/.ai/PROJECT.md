# Guide OS Mini App — Project State

> Обновлено: 2026-08-29

## Статус

Этап **MA3 complete** на mocks. **MA4 complete** (contract + shared services). **MA5 complete** (`web_api/` transport). **MA6 complete** (initData auth + session tokens). **MA7** React HTTP client — не начато.

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

Mini App target:

```text
frontend -> Web API -> те же services -> database
```

GuideShop remains optional read-only through existing Guide OS client.

## Critical constraints

- не менять production или действующий bot на mock/prototype stages;
- не создавать вторую calendar business logic;
- не давать frontend direct DB/GuideShop access;
- не доверять frontend user ID/initDataUnsafe;
- не запускать два независимых SQLite writers на одном volume;
- staging полностью изолирован;
- production feature default off до отдельного gate.

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
- Wireframes/Figma: not started.
- Frontend manifest/source/tests: present in `miniapp/` (mocks only).
- Web API: present (`web_api/`, `guide_os_miniapp_api.py`; feature flag off by default).
- Telegram Mini App auth: initData validation + SQLite sessions (MA6); dev stub gated by flag.
- Time/daily-location schema: present (MA4 migrations).
- Staging Mini App bot/deployment: absent.

## Scope discipline

Start only the task in `NEXT_TASK.md`. Update this file when actual project state changes, not for speculative plans.
