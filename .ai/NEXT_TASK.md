# Guide OS — Next Task

> Обновлено: 2026-08-09

## Единственная следующая задача

Stage 4B — подготовить request-scoped GuideShop client composition с доверенным разрешением `telegram_user_id -> guide_os_id`.

## Цель

Исключить общий HTTP client между гидами: каждый пользовательский GuideShop request должен получать клиент, навсегда привязанный к `guide_os_id`, разрешённому серверной частью Guide OS.

## Требуемый результат

- отдельный async client/service factory boundary;
- lookup `guide_os_id` только по текущему Telegram user ID через существующий database query;
- новый identity-bound HTTP client на пользовательский request или безопасно определённый lifecycle;
- client всегда закрывается при success и exception;
- missing user/identity, disabled integration и configuration failure обрабатываются fail-closed;
- fake development flow и текущий default-off UX сохраняются;
- tests доказывают отсутствие cross-user reuse и identity substitution.

## Ограничения

- Не включать reads по умолчанию.
- Не подключаться напрямую к базе GuideShop.
- Не реализовывать OAuth/JWT provider, linking completion, events или notifications.
- Не хранить GuideShop business data в SQLite.
- Не логировать credentials, response bodies, PII или payment data.
- Не менять тексты и структуру Telegram UI без необходимости композиции.
- Не активировать staging/production без согласованного GuideShop endpoint и credentials.

## Definition of Done

- Ни один HTTP client не используется для двух разных `guide_os_id`.
- Route, callback и deep-link payload не могут подменить identity.
- Database lookup не создаёт пользователя как побочный эффект.
- Client cleanup гарантирован на всех путях.
- Existing fake/manual UX остаётся работоспособным.
- Focused и полный suite проходят; production composition остаётся fail-closed без token provider.
