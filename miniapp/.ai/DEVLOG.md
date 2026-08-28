# Guide OS Mini App — Development Log

Краткий append-only журнал завершённых Mini App stages. Не копировать сюда длинные prompts, terminal output, secrets, commit hashes или speculative plans.

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
- `MINI_APP_API_ENABLED=false` by default; React client still on mocks; next MA6 (initData auth).
