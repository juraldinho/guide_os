# Guide OS — Next Task

> Обновлено: 2026-08-16

## Единственная следующая задача

Провести финальный read-only exact release-candidate diff review перед production release window.

## Цель

Доказать точный состав `origin/main..staging-guide-user-lifecycle-api`, отсутствие неожиданных изменений и готовность к fast-forward release с одновременной ротацией production `BOT_TOKEN`.

## Требуемый результат

- зафиксированы exact base/head SHA и merge-base;
- подтверждена возможность fast-forward `main` к candidate head;
- каждый changed runtime/config/test/docs file классифицирован;
- повторены full suite, diff checks и sensitive/artifact scans;
- staging active deployment и production baseline сопоставлены с candidate/base;
- подготовлен один атомарный release plan: BotFather revoke/new token → Railway variable set without implicit deploy → fast-forward main → single production deploy → Telegram smoke.

## Ограничения

- Gate строго read-only: не merge/push/deploy и не ротировать token.
- Не читать production secret values.
- Не менять Railway, production или GuideShop.
- Не включать integration flags; они остаются off/default-off.
- Не включать secrets, production data или backup paths/passwords в repository docs.
- Не менять runtime source/tests/config.
- Не merge/tag/release.
- Не затрагивать GuideShop или integration flags.

## Definition of Done

- Verdict `READY FOR CONTROLLED RELEASE` либо точный blocker.
- Exact merge diff, tests и release/rollback procedure проверены.
- Production, repositories и GuideShop неизменны.
- Runtime candidate и infrastructure неизменны.
- Production и GuideShop не затронуты.

## Зафиксировано для последующей работы

После PASS выполнить единое controlled release window с обязательной ротацией `BOT_TOKEN`. Production integration flags обеих систем остаются выключенными.

Production backup PASS: encrypted artifact существует вне repositories с mode `600`; integrity и restore reconciliation прошли. Railway native snapshot отсутствует из-за permission limitation и не является release blocker после owner-approved off-platform backup.
