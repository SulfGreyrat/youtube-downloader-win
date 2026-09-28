"""yt-dlp wrapper: probing (title/duration/sizes per quality), download with
combined progress + cancellation, correct final file names.

No Tk imports — shared by the GUI, the queue manager and the background agent.
"""

from __future__ import annotations

import glob
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import yt_dlp

import stats

# Quality keys: "best", "audio", or "h<height>" (e.g. "h1080").
BEST = "best"
AUDIO = "audio"
BEST_FORMAT_ID = BEST  # backwards compatibility

# Prefer the highest resolution; among equals prefer H.264 + AAC so the merged
# MP4 plays everywhere (Windows player, phones, TVs).
FORMAT_SORT = ["res", "fps", "vcodec:h264", "acodec:m4a"]

# Title is cut to 180 bytes so long titles never hit the Windows MAX_PATH wall.
OUTTMPL = "%(title).180B.%(ext)s"


class DownloaderError(Exception):
    """Any user-facing failure coming out of this module."""


class Cancelled(Exception):
    """Raised inside yt-dlp hooks to abort a download."""


# ----------------------------------------------------------------- helpers
def human_size(num: Optional[float]) -> str:
    if not num:
        return "—"
    value = float(num)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if value < 1024 or unit == "ТБ":
            return f"{value:.0f} {unit}" if unit in ("Б", "КБ") else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ТБ"


def human_duration(sec: Optional[float]) -> str:
    if not sec:
        return "—"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def human_hours(sec: Optional[float]) -> str:
    """Long-form total time: '3 ч 25 мин' / '12 мин'."""
    sec = int(sec or 0)
    h, m = sec // 3600, (sec % 3600) // 60
    if h:
        return f"{h} ч {m} мин"
    if m:
        return f"{m} мин"
    return f"{sec} с"


def quality_label(quality: str) -> str:
    if quality == BEST:
        return "Лучшее"
    if quality == AUDIO:
        return "Аудио"
    if quality.startswith("h"):
        return f"{quality[1:]}p"
    return quality


def _selector(quality: str) -> str:
    if quality == AUDIO:
        return "ba[ext=m4a]/ba/b"
    if quality.startswith("h") and quality[1:].isdigit():
        h = int(quality[1:])
        return f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b"
    return "bv*+ba/b"


def _app_base() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_ffmpeg() -> Optional[str]:
    """Locate ffmpeg: next to the exe/script first, then PATH."""
    base = _app_base()
    for candidate_dir in (base, os.path.dirname(base)):
        if os.path.isfile(os.path.join(candidate_dir, "ffmpeg.exe")):
            return candidate_dir
    found = shutil.which("ffmpeg")
    return os.path.dirname(found) if found else None


def find_node() -> Optional[str]:
    """YouTube needs a JS runtime to unlock all formats (1080p+)."""
    found = shutil.which("node")
    if found:
        return found
    for cand in (r"C:\Program Files\nodejs\node.exe",
                 os.path.expandvars(r"%LOCALAPPDATA%\hermes\node\node.exe")):
        if os.path.isfile(cand):
            return cand
    return None


def base_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "format_sort": FORMAT_SORT,
        "windowsfilenames": True,
        "restrictfilenames": False,
        "socket_timeout": 30,
        "retries": 10,
        "fragment_retries": 10,
    }
    node = find_node()
    if node:
        opts["js_runtimes"] = {"node": {"path": node}}
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    return opts


def _fmt_size(fmt: dict, duration: Optional[float]) -> Optional[int]:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if not size and fmt.get("tbr") and duration:
        size = fmt["tbr"] * 1000 / 8 * duration
    return int(size) if size else None


def _thumb_of(info: dict) -> Optional[str]:
    vid = info.get("id")
    if vid and len(vid) == 11:
        return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbs = info.get("thumbnails") or []
    return thumbs[-1].get("url") if thumbs else None


