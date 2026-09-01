# Guide OS Mini App — инструкции для AI-агентов

Этот файл действует для каталога `miniapp/` и всех вложенных файлов. Читай его первым. Не сканируй весь репозиторий без доказанной необходимости.

При конфликте приоритет: текущий код и тесты → этот файл → `miniapp/.ai/*` → остальные Mini App Markdown-документы → root docs.

## Текущее состояние

> Обновлено: 2026-09-01. Этапы **MA0–MA10** — завершённые исторические этапы. Post-MA10: **Owner-approved Mini App MVP UX checkpoint — complete** (commit `57405f4` on `main`). **Public production pilot — ACTIVE, owner-validated** (2026-09-01). **Нет активной coding/deployment задачи** — следующий шаг только по явному запросу владельца.

| Этап | Статус | Артефакт |
|------|--------|----------|
| MA0 | ✅ | docs, DECISIONS, AGENTS |
| MA1 | ✅ | `prototype/index.html` (low-fi) |
| MA2 | ✅ | high-fi prototype (owner approved) |
| MA3 | ✅ | React + Vite в `miniapp/src/` (mocks) |
| MA4 | ✅ | contract + shared services + migrations |
| MA5 | ✅ | `web_api/`, `guide_os_miniapp_api.py` |
| MA6 | ✅ | initData HMAC + `miniapp_sessions` + bearer tokens |
| MA7 | ✅ | React HTTP client (`httpClient.ts`, session bootstrap) |
| MA8 | ✅ | Reports/availability via API (HTTP mode) |
| MA9 | ✅ | Staging smoke + production gate docs |
| MA10 | ✅ | Local Telegram E2E PASS (real initData, local stack) |
| MA11 | ⏸ | Hosted closed staging — **не** текущая задача; owner вместо этого авторизовал reversible public production pilot |

**Post-MA10 UX checkpoint (2026-08-31):** Owner-approved Mini App MVP UX — complete. React interface owner-validated in dedicated local test bot; no known blocking UX issues.

**Public production pilot (2026-09-01):** Mini App доступен через production Guide OS bot (`MenuButtonWebApp`). Owner explicitly approved **оставить pilot enabled**. Two real Telegram accounts: bot ↔ Mini App synchronization PASS; cross-account isolation / IDOR manual verification PASS. Automated security evidence on `main` (commits `2eb02f2`, `e8aed0b`, `0076101`): targeted Mini App security/API **133 passed**; full backend **1167 passed, 1 skipped**; month-picker **32 passed**; feed **32 passed**; production frontend builds successful.

**Formal general production release** — не объявлен отдельно. Production gate docs (`PRODUCTION_GATE_MA9.md`) сохранены для будущего formal release review; не утверждать, что каждый formal gate item complete.

**Агентам:** не отключать pilot, не redeploy, не расширять scope и не объявлять formal general release без **нового явного запроса владельца**. Rollback reversible: `MINI_APP_ENABLED=false`, при необходимости `MINI_APP_API_ENABLED=false`, redeploy bot — только когда owner попросит скрыть Mini App.

**Frontend** (`miniapp/src/`) по умолчанию на **mock store** (`VITE_USE_MOCK_API` unset/`true`). HTTP client готов: `VITE_USE_MOCK_API=false` + API/proxy. **Production Web API** с **real initData auth**; production bot и Mini App используют общий Guide OS data layer через shared services/database.

Главная следующая задача — только в `.ai/NEXT_TASK.md` (сейчас: **нет активной задачи**).

## Цель и приоритет

Guide OS Mini App — быстрый профессиональный календарь туристического гида внутри Telegram.

Приоритет:

```text
скорость ключевого сценария
> правильность и изоляция данных
> единая логика с ботом
> простой MVP
> визуальные улучшения
> дополнительные функции
```

Обязательный порядок: `ANALYZE → PLAN → CODE → TARGETED TEST → STOP`.

Перед нетривиальным кодом кратко показать:

- `ANALYSIS`;
- `FILES TO CHANGE`;
- `RISKS`;
- `PLAN`.

## Неподвижные продуктовые границы

- Пользователь Mini App — только гид.
- Бот и Mini App — равноценные интерфейсы общих данных.
- MVP имеет две вкладки: `Календарь` и `Итоги`.
- Основной сценарий `проверить дату → добавить тур` должен занимать 10–15 секунд.
- Русский язык и USD — единственные язык и валюта MVP.
- GuideShop в MVP не является большим отдельным модулем.
- Official GuideShop data всегда read-only без отдельного approval.
- Полный список решений: `../docs/mini_app/DECISIONS.md`.

## Целевая архитектура

