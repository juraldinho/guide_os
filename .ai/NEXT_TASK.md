# Guide OS — Next Task

> Обновлено: 2026-08-07

## Единственная следующая задача

Stage 3B — реализовать внутренние GuideShop routes и короткие server-side navigation tokens для Telegram callbacks/deep links без создания экранов.

## Цель

Подготовить безопасную маршрутизацию к Visit, Sale и points transaction, не помещая длинные IDs, credentials или персональные данные в callback/deep link.

## Требуемый результат

- typed route model для home, lists и object details;
- разрешённые route kinds и обязательные параметры;
- короткий криптографический navigation token;
- хранение только hash токена и server-side route payload;
- TTL, привязка к Telegram user ID и одноразовое либо ограниченное использование;
- revoke/expiry и безопасные domain errors;
- payload size, callback safety и cross-user negative tests;
- отсутствие Telegram UI и реальных GuideShop calls.

## Ограничения

- Не добавлять handlers или keyboards.
- Не подключать GuideShop и HTTP.
- Не помещать object IDs в публичный token.
- Не помещать token/PII в логи.
- Не переиспользовать linking tokens как navigation tokens.
- Не включать integration flags.
- Сохранить все существующие сценарии Guide OS.

## Definition of Done

- Navigation tokens короткие, opaque, expiring и user-bound.
- Другой Telegram user не может разрешить token.
- Route payload валидируется до сохранения и после чтения.
- Raw token не хранится.
- Focused tests и полный suite проходят.
- Нет Telegram UI, network calls и production activation.
