# Guide OS — Development Log

## 2026-09-06 — GO11A read-only reconciliation local snapshots

- Added authenticated GET reconcile routes on the API-only Guide Operator integration surface under `/integration/v1/reconcile/guides/{guideOsId}/…` with exact scope `guide-operator:reconcile`.
- Returns local connection status, assignment status, active/pending version numbers, protected calendar projection existence/dates/version, and cancellation state only. Bounded `limit`/`cursor`/`ids`. Non-disclosing 404 for wrong guide/resource.
- Read-only: no mutations, outbox writes, repairs, or delivery marks. Service auth remains default-off/fail-closed.
- Did not change calendar, polling, reports, GuideShop, Mini App UI, or personal tours.
- Targeted tests: `tests/test_guide_operator_reconcile_http.py` plus discovery/integration/auth suite passed.
- STOP before GO11B comparison/repair.

## 2026-09-05 — GO9A local two-service HTTP E2E

- Added test-only `tests/go9a_guide_os_servers.py` (GO8D1/D2 + Mini App on loopback, isolated SQLite) and skip-if-missing wrapper `tests/test_guide_operator_shared_e2e.py`.
- Canonical harness lives in sibling Guide Operator `tests/test_guide_os_shared_e2e.py`: real HTTP, ephemeral Ed25519 keys, outbox workers, privacy/idempotency/occupancy asserts, one queued-retry scenario.
- Production flags remain off. No calendar/GuideShop/UI behavior change.
- Contract fix (smallest): `_validate_critical_change_summary` now accepts Operator full diffs whose items may be `ordinary` or `uncertain` while the envelope severity is `critical`. Title/driver/day-added publishes were 400 against the previous "every item must be critical" rule.
- STOP before reconciliation, notifications, frontend API wiring, or deployment.

## 2026-08-28 — Stage 19 personal records in progress

- Integration Stages 0–18 remain production-complete: GuideShop events ON, Guide OS events/notifications ON, reconciliation CLEAN after owner notification and observation smoke.
- Stage 19A audit confirmed personal places and self-reported external outcomes can be implemented inside Guide OS without changing GuideShop or the event pipeline.
- Stage 19B persistence/ownership was committed and pushed on branch `stage19-personal-records`, commit `22fb924`.
- Stage 19C private personal-place Telegram CRUD was implemented locally and remains uncommitted pending local smoke and owner Terminal commit/push.
- New operating rule recorded: routine Terminal actions such as Git branch/add/commit/push are owner-run from exact commands; Cursor is reserved for code changes and meaningful code analysis.

## 2026-08-19 — GuideShop Stage 11 handoff accepted

- Stage 11A contracts завершён: package `v1.2.0`;
- Stage 11B transactional outbox завершён на commit `3e8a760`;
- Stage 11C authenticated event feed завершён на commit `a6299c7`;
- GuideShop `develop == origin/develop`;
- event flags остаются default OFF; deployment и activation не выполнялись;
- GuideShop остановлен до интеграционного тестирования Stage 12;
- следующий этап Guide OS: Stage 12 contract pin `v1.2.0`, inbox, deduplication и notifications;
- Guide OS runtime, Railway, production, staging, keys и flags не изменялись.

## 2026-08-18 — Master roadmap synchronized; Stage 11 planning selected

- каноническим источником Stages назначен `integration_foundation.md`, раздел 18;
- Stages 0–10C зафиксированы как PASS;
- read-only MVP зафиксирован как завершённый на 100%;
- устаревшая внутренняя схема Stages 0–7 помечена исторической и больше не используется для выбора следующего этапа;
- Stage 11 Outbox/events выбран владельцем только как следующий design gate;
- Stage 12 inbox/notifications не начинается до завершения и отдельного approval Stage 11;
- runtime-код, Railway, production и GuideShop не изменялись.

## 2026-08-06 — Сформирован первичный план интеграции Guide OS ↔ GuideShop

Выполнено:

- определены архитектурные границы read-only MVP;
- интеграция разделена на последовательные этапы от readiness до production rollout;
- зафиксированы требования к identity, linking, API, событиям, deep links, безопасности, идемпотентности, мониторингу и reconciliation;
- установлена первая следующая задача: Stage 0 — readiness и владельцы данных;
- Cursor Prompt намеренно отложен до завершения readiness-проверки.

Код проекта не изменялся. Автоматические и ручные тесты не запускались, поскольку этап был исключительно документальным.

## 2026-08-07 — Stage 0 закрыт, Stage 1A завершён

Выполнено:

- Stage 0 закрыт решением Product Owner;
- shared-staging и live production-safety evidence сохранены как production activation gate;
- в `users` добавлен стабильный UUID4 `guide_os_id`;
- существующие пользователи получают ID через идемпотентный backfill;
- повторная регистрация сохраняет исходный ID;
- добавлен read-only lookup без побочного создания пользователя.

Проверка: focused suite — `5 passed`; полный suite — `37 passed`; `git diff --check` clean.

## 2026-08-07 — Stage 1B завершён

Выполнено:

- добавлено временное хранилище GuideShop linking requests;
- реализованы URL-safe tokens с 256 битами криптографической случайности;
- сохраняется только SHA-256 hash;
- зафиксированы audience `guideshop-link` и TTL 10 минут UTC;
- новый запрос отзывает предыдущий issued-запрос;
- consume выполняется однократно через атомарный условный UPDATE;
- expiration включён в атомарное SQL-условие;
- добавлены доменные ошибки для unknown, expired, consumed, revoked и wrong audience.

Проверка: Stage 1B — `8 passed`; Stage 1A — `5 passed`; полный suite — `45 passed`; `git diff --check` clean.

Остаточный риск: автоматическая очистка link-request history отложена до утверждения retention policy.

## 2026-08-07 — Stage 2A завершён

Выполнено:

- добавлены строгие DTO для Company, Visit, Sale и points transaction;
- добавлены pagination, API list/detail envelopes и безопасные API errors;
- деньги и points ограничены Decimal-строками без numeric coercion;
- timestamps ограничены UTC ISO 8601;
- неизвестные поля и неподдерживаемые версии отклоняются;
- добавлены четыре типизированных event payload v1;
- event type, subject type, typed data и object ID проверяются совместно;
- `subject.id` обязан совпадать с ID основного объекта внутри event data;
- доказано отсутствие DB/network side effects при валидации.

Проверка: contract suite — `40 passed`; Stage 1 regression — `13 passed`; полный suite — `85 passed`; `git diff --check` clean.

Следующее действие: Stage 3A — feature flags и mockable GuideShop client boundary без реальной сети.

## 2026-08-07 — Stage 3A завершён

Выполнено:

- добавлены независимые default-off flags для reads, linking, events и notifications;
- добавлен async read-only GuideShop client protocol;
- identity scope исключён из user-controlled method arguments;
- disabled client не выполняет сеть и SQLite;
- production factory не включает fake при reads-enabled;
- explicit in-memory fake возвращает только валидированные Stage 2A DTO;
- реализованы deep-copy isolation, deterministic ordering, filtering, details, history и opaque scoped pagination.

Проверка: Stage 3A — `27 passed`; Stage 1/2 regression — `53 passed`; полный suite — `112 passed`; `git diff --check` clean.

Остаточный риск: reads-enabled намеренно неработоспособен до реализации реального authenticated client.

## 2026-08-07 — Stage 3B завершён

Выполнено:

- добавлена строгая immutable GuideShop route model;
- добавлено server-side хранение navigation route payload;
- реализованы 192-bit tokens длиной 35 символов с SHA-256-only persistence;
- tokens привязаны к Telegram user ID и TTL 24 часа;
- resolution single-use и атомарно проверяет user, status и expiration;
- cross-user доступ не consumes и не revokes token;
- повреждённые server-side routes повторно валидируются и безопасно отклоняются;
- linking tokens и navigation tokens полностью разделены.

Проверка: Stage 3B — `50 passed`; previous integration regression — `80 passed`; полный suite — `162 passed`; `git diff --check` clean.

Остаточный риск: navigation audit rows сохраняются без cleanup до утверждения retention policy.

