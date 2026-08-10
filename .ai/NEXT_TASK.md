# Guide OS — Next Task

> Обновлено: 2026-08-10

## Единственная следующая задача

Начать GuideShop-side подготовку Stage 4B на Mac Neo: реализовать staging Integration API и EdDSA verifier по утверждённому контракту.

## Цель

Создать на стороне GuideShop минимальную безопасную read-only поверхность, необходимую для реального staging-подключения уже подготовленного Guide OS клиента.

## Требуемый результат

- GuideShop проверяет EdDSA JWT, обязательные headers/claims, TTL, audience, scope и `guide_os_id`;
- GuideShop разрешает identity только через активную безопасную связь профилей;
- доступны согласованные `/integration/v1/me/...` read-only endpoints;
- каждый endpoint возвращает только данные гида из проверенного token identity;
- ответы соответствуют Stage 2A DTO/API contract Guide OS;
- staging keys и configuration отделены от production;
- есть контрактные, авторизационные и cross-guide negative tests.

## Ограничения

- Работа выполняется в отдельном GuideShop checkout на Mac Neo.
- Не использовать прямой доступ Guide OS к базе GuideShop.
- Не передавать identity через URL, query или пользовательский payload.
- Не включать production activation, events или notifications.
- Не менять Guide OS до появления проверяемого staging API, кроме отдельно согласованных исправлений контракта.

## Definition of Done

- GuideShop staging verifier и read-only API доступны для интеграционных тестов.
- Утверждённые positive и cross-guide negative tests проходят.
- После этого разблокирован Stage 4B: реальное staging-подключение Guide OS.
