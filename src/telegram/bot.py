import logging

from telethon import TelegramClient

from .constants import API_ID, API_HASH

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="[%(levelname)s %(asctime)s] %(name)s: %(message)s",
    level=logging.WARNING,
)

# ---------------------------------------------------------------------------
# Telegram client
# ---------------------------------------------------------------------------

# Session name "dox" persists the auth session to dox.session on disk.
client = TelegramClient("dox", api_id=API_ID, api_hash=API_HASH)