## 2026-08-09 — Stage 3C1 завершён

Выполнено:

- добавлены immutable GuideShop screen/action models;
- добавлен async presentation service с client injection;
- реализованы home, list, detail, pagination, empty и error screens;
- внешние DTO values экранируются для HTML;
- Decimal strings отображаются без пересчётов;
- detail actions различаются ordinal labels без object IDs в тексте кнопки;
- keyboard callbacks содержат только user-bound `gs_` navigation tokens;
- исправлен probabilistic Stage 3B opacity test через deterministic random source.

Проверка: navigation — `50 passed`; UI — `18 passed`; полный suite — `180 passed`; `git diff --check` clean.

Остаточный риск: abandoned unsent keyboards оставляют issued navigation tokens до TTL/revocation.

## 2026-08-09 — Stage 3C2 завершён

Выполнено:

- добавлена development/test-only fake runtime setting;
- main menu остаётся default-off и показывает GuideShop только при reads flag;
- добавлены entry handler и user-bound typed callback dispatch;
- navigation errors отображаются безопасно без message edit и replacement tokens;
- disabled callback не consumes token;
- explicit local fake composition не допускается в staging/production;
- GuideShop router подключён до global errors router;
- тесты изолированы от локального `.env`.

Проверка: Stage 3C2 — `40 passed`; полный suite — `220 passed`; `git diff --check` clean. Локальная кнопка подтверждена в development smoke.

Остаточный риск: token consumes до Telegram edit; восстановление выполняется повторным входом в GuideShop.

## 2026-08-09 — Stage 3D завершён

Выполнено:

- добавлен строгий builder `https://t.me/<bot>?start=<opaque-token>`;
- GuideShop handler принимает только точный `gs_` payload и зарегистрирован до generic `/start`;
- deep links используют существующие typed routes и user-bound single-use navigation tokens;
- disabled, stale, access-denied и invalid-route состояния отображаются безопасно;
- обычный `/start` и посторонние payload сохраняют прежний flow;
- добавлен development-only локальный helper для выпуска smoke-test ссылки без Telegram-команды.

Проверка: deep-link и helper regression — `58 passed`; полный suite — `278 passed`; `git diff --check` clean. Ручная development-проверка: первое открытие показало Visits, повторное открытие вернуло stale-link state.

Остаточный риск: token consumes до отправки Telegram screen; при ошибке доставки требуется новая ссылка или повторный вход в GuideShop.

## 2026-08-09 — Stage 4A: HTTP client foundation

Выполнено:

- добавлены immutable HTTP settings с централизованной валидацией direct/env construction;
- HTTPS обязателен для staging/production, unsafe URL и неограниченные числовые параметры отклоняются;
- добавлен runtime-checkable async access-token provider boundary без выбора OAuth/JWT реализации;
- identity-bound aiohttp client реализует восемь `/integration/v1/me/...` read endpoints;
- service token передаётся только через Bearer header, guide identity отсутствует в URL/query;
- успешные ответы проходят строгую Stage 2A DTO validation;
- timeout, connection, rate-limit и transient retries ограничены;
- response body читается потоково не более 1,000,000 bytes плюс один detection byte;
- lifecycle сессии явный, production factory остаётся default-off/fail-closed.

Проверка: Stage 4A и выбранные regressions — `169 passed`; полный suite — `380 passed`; `git diff --check` clean.

Открытая зависимость: production composition требует реального GuideShop access-token provider и доступного Integration API.

## 2026-08-09 — Stage 4A: request-scoped identity composition

Выполнено:

- добавлены static и request-scoped GuideShop UI service providers;
- trusted identity lookup выполняется один раз на request до navigation token consumption;
- каждый реальный request получает отдельный client, привязанный только к разрешённому `guide_os_id`;
- route, cursor, object ID, callback и deep-link payload не могут подменить identity;
- client закрывается ровно один раз при success, exception, cancellation и Telegram rendering failure;
- runtime проверяет полный `GuideShopClient` protocol и async cleanup до выдачи UI service;
- invalid client/provider configuration обрабатывается fail-closed и не consumes navigation token;
- существующий development fake flow сохранён через backward-compatible static provider.

Проверка: runtime/handlers/deep-links — `124 passed`; полный suite — `420 passed`; `git diff --check` clean. Ручной fake smoke test успешен: entry, Visits и возврат работают без изменений.

Открытая зависимость: выбор service authentication и реальный access-token provider остаются обязательными до production composition.

## 2026-08-09 — Stage 4A: service authentication contract

Документально утверждён production service-auth contract:

- asymmetric signed JWT Ed25519/`EdDSA` без OAuth token endpoint;
- strict `alg`, `typ`, `kid`, `iss`, `aud`, `sub`, `guide_os_id`, `scope`, `iat`, `nbf`, `exp`, `jti`;
- TTL 60 секунд и clock skew максимум 10 секунд;
- identity equality и active-link resolution обязательны на GuideShop side;
- bounded read retries могут повторно использовать token до expiration;
- staging/production key pairs разделены;
- описаны overlap rotation, emergency revocation, denylist и feature-flag rollback;
- private keys и реальные tokens запрещены в Git и логах.

Этап документальный: исходный код не менялся, автоматические и ручные тесты не требовались.

## 2026-08-09 — Stage 4A: EdDSA access-token provider

Выполнено:

- добавлены pinned `PyJWT==2.13.0` и `cryptography==48.0.1`;
- добавлены immutable signing settings с централизованной direct/env validation;
- принимается только unencrypted PKCS#8 Ed25519 private key и strict environment-specific `kid`;
- private key исключён из repr/equality diagnostics и safe errors;
- async provider реализует существующий `GuideShopAccessTokenProvider`;
- каждый вызов выпускает новый EdDSA token для canonical UUID4 `guide_os_id`;
- header и claims точно соответствуют утверждённому Stage 4A auth contract, TTL равен 60 секундам;
- `jti` содержит 128 bits injected cryptographic randomness;
- clock/randomness injectable и строго валидируются;
- tests независимо проверяют signature через ephemeral public key;
- реальные keys/tokens, persistence, network и runtime activation отсутствуют.

Проверка: auth/HTTP/runtime — `188 passed`; полный suite — `466 passed`; `git diff --check` clean.

Открытая зависимость: provider ещё не подключён к default-off production runtime; GuideShop verifier и API отсутствуют.

## 2026-08-10 — Stage 4A завершён

Выполнено:

- disabled flow не читает real HTTP/JWT settings и не создаёт providers;
- development/test fake flow остаётся credential-free и backward compatible;
- real flow соединяет trusted `get_guide_os_id`, shared EdDSA provider, lazy identity-bound HTTP clients и request-scoped UI provider;
- startup не выполняет identity lookup, token signing, HTTP, navigation-token creation или database writes;
- каждый request создаёт отдельный client и использует только trusted local identity;
- configuration failure очищает provider state и fail-closed до polling.

Проверка: GuideShop regression — `232 passed`; полный suite — `470 passed`; `git diff --check` clean. Локальный fake flow ранее вручную подтверждён владельцем; повторная проверка не требуется.

Stage 4B не начат и ожидает GuideShop staging API/verifier на separate development environment.

## 2026-08-10 — Quality gate: воспроизводимое окружение

Выполнено:

- добавлен sanitized `.env.example` со всеми текущими core и GuideShop variables;
- все GuideShop flags default-off, API/JWT secrets отсутствуют;
- Python runtime зафиксирован как `3.13.1`;
- README описывает fresh macOS setup, tests, local fake и security rules;
- local development environment, separate development environment и Railway явно разделены как независимые environments;
- virtual environments запрещено копировать между машинами;
- уточнено, что audit observation о broken `venv` относится к отдельному checkout на separate development environment.

Проверка: documentation test — `1 passed`; полный suite — `471 passed`; `git diff --check` clean.

## 2026-08-10 — Quality gate: continuous integration

Выполнено:

