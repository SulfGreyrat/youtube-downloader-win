"""Background HTTP agent so the Chrome extension can trigger downloads.

Runs silently (no console window when built with server.spec / run via
pythonw), listens on 127.0.0.1 only, and exposes a tiny JSON API the
extension's background script calls:

  GET  /ping                       -> {"ok": true}
  GET  /settings                   -> {"output_dir": "..."}
  POST /settings {"output_dir":..} -> {"output_dir": "..."}
  POST /download {"url": "..."}    -> {"id": "...", "status": "started"}
  GET  /status/<id>                -> {"status": ..., "pct": ..., "title": ...}

Downloads always use the synthetic "best" format (video+audio auto-merged),
matching the extension's one-click behaviour. Progress can be polled by id
if a future UI wants it; the extension itself only needs start + eventual
done/error, surfaced via the browser's own download shelf notifications are
not used here (writes to disk directly via yt-dlp, not via chrome.downloads).
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as appconfig  # noqa: E402
from downloader import Cancelled, DownloaderError, download  # noqa: E402

HOST = "127.0.0.1"
PORT = 8756

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
# one download at a time from the extension, so parallel clicks don't
# saturate the link; the rest wait with status "queued"
_slot = threading.Semaphore(1)


def _set_job(job_id: str, **fields) -> None:
    with _jobs_lock:
        _jobs.setdefault(job_id, {}).update(fields)


def _run_download(job_id: str, url: str) -> None:
    out_dir = appconfig.get_output_dir()
    quality = appconfig.get("quality") or "best"
    _slot.acquire()
    _set_job(job_id, status="downloading", pct=0, error=None)

    def on_progress(d: dict) -> None:
        st = d.get("status")
        if st == "info":
            _set_job(job_id, title=d.get("title"), duration=d.get("duration"),
                     total_bytes=d.get("total_bytes"))
        elif st == "downloading":
            total = d.get("total_bytes") or 0
            done = d.get("downloaded_bytes") or 0
            pct = round((done / total * 100), 1) if total else None
            _set_job(job_id, status="downloading", pct=pct, downloaded_bytes=done,
                     total_bytes=total, speed=d.get("speed"))
        elif st == "merging":
            _set_job(job_id, status="merging")

    try:
        path = download(url, quality, out_dir, progress_callback=on_progress,
                        source="extension")
        _set_job(job_id, status="done", path=path, pct=100)
    except Cancelled:
        _set_job(job_id, status="error", error="Отменено")
    except DownloaderError as exc:
        _set_job(job_id, status="error", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        _set_job(job_id, status="error", error=f"Unexpected error: {exc}")
    finally:
        _slot.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "YTDLAgent/1.0"

    def log_message(self, fmt, *args) -> None:  # noqa: A003 - silence stdout
        pass

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # Chrome extension background scripts are cross-origin to localhost;
        # allow it explicitly instead of a wide-open '*'.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            return {}

    def do_OPTIONS(self) -> None:  # CORS preflight
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/ping":
            self._send_json({"ok": True})
        elif self.path == "/settings":
            self._send_json({"output_dir": appconfig.get_output_dir()})
        elif self.path.startswith("/status/"):
            job_id = self.path.split("/status/", 1)[1]
            with _jobs_lock:
                job = _jobs.get(job_id)
            if job is None:
                self._send_json({"error": "unknown job id"}, status=404)
            else:
                self._send_json(job)
        else:
            self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        if self.path == "/download":
            data = self._read_json()
            url = (data.get("url") or "").strip()
            if not url:
                self._send_json({"error": "url is required"}, status=400)
                return
            job_id = uuid.uuid4().hex[:12]
            _set_job(job_id, status="queued", pct=0, url=url)
            threading.Thread(target=_run_download, args=(job_id, url), daemon=True).start()
            self._send_json({"id": job_id, "status": "started"})
        elif self.path == "/settings":
            data = self._read_json()
            out_dir = (data.get("output_dir") or "").strip()
            if not out_dir:
                self._send_json({"error": "output_dir is required"}, status=400)
                return
            appconfig.set_output_dir(out_dir)
            self._send_json({"output_dir": out_dir})
        else:
            self._send_json({"error": "not found"}, status=404)


def main() -> None:
    # Single-instance guard: if the port is already taken, another copy of
    # the agent (e.g. from a previous login) is already serving requests.
    try:
        httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        return
    httpd.serve_forever()


if __name__ == "__main__":
    main()
