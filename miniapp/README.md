# Guide OS Mini App — Frontend (MA3 complete)

React + TypeScript + Vite scaffold with mock data. All approved MA2 MVP flows ported to React.

## Status

**MA3 complete** — Calendar, Reports («Итоги»), Settings, free-dates overlay, and demo system states on mocks. Next: **MA4** (Web API + shared services).

## Quick start

```sh
cd miniapp
npm install
npm run dev
```

Open `http://localhost:5173/`.

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Vite dev server |
| `npm run build` | Typecheck + production build |
| `npm run preview` | Preview production build |
| `npm test` | Vitest unit/component tests |

## MVP flows in React (mock-only)

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
- Income = overlapping days × daily rate; unique working days
- «Поделиться свободными датами» → shared free-dates overlay

### Free-dates overlay (Calendar + Reports)

- Context from opener: calendar month or reports period (snapshotted `availOpenFrom`)
- Modes: automatic context vs custom date range
- Only fully free dates; preview + copy + empty state

### Settings (gear icon)

- Profile name, Telegram ID + copy
- Guide types + geography (read-only cards from mock profile)
- Notifications toggle + reminder time
- Theme demo: Как в Telegram / Светлая / Тёмная (`sessionStorage` + `mockAdapter`)
- Link to demo UI states; language/about stubs

### Demo system states (Settings → dev section)

- Loading (auto-clear 2s), error, offline screens for manual QA
- Dev-only; not enabled in production paths

## Mock scenario

- Today: **28 August 2026** (`MOCK_TODAY` in `src/config.ts`)
- Existing tour: **Обзорный Самарканд** 09:00–14:00
- Add tour on same day with **12:00–16:00** to trigger blocking time conflict

## Architecture

```text
src/
├── app/              # AppShell, GlobalOverlays, DemoScreens
├── features/
│   ├── calendar/     # Calendar UI + lib
│   └── reports/      # ReportsPage, free-dates, lib (summary, periods, availability)
├── features/settings/# SettingsOverlay, DemoStatesOverlay
├── components/       # Shared layout + UI (Chip, OverlaySheet, Toast)
├── api/              # Types, mock client/store
├── telegram/         # Mock theme adapter
├── i18n/             # RU strings
└── styles/           # tokens.css + global.css
```

- **No network** — `api/mock/store.ts` in-memory data
- **No Telegram SDK** — `telegram/mockAdapter.ts` stubs theme
- **prototype/** left unchanged as disposable MA2 reference

## Tests

```sh
npm test
```

Covers conflicts, feed smoke, `calcSummary`/report ranges, `buildFreeDatesText` headings, Reports metric labels.

## Constraints

- Russian UI, USD only
- Do not use for production until Web API integration (MA4)
- Official logo: `public/assets/logo.svg`