- добавлен минимальный GitHub Actions workflow для push, pull request и ручного запуска;
- clean Ubuntu runner использует Python `3.13.1`, pip cache и pinned `requirements.txt`;
- CI проверяет dependency consistency, whitespace и полный test suite;
- workflow имеет только read-only repository permissions и не выполняет Telegram polling, GuideShop network calls, artifact upload или deployment;
- все CI environment values являются явными безопасными строками, GuideShop flags остаются default-off;
- subprocess-тест development deep-link helper переведён с локального `venv/bin/python` на текущий `sys.executable`, поэтому одинаково работает локально и на clean runner.

Проверка: локально — `472 passed`, `git diff --check` clean; GitHub Actions run `31408186374` — success.

Подготовительные Guide OS quality gates завершены. Следующая интеграционная работа — Stage 4B после реализации GuideShop staging API/verifier на separate development environment.

## 2026-08-11 — Product decision: личные места и внешние продажи

Зафиксировано для будущего post-MVP workstream:

- неофициальные магазины, лавки и другие места не создаются как глобальные компании GuideShop;
- каждый гид ведёт собственный приватный список личных мест в Guide OS;
- Guide OS является источником истины для self-reported external sale и фактически полученного наличного дохода;
- GuideShop остаётся источником истины для официального points balance и не получает свободное название места без необходимости;
- возможная заявка на points передаётся позже как отдельная идемпотентная write-операция по `external_sale_id`;
- автоматическое начисление, redemption, налоги, лимиты и anti-fraud требуют отдельного утверждения до реализации;
- решение не входит в текущий read-only MVP и не изменяет следующую задачу Stage 4B.

Изменялась только Markdown-документация; исходный код и текущий контракт не изменялись. Тесты и ручная проверка не требовались.

## 2026-08-12 — Guide OS Stage 5D provider завершён

Выполнено:

- добавлены additive idempotent link-exchange и immutable lifecycle-evidence persistence;
- raw linking token потребляется атомарно и сохраняется только как SHA-256 hash;
- реализованы authoritative `active`, `revoked`, `conflict` evidence и UTC timestamps;
- добавлена строгая inbound GuideShop EdDSA JWT verification по contract `v1.1.0`;
- JTI replay protection атомарно отклоняет повторные и конкурентные JWT, сохраняя только SHA-256 digest;
- реализованы `POST /integration/v1/link-exchanges`, status GET и evidence GET;
- GET routes используют opaque exchange ID и authenticated fixed service principal без раскрытия membership reference;
- provider имеет отдельный default-off flag, loopback-only development/test composition и exactly-once cleanup;
- `.env.example` содержит только безопасные выключенные значения и пустой public-key allowlist;
- реальные credentials, staging/production activation, deployment и Stage 6 соединение отсутствуют.

Проверка: focused provider — `30 passed`; полный suite — `584 passed`; `git diff --check` clean. Commit `aa60f18`. GitHub CI run `31622573211` и Integration Contracts run `31622573278` завершены успешно.

Следующее действие: передать независимый `Guide OS Stage 5D provider — PASS` в GuideShop и выполнить Stage 6 isolated HTTP E2E только как совместную задачу двух систем.

## 2026-08-13 — Stage 9B Gate 1 и Gate 2A завершены

Выполнено:

- в Railway project `radiant-expression` создано отдельное environment `staging`;
- создан пустой staging-only service `guide-os-staging-api` без source, image, start command и deployments;
- создан отдельный volume `guide-os-staging-api-volume`, подключённый к `/data` и изолированный от production volume;
- через `--skip-deploys` установлены только 10 утверждённых несекретных staging variables;
- `DATABASE_PATH` направлен в `/data/guide_os_staging.db`;
- все GuideShop flags, включая provider flag, оставлены в `false`;
- JWT keys, API URL, source, domain и deployment не настраивались;
- ручная проверка Railway staging выполнена владельцем и подтверждена как успешная;
- production service, variables, volume и deployment history остались без изменений;
- Guide OS repository остался на commit `7f2d91049828f62e14cfbd509e0a5af7cedb83e1` с clean status; GuideShop не изменялся.

GuideShop Gate 3 readiness: готов `1/4` — public handoff Guide OS (`kid` `guide-os-staging-read-20260813-1f839319`, fingerprint `39a004…b366`). Не готовы HTTPS base URL, установка GuideShop public key и сохранение Guide OS private signing key в staging.

Следующая задача: минимально адаптировать provider runtime для безопасного Railway staging execution, сохранив production fail-closed. Ключи, source, deployment, domain и activation остаются отдельными последующими gates.

## 2026-08-13 — Railway staging provider runtime подготовлен

Выполнено Cursor и независимо проверено этим чатом:

- добавлен отдельный default-off flag `GUIDESHOP_LINK_PROVIDER_STAGING_ENABLED`;
- staging activation требует `APP_ENV=staging`, оба enabled flags, bind host `0.0.0.0`, валидный Railway `PORT` и непустой public-key allowlist при composition;
- staging path не использует fallback на локальный port `8081`;
- production activation при любых комбинациях flags остаётся fail-closed;
- development/test loopback behavior сохранён;
- endpoints, JWT/JTI policy, raw-token lifecycle, persistence и cleanup не изменялись;
- Railway, GuideShop, keys, source, deployment и domain не затрагивались.

Независимая проверка выполнена во временном isolated Python 3.13.14 environment в `/tmp`, поскольку существующий repository `venv` содержит broken symlink. Focused suite по provider, inbound auth, exchange lifecycle и environment documentation: `104 passed`. Полный suite: `588 passed`. `git diff --check` clean.

Изменения ещё не закоммичены. Следующая задача — один commit/push и успешная проверка GitHub CI до любых staging key/source/deployment действий.

## 2026-08-13 — Stage 9B Gate 2B завершён

Выполнено:

- в isolated Railway staging service через `--skip-deploys` установлены три утверждённые key variables;
- inbound allowlist содержит GuideShop public key с `kid` `guideshop-staging-link-20260813-b8375404`;
- Guide OS private signing key сохранён с `kid` `guide-os-staging-read-20260813-1f839319`;
- derived Guide OS public fingerprint совпал с handoff `39a004…b366` по SHA-256 DER SPKI;
- все GuideShop/provider flags остались выключены;
- source, start command, deployments и public domain отсутствуют;
- production и репозитории не изменялись в рамках gate;
- key material не выводился и временные key directories пока сохранены.

GuideShop Gate 3 readiness: `3/4`. Готовы inbound GuideShop public key, outbound Guide OS private signing key и Guide OS public handoff. Не готов только HTTPS base URL.

Перед последним infrastructure gate обнаружен архитектурный блокер: текущий provider запускается только из `bot.py`, который требует `BOT_TOKEN` и запускает Telegram polling. Для отдельного `guide-os-staging-api` требуется минимальный API-only entrypoint без Telegram runtime.

Отдельное наблюдение: production latest deployment baseline между Gate 2A и Gate 2B изменился с `ac1b8a97-85c9-478e-a80f-6827a5214c7f` на `26d2c035-e5a0-457f-a4af-17dd8204e549`. По evidence Gate 2B новое значение было неизменно before/after и не вызвано этим gate, но его происхождение должно быть проверено до staging deployment.

## 2026-08-14 — API-only staging entrypoint подготовлен

Выполнено Cursor и независимо проверено этим чатом:

- добавлен отдельный `guide_shop_link_api.py`, который не импортирует Telegram runtime или `BOT_TOKEN` configuration;
- entrypoint инициализирует SQLite и запускает только существующий Stage 5D provider;
- добавлен фиксированный безопасный `GET /health` на том же aiohttp app;
- health test использует socket-free direct handler resolution и не создаёт `ClientSession`;
- signal handlers удаляются только если entrypoint успешно установил их;
- runner cleanup сохраняет exactly-once behavior;
- существующие Stage 5D endpoints и JWT/JTI/raw-token/persistence contracts не изменены;
- Railway, GuideShop, keys, flags, deployment, domain и production не затрагивались.

Независимая проверка: focused suite `117 passed`; полный suite `601 passed`; `git diff --check` clean. Изменения ещё не закоммичены.

Следующая задача: commit/push API-only entrypoint и подтверждение clean-runner CI. После этого требуется отдельно проверить происхождение нового production latest deployment baseline до любых Railway source/deploy действий.

