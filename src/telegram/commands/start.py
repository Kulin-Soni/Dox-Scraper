from telegram.handlers.commands import Command
from telethon import TelegramClient
from telethon.tl.custom.message import Message

@Command(name="start")
async def start(event: Message, client: TelegramClient):
    await event.respond("Hey, am alive!\n\nFollowing commands are available -\n/find : Use to search for anime") 