# ------------------------------------------------------------------ probing
@dataclass
class QualityOption:
    quality: str          # "best" / "audio" / "h1080"
    label: str            # "1080p · 60fps · H.264"
    size: Optional[int]   # video + audio, bytes
    ext: str


@dataclass
class VideoInfo:
    url: str
    video_id: str
    title: str
    channel: str
    duration: Optional[float]
    thumbnail: Optional[str]
    options: list[QualityOption] = field(default_factory=list)
    raw: Optional[dict] = None          # processed yt-dlp info (reused for download)
    fetched_at: float = 0.0

    def size_for(self, quality: str) -> Optional[int]:
        for o in self.options:
            if o.quality == quality:
                return o.size
        if quality.startswith("h"):
            want = int(quality[1:])
            cands = [o for o in self.options if o.quality.startswith("h")
                     and int(o.quality[1:]) <= want]
            if cands:
                return max(cands, key=lambda o: int(o.quality[1:])).size
        return None


@dataclass
class PlaylistInfo:
    url: str
    title: str
    entries: list[dict]   # {url, title, duration, video_id, thumbnail, channel}


def _codec_name(vcodec: str) -> str:
    v = (vcodec or "").lower()
    if v.startswith("avc"):
        return "H.264"
    if v.startswith(("vp9", "vp09")):
        return "VP9"
    if v.startswith("av01"):
        return "AV1"
    return ""


def _selected(ydl, info: dict, quality: str) -> list[dict]:
    fmts = info.get("formats") or []
    ctx = {
        "formats": fmts,
        "has_merged_format": any(f.get("vcodec") not in (None, "none")
                                 and f.get("acodec") not in (None, "none") for f in fmts),
        "incomplete_formats": False,
    }
    try:
        chosen = next(iter(ydl.build_format_selector(_selector(quality))(ctx)), None)
    except Exception:  # noqa: BLE001
        chosen = None
    if not chosen:
        return []
    return chosen.get("requested_formats") or [chosen]


def _build_options(ydl, info: dict) -> list[QualityOption]:
    duration = info.get("duration")
    heights = sorted({f["height"] for f in info.get("formats") or []
                      if f.get("height") and f.get("vcodec") not in (None, "none")},
                     reverse=True)
    options: list[QualityOption] = []
    seen: set[tuple] = set()

    def add(quality: str, prefix: str) -> None:
        parts = _selected(ydl, info, quality)
        key = tuple(p.get("format_id") for p in parts)
        if not parts or (quality.startswith("h") and key in seen):
            return
        seen.add(key)
        size = sum(s for s in (_fmt_size(p, duration) for p in parts) if s) or None
        video = next((p for p in parts if p.get("vcodec") not in (None, "none")), None)
        bits = [prefix]
        if video:
            if quality == BEST and video.get("height"):
                bits = [f"Лучшее — {video['height']}p"]
            if video.get("fps") and video["fps"] > 30:
                bits.append(f"{int(video['fps'])}fps")
            codec = _codec_name(video.get("vcodec"))
            if codec:
                bits.append(codec)
            ext = "mp4"
        else:
            abr = parts[0].get("abr")
            if abr:
                bits.append(f"{int(abr)} kbps")
            ext = parts[0].get("ext") or "m4a"
        options.append(QualityOption(quality, " · ".join(bits), size, ext))

    add(BEST, "Лучшее")
    for h in heights:
        if h >= 144:
            add(f"h{h}", f"{h}p")
    add(AUDIO, "Только аудио")
    return options


def _video_from_info(url: str, ydl, info: dict) -> VideoInfo:
    return VideoInfo(
        url=info.get("webpage_url") or url,
        video_id=info.get("id") or "",
        title=info.get("title") or "(без названия)",
        channel=info.get("channel") or info.get("uploader") or "",
        duration=info.get("duration"),
        thumbnail=_thumb_of(info),
        options=_build_options(ydl, info),
        raw=info,
        fetched_at=time.time(),
    )


