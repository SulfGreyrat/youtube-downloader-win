"""yt-dlp wrapper: format listing, download, progress.

No Tkinter imports here — this module is UI-agnostic and unit-testable.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from typing import Callable, Optional

import yt_dlp

#: Synthetic format id for the "best available" convenience entry.
BEST_FORMAT_ID = "bestvideo+bestaudio/best"


class DownloaderError(Exception):
    """Any user-facing failure coming out of this module."""


@dataclass
class FormatInfo:
    format_id: str
    ext: str
    resolution: str
    fps: Optional[float]
    vcodec: str
    acodec: str
    filesize_approx: Optional[int]
    note: str

    @property
    def is_video_only(self) -> bool:
        return self.vcodec != "none" and self.acodec == "none"

    @property
    def is_audio_only(self) -> bool:
        return self.vcodec == "none" and self.acodec != "none"


def _human_size(num: Optional[int]) -> str:
    if not num:
        return "size unknown"
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"~{value:.1f}{unit}"
        value /= 1024
    return f"~{value:.1f}GB"


def _make_note(fmt: dict) -> str:
    vcodec = fmt.get("vcodec") or "none"
    acodec = fmt.get("acodec") or "none"
    ext = fmt.get("ext") or "?"
    size = _human_size(fmt.get("filesize") or fmt.get("filesize_approx"))

    if vcodec == "none":
        abr = fmt.get("abr")
        label = f"audio only{f' {abr:.0f}kbps' if abr else ''}"
    else:
        height = fmt.get("height")
        fps = fmt.get("fps")
        label = f"{height}p" if height else (fmt.get("resolution") or "video")
        if fps:
            label += f"{int(fps)}"
        if acodec == "none":
            label += " (video only, will be merged with audio)"
        else:
            label += " (video+audio)"

    return f"{label} — {ext} — {size} [id {fmt.get('format_id')}]"


def _resolution_of(fmt: dict) -> str:
    if (fmt.get("vcodec") or "none") == "none":
        return "audio only"
    w, h = fmt.get("width"), fmt.get("height")
    if w and h:
        return f"{w}x{h}"
    return fmt.get("resolution") or "unknown"


def list_formats(url: str) -> tuple[str, list[FormatInfo]]:
    """Return (video_title, formats) sorted best-quality-first.

    The first entry is always the synthetic "Best available" option.
    """
    url = (url or "").strip()
    if not url:
        raise DownloaderError("Please paste a video URL first.")

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise DownloaderError(str(exc)) from exc
    except Exception as exc:  # network, parsing, ...
        raise DownloaderError(f"Could not fetch video info: {exc}") from exc

    if info is None:
        raise DownloaderError("No video information returned for this URL.")
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise DownloaderError("This URL resolved to an empty playlist.")
        info = entries[0]

    title = info.get("title") or "(untitled)"

    raw_formats = info.get("formats") or []
    result: list[FormatInfo] = []
    for fmt in raw_formats:
        vcodec = fmt.get("vcodec") or "none"
        acodec = fmt.get("acodec") or "none"
        if vcodec == "none" and acodec == "none":
            continue  # storyboards / thumbnails
        if not fmt.get("format_id"):
            continue
        result.append(
            FormatInfo(
                format_id=str(fmt["format_id"]),
                ext=fmt.get("ext") or "?",
                resolution=_resolution_of(fmt),
                fps=fmt.get("fps"),
                vcodec=vcodec,
                acodec=acodec,
                filesize_approx=fmt.get("filesize") or fmt.get("filesize_approx"),
                note=_make_note(fmt),
            )
        )

    result.sort(
        key=lambda f: (
            0 if f.vcodec == "none" else 1,   # video formats above audio-only
            _height_of(f),
            f.filesize_approx or 0,
        ),
        reverse=True,
    )

    best = FormatInfo(
        format_id=BEST_FORMAT_ID,
        ext="mp4",
        resolution="best",
        fps=None,
        vcodec="?",
        acodec="?",
        filesize_approx=None,
        note="Best available (auto, video+audio merged)",
    )
    return title, [best] + result


def _height_of(f: FormatInfo) -> int:
    try:
        return int(f.resolution.split("x")[1])
    except (IndexError, ValueError):
        return 0


def find_ffmpeg() -> Optional[str]:
    """Locate ffmpeg: next to the exe/script first, then PATH."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    for candidate_dir in (base, os.path.dirname(base)):
        candidate = os.path.join(candidate_dir, "ffmpeg.exe")
        if os.path.isfile(candidate):
            return candidate_dir

    found = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if found:
        return os.path.dirname(found)
    return None


def _needs_merge(format_id: str, formats: Optional[list[FormatInfo]]) -> bool:
    if format_id == BEST_FORMAT_ID:
        return True
    if not formats:
        return False
    for f in formats:
        if f.format_id == format_id:
            return f.is_video_only
    return False


def download(
    url: str,
    format_id: str,
    output_dir: str,
    progress_callback: Callable[[dict], None],
    formats: Optional[list[FormatInfo]] = None,
) -> str:
    """Download `format_id` into `output_dir`; return the final file path."""
    url = (url or "").strip()
    if not url:
        raise DownloaderError("Please paste a video URL first.")
    if not output_dir:
        raise DownloaderError("Please choose an output folder.")

    try:
        os.makedirs(output_dir, exist_ok=True)
        probe = os.path.join(output_dir, ".ytdl_write_test")
        with open(probe, "w", encoding="utf-8"):
            pass
        os.remove(probe)
    except OSError as exc:
        raise DownloaderError(
            f"Cannot write to output folder '{output_dir}': {exc}"
        ) from exc

    ffmpeg_dir = find_ffmpeg()
    merge_needed = _needs_merge(format_id, formats)
    if merge_needed and not ffmpeg_dir:
        raise DownloaderError(
            "This quality needs ffmpeg to merge separate video and audio "
            "streams, but ffmpeg was not found.\n\n"
            "Install it with `winget install Gyan.FFmpeg` (then restart the "
            "app), or place ffmpeg.exe next to this application."
        )

    if format_id == BEST_FORMAT_ID:
        fmt_selector = BEST_FORMAT_ID
    elif merge_needed:
        fmt_selector = f"{format_id}+bestaudio/best"
    else:
        fmt_selector = format_id

    final_path: dict[str, str] = {}

    def hook(d: dict) -> None:
        status = d.get("status")
        if status == "finished":
            if d.get("filename"):
                final_path["path"] = d["filename"]
            progress_callback({"status": "finished", "filename": d.get("filename")})
        elif status == "downloading":
            progress_callback(
                {
                    "status": "downloading",
                    "downloaded_bytes": d.get("downloaded_bytes") or 0,
                    "total_bytes": d.get("total_bytes")
                    or d.get("total_bytes_estimate")
                    or 0,
                    "speed": d.get("speed"),
                    "eta": d.get("eta"),
                }
            )
        elif status == "error":
            progress_callback({"status": "error"})

    opts = {
        "format": fmt_selector,
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "restrictfilenames": True,
    }
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise DownloaderError(str(exc)) from exc
    except OSError as exc:
        raise DownloaderError(f"File system error: {exc}") from exc
    except Exception as exc:
        raise DownloaderError(f"Download failed: {exc}") from exc

    if isinstance(info, dict):
        requested = info.get("requested_downloads") or []
        if requested and requested[0].get("filepath"):
            return requested[0]["filepath"]
        if info.get("_filename"):
            return info["_filename"]
    return final_path.get("path", os.path.join(output_dir, "(downloaded file)"))