## 2026-08-14 — API-only staging entrypoint закоммичен и прошёл CI

Выполнено:

- commit `ac779b417b6adb50f43494cf4c0d25e6e292d646` (`Add API-only GuideShop staging provider`) отправлен в `origin/main`;
- commit содержит ровно семь ожидаемых code/test/Markdown файлов;
- focused suite: `117 passed`;
- полный suite: `601 passed`;
- `git diff --check` clean;
- GitHub CI run `31743087618` — success;
- Integration Contracts run `31743087697` — success;
- `main == origin/main`, working tree clean;
- Railway, GuideShop, keys, flags, source, deployment, domain и production не изменялись.

Следующая задача: read-only provenance audit production latest deployment `26d2c035-e5a0-457f-a4af-17dd8204e549`. До завершения аудита запрещены staging source connection, deployment, domain и feature activation.

## 2026-08-14 — Production deployment provenance audit завершён

Read-only audit установил:

- production deployment `26d2c035-e5a0-457f-a4af-17dd8204e549` был GitHub auto-deploy commit `d4198daaef01bc50a28633bedc2c9eb5759aa7cc` из `main`;
- deployment завершился `FAILED` на `BUILD_IMAGE`, не запускал runtime и никогда не становился active;
- последующий deployment `af558089…` аналогично был auto-deploy commit `ac779b417b6adb50f43494cf4c0d25e6e292d646` и также не стал active;
- production active deployment остался `1e048703-6848-4839-9ce2-f69129b9d839` (`SUCCESS`);
- production variables hash, volume, instances и active runtime не изменились;
- staging service сохранил отсутствие source, start command, deployments и domain;
- audit не выполнил Railway mutations и не затронул GuideShop или source code.

Вердикт: `SAFE TO PROCEED TO STAGING DEPLOYMENT GATE`.

Остаточный production risk: production `guide_os` подключён к GitHub `main`, поэтому каждый push создаёт новый failed production deployment attempt. Это не блокирует изолированный staging deploy, но требует отдельного будущего исправления production build/deployment flow.

## 2026-08-14 — Staging deployment gate заблокирован Railpack/mise

Выполнено:

- staging source подключён к Guide OS repository / `main` на exact commit `ac779b417b6adb50f43494cf4c0d25e6e292d646`;
- start command установлен как `python guide_shop_link_api.py`;
- выполнены один initial deployment и один разрешённый retry;
- deployments `0e861878-bb67-4619-8662-ed99ec02ddd2` и `2ebea9ce-e950-4dd9-98e6-932e40a20f68` детерминированно завершились `FAILED` до запуска приложения;
- Railpack v0.36.4 / mise не смог установить `python@3.13.1`: для precompiled artifact отсутствовала GitHub attestation;
- runtime, domain и health checks не были достигнуты;
- rollback вернул `GUIDESHOP_LINK_PROVIDER_ENABLED` и `GUIDESHOP_LINK_PROVIDER_STAGING_ENABLED` в `false`;
- production, GuideShop, keys, volume и repository source не изменялись.

GuideShop Gate 3 readiness остаётся `3/4`; HTTPS base URL отсутствует.

Официальная mise documentation подтверждает scoped build setting `MISE_PYTHON_GITHUB_ATTESTATIONS`. Следующий gate может временно установить его в `false` только для isolated staging, повторно включить provider flags и выполнить один deployment attempt. Это staging-only supply-chain exception; production использовать его запрещено.

## 2026-08-14 — Guide OS staging readiness 4/4

Выполнено:

- `MISE_PYTHON_GITHUB_ATTESTATIONS=false` установлен только в isolated staging service;
- глобальный `MISE_GITHUB_ATTESTATIONS` и production variables не изменялись;
- provider и staging authorization flags включены только в staging;
- единственный deployment attempt `5c098777-ba6e-40ad-ba03-83480b0e3596` завершён `SUCCESS` на exact commit `ac779b417b6adb50f43494cf4c0d25e6e292d646`;
- API-only process `python guide_shop_link_api.py` стал active без Telegram polling и `BOT_TOKEN`;
- staging volume `/data` остался `READY`;
- создан ровно один Railway HTTPS domain: `https://guide-os-staging-api-staging.up.railway.app`;
- три внешние HTTPS health checks вернули HTTP 200 и expected safe payload;
- дополнительная независимая проверка этим чатом также получила HTTP 200, `application/json` и expected parsed payload;
- production active runtime, variables, volume, source и instances не изменились;
- GuideShop и repository source не изменялись, secrets не раскрывались.

Вердикт: `PASS — GUIDE OS STAGING READINESS 4/4`. GuideShop может продолжить Gate 3, используя переданный HTTPS base URL и ранее переданный Guide OS public handoff. Production activation остаётся запрещённой.

## 2026-08-16 — GuideShop staging E2E handoff принят

Получено и принято как закрытие внешнего E2E gate:

- GuideShop Gate 4A lifecycle: `PASS`, `44/44`;
- подтверждён lifecycle `issue → exchange → awaiting → confirm → active → evidence → revoke`;
- raw-token replay и JTI replay отклонены;
- после проверки оставлена чистая active link;
- GuideShop Gate 4B reads: `PASS`;
- dataset evidence: Companies `1`, Visits `2`, Sales `4`, Points `2`, History `1`;
- auth/query/cursor matrix: `26/26`;
- FA/IC: `0 FAIL`;
- contract baseline: `v1.1.0`;
- GuideShop production release `v1.3.0` выполнен, но все integration flags остаются выключены.

GuideShop E2E больше не является блокером Guide OS release candidate. Production GuideShop integration включать запрещено.

Оставшиеся Guide OS production-release blockers:

1. read-only подтвердить отсутствие staging lifecycle variables в production;
2. исправить Railpack production build failure на candidate-ветке;
3. повторить full suite и staging deploy после исправления;
4. получить свежий backup production SQLite;
5. отделить `.ai`/docs изменения от runtime candidate;
6. повторно проверить exact merge diff;
7. только затем выполнить fast-forward/merge и наблюдать production deploy.

## 2026-08-16 — Production lifecycle absence audit завершён

Read-only audit подтвердил:

- `GUIDESHOP_STAGING_LIFECYCLE_ENABLED` отсутствует во всех production-effective scopes;
- `GUIDESHOP_STAGING_LIFECYCLE_JWT_PUBLIC_KEYS` отсутствует во всех production-effective scopes;
- семь GuideShop integration flags отсутствуют и эффективны как default-off;
- `MISE_PYTHON_GITHUB_ATTESTATIONS` и `MISE_GITHUB_ATTESTATIONS` отсутствуют в production;
- production service имеет только четыре user-set keys: `ADMIN_ID`, `BOT_TOKEN`, `DATABASE_PATH`, `TIMEZONE`;
- production before/after snapshots идентичны; audit не выполнил mutation;
- candidate commit `e49a5a7174a34e836dbf806b30b2c61ebdc69c48` уже имеет successful staging deployment `414fee35…` с staging-only build exception.

Вердикт: production lifecycle absence blocker закрыт.

Процессное замечание: во временной директории был создан ранний raw variable dump, затем удалён. До production release требуется подтвердить, что secret values не выводились в terminal/chat/log/history и не покидали локальный temp storage. При невозможности доказать containment затронутые production secrets должны быть ротированы.

Следующий blocker: устранить production Railpack build failure на candidate-ветке и доказать successful staging build без `MISE_PYTHON_GITHUB_ATTESTATIONS=false`.

## 2026-08-16 — Production-safe Railpack code gate завершён

Cursor подготовил минимальный uncommitted fix на candidate-ветке:

- `.python-version`: `3.13.1` → `3.13.14`;
- README фиксирует exact runtime и требование не отключать artifact verification;
- environment documentation test обновлён под новый pin;
- Python `3.13.14` dependency install и `pip check` прошли;
- focused tests: `2 passed`;
- full suite: `632 passed`;
- `git diff --check`: clean;
- attestation bypass в repository config не добавлен;
- Railway, production, GuideShop и integration flags не изменялись.

