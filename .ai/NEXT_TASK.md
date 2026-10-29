# Guide OS — Next Task

Обновлено: **2026-10-29**. [Текущее состояние](../docs/CURRENT_STATE.md).

## Завершено

Чаевые Mini App-first — production 2026-10-27. Переход «Открыть в приложении» из новых напоминаний — production 2026-10-29. Backend `cfe3ab97-25e5-4952-a488-779e264bb52e`, frontend `3142566b-e4cb-4c6c-8632-f290f361ab5c`, оба SUCCESS. Staging остаётся на backend `4f2df896-9a08-43a1-88f4-da86da2fde47`, frontend `346e539b-36c7-4524-adb8-28af77e14a80`.

Core/Stage 19, Mini App MA0–MA10, GuideShop GSMA0–GSMA10 и реализованные GO6–GO13 paths описаны в AGENTS. Не запускать заново уже выполненные development/deployment этапы.

## Следующие действия

1. Ручная функциональная проверка закрыта владельцем 2026-10-29: owner-reported PASS. Повторять её как незавершённый пункт не требуется.
2. Git commit/push и production pins закрыты: `569e8906c04a5380c96dc6a142b3cdd264b1f806`. Посторонние analytics/media/QR не включены.
3. Открыт отдельный CI defect: standalone API import без BOT_TOKEN падает через analytics/config; 1 failed, 1882 passed, 3 skipped. Production smoke PASS. Новая coding-задача не назначена. Не деплоить заново и не менять runtime/flags по этому статусу.

## Evidence

- [Чаевые: tests, artifacts, migration, backup и release](../docs/DAILY_TIPS_IMPLEMENTATION.md).
- [Reminder links: полный regression и deployment checks](../docs/REMINDER_MINIAPP_LINK.md).
- Last feature regression: 1885 backend passed, 1 skipped; 375 frontend passed; build successful. Это датированные локальные результаты, не новый прогон этой docs-задачи.

## Ограничения

Google Calendar остаётся неактивным. Telegram tips UX/statistics, operator notifications UI, guide-initiated disconnect и dedicated withdrawn/expired Mini App sections не активируются автоматически. Official GuideShop остаётся read-only. Нового полного production GO E2E эти релизы не подтверждают.

Production service-auth/integration/outbound flags наблюдались включёнными до этих releases и сохранены. Source defaults остаются fail-closed; не отключать или включать интеграции на основании старых roadmap gates. GO notification delivery flags отдельно последним preflight не аттестованы.
