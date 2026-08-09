# Guide OS — Next Task

> Обновлено: 2026-08-09

## Единственная следующая задача

Stage 4A — реализовать production-safe authenticated read-only HTTP client foundation для GuideShop.

## Цель

Подготовить Guide OS к чтению согласованных Stage 2A DTO через настраиваемый GuideShop API, сохраняя интеграцию default-off и не подключаясь к базе GuideShop.

## Требуемый результат

- строгие настройки base URL, service credential, timeout и retry limits;
- HTTPS обязательно вне test/development;
- async HTTP implementation существующего read-only client protocol;
- guide identity передаётся только из доверенного Guide OS context;
- ответы валидируются существующими Stage 2A DTO;
- ограниченные retries только для безопасных transient failures;
- безопасная обработка timeout, rate limit, unauthorized, forbidden, not found и invalid payload;
- fake и disabled clients сохраняют текущее поведение.

## Ограничения

- Не включать reads по умолчанию.
- Не подключаться напрямую к базе GuideShop.
- Не реализовывать linking completion, events или notifications.
- Не хранить GuideShop business data в SQLite.
- Не логировать credentials, response bodies, PII или payment data.
- Не менять Telegram UI и navigation.
- Не активировать staging/production без согласованного GuideShop endpoint и credentials.

## Definition of Done

- Клиент реализует существующий protocol без изменения DTO contract.
- Конфигурация fail-closed и разделяет environments.
- Ownership scope нельзя заменить пользовательским route/callback input.
- Retry/timeout/rate-limit поведение ограничено и протестировано.
- Ошибочные и чужие данные не достигают presentation layer.
- Focused и полный suite проходят; production flags остаются выключенными.
