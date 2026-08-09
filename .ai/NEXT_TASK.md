# Guide OS — Next Task

> Обновлено: 2026-08-09

## Единственная следующая задача

Stage 4D — реализовать Guide OS EdDSA access-token provider по утверждённому Stage 4C contract.

## Цель

Безопасно выпускать короткоживущий identity-bound Bearer JWT для существующего Stage 4A HTTP client, не активируя реальный runtime.

## Требуемый результат

- immutable strict signing settings;
- Ed25519 private-key loading только из injected secret/environment;
- async provider, реализующий существующий `GuideShopAccessTokenProvider`;
- strict header `alg=EdDSA`, `typ=guideshop-service+jwt`, allowlisted `kid`;
- claims из Stage 4C с TTL 60 секунд и unique 128-bit `jti`;
- injectable UTC clock и cryptographic randomness;
- safe errors без key/token/identity leakage;
- deterministic contract и negative security tests.

## Ограничения

- Не создавать и не коммитить реальные production keys.
- Не добавлять token в логи, exceptions или persistent storage.
- Не подключать provider в `bot.py` и не включать reads.
- Не реализовывать GuideShop verifier в этом repository.
- Не менять HTTP endpoints, UI, navigation, linking, events или notifications.
- Не использовать symmetric shared secret или алгоритм, выбираемый из JWT header.

## Definition of Done

- Provider удовлетворяет существующему runtime-checkable protocol.
- Каждый вызов создаёт новый signed token только для переданного trusted `guide_os_id`.
- Header и claims точно соответствуют Stage 4C.
- Invalid key/settings/identity fail before token return.
- Tests независимо проверяют signature и все claims через public key.
- Production runtime остаётся fail-closed и default-off.
