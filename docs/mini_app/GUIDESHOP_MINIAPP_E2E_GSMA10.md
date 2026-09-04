# GuideShop Mini App — GSMA10 two-account E2E checklist

> Версия: 1.0
> Дата: 2026-09-04
> Аудитория: owner
> Статус: **owner E2E PASS** (2026-09-04) на public production **pilot**. Не general release. Не содержит секретов / Telegram IDs / токенов / production PII.

Automated GSMA9 tests **не** заменяют этот прогон. Owner выполнил шаги на **двух реальных Telegram-аккаунтах**. В git — только sanitized PASS, без account identifiers.

Связанные документы:

- Roadmap §GSMA10: [`GUIDESHOP_MINIAPP_ROADMAP.md`](GUIDESHOP_MINIAPP_ROADMAP.md)
- Security matrix (last row = this stage): [`GUIDESHOP_MINIAPP_SECURITY_GSMA9.md`](GUIDESHOP_MINIAPP_SECURITY_GSMA9.md)
- Rollback: [`GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md`](GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md)
- Evidence style: [`STAGING_SMOKE_MA9.md`](STAGING_SMOKE_MA9.md) §2

---

## Evidence rules

- **Не** записывать в git, тикеты или этот файл: `BOT_TOKEN`, `session_token`, raw `initData`, Telegram user IDs, телефоны, реальные production-названия компаний/клиентов.
- Скриншоты: обрезать ID, номера, лица; только synthetic test names (например `GSMA10-A-test`).
- Result values: `PASS` / `FAIL` / `NOT RUN` / `N/A` (official catalog not linked).
- `N/A` допустим только для official-блока, если у аккаунта нет GuideShop link/access. Personal/Reports сценарии **не** N/A.
- Не менять Railway, production flags, и не деплоить в рамках заполнения чеклиста.

---

## Prerequisites

| Item | Requirement | Owner notes (local only) |
|------|-------------|--------------------------|
| Account A | Primary Telegram; Mini App via existing `MenuButtonWebApp` | |
| Account B | Second Telegram; same Mini App URL | |
| Pilot | Public Mini App **ACTIVE**; do not disable to run this list | |
| Data | Use **synthetic** personal companies/commissions only | |
| Official catalog | Visibility **depends on GuideShop link/access per account**. A may see official companies; B may see empty / `access_denied` / «раздел временно отключён». Both are valid. Do not require a specific live catalog. | A: __________ B: __________ |
| Bot personal places | Bot still has «личные места» / комиссии UX (`handlers/personal_places.py`). Use it for scenario 9. | |
| Rollback ready | [`GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md`](GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md); kill switch `MINI_APP_ENABLED=false` | Do **not** run unless owner decides rollback |

---

## Pass / fail record (owner fills at run time)

| # | Scenario | Owner | Date | Result | Notes (no secrets) |
|---|----------|-------|------|--------|---------------------|
| 1 | A: nav Calendar / Reports / GuideShop | owner | 2026-09-04 | PASS | |
| 2 | A: Итоги tours + «Комиссии»; period; chips | owner | 2026-09-04 | PASS | Period OK; tour chips independent |
| 3 | A: Мои компании + commission add/«Удалить» | owner | 2026-09-04 | PASS | Soft delete; gone from history/reports |
| 4 | A: official detail/visits/points/history | owner | 2026-09-04 | PASS | Visits newest-first |
| 5 | A: no «Продажи GuideShop» | owner | 2026-09-04 | PASS | Sales remain withdrawn |
| 6 | B: no A personal/report rows | owner | 2026-09-04 | PASS | |
| 7 | B: no cross-user cards in UI | owner | 2026-09-04 | PASS | |
| 8 | B: empty or own data only | owner | 2026-09-04 | PASS | |
| 9 | B Mini App → bot (B only); A cannot see B | owner | 2026-09-04 | PASS | Bot ↔ Mini App sync |
| 10 | Official degraded; personal + Итоги work | owner | 2026-09-04 | PASS | |
| 11 | Narrow phone layout spot-check | owner | 2026-09-04 | PASS | |
| 12 | Owner sign-off block (this file §Sign-off) | owner | 2026-09-04 | PASS | |
| 13 | Rollback pointer acknowledged | owner | 2026-09-04 | PASS | |

**Overall GSMA10 E2E:** **PASS** ☑ / FAIL ☐ / NOT RUN ☐

Owner-reported production E2E complete (2026-09-04). Public **pilot remains ENABLED**. Formal general release **not** separately declared. If a future FAIL occurs: do **not** declare general release; keep or roll back the **pilot** per owner decision. File defects without tokens.

