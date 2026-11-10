"""Business timezone configuration independent of Telegram bot credentials."""

import os

from dotenv import load_dotenv

load_dotenv()
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tashkent")
