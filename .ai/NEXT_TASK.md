# Guide OS — Next Task

> Обновлено: 2026-08-13

## Единственная следующая задача

Закоммитить и отправить проверенный API-only staging entrypoint, затем подтвердить GitHub CI.

## Цель

Получить immutable commit и clean-runner evidence для API-only процесса до подключения Railway source или deployment.

## Требуемый результат

- один commit включает API-only entrypoint, health route, focused tests и актуальную `.ai`-документацию;
- commit отправлен в `origin/main`;
- CI и Integration Contracts workflow для точного commit успешны;
- рабочая директория clean и `main == origin/main`;
- Railway source, deployment, domain и flags не меняются.

## Ограничения

- Не менять уже проверенный implementation/test diff, кроме обязательной документации.
- Не устанавливать и не читать staging key material.
- Не подключать Railway source и не создавать deployment/domain.
- Не менять Railway variables и не включать flags.
- Не менять production или GuideShop.

## Definition of Done

- Commit создан и отправлен.
- GitHub clean-runner checks успешны.
- Commit содержит только ожидаемые файлы и не содержит secrets/runtime artifacts.
- Локальная ветка синхронизирована и clean.
- Railway, production, GuideShop и keys не затронуты.

## Зафиксировано для последующей работы

После этого отдельными gates выполняются: установка staging keys, source/deployment, HTTPS domain, provider activation и E2E. GuideShop Gate 3 продолжается только после явного подтверждения readiness `4/4`.
