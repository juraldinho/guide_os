# Guide OS — Current Development Session

> Обновлено: 2026-08-10

## Текущий фокус

Подготовка перехода к GuideShop-side разработке на Mac Neo. Доступная до GuideShop работа в Guide OS завершена.

## Завершённые этапы

- Stage 0;
- Stage 1A/1B — identity и linking requests;
- Stage 2A — DTO/event contract;
- Stage 3A — flags/client boundary;
- Stage 3B — navigation tokens;
- Stage 3C1 — presentation/keyboards;
- Stage 3C2 — feature-gated mock Telegram UI.
- Stage 3D — user-bound `/start` deep links и development smoke helper.
- Stage 4A завершён: HTTP client, identity composition, EdDSA auth и default-off real runtime готовы.
- Stage 4B ещё не начат и требует GuideShop staging API на Mac Neo.
- Reproducible-environment и continuous-integration quality gates завершены.

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
- Python runtime зафиксирован как `3.13.1`;
- documentation/full suite: `1 passed` / `471 passed`.
- CI portability fix: focused `14 passed`, полный suite `472 passed`.
- GitHub Actions run `31408186374` для commit `785a780` завершён успешно.

## Следующее действие

Согласно `.ai/NEXT_TASK.md`, начать на Mac Neo GuideShop-side staging API и EdDSA verifier. После их готовности вернуться в Guide OS к Stage 4B staging connection.

## Зафиксированное будущее требование

- Личные неофициальные места и self-reported external sales принадлежат аккаунту гида в Guide OS.
- Записи разных гидов не объединяются в глобальный каталог GuideShop.
- GuideShop остаётся владельцем официального points balance и позже может принимать минимальные идемпотентные claims по `external_sale_id`.
- Это отдельный post-MVP write workstream после базовой read-only интеграции; налоговая, redemption и anti-fraud модель ещё требует решения.

## Production gate

GuideShop API, shared staging, E2E, recovery и live production-safety evidence обязательны до production activation.

## Ограничения сессии

- Исходный код изменяет только Cursor.
- Этот чат анализирует, проектирует, проверяет и обновляет Markdown.
- Minimal Change; никаких несвязанных изменений.
