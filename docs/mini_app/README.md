# Guide OS Mini App — продуктовая и архитектурная документация

> **Статус: MA0–MA5 complete** (2026-08-29). Следующий этап: **MA6** (Telegram initData auth).

Канонический корень Mini App: [`../../miniapp/`](../../miniapp/README.md).

## Что реализовано

| Слой | Статус | Где |
|------|--------|-----|
| Product docs + DECISIONS | ✅ | эта папка + `miniapp/` |
| MA2 HTML prototype | ✅ | `miniapp/prototype/` |
| React UI (mocks) | ✅ | `miniapp/src/` |
| Shared services | ✅ | `services/tour_service.py`, `reports_service.py`, `availability_service.py` |
| Web API `/app/v1` | ✅ | `web_api/`, `guide_os_miniapp_api.py` |
| Real Telegram auth | ⏳ | MA6 |
| React → API | ⏳ | MA7 |

Telegram-бот (handlers) **не изменён**. Production rollout **выключен**.

## Файлы в этой папке

| Файл | Назначение |
|------|------------|
| [`00-questionnaire.md`](00-questionnaire.md) | Завершённый стартовый опросник |
| [`DECISIONS.md`](DECISIONS.md) | Канонический журнал решений D-001… |
| [`API_CONTRACT_v1.md`](API_CONTRACT_v1.md) | HTTP contract `/app/v1` (MA5 implemented) |
| [`SERVICE_GAP_ANALYSIS_MA4.md`](SERVICE_GAP_ANALYSIS_MA4.md) | Mapping mock → services (Step 2 closed) |

## Связанные документы

1. [`../../miniapp/GuideOS_miniapp_Development_Operating_System.md`](../../miniapp/GuideOS_miniapp_Development_Operating_System.md) — экраны и roadmap MA0–MA15
2. [`../../miniapp/GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md`](../../miniapp/GUIDE_OS_miniapp_INTEGRATION_FOUNDATION.md) — auth, runtime, data ownership
3. [`../../miniapp/AGENTS.md`](../../miniapp/AGENTS.md) — правила для AI-агентов
4. [`../../miniapp/.ai/NEXT_TASK.md`](../../miniapp/.ai/NEXT_TASK.md) — текущая задача

## Граница с кодом

- **Документация** — здесь и в `miniapp/*.md`
- **Frontend** — `miniapp/src/` (React, mocks до MA7)
- **Backend API** — `web_api/` в root repo (feature flag off)
- **Бот** — без изменений; общие services используются API, handlers пока на прежних вызовах

## Локальный запуск

**React UI:**

```sh
cd miniapp && npm install && npm run dev
```

**Web API (dev auth):**

```sh
MINI_APP_API_ENABLED=true MINI_APP_API_DEV_AUTH=true python guide_os_miniapp_api.py
```

См. [`../../miniapp/README.md`](../../miniapp/README.md) для деталей.
