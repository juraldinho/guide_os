# Guide OS Mini App — Development Operating System

> Версия: 1.0  
> Дата: 2026-08-28  
> Статус: утверждённая архитектура; **implementation progress через MA5** (см. §1.1)

## 1. Назначение документа

Документ является основной спецификацией продукта, экранов и последовательности разработки Guide OS Mini App. Он переводит утверждённые решения владельца в проверяемую архитектуру и roadmap.

При конфликте приоритет имеют текущий код и тесты Guide OS, затем `miniapp/AGENTS.md`, затем журнал решений `docs/mini_app/DECISIONS.md`.

### 1.1 Implementation progress (2026-08-29)

| Этап | Статус | Реализовано |
|------|--------|-------------|
| MA0 | ✅ | Docs, DECISIONS, AGENTS |
| MA1 | ✅ | `miniapp/prototype/` low-fi |
| MA2 | ✅ | High-fi prototype (approved) |
| MA3 | ✅ | React app on mocks (`miniapp/src/`) |
| MA4 | ✅ | Services, migrations, contract docs |
| MA5 | ✅ | `web_api/`, `guide_os_miniapp_api.py` (dev auth) |
| MA6 | ⏳ | Telegram initData session |
| MA7 | ⏳ | React HTTP client |
| MA8–MA15 | ⏳ | Integration, staging, production |

Telegram-бот (handlers) **не изменён**. Production Mini App **выключен** (`MINI_APP_API_ENABLED=false`).

## 2. Продуктовая формулировка

Guide OS Mini App — быстрый профессиональный календарь туристического гида внутри Telegram, позволяющий за несколько секунд проверить занятость, добавить тур, увидеть расписание и оценить работу и доход за период.

Продукт отвечает на три главных вопроса:

1. Что у меня сегодня и в ближайшие дни?
2. Свободен ли я в выбранную дату?
3. Как я работал и сколько заработал за выбранный период?

## 3. Пользователь и границы

Единственный пользователь Guide OS — туристический гид. Роли Owner, Manager, Dispatcher и Tour Operator принадлежат другим продуктам Tourism OS и здесь не проектируются.

Telegram-бот и Mini App остаются двумя равноценными способами работы с Guide OS:

- данные общие;
- изменения видны в обоих интерфейсах;
- бизнес-правила общие;
- UI и набор быстрых возможностей могут различаться;
- время начала/окончания является Mini App-first возможностью, но сохраняется в общей модели.

## 4. Product principles

1. Скорость важнее количества функций.
2. Календарь важнее dashboard.
3. Частые действия доступны за 1–2 нажатия.
4. Одна форма лучше длинного wizard.
5. Состояние объясняется текстом, а не только цветом.
6. Пользователь всегда понимает, что сохранено и что изменится.
7. Личный календарь не зависит от доступности GuideShop.
8. Mini App не создаёт вторую бизнес-логику рядом с ботом.
9. Mobile-first без потери работоспособности в Telegram Desktop.
10. Production остаётся выключенным до отдельного release gate.

## 5. Scope MVP

### 5.1 Обязательно

- Telegram authentication;
- вкладки `Календарь` и `Итоги`;
- day/week/month calendar;
- agenda выбранного дня;
- добавление тура и выходного;
- однодневные и многодневные туры;
- optional start/end time;
- статусы `Бронь` и `Занято`;
- `Оплачено` и `Не оплачено`;
- income в USD;
- редактирование, копирование и удаление;
- конфликты дат и времени;
- per-day location для multi-day;
- месячная визуализация занятости;
- отчёты и фильтры;
- сообщение со свободными датами;
- профиль, тип гида, география и Telegram ID;
- управление напоминаниями;
- Telegram light/dark theme;
- loading, empty, error, offline/degraded states;
- user isolation и parity tests.

### 5.2 Позже

- official GuideShop events в календаре;
- узбекский и английский;
- дополнительные валюты;
- расширяемый список географии;
- QR для Guide ID/linking;
- Tourism OS Mini App Starter.

### 5.3 Не входит

- полный GuideShop кабинет;
- Google Calendar;
- публичные booking slots;
- recurring rules;
- чаевые и payments;
- квизы;
- marketplace/social feed;
- admin, broadcast и backup UI;
- Guide Operator;
- PostgreSQL migration внутри Mini App workstream.

## 6. Информационная архитектура

