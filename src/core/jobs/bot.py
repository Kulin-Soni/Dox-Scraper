import asyncio
import logging
from shared.logger import config_logger
from telegram.launch import telegram_jobs

def launch_bot_job(*_):
    config_logger()
    logger = logging.getLogger(__name__)
    logger.info("Starting bot and uploader")
    
    asyncio.run(telegram_jobs())