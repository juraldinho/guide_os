# Guide OS — Development Log

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

Проверка: Stage 3C2 — `40 passed`; полный suite — `220 passed`; `git diff --check` clean. Локальная кнопка подтверждена в `@Guideosbot`.

Остаточный риск: token consumes до Telegram edit; восстановление выполняется повторным входом в GuideShop.

## 2026-08-09 — Stage 3D завершён

Выполнено:

- добавлен строгий builder `https://t.me/<bot>?start=<opaque-token>`;
- GuideShop handler принимает только точный `gs_` payload и зарегистрирован до generic `/start`;
- deep links используют существующие typed routes и user-bound single-use navigation tokens;
- disabled, stale, access-denied и invalid-route состояния отображаются безопасно;
- обычный `/start` и посторонние payload сохраняют прежний flow;
- добавлен development-only локальный helper для выпуска smoke-test ссылки без Telegram-команды.

Проверка: deep-link и helper regression — `58 passed`; полный suite — `278 passed`; `git diff --check` clean. Ручная проверка в `@Guideosbot`: первое открытие показало Visits, повторное открытие вернуло stale-link state.

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

Проверка: runtime/handlers/deep-links — `124 passed`; полный suite — `420 passed`; `git diff --check` clean. Ручной fake smoke test в `@Guideosbot` успешен: entry, Visits и возврат работают без изменений.

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

Stage 4B не начат и ожидает GuideShop staging API/verifier на Mac Neo.

## 2026-08-10 — Quality gate: воспроизводимое окружение

Выполнено:

- добавлен sanitized `.env.example` со всеми текущими core и GuideShop variables;
- все GuideShop flags default-off, API/JWT secrets отсутствуют;
- Python runtime зафиксирован как `3.13.1`;
- README описывает fresh macOS setup, tests, local fake и security rules;
- текущий Mac, Mac Neo и Railway явно разделены как независимые environments;
- virtual environments запрещено копировать между машинами;
- уточнено, что audit observation о broken `venv` относится к отдельному checkout на Mac Neo.

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

Подготовительные Guide OS quality gates завершены. Следующая интеграционная работа — Stage 4B после реализации GuideShop staging API/verifier на Mac Neo.

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

- staging source подключён к `juraldinho/guide_os` / `main` на exact commit `ac779b417b6adb50f43494cf4c0d25e6e292d646`;
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