Причина прежнего failure: старый mise precompiled artifact Python `3.13.1` не имел GitHub attestation. Для выбранного Python `3.13.14` подтверждены attested artifact и успешная независимая verification.

Code gate: `PASS — ready for review`. Следующий этап: создать отдельный candidate commit только из трёх build-gate файлов, получить CI PASS, затем отдельным Railway gate удалить staging-only `MISE_PYTHON_GITHUB_ATTESTATIONS` и доказать staging deployment без bypass.

Обнаружено несоответствие в pre-existing dirty `docs/project_context.md`, где ещё указан Python `3.13.1`. Этот файл запрещено смешивать с runtime build commit; документация будет синхронизирована отдельным docs-gate.

## 2026-08-16 — Attested Python candidate commit и CI завершены

- branch: `staging-guide-user-lifecycle-api`;
- commit: `b89562294461b925755255ac48e9a53d65d0b071`;
- message: `Use attested Python runtime for Railpack builds`;
- commit содержит ровно `.python-version`, `README.md`, `tests/test_environment_documentation.py`;
- push в `origin/staging-guide-user-lifecycle-api` успешен;
- GitHub CI run `31942628286`: success;
- Integration Contracts run `31942628273`: success;
- branch синхронизирована с origin;
- `.ai/*` и pre-existing docs изменения остались вне commit;
- merge, Railway, production и GuideShop не изменялись.

Следующий gate: staging proof build exact commit `b895622…` после удаления staging-only `MISE_PYTHON_GITHUB_ATTESTATIONS`, с production before/after invariants и health verification.

## 2026-08-16 — Staging attestation proof завершён

- обнаруженный auto-deploy `382d5087…` не принят как proof, потому что был собран до удаления bypass;
- `MISE_PYTHON_GITHUB_ATTESTATIONS` удалён только из staging без implicit deployment;
- оба bypass key отсутствуют во всех staging scopes;
- выполнен ровно один controlled deployment `a79abd94-c7c8-4f61-b18b-9de3c136fbcd`;
- deployment exact commit `b89562294461b925755255ac48e9a53d65d0b071` завершён `SUCCESS`;
- Railpack запросил и установил Python `3.13.14`, GitHub artifact attestations verified;
- API-only start command остался `python guide_shop_link_api.py`;
- staging volume `/data` остался Ready;
- три HTTPS health checks вернули HTTP 200 и expected parsed JSON;
- production before/after идентичен;
- repositories и GuideShop не изменялись;
- secrets не печатались.

Вердикт: production-safe Railpack blocker закрыт. Следующий production-release blocker — fresh consistent backup production SQLite.

## 2026-08-16 — Production SQLite backup preflight завершён

Read-only preflight подтвердил:

- production database: expected `/data/guide_os.db`, WAL mode;
- size `139264` bytes, volume имеет около `4.5 GiB` free;
- runtime поддерживает Python `sqlite3.Connection.backup()`;
- raw copy live database запрещён;
- Railway поддерживает native volume-instance backups, но сейчас backup/schedule отсутствуют;
- binary-safe export возможен через Railway SSH с прямым перенаправлением stdout в local file без печати содержимого;
- production before/after invariants идентичны;
- rows, PII и secrets не читались и не печатались;
- никаких файлов, backups или infrastructure mutations не создано.

Вердикт: `NEEDS USER DECISION`. До mutation gate владелец должен утвердить destination, encryption/key custody и необходимость complementary Railway snapshot.

## 2026-08-16 — Production backup Gate 1 заблокирован Railway authorization

- owner утвердил Railway native snapshot + local age-encrypted copy;
- local destination создан с mode `700`, вне repositories и `/tmp`;
- `age v1.3.1` установлен;
- единственная попытка `volumeInstanceBackupCreate` завершилась `Not Authorized`;
- Railway backups/schedules после попытки: `0/0`;
- согласно gate ordering local online backup не запускался;
- container `/tmp` snapshot, plaintext и encrypted local files отсутствуют;
- production before/after invariants идентичны;
- secrets, rows, PII и binary data не печатались.

Вердикт: `BLOCKED` только для dual-backup варианта. Требуется либо authorized Railway identity, либо явное разрешение владельца продолжить с проверенной age-encrypted off-platform копией без native Railway snapshot.

## 2026-08-16 — Local age backup attempt прерван на interactive export

- owner разрешил local age-encrypted backup без Railway snapshot;
- consistent remote SQLite snapshot был создан и прошёл integrity check;
- export pipeline был terminated во время `age -p` prompt из-за совместного использования interactive terminal Railway SSH и age;
- encrypted target не создан;
- local plaintext files отсутствуют;
- remote `/tmp` snapshot удалён, `snapshot_gone=true`;
- production `/data` listing, source size и mtime не изменились;
- Railway native snapshot не повторялся.

Вердикт: backup всё ещё отсутствует. Для одной новой попытки требуется owner approval; corrected export должен изолировать Railway stdin/stderr от TTY, используемого `age`, без ослабления encryption или печати binary data.

## 2026-08-16 — Production SQLite encrypted backup завершён

- owner разрешил одну corrected retry без Railway native snapshot;
- fresh consistent online backup создан с UTC `20260816T122903Z`;
- encrypted artifact filename: `guide_os-prod-20260816T122903Z-b7ebbbcf.db.gz.age` (stored outside repositories);
- file mode `600`, size `17983`, SHA-256 `e0418a2b4f3a5fcdc544577aec25f7fe6a9c8fcb18d968d0d1e6dfd8bd43fee9`;
- remote/restored database SHA-256 совпали;
- remote/restored integrity checks: `ok`;
- schema inventory и per-table counts совпали без чтения/печати row contents;
- local и remote plaintext artifacts удалены;
- Railway native snapshot не повторялся;
- production before/after идентичен;
- repositories и GuideShop не изменялись;
- secrets/passphrase/PII/binary/base64 не печатались.

Локальная независимая проверка подтвердила encrypted file mode, size и SHA-256. Production backup blocker закрыт.

## 2026-08-16 — Docs separation commit завершён

- docs-only commit `dd04e4c0ac170a92d3ff37c627898d7c17ac6f76` создан на `staging-guide-user-lifecycle-api`;
- commit содержит ровно четыре `.ai/*.md` и два `docs/*.md` файла;
- staged sensitive-data scan и `git diff --cached --check` clean;
- CI run `31952195788` и Integration Contracts run `31952195720` successful;
- branch синхронизирована с origin, working tree clean;
- runtime, infrastructure, production и GuideShop не изменялись.

Следующий release blocker: read-only containment audit раннего raw production variable dump; при недостаточном доказательстве требуется ротация затронутого production secret.

## 2026-08-16 — Raw variable dump containment audit завершён

- raw Railway variable output был сначала записан в temp file, затем unsanitized прочитан через `head`;
- prefix попал в Cursor Shell tool stdout;
- raw file удалён, external upload/commit evidence отсутствует;
- строгий containment доказать невозможно из-за tool-result retention;
- единственный secret-bearing production user key в scope: `BOT_TOKEN`;
- `ADMIN_ID`, `DATABASE_PATH`, `TIMEZONE` credential rotation не требуют;
- production variables повторно не читались, secret values в audit не выводились;
- Railway, repositories, production и GuideShop не изменялись.

Вердикт: `ROTATION REQUIRED` только для production `BOT_TOKEN`. Ротацию следует объединить с контролируемым production release window после exact merge-diff review, чтобы не оставить bot offline на старом runtime и не вызвать build старого Python pin.
## 2026-08-18 — Company and Visit points production UI completed

- GuideShop production read API commit `94e876175fcbf8656049322a5ebe18a100c45527` deployed successfully;
- company reads now expose optional `phone`, `address`, `description` and `type` fields;
- points reads support an authorized optional `visit_id` filter;
- Guide OS production UI commit `45499389bc680fd08e85d7505e818537c811814a` deployed successfully;
- company cards show public details without opaque IDs;
- Visit details show the company name and points belonging to that Visit;
- the Sales button was removed from the guide-facing GuideShop menu while low-level compatibility remains;
- GuideShop full suite: `1924 passed`; Guide OS full suite: `712 passed`;
- both repositories passed hosted contract checks; production health and Telegram polling were successful;
- owner confirmed `Company Visit UI smoke PASS`;
- no business data, keys, flags or staging resources were changed during the UI release.
## 2026-08-18 — Final Visits and points UX completed