---

## Account A

### 1. Navigation

Open Mini App as A from the production bot MenuButton.

- Bottom nav: **Календарь** → **Итоги** → **GuideShop** (horizontal chip scroll, not full-page swipe).
- Header for GuideShop: center `GuideShop`.

### 2. Итоги — tours + «Комиссии»

- Tour metrics remain (туры, дни, доход $, оплачено/не оплачено).
- Section **Комиссии** is **below** tour metrics and **above** «Поделиться свободными датами».
- Change **Месяц / Год / За весь период** (and prev/next month or year): commission totals/breakdown refresh.
- Change tour chips (Бронь / Занято / Оплачено / Не оплачено): **commission section must not refetch** as if the date range changed (totals stay the same unless you also changed period).

### 3. GuideShop — Мои компании

- Create / edit a **synthetic** personal company.
- Add a commission (date + positive integer; no `$` / `PTS` / «Баллы» as the commission value).
- Detail action **Удалить** confirms with delete copy; record **disappears from active list and reports** (soft deactivate — not hard DB delete). Company **Деактивировать** stays company-level wording.

### 4. Official (if linked)

If official list is empty, access denied, or integration disabled: mark **N/A** and still run §10 if you can observe official error UI.

If companies load:

- Open official company detail: **no** edit / add commission / deactivate on official data.
- **Визиты**: list newest `visitAt` first.
- Visit detail: time, tourist count, **баллы** (points), payment status as shown; back works.
- **Баллы GuideShop** (summary).
- **История выплат** from points flow.

### 5. No Mini App sales

- Confirm there is **no** «Продажи GuideShop» button, sheet, or route in Mini App.
- Bot official sales (if any) are out of this Mini App check.

---

## Account B (isolation)

Switch Telegram account (fresh Mini App session). Do not paste A’s URLs with opaque IDs into B’s chat.

### 6. No A data

- GuideShop **Мои компании** does not list A’s companies.
- Итоги **Комиссии** does not include A’s totals/rows.

### 7. No cross-user cards

- B cannot open A’s company/commission from the UI (no leaked cards). Do not brute-force IDs in this checklist.

### 8. Own data only

- Empty state **or** only B’s synthetic records.

### 9. Bot ↔ Mini App (B)

- Create synthetic personal company + commission in Mini App as B.
- In **bot**, open personal places for B: same records visible.
- As **A**, those B records are **absent** in Mini App and bot.

---

## Degraded official

### 10. Isolation of official failure

When official section shows error / access denied / temporarily unavailable:

- Error is **local** to official GuideShop (optional **Повторить**).
- **Мои компании** still load.
- **Итоги** including **Комиссии** still load.
- **Календарь** still loads.

Do **not** flip `GUIDESHOP_READS_ENABLED` on production just to force this, unless the owner separately authorizes a safe method. If A/B already see a degraded official state, use that. Otherwise `NOT RUN` with note.

---

## Layout (spot-check)

### 11. Narrow phone (~320–430px)

- Touch targets usable (~44px).
- Long company names wrap.
- **No** horizontal swipe that switches Calendar/Reports/GuideShop as full pages.
- Bottom nav remains reachable (safe area).

Mark unused devices `NOT RUN` (not implicit PASS). Optional extra: Desktop / Android.

---

## Release note (not auto-approve general release)

### 12. Owner sign-off

```text
GSMA10 two-account E2E: PASS
Public production pilot: REMAINS ENABLED
Formal general Mini App release: NOT APPROVED by this checklist (requires separate owner request)
GuideShop write ownership: UNCHANGED (official data remains read-only in Guide OS Mini App)
Mini App sales: REMAIN WITHDRAWN
Owner: owner
Date: 2026-09-04
Notes (no secrets): All checklist scenarios PASS. Sanitized record only — no account IDs or production names.
```

**PASS** confirms isolation/parity/degraded UX for the **public production pilot**. It does **not** by itself mean formal general production release.

### 13. Rollback pointer

If E2E FAIL or owner wants to hide Mini App:

1. Official reads only: `GUIDESHOP_READS_ENABLED=false` — see [`GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md`](GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md).
2. Hide Mini App: `MINI_APP_ENABLED=false` and `MINI_APP_API_ENABLED=false`, redeploy bot — **owner-run only**.

Do not re-enable Mini App sales.

---

## Cleanup (after PASS or FAIL)

- Soft-deactivate only **synthetic** personal test companies/commissions.
- Never delete or mutate official GuideShop data.
- Do not commit a filled table with account identifiers.
