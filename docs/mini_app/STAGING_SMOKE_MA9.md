# Guide OS Mini App — Staging Smoke (MA9)

> Версия: 1.0
> Дата: 2026-08-29
> Аудитория: owner / release operator
> Статус: **чеклист для ручного прогона** — заполняется при hosted staging deploy (**MA11+**). Не содержит секретов.

## Цель

Проверить полный HTTP stack Mini App на **изолированном staging** перед любым production gate. Smoke подтверждает: initData → session, CRUD календаря, профиль, отчёты и свободные даты с серверной логикой (единый source of truth с ботом).

## Связанные документы

- [API_CONTRACT_v1.md](API_CONTRACT_v1.md)
- [PRODUCTION_GATE_MA9.md](PRODUCTION_GATE_MA9.md)
- [miniapp/GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md](../../miniapp/GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md) §20–21

---

## 1. Prerequisites (staging only)

Заполнить **локально** (не коммитить в repo):

| Item | Requirement | Owner notes |
|------|-------------|-------------|
| Staging bot | Отдельный Telegram bot (не production) | Bot username: __________ |
| `BOT_TOKEN` | Token **только** staging bot; в secrets manager / Railway env | Stored in: __________ |
| SQLite DB | Отдельный volume/path; **не** production `guide_os.db` | Path/volume: __________ |
| API process | `python guide_os_miniapp_api.py` или coordinated runtime (MA11) | Host: __________ |
| `MINI_APP_API_ENABLED` | `true` on staging | |
| `MINI_APP_API_DEV_AUTH` | **`false`** on staging (real initData only) | |
| `MINI_APP_API_ALLOWLIST` | Comma-separated Telegram user IDs тестеров | IDs (local only): __________ |
| `MINI_APP_SESSION_TTL_SECONDS` | e.g. `3600` | |
| `MINI_APP_INITDATA_MAX_AGE` | e.g. `86400` | |
| `MINI_APP_API_HOST` / `PORT` | Bind + port reachable behind HTTPS reverse proxy | |
| Static Mini App | Built `miniapp/dist/` на HTTPS origin **того же** или trusted API host | URL: __________ |
| Frontend env (build) | `VITE_USE_MOCK_API=false` | |
| Frontend env (build) | `VITE_API_BASE_URL` = публичный API base (или same-origin `/app/v1`) | |
| HTTPS | WebView + API только HTTPS; initData не на HTTP | |
| Telegram menu | Staging bot открывает Mini App URL (MA11 wiring) | |
| Local dev reference | `MINI_APP_API_DEV_AUTH=true` + `VITE_DEV_USER_ID` — **не** для staging smoke | |

**Fail closed:** если allowlist задан и ваш Telegram ID не в списке → `403 forbidden` после валидного initData.

**Kill switch:** `MINI_APP_API_ENABLED=false` → API не стартует / routes недоступны; Mini App UI без backend.

---

## 2. Evidence rules

- Заполнять таблицу Pass/Fail в §4.
- **Не** вставлять в тикеты/docs: `BOT_TOKEN`, `session_token`, raw `init_data`, PEM, notes, реальные имена компаний из production.
- Скриншоты: обрезать Telegram ID / токены; использовать synthetic туры на staging DB.
- Curl: заменить placeholders; не сохранять вывод с токенами в git.

---

## 3. Step-by-step smoke

### 3.a Session bootstrap (initData → session_token)

**Telegram WebView**

1. Открыть Mini App из staging bot (Menu / Web App button).
2. Убедиться: UI загрузился, не mock (данные совпадают с staging DB, не с фиксированным mock 28.08.2026 только если так seeded).

**Optional curl** (получить `init_data` из WebView debug или Telegram test tools — **не логировать**):

```sh
curl -sS -X POST "https://<STAGING_API_HOST>/app/v1/session" \
  -H 'Content-Type: application/json' \
  -d '{"init_data":"<INIT_DATA>"}'
```

**Expected:** HTTP 200, envelope `data.session_token` (opaque), `data.session_expires_at`, `data.user.telegram_id` matches your account.

**Failure codes:** `401 auth_invalid` (bad/expired initData), `403 forbidden` (allowlist).

---

### 3.b List entries / create tour / edit / delete

Сохранить `SESSION_TOKEN` только в shell session (не в файлы).

```sh
export API="https://<STAGING_API_HOST>"
export AUTH="Authorization: Bearer <SESSION_TOKEN>"
```

| Step | Action | Expected |
|------|--------|----------|
| List | `GET $API/app/v1/entries?from=2026-01-01&to=2026-12-31` + `$AUTH` | 200, `data.entries` array |
| Create | `POST $API/app/v1/tours` + `Idempotency-Key: <uuid>` + JSON body (title, dates, status, payment, income) | 201, entry with `id` |
| Get | `GET $API/app/v1/entries/<ENTRY_ID>` | 200, same entry |
| Edit | `PATCH $API/app/v1/entries/<ENTRY_ID>` + idempotency key | 200, updated fields |
| Delete | `DELETE $API/app/v1/entries/<ENTRY_ID>` + idempotency key | 200, empty `data` |