def probe(url: str, allow_playlist: bool = True) -> VideoInfo | PlaylistInfo:
    """Fetch metadata. Returns VideoInfo (with per-quality sizes) or,
    for a playlist/channel URL, PlaylistInfo with flat entries."""
    url = (url or "").strip()
    if not url:
        raise DownloaderError("Вставьте ссылку на видео.")
    opts = base_opts()
    opts.update({"skip_download": True, "extract_flat": "in_playlist"})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise DownloaderError("YouTube не вернул информацию по ссылке.")
            if info.get("_type") in ("playlist", "multi_video"):
                entries = []
                for e in info.get("entries") or []:
                    if not e:
                        continue
                    vid = e.get("id") or ""
                    eurl = e.get("url") or e.get("webpage_url") or ""
                    if not eurl.startswith("http"):
                        eurl = f"https://www.youtube.com/watch?v={vid or eurl}"
                    entries.append({
                        "url": eurl, "title": e.get("title") or "",
                        "duration": e.get("duration"), "video_id": vid,
                        "thumbnail": _thumb_of(e),
                        "channel": e.get("channel") or e.get("uploader") or "",
                    })
                if not entries:
                    raise DownloaderError("Плейлист пуст.")
                if not allow_playlist:
                    return probe(entries[0]["url"], allow_playlist=False)
                return PlaylistInfo(url=url, title=info.get("title") or "Плейлист",
                                    entries=entries)
            return _video_from_info(url, ydl, info)
    except DownloaderError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        raise DownloaderError(_clean_err(str(exc))) from exc
    except Exception as exc:  # noqa: BLE001
        raise DownloaderError(f"Не удалось получить информацию: {exc}") from exc


def _clean_err(msg: str) -> str:
    msg = msg.replace("ERROR: ", "").strip()
    if "Sign in to confirm" in msg:
        return "YouTube требует вход (проверка на бота или 18+).\n" + msg
    if "Video unavailable" in msg or "Private video" in msg:
        return "Видео недоступно (удалено или приватное)."
    return msg


# ----------------------------------------------------------------- download
def _check_dir(output_dir: str) -> None:
    if not output_dir:
        raise DownloaderError("Выберите папку для сохранения.")
    try:
        os.makedirs(output_dir, exist_ok=True)
        probe_file = os.path.join(output_dir, ".ytdl_write_test")
        with open(probe_file, "w", encoding="utf-8"):
            pass
        os.remove(probe_file)
    except OSError as exc:
        raise DownloaderError(f"Нет доступа к папке «{output_dir}»: {exc}") from exc


def _cleanup_partials(files: set[str]) -> None:
    for f in files:
        for cand in glob.glob(glob.escape(f) + "*"):
            if cand.endswith((".part", ".ytdl")) or ".part-Frag" in cand or cand == f:
                try:
                    os.remove(cand)
                except OSError:
                    pass


