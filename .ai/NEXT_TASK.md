# Guide OS — Next Task

> Обновлено: 2026-08-12

## Единственная следующая задача

Передать Guide OS Stage 5D provider PASS в GuideShop и подготовить Stage 6 isolated HTTP E2E.

## Цель

Проверить совместимость уже готовых GuideShop Stage 5E consumer и Guide OS Stage 5D provider через изолированную реальную локальную HTTP-границу без production deployment.

## Требуемый результат

- GuideShop принимает независимый Stage 5D PASS и повторно сверяет contract `v1.1.0`;
- используются только временные isolated keys, test DB и loopback URL;
- выполняется create → awaiting confirmation → evidence → active → revoke/conflict lifecycle;
- проходят wrong-key/scope/audience, JTI replay, raw-token replay и isolation negative cases;
- GuideShop registry и Guide OS exchange/evidence согласуются по IDs, status и UTC timestamps;
- после проверки временные ключи удаляются, оба feature flag возвращаются в `off`.

## Ограничения

- Stage 6 начинается только после принятия Stage 5D PASS в чате GuideShop.
- Не использовать production/staging credentials или публичный endpoint.
- Не выполнять Railway deployment, production activation, events или notifications.
- Не использовать прямой межсистемный доступ к SQLite.
- Не начинать read API до успешного Stage 6 gate.

## Definition of Done

- Positive lifecycle и auth/replay/isolation negative matrix проходят через real local HTTP.
- DB/audit/evidence reconciliation не имеет необъяснимых расхождений.
- Temporary secrets удалены, flags выключены, production не затронут.
- После этого разблокирован следующий GuideShop-first этап — read API.

## Зафиксировано для последующей работы

После базовой read-only интеграции отдельно проектируются личные места и self-reported external sales. Они хранятся в Guide OS и не создают глобальные компании GuideShop. Возможная отправка points claim в GuideShop является отдельным будущим write contract и не входит в текущую задачу.
