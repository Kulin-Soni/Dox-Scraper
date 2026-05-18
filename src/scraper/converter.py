import subprocess
from shutil import which
from pathlib import Path


def _convert_vtt_to_srt(subtitle: str) -> str | None:
    """Converts a VTT subtitle file to SRT using FFmpeg. Returns the SRT path, or None on failure."""
    srt_path = Path(subtitle).with_suffix(".srt").as_posix()
    try:
        subprocess.run(
            ["ffmpeg", "-nostdin", "-i", subtitle, srt_path],
            check=True, capture_output=True, text=True,
        )
        return srt_path
    except subprocess.CalledProcessError:
        return None


def _build_merge_command(video: str, srt_subtitles: list[str], output: str) -> list[str]:
    """Builds the FFmpeg command to merge video and SRT subtitles into an MKV."""
    cmd = ["ffmpeg", "-nostdin", "-i", video]
    for subtitle in srt_subtitles:
        cmd += ["-i", subtitle]
    cmd += ["-c", "copy", "-c:s", "srt", output]
    return cmd


async def convert(metadata: dict) -> dict:
    """
    Converts VTT subtitles to SRT and merges them with the video into an MKV container.
    Raises RuntimeError if FFmpeg is not installed.
    """
    if not which("ffmpeg"):
        raise RuntimeError("FFmpeg is not installed on the system.")

    video_path = Path(metadata["video"])
    output_path = (video_path.parent / f"{video_path.stem}.mkv").as_posix()

    srt_subtitles = [
        srt for subtitle in metadata["subtitles"]
        if (srt := _convert_vtt_to_srt(subtitle)) is not None
    ]

    merge_command = _build_merge_command(video_path.as_posix(), srt_subtitles, output_path)
    subprocess.run(merge_command, check=True, capture_output=True, text=True)

    metadata["video"] = output_path
    return metadata