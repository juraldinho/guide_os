# Guide OS — Next Task

> Обновлено: 2026-08-09

## Единственная следующая задача

Stage 4A — финальная подзадача: реализовать default-off real GuideShop runtime composition в Guide OS.

## Цель

Соединить trusted identity lookup, EdDSA token provider, HTTP client и request-scoped service provider без включения production flags по умолчанию.

## Требуемый результат

- disabled flow не читает HTTP/JWT settings и сохраняет текущий UX;
- explicit development fake flow работает без real credentials;
- real flow создаёт validated HTTP/JWT settings только при reads-enabled и fake-disabled;
- shared stateless token provider и новый identity-bound HTTP client на request;
- identity lookup использует существующий read-only `get_guide_os_id`;
- configuration failures fail-closed без secret leakage;
- client lifecycle управляется существующим request-scoped provider;
- production remains disabled until explicit flags and valid secrets are supplied.

## Ограничения

- Не добавлять реальные keys/secrets в `.env` или repository.
- Не включать feature flags по умолчанию.
- Не выполнять HTTP при startup/composition.
- Не реализовывать GuideShop verifier, events или notifications.
- Не менять routes, DTO, UI texts или navigation semantics.
- Не создавать пользователей при identity lookup.
- Не логировать settings, token, key, identity или upstream payload.

## Definition of Done

- Disabled and fake flows полностью backward compatible.
- Real composition использует только validated existing components.
- Каждый request получает client для trusted local `guide_os_id`.
- Startup не выполняет token signing или network request.
- Missing/malformed config fails safely before polling.
- Focused/full tests проходят; без explicit real settings production остаётся выключенным.
