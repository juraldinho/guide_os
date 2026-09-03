# Guide OS Mini App — Development Log

Краткий append-only журнал завершённых Mini App stages. Не копировать сюда длинные prompts, terminal output, secrets, commit hashes или speculative plans.

## 2026-09-03 — Owner UX: hide GuideShop sales + visit detail points

- Removed Mini App «Продажи GuideShop» UI/API/client exposure (routes unregistered); bot sales unchanged;
- Visit detail includes GuideShop `points[]` (amount/unit/status) via `list_points(visit_id)` parity with bot;
- Personal commissions untouched; GSMA8 not started.

## 2026-09-03 — GSMA7E Official GuideShop Payout / History

- Web API `GET /app/v1/guideshop/history` (list-only) via shared Mini App GuideShop provider;
- entry from Points sheet «История выплат»; company-scoped PTS payout list; GuideShop badge;
- no mix with personal commission history; no GuideShop writes;
- GSMA7 optional submodule set complete (visits, points summary, sales, history);
- bot, schema, Railway и production flags не изменялись.

## 2026-09-03 — GSMA7D Official GuideShop Sales (list + detail)

- Web API `GET /app/v1/guideshop/sales` + `/{saleId}` via shared Mini App GuideShop provider;
- official company detail entry «Продажи GuideShop»; USD decimal strings; company-scoped filter; no mix with personal commissions;
- payout/history not implemented;
- bot, schema, Railway и production flags не изменялись.

## 2026-09-03 — GSMA7C Official GuideShop Points summary

- Web API `GET /app/v1/guideshop/points/summary` via shared Mini App GuideShop provider;
- official company detail entry «Баллы GuideShop»; PTS totals + company-scoped row; no mix with personal commissions;
- accruals list / sales / payout history not implemented;
- bot, schema, Railway и production flags не изменялись.

## 2026-09-03 — GSMA7B Official GuideShop Visits (list + detail)

- Web API `GET /app/v1/guideshop/visits` + `/{visitId}` via shared Mini App GuideShop provider;
- official company detail entry “Визиты”; company-scoped client-side filter; GuideShop badge; no mutations;
- sales / points / history not implemented;
- bot, schema, Railway и production flags не изменялись.

## 2026-09-03 — GSMA7A Official GuideShop submodules contract (docs only)

- inventory of existing GuideShop client visits/sales/points/history methods and DTOs;
- proposed `/app/v1/guideshop/...` composition endpoint names (not implemented);
- per-submodule product analysis; recommended first slice: visits;
- owner must pick exactly one submodule before GSMA7B coding;
- application code, schema, Railway и production не изменялись.

## 2026-09-02 — Future Google Calendar roadmap approved (not implemented)

- утверждён one-way import `Google Calendar → Guide OS`;
- external event показывается как заготовка и блокирует занятость без дохода/statistics;
- пользователь может дополнить запись и сохранить через общий `tour_service` как полноценный тур;
- преобразованный тур не перезаписывается и не удаляется автоматически источником;
- Apple/iCloud и обратная запись в Google исключены из первого scope;
- GC0–GC13 зафиксированы в `docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md`;
- код, schema, OAuth, Railway и production не изменялись.

## 2026-09-02 — Future tips roadmap approved (not implemented)

- утверждена одна сумма чаевых на пользователя и календарную дату, отдельно от tours/daily income;
- чаевые можно добавить в любой день; multi-day, day off, copy/delete tour на них не влияют;
- порядок реализации: shared foundation → Telegram bot → bot validation → Web API → Mini App → E2E;
- отчёты должны разделять доход от туров, чаевые и общий доход;
- payments/эквайринг, разные валюты и GuideShop mutations вне scope;
- TIP0–TIP10 зафиксированы в `docs/TIPS_ROADMAP.md`;
- код, schema, Railway и production не изменялись.

## 2026-09-02 — GuideShop Mini App workstream activated (GSMA0 docs)

- утверждён третий нижний раздел после Calendar/Reports и масштабируемая horizontal nav;
- official GuideShop companies остаются read-only;
- personal companies/commissions переиспользуют существующие personal-place services/data;
- зафиксированы этапы GSMA0–GSMA10 в `docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`;
- активный следующий этап — GSMA0 audit/contract;
- application code, schema, API, Railway и production не изменялись.

## 2026-08-28 — MA0 product discovery completed

