import shutil
from pathlib import Path

import aiohttp
from camoufox import AsyncCamoufox

from .anilist import AnilistGenerator
from .converter import convert
from .progress import ProgressTracker
from .scraper import Scraper
from .proxy import ProxyServer
from core.handlers.process import app_ctx

TEMP_DIR = Path("./temp")
RECORD_FILE = Path("record.json")


def _clear_temp() -> None:
    """Removes the temp directory if it exists."""
    try:
        shutil.rmtree(TEMP_DIR)
    except FileNotFoundError:
        pass


async def _load_or_generate_anime_list(tracker: ProgressTracker) -> tuple[int, list]:
    """Returns saved progress if available, otherwise generates a fresh anime list."""
    page, items = tracker.load()
    if items:
        return page, items
    anime_list = await AnilistGenerator(page, 1).generate()
    return page, anime_list


def _upload_to_telegram(metadata: dict) -> bool:
    """Sends metadata to the Telegram uploader process. Returns True if successful."""
    app_ctx.data_q.put(metadata)
    response = app_ctx.ok_q.get()
    return response.get("job") == "upload" and response.get("status") == "done"


async def scrape_job() -> None:
    """
    Main scrape job: loads or generates an anime list, scrapes each entry,
    converts media to MKV, and uploads to Telegram. Saves progress throughout.
    """
    _clear_temp()

    tracker = ProgressTracker(RECORD_FILE)
    page, anime_list = await _load_or_generate_anime_list(tracker)

    scraper = Scraper()
    server = ProxyServer()
    server.launch()

    async with AsyncCamoufox(headless=True) as browser, aiohttp.ClientSession() as session:
        ctx = await browser.new_context()  # type: ignore

        for i, anime in enumerate(anime_list):
            print(f"\n=> Scrape Job: ({i + 1}/{len(anime_list)})")

            metadata = await scraper.scrape(anime, ctx, session)

            if metadata:
                print("=> Converting to MKV")
                metadata = await convert(metadata)

                print("=> Attempting data transfer to Telegram")
                if not _upload_to_telegram(metadata):
                    print("=> Issue with uploader")
                    break
            else:
                print("=> No metadata received!")

            tracker.save(page, anime_list[i:])

    server.stop()
    tracker.save(page + 1, None)