```text
miniapp frontend
  -> Guide OS Web API
    -> shared Guide OS services
      -> Guide OS database
      -> existing read-only GuideShop client

Telegram bot handlers
  -> те же shared Guide OS services
```

Нельзя создавать отдельную бизнес-логику календаря во frontend или Web API.

### Планируемая структура

Структура ниже является целевой и создаётся поэтапно, а не заранее пустыми папками:

```text
miniapp/
├── src/
│   ├── app/          # composition, routes, providers
│   ├── features/     # calendar, tours, reports, settings
│   ├── components/   # shared UI only
│   ├── api/          # typed API client
│   ├── telegram/     # WebApp adapter and theme/safe-area integration
│   ├── i18n/         # RU now, future UZ/EN-ready
│   └── styles/       # tokens and global styles
├── tests/
├── public/
└── package.json

web_api/              # MA5: transport/auth in root Guide OS
services/             # MA4: shared business logic
database/             # schema + SQL boundary
```

Не расширяй `web_api/`, schema и dependencies без задачи в `NEXT_TASK.md`.

## PROJECT MAP — текущее расположение источников

| Нужно понять или изменить | Где смотреть сначала |
|---|---|
| Утверждённый продукт и экраны | `miniapp/GuideOS_miniapp_Development_Operating_System.md` |
| API contract v1 | `docs/mini_app/API_CONTRACT_v1.md` |
| Service gap / MA4 mapping | `docs/mini_app/SERVICE_GAP_ANALYSIS_MA4.md` |
| Web API routes | `web_api/`, `guide_os_miniapp_api.py` |
| Shared services (MA4) | `services/tour_service.py`, `reports_service.py`, `availability_service.py` |
| React frontend (mocks) | `miniapp/src/`, `miniapp/src/api/client.ts` |
| MA2 disposable reference | `miniapp/prototype/` |
| Туры и конфликты бота | `services/tour_service.py`, `handlers/add_tour.py` |
| Календарь и карточки дня | `services/calendar_service.py`, `services/day_view_service.py`, `services/day_card_service.py` |
| Доход и статистика | `services/income_service.py`, `services/stats_service.py` |
| Профиль и уведомления | `handlers/profile.py`, `handlers/notifications.py` |
| SQL и migrations | `database/queries.py`, `database/db.py` |
| GuideShop reads | `services/guide_shop_runtime.py`, `services/guide_shop_client.py` |
| Root project rules | `AGENTS.md` |

## Business invariants

### Tours and calendar

- `reserved` и `confirmed` блокируют дату.
- `paid` и `unpaid` — единственные payment statuses MVP.
- `income` — дневная ставка; для multi-day расчёт идёт по дням.
- `day_off` занимает весь день, имеет нулевой доход и не считается рабочим днём.
- Отмена тура означает подтверждённое удаление; cancelled status не добавлять.
- Multi-day использует общий `tour_group_id`; общие изменения и удаление применяются ко всей группе.
- Местоположение допускает daily override внутри multi-day тура.
- Время Mini App необязательно; если включено, нужны `start_time` и `end_time`.
- Тур без времени занимает весь день.
- Непересекающиеся интервалы одного дня допустимы после понятного date warning.
- Одинаковые или пересекающиеся интервалы Mini App должен блокировать до исправления.
- Это новое правило времени должно жить в общем service layer, даже если бот не спрашивает время.

### Reports and availability

- Один день с любым количеством туров считается одним рабочим днём.
- `Бронь` не является свободной датой.
- В клиентский текст входят только полностью свободные даты.
- Частично свободный день показывается гиду, но не экспортируется как свободный.
- Фактический доход — сумма туров со статусом `Оплачено`; отдельной фактической суммы нет.
- Разные периоды и фильтры не должны менять базовые правила расчёта.

### Identity, auth and isolation

- Frontend отправляет raw `Telegram.WebApp.initData`; сервер валидирует подпись и свежесть.
- Никогда не доверять `initDataUnsafe` или `user_id` из тела/URL как доказательству личности.
- Каждый запрос user-scoped; cross-user access fail closed.
- `guide_os_id` immutable lowercase UUIDv4.
- Telegram ID показывается только текущему гиду и может быть скопирован.
- Bot token, service private keys и GuideShop credentials никогда не попадают во frontend.

### Integration and availability

- Frontend не обращается к SQLite или GuideShop напрямую.
- Core calendar работает при полном отключении GuideShop.
- GuideShop outage даёт degraded state и не блокирует личный календарь.
- Нельзя использовать одну SQLite из двух независимых production runtimes.
- Staging и production имеют разные bot tokens, DB, keys, URLs и volumes.

## Frontend rules

