"""The Telegram bot token, resolved from disk first and the environment second.

Why the file wins
-----------------
The sandbox injects ``TELEGRAM_BOT_TOKEN`` when a session starts, so a token
rotated mid-session keeps posting from the old bot — and the old bot is the
one whose token a third-party panel had (the profile of ``@yip0802_bot``
was turned into porn referral spam that way). The on-disk copy is the single
source of truth for the sandbox side.

CI has no such file and reads the GitHub Actions secret, which is updated
the same way.

Every script that sends a message imports this rather than reading the
environment directly, so one place decides where the token comes from.
"""
import os
from pathlib import Path

TOKEN_FILE = Path(os.environ.get(
    "TELEGRAM_BOT_TOKEN_FILE", "/workspace/.secrets/telegram_bot_token"))


def get_token() -> str:
    """The bot token, or an empty string when there is none."""
    try:
        if TOKEN_FILE.exists():
            value = TOKEN_FILE.read_text().strip()
            if value:
                return value
    except OSError:
        pass
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


TG_TOKEN = get_token()
