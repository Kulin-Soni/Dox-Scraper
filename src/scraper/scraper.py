import asyncio
import shutil
import typing
from os import remove
from pathlib import Path
from urllib.parse import quote

import aiofiles
import aiohttp
from aiohttp.typedefs import LooseHeaders
from camoufox.async_api import BrowserContext  # type: ignore
from tqdm import trange
from tqdm.asyncio import tqdm

# Default metadata value
_EMPTY_METADATA: typing.Dict[str, typing.Any] = {
    "video": "",
    "subtitles": [],
    "dir": "",
}

# Maximum concurrent chunk download requests
_MAX_CONCURRENT_DOWNLOADS = 75

# ---------------------------------------------------------------------------
# Media scraper
# ---------------------------------------------------------------------------

class Scraper:
    """
    Intercepts HLS (.m3u8) streams and subtitle (.vtt) files loaded by a
    browser page, downloads all TS chunks in parallel, and merges them into
    a single .ts file on disk.
    """

    def __init__(self, headers: LooseHeaders) -> None:
        self._chunk_urls: typing.List[str] = []
        self._current_title: str = ""
        self._output_dir: Path | None = None
        self._metadata: typing.Dict[str, typing.Any] = dict(_EMPTY_METADATA)
        self._media_found: bool = False
        self._headers = headers

    # ------------------------------------------------------------------
    # Browser response interception
    # ------------------------------------------------------------------

    async def _on_browser_response(self, response) -> None:
        """Called for every network response captured by Camoufox."""
        await self._handle_m3u8_or_vtt(response)

    async def _handle_m3u8_or_vtt(self, response) -> None:
        """
        Parse HLS playlist responses to collect TS chunk URLs,
        or save subtitle (VTT) responses to disk.
        """
        url = str(response.url)

        if url.endswith(".m3u8"):
            content = await response.text()
            # Only process media playlists (those containing actual segments)
            if "#EXTINF" in content:
                for line in content.splitlines():
                    if "https://" in line:
                        self._chunk_urls.append(line)

        elif url.endswith(".vtt"):
            content = await response.text()
            subtitle_filename = url.split("/")[-1]
            await self._save_subtitle(content, subtitle_filename)

    # ------------------------------------------------------------------
    # Subtitle handling
    # ------------------------------------------------------------------

    def _ensure_output_dir(self) -> None:
        """Create the per-title temp directory if it doesn't exist yet."""
        if self._output_dir is None:
            self._output_dir = Path("./temp") / self._current_title
            self._output_dir.mkdir(exist_ok=True, parents=True)

    async def _save_subtitle(self, content: str, filename: str) -> None:
        """Append subtitle content to a VTT file inside the output directory."""
        self._ensure_output_dir()
        subtitle_path = self._output_dir / f"{self._current_title}_{filename}.vtt"

        self._metadata["dir"] = self._output_dir

        async with aiofiles.open(subtitle_path.resolve(), "a") as f:
            await f.write(content)

        self._metadata["subtitles"].append(subtitle_path.as_posix())

    # ------------------------------------------------------------------
    # Chunk download and merge
    # ------------------------------------------------------------------

    async def _download_and_merge_chunks(self, session: aiohttp.ClientSession) -> None:
        """
        Download all collected TS chunk URLs concurrently, write each to a
        numbered temp file, then concatenate them in order into a single .ts file.
        """
        if not self._chunk_urls:
            return

        self._ensure_output_dir()
        self._media_found = True

        output_path = self._output_dir / f"{self._current_title}.ts"
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_DOWNLOADS)

        async def download_chunk(url: str, index: int, progress: tqdm) -> None:
            temp_path = self._output_dir / f"temp_{index}.ts"
            try:
                async with semaphore, aiofiles.open(temp_path, "w+b") as f:
                    response = await session.get(url, headers=_DOWNLOAD_HEADERS)
                    data = await response.read()
                    await f.write(data)
                    await f.flush()
            except Exception as e:
                print(f"[chunk {index}] Download error: {e}")
            finally:
                progress.update(1)

        # Download all chunks concurrently
        with tqdm(
            total=len(self._chunk_urls), unit="chunks", desc="=> Downloading "
        ) as bar:
            await asyncio.gather(
                *(
                    asyncio.create_task(download_chunk(url, i, bar))
                    for i, url in enumerate(self._chunk_urls)
                )
            )

        # Merge temp files in order into the final .ts file
        with open(output_path, "ab") as merged:
            for i in trange(len(self._chunk_urls), desc="=> Merging ", unit="file"):
                temp_path = self._output_dir / f"temp_{i}.ts"
                with open(temp_path.resolve(), "rb") as temp:
                    merged.write(temp.read())
                merged.flush()

        self._metadata["video"] = output_path.as_posix()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def _cleanup(self) -> None:
        """Remove per-chunk temp files and reset scraper state for the next run."""
        if self._media_found and self._output_dir:
            for i in range(len(self._chunk_urls)):
                temp_path = self._output_dir / f"temp_{i}.ts"
                remove(temp_path)

        self._chunk_urls.clear()
        self._media_found = False
        self._output_dir = None
        self._metadata = dict(_EMPTY_METADATA)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def scrape(
        self,
        target: dict,
        browser_ctx: BrowserContext,
        http_session: aiohttp.ClientSession,
    ) -> dict | None:
        """
        Open `target["url"]` inside the proxy server via Camoufox, wait for
        HLS stream responses, download all chunks, and return metadata:

            {
                "video":     "<path to merged .ts file>",
                "subtitles": ["<path to .vtt>", ...],
                "dir":       "<output directory>",
            }

        Returns None if no media was found or an error occurred.
        """
        metadata = dict(_EMPTY_METADATA)
        try:
            self._current_title = target["name"]

            page = await browser_ctx.new_page()
            page.on("response", self._on_browser_response)

            proxied_url = f"http://localhost:8280?url={quote(target['url'])}"
            await page.goto(proxied_url)
            await page.wait_for_load_state("domcontentloaded")

            # Give the player a moment to trigger playlist requests
            await asyncio.sleep(5)
            await page.close()

            await self._download_and_merge_chunks(http_session)

            metadata = self._metadata
            found = self._media_found

            await self._cleanup()

            if found:
                return metadata

            # No video found; clean up any subtitle-only directory
            if metadata["dir"]:
                shutil.rmtree(metadata["dir"])
            return None

        except Exception as e:
            print(f"[scrape] Error for '{target.get('name')}': {e}")
            if metadata["dir"]:
                shutil.rmtree(metadata["dir"])
            return None