- GuideShop production commit `cd3895d9d7828d4ec1ad1e4e41ad30b90a7c96b0` добавил complete-scope points summary;
- GuideShop deployment `912823ec-bb75-4389-a241-c43697ffd452` успешно активирован;
- Guide OS production commit `0d6728949a86e5dad08b81164b6e3db1e24a8a19` выпустил финальный read-only UX;
- Guide OS deployment `0bc71c65-b13d-4e7e-bdfb-69f0f4e8dd74` успешно активирован;
- Visits показывают названия компаний, локальные даты, туристов и русские статусы без opaque IDs;
- pending и credited points показывают complete totals и разбивку по компаниям;
- Sales остаётся скрытым из guide-facing menu;
- GuideShop full suite: `1940 passed`; Guide OS full suite: `720 passed`;
- health, Telegram polling и read-only compatibility checks прошли;
- owner подтвердил `Final points UX smoke PASS`;
- variables, flags, keys, business rows и staging не изменялись.

## 2026-08-20 — Guide OS Stage 12A–12C completed

- contracts pin обновлён до immutable `v1.2.0` в commit `f09b0d2`;
- durable SQLite inbox, event deduplication и aggregate watermarks добавлены в commit `f55e2ae`;
- dedicated `guideshop:events` JWT, GET-only event feed client и CAS checkpoint добавлены в commit `494df56`;
- Stage 12C focused suite: `162 passed`; full suite: `769 passed`;
- CI run `32345976412` и Integration Contracts run `32345976382` successful;
- background polling, Telegram notifications, Railway, flags, staging и production не изменялись;
- следующий gate: Stage 12D notification processing без scheduler/runtime activation.

## 2026-08-20 — Guide OS Stage 12D notification processing completed

- pending inbox event атомарно переводится в `processing`, concurrent claim отправляет ровно одно уведомление;
- success переводит event в `delivered`, transient failure использует bounded retry, exhausted/invalid event — `dead_letter`;
- пять разрешённых event types отображаются безопасными русскими сообщениями;
- Visit и points notifications используют существующие GuideShop navigation/deep-link routes;
- focused suite: `63 passed`; full suite: `786 passed`; `git diff --check` clean;
- scheduler, background polling, runtime composition, Railway и flags не изменялись;
- следующий gate: Stage 12E default-off runtime composition.

## 2026-08-20 — Guide OS Stage 12E runtime composition code gate completed

- event worker подключён к `bot.py` строго через существующие events/notifications flags;
- events-only mode загружает одну bounded page на active identity без Telegram delivery;
- notifications mode обрабатывает не более 20 pending events за cycle;
- invalid notifications-without-events configuration fail-closed;
- cycle failure не завершает worker и не раскрывает exception data;
- shutdown отменяет worker и гарантирует link-provider cleanup;
- focused suite: `138 passed`; full suite: `803 passed`; `git diff --check` clean;
- Railway, live flags, staging и production не изменялись;
- следующий gate после commit/CI: controlled staging events-only activation.

## 2026-08-20 — Guide OS Stage 12 production release completed default-off

- Stage 12E commit `66ecfe515d02639005e9d235f4a54c07d3ea8366` fast-forwarded to `main` without force;
- production deployment `6e9c5fb8-e980-486a-a313-767f2577c0e2` reached SUCCESS and remained active;
- health, `/data`, GuideShop provider and Telegram polling passed;
- event worker did not start and no event-feed request occurred;
- `GUIDESHOP_EVENTS_ENABLED=false` and `GUIDESHOP_NOTIFICATIONS_ENABLED=false` remained unchanged;
- owner confirmed `Production Telegram smoke PASS`;
- GuideShop, staging, variables, keys and live data were unchanged;
- next stage: Stage 13 recovery before event activation.

## 2026-08-20 — Guide OS Stage 13A recovery code gate completed

- abandoned `processing` events старше пяти минут атомарно возвращаются в due `pending` либо переходят в `dead_letter` при exhausted attempts;
- manual dead-letter replay default dry-run и требует explicit `--apply`;
- каждый manual replay даёт ровно одну дополнительную попытку и общий предел 20;
- concurrent recovery/replay имеет одного победителя, stale worker не перезаписывает состояние;
- CLI выводит только sanitized counts и не требует bot runtime/BOT_TOKEN;
- focused suite: `76 passed`; full suite: `819 passed`; backup/restore и `git diff --check` green;
- events/notifications остаются OFF; внешние системы не изменялись;
- следующий gate: Stage 13B read-only reconciliation/gap report.

## 2026-08-21 — Guide OS Stage 13B reconciliation code gate completed

- добавлен strictly read-only SQLite reconciliation snapshot в `mode=ro` + `query_only`;
- отчёт считает inbox states, abandoned/DLQ, aggregate gaps/collisions, watermark и checkpoint anomalies;
- первый observed aggregate version больше 1 не считается gap автоматически;
- CLI возвращает только verdict и sanitized integer counts, не имеет mutation options;
- focused suite: `74 passed`; full suite: `834 passed`; WAL/backup/restore/quick_check green;
- внешние системы, flags и live data не изменялись;
- следующий gate: Stage 13C isolated recovery drill.

## 2026-08-21 — Guide OS Stage 13C isolated recovery drill completed

- initial reconciliation: `NEEDS_ATTENTION`;
- abandoned recovery selected 2: one returned to pending, one moved to dead-letter;
- manual replay selected/replayed 2 with exactly one additional attempt each;
- final reconciliation: `CLEAN`; inbox row count stayed 4, deleted rows 0;
- pre-mutation backup restored with original `NEEDS_ATTENTION`, matching schema/counts;
- source, final, backup and restored `PRAGMA quick_check`: `ok`;
- negative 20/20 dead-letter remained non-replayable and `NEEDS_ATTENTION`;
- temporary files cleaned; repositories and external systems unchanged;
- Stage 13 is complete; next action is default-off production release.

## 2026-08-21 — Guide OS Stage 13 production release completed

- `main` fast-forwarded without force to `27e016bd579e007e5310a4fa069f0e8987187c7c`;
- production deployment `0e714525-a8e9-4c7e-8d76-e9c61be7cb9f` reached SUCCESS with `/data` READY;
- health, GuideShop provider and Telegram polling passed;
- event worker did not start; recovery/replay/reconciliation commands were not executed;
- events/notifications remained OFF and no database maintenance write occurred;
- owner confirmed `Stage 13 Production smoke PASS`;
- next stage: Stage 14 observability/security/load gates.

## 2026-08-21 — Guide OS Stage 14A observability code gate completed

- event worker возвращает fixed low-cardinality cycle metrics и пишет один sanitized INFO summary за completed cycle;
- inbox snapshot считает states, due pending, abandoned processing, checkpoints и oldest due lag;
- pull/cleanup/recovery/notification/superseded/failure outcomes имеют отдельные counters;
- snapshot failure не завершает worker и не раскрывает exception data;
- default-off runtime не создаёт worker и не пишет event metrics;
- focused suite: `61 passed`; full suite: `847 passed`; WAL/backup/restore/quick_check green;
- внешние системы и flags не изменялись;
- следующий gate: Stage 14B security matrix.

## 2026-08-21 — Guide OS Stage 14B security matrix completed

- security matrix: `52 passed`; requested focused suite: `223 passed`; full suite: `899 passed`;
- JWT/scope, HTTP boundary, principal isolation, replay/conflict races, notification privacy, operational CLI и default-off проверены;
- mixed-principal page не создаёт inbox/checkpoint writes;
- единственный найденный дефект: argparse отражал attacker-controlled argument; исправлен fixed `action=EXECUTION_FAILURE`;
- sensitive scan clean, реальных network calls не было;
- events/notifications и внешние системы не изменялись;
- следующий gate: Stage 14C bounded load/failure tests.