- определена основная формулировка: быстрый профессиональный календарь гида;
- подтверждён только guide user scope;
- утверждены Calendar/Reports navigation и settings entry;
- определены tour, time, conflict, multi-day, income, availability, profile и notification rules;
- зафиксирован Russian/USD MVP;
- утверждено сочетание Professional Minimal + Telegram Native + restrained tourism accents;
- решения записаны в `docs/mini_app/DECISIONS.md`.

## 2026-08-28 — MA0 documentation baseline completed

- создан isolated `miniapp/` root для будущего frontend;
- создан `miniapp/AGENTS.md` для context-efficient Codex/Cursor work;
- создан Product/Screen/Development Operating System;
- создан Integration Foundation;
- создан комплект `miniapp/.ai/*`;
- root Guide OS code, DB, tests, configuration, CI and production untouched;
- следующая задача: MA1 low-fidelity wireframes, no code.

## 2026-08-28 — MA1 UX prototype created (pending owner review)

- создан `miniapp/prototype/index.html` — автономный кликабельный low-fidelity прототип на mock-данных;
- создан `miniapp/prototype/README.md` с инструкцией открытия;
- покрыты calendar day/week/month, agenda, add tour/day off, forms, date warning, blocking time conflict, tour card actions, reports/filters/workload, free dates preview/copy, settings/profile/notifications;
- mock: 28.08.2026, тур «Обзорный Самарканд» 09:00–14:00; демо пересечения 12:00–16:00;
- логотип: текстовый wordmark (официальный SVG вне repo);
- проверки: HTML parse, `git diff --check`, без внешних requests;
- MA1 не отмечен fully complete — требуется ручной review владельца перед MA2/scaffold.

## 2026-08-28 — MA1 owner review approved

- владелец утвердил MA1 low-fidelity prototype;
- подтверждено, что production Mini App автоматически следует light/dark theme Telegram через WebApp theme parameters;
- тёмный вид локального prototype определяется системным `prefers-color-scheme` и не фиксирует production theme;
- следующий этап — MA2 design system and high-fidelity prototype;
- application code, Web API и backend пока не начинаются.

## 2026-08-28 — MA2 high-fidelity prototype created (pending owner visual review)

- MA1 `index.html` обновлён до high-fidelity: semantic CSS tokens, Professional Minimal polish;
- скопирован official logo в `miniapp/prototype/assets/logo.svg` (verified identical);
- demo theme control: Как в Telegram / Светлая / Тёмная (`sessionStorage`, не production);
- сохранена полная MA1 функциональность и mock-сценарии конфликтов;
- добавлены focus states, reduced motion, offline demo state, SVG nav icons;
- обновлён `miniapp/prototype/README.md`;
- проверки: HTML parse, JS syntax, logo cmp, network grep, `git diff --check`;
- MA2 не отмечен fully complete — требуется визуальный review владельца перед scaffold.

## 2026-08-28 — MA2 owner feedback: Reports week workload

- убрана календарная сетка из вкладки «Итоги» (дублировала «Календарь»);
- добавлена компактная визуализация по неделям: рабочий / свободный / выходной;
- сохранены summary, фильтры, доход и кнопка «Поделиться свободными датами»;
- hint навигации к вкладке «Календарь» для работы с конкретной датой;
- MA2 status: pending owner visual review.

## 2026-08-28 — MA2 Reports week grouping fix

- `getWeekChunks()` переведён на календарные недели Пн–Вс;
- неполные первые/последние недели: дни вне периода — пустые сегменты без статуса;
- подписи недель — диапазоны дат вместо «Неделя N»;
- summary периода считает только дни внутри выбранного диапазона (без изменений логики).

## 2026-08-28 — MA2 calendar UX: feed + expandable month

- убран переключатель День/Неделя/Месяц;
- основной экран: вертикальная лента 8 дней (сегодня + 7);
- tap дня → подробный экран; tap тура → карточка с возвратом в день;
- раскрываемый месячный календарь с навигацией prev/next;
- MA2 status: pending owner visual review.

## 2026-08-28 — MA2 blocking conflict overlay fix

- `returnToTourFormFromConflict(targetField)` вместо `closeOverlay()` + inline overlay mutation;
- «Изменить время» / «Изменить дату» восстанавливают форму с сохранёнными полями, edit/copy context и `overlayReturn`;
- focus на `f-start-time` или `f-start` после reopen;
- удалён unused `.view-tabs` CSS;
- MA2 status: pending owner visual review.

## 2026-08-28 — MA2 Reports stats + free-dates period fix

