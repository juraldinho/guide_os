# Guide OS — текущее состояние

**Closure — 2026-10-29:** ручная функциональная проверка закрыта владельцем (owner-reported PASS). Код зафиксирован и отправлен в GitHub: `569e8906c04a5380c96dc6a142b3cdd264b1f806`; оба production-сервиса Railway закреплены на этом commit. Backend `cfe3ab97-25e5-4952-a488-779e264bb52e` и frontend `3142566b-e4cb-4c6c-8632-f290f361ab5c` — SUCCESS; live smoke PASS, staging не изменён. Отдельно открыт CI defect: standalone Mini App API import требует BOT_TOKEN через analytics/config (1 failed, 1882 passed, 3 skipped); integration workflows PASS. Подробности: `docs/REMINDER_MINIAPP_LINK.md`.

Обновлено **2026-10-29** по коду и записанным release-проверкам. Git/source alignment и live smoke повторно выполнены 2026-10-29. Приоритет: код/тесты → [AGENTS.md](../AGENTS.md) → operational docs → исторические планы.

## Последние подтверждённые окружения

| Окружение | Backend | Mini App frontend | Проверено |
|---|---|---|---|
| Production, @Guide_os_bot | `cfe3ab97-25e5-4952-a488-779e264bb52e` | `3142566b-e4cb-4c6c-8632-f290f361ab5c` | 2026-10-29, оба SUCCESS |
| Staging, @Guideosbot | `4f2df896-9a08-43a1-88f4-da86da2fde47` | `346e539b-36c7-4524-adb8-28af77e14a80` | 2026-10-28; IDs повторно сверены 2026-10-29 |

Production: `python guide_os_production_runtime.py`, одна replica/один runtime и poller, SQLite `/data/guide_os.db`. Staging: `python guide_os_staging_runtime.py`, отдельный volume и `/data/guide_os_staging.db`. Проверки перед/после релизов: online backup, full SQLite integrity `ok`, auth gates `401`, health `200`, один polling startup без getUpdates conflict в просмотренном окне.

Production Mini App: https://guide-os-miniapp-production.up.railway.app/ ; API: https://guideos-production.up.railway.app . Staging Mini App: https://guide-os-staging-miniapp-staging.up.railway.app/ ; API: https://api.staging.guideos.uz . Секреты и пользовательские данные в сводку не включаются.

## Выпущенные функции

- Core calendar/tours/day off, income/reports, профиль, reminders, личные места и комиссии; Stage 19 завершён.
- Mini App MA0–MA10 и GSMA0–GSMA10 завершены для public pilot. Четыре вкладки: Календарь, Итоги, GuideShop, Guide Operator. Official GuideShop остаётся read-only; продажи GuideShop убраны из Mini App. Formal general release отдельно не объявлен.
- **Дневные чаевые**: staging 2026-10-22, production 2026-10-27. Одна integer USD сумма `0…1_000_000_000` на пользователя/дату, replace, zero/delete. Не связаны с tour/occupancy. «Итоги»: доход туров, чаевые и общий доход; filters туров не скрывают tips периода; all-time включает tips-only даты. [Roadmap](TIPS_ROADMAP.md), [API](mini_app/API_CONTRACT_v1.md), [release handoff](DAILY_TIPS_IMPLEMENTATION.md).
- **Переход из напоминания**: staging 2026-10-28, production 2026-10-29. Новая кнопка «Открыть в приложении» открывает точную карточку через owner-scoped API; старая «Открыть тур» сохранена. Multi-day row ID разрешается в canonical entry ID; operator projection открывает существующий assignment detail. Старые сообщения не редактируются. [Handoff и проверки](REMINDER_MINIAPP_LINK.md).

## Guide Operator: реализация и границы evidence

Consent, offers/accept/decline, protected projections, ordinary/critical versions, cancellation, outboxes, discovery/availability, reconcile snapshots и ограниченный local repair реализованы; подробная карта — [AGENTS.md](../AGENTS.md). GO13I1 добавил offered-only withdrawal/expiry intake; отдельных Mini App sections/status typing для них нет. GO13J1 launcher уже используется в production, а не только подготовлен локально.

GO13D staging E2E от 2026-10-08 и GO13E–GO13G closure от 2026-10-09 остаются историческим evidence: [runbook](GUIDE_OPERATOR_STAGING_E2E_GO13D.md). Relevance policy: True → send; False → superseded; None → local_state. Нового полного production GO E2E эти релизы не подтверждают.

Production preflight 2026-10-29 наблюдал включённые service auth, integration API и outbound flags; они существовали до reminder release и не менялись им. Два confirmed-connection identity API файла уже были live и сохранены при обоих production promotions. Не путать отсутствие Git-коммита с отсутствием deployed функции. Guide Operator notification delivery/worker flags отдельно этим последним preflight не аттестованы.

## Git и provenance

Application source commit — `569e8906c04a5380c96dc6a142b3cdd264b1f806` (main, pushed). Production backend и frontend source pins указывают на этот immutable commit; Git-backed builds успешно заменили прежние local-upload deployments. Последующий documentation-only commit не меняет application source/pins. Посторонние `docs/analytics/`, `media/` и QR-файл не включены.

Полные manifests, source/archive hashes, backup paths и application rollback IDs находятся в handoffs. Application rollback не требует удаления daily_tips или разрушительного восстановления DB.

## Проверки и оставшаяся работа

- Local reminder regression: **1885 backend passed, 1 skipped; 375 frontend passed**, TypeScript/Vite build и whitespace check успешны (2026-10-28).
- Staging candidate: **34 backend + 14 frontend tests**; production candidate: **37 focused backend tests** и production HTTP build. При возобновлении 2026-10-29 неизменённые тесты/build не повторялись.
- Production 2026-10-29: 119 source hashes, generated keyboard/menu, SQLite integrity, backup hash, runtime/poller и public frontend bundle hash проверены; флаги сохранены.
- Владелец 2026-10-29 сообщил о закрытии ручной функциональной проверки: работает корректно. Зафиксирован owner-reported PASS; детализация отдельной device matrix не предоставлялась.
- Telegram bot UX/statistics для чаевых отложены. Google Calendar GC0–GC13 не активирован; operator notifications UI и guide-initiated disconnect не объявлены реализованными. Новая функция/деплой требуют своего scope.

Git-задача закрыта. Открытый CI defect: `tests/test_miniapp_api.py::test_entrypoint_import_without_bot_modules` падает без BOT_TOKEN через `services/miniapp_analytics.py → config.py`; этот import существовал до данного release (`2b4b3fa`). GitHub CI: 1 failed, 1882 passed, 3 skipped; Integration Contracts и Shared GuideShop Event E2E — PASS. Исправление analytics import не включалось в scope фиксации проверенного production source. Operational pointers: [root NEXT_TASK](../.ai/NEXT_TASK.md), [Mini App NEXT_TASK](../miniapp/.ai/NEXT_TASK.md). Исторические DEVLOG, MA/GSMA планы и старые gates сохраняют исходные даты и не подменяют эту сводку.
