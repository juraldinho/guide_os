# Guide OS Mini App — UX Prototype (MA2)

High-fidelity disposable clickable prototype on mock data. Not production frontend.

## Status

**MA2 high-fidelity prototype** — pending owner visual review.

## Open locally

```sh
open miniapp/prototype/index.html
```

Or serve statically (no build required):

```sh
python3 -m http.server 8765 --directory miniapp/prototype
```

Then open `http://localhost:8765/`.

## Theme demo

Prototype includes a **demonstration-only** theme control in Settings → **Тема (демо)**:

- **Как в Telegram** — follows OS `prefers-color-scheme` (default)
- **Светлая** / **Тёмная** — force light or dark semantic tokens

Selection is stored in `sessionStorage` for the current browser tab only.

Production Mini App will use `Telegram.WebApp.colorScheme` and `Telegram.WebApp.themeParams`. Telegram SDK is **not** connected in this prototype.

## Viewports to check manually

- 320 px (narrow iPhone)
- 390 px (iPhone)
- 430 px (wider Android)
- Telegram Desktop width (~480 px max content)

Verify: no horizontal scroll, readable light/dark, touch targets ~44×44 px, bottom nav does not hide primary actions.

## Logo

`assets/logo.svg` is an exact copy of the official Tourism OS marketing file (`marketing tourism os/logo/logo.svg`). Geometry, colors and text are unchanged.

## Scope (unchanged from MA1)

- Calendar: 8-day vertical feed, expandable month picker, day detail, add tour/day off, forms, conflicts
- Tour card: edit / copy / delete
- Reports: bot-style period stats (month/year/all-time), filters, free dates overlay + copy
- Settings: profile, Telegram ID, types/geography, notifications
- Loading, empty, error, offline demo states

## Mock scenario

- Today: **28 August 2026**
- Existing tour: **Обзорный Самарканд**, Silk Road Travel, 09:00–14:00, Бронь, $100, Не оплачено
- Add tour on the same day with **12:00–16:00** to see blocking time conflict

## Constraints

- No dependencies, no network requests, no backend/API/auth
- Russian UI, USD only
- Prototype-only — do not scaffold production frontend until MA2 is approved
