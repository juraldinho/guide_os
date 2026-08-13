# Guide OS — Next Task

> Обновлено: 2026-08-13

## Единственная следующая задача

Закоммитить и отправить проверенные изменения Railway staging provider runtime, затем подтвердить успешный GitHub CI.

## Цель

Создать единый проверяемый commit, синхронизировать `main` с `origin/main` и получить clean-runner evidence до установки staging keys или подключения Railway source.

## Требуемый результат

- один commit включает четыре source/test/config изменения и актуальную `.ai`-документацию;
- commit отправлен в `origin/main`;
- GitHub CI и Integration Contracts workflow, если он запускается для commit, завершаются успешно;
- локальная рабочая директория после push чистая;
- реальные keys, Railway source, deployment, domain и provider activation отсутствуют.

## Ограничения

- Не изменять проверенный source/test diff перед commit, кроме необходимой Markdown-документации.
- Не устанавливать и не читать staging key material.
- Не подключать Railway source и не создавать deployment/domain.
- Не менять Railway variables и не включать flags.
- Не менять production или GuideShop.
- Не включать в commit `.env`, databases, caches, logs, temporary environments или key material.

## Definition of Done

- Commit создан и отправлен в `origin/main`.
- GitHub clean-runner checks успешны.
- `main` синхронизирована с `origin/main`.
- Рабочая директория clean.
- Railway, production, GuideShop и keys не затронуты.

## Зафиксировано для последующей работы

После этого отдельными gates выполняются: установка staging keys, source/deployment, HTTPS domain, provider activation и E2E. GuideShop Gate 3 продолжается только после явного подтверждения readiness `4/4`.
