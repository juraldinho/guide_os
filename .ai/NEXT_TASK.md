# Guide OS — Next Task

> Обновлено: 2026-08-16

## Единственная следующая задача

Создать отдельный docs-only commit из проверенных Markdown-изменений и получить CI PASS.

## Цель

Зафиксировать проверенный operational/project documentation state отдельным commit без изменения runtime candidate или infrastructure.

## Требуемый результат

- commit содержит ровно четыре `.ai/*.md` и два `docs/*.md` файла;
- sensitive/staleness scan и `git diff --check` проходят;
- branch pushed без merge;
- hosted CI workflows проходят на exact docs commit;
- working tree становится clean.

## Ограничения

- Не изменять файлы перед staging; текущий Markdown diff уже reviewed.
- Abort, если staged set содержит не ровно шесть утверждённых Markdown-файлов.
- Не включать secrets, production data или backup paths/passwords в repository docs.
- Не менять runtime source/tests/config.
- Не merge/tag/release.
- Не затрагивать GuideShop или integration flags.

## Definition of Done

- Docs-only commit создан и pushed.
- CI/Integration Contracts successful.
- Working tree clean.
- Runtime candidate и infrastructure неизменны.
- Production и GuideShop не затронуты.

## Зафиксировано для последующей работы

После docs separation потребуется raw-dump containment resolution и exact release-candidate merge diff. Production integration flags обеих систем остаются выключенными.

Production backup PASS: encrypted artifact существует вне repositories с mode `600`; integrity и restore reconciliation прошли. Railway native snapshot отсутствует из-за permission limitation и не является release blocker после owner-approved off-platform backup.