- Mobile-first; проверять iPhone, Android и Telegram Desktop.
- Следовать Telegram theme variables и safe areas.
- Professional Minimal foundation + Telegram-native behavior + умеренный tourism accent.
- Официальный SVG не перерисовывать и не менять геометрию.
- Состояния нельзя передавать только цветом.
- Touch targets, контраст, loading, empty, error, disabled и offline states обязательны.
- Не добавлять тяжёлую state-management библиотеку до реальной необходимости.
- API types должны происходить из зафиксированного контракта, а не из случайных mock shapes.
- Не размещать business calculations в React components.
- Не создавать component abstraction до второго реального использования.

## Context efficiency rules

1. Начинай с этого файла и `.ai/NEXT_TASK.md`.
2. Определи минимальный scope; обычно 1–3 файла, максимум 5 без явного approval.
3. Читай только связанные файлы и непосредственные зависимости.
4. После нахождения нужного pattern прекращай широкое исследование.
5. Не делай unrelated refactoring, cleanup или переименование.
6. Не исправляй случайно найденные проблемы, если они не блокируют задачу.
7. Не меняй UX, API или business behavior вне scope.
8. Переиспользуй существующие services, helpers, tokens и компоненты.
9. Не создавай параллельную реализацию существующей логики.
10. Не добавляй dependency без объяснённой необходимости и approval.
11. Не форматируй несвязанные файлы.
12. Не читай большие логи, DB или весь DEVLOG без конкретной причины.
13. Не запускай полный suite после каждого небольшого изменения.
14. Routine Git add/commit/push оставляй владельцу; никогда не использовать `git add .`.

## Language rules

- Все готовые промпты, предназначенные для вставки в Cursor или другой coding agent, писать на английском языке.
- Обычные объяснения, вопросы и отчёты владельцу проекта писать на русском языке, если владелец явно не попросил другой язык.
- Не дублировать один и тот же Cursor prompt на русском и английском: предоставлять только английскую версию для экономии контекста.

## Testing strategy

### Frontend (`miniapp/`)

```sh
cd miniapp
npm install
npm test
npm run build
npm run dev
```

### Backend / Web API (root Guide OS)

```sh
.venv/bin/python -m pytest -q tests/test_tour_service.py tests/test_reports_service.py tests/test_availability_service.py tests/test_miniapp_api.py tests/test_miniapp_telegram_auth.py
.venv/bin/python -m pytest -q
git diff --check
```

Локальный Web API (production auth path with real `BOT_TOKEN`):

```sh
MINI_APP_API_ENABLED=true python guide_os_miniapp_api.py
# POST /app/v1/session with {"init_data": "..."} → Bearer session_token
```

**Local Telegram E2E (MA10 validated):** see [README.md](README.md) § Local Telegram E2E — test bot, real initData, Vite + Cloudflare Quick Tunnel, owner allowlist. Not staging/production.

Dev-only shortcut (tests/local explicit flag):

```sh
MINI_APP_API_ENABLED=true MINI_APP_API_DEV_AUTH=true python guide_os_miniapp_api.py
```

Правила:

- во время разработки — targeted tests изменённого service/API/UI;
- business logic требует regression test;
- auth, ownership и isolation требуют positive и negative tests;
- полный suite — один раз, когда оправдан масштабом/риском;
- visual UI требует ручной проверки целевых viewport и light/dark themes;
- E2E не запускает production bot или production GuideShop.

## Default workflow

1. Прочитать `AGENTS.md` и `.ai/NEXT_TASK.md`.
2. Проверить текущее состояние, не предполагая наличие планируемого кода.
3. Определить минимальный scope и invariants.
4. Найти существующий service/pattern.
5. Показать короткий план.
6. Сделать минимальное изменение.
7. Добавить или обновить связанные тесты.
8. Запустить targeted checks.
9. При необходимости один раз запустить широкий suite.
10. Обновить `.ai` только если изменился фактический статус этапа.
11. Остановиться после выполнения запроса.

## Stop condition

После выполнения требований и необходимых проверок остановись. Без отдельного запроса не делать cleanup, новый экран, refactor, dependency upgrade, deployment, Git commit/push или исправление соседних bugs.

## Security red flags

- raw Telegram initData, JWT, PEM, bot tokens, cookies и session tokens в logs;
- frontend ownership по Telegram ID из request body;
- прямой SQL из Web API route;
- frontend request к GuideShop;
- shared staging/production secrets или DB;
- production enablement без отдельного approval;
- hidden fallback на mock data в production;
- hardcoded internal/opaque IDs в UI.

## Final response format

1. Summary.
2. Changed files.
3. Tests/checks executed.
4. Result.
5. Manual checks needed.
6. Risks/issues — только реальные.
