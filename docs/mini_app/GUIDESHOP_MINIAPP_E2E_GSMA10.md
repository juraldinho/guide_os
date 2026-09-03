# GuideShop Mini App — GSMA10 owner E2E checklist

This checklist is for owner-run Telegram validation of a committed release candidate. Use synthetic temporary personal data only. Do not enter credentials, tokens, internal identifiers, production URLs, or personal/customer data in this document.

## A. Preconditions

- [ ] Release candidate commit recorded after the owner commits: `<RC_COMMIT>`
- [ ] Bot and Mini App use the same production Guide OS runtime and database.
- [ ] Public Mini App pilot remains enabled.
- [ ] Two Telegram accounts are available: Account A and Account B.
- [ ] Account A and Account B have distinct Guide OS identities.
- [ ] Official GuideShop visibility for each account may differ according to its link/access state.
- [ ] Rollback procedure is available but will not run automatically.

## B. Account A baseline

Record observations before creating temporary data:

| Check | Observation |
|---|---|
| Existing calendar data visible | `PASS / FAIL / NOT RUN` |
| Existing personal companies visible | `PASS / FAIL / NOT RUN` |
| Existing commission history visible | `PASS / FAIL / NOT RUN` |
| Official GuideShop state | `VISIBLE / ACCESS DENIED / INTEGRATION DISABLED / EMPTY / UNAVAILABLE` |
| Observed state matches Account A authorization | `PASS / FAIL / NOT RUN` |

Official data is not required to be visible when Account A has no valid GuideShop link. The observed state must match authorization.

## C. Account A bot → Mini App parity

1. [ ] Through the bot, create a uniquely named temporary personal company using synthetic text.
2. [ ] Through the bot, add a temporary commission containing a date, positive integer commission, and synthetic note.
3. [ ] Open the Mini App as Account A.
4. [ ] Confirm the temporary company and commission appear.
5. [ ] Confirm the personal commission shows no purchase amount, currency, income, or `Баллы` label.
6. [ ] Edit the temporary personal company in the Mini App.
7. [ ] Confirm the bot shows the updated company.
8. [ ] Edit the temporary commission in the Mini App.
9. [ ] Confirm the bot shows the updated date, commission, and note.
10. [ ] Confirm no real customer or financial data was used.

## D. Account B new-user behavior

1. [ ] Send `/start` from Account B.
2. [ ] Confirm the normal bot welcome and menu behavior.
3. [ ] Open the Mini App from the Telegram `MenuButtonWebApp`.
4. [ ] Confirm the session belongs to Account B without recording its identifier.
5. [ ] Confirm Account A calendar, personal companies, and commissions are absent.
6. [ ] Create a synthetic temporary personal company in the Mini App.
7. [ ] Add a synthetic temporary commission.
8. [ ] Confirm both records appear in the bot for Account B.
9. [ ] Confirm neither record appears for Account A.

## E. Cross-account isolation

| Check | Result |
|---|---|
| Account A cannot see Account B personal company | `PASS / FAIL / NOT RUN` |
| Account A cannot see Account B commission | `PASS / FAIL / NOT RUN` |
| Account B cannot see Account A personal company | `PASS / FAIL / NOT RUN` |
| Account B cannot see Account A commission | `PASS / FAIL / NOT RUN` |
| Switching Telegram accounts creates a fresh authenticated Mini App session | `PASS / FAIL / NOT RUN` |
| No stale bearer/session identity remains after switching accounts | `PASS / FAIL / NOT RUN` |
| The same display name in both accounts remains two independent records | `PASS / FAIL / NOT RUN` |

## F. Official GuideShop checks

Record the authorized state separately for each account:

| Account | Authorized observed state |
|---|---|
| Account A | `VISIBLE / ACCESS DENIED / INTEGRATION DISABLED / EMPTY / UNAVAILABLE / NOT RUN` |
| Account B | `VISIBLE / ACCESS DENIED / INTEGRATION DISABLED / EMPTY / UNAVAILABLE / NOT RUN` |

If official access exists:

- [ ] Official company list loads.
- [ ] Official company detail opens.
- [ ] Source badge says `GuideShop`.
- [ ] No edit, deactivate, or add-commission action is present.
- [ ] Visits open and back navigation works.
- [ ] Points summary opens.
- [ ] Payout history opens.
- [ ] Sales are absent.
- [ ] Opaque identifiers are not displayed.

If official access does not exist:

- [ ] The official section shows the correct access/degraded message.
- [ ] Personal companies remain fully usable.
- [ ] Calendar remains usable.
- [ ] Reports remain usable.

Do not modify official GuideShop data.

## G. Resilience smoke

Use only safe owner-approved methods. Do not intentionally disable or break production configuration during this checklist.

| Check | Result |
|---|---|
| Official request failure remains inside the official section | `PASS / FAIL / NOT RUN` |
| Personal companies remain usable | `PASS / FAIL / NOT RUN` |
| Calendar remains usable | `PASS / FAIL / NOT RUN` |
| Reports remain usable | `PASS / FAIL / NOT RUN` |
| Retry does not duplicate personal mutations | `PASS / FAIL / NOT RUN` |
| Closing a loading official sheet does not later show stale data | `PASS / FAIL / NOT RUN` |
| Production outage simulation | `NOT RUN — destructive configuration change not authorized` |

Use the current observable state or a local/mock simulation for resilience checks unless the owner separately authorizes another safe method.

## H. Device/layout matrix

Unavailable devices must be marked `NOT RUN`, never passed implicitly.

| Device | Result |
|---|---|
| iPhone Telegram WebView | `PASS / FAIL / NOT RUN` |
| Second Telegram account/device | `PASS / FAIL / NOT RUN` |
| Telegram Desktop, if available | `PASS / FAIL / NOT RUN` |
| Android, if available | `PASS / FAIL / NOT RUN` |

For each available device verify:

- [ ] Bottom navigation scrolls and all three modules are reachable.
- [ ] Safe-area spacing is correct.
- [ ] GuideShop page scroll reaches the final controls.
- [ ] Long names and addresses wrap.
- [ ] Sheets can be closed.
- [ ] Back navigation returns to the correct company or section.
- [ ] Light and dark themes work where available.
- [ ] There is no horizontal page overflow.
- [ ] Touch targets remain usable.

## I. Cleanup

- [ ] Deactivate or delete only temporary personal test data through supported application actions.
- [ ] Never delete official GuideShop data.
- [ ] Confirm both accounts return to their original personal state.
- [ ] Do not disable the public pilot unless the owner explicitly requests rollback.

## J. Owner decision block

```text
Automated verification: PASS / FAIL
Account A E2E: PASS / FAIL / NOT RUN
Account B E2E: PASS / FAIL / NOT RUN
Cross-account isolation: PASS / FAIL / NOT RUN
Official GuideShop behavior: PASS / FAIL / NOT RUN
Device review: PASS / FAIL / PARTIAL
Temporary data cleaned: YES / NO
Public pilot decision: KEEP ENABLED / ROLLBACK / UNDECIDED
Formal release decision: APPROVED / NOT APPROVED / UNDECIDED
Owner:
Date:
Notes:
```
