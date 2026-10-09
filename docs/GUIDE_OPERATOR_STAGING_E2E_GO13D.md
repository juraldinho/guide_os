# GO13D Guide Operator ↔ Guide OS staging E2E runbook

Status: `GO13D_PASS` (owner-authorized staging execution completed 2026-10-08).

Sanitized closure: one confirmed connection; one cancelled assignment; immutable v1/v2 retained; zero active protected projections; cancellation and acknowledgement applied exactly once; GO11B1 discrepancy count zero; eligible integration-outbox rows zero in both systems; SQLite quick check `ok`. GO13D3A changed only the cancelled-tour assignment-cancellation frontend guard.

Post-run closure: GO13E recorded the operational audit. The fail-closed notification policy sends only when relevance is explicitly `True`; `False` becomes `superseded`, while unprovable `None` becomes `local_state`, both without Telegram HTTP. `STAGING_NOTIFICATION_DRAIN_PASS` suppressed three obsolete notifications without Telegram requests and delivered the current cancellation exactly once; staging delivery and its single in-runtime worker are enabled. `GO13F_ALREADY_COMPLETE`: both Guide OS production services are pinned to `f3c3806d328332fb0ff0a40987d582a4f0d09316` and no longer follow new `main` pushes. Production rollout remains unauthorized. `staging.guideos.uz` is absent and optional; the healthy Railway Mini App domain remains the configured staging URL.

## Staging boundaries

- Guide Operator: `https://staging.guideoperator.uz`
- Guide OS bot: `@Guideosbot`
- Guide OS Mini App: `https://guide-os-staging-miniapp-staging.up.railway.app`
- Guide OS Mini App API: `https://api.staging.guideos.uz`
- Use only the existing staging guide profile and staging operator membership.
- Never record Telegram IDs, initData, cookies, JWTs, keys, tokens, or production data.
- Record only opaque domain IDs when required for event-count and reconciliation evidence.

## Preflight

- [ ] Confirm both projects and all selected Railway environments are `staging`.
- [ ] Record current staging deployment IDs and source revisions.
- [ ] Record production deployment IDs for post-run equality comparison; perform no production mutation.
- [ ] Confirm Guide OS has one runtime replica, one Telegram poller, one `/data` volume, and SQLite integrity `ok`.
- [ ] Confirm Guide Operator API, frontend, worker, and PostgreSQL are healthy.
- [ ] Confirm both integration workers are healthy and pending historical queues are empty.
- [ ] Confirm authenticated connectivity in both directions and fail-closed unauthenticated requests.
- [ ] Confirm the staging guide is discoverable without reporting identity in the run log.

## Live scenario

- [ ] Operator discovers the existing staging guide.
- [ ] Operator sends one connection invitation.
- [ ] Guide sees the invitation in the Guide Operator tab.
- [ ] Guide confirms the connection.
- [ ] Operator sees the confirmed connection.
- [ ] Operator creates one tour and assignment draft.
- [ ] Operator publishes immutable version 1 and sends the offer.
- [ ] Guide sees the offer and accepts it.
- [ ] Exactly one protected projection appears in the normal Guide OS calendar.
- [ ] Projection dates and role match the version 1 working package.
- [ ] Operator publishes one ordinary update.
- [ ] Guide sees the unread change and acknowledges it.
- [ ] Operator publishes one critical update.
- [ ] Previous active version and projection remain active before guide confirmation.
- [ ] Guide confirms the critical update.
- [ ] The protected projection changes exactly once to the confirmed version.
- [ ] Operator cancels the assignment.
- [ ] Guide sees the cancellation.
- [ ] Calendar occupancy is released while cancelled assignment history remains.

## Idempotency and reconciliation evidence

- [ ] Each connection, offer, decision, version, acknowledgement, and cancellation event has one logical outcome.
- [ ] No duplicate protected projections, notifications, decisions, or acknowledgements exist.
- [ ] Worker retries, if any, preserve the original event identity and do not duplicate effects.
- [ ] Guide Operator and Guide OS reconciliation snapshots report no unexpected discrepancy.
- [ ] Final integration outboxes have no unexpected eligible pending rows.

## Closure

- [ ] Guide OS SQLite `PRAGMA quick_check` is `ok`.
- [ ] Guide OS remains one replica and one poller.
- [ ] Guide Operator health/readiness and browser login remain healthy.
- [ ] Production bots, databases, domains, variables, and deployment IDs equal the preflight baseline.
- [ ] Remove only the staging business objects created for this scenario if an approved cleanup procedure exists; otherwise retain them as labelled staging evidence.
- [ ] Publish a sanitized PASS/FAIL report without identities or credentials.