## 2026-08-21 — Guide OS Stage 14C bounded load/failure gate completed

- добавлен только `tests/test_guide_shop_event_load.py`; runtime code не изменялся;
- проверены 40 events в двух страницах, 40 notifications в двух bounded batches, две изолированные identities и backlog 200 rows;
- concurrent identical ingestion дал 1 insert + 7 duplicates, concurrent distinct ingestion сохранил все 40 rows;
- checkpoint CAS дал одного winner и 9 rejected contenders без regression;
- SQLite lock contention завершился bounded retry без потери event;
- partial-page failure сохранил checkpoint, повторная доставка идемпотентно завершила ingestion;
- HTTP retry, fresh JWT/JTI, cleanup, cancellation, dead-letter и abandoned recovery прошли;
- Stage 14C module: `18 passed`; focused suite: `131 passed`; full suite: `917 passed`;
- `git diff --check` и sensitive scan clean; real network/Telegram calls отсутствовали;
- runtime defect не найден; следующий шаг — commit/CI, затем отдельный default-off production release.

## 2026-08-21 — Guide OS Stage 14 completed and CI green

- Stage 14C committed as `0ef25af5ff1c5d7bea0e0e63f39abeb0b4e959bd` on `stage14-event-load`;
- committed exactly `tests/test_guide_shop_event_load.py`;
- CI run `32395490995` и Integration Contracts run `32395491107` завершились success;
- Stage 14A observability, Stage 14B security и Stage 14C load/failure gates завершены;
- events/notifications остаются OFF; `main`, Railway и production не изменялись;
- следующий шаг — controlled default-off production release после явного разрешения владельца.

## 2026-08-21 — Guide OS Stage 14 production release completed

- `main` fast-forwarded без force до `0ef25af5ff1c5d7bea0e0e63f39abeb0b4e959bd`;
- production deployment `dc898131-683f-4f7e-8dcf-31363f032ded` достиг SUCCESS;
- health, `/data`, Telegram polling и GuideShop provider прошли;
- event worker не запускался и event-feed requests не выполнялись;
- `GUIDESHOP_EVENTS_ENABLED=false` и `GUIDESHOP_NOTIFICATIONS_ENABLED=false` сохранены;
- GuideShop production и Guide OS staging не изменялись;
- owner подтвердил `Stage 14 Production smoke PASS`;
- Stage 14 завершён; следующий этап — Stage 15 shared integration E2E без production activation.

## 2026-08-22 — Stage 15A shared event E2E code gate completed

- реальный GuideShop outbox/event-feed соединён с Guide OS JWT client, checkpoint, inbox, notification и reconciliation через in-process ASGI;
- покрыты `visit.created` и `points.accrual_updated`, две synthetic identities и principal isolation;
- duplicate replay не создаёт inbox rows или повторных notifications, checkpoint не регрессирует;
- partial-page failure, replay convergence, abandoned recovery, bounded dead-letter replay и final CLEAN reconciliation прошли;
- реальных network/Telegram calls и persistent test artifacts нет;
- исправлена CI portability: обычный suite делает safe skip без sibling repo, dedicated workflow fail-closed загружает GuideShop exact commit `4cf1c10b…`;
- local shared E2E: `1 passed`; focused: `311 passed`; full Guide OS: `919 passed, 1 skipped`; GuideShop events: `51 passed`;
- следующий шаг — commit/push Stage 15A и проверка dedicated shared E2E workflow.

## 2026-08-22 — Stage 15A cross-repository CI access blocked

- Stage 15A committed as `c2d6ba6c9096bae5ada1a62ad44487b99224f32b`;
- CI `32399953005` и Integration Contracts `32399952906` successful;
- Shared GuideShop Event E2E run `32399953190` failed before test execution on private GuideShop checkout with `Repository not found`;
- причина: standard Guide OS workflow token не имеет cross-repository доступа к private GuideShop;
- local required shared E2E остаётся PASS; runtime defect отсутствует;
- следующий шаг — узкий GuideShop contents read credential, затем rerun only failed shared workflow.

## 2026-08-22 — Existing cross-repository read credential confirmed

- Guide OS Actions secret list проверен без чтения значений;
- существующий secret `CONTRACTS_READ_TOKEN` создан `2026-08-11`;
- новый PAT создавать не требуется;
- следующий шаг — использовать secret только в private GuideShop checkout step и повторить shared E2E workflow.

## 2026-08-22 — Stage 15 shared integration E2E completed

- Stage 15 branch amended to `930759340a867113c6a78da64552936f5428597d`;
- `CONTRACTS_READ_TOKEN` используется только private GuideShop checkout step, credential masked и `persist-credentials: false`;
- GuideShop exact commit `4cf1c10b76303af6c5b1e95a26175a7ede1a3fc7` подтверждён workflow;
- CI `32456928158`, Integration Contracts `32456928115` и Shared GuideShop Event E2E `32456928148` successful;
- shared test реально выполнен: `1 passed in 1.09s`, skip отсутствует;
- Stage 15 завершён без GuideShop/Railway/live flag/data изменений;
- следующий шаг — controlled Guide OS main fast-forward default-off, затем Stage 16 canary pilot.

## 2026-08-22 — Stage 15 production release completed

- Guide OS `main` fast-forwarded без force до `930759340a867113c6a78da64552936f5428597d`;
- production deployment `918f7eb5-f1e3-4475-95a7-914440c93910` достиг SUCCESS;
- health, `/data`, Telegram polling и GuideShop provider прошли;
- event worker не запускался, event-feed requests отсутствовали;
- events/notifications остались OFF, variables unchanged;
- GuideShop production и Guide OS staging не изменялись;
- owner подтвердил `Stage 15 Production smoke PASS`;
- Stage 15 завершён; следующий этап — Stage 16 limited production canary.

## 2026-08-22 — Stage 16A production canary readiness blocked by GuideShop

- GuideShop production deployment `912823ec…` работает на `cd3895d…` и health 200;
- active GuideShop commit не содержит Stage 11B `3e8a760`, Stage 11C `a6299c7` или shared baseline `4cf1c10b…`;
- event outbox, `/integration/v1/me/events` и `guideshop:events` scope отсутствуют в production runtime;
- Guide OS production `9307593` healthy, events/notifications OFF;
- audit остановлен до DB/key/link inspection и без любых mutations;
- следующий шаг — GuideShop Stage 11 production candidate default-off в отдельном чате.

## 2026-08-22 — GuideShop Stage 11 production candidate code gate completed

- Stage 11 baseline перенесён поверх current production main `cd3895d…` без conflicts;
- добавлен единый production-safety gate в outbox routing boundary;
- events OFF сохраняет migrations/schema, но не создаёт outbox или aggregate-version rows;
- false→true не backfill старые records; true→false не удаляет rows и останавливает новые writes;
- feed disabled возвращает safe 503, enabled behavior сохраняется;
- Stage 11 focused: `54 passed`; full GuideShop: `1987 passed`; contracts: `56 passed` и `VALIDATION_OK`;
- следующий шаг — shared Guide OS E2E против corrected candidate, затем commit/push/CI без deploy.

## 2026-08-22 — GuideShop Stage 11 production candidate committed

- candidate commit `37a5bd185b45601e0abf2652622f77c21f1216ac` pushed on `stage11-production-candidate`;
- committed exactly 16 Stage 11 files; unrelated untracked files preserved;
- shared Guide OS E2E executed without skip: `1 passed`;
- GuideShop focused `54 passed`, full `1987 passed`, contracts `56 passed` и `VALIDATION_OK`;
- Integration Contracts run `32459956253` successful;
- events default OFF; main/Railway/live data unchanged;
- следующий шаг — controlled staging proof default-off.

## 2026-08-22 — GuideShop Stage 11 staging proof completed

- staging deployment `c2251e02-9c9e-4635-ae22-b859f068e792` SUCCESS на exact `37a5bd1`;
- combined runtime, API, bot polling, `/data` и health 200 прошли;
- migration создала Stage 11 tables/indexes/triggers, quick_check `ok`;
- business counts unchanged, outbox/version rows `0→0`;
- events OFF, unauthenticated event endpoint safe 503, JWT не создавался;
- GuideShop и Guide OS production остались unchanged и healthy;
- rollback не использовался;
- следующий шаг — controlled GuideShop production release default-off.

