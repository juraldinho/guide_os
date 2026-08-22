# Guide OS — Current Development Session

> Обновлено: 2026-08-22

## Текущий фокус

Stages 0–18 завершены. Runtime/data/security/operations closure — PASS; открытых implementation gates нет. Текущая работа — только documentation closure, после неё routine monitoring и incident response.

Финальная production-схема: GuideShop outbox/feed → Guide OS inbox/deduplication → Telegram notification/deep link. GuideShop остаётся источником истины для Visits и points; event production в GuideShop отделён от Telegram notification delivery в Guide OS.

## Завершённые этапы

- Master roadmap Stages 0–9C — PASS;
- Stage 10A GuideShop production release — PASS;
- Stage 10B Guide OS production release — PASS;
- Stage 10C production linking, reads and final UX — PASS;
- owner smoke: `Final points UX smoke PASS`;
- Stage 11A contracts `v1.2.0` — PASS;
- Stage 11B GuideShop outbox `3e8a760` — PASS;
- Stage 11C GuideShop event feed `a6299c7` — PASS;
- Stage 12A contracts pin `v1.2.0` commit `f09b0d2` — PASS;
- Stage 12B durable inbox/deduplication commit `f55e2ae` — PASS;
- Stage 12C event feed client/checkpoint commit `494df56` — PASS; CI и Integration Contracts successful;
- Stage 12D notification processing — PASS; atomic claim, bounded retry/dead-letter и safe GuideShop deep links проверены;
- Stage 12E default-off runtime composition — PASS; bounded worker, flag matrix и clean shutdown проверены (`803 passed`);
- Stage 12 production release commit `66ecfe5`, deployment `6e9c5fb8…` — PASS; owner smoke PASS; events/notifications OFF;
- Stage 13A abandoned-processing recovery и bounded dead-letter replay — PASS (`819 passed`);
- Stage 13B read-only reconciliation/gap report — PASS (`834 passed`);
- Stage 13C isolated recovery/restore drill — PASS; initial/restored NEEDS_ATTENTION, recovered CLEAN, quick_check ok;
- Stage 13 production deployment `0e714525…` — PASS; owner smoke PASS; events/notifications OFF;
- Stage 14A sanitized operational metrics — PASS (`847 passed`);
- Stage 14B security matrix — PASS (`52` matrix cases; full suite `899 passed`);
- Stage 14C commit `0ef25af` — PASS (`18` module tests; full suite `917 passed`); CI/contracts green; runtime defect не найден;
- Stage 14 production deployment `dc898131…` — PASS; owner smoke PASS; events/notifications OFF;
- Stage 15A shared E2E — PASS: local required test `1 passed`, focused `311 passed`, full Guide OS `919 passed, 1 skipped`, GuideShop event suites `51 passed`;
- shared CI workflow закрепляет GuideShop commit `4cf1c10b…`, required mode и sibling checkout без secrets;
- amended Stage 15 commit `9307593`; CI/contracts/shared E2E green, test executed and did not skip;
- Stage 15 production deployment `918f7eb5…` — PASS; owner smoke PASS; events/notifications OFF;
- Stage 16 notification canary — PASS; owner notification/deep-link и Visit back-navigation smoke — PASS;
- Stage 17 observation — PASS: `10m11s`, `22` cycles, HTTP `200×22`, failures/retries/duplicates/DLQ `0`;
- Stage 18 final closure audit — PASS для runtime, data, security и operations;
- Stage 16A audit: GuideShop production `cd3895d…` не содержит `3e8a760`, `a6299c7` или `4cf1c10b…`; canary не готов;
- Stage 11 candidate: events OFF блокирует outbox/version writes через единый shared boundary; migrations unconditional;

- Stage 0;
- Stage 1A/1B — identity и linking requests;
- Stage 2A — DTO/event contract;
- Stage 3A — flags/client boundary;
- Stage 3B — navigation tokens;
- Stage 3C1 — presentation/keyboards;
- Stage 3C2 — feature-gated mock Telegram UI.
- Stage 3D — user-bound `/start` deep links и development smoke helper.
- Stage 4A завершён: HTTP client, identity composition, EdDSA auth и default-off real runtime готовы.
- Stage 4B GuideShop staging reads завершён: auth/query/cursor matrix `26/26`, FA/IC `0 FAIL`.
- Reproducible-environment и continuous-integration quality gates завершены.
- Stage 5D — link exchange persistence/evidence, inbound JWT/JTI и HTTP provider — завершён.
- Stage 9B Gate 1 — isolated Railway staging environment/service/volume — завершён.
- Stage 9B Gate 2A — только несекретная default-off staging configuration — завершён и вручную проверен.

## Проверенное состояние