def download(
    url: str,
    quality: str,
    output_dir: str,
    progress_callback: Callable[[dict], None],
    cancel_event: Optional[threading.Event] = None,
    cached: Optional[VideoInfo] = None,
    source: str = "app",
) -> str:
    """Download `url` at `quality` into `output_dir`; return the final path.

    progress_callback receives dicts:
      {"status": "info", title, duration, total_bytes, video_id, channel, thumbnail}
      {"status": "downloading", downloaded_bytes, total_bytes, speed, eta}
      {"status": "merging"}
    Successful downloads are recorded in the statistics DB.
    """
    url = (url or "").strip()
    if not url:
        raise DownloaderError("Вставьте ссылку на видео.")
    _check_dir(output_dir)
    if quality not in (BEST, AUDIO) and not quality.startswith("h"):
        quality = BEST
    if quality != AUDIO and not find_ffmpeg():
        raise DownloaderError(
            "Для склейки видео и звука нужен ffmpeg, но он не найден.\n"
            "Установите: winget install Gyan.FFmpeg (и перезапустите приложение) "
            "или положите ffmpeg.exe рядом с программой.")

    cancel_event = cancel_event or threading.Event()
    touched: set[str] = set()
    per_file: dict[str, list] = {}       # filename -> [done, total]
    state = {"expected": 0, "last": 0.0}

    def hook(d: dict) -> None:
        if cancel_event.is_set():
            raise Cancelled()
        fn = d.get("filename") or d.get("tmpfilename") or "?"
        touched.add(fn)
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            per_file[fn] = [d.get("downloaded_bytes") or 0, total]
            now = time.monotonic()
            if now - state["last"] < 0.25:
                return
            state["last"] = now
            done = sum(v[0] for v in per_file.values())
            known = sum(v[1] for v in per_file.values())
            total_all = max(state["expected"], known)
            speed = d.get("speed")
            eta = (total_all - done) / speed if speed and total_all > done else d.get("eta")
            progress_callback({"status": "downloading", "downloaded_bytes": done,
                               "total_bytes": total_all, "speed": speed, "eta": eta})
        elif d.get("status") == "finished" and fn in per_file:
            per_file[fn][0] = per_file[fn][1] or per_file[fn][0]

    def pp_hook(d: dict) -> None:
        if cancel_event.is_set():
            raise Cancelled()
        if d.get("status") == "started" and "Merger" in (d.get("postprocessor") or ""):
            progress_callback({"status": "merging"})

    opts = base_opts()
    opts.update({
        "format": _selector(quality),
        "outtmpl": os.path.join(output_dir, OUTTMPL),
        "progress_hooks": [hook],
        "postprocessor_hooks": [pp_hook],
    })
    if quality != AUDIO:
        opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            if cached and cached.raw and time.time() - cached.fetched_at < 3 * 3600:
                info = cached.raw
            else:
                info = ydl.extract_info(url, download=False)
            if cancel_event.is_set():
                raise Cancelled()
            if info.get("_type") in ("playlist", "multi_video"):
                raise DownloaderError("Это плейлист — добавьте его через вкладку «Скачать».")
            parts = _selected(ydl, info, quality)
            state["expected"] = sum(_fmt_size(p, info.get("duration")) or 0 for p in parts)
            progress_callback({
                "status": "info", "title": info.get("title"),
                "duration": info.get("duration"), "total_bytes": state["expected"],
                "video_id": info.get("id"), "thumbnail": _thumb_of(info),
                "channel": info.get("channel") or info.get("uploader") or "",
            })
            result = ydl.process_ie_result(info, download=True)
    except Cancelled:
        _cleanup_partials(touched)
        raise
    except yt_dlp.utils.DownloadError as exc:
        if cancel_event.is_set():
            _cleanup_partials(touched)
            raise Cancelled() from exc
        raise DownloaderError(_clean_err(str(exc))) from exc
    except DownloaderError:
        raise
    except OSError as exc:
        raise DownloaderError(f"Ошибка файловой системы: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        if cancel_event.is_set():
            _cleanup_partials(touched)
            raise Cancelled() from exc
        raise DownloaderError(f"Ошибка загрузки: {exc}") from exc

    path = None
    if isinstance(result, dict):
        req = result.get("requested_downloads") or []
        if req and req[0].get("filepath"):
            path = req[0]["filepath"]
        path = path or result.get("filepath") or result.get("_filename")
    if not path or not os.path.isfile(path):
        raise DownloaderError("Загрузка завершилась, но итоговый файл не найден.")

    try:
        stats.record(
            url=result.get("webpage_url") or url, video_id=result.get("id") or "",
            title=result.get("title") or os.path.basename(path),
            channel=result.get("channel") or result.get("uploader") or "",
            duration=result.get("duration") or 0, size=os.path.getsize(path),
            quality=quality_label(quality), path=path, source=source,
        )
    except Exception:  # noqa: BLE001 — stats must never break a download
        pass
    return path
