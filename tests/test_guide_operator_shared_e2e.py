"""GO9A wrapper: run the canonical sibling Guide Operator shared E2E when present."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

OPERATOR_ROOT = Path(__file__).resolve().parents[2] / "guide operator"
OPERATOR_TEST = OPERATOR_ROOT / "tests" / "test_guide_os_shared_e2e.py"
OPERATOR_PYTHON = OPERATOR_ROOT / ".venv" / "bin" / "python"
SHARED_E2E_SKIP_REASON = "shared E2E requires sibling Guide Operator checkout"
SHARED_E2E_REQUIRED = os.getenv("GUIDE_OPERATOR_SHARED_E2E_REQUIRED") == "true"

if not OPERATOR_TEST.is_file():
    if SHARED_E2E_REQUIRED:
        raise RuntimeError("required sibling Guide Operator checkout is missing")
    pytest.skip(SHARED_E2E_SKIP_REASON, allow_module_level=True)


def test_go9a_local_two_service_http_flow_via_sibling_operator() -> None:
    if not OPERATOR_PYTHON.is_file():
        pytest.skip("sibling Guide Operator venv is missing")
    completed = subprocess.run(
        [str(OPERATOR_PYTHON), "-m", "pytest", "-q", "tests/test_guide_os_shared_e2e.py"],
        cwd=OPERATOR_ROOT,
        check=False,
    )
    assert completed.returncode == 0
