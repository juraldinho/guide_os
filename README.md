# Guide OS

Guide OS is a Telegram bot for guides to manage tours, schedules, income,
notifications, and optional GuideShop views.

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

Real GuideShop mode remains disabled until the GuideShop staging API and
verifier exist. This repository does not provide instructions that activate
real mode.

## Security and environment isolation

Never commit `.env`, database files, logs, private keys, bot tokens, access
tokens, or other credentials. Keep `BOT_TOKEN` in the environment or an
approved secrets manager. The Ed25519 private key for future real GuideShop
composition must also be supplied through environment secrets and must never
be stored in the repository.

The current Mac, Mac Neo, and Railway are independent environments with
different filesystem paths, separately created virtual environments, and
separate secrets. Never copy `venv` between them. The audit observation about
a broken virtual environment concerned a separate Guide OS checkout on Mac
Neo; it did not describe the current Mac environment.
