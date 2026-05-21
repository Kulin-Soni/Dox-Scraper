from beanie import Document
from typing import Any

class TelegramFile(Document):
    channel_id: int
    msg_id: int
    queries: list[str]
    anilist: dict[str, Any]

    class Settings:
        name = "telegram_files"