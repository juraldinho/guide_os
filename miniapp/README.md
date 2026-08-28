# Guide OS Mini App

React frontend + disposable MA2 prototype + Web API backend (MA0–MA5 complete). Telegram-бот не изменён; production rollout не включён.

## Status (2026-08-29)

| Этап | Статус | Описание |
|------|--------|----------|
| MA0 | ✅ | Product docs, DECISIONS, AGENTS |
| MA1 | ✅ | Low-fi UX prototype |
| MA2 | ✅ | High-fi prototype (owner approved) |
| MA3 | ✅ | React + Vite, all MVP screens on **mocks** |
| MA4 | ✅ | Shared services + DB migrations + API contract docs |
| MA5 | ✅ | `web_api/` transport (`guide_os_miniapp_api.py`, dev auth stub) |
| **MA6** | ⏳ | Telegram initData session auth |
| **MA7** | ⏳ | React HTTP client → API |

## Quick start — React UI (mocks)

```sh
cd miniapp
npm install
npm run dev
```

Open `http://localhost:5173/` (or next free port if 5173 is busy).

```sh
npm test
npm run build
```

## Quick start — Web API (optional, dev auth)

```sh
# from repo root
MINI_APP_API_ENABLED=true MINI_APP_API_DEV_AUTH=true python guide_os_miniapp_api.py
```

```sh
curl -X POST http://127.0.0.1:8083/app/v1/session \
  -H 'Content-Type: application/json' \
  -d '{"dev_user_id":123}'
```

Feature flag **`MINI_APP_API_ENABLED=false`** in `.env.example` by default.

## MVP flows in React (mock-only until MA7)

### Calendar

- 8-day feed from `MOCK_TODAY`, expandable month picker, day detail screen
- Add tour / day off, date warning, blocking time conflict with return to form
- Tour card: edit, copy, delete; multi-day location sheet
- Day detail: «Поделиться свободными датами»

### Reports («Итоги»)

- Period: month / year / «За весь период» with prev/next navigation
- Current year ends at `MOCK_TODAY` (2026-08-28); no future years
- Filter chips: status (Все/Бронь/Занято), payment (Все/Оплачено/Не оплачено)
- Five metrics: туров, рабочих дней, доход ($), оплаченных/неоплаченных туров
- «Поделиться свободными датами» → shared free-dates overlay

### Settings, free-dates, demo states

- Profile, Telegram ID copy, types/geography (mock), notifications, theme demo
- Free-dates overlay: context snapshot + custom range (local state, live preview)
- Demo loading / error / offline screens (dev QA only)

## Architecture

```text
Telegram Mini App (miniapp/src/)     [mocks until MA7]
        |
        |  future: HTTPS + session
        v
Guide OS Web API (web_api/)          [MA5, flag off]
        |
        v
shared services (MA4)
  tour_service, reports_service, availability_service
        |
        v
Guide OS SQLite
```

```text
miniapp/
├── src/              # React app (MA3)
├── prototype/        # MA2 disposable HTML reference
├── tests/            # Vitest
├── public/           # logo.svg
└── package.json

web_api/              # aiohttp /app/v1 (MA5)
guide_os_miniapp_api.py
```

## Mock scenario

- Today: **28 August 2026** (`MOCK_TODAY` in `src/config.ts`)
- Existing tour: **Обзорный Самарканд** 09:00–14:00
- Add tour same day **12:00–16:00** → blocking time conflict

## Documentation

- [AGENTS.md](AGENTS.md) — правила для AI-агентов
- [GuideOS_miniapp_Development_Operating_System.md](GuideOS_miniapp_Development_Operating_System.md) — продукт и roadmap
- [GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md](GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md) — интеграция и auth
- [docs/mini_app/API_CONTRACT_v1.md](../docs/mini_app/API_CONTRACT_v1.md) — HTTP contract
- [docs/mini_app/SERVICE_GAP_ANALYSIS_MA4.md](../docs/mini_app/SERVICE_GAP_ANALYSIS_MA4.md) — service mapping
- [.ai/NEXT_TASK.md](.ai/NEXT_TASK.md) — следующая задача (MA6)
- [prototype/README.md](prototype/README.md) — MA2 HTML prototype

## Constraints

- Russian UI, USD only
- Bot handlers unchanged; parallel development
- No production Mini App until staging gate (MA10+)
- Official logo: `public/assets/logo.svg` (viewBox cropped for header)