```text
Mini App
├── Календарь
│   ├── День / Неделя / Месяц
│   ├── Agenda выбранного дня
│   ├── Добавить
│   │   ├── Тур
│   │   └── Выходной
│   ├── Карточка тура
│   │   ├── Изменить
│   │   ├── Копировать
│   │   └── Удалить
│   └── Поделиться свободными датами
├── Итоги
│   ├── Период
│   ├── Сводка
│   ├── Визуальная занятость
│   ├── Фильтры
│   └── Свободные даты
└── Настройки
    ├── Профиль
    ├── Типы и география гида
    ├── Telegram ID
    ├── Уведомления
    ├── Язык
    └── О приложении
```

## 7. Глобальная навигация

Нижняя панель:

1. `Календарь` — стартовая вкладка.
2. `Итоги` — отчёт и доступность.

Шестерёнка открывает настройки. Кнопка `Добавить` доступна из календаря и относится к выбранной дате.

При открытии:

- выбирается сегодняшний день в timezone `Asia/Tashkent`;
- загружается вертикальная лента сегодняшнего и следующих семи дней;
- сохранённая ранее дата не заменяет today default.

## 8. Экран «Календарь»

### 8.1 Верхняя панель

- официальный знак Guide OS в компактном варианте, если не мешает высоте;
- нажимаемый текущий месяц и год;
- кнопка `Сегодня`;
- шестерёнка.

### 8.2 Основная лента и календарь месяца

По умолчанию показывается вертикальная лента из восьми дней:

- сегодняшний день;
- следующие семь дней.

Строка дня показывает дату, день недели и краткое состояние. Если есть туры, рядом показывается их краткое содержание. Нажатие на день открывает подробный экран дня. Нажатие на конкретный тур открывает карточку тура.

Нажатие на название месяца и года разворачивает календарь месяца над лентой. Месячный календарь:

- поддерживает предыдущие и следующие месяцы;
- показывает выбранную и сегодняшнюю дату;
- использует компактные status markers;
- после выбора даты открывает подробный день и сворачивается либо остаётся компактным согласно прототипу;
- не заменяет вертикальную ленту как основной режим.

Постоянный переключатель `День / Неделя / Месяц` отсутствует.

### 8.3 Маркеры

- свободно — нейтральное состояние или зелёный marker;
- бронь — жёлтый marker;
- занято — бирюзовый marker;
- выходной — серый marker;
- несколько туров — несколько markers;
- конфликт — красный warning marker.

Цвет сопровождается подписью/иконкой в agenda и detail view.

### 8.4 День и agenda

Для каждой записи без открытия details показываются:

- время или `Весь день`;
- название;
- статус;
- компания;
- доход;
- `Оплачено/Не оплачено`.

Заметка показывается только в details.

Для пустого дня:

- статус `День свободен`;
- основная кнопка `Добавить`;
- при наличии соседних свободных дней компактная строка диапазона.

При возврате из карточки тура пользователь попадает обратно в подробный день, а затем в ту же позицию основной ленты.

### 8.5 Quick availability

Кнопка `Поделиться свободными датами` открывает общий availability flow с предвыбранным текущим месяцем.

## 9. Добавление записи

После `Добавить` открывается компактный selector:

- `Тур`;
- `Выходной`.

### 9.1 Форма тура

Открывается bottom sheet на подходящем viewport или full-screen mobile form.

Обязательные поля:

- дата либо период;
- название тура.

Необязательные:

- компания;
- местоположение;
- переключатель времени;
- start time;
- end time;
- доход в USD;
- заметка.

Видимые значения по умолчанию:

- статус `Бронь`;
- оплата `Не оплачено`;
- время выключено.

Кнопка: `Сохранить тур`.

### 9.2 Date range

- single-day — одна дата;
- multi-day — start/end с визуально выделенным диапазоном;
- end date не может быть раньше start date;
- selected range отображается до сохранения.

### 9.3 Time picker

- time picker использует нативный или Telegram-friendly mobile control;
- если время включено, start и end обязательны;
- end должен быть позже start;
- неполный интервал не сохраняется;
- тур без времени является full-day.

### 9.4 Suggestions

Company и location предлагают ранее введённые значения текущего гида. Пользователь может ввести новый свободный текст. Никакого общего каталога других гидов нет.

### 9.5 Multi-day location refinement

После сохранения multi-day тура показывается список дней с первоначально одинаковым location. Подсказка предлагает уточнить город каждого дня.

Общие поля сохраняются на уровне tour group. Location поддерживает day override.

### 9.6 Выходной

- дата или период;
- всегда full-day;
- income 0;
- не считается рабочим днём;
- блокирует доступность;
- сохраняется кнопкой `Сохранить выходной`.

## 10. Конфликты

