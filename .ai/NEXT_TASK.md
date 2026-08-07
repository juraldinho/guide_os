# Guide OS — Next Task

> Обновлено: 2026-08-07

## Единственная следующая задача

Stage 3A — добавить безопасные feature flags и mockable GuideShop client boundary без сетевого подключения.

## Цель

Создать отключённую по умолчанию границу интеграции, через которую будущие Telegram-сервисы смогут получать уже валидированные DTO, не связываясь напрямую с HTTP implementation.

## Требуемый результат

- отдельные flags для GuideShop reads, linking, events и notifications;
- все flags выключены по умолчанию;
- строгий client protocol/interface для read-only operations;
- disabled client, который не выполняет сеть и возвращает безопасную domain error;
- in-memory fake client для будущих экранов и тестов;
- методы companies, visits/detail, sales/detail, points/detail и history;
- focused tests на default-off, отсутствие сети и DTO boundary.

## Ограничения

- Не реализовывать HTTP client.
- Не подключать GuideShop.
- Не добавлять credentials.
- Не изменять Telegram UI.
- Не сохранять GuideShop business data в SQLite.
- Не реализовывать события или уведомления.
- Сохранить текущие сценарии Guide OS.

## Definition of Done

- Integration flags безопасно выключены по умолчанию.
- Disabled client не выполняет network/database operations.
- Fake client возвращает только Stage 2A DTO.
- Focused tests, Stage 1/2 regression и полный suite проходят.
- Нет production activation и GuideShop coupling.
