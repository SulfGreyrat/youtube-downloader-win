"""Download queue: persistent, N parallel workers, cancel / retry / reorder.

UI-agnostic. The GUI subscribes with `listener(item_id)` (called from worker
threads — the GUI must marshal to its own thread) and reads `items()`.
State survives restarts in %APPDATA%/YouTubeDownloader/queue.json;
items that were mid-download are resumed (yt-dlp continues .part files).
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

import config
import downloader as dl

QUEUE_PATH = os.path.join(config.CONFIG_DIR, "queue.json")

QUEUED, PROBING, DOWNLOADING, MERGING = "queued", "probing", "downloading", "merging"
DONE, ERROR, CANCELLED = "done", "error", "cancelled"
ACTIVE = (PROBING, DOWNLOADING, MERGING)
FINISHED = (DONE, ERROR, CANCELLED)

STATUS_RU = {
    QUEUED: "в очереди", PROBING: "получение данных", DOWNLOADING: "скачивается",
    MERGING: "склейка", DONE: "готово", ERROR: "ошибка", CANCELLED: "отменено",
}


@dataclass
class Item:
    url: str
    quality: str
    output_dir: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    title: str = ""
    channel: str = ""
    video_id: str = ""
    thumbnail: str = ""
    duration: float = 0
    size: int = 0                 # expected bytes (video + audio)
    status: str = QUEUED
    downloaded: int = 0
    speed: float = 0
    eta: float = 0
    path: str = ""
    error: str = ""
    added: float = field(default_factory=time.time)
    started: float = 0
    finished: float = 0

    @property
    def progress(self) -> float:
        if self.status == DONE:
            return 1.0
        return min(self.downloaded / self.size, 1.0) if self.size else 0.0


class QueueManager:
    def __init__(self, listener: Optional[Callable[[str], None]] = None,
                 path: str = QUEUE_PATH, autostart: bool = True):
        self._path = path
        self._lock = threading.RLock()
        self._save_lock = threading.Lock()
        self._items: list[Item] = []
        self._cancel: dict[str, threading.Event] = {}
        self._cache: dict[str, dl.VideoInfo] = {}
        self._listener = listener or (lambda _id: None)
        self._wake = threading.Event()
        self._stop = False
        self.paused = False
        self.concurrency = max(1, int(config.get("concurrency") or 2))
        self._load()
        self._threads: list[threading.Thread] = []
        if autostart:
            self.start()

    # ---------------------------------------------------------- persistence
    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            return
        known = set(Item.__dataclass_fields__)
        for d in raw.get("items", []):
            try:
                it = Item(**{k: v for k, v in d.items() if k in known})
            except TypeError:
                continue
            if it.status in ACTIVE:
                it.status = QUEUED
                it.speed = it.eta = 0
            self._items.append(it)
        self.paused = bool(raw.get("paused", False))

    def _save(self) -> None:
        with self._lock:
            data = {"paused": self.paused, "items": [asdict(i) for i in self._items]}
        with self._save_lock:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = f"{self._path}.{threading.get_ident()}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
            for attempt in range(10):   # AV / indexer may hold the file briefly
                try:
                    os.replace(tmp, self._path)
                    return
                except PermissionError:
                    time.sleep(0.05 * (attempt + 1))
            try:
                os.remove(tmp)
            except OSError:
                pass

    # --------------------------------------------------------------- access
    def items(self) -> list[Item]:
        with self._lock:
            return list(self._items)

    def get(self, item_id: str) -> Optional[Item]:
        with self._lock:
            return next((i for i in self._items if i.id == item_id), None)

    def summary(self) -> dict:
        """Totals for the pending part of the queue (queued + active)."""
        with self._lock:
            pending = [i for i in self._items if i.status not in FINISHED]
            left = sum(max(i.size - i.downloaded, 0) for i in pending)
            speed = sum(i.speed or 0 for i in pending if i.status == DOWNLOADING)
            return {
                "pending": len(pending),
                "active": sum(1 for i in pending if i.status in ACTIVE),
                "bytes": sum(i.size for i in pending),
                "bytes_left": left,
                "seconds": sum(i.duration or 0 for i in pending),
                "unknown": sum(1 for i in pending if not i.size),
                "speed": speed,
                "eta": left / speed if speed else 0,
                "done": sum(1 for i in self._items if i.status == DONE),
                "failed": sum(1 for i in self._items if i.status == ERROR),
            }

    # -------------------------------------------------------------- actions
    def add(self, url: str, quality: str, output_dir: str,
            info: Optional[dl.VideoInfo] = None, meta: Optional[dict] = None) -> Item:
        it = Item(url=url, quality=quality, output_dir=output_dir)
        if info:
            it.title, it.channel, it.video_id = info.title, info.channel, info.video_id
            it.thumbnail, it.duration = info.thumbnail or "", info.duration or 0
            it.size = info.size_for(quality) or 0
            self._cache[it.id] = info
        elif meta:
            it.title = meta.get("title") or ""
            it.channel = meta.get("channel") or ""
            it.video_id = meta.get("video_id") or ""
            it.thumbnail = meta.get("thumbnail") or ""
            it.duration = meta.get("duration") or 0
        with self._lock:
            self._items.append(it)
        self._save()
        self._emit(it.id)
        self._wake.set()
        return it

    def cancel(self, item_id: str) -> None:
        with self._lock:
            it = self.get(item_id)
            if not it or it.status in FINISHED:
                return
            ev = self._cancel.get(item_id)
            if ev:
                ev.set()          # worker will flip status to CANCELLED
            else:
                it.status = CANCELLED
                it.finished = time.time()
        self._save()
        self._emit(item_id)

    def retry(self, item_id: str) -> None:
        with self._lock:
            it = self.get(item_id)
            if not it or it.status not in (ERROR, CANCELLED):
                return
            it.status, it.error, it.downloaded, it.speed, it.eta = QUEUED, "", 0, 0, 0
        self._save()
        self._emit(item_id)
        self._wake.set()

    def remove(self, item_id: str) -> None:
        self.cancel(item_id)
        with self._lock:
            self._items = [i for i in self._items if i.id != item_id]
            self._cache.pop(item_id, None)
        self._save()
        self._emit(item_id)

    def clear_finished(self) -> None:
        with self._lock:
            self._items = [i for i in self._items if i.status not in (DONE, CANCELLED)]
        self._save()
        self._emit("*")

    def retry_failed(self) -> None:
        for it in self.items():
            if it.status == ERROR:
                self.retry(it.id)

    def move(self, item_id: str, delta: int) -> None:
        with self._lock:
            idx = next((n for n, i in enumerate(self._items) if i.id == item_id), None)
            if idx is None:
                return
            new = max(0, min(len(self._items) - 1, idx + delta))
            self._items.insert(new, self._items.pop(idx))
        self._save()
        self._emit("*")

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self._save()
        self._wake.set()
        self._emit("*")

    def set_concurrency(self, n: int) -> None:
        self.concurrency = max(1, min(4, int(n)))
        config.save(concurrency=self.concurrency)
        self._ensure_workers()
        self._wake.set()

    def set_quality(self, item_id: str, quality: str) -> None:
        with self._lock:
            it = self.get(item_id)
            if not it or it.status != QUEUED:
                return
            it.quality = quality
            info = self._cache.get(item_id)
            it.size = (info.size_for(quality) if info else 0) or 0
        self._save()
        self._emit(item_id)
        self._wake.set()

    # -------------------------------------------------------------- workers
    def start(self) -> None:
        self._ensure_workers()
        t = threading.Thread(target=self._meta_loop, daemon=True, name="queue-meta")
        t.start()

    def shutdown(self) -> None:
        self._stop = True
        for ev in list(self._cancel.values()):
            ev.set()
        self._wake.set()
        # cancelled-by-shutdown items must resume next launch, not stay cancelled
        with self._lock:
            for it in self._items:
                if it.status in ACTIVE or (it.id in self._cancel):
                    it.status = QUEUED
        self._save()

    def _ensure_workers(self) -> None:
        self._threads = [t for t in self._threads if t.is_alive()]
        while len(self._threads) < 4:
            t = threading.Thread(target=self._worker, args=(len(self._threads),),
                                 daemon=True, name=f"queue-worker-{len(self._threads)}")
            t.start()
            self._threads.append(t)

    def _emit(self, item_id: str) -> None:
        try:
            self._listener(item_id)
        except Exception:  # noqa: BLE001
            pass

    def _claim(self, slot: int) -> Optional[Item]:
        with self._lock:
            if self._stop or self.paused or slot >= self.concurrency:
                return None
            active = sum(1 for i in self._items if i.status in ACTIVE)
            if active >= self.concurrency:
                return None
            it = next((i for i in self._items if i.status == QUEUED), None)
            if it:
                it.status = PROBING if not it.size else DOWNLOADING
                it.started = time.time()
                it.error = ""
                self._cancel[it.id] = threading.Event()
            return it

    def _worker(self, slot: int) -> None:
        while not self._stop:
            it = self._claim(slot)
            if not it:
                self._wake.wait(1.0)
                self._wake.clear()
                continue
            try:
                self._save()
                self._emit(it.id)
                self._run(it)
            except Exception as exc:  # noqa: BLE001 — a worker must never die
                with self._lock:
                    if it.status in ACTIVE:
                        it.status, it.error = ERROR, f"Внутренняя ошибка: {exc}"
                    self._cancel.pop(it.id, None)
                self._emit(it.id)
            self._wake.set()

    def _run(self, it: Item) -> None:
        ev = self._cancel[it.id]
        last_emit = [0.0]

        def cb(d: dict) -> None:
            st = d.get("status")
            with self._lock:
                if st == "info":
                    it.title = d.get("title") or it.title
                    it.duration = d.get("duration") or it.duration
                    it.size = d.get("total_bytes") or it.size
                    it.video_id = d.get("video_id") or it.video_id
                    it.thumbnail = d.get("thumbnail") or it.thumbnail
                    it.channel = d.get("channel") or it.channel
                    it.status = DOWNLOADING
                elif st == "downloading":
                    it.status = DOWNLOADING
                    it.downloaded = d.get("downloaded_bytes") or 0
                    total = d.get("total_bytes") or 0
                    if total > it.size:
                        it.size = total
                    it.speed = d.get("speed") or 0
                    it.eta = d.get("eta") or 0
                elif st == "merging":
                    it.status = MERGING
                    it.speed = it.eta = 0
            now = time.monotonic()
            if st != "downloading" or now - last_emit[0] > 0.3:
                last_emit[0] = now
                self._emit(it.id)

        try:
            path = dl.download(it.url, it.quality, it.output_dir, cb, cancel_event=ev,
                               cached=self._cache.get(it.id), source="app")
            with self._lock:
                it.status, it.path = DONE, path
                try:
                    it.size = os.path.getsize(path)
                except OSError:
                    pass
                it.downloaded = it.size
        except dl.Cancelled:
            with self._lock:
                it.status = QUEUED if self._stop else CANCELLED
        except dl.DownloaderError as exc:
            with self._lock:
                it.status = QUEUED if self._stop else ERROR
                it.error = str(exc)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                it.status, it.error = ERROR, f"Непредвиденная ошибка: {exc}"
        finally:
            with self._lock:
                it.speed = it.eta = 0
                if it.status in FINISHED:
                    it.finished = time.time()
                self._cancel.pop(it.id, None)
                self._cache.pop(it.id, None)
            if not self._stop:
                self._save()
            self._emit(it.id)

    def _meta_loop(self) -> None:
        """Fill in title / duration / size for queued items added bare
        (multi-paste, playlist, restored queue) so totals are known upfront."""
        failed: set[str] = set()
        while not self._stop:
            with self._lock:
                it = next((i for i in self._items if i.status == QUEUED and not i.size
                           and i.id not in failed and i.id not in self._cache), None)
            if not it:
                time.sleep(1.5)
                continue
            try:
                info = dl.probe(it.url, allow_playlist=False)
            except Exception:  # noqa: BLE001
                failed.add(it.id)
                continue
            with self._lock:
                if it.status != QUEUED:
                    continue
                self._cache[it.id] = info
                it.title = it.title or info.title
                it.channel, it.video_id = info.channel, info.video_id
                it.thumbnail = info.thumbnail or it.thumbnail
                it.duration = info.duration or it.duration
                it.size = info.size_for(it.quality) or 0
            self._save()
            self._emit(it.id)