- identity lookup выполняется до token consumption;
- client/service не переиспользуются между requests или guides;
- invalid runtime configuration fail-closed;
- cleanup гарантирован при success/error/cancellation;
- request-scoped runtime regression: `124 passed`;
- full suite: `420 passed`;
- локальный fake smoke test успешен.
- JWT profile: EdDSA, TTL 60 секунд, skew 10 секунд, strict audience/scope/identity validation;
- staging и production key material полностью разделены.
- signing settings принимают только Ed25519 PKCS#8 key;
- provider выпускает strict 60-second identity-bound JWT;
- full suite: `466 passed`.
- final Stage 4A regression: `232 passed`;
- final full suite: `470 passed`;
- ручной fake smoke test уже подтверждён владельцем.
- `.env.example` default-off и не содержит secrets;
- Базовый production runtime был зафиксирован как `3.13.1`; candidate build gate переводит pin на attested `3.13.14`.
- documentation/full suite: `1 passed` / `471 passed`.
- CI portability fix: focused `14 passed`, полный suite `472 passed`.
- GitHub Actions run `31408186374` для commit `785a780` завершён успешно.
- Stage 5D provider: focused `30 passed`, полный suite `584 passed`.
- Commit `aa60f18`; CI run `31622573211` и Integration Contracts run `31622573278` — success.
- Provider flag default-off; реальные keys, external connection и deployment отсутствуют.
- Railway staging service не имеет source, start command, deployments или domain.
- Staging volume `/data` изолирован от production volume.
- Production Railway state не изменён.
- GuideShop Gate 3 readiness до финального deployment составлял `3/4`; теперь подтверждён `4/4`.
- Staging runtime code: focused `104 passed`, полный suite `588 passed`, `git diff --check` clean.
- Существующий repository `venv` сломан; независимая проверка выполнена во временном `/tmp` environment на Homebrew Python 3.13.14 без изменения репозитория.
- Staging keys установлены без deploy: GuideShop public verification key, Guide OS private signing key и matching public handoff подтверждены.
- Текущий staging API не готов к deployment: provider запускается только вместе с Telegram bot runtime и требует `BOT_TOKEN`.
- Production latest deployment baseline изменился между gates внешним действием; перед deployment требуется provenance check.
- API-only entrypoint: focused `117 passed`, полный suite `601 passed`, socket-free health test, `git diff --check` clean.
- API-only commit `ac779b417b6adb50f43494cf4c0d25e6e292d646`; CI `31743087618` и contracts `31743087697` successful.
- Production provenance audit: новые failed deployments являются GitHub auto-deploy attempts и не заменили active production runtime; verdict `SAFE TO PROCEED TO STAGING DEPLOYMENT GATE`.
- Staging deployment attempts `0e861878…` и `2ebea9ce…` failed до runtime из-за отсутствующей GitHub artifact attestation для mise Python 3.13.1.
- После промежуточного rollback source и start command были сохранены; финальный gate повторно включил staging provider flags и создал один HTTPS domain после успешного deployment.
- Финальный staging deployment `5c098777-ba6e-40ad-ba03-83480b0e3596` — `SUCCESS` на commit `ac779b4`.
- HTTPS base URL: `https://guide-os-staging-api-staging.up.railway.app`.
- Три gate health checks и одна независимая проверка этого чата вернули HTTP 200 и expected safe JSON.
- GuideShop Gate 3 readiness: `4/4`.
- GuideShop Gate 4A lifecycle: `44/44 PASS`; raw-token/JTI replay rejected; clean active link retained.
- GuideShop Gate 4B reads: `PASS`; Companies `1`, Visits `2`, Sales `4`, Points `2`, History `1`; auth/query/cursor `26/26`; FA/IC `0 FAIL`.
- GuideShop production `v1.3.0` выпущен с выключенными integration flags.
- Production lifecycle variables и all integration flags отсутствуют/default-off; audit PASS.
- Raw variable dump containment требует отдельного подтверждения либо secret rotation.
- Candidate commit `b89562294461b925755255ac48e9a53d65d0b071` содержит ровно Python pin/README/test; CI `31942628286` и contracts `31942628273` successful.
- Staging proof deployment `a79abd94…` SUCCESS на `b895622…`: Python 3.13.14 attestations verified, bypass keys absent, health 3/3, production unchanged.
- Production backup PASS: verified age artifact `guide_os-prod-20260816T122903Z-b7ebbbcf.db.gz.age`, mode `600`, encrypted SHA-256 `e0418a2b…fee9`; restore integrity/count reconciliation passed, plaintext cleaned, production unchanged.
- Docs-only commit `dd04e4c` pushed; CI `31952195788` and contracts `31952195720` successful; working tree был clean до следующего operational update.
- Containment audit verdict `ROTATION REQUIRED`: unsanitized raw variable prefix попал в Cursor Shell output; minimum scope только production `BOT_TOKEN`.

## Следующее действие

Согласно `.ai/NEXT_TASK.md`, выполнять routine post-launch monitoring и incident response. Новая product-разработка начинается только после выбора нового roadmap item владельцем.

## Зафиксированное будущее требование

- Личные неофициальные места и self-reported external sales принадлежат аккаунту гида в Guide OS.
- Записи разных гидов не объединяются в глобальный каталог GuideShop.
- GuideShop остаётся владельцем официального points balance и позже может принимать минимальные идемпотентные claims по `external_sale_id`.
- Это отдельный post-MVP write workstream после базовой read-only интеграции; налоговая, redemption и anti-fraud модель ещё требует решения.

## Финальное production-состояние

- Guide OS: commit `930759340a867113c6a78da64552936f5428597d`, deployment `9da4811d-8987-467d-bcd8-8f667f6fd081`, events/notifications ON;
- GuideShop: commit `c6cbbf48a7d0c0a6d133e724db2c39ce28a5ab3b`, deployment `cfd82638-bc76-4a87-b7db-dd0f6886a593`, events ON, notifications OFF;
- одна active link; outbox `2`; один aggregate subject version `2`;
- inbox stale `1`, delivered `1`, pending/processing/dead-letter `0`;
- checkpoint generation `2`, watermark version `2`;
- notification attempts/successes `1/1`, duplicates `0`, reconciliation `CLEAN`.

## Ограничения сессии

- Исходный код изменяет только Cursor.
- Этот чат анализирует, проектирует, проверяет и обновляет Markdown.
- Minimal Change; никаких несвязанных изменений.
