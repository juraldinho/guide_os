# Guide OS — Next Task

> Обновлено: 2026-08-09

## Единственная следующая задача

Stage 3C2 — подключить feature-gated Telegram handler, main-menu entry и обработку Stage 3B navigation callbacks на explicit development fake.

## Цель

Сделать mock-backed GuideShop screens доступными в локальном Telegram-боте без подключения GuideShop и без изменения default-off production UX.

## Требуемый результат

- кнопка `🛍 GuideShop` только при reads-enabled;
- handler входа и callback dispatcher для typed routes;
- разрешение token только для `callback.from_user.id`;
- рендер Stage 3C1 screen и keyboard;
- безопасные expired/consumed/revoked/access-denied ответы;
- explicit fake composition только в development/test;
- router registration без нарушения существующих handlers;
- handler tests и ручной smoke test на `@Guideosbot`.

## Ограничения

- Не реализовывать HTTP client.
- Не подключать GuideShop.
- Не включать reads по умолчанию.
- Не помещать IDs/PII в callback data или логи.
- Не добавлять `/start` deep links и notifications.
- Не сохранять GuideShop business data в SQLite.
- Сохранить существующий main menu при выключенном flag.

## Definition of Done

- Default-off UX полностью совместим с текущим ботом.
- Explicit local development mode открывает mock GuideShop screens.
- Все callbacks используют user-bound single-use tokens.
- Error states безопасны и не раскрывают route/token details.
- Focused handler tests и полный suite проходят.
- Ручной smoke test на локальном bot успешен.
