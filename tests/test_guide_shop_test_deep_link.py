import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest

from database.db import get_connection
from services.guide_shop_navigation import (
    GuideShopRoute,
    NavigationTokenAccessDeniedError,
    NavigationTokenConsumedError,
    NavigationToken,
    resolve_navigation_token,
)
from scripts import create_guide_shop_test_deep_link as helper


ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
SCRIPT = ROOT / "scripts" / "create_guide_shop_test_deep_link.py"


def run_helper(*arguments: str, app_env: str | None = None):
    environment = os.environ.copy()
    if app_env is None:
        environment.pop("APP_ENV", None)
    else:
        environment["APP_ENV"] = app_env
    return subprocess.run(
        [str(PYTHON), str(SCRIPT), *arguments],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_refuses_when_app_env_is_missing(monkeypatch, capsys):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setattr(helper, "load_dotenv", Mock())
    with pytest.raises(SystemExit) as error:
        helper.main(["--telegram-user-id", "101"])
    assert error.value.code != 0
    assert "APP_ENV must be development" in capsys.readouterr().err


@pytest.mark.parametrize("app_env", ["test", "staging", "production"])
def test_refuses_non_development_environments(monkeypatch, capsys, app_env):
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setattr(helper, "load_dotenv", Mock())
    with pytest.raises(SystemExit) as error:
        helper.main(["--telegram-user-id", "101"])
    assert error.value.code != 0
    assert "APP_ENV must be development" in capsys.readouterr().err


@pytest.mark.parametrize(
    "user_id",
    ["0", "-1", "true", "false", "yes", "no", "1.5", "not-an-integer"],
)
def test_rejects_invalid_telegram_user_ids(user_id):
    result = run_helper(
        "--telegram-user-id",
        user_id,
        app_env="development",
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert "positive integer" in result.stderr


def test_reuses_existing_services_and_initialization(monkeypatch, capsys):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(helper, "load_dotenv", Mock())
    init_db = Mock()
    create_token = Mock(
        return_value=NavigationToken(
            raw_token="gs_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef",
            expires_at=Mock(),
        )
    )
    build_link = Mock(return_value="https://t.me/Guideosbot?start=opaque")
    monkeypatch.setattr(helper, "init_db", init_db)
    monkeypatch.setattr(helper, "create_navigation_token", create_token)
    monkeypatch.setattr(helper, "build_navigation_deep_link", build_link)

    assert helper.main(["--telegram-user-id", "101"]) == 0
    init_db.assert_called_once_with()
    create_token.assert_called_once_with(101, GuideShopRoute(kind="visits"))
    build_link.assert_called_once_with(
        "Guideosbot", "gs_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    )
    assert capsys.readouterr().out == "https://t.me/Guideosbot?start=opaque\n"


def test_successful_subprocess_execution_creates_user_bound_single_use_visits_link():
    user_id = 8_765_432_101_234_567
    result = run_helper(
        "--telegram-user-id",
        str(user_id),
        "--bot-username",
        "@LocalGuideBot",
        app_env="development",
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1

    url = result.stdout.rstrip("\n")
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "t.me"
    assert parsed.path == "/LocalGuideBot"
    assert set(parse_qs(parsed.query)) == {"start"}
    raw_token = parse_qs(parsed.query)["start"][0]
    assert url == f"https://t.me/LocalGuideBot?start={raw_token}"
    assert str(user_id) not in url
    assert "visits" not in url
    assert "object" not in url

    with pytest.raises(NavigationTokenAccessDeniedError):
        resolve_navigation_token(raw_token, user_id + 1)

    route = resolve_navigation_token(raw_token, user_id)
    assert route == GuideShopRoute(kind="visits")

    with pytest.raises(NavigationTokenConsumedError):
        resolve_navigation_token(raw_token, user_id)

    conn = get_connection()
    user = conn.execute(
        "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    assert user is None
