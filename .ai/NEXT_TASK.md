# Guide OS — Next Task

> Обновлено: 2026-08-07

## Единственная следующая задача

Stage 3C — добавить feature-gated Telegram entry point и базовые GuideShop list/detail экраны на explicit in-memory fake client.

## Цель

Проверить Telegram UX, маршрутизацию и состояния экранов до подключения реального GuideShop API.

## Требуемый результат

- пункт входа GuideShop, скрытый при выключенном reads flag;
- home menu: компании, визиты, продажи, баллы и история;
- list/detail rendering из Stage 2A DTO;
- inline keyboards через Stage 3B navigation tokens;
- состояния empty, unavailable, forbidden и not found;
- возврат назад без raw object IDs в callback data;
- explicit fake composition только для development/test;
- handler/service tests и ручной Telegram smoke checklist.

## Ограничения

- Не реализовывать HTTP client.
- Не подключать GuideShop.
- Не включать integration по умолчанию.
- Не помещать object IDs или PII в callback data.
- Не сохранять GuideShop business data в SQLite.
- Не реализовывать `/start` deep-link entry и notifications на этом этапе.
- Сохранить существующее главное меню при выключенном flag.

## Definition of Done

- При default-off существующий UX не меняется.
- При explicit development fake доступны базовые read-only экраны.
- Все callback transitions используют user-bound navigation tokens.
- Empty/error/not-found состояния безопасны.
- Focused tests и полный suite проходят.
- Ручной smoke test выполняется на локальном `@Guideosbot` без production activation.
