# Guide OS — Next Task

> Обновлено: 2026-08-07

## Единственная следующая задача

Stage 2A — формализовать Guide OS-side integration contract и mock payloads до создания Telegram-экранов и подключения GuideShop.

## Цель

Зафиксировать стабильные модели входных данных, ошибок и событий, которые Guide OS сможет валидировать независимо от реального GuideShop API.

## Требуемый результат

- DTO для Company, Visit, Sale и points transaction;
- Decimal-compatible строки без `float`;
- UTC ISO 8601 timestamps;
- pagination envelope и стабильные identifiers;
- versioned event envelope;
- состояния cancelled, voided, corrected и reversed;
- безопасные error codes;
- валидные и негативные mock payloads;
- focused contract tests без сетевого подключения.

## Ограничения

- Не подключать GuideShop.
- Не добавлять HTTP server или production credentials.
- Не создавать Telegram UI на этом этапе.
- Не реализовывать события и уведомления.
- Использовать Minimal Change и существующие зависимости.
- Сохранить все текущие сценарии Guide OS.

## Definition of Done

- Контрактные решения согласованы с `GUIDE_OS_INTEGRATION_FOUNDATION.md`.
- Mock payloads покрывают успешные и негативные случаи.
- Focused contract tests и полный suite проходят.
- Нет сетевых вызовов, GuideShop coupling и production activation.