### 10.1 Date warning

Любое совпадение даты обнаруживается и объясняется до сохранения.

Если существующий и новый туры имеют непересекающееся время, сохранение допустимо после информирования.

### 10.2 Blocking time conflict

Сохранение блокируется, если:

- время совпадает;
- интервалы пересекаются;
- один тур full-day;
- существующий тур создан ботом без времени;
- на дате есть выходной.

Сообщение содержит:

- конфликтующую дату;
- существующий тур;
- существующий интервал;
- новый интервал;
- понятную причину;
- действие `Изменить время` или `Изменить дату`.

Пример:

`Время нового тура пересекается с туром «Самарканд» 09:00–14:00. Измените время или дату.`

### 10.3 Не использовать

- молчаливое исправление времени;
- сохранение невозможного overlap;
- только красный цвет без текста;
- generic `Ошибка 400`.

## 11. Карточка тура

Показывает:

- название;
- date/range;
- start/end или `Весь день`;
- company;
- location конкретного дня;
- income USD;
- payment status;
- booking status;
- note;
- source: `Guide OS bot`, `Mini App`, позже `GuideShop/Guide Operator`.

Действия:

- `Изменить`;
- `Копировать`;
- `Удалить`.

### 11.1 Edit

- форма открывается с текущими значениями;
- изменения применяются по `Сохранить`;
- при закрытии dirty form — предупреждение;
- common multi-day fields меняют всю group;
- location конкретного дня может меняться отдельно.

### 11.2 Copy

Копируются название, company, location, income, status, payment status, time и note. Даты пользователь выбирает заново. Recurrence rule не создаётся.

### 11.3 Delete

- single-day: `Удалить тур?` → `Да/Нет`;
- multi-day: явное предупреждение об удалении всех дней;
- после `Да` удаление окончательное;
- undo и cancelled history в MVP отсутствуют.

## 12. Экран «Итоги»

### 12.1 Period selector

- конкретный месяц;
- конкретный год;
- весь период.

Выбор оформляется компактно по образцу статистики Telegram-бота: месяцы, переход между периодами и отдельное действие `За весь период`. Текущий год считается с 1 января по сегодняшний день; завершённый прошлый год — с 1 января по 31 декабря. Будущий год выбрать нельзя.

### 12.2 Summary

- количество туров;
- рабочие дни;
- доход в USD;
- количество оплаченных туров;
- количество неоплаченных туров.

Один день с несколькими турами считается одним рабочим днём.

Свободные даты формируются отдельным действием `Поделиться свободными датами` и не добавляют длинную визуализацию в сводку.

### 12.3 Income semantics

- одна актуальная daily rate per tour;
- если цена изменилась, гид редактирует сумму;
- planned — все подходящие туры с income;
- actual — только `paid`;
- `reserved` входит в planned;
- USD only;
- multi-day daily rate умножается на число дней в выбранном периоде.

### 12.4 Filters

Основные:

- period;
- `Все/Бронь/Занято`;
- `Все/Оплачено/Не оплачено`.

Дополнительные:

- company;
- location.

Активные filters видны и сбрасываются одной кнопкой.

### 12.5 Presentation

Вкладка `Итоги` не повторяет календарную сетку и не показывает распределение по неделям. После выбора месяца, года или всего периода она показывает только компактную числовую сводку. Для просмотра и изменения конкретного дня пользователь переходит во вкладку `Календарь`.

## 13. Свободные даты для клиента

### 13.1 Inputs

- текущий месяц;
- следующий месяц;
- custom date range.

При входе из календаря текущим считается месяц открытой или выбранной даты, а не жёстко заданный месяц. При входе из `Итогов` используется выбранный там месяц или диапазон. Заголовок и готовый текст вычисляются из фактических границ периода.

### 13.2 Rules

- экспортируются только полностью свободные даты;
- `Бронь`, `Занято`, `Выходной` исключаются;
- любой timed tour исключает весь день из клиентского текста;
- частичная свобода показывается только гиду;
- consecutive dates объединяются в ranges.

### 13.3 Preview

Перед копированием пользователь видит готовый текст.

Пример:

```text
Свободные даты в августе: 3–5, 8, 12–14 и 21–25 августа.
```

Основная кнопка `Скопировать`. После успеха — короткое подтверждение `Скопировано`.

Если свободных дат нет, показывается спокойный empty state без пустого сообщения.

## 14. Настройки и профиль

### 14.1 Основные поля

- display name;
- Telegram ID с `Скопировать ID`;
- professional types;
- geography per type;
- notifications;
- language `Русский`;
- app/version/privacy information.

