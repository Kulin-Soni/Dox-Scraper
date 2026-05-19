import shutil
from pathlib import Path

import aiohttp
from aiohttp.typedefs import LooseHeaders
from camoufox import AsyncCamoufox

from .anilist import AnilistGenerator
from .converter import convert
from .progress import ProgressTracker
from .hls import HLSScraper
from .proxy import ProxyServer
from .providers.megabuzz import URLBuilder
from core.handlers.process import app_ctx

TEMP_DIR = Path("./temp")
RECORD_FILE = Path("record.json")


def _clear_temp() -> None:
    """Removes the temp directory if it exists."""
    try:
        shutil.rmtree(TEMP_DIR)
    except FileNotFoundError:
        pass


async def _load_or_generate_anime_list(tracker: ProgressTracker) -> tuple[int, list, str]:
    """Returns saved progress if available, otherwise generates a fresh anime list."""
    page, items = tracker.load()
    if items:
        origin = URLBuilder().origin()
        return page, items, origin
    anime_list = await AnilistGenerator(page, 1).generate()
    anime_list, origin = URLBuilder(anime_list=anime_list).build()
    return page, anime_list, origin


def _upload_to_telegram(metadata: dict) -> bool:
    """Sends metadata to the Telegram uploader process. Returns True if successful."""
    app_ctx.data_q.put(metadata)
    response = app_ctx.ok_q.get()
    return response.get("job") == "upload" and response.get("status") == "done"

def _download_headers(provider_origin: str) -> LooseHeaders:
    """
    Build HTTP request headers for downloading from a streaming provider.

    ``Origin`` and ``Referer`` are set dynamically so the same function works
    across different provider origins without duplicating header blocks.
    """
    return {
        "User-Agent":      "Mozilla/5.0 (X11; Linux x86_64; rv:149.0) Gecko/20100101 Firefox/149.0",
        "Accept":          "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Origin":          provider_origin,
        "Referer":         provider_origin,
        "Connection":      "keep-alive",
        "Sec-GPC":         "1",
        "Sec-Fetch-Dest":  "empty",
        "Sec-Fetch-Mode":  "cors",
        "Sec-Fetch-Site":  "cross-site",
    }


async def scrape_job() -> None:
    """
    Main scrape job: loads or generates an anime list, scrapes each entry,
    converts media to MKV, and uploads to Telegram. Saves progress throughout.
    """
    _clear_temp()

    tracker = ProgressTracker(RECORD_FILE)
    page, anime_list, origin = await _load_or_generate_anime_list(tracker)

    scraper = HLSScraper(
        _download_headers(origin)
    )
    server = ProxyServer()
    server.launch()

    async with AsyncCamoufox(headless=True) as browser, aiohttp.ClientSession() as session:
        ctx = await browser.new_context()  # type: ignore

        for i, anime in enumerate(anime_list):
            print(f"\n=> Scrape Job: ({i + 1}/{len(anime_list)})")

            metadata = await scraper.scrape(anime, ctx, session)

            if metadata:
                print("=> Merging & converting to MKV")
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