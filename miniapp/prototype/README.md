# Guide OS Mini App — UX Prototype (MA2)

High-fidelity **disposable** clickable prototype on mock data. **Not** the production frontend — use `miniapp/src/` (MA3 React app) for active development.

## Status

**MA2 approved**. Reference only — active UI: `miniapp/src/`. Backend: `web_api/` (MA5–MA6).

## Open locally

```sh
open miniapp/prototype/index.html
```

Or serve statically:

```sh
python3 -m http.server 8765 --directory miniapp/prototype
```

Then open `http://localhost:8765/`.

## Theme demo

Settings → **Тема (демо)**: Как в Telegram / Светлая / Тёмная (`sessionStorage`). Production will use `Telegram.WebApp.colorScheme`.

## Scope

- Calendar: 8-day feed, expandable month picker, day detail, add tour/day off, forms, conflicts
- Tour card: edit / copy / delete
- Reports: bot-style period stats (5 metrics), filters, free dates overlay + copy
- Settings: profile, Telegram ID, types/geography, notifications
- Loading, empty, error, offline demo states

## Logo

`assets/logo.svg` — official Tourism OS SVG; viewBox cropped for header optical size (paths unchanged).

## Mock scenario

- Today: **28 August 2026**
- Tour: **Обзорный Самарканд** 09:00–14:00; demo overlap **12:00–16:00**

## Constraints

- No dependencies, no network, no backend
- Do not edit for new features — port changes to `miniapp/src/` instead
