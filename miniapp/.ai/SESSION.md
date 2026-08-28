# Guide OS Mini App — Session

> Обновлено: 2026-08-29

## Текущий статус: MA0–MA5 complete

| Этап | Результат |
|------|-----------|
| MA0 | Docs, DECISIONS D-001…D-051, AGENTS |
| MA1 | `prototype/index.html` low-fi — approved |
| MA2 | High-fi prototype — approved (feed, stats, logo, conflicts) |
| MA3 | React + Vite — Calendar, Reports, Settings, free-dates, demo states on mocks |
| MA4 Step 1 | `API_CONTRACT_v1.md`, `SERVICE_GAP_ANALYSIS_MA4.md` |
| MA4 Step 2 | Migrations, `tour_service` / `reports_service` / `availability_service`, pytest |
| MA5 | `web_api/`, `guide_os_miniapp_api.py`, dev auth stub, 16 API tests |

**Следующий:** MA6 — Telegram initData session auth. **React на mocks** до MA7.

## Ключевые артефакты

- Frontend: `miniapp/src/` (`npm run dev`, `npm test`, `npm run build`)
- Prototype (reference): `miniapp/prototype/`
- Web API: `web_api/`, entrypoint `guide_os_miniapp_api.py`
- Services: `services/tour_service.py`, `reports_service.py`, `availability_service.py`
- Tests: `tests/test_miniapp_api.py` + full suite **1005 passed**

## Важные нюансы

- Bot handlers **не изменены**; date conflicts в боте — warning, в Mini App time overlap — blocking (shared service MA4).
- Legacy tours без времени = full-day.
- Web API: `MINI_APP_API_ENABLED=false` по умолчанию; dev auth только с `MINI_APP_API_DEV_AUTH=true`.
- GuideShop не входит в MVP Mini App.

## Resume instructions

1. Read `../AGENTS.md` and `NEXT_TASK.md`.
2. MA6 scope: `web_api/auth.py`, initData HMAC, session store.
3. Do not wire `miniapp/src` HTTP client until MA7 approved.
4. Bot/production unchanged without explicit release scope.
