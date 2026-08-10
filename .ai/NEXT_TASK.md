# Guide OS — Next Task

> Обновлено: 2026-08-10

## Единственная следующая задача

Подготовительный quality gate — воспроизводимое окружение Guide OS.

## Цель

Документировать безопасную установку и конфигурацию текущего Guide OS без изменения runtime behavior и без добавления секретов.

## Требуемый результат

- sanitized `.env.example` со всеми обязательными и optional переменными;
- GuideShop flags default-off и без реальных token/key values;
- зафиксированная версия Python 3.13.1 для текущего Guide OS runtime;
- README-инструкция создания `venv`, установки requirements, тестов и запуска;
- явное различие текущего Mac, Railway и Mac Neo paths/environments;
- проверка, что clean configuration не раскрывает secrets и не включает GuideShop.

## Ограничения

- Не менять Python runtime logic.
- Не добавлять реальные BOT_TOKEN, ADMIN_ID, JWT keys или API URLs.
- Не включать GuideShop flags по умолчанию.
- Не добавлять machine-specific absolute paths.
- Не объявлять Mac Neo `venv` дефектом текущего Mac.
- Не добавлять GuideShop API, events или notifications.

## Definition of Done

- Новый developer может создать окружение из repository instructions.
- `.env.example` содержит только placeholders и safe defaults.
- Python version одинаково зафиксирована для local/CI deployment guidance.
- Existing imports/tests проходят без изменений runtime logic.
- Stage 4B остаётся заблокированным до GuideShop staging API/verifier.
