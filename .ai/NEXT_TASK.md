# Guide OS — Next Task

> Обновлено: 2026-08-29

## Завершённое состояние

Интеграционные Stages 0–18 завершены. Production pipeline работает по схеме GuideShop outbox/feed → Guide OS inbox/deduplication → Telegram notification/deep link. GuideShop остаётся источником истины для Visits и points; Guide OS отвечает за безопасную доставку Telegram-уведомлений и read-only переход к актуальному состоянию.

Финальное production-состояние:

- Guide OS commit `930759340a867113c6a78da64552936f5428597d`, deployment `9da4811d-8987-467d-bcd8-8f667f6fd081`, events/notifications ON;
- GuideShop commit `c6cbbf48a7d0c0a6d133e724db2c39ce28a5ab3b`, deployment `cfd82638-bc76-4a87-b7db-dd0f6886a593`, events ON и GuideShop notifications OFF;
- одна active link; outbox `2`; один aggregate subject version `2`;
- inbox: stale `1`, delivered `1`, pending/processing/dead-letter `0`;
- checkpoint generation `2`, watermark version `2`;
- notification attempts/successes `1/1`, duplicates `0`, reconciliation `CLEAN`;
- owner notification/deep-link smoke и Visit back-navigation smoke — PASS;
- Stage 17: `10m11s`, `22` worker cycles, HTTP `200×22`, failures/retries/duplicates/DLQ `0`;
- Stage 18 runtime/data/security/operations closure — PASS.

## Текущая разработка

Stage 19 завершён и выпущен в Guide OS production.

- Stage 19A audit — PASS: архитектурного blocker нет.
- Stage 19B persistence/ownership — PASS.
- Stage 19C/19D personal-place Telegram UX — PASS.
- Production commit `be1717921319d5650288ec245b0a8364212f3b39`, deployment `5408aa69-33a0-4052-883c-e3d0c7716167`, health PASS.
- Owner production smoke — PASS.
- Личные места и комиссии хранятся только в Guide OS; GuideShop official sales/points не изменялись.
- Mini-app foundation вынесен в отдельную ветку/чат и не является текущей задачей этого документа.

## Единственная следующая задача

Routine post-launch monitoring и incident response. Новая product-разработка начинается только после выбора владельцем следующего roadmap item.

## Зафиксированный будущий roadmap

Google Calendar one-way import для Mini App утверждён как будущая функция, но ещё не активирован для разработки. Импортированное событие сможет стать полноценным Guide OS туром после дополнения пользователем. Канонический план GC0–GC13: `docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md`.

Дневные чаевые утверждены как отдельный будущий bot-first roadmap: одна сумма на пользователя и календарную дату, независимо от туров; shared foundation → Telegram bot → owner validation → Web API → Mini App. Реализация не начата. Канонический план TIP0–TIP10: `docs/TIPS_ROADMAP.md`.

## Активированный Mini App workstream

Владелец активировал GuideShop Mini App. Следующий этап — **GSMA0: product/API audit и точный contract**, без немедленного изменения application code. Затем отдельным change выполняется GSMA1 horizontal scalable bottom navigation.

Official GuideShop остаётся read-only; личные компании и комиссии должны переиспользовать существующие `personal_places`, `personal_place_entries` и shared services. Канонический план GSMA0–GSMA10: `docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`.
