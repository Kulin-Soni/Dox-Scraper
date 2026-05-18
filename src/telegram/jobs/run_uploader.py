import asyncio
import json
import mimetypes
import shutil
import subprocess
from pathlib import Path

from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import (
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    InputMediaUploadedDocument,
)

from telegram.bot import client
from telegram.constants import STORE_CHANNEL_ID
from telegram.utils.parallel import UploadManager

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_DEFAULT_VIDEO_INFO = {"width": 0, "height": 0, "duration": 0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_duration(duration_str: str) -> float:
    """
    Convert an HH:MM:SS.sss timestamp string into total seconds.

    The string is split on ":", reversed so index 0 = seconds, 1 = minutes,
    2 = hours, then each component is weighted by 60^i.

    Returns 0.0 if the string is empty or malformed.
    """
    if not duration_str:
        return 0.0

    parts = list(reversed(duration_str.split(":")))
    return sum(float(part) * (60 ** i) for i, part in enumerate(parts))


def get_video_info(path: str | Path) -> dict:
    """
    Use ffprobe to extract width, height, and duration from a video file.

    Returns a dict with keys ``width``, ``height``, and ``duration`` (seconds).
    Falls back to zeros if no video stream is found.
    """
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    streams = json.loads(result.stdout).get("streams", [])

    for stream in streams:
        if stream.get("codec_type") != "video":
            continue

        raw_duration = stream.get("tags", {}).get("DURATION", "")
        return {
            "width":    stream["width"],
            "height":   stream["height"],
            "duration": _parse_duration(raw_duration),
        }

    return _DEFAULT_VIDEO_INFO.copy()


# ---------------------------------------------------------------------------
# Upload worker
# ---------------------------------------------------------------------------

async def upload_to_telegram(ctx) -> None:
    """
    Consume video metadata from the data queue and upload each file to Telegram.

    Flow per iteration
    ------------------
    1. Dequeue a metadata dict containing at least a ``"video"`` path.
    2. Upload the video file via UploadManager.
    3. Send the uploaded file to the store channel as a streaming document.
    4. Signal completion on the ok queue.
    5. Remove the parent folder to free disk space.

    The worker blocks until the "p2" process is ready before entering the loop.
    """
    # Wait for the dependent process to be fully started before consuming work.
    await asyncio.to_thread(ctx.wait_for, "p2")

    while True:
        metadata  = await asyncio.to_thread(ctx.data_q.get)
        video_path = Path(metadata["video"])

        # --- Upload raw bytes to Telegram ---
        manager     = UploadManager(client=client, file_path=video_path)
        uploaded    = await manager.upload_file()
        video_info  = get_video_info(video_path)

        mime_type = mimetypes.guess_type(video_path)[0] or "application/octet-stream"
        attributes = [
            DocumentAttributeFilename(video_path.name),
            DocumentAttributeVideo(
                duration=video_info["duration"],
                w=video_info["width"],
                h=video_info["height"],
                supports_streaming=True,
            ),
        ]

        # --- Send the document to the store channel ---
        await client(  # type: ignore[operator]
            SendMediaRequest(
                peer=STORE_CHANNEL_ID,
                media=InputMediaUploadedDocument(
                    file=uploaded,
                    thumb=None,
                    mime_type=mime_type,
                    attributes=attributes,
                ),
                message=video_path.name,
            )
        )

        # Acknowledge completion so the coordinator can proceed.
        ctx.ok_q.put({"job": "upload", "status": "done"}, timeout=10)

        # Clean up the working directory now that the upload is confirmed.
        shutil.rmtree(video_path.parent)


def upload_job(ctx) -> None:
    """Entry point for the upload worker process; runs the async loop synchronously."""
    asyncio.run(upload_to_telegram(ctx))