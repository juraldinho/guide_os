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
