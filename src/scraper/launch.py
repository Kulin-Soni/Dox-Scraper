import asyncio
import copy
import logging
import shutil
from pathlib import Path
import traceback
from typing import Any

import aiohttp
from aiohttp.typedefs import LooseHeaders
from camoufox import AsyncCamoufox

from shared.metadata import Metadata
from shared.model import TelegramFile
from shared.mongo import init_mongo

from .anilist import AnilistGenerator
from .converter import convert
from .progress import ProgressTracker
from .proxy import ProxyServer
from .providers.anikoto import URLBuilder, HLSScraper
from core.handlers.process import app_ctx

TEMP_DIR = Path("./temp")
RECORD_FILE = Path("record.json")

logger = logging.getLogger(__name__)

def _clear_temp() -> None:
    """Removes the temp directory if it exists."""
    try:
        shutil.rmtree(TEMP_DIR)
    except FileNotFoundError:
        pass


async def _load_or_generate_anime_list(
    tracker: ProgressTracker,
) -> tuple[int, list, str]:
    """Returns saved progress if available, otherwise generates a fresh anime list."""
    page, items = tracker.load()
    if items:
        origin = URLBuilder().origin()
        return page, items, origin
    r_anime_list = await AnilistGenerator(page, 1).generate()
    entries, origin = URLBuilder(anime_list=r_anime_list).build()

    anime_list: list[dict[str, list[dict[str, str]] | dict[str, Any]]] = []
    for data, entry in zip(r_anime_list, entries):
        anime_list.append({"info": data, "entries": entry})

    return page, anime_list, origin


async def _upload_to_telegram(metadata: Metadata) -> tuple[bool, Any, Any]:
    """Sends metadata to the Telegram uploader process. Returns True if successful."""
    loop = asyncio.get_event_loop()
    app_ctx.data_q.put(metadata.model_dump_json())  # Sending serialized data
    response: dict = await loop.run_in_executor(None, app_ctx.ok_q.get)

    return (
        response.get("job") == "upload" and response.get("status") == "done",
        response.get("channel_id"),
        response.get("msg_id"),
    )


def _download_headers(provider_origin: str) -> LooseHeaders:
    """
    Build HTTP request headers for downloading from a streaming provider.

    ``Origin`` and ``Referer`` are set dynamically so the same function works
    across different provider origins without duplicating header blocks.
    """
    return {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:149.0) Gecko/20100101 Firefox/149.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Origin": provider_origin,
        "Referer": provider_origin,
        "Connection": "keep-alive",
        "Sec-GPC": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
    }


def compute_track(anime_list: list, i: int, j: int):
    temp = copy.deepcopy(anime_list)
    temp[i]["entries"] = temp[i]["entries"][j:]
    if len(temp[i]["entries"]):
        return temp[i:]
    return temp[i + 1 :]


async def scrape_job() -> None:
    """
    Main scrape job: loads or generates an anime list, scrapes each entry,
    converts media to MKV, and uploads to Telegram. Saves progress throughout.
    """
    _clear_temp()
    await init_mongo()

    tracker = ProgressTracker(RECORD_FILE)
    page, anime_list, origin = await _load_or_generate_anime_list(tracker)
    headers = _download_headers(origin)

    server = ProxyServer()
    server.launch()

    async with (
        AsyncCamoufox(
            headless=True, firefox_user_prefs={"media.volume_scale": "0.0"}
        ) as browser,
        aiohttp.ClientSession() as session,
    ):
        ctx = await browser.new_context()  # type: ignore
        for i, anime in enumerate(anime_list):
            entries = anime["entries"]
            for j, entry in enumerate(entries):

                logger.info(
                    "Scrape Job: (%s/%s) (%s/%s)",
                    j + 1,
                    len(entries),
                    i+1,
                    len(anime_list)
                )

                scraper = HLSScraper(headers)
                metadata = await scraper.scrape(entry, ctx, session)

                if metadata:
                    logger.info("Merging & converting to MKV")
                    metadata = await convert(metadata)

                    logger.info("Sending data to uploader process")
                    success, channel_id, msg_id = await _upload_to_telegram(metadata)
                    if success:
                        queries: list[str] = Path(metadata.video).stem.split("_")
                        try:
                            await TelegramFile(
                                channel_id=channel_id,
                                msg_id=msg_id,
                                queries=queries,
                                anilist=anime["info"],
                            ).create()
                            logger.info("Saved to DB")
                        except Exception:
                            logger.error("[mongo] Error saving to db, follow the log msg below:")
                            print(traceback.format_exc())
                    else:
                        logger.warning("Issue with uploader")
                        break
                else:
                    logger.info("No metadata received!")

                tracker.save(page, compute_track(anime_list, i, j))

    server.stop()
    tracker.save(page + 1, None)
