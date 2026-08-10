# Guide OS — Next Task

> Обновлено: 2026-08-10

## Единственная следующая задача

Подготовительный quality gate — continuous integration для Guide OS.

## Цель

Проверять clean checkout Guide OS на каждом push/PR без Telegram, production secrets или GuideShop API.

## Требуемый результат

- минимальный GitHub Actions workflow;
- Python 3.13.1;
- dependency install из `requirements.txt`;
- полный `pytest -q` на clean checkout;
- dependency consistency/import verification;
- pip cache без repository secrets;
- concurrency cancellation для устаревших runs;
- no deployment, Telegram polling или GuideShop network calls.

## Ограничения

- Не менять Python runtime logic и tests ради CI.
- Не добавлять repository secrets или `.env`.
- Не запускать `bot.py`.
- Не выполнять deployment/push в Railway.
- Не добавлять GuideShop API, events или notifications.
- Не вводить lint/type gates, которых проект пока не использует.

## Definition of Done

- Workflow запускается на push и pull request.
- Clean checkout устанавливает pinned dependencies и выполняет полный suite.
- CI не требует BOT_TOKEN или других secrets.
- Workflow не запускает Telegram/network/deployment behavior.
- Stage 4B остаётся заблокированным до GuideShop staging API/verifier.