- `getAvailRange()` / heading из реального контекста (календарь, месяц итогов, custom диапазон);
- «Итоги»: 5 bot-style метрик, навигация месяц/год/весь период; weekly workload полностью удалён;
- MA2 status: pending owner visual review.

## 2026-08-28 — MA3 Phase 1 React scaffold + Calendar

- React 18 + TypeScript strict + Vite в `miniapp/src/`;
- Calendar flow ported from MA2 prototype on mock store;
- `prototype/` unchanged; root Guide OS untouched.

## 2026-08-28 — MA3 Phase 2 Reports, Settings, free-dates, demo states

- Reports tab: period nav, filters, 5 metrics, free-dates entry;
- Shared free-dates overlay with context snapshot and custom range;
- Settings overlay: profile, types, notifications, theme demo;
- Demo loading/error/offline states for QA;
- Business logic in `features/reports/lib/`; targeted Vitest tests;
- MA3 complete on mocks.

## 2026-08-29 — MA4 Step 1 API contract + gap analysis

- `docs/mini_app/API_CONTRACT_v1.md` — `/app/v1` endpoints, schemas, auth flow, errors, idempotency;
- `docs/mini_app/SERVICE_GAP_ANALYSIS_MA4.md` — mock client → service mapping, schema gaps, test plan;
- No bot, web_api, DB schema, or frontend changes; next MA4 Step 2 (services + migrations).

## 2026-08-29 — MA4 Step 2 shared services + migrations

- Additive `tours` columns: title, start_time, end_time, source, day_locations_json;
- `tour_service`: time-aware conflicts, entry CRUD/copy/day-locations, read mapper;
- `reports_service`, `availability_service` — MA3 parity with summary.ts / availability.ts;
- Pytest extended; bot handlers untouched; next MA5 (web_api).

## 2026-08-28 — MA2 owner visual review approved

- header: logo optical size (viewBox crop), symmetric toolbar with gear;
- «Итоги» и free-dates flows approved;
- MA2 closed; MA3 scaffold started.

## 2026-08-29 — MA3 build fixes + free-dates overlay fix

- TypeScript build errors fixed (imports, fmtDateShort, duplicate i18n keys, vite prototype exclude);
- Free-dates overlay: local state for custom range — preview updates on date change;
- `npm test` + `npm run build` pass locally.

## 2026-08-29 — MA5 Web API transport layer

- `web_api/` aiohttp app: entries CRUD, profile, reports summary, availability preview, session stub;
- `guide_os_miniapp_api.py` standalone entrypoint (no bot polling);
- Dev auth stub: `X-Dev-User-Id` / `Bearer dev:<user_id>` when `MINI_APP_API_DEV_AUTH=true`;
- Idempotency store (`miniapp_idempotency` table); camelCase DTO mapping; Russian error envelope;
- `tests/test_miniapp_api.py` (16 tests); full suite 1005 passed;
- `MINI_APP_API_ENABLED=false` by default; React client still on mocks (MA7 next).

## 2026-08-29 — MA6 Telegram initData auth + sessions

- `web_api/telegram_auth.py`: HMAC-SHA256 initData validation, auth_date freshness;
- `miniapp_sessions` table; opaque bearer tokens (hash stored server-side);
- `POST/DELETE /app/v1/session` production path; dev stub only when `MINI_APP_API_DEV_AUTH=true`;
- Optional `MINI_APP_API_ALLOWLIST`; env: session TTL, initData max age;
- `tests/test_miniapp_telegram_auth.py` (7 tests); full suite 1012 passed;
- next MA7 (React HTTP client).

## 2026-08-29 — MA7 React HTTP client

- `httpClient.ts`: session bootstrap (initData / dev_user_id), bearer, idempotency, 409 → `ApiConflictError`;
- `createClient.ts`: mock vs HTTP via `VITE_USE_MOCK_API` (default mock);
- `CalendarContext` wired to `guideOsClient`; server `date_warning` ack path;
- Vite proxy `/app/v1`; vitest `httpClient.test.ts` (4 tests); frontend **16 passed**;
- next MA8 (reports/availability API + staging smoke).

## 2026-08-29 — MA8 Reports and availability via API

- `GuideOsClient`: `getReportsSummary`, `previewAvailability`;
- HTTP mode: Reports metrics and free-dates copy from server; mock keeps local calc;
- `buildAvailabilityPreview` helper for mock client; vitest httpClient +18 tests total;
- next MA9 (staging smoke).