### 14.2 Guide types

Можно выбрать один, два или три:

1. `Локальный гид` — один город.
2. `Маршрутный гид` — несколько направлений или весь Узбекистан.
3. `Сопровождающий гид` — несколько направлений или весь Узбекистан.

География хранится отдельно для каждого выбранного типа.

Начальный список:

- Самарканд;
- Ташкент;
- Бухара;
- Хива;
- Каракалпакстан;
- Сурхандарья;
- Шахрисабз;
- Ферганская долина;
- весь Узбекистан — только для применимых типов.

Список расширяемый и не должен быть DB enum.

### 14.3 Telegram ID

ID показывается самому гиду для личного предъявления партнёру GuideShop. В MVP есть copy button, QR отсутствует.

### 14.4 Notifications

- enabled toggle;
- notification time;
- фактическую Telegram-доставку выполняет бот;
- обе поверхности меняют одни settings.

### 14.5 Theme and language

- theme автоматически следует Telegram;
- manual override отсутствует;
- MVP Russian only;
- strings архитектурно готовы для future UZ/EN.

## 15. System states

Каждый network screen имеет:

- initial loading;
- refresh loading без исчезновения usable data;
- empty;
- validation error;
- recoverable server error;
- unauthorized/expired session;
- offline;
- GuideShop degraded state, когда применимо;
- disabled/loading button при submit;
- success feedback;
- protection от double submit.

## 16. Visual system

### Direction

- Professional Minimal foundation;
- Telegram-native behavior;
- light Tourism OS accent.

### Brand

- official SVG only;
- main `#4E8482`;
- accent `#52B3B7`;
- wordmark font in source: Corbel Bold;
- brand font не обязан становиться UI body font.

### UI principles

- system/readable sans serif for interface;
- 44px+ practical touch targets;
- moderate radii;
- minimal shadows;
- semantic tokens;
- accessible contrast;
- no glassmorphism;
- no decorative gradients;
- no large travel photos inside operational views;
- status has non-color cue;
- motion short and functional, respecting reduced motion.

## 17. Accessibility and Telegram constraints

- safe area top/bottom;
- dynamic viewport and software keyboard;
- Telegram BackButton integration where useful;
- haptic feedback only for meaningful success/warning;
- font scaling without clipped controls;
- keyboard focus for Desktop;
- screen-reader labels;
- Russian pluralization;
- dates localized but API ISO-based;
- no reliance on hover.

## 18. Analytics and product validation

MVP analytics must be minimal and privacy-safe:

- miniapp_opened;
- date_checked;
- tour_form_opened;
- tour_saved;
- conflict_shown;
- conflict_resolved;
- availability_previewed;
- availability_copied;
- report_opened.

Не логировать содержимое notes, Telegram initData, names, IDs, companies или income values в analytics event payload без отдельного privacy review.

Целевые продуктовые метрики:

- median `open → selected date`;
- median `date selected → tour saved`;
- completion rate create tour;
- conflict correction rate;
- availability copy usage;
- error rate per operation.

## 19. Development workflow

```text
architecture
→ wireframes
→ clickable prototype
→ guide usability check
→ shared service preparation
→ API contract
→ mock frontend
→ Telegram auth/API
→ closed staging
→ parity/security/E2E
→ controlled production rollout
```

Каждый stage:

1. имеет ограниченный scope;
2. не активирует следующий stage автоматически;
3. получает targeted tests;
4. обновляет `.ai` только после реального результата;
5. заканчивается stop condition.

## 20. Этапы разработки

### MA0 — Documentation baseline

Результат:

- architecture docs;
- decisions;
- Mini App AGENTS;
- scope и invariants;
- следующий task определён.

DoD: документы согласованы, code/runtime не изменён.

### MA1 — UX flows and low-fidelity wireframes

Экраны:

- Calendar day/week/month;
- add selector;
- tour form;
- conflict;
- tour details;
- reports;
- availability preview;
- settings/profile.

DoD: все primary flows кликабельны на mock data; no backend.

### MA2 — Design system and high-fidelity prototype

- tokens;
- official brand;
- components;
- light/dark;
- responsive states;
- loading/empty/error;
- prototype in Figma.

DoD: handoff-ready screens validated on narrow iPhone, Android and Desktop frames.

### MA3 — Frontend scaffold, mock-only

Рекомендуемый baseline для отдельного утверждения при старте:

- React;
- TypeScript strict;
- Vite;
- lightweight router if needed;
- server-state library only if justified;
- component tests;
- mocked Telegram adapter and API.

