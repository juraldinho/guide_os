from collections import Counter
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_VARIABLES = {
    "BOT_TOKEN",
    "ADMIN_ID",
    "TIMEZONE",
    "DATABASE_PATH",
    "APP_ENV",
    "GUIDESHOP_READS_ENABLED",
    "GUIDESHOP_LINKING_ENABLED",
    "GUIDESHOP_EVENTS_ENABLED",
    "GUIDESHOP_NOTIFICATIONS_ENABLED",
    "GUIDESHOP_USE_FAKE",
    "GUIDESHOP_LINK_PROVIDER_ENABLED",
    "GUIDESHOP_LINK_PROVIDER_HOST",
    "GUIDESHOP_LINK_PROVIDER_PORT",
    "GUIDESHOP_API_BASE_URL",
    "GUIDESHOP_API_TIMEOUT_SECONDS",
    "GUIDESHOP_API_MAX_RETRIES",
    "GUIDESHOP_API_MAX_RETRY_AFTER_SECONDS",
    "GUIDESHOP_JWT_KEY_ID",
    "GUIDESHOP_JWT_PRIVATE_KEY",
    "GUIDESHOP_LINK_JWT_PUBLIC_KEYS",
}

FEATURE_FLAGS = {
    "GUIDESHOP_READS_ENABLED",
    "GUIDESHOP_LINKING_ENABLED",
    "GUIDESHOP_EVENTS_ENABLED",
    "GUIDESHOP_NOTIFICATIONS_ENABLED",
    "GUIDESHOP_USE_FAKE",
    "GUIDESHOP_LINK_PROVIDER_ENABLED",
}


def parse_environment_template(text):
    assignments = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, separator, value = stripped.partition("=")
        assert separator, f"Invalid environment template line: {line!r}"
        assignments.append((name, value))
    return assignments


def test_reproducible_environment_documentation_is_complete_and_safe():
    python_version = (ROOT / ".python-version").read_text(encoding="utf-8")
    environment_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert python_version == "3.13.1\n"

    assignments = parse_environment_template(environment_text)
    counts = Counter(name for name, _ in assignments)
    values = dict(assignments)
    assert set(counts) == REQUIRED_VARIABLES
    assert all(counts[name] == 1 for name in REQUIRED_VARIABLES)
    assert all(values[name] == "false" for name in FEATURE_FLAGS)
    assert values["GUIDESHOP_API_TIMEOUT_SECONDS"] == "10.0"
    assert values["GUIDESHOP_API_MAX_RETRIES"] == "2"
    assert values["GUIDESHOP_API_MAX_RETRY_AFTER_SECONDS"] == "10.0"
    assert values["GUIDESHOP_API_BASE_URL"] == ""
    assert values["GUIDESHOP_JWT_KEY_ID"] == ""
    assert values["GUIDESHOP_JWT_PRIVATE_KEY"] == ""
    assert values["GUIDESHOP_LINK_PROVIDER_HOST"] == "127.0.0.1"
    assert values["GUIDESHOP_LINK_PROVIDER_PORT"] == "8081"
    assert values["GUIDESHOP_LINK_JWT_PUBLIC_KEYS"] == "{}"

    combined = environment_text + readme
    assert "BEGIN PRIVATE KEY" not in combined
    assert "BEGIN PUBLIC KEY" not in combined
    assert re.search(r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", combined) is None
    assert re.search(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b", combined) is None
    assert re.search(r"/Users/[^\s]+", combined) is None
    assert re.search(r"GUIDESHOP_API_BASE_URL\s*=\s*https?://", combined) is None

    canonical_commands = {
        "python3.13 -m venv venv",
        "source venv/bin/activate",
        "venv/bin/python -m pip install -r requirements.txt",
        "venv/bin/python -m pytest -q tests/test_environment_documentation.py",
        "venv/bin/python -m pytest -q",
    }
    assert all(command in readme for command in canonical_commands)
    normalized_readme = readme.casefold()
    assert "independent environments" in normalized_readme
    assert "must never be copied" in normalized_readme
    assert "current mac venv is broken" not in normalized_readme
    assert "real guideshop mode remains disabled" in normalized_readme
    assert "guideshop_use_fake=false" not in normalized_readme
