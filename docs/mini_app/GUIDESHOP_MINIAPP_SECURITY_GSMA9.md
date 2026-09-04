# GuideShop Mini App — security matrix (GSMA9)

> Дата: 2026-09-03 (manual E2E row updated 2026-09-04)  
> Scope: Mini App composition API + frontend client. Official GuideShop remains **read-only**. Mini App **sales are withdrawn**.  
> Evidence: automated tests cited below, plus completed GSMA10 owner E2E. **Not** a formal security certification. **Not** a separate formal general release.

Fail-closed rule: expected auth/ownership/validation failures must **not** be HTTP 500. Cross-user personal resources use **`404 not_found`**, not `403` leakage.

## Matrix

| Threat | Expected status / code | Evidence |
|---|---|---|
| Missing bearer session | `401 auth_required` | `tests/test_miniapp_security.py::TestBearerSessionSecurity::test_missing_authorization_rejected`; personal: `test_personal_places_auth_required_for_all_endpoints`, `test_personal_commissions_auth_required_for_all_endpoints`; official: `test_official_visits_auth_required`, `test_official_history_auth_required`; reports: `test_commission_reports_auth_required` |
| Expired / revoked session | `401` (not 500); token not echoed | `TestBearerSessionSecurity::test_expired_session_rejected`, `test_revoked_session_rejected`, `test_token_not_echoed_in_error_responses` |
| Forged / tampered initData | `401` / `auth_invalid`; no initData leak | `TestTelegramInitDataValidation::*`; `TestSensitiveDataLeakage` tamper case |
| Body `user_id` / `userId` spoof | Ignored; identity from session only | `TestBearerSessionSecurity::test_body_user_id_fields_do_not_change_session_identity`; `test_personal_places_create_rejects_owner_override`; `test_personal_commissions_create_rejects_owner_override` |
| Cross-user personal place ID (IDOR/BOLA) | `404 not_found` (not 403, not 500); no owner fields | `test_personal_company_bola_matrix_and_owner_only_lists`; `test_personal_places_get_foreign_id_not_found`; `test_personal_places_deactivate_foreign_not_found` |
| Cross-user personal commission ID | `404 not_found`; no note/id leak | `TestPersonalCommissionsIdorBola::*`; `test_commission_cannot_be_enumerated_or_reassociated_across_owners` |
| Forged/malformed personal opaque IDs | `404 not_found`; not 500 | `test_personal_places_get_malformed_id_not_found`; `test_personal_commissions_get_foreign_and_malformed_not_found`; `TestPersonalCommissionsIdorBola` malformed paths |
| Foreign/forged official company/visit IDs | `404 not_found`; opaque ID not reflected; not 500 | `test_forged_official_ids_fail_closed_without_namespace_reinterpretation`; `test_official_detail_uses_request_scoped_identity`; `test_official_visit_detail_unsafe_id_is_safe_not_found` |
| Official GET-only; mutations | `405` on POST/PUT/PATCH/DELETE of registered official routes; no official Mini App mutations | `test_registered_official_surface_is_get_only_and_sales_are_withdrawn`; `test_official_visits_mutations_unavailable`; `test_official_history_mutations_unavailable`; `test_unregistered_official_history_detail_and_sales_never_500` |
| Mini App sales routes | Unregistered; `404` (not 500); sales remain withdrawn | `tests/test_miniapp_guideshop_sales.py`; `test_registered_official_surface_is_get_only_and_sales_are_withdrawn`; `test_unregistered_official_history_detail_and_sales_never_500`; frontend: `miniapp/tests/httpClient.test.ts` («sales API withdrawn») |
| Frontend never calls GuideShop `/integration/v1`; no JWT/bot token | Official HTTP paths are `/app/v1/guideshop/...` only | `miniapp/tests/httpClient.test.ts` official GET path assertions; `never requests GuideShop /integration/v1 from the Mini App client` |
| HTML/script in names/notes | Stored/returned as inert JSON text | `test_official_companies_script_like_strings_remain_inert`; `test_commission_reports_script_name_remains_inert_json`; `test_personal_place_and_commission_html_roundtrip_is_inert` |
| Input length limits (place/commission writes) | `400 validation_error`; no 500 | `test_personal_places_create_rejects_too_long_name`; `test_personal_places_create_rejects_too_long_optional_fields`; `test_personal_commissions_create_rejects_note_limit_and_server_keys` |
| Commission reports scoped to session; period params only | Session user only; extra query (`userId`, tour filters) → `400 validation_error`; empty is 200 | `test_commission_reports_multi_company_breakdown`; `test_commission_reports_validation_errors`; `test_commission_reports_session_scoped_period_only` |
| Logs: no tokens, initData, opaque IDs, PII | Sanitized `miniapp_guideshop` outcome/latency only | `tests/test_miniapp_guideshop_observe.py`; runbook `GUIDESHOP_MINIAPP_ROLLBACK_GSMA8.md` §5 |
| Official outage isolated from personal + calendar/reports | Official `503 temporarily_unavailable`; personal list and commission reports still 200 | `test_official_failure_does_not_break_personal_places`; `test_official_outage_does_not_block_personal_or_commission_reports` |
| Idempotency not shared across users | Separate caches; 409 only for same user/endpoint/body mismatch | `test_personal_commission_idempotency_is_user_and_endpoint_scoped`; `TestIdempotencyIsolation`; `test_personal_places_idempotency_isolated_between_users` |
| Two Telegram accounts, real initData, device layouts | Manual owner E2E **PASS** on 2026-09-04 | [`GUIDESHOP_MINIAPP_E2E_GSMA10.md`](GUIDESHOP_MINIAPP_E2E_GSMA10.md) (no Telegram IDs, tokens, initData, company names, or production PII recorded here) |

## Surfaces in scope

```text
/app/v1/personal-places
/app/v1/personal-commissions
/app/v1/reports/commissions
/app/v1/guideshop/companies
/app/v1/guideshop/visits
/app/v1/guideshop/points/summary
/app/v1/guideshop/history
```

Out of Mini App: `/app/v1/guideshop/sales` (withdrawn). Bot GuideShop sales unchanged.

## Explicit non-claims

- Not a formal security certification.
- Not a separate formal general production release; public production pilot remains owner-controlled.
- No GuideShop official mutations from Mini App.
- Mini App sales remain withdrawn.
- Rollback of official reads: `GUIDESHOP_READS_ENABLED=false` (see GSMA8 runbook).
