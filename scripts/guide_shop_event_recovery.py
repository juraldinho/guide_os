"""Bounded manual maintenance for the GuideShop event inbox."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.guide_shop_event_inbox import GuideShopEventInboxService


def _limit(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("limit must be 1..100") from exc
    if not 1 <= parsed <= 100:
        raise argparse.ArgumentTypeError("limit must be 1..100")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="GuideShop event inbox recovery"
    )
    parser.add_argument(
        "action", choices=("recover-abandoned", "replay-dead-letter")
    )
    parser.add_argument("--limit", type=_limit, default=100)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    service = GuideShopEventInboxService(
        clock=lambda: datetime.now(timezone.utc)
    )
    try:
        if args.action == "recover-abandoned":
            result = service.recover_abandoned(
                limit=args.limit, apply=args.apply
            )
            print(
                f"action={args.action} selected={result.selected_count} "
                f"pending={result.pending_count} "
                f"dead_letter={result.dead_letter_count}"
            )
        else:
            result = service.replay_dead_letters(
                limit=args.limit, apply=args.apply
            )
            print(
                f"action={args.action} selected={result.selected_count} "
                f"replayed={result.replayed_count}"
            )
    except Exception:
        print(f"action={args.action} failure_count=1", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