## 2026-08-22 — GuideShop Stage 11 production release completed

- GuideShop `main` fast-forwarded без force до `37a5bd185b45601e0abf2652622f77c21f1216ac`;
- production deployment `85816c2c-56e8-4e21-a337-c69c68ac6d72` SUCCESS;
- migration/schema, quick_check, health, API и bot polling прошли;
- business counts unchanged, outbox/version rows `0`, events/notifications OFF;
- final-main Integration Contracts run `32461168719` successful;
- baseline GuideShop General CI отсутствует; local full `1987 passed` и staging proof приняты как compensating evidence;
- owner подтвердил `GuideShop Stage 11 Production smoke PASS`;
- следующий шаг — Stage 16 final read-only canary preflight.

## 2026-08-22 — Stage 16 events-only activation rolled back safely

- GuideShop events=true variable update выполнен skip-deploy, activation deployment `c61809da…` failed на fixed `events_not_available` startup gate;
- Guide OS activation не начиналась;
- GuideShop rollback deployment `cde15216…` SUCCESS, events restored false;
- обе production systems healthy, notifications false, worker/cycles/notifications отсутствовали;
- outbox/inbox/checkpoints/watermarks пусты, reconciliation CLEAN, business mutations отсутствовали;
- exact blocker: устаревший hardcoded startup rejection после выпуска Stage 11;
- следующий шаг — минимальный GuideShop startup readiness fix и default-off release.

## 2026-08-22 — GuideShop event startup readiness fix completed

- obsolete unconditional `events_not_available` удалён;
- events=true теперь требует valid Ed25519 verification keys, approved event scope/operation, enabled non-empty allowlist и enabled bounded rate limit;
- missing/disabled/invalid guard fail-closed через fixed `events_incomplete` без config leakage;
- events=false не требует event credentials и сохраняет default-off behavior;
- outbox/feed/contracts/business schema не менялись;
- focused startup `62 passed`, Stage 11 `54 passed`, full GuideShop `2001 passed`;
- следующий шаг — commit/push/CI, затем staging events-on proof.

## 2026-08-22 — GuideShop startup readiness fix committed

- fix committed as `56e75ab4dcad10ff2976ed61e16c4b1cdccfa088`;
- committed exactly four readiness/validator test files;
- startup `62 passed`, Stage 11 `54 passed`, full GuideShop `2001 passed`;
- Integration Contracts run `32466862656` successful;
- main, Railway и flags unchanged;
- следующий шаг — controlled staging events-on proof.

## 2026-08-22 — GuideShop staging events-on proof completed

- candidate `56e75ab` deployed default-off as `4d3e188d…` and events-on as `937258be…`;
- readiness passed with allowlist enabled size 1 and rate limit 10/60;
- one authenticated `guideshop:events` request returned HTTP 200 and empty feed;
- outbox/version/business counts unchanged, quick_check `ok`;
- notifications remained OFF, no business mutation occurred;
- production systems remained unchanged and events OFF;
- следующий шаг — production release startup fix default-off.

## 2026-08-22 — GuideShop startup readiness production release completed

- GuideShop main fast-forwarded до `56e75ab4dcad10ff2976ed61e16c4b1cdccfa088`;
- production deployment `e3781829-289e-40a8-a18e-db82c0181194` SUCCESS;
- Integration Contracts run `32471455955` successful;
- health, quick_check, API и bot polling прошли;
- events/notifications OFF, outbox/version rows `0`, business counts unchanged;
- owner подтвердил `GuideShop startup fix smoke PASS`;
- следующий шаг — repeat Stage 16 events-only canary.

## 2026-08-22 — Stage 16 empty canary and Visit back-navigation fix

- GuideShop deployment `ed4c4fc5…` и Guide OS deployment `e44269cc…` запущены с events ON / notifications OFF;
- четыре empty worker cycles завершились HTTP 200, queues остались empty, reconciliation CLEAN;
- owner подтвердил `Stage 16 Empty canary smoke PASS`;
- при подготовке первого Visit найден UX bug: guide-search back открывал main menu и очищал flow;
- fix возвращает search→source type и results/no-results→search, сохраняя Visit FSM data;
- focused Visit tests `37 passed`, full GuideShop `2011 passed`;
- canary business-event step paused до commit/release UX fix.

## 2026-08-22 — Visit back-navigation released and events-only canary proven

- GuideShop main/deployment обновлены до `c6cbbf4` / `cfd82638…`;
- owner подтвердил `Visit back navigation smoke PASS`;
- normal Visit lifecycle создал `visit.created` v1 и `visit.completed` v2;
- Guide OS inbox содержит stale v1 + pending v2, checkpoint/watermark v2, reconciliation CLEAN;
- post-deployment event cycles green, notifications OFF и sends 0;
- следующий шаг — Guide OS notifications-only activation для ровно одного pending event.

## 2026-08-22 — Stage 16 production notification canary completed

- Guide OS deployment `9da4811d…` запущен с events/notifications ON;
- GuideShop events ON, GuideShop notifications OFF;
- pending `visit.completed` доставлен один раз: attempts/success `1/1`;
- inbox transition pending `1→0`, delivered `0→1`, stale remains `1`, dead-letter `0`;
- четыре дополнительные cycles не создали duplicate notification;
- checkpoint/watermark version `2`, reconciliation CLEAN;
- owner подтвердил `Stage 16 Notification smoke PASS`;
- deep link открыл правильный completed Visit с company name, local timestamps, tourist count и safe points empty state;
- Stage 16 завершён; следующий этап — Stage 17 observation текущего linked population.

## 2026-08-22 — Stage 17 production observation completed

- observation duration `10m11s`, completed worker cycles `22`;
- event feed HTTP 200×22, non-200/timeouts `0`;
- pulls successful `22`, failures/cleanup failures `0`;
- fetched/inserted/duplicate/stale during window `0/0/0/0`;
- inbox stable: stale `1`, delivered `1`, pending/processing/dead-letter `0`;
- checkpoint generation `2`, watermark version `2`, reconciliation CLEAN;
- GuideShop outbox/version stable `2/1`, business counts unchanged;
- deployments/flags/staging/Git unchanged, audit mutations absent;
- Stage 17 завершён; следующий этап — Stage 18 final closure audit.

## 2026-08-22 — Stage 18 final integration closure PASS

- runtime/data/security/operations closure — PASS; Stages 0–18 завершены, runtime integration work complete;
- Guide OS production: commit `930759340a867113c6a78da64552936f5428597d`, deployment `9da4811d-8987-467d-bcd8-8f667f6fd081`, events/notifications ON;
- GuideShop production: commit `c6cbbf48a7d0c0a6d133e724db2c39ce28a5ab3b`, deployment `cfd82638-bc76-4a87-b7db-dd0f6886a593`, events ON, notifications OFF;
- одна active link; GuideShop outbox `2`; один aggregate subject version `2`;
- Guide OS inbox stable: stale `1`, delivered `1`, pending/processing/dead-letter `0`;
- checkpoint generation `2`, watermark version `2`; notification attempts/successes `1/1`; duplicates `0`; reconciliation `CLEAN`;
- Stage 17 evidence: `10m11s`, `22` completed cycles, HTTP `200×22`, failures/retries/duplicates/DLQ `0`;
- owner notification/deep-link smoke и Visit back-navigation smoke — PASS;
- production/staging health, database quick checks, key compatibility, allowlist, rate limit, recovery, backup/restore, observability, security, load и shared E2E evidence — green;
- implementation gates отсутствуют; следующая деятельность — routine post-launch monitoring и incident response.

## 2026-09-02 — Future daily tips roadmap recorded

- one amount per user/calendar date, independent of tours;
- bot-first, then shared Web API and Mini App;
- implementation not started; canonical plan: `docs/TIPS_ROADMAP.md`.

## 2026-09-02 — GuideShop Mini App GSMA0 activated

- roadmap documented; application implementation not started;
- canonical plan: `docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`.
