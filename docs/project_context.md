# Guide OS — Project Context for AI

Чаевые Mini App-first выпущены в production 2026-10-27; «Открыть в приложении» в новых напоминаниях — 2026-10-29. Текущие production deployments: backend `5dd8037d-97e8-48ad-890a-c04cb0cb6683`, frontend `3d307e26-3378-4171-8f13-aa6fa7e3379c`. Technical smoke прошёл; authenticated manual Telegram/device E2E не объявлен PASS. Релизы выполнены из изолированных артефактов; Git HEAD остаётся `24b3cad`, старые source pins не включают новые функции. Следующие действия: ручная проверка и owner-run Git/source alignment перед новой выкладкой из Git. Новая coding-задача не активирована.

Обновлено: 2026-10-29. Первичная карта — [AGENTS.md](../AGENTS.md); [текущее состояние и evidence](CURRENT_STATE.md). Приоритет: код/тесты → AGENTS → `.ai/*` → остальные документы.

## Продукт и данные

Guide OS — Telegram bot и Mini App для гида: calendar/tours/day off, income/reports, профиль, reminders, личные места/комиссии. Mini App содержит Calendar, Reports, GuideShop и Guide Operator. Official GuideShop read-only; локальные записи принадлежат гиду и не становятся официальными GuideShop sales.

## Реализация и runtime

- `handlers/` → `services/` → `database/`; shared business logic для bot и Web API.
- `bot.py` владеет polling, Mini App API и background lifecycle; `guide_os_miniapp_api.py` — standalone API.
- `guide_shop_link_api.py` — API-only linking provider.
- `guide_operator_integration_api.py` — authenticated GO inbound/read/repair; `guide_operator_outbound_worker.py` — standalone outbound CLI.
- `guide_os_staging_runtime.py` — consolidated staging; `guide_os_production_runtime.py` — действующий GO13J1 production runtime (observed 2026-10-29).
- SQLite/WAL; Python pin 3.13.14; business timezone `Asia/Tashkent`.
- GuideShop contracts: CI pin `v1.2.0`, commit `28eeec371208c4d58dea008e4890f6b69f651c75` в `.github/workflows/integration-contracts.yml`.

## Состояние

Stage 19 и GSMA0–GSMA10 завершены. Guide Operator consent/assignments/versions/cancellation, reconciliation, notification/outbound infrastructure реализованы. GO13I1 добавил offered-only withdrawal/expiry backend; frontend terminal sections для них не добавлены. GO13J1 используется в production. Последние release checks и deployed artifact IDs от 2026-10-29 находятся в CURRENT_STATE.md; новая полная production GO E2E-аттестация не заявлена.

## Security и правила

Все пользовательские операции owner-scoped; session identity не берётся на доверии из body. `guide_os_id` immutable UUIDv4. Service JWT, replay protection и fail-closed configuration обязательны. Staging/production credentials, volumes и processes разделены. Не выводить secrets/PII и не хранить их в документации.

Confirmed-connection identity endpoint уже был live в production и сохранён в новых артефактах; его исходники ещё не зафиксированы отдельным Git commit. Source и deployment — разные состояния; см. [сводку](CURRENT_STATE.md).

Начинать с AGENTS и релевантного NEXT_TASK; минимальные изменения, targeted tests, full suite только при значимой логике/workflow, `git diff --check`. Git mutations выполняет владелец. Google Calendar остаётся неактивным; tips и reminder links выпущены в Mini App/production. Telegram bot tips UX отложен.