## 2026-08-30 — MA10 local Telegram E2E PASS

- Owner validated full MVP flow locally on Mac: dedicated test bot, real initData, API `127.0.0.1:8083`, Vite `127.0.0.1:5173`, Cloudflare Quick Tunnel, local SQLite, owner-only allowlist;
- Scenarios PASS: calendar CRUD, conflicts, day-off, multi-day/locations, reports (month/year/all-time + filters), availability, clipboard, profile/settings, themes;
- Railway hosted staging **deferred**; production unchanged; **MA10 complete**;
- next **MA11** — hosted closed staging deployment (deferred until owner approval).

## 2026-08-29 — MA10 Railway staging deploy (deferred)

- Combined Mini App routes on staging link API process explored in repo;
- Railway staging deploy attempted separately; not part of MA10 PASS;
- Hosted staging checklist remains [STAGING_SMOKE_MA9.md](../../docs/mini_app/STAGING_SMOKE_MA9.md) for future MA11.

## 2026-08-29 — MA9 Staging smoke + production gate docs

- `docs/mini_app/STAGING_SMOKE_MA9.md` — owner-operable WebView + curl checklist, pass/fail table, kill switch;
- `docs/mini_app/PRODUCTION_GATE_MA9.md` — pre-production checklist + owner sign-off;
- no code/deploy changes; MA10 local E2E followed.

## 2026-08-31 — Owner-approved Mini App MVP UX checkpoint — complete

- Post-MA10 UX checkpoint closed after owner manual review in dedicated local Telegram test bot;
- React Mini App interface approved as working MVP; no known blocking UX issues;
- Verified UX: sticky header with centered month/year and logo→Today; continuous feed; month-boundary title switching; seven-column month picker anchored to sticky header; Reports single title and bottom-safe scroll; `Telegram.WebApp.ready()` + `expand()` on startup;
- MA10 remains validated local Telegram E2E stage; MA11 hosted staging **deferred**; production pilot not yet authorized at that date;
- next product task defined by owner only.

## 2026-09-01 — Public production Mini App pilot validated and left active

- **Guide OS Mini App public production pilot — ACTIVE and owner-validated** on production Guide OS bot via `MenuButtonWebApp`;
- Owner explicitly approved **keeping the reversible public pilot enabled** (no rollback performed);
- **Primary production account (PASS):** bot opens Mini App; signed `initData` auth; existing bot tours visible; Mini App tours visible in bot; shared production data via services/database; tour CRUD, day off, reports, profile, calendar;
- **Second real Telegram account (PASS):** `/start` + Mini App; personal empty calendar; no visibility of first account data; bidirectional bot ↔ Mini App sync for create/edit/delete; return to first account confirms isolation; cross-account IDOR manual verification PASS;
- **Automated evidence on `main`:** Mini App security/API targeted **133 passed**; full backend **1167 passed, 1 skipped**; month-picker **32 passed**; feed **32 passed**; production frontend builds successful; `git diff --check` clean;
- Checkpoints: `2eb02f2` (API auth/validation hardening), `e8aed0b` (month cell status colors), `0076101` (feed day status colors);
- **Formal general production release** not separately declared; production gate docs retained for future review;
- **MA11** hosted closed staging not active next step; **no active coding/deployment task** until owner defines next step;
- Reversible rollback documented (`MINI_APP_ENABLED=false`, optional `MINI_APP_API_ENABLED=false`, redeploy) — **not executed** per owner decision.
## 2026-09-02 — GSMA0 GuideShop Mini App audit/contract

- GSMA0 завершён документационно; application code и production не менялись;
- Утверждён третий `guideshop` tab и горизонтально масштабируемая bottom navigation без full-page swipe;
- Personal companies/commissions переиспользуют существующие user-scoped services/tables;
- Official GuideShop остаётся read-only и изолированным degraded section;
- Зафиксированы API schemas, errors, idempotency/security invariants и targeted test matrix;
- next: GSMA1 navigation shell only.

## 2026-09-02 — GSMA1 GuideShop navigation foundation

- Added canonical `guideshop` tab, page placeholder and static header title;
- Bottom nav now uses a horizontally scrollable/snap track with active-item auto-scroll and `aria-current`;
- Calendar/Reports state and behavior retained; no GuideShop data API, backend or deploy changes;
- Frontend tests: 162 passed; production build passed;
- next: GSMA2 Personal Places Web API.
