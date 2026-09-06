# Guide OS — Next Task

> Обновлено: 2026-09-06

## Завершённое состояние

Интеграционные Stages 0–18 и Stage 19 (личные места) завершены. GuideShop Mini App GSMA0–GSMA10 complete for the public production pilot (GSMA10 owner E2E PASS 2026-09-04). Formal general release was not separately declared.

**GO6A–GO6B5, GO7B1–GO7B2, GO7D1–GO7D2, GO7E1–GO7E3, GO8B, GO8C2, GO8C3, GO8D1, GO8D2, GO8F2A, GO8F2B, GO9A, GO10A1, GO10A2A, GO10A2B, and GO11A complete**:
- GO6A–GO6B5: intake through lifecycle lists / calendar / reports semantics
- GO7B1–GO7B2: cancellation apply + cancelled list/detail
- GO7D1–GO7D2: ordinary version apply + unread acknowledgement UX
- GO7E1–GO7E3: critical intake + confirm/reject service + Mini App API/UX
- GO8B: Guide Operator service JWT verify/sign foundation
- GO8C2: local connection-consent domain + offer intake enforcement
- GO8C3: connection Mini App API + Guide Operator tab UX
- GO8D1: authenticated inbound HTTP event routes (API-only entrypoint)
- GO8D2: authenticated discovery + availability reads on the same API-only surface
- GO8F2A: authenticated single-event outbound `deliver_one()` to Guide Operator GO8F1 routes
- GO8F2B: bounded outbound delivery worker (separate CLI process; default off)
- GO9A: local two-service HTTP E2E harness (sibling Guide Operator pytest + Guide OS test-only servers; flags off outside the harness)
- GO10A1: durable guide-notification outbox foundation (atomic with intake)
- GO10A2A: reusable `deliver_one_notification()` Telegram send (default off)
- GO10A2B: bounded notification drain task inside existing `bot.py` (default off)
- GO11A: read-only reconciliation local-projection snapshots (`GET /integration/v1/reconcile/guides/{guideOsId}/…`, scope `guide-operator:reconcile`)

## Единственная следующая задача

**STOP before GO11B comparison/repair, operator-facing notifications UI, or deployment.** Do not add automatic drift repair, Mini App notification UI, production keys, or staging/production rollout without a new explicit owner request.

## Local notification delivery (disabled by default)

Runs only inside the existing bot process (`python bot.py`) as one background task. Does not create a second bot, getUpdates loop, or webhook.

Env (documented in `.env.example`, defaults off / safe):
- `GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_DELIVERY_ENABLED` — requires `BOT_TOKEN` + HTTPS `MINI_APP_PUBLIC_URL`
- `GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_WORKER_ENABLED`
- `GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_WORKER_POLL_INTERVAL_SECONDS` (1–300, default 5)
- `GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_WORKER_BATCH_SIZE` (1–50, default 10)
- `GUIDE_OS_GUIDE_OPERATOR_NOTIFICATION_WORKER_SHUTDOWN_TIMEOUT_SECONDS` (1–120, default 15)

## Out of scope until activated

- GO11B comparison / automatic repair
- Operator-facing / Mini App notification UI
- End-to-end Guide OS ↔ Guide Operator deployment
- Google Calendar roadmap (`docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md`)
- Tips roadmap (`docs/TIPS_ROADMAP.md`)
- GuideShop Mini App new coding (pilot remains enabled; no active GSMA task)

## Known GO limitations

- Inbound HTTP + discovery/availability are implemented (GO8D1–GO8D2) but remain feature-flagged off by default
- Outbound `deliver_one()` + worker exist (GO8F2A–GO8F2B) and are proven by the GO9A local HTTP harness; they remain feature-flagged off
- Guide-notification rows + single-send + in-bot drain exist (GO10A1–GO10A2B) but remain feature-flagged off
- GO11A reconcile reads exist on the API-only surface and remain behind service-auth fail-closed defaults
- Mini App WebApp button opens the approved Mini App URL (Guide Operator tab deep-link not invented yet)
- Comparison/repair, notifications UI, and deployment are not started
- Operator projection has no guide fee (income NULL; excluded from paid/unpaid)
- Withdrawal/expiration are not implemented
- Guide-initiated disconnect is not implemented
