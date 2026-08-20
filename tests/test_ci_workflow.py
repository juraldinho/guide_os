from pathlib import Path
import re
import os
import shutil
import subprocess
import sys

import pytest


WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
)
SHARED_WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "shared-event-e2e.yml"
)
SHARED_TEST = (
    Path(__file__).resolve().parent / "test_guide_shop_event_shared_e2e.py"
)
GUIDESHOP_COMMIT = "4cf1c10b76303af6c5b1e95a26175a7ede1a3fc7"


def test_ci_workflow_is_safe_complete_and_test_only():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    normalized = workflow.casefold()

    assert re.search(r"(?m)^on:\s*$", workflow)
    assert re.search(r"(?m)^  push:\s*$", workflow)
    assert re.search(r"(?m)^  pull_request:\s*$", workflow)
    assert "pull_request_target" not in workflow
    assert "schedule:" not in normalized

    permissions = re.search(
        r"(?ms)^permissions:\s*\n(?P<body>(?:  [^\n]+\n)+)", workflow
    )
    assert permissions
    assert permissions.group("body").strip() == "contents: read"

    assert re.search(r"(?m)^concurrency:\s*$", workflow)
    assert "github.workflow" in workflow
    assert "github.ref" in workflow
    assert re.search(r"(?m)^  cancel-in-progress: true\s*$", workflow)
    assert "runs-on: ubuntu-latest" in workflow
    assert "actions/checkout@v6" in workflow
    assert "actions/setup-python@v6" in workflow
    assert "python-version-file: .python-version" in workflow
    assert re.search(r"(?m)^\s+cache: pip\s*$", workflow)
    assert "cache-dependency-path: requirements.txt" in workflow

    required_commands = {
        "python -m pip install --disable-pip-version-check -r requirements.txt",
        "python -m pip check",
        "git diff --check",
        "python -m pytest -q",
    }
    assert all(command in workflow for command in required_commands)

    forbidden_text = {
        "bot.py",
        "railway",
        "actions/upload-artifact",
        "begin private key",
        "guideshop_api_base_url",
        "guideshop_jwt_key_id",
        "guideshop_jwt_private_key",
    }
    assert all(value not in normalized for value in forbidden_text)
    assert re.search(r"\b(deploy|curl|wget)\b", normalized) is None
    assert "${{ secrets." not in normalized
    assert re.search(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b", workflow) is None
    assert re.search(r'(?m)^\s+BOT_TOKEN: "ci-placeholder"\s*$', workflow)
    assert re.search(r'(?m)^\s+APP_ENV: "test"\s*$', workflow)

    for name in (
        "GUIDESHOP_READS_ENABLED",
        "GUIDESHOP_LINKING_ENABLED",
        "GUIDESHOP_EVENTS_ENABLED",
        "GUIDESHOP_NOTIFICATIONS_ENABLED",
        "GUIDESHOP_USE_FAKE",
    ):
        assert re.search(rf'(?m)^\s+{name}: "false"\s*$', workflow)


def test_shared_event_e2e_workflow_is_pinned_isolated_and_fail_closed():
    workflow = SHARED_WORKFLOW.read_text(encoding="utf-8")
    normalized = workflow.casefold()
    test_source = SHARED_TEST.read_text(encoding="utf-8")

    assert re.search(r"(?m)^on:\s*$", workflow)
    assert re.search(r"(?m)^  push:\s*$", workflow)
    assert re.search(r"(?m)^  pull_request:\s*$", workflow)
    assert "pull_request_target" not in workflow
    assert "schedule:" not in normalized
    assert re.search(r"(?ms)^permissions:\s*\n  contents: read\s*$", workflow)
    assert "runs-on: ubuntu-latest" in workflow
    assert 'GUIDESHOP_SHARED_E2E_REQUIRED: "true"' in workflow
    assert "actions/checkout@v6" in workflow
    assert "repository: juraldinho/guideshop" in workflow
    assert f"ref: {GUIDESHOP_COMMIT}" in workflow
    assert re.search(r"(?m)^\s+path: guide_os\s*$", workflow)
    assert re.search(r"(?m)^\s+path: guideshop\s*$", workflow)
    assert 'python-version: "3.13.14"' in workflow
    assert "-r guide_os/requirements.txt" in workflow
    assert "-r guideshop/requirements.txt" in workflow
    assert "python -m pip check" in workflow
    assert "python -m pytest -q tests/test_guide_shop_event_shared_e2e.py" in workflow
    assert workflow.count("python -m pytest") == 1
    assert "git diff --check" in workflow
    assert "actual_commit=\"$(git rev-parse HEAD)\"" in workflow
    assert f'expected_commit="{GUIDESHOP_COMMIT}"' in workflow
    assert "persist-credentials: false" in workflow
    secret_references = re.findall(r"secrets\.[A-Za-z0-9_]+", workflow)
    assert secret_references == ["secrets.CONTRACTS_READ_TOKEN"]
    guide_os_checkout, guideshop_checkout = workflow.split(
        "      - name: Checkout immutable GuideShop", maxsplit=1
    )
    guideshop_checkout = guideshop_checkout.split(
        "      - name: Verify immutable GuideShop identity", maxsplit=1
    )[0]
    assert "secrets." not in guide_os_checkout
    assert (
        "          token: ${{ secrets.CONTRACTS_READ_TOKEN }}"
        in guideshop_checkout
    )
    assert guideshop_checkout.count("secrets.CONTRACTS_READ_TOKEN") == 1
    for forbidden in ("bot_token", "railway", "curl", "wget", "deploy"):
        assert forbidden not in normalized

    assert 'parents[2] / "guideshop"' in test_source
    assert "if SHARED_E2E_REQUIRED:" in test_source
    assert 'raise RuntimeError("required sibling GuideShop checkout is missing")' in test_source


def test_shared_event_e2e_missing_sibling_skips_only_in_ordinary_mode(tmp_path):
    isolated_root = tmp_path / "workspace" / "guide_os"
    isolated_test = isolated_root / "tests" / SHARED_TEST.name
    isolated_test.parent.mkdir(parents=True)
    shutil.copy2(SHARED_TEST, isolated_test)
    environment = os.environ.copy()
    environment.pop("GUIDESHOP_SHARED_E2E_REQUIRED", None)

    ordinary = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rs", str(isolated_test)],
        cwd=isolated_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ordinary.returncode == pytest.ExitCode.NO_TESTS_COLLECTED
    assert "1 skipped" in ordinary.stdout
    assert "shared E2E requires sibling GuideShop checkout" in ordinary.stdout

    environment["GUIDESHOP_SHARED_E2E_REQUIRED"] = "true"
    required = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(isolated_test)],
        cwd=isolated_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert required.returncode != 0
    assert "required sibling GuideShop checkout is missing" in (
        required.stdout + required.stderr
    )
