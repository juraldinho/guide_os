from pathlib import Path
import re


WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
)


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
