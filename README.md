# Guide OS

Текущий release 2026-10-29: чаевые и переход из новых напоминаний в точную карточку работают в production. [Технические проверки и текущие deployment IDs](docs/REMINDER_MINIAPP_LINK.md). Manual Telegram E2E и owner Git/source alignment остаются отдельными follow-up.

> Сводка обновлена 2026-10-29 по записанным release evidence: [реализация и окружения](docs/CURRENT_STATE.md). Исторические PASS относятся к своим датам; эта docs-правка не является новым live-аудитом.

Guide OS is a Telegram bot for guides to manage tours, schedules, income,
notifications, and optional GuideShop views.

## Released features and future roadmap

The owner-approved, not-yet-implemented one-way Google Calendar import roadmap is documented in [`docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md`](docs/mini_app/GOOGLE_CALENDAR_ROADMAP.md). It covers importing external events, supplementing them in Guide OS, and converting them into native tours without writing back to Google.

Daily tips are implemented Mini App-first and deployed to production (2026-10-27): one total per user/date, independent of tours, with separate tour/tips/combined income. [Roadmap](docs/TIPS_ROADMAP.md), [release evidence](docs/DAILY_TIPS_IMPLEMENTATION.md). New reminders also link directly to the exact Mini App tour card (production 2026-10-29): [handoff](docs/REMINDER_MINIAPP_LINK.md). Telegram bot tips UX/statistics remain deferred.

The completed GuideShop Mini App GSMA0–GSMA10 pilot workstream is documented in [`docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`](docs/mini_app/GUIDESHOP_MINIAPP_ROADMAP.md). It provides scalable bottom navigation, personal companies/commissions and the official read-only GuideShop catalog. Guide Operator adds a fourth module; its production rollout remains separately gated.

## Prerequisites

- Python 3.13.14
- A Telegram bot token for local execution

Each Mac, Railway service, or other environment needs its own virtual
environment and secrets. Paths differ between environments, so a virtual
environment must never be copied between Macs or deployments.

Railpack reads the exact runtime from `.python-version`. The pinned release
has an attested precompiled mise artifact; GitHub artifact verification must
remain enabled.

## Fresh local setup

Create and activate a new virtual environment on macOS:

```sh
python3.13 -m venv venv
source venv/bin/activate
```

Install the pinned project dependencies:

```sh
venv/bin/python -m pip install -r requirements.txt
```

Create local configuration from the sanitized template:

```sh
cp .env.example .env
```

Replace the empty `BOT_TOKEN` value in `.env` with a local Telegram bot token.
Do not reuse production secrets.

Run the existing entrypoint; startup initializes the local database when
needed:

```sh
venv/bin/python bot.py
```

## Tests

Run the focused environment-documentation test:

```sh
venv/bin/python -m pytest -q tests/test_environment_documentation.py
```

Run the complete suite:

```sh
venv/bin/python -m pytest -q
```

## Local GuideShop fake

GuideShop is off by default. For an explicit development-only fake, set
`APP_ENV=development`, `GUIDESHOP_READS_ENABLED=true`, and
`GUIDESHOP_USE_FAKE=true` in the local `.env`. This uses the existing empty
in-memory GuideShop client and requires no API URL or signing key.

Real GuideShop mode remains disabled in fresh local configuration unless explicitly configured. The historical staging API/verifier and production integration stages are complete. This repository does not provide instructions that activate
real mode.

## Security and environment isolation

Never commit `.env`, database files, logs, private keys, bot tokens, access
tokens, or other credentials. Keep `BOT_TOKEN` in the environment or an
approved secrets manager. The Ed25519 private key for real GuideShop
composition must also be supplied through environment secrets and must never
be stored in the repository.

The current Mac, Mac Neo, and Railway are independent environments with
different filesystem paths, separately created virtual environments, and
separate secrets. Never copy `venv` between them. The audit observation about
a broken virtual environment concerned a separate Guide OS checkout on Mac
Neo; it did not describe the current Mac environment.
