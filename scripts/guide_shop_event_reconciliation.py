"""Sanitized read-only GuideShop event reconciliation report."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.guide_shop_event_reconciliation import (
    GuideShopEventReconciliationService,
)


def main() -> int:
    if len(sys.argv) != 1:
        print("verdict=EXECUTION_FAILURE")
        return 1
    try:
        report = GuideShopEventReconciliationService().reconcile()
    except Exception:
        print("verdict=EXECUTION_FAILURE")
        return 1
    print(f"verdict={report.verdict}")
    for name, count in report.metrics():
        print(f"{name}={count}")
    return 0 if report.verdict == "CLEAN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
