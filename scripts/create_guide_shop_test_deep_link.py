#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db import init_db
from services.guide_shop_navigation import (
    GuideShopRoute,
    build_navigation_deep_link,
    create_navigation_token,
)


def _positive_user_id(value: str) -> int:
    try:
        user_id = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if user_id <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return user_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a development GuideShop test deep link."
    )
    parser.add_argument(
        "--telegram-user-id",
        required=True,
        type=_positive_user_id,
    )
    parser.add_argument("--bot-username", default="Guideosbot")
    args = parser.parse_args(argv)

    load_dotenv()
    if os.getenv("APP_ENV") != "development":
        parser.error("APP_ENV must be development")

    init_db()
    route = GuideShopRoute(kind="visits")
    token = create_navigation_token(args.telegram_user_id, route)
    url = build_navigation_deep_link(args.bot_username, token.raw_token)
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
