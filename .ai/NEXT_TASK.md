# Guide OS — Next Task

> Обновлено: 2026-08-09

## Единственная следующая задача

Stage 4C — утвердить service authentication contract Guide OS ↔ GuideShop.

## Цель

Выбрать и зафиксировать один production-механизм получения короткоживущего Bearer token до реализации access-token provider и GuideShop verification endpoint.

## Требуемый результат

- решение: OAuth2 client credentials или asymmetric signed JWT;
- threat model и trust boundaries;
- точные token claims/fields, issuer, audience, subject, guide identity и scopes;
- TTL, clock skew, replay protection и `jti` policy;
- key/secret storage, rotation, revocation и environment separation;
- failure/status contract между Guide OS и GuideShop;
- staging bootstrap и production activation checklist;
- согласованный план реализации обеих сторон без добавления credentials в repository.

## Ограничения

- На этом шаге не менять исходный код.
- Не создавать реальные keys/secrets.
- Не помещать credentials или token examples с рабочими значениями в Git.
- Не активировать reads в staging/production.
- Не проектировать events/notifications раньше завершения read-only authentication.
- Учитывать разные filesystem/deployment paths Guide OS и GuideShop на Mac Neo/Railway.

## Definition of Done

- Выбран ровно один production auth mechanism с обоснованием.
- GuideShop может независимо проверить service identity, guide scope, audience, expiry и scopes.
- Replay, rotation, revocation и clock skew имеют конкретные правила.
- Staging и production credentials полностью разделены.
- Документ определяет следующую реализационную задачу отдельно для Guide OS и GuideShop.
- До согласования contract production composition остаётся fail-closed.