**WebView:** создать тур через UI → виден в ленте → редактирование → удаление.

---

### 3.c Day off + time conflict + date_warning ack

| Scenario | How | Expected |
|----------|-----|----------|
| Day off | `POST $API/app/v1/day-offs` `{"startDate":"...","endDate":"..."}` | 201, `type: day_off` |
| Day off conflict | Day off на дату с существующим туром | 409 `day_off_conflict` or `time_conflict` |
| Date warning | Timed tour same day, non-overlapping times | 409 `date_warning`; retry with `ack_date_warning: true` in body | 201/200 |
| Time conflict | Overlapping times same day | 409 `time_conflict`; save blocked until time changed |

WebView: повторить сценарии из MA1/MA2 prototype (blocking overlay / warning ack).

---

### 3.d Multi-day tour + day locations patch

1. Create tour `startDate` / `endDate` spanning ≥2 days.
2. `PATCH $API/app/v1/entries/<ENTRY_ID>/day-locations` body: `{"locations":{"2026-09-01":"City A","2026-09-02":"City B"}}`
3. Expected: 200, `dayLocations` in response.

WebView: multi-location overlay сохраняет локации по дням.

---

### 3.e Profile read / patch

| Step | Action | Expected |
|------|--------|----------|
| Read | `GET $API/app/v1/profile` | 200, name, telegramId, types, notifications |
| Patch | `PATCH $API/app/v1/profile` `{"name":"...","notifications":{"enabled":true,"time":"20:00"}}` | 200, updated profile |

WebView: Settings → изменить имя и время напоминания → сохраняется после reload.

---

### 3.f Reports summary (month / year / filters)

**HTTP mode UI:** `VITE_USE_MOCK_API=false`, Reports tab.

| Step | Action | Expected |
|------|--------|----------|
| Month | Select month period + status/payment chips | Metrics match `GET /app/v1/reports/summary?from=&to=&status=&payment=` |
| Year | Year period | Totals update; current year capped at today (contract) |
| Filters | reserved / confirmed, paid / unpaid | Counts change per filter |

Curl example:

```sh
curl -sS "$API/app/v1/reports/summary?from=2026-08-01&to=2026-08-31&status=all&payment=all" -H "$AUTH"
```

Expected fields: `tourCount`, `workDays`, `income`, `paidTours`, `unpaidTours`, `period`.

---

### 3.g Availability preview + clipboard copy

| Step | Action | Expected |
|------|--------|----------|
| API | `POST $API/app/v1/availability/preview` `{"from":"...","to":"...","format":"text"}` | 200, `heading`, `text`, `freeDates`, `ranges` |
| UI | Reports or Calendar → «Поделиться свободными датами» | Preview text from server in HTTP mode |
| Copy | Copy button | Clipboard contains `text`; toast success |

Empty range: `text` empty → UI shows empty state (no free dates).

---

### 3.h DELETE session → subsequent 401

```sh
curl -sS -X DELETE "$API/app/v1/session" -H "$AUTH"
curl -sS "$API/app/v1/profile" -H "$AUTH"
```

Expected: DELETE 200; next request `401 auth_required`.

WebView: after session expiry or logout path (if exposed) — protected screens fail closed.

---

## 4. Pass / fail record (owner fills at run time)

| # | Step | Pass | Fail | Notes (no secrets) |
|---|------|------|------|---------------------|
| a | Session bootstrap | ☐ | ☐ | |
| b | Entries CRUD | ☐ | ☐ | |
| c | Day off + conflicts | ☐ | ☐ | |
| d | Multi-day + day locations | ☐ | ☐ | |
| e | Profile read/patch | ☐ | ☐ | |
| f | Reports summary | ☐ | ☐ | |
| g | Availability + copy | ☐ | ☐ | |
| h | Session revoke | ☐ | ☐ | |

**Run metadata (sanitized):** date __________ | staging API host __________ | Mini App URL __________ | operator __________

**Overall staging smoke:** PASS ☐ / FAIL ☐

If FAIL: block production gate; open defect with repro steps (no tokens).

---

## 5. Rollback / kill switch

| Action | Effect |
|--------|--------|
| `MINI_APP_API_ENABLED=false` | API entrypoint exits / no listener; Mini App HTTP calls fail |
| Remove / hide Web App button on staging bot | Users cannot open Mini App |
| Clear `MINI_APP_API_ALLOWLIST` or remove IDs | New sessions rejected (`403`) if allowlist enforced |
| Revert static deploy to previous `dist/` | UI rollback independent of API |
| Staging DB restore from backup | Data rollback (separate procedure) |

Production bot and production DB are **not** touched during staging smoke.

---

## 6. Automated checks before manual smoke

Run in repo (no deploy):

```sh
cd miniapp && npm test && npm run build
.venv/bin/python -m pytest -q tests/test_miniapp_api.py tests/test_miniapp_telegram_auth.py
```

All green does **not** replace Telegram WebView smoke — initData and WebView UX require manual §3.