DoD: all MVP screens work on deterministic mocks; no production calls or secrets.

### MA4 — Shared Guide OS service readiness

- audit create/update/delete/conflict/calendar/stats services;
- isolate Telegram-specific formatting;
- add time interval model and daily location override;
- preserve existing bot behavior;
- migrations with backup/rollback plan.

DoD: bot regression tests pass; services callable outside handlers.

### MA5 — Web API contract

- `/app/v1/session` or equivalent auth exchange;
- me/settings;
- calendar/day/month;
- tours CRUD/copy;
- availability;
- reports;
- typed errors;
- idempotency for writes.

DoD: contract examples and tests approved before frontend real-data integration.

### MA6 — Telegram authentication and session

- verify raw initData;
- auth_date freshness;
- session cookie/token strategy;
- allowlist for staging;
- ownership and CSRF/session protection;
- replay/expiry tests.

DoD: forged, expired, cross-user and missing auth fail closed.

### MA7 — Calendar and tours integration

- real user-scoped reads/writes;
- date/week/month;
- forms;
- conflict/time rules;
- multi-day location refinement;
- bot/Mini App parity.

DoD: create/update/delete in either interface immediately visible in the other.

### MA8 — Reports and availability

- summary calculations;
- filters;
- monthly workload;
- free-date generation and clipboard;
- boundaries across months/timezone.

DoD: calculations covered by fixtures and match bot/shared services.

### MA9 — Profile and notifications

- name;
- guide types/geography;
- Telegram ID copy;
- notification settings;
- theme and Russian strings.

DoD: settings are user-scoped and reflected in bot behavior where shared.

### MA10 — Closed Telegram staging

- separate test bot/token;
- separate URL/DB/secrets;
- allowlist;
- synthetic data;
- feature flags;
- monitoring/error tracking without secrets.

DoD: URL without valid test-bot initData and allowlisted ID is rejected.

### MA11 — Quality gate

- component/API/auth/ownership tests;
- iPhone/Android/Desktop;
- light/dark;
- slow/offline;
- double submit;
- refresh/session recovery;
- backup/restore;
- accessibility;
- end-to-end through test bot.

DoD: no critical defects; rollback and kill switch proven.

### MA12 — Guide pilot

- small allowlisted guide group;
- usability observation;
- 10–15 second scenario measurement;
- wording/navigation corrections only within approved scope.

DoD: guides complete primary scenarios without explanation.

### MA13 — Production readiness

- production URL and bot setup prepared but disabled;
- privacy policy;
- monitoring;
- rate limits;
- migration/backup/rollback;
- security review;
- smoke checklist;
- `MINI_APP_ENABLED=false` until approval.

### MA14 — Gradual rollout

- owner smoke;
- tiny cohort;
- observation;
- gradual exposure;
- immediate feature-flag rollback available.

### MA15 — Post-MVP

- read-only GuideShop calendar events after integration gate;
- localization;
- starter kit extraction;
- separate discovery for tips/quizzes/operator.

## 21. Test matrix

### Unit/service

- interval overlap boundaries;
- full-day vs timed;
- midnight/invalid range;
- multi-day daily rate;
- work/free/day-off counts;
- free-date range compression;
- filters;
- daily location override.

### API

- validation;
- auth/session;
- user scoping;
- idempotent writes;
- error envelope;
- concurrent/double submit.

### Security

- forged/expired initData;
- other bot signature;
- cross-user object IDs;
- XSS in free text;
- CSRF/session misuse;
- rate limiting;
- secret/PII log audit.

### UI/E2E

- create in bot → Mini App;
- create in Mini App → bot;
- edit/delete parity;
- day/week/month;
- light/dark;
- iPhone/Android/Desktop;
- keyboard/safe area;
- offline/retry;
- clipboard permission/fallback.

## 22. Definition of Done MVP

- all approved MVP flows work;
- 10–15 second primary scenario is achievable;
- bot/Mini App data parity proven;
- auth and cross-user tests pass;
- time conflicts cannot create invalid overlap;
- reports and availability calculations verified;
- themes and target clients verified;
- loading/empty/error/offline covered;
- monitoring, backup and rollback ready;
- feature flag disables Mini App;
- closed guide pilot completed;
- production exposure requires final owner approval.

## 23. Open items that do not block MA1

- exact frontend dependencies;
- final Figma component measurements;
- session transport choice;
- exact API pagination shape;
- final privacy text;
- additional geography values;
- timing of GuideShop event rendering.

These are resolved at the relevant stage, not through another broad questionnaire.
