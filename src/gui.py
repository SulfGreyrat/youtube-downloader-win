"""Tkinter GUI for the YouTube downloader."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from downloader import DownloaderError, FormatInfo, download, list_formats


def _default_output_dir() -> str:
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    return downloads if os.path.isdir(downloads) else os.path.expanduser("~")


def _fmt_speed(speed) -> str:
    if not speed:
        return "--"
    value = float(speed)
    for unit in ("B/s", "KB/s", "MB/s"):
        if value < 1024 or unit == "MB/s":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} MB/s"


def _fmt_eta(eta) -> str:
    if eta is None:
        return "--"
    eta = int(eta)
    return f"{eta // 60}m {eta % 60}s" if eta >= 60 else f"{eta}s"


class DownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("YouTube Downloader")
        self.geometry("720x330")
        self.minsize(640, 330)

        self.current_url: str = ""
        self.current_formats: list[FormatInfo] = []
        self.output_dir: str = _default_output_dir()
        self._queue: queue.Queue = queue.Queue()
        self._busy = False

        self._build_widgets()
        self.after(100, self._poll_queue)

    # ---------------------------------------------------------------- layout
    def _build_widgets(self) -> None:
        pad = {"padx": 8, "pady": 5}
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Video URL:").grid(row=0, column=0, sticky="w", **pad)
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(self, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=1, sticky="ew", **pad)
        self.fetch_btn = ttk.Button(self, text="Get info", command=self.on_fetch)
        self.fetch_btn.grid(row=0, column=2, sticky="ew", **pad)

        self.title_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.title_var, wraplength=650,
                  foreground="#1a4d8f").grid(row=1, column=0, columnspan=3,
                                             sticky="w", **pad)

        ttk.Label(self, text="Quality:").grid(row=2, column=0, sticky="w", **pad)
        self.format_combo = ttk.Combobox(self, state="disabled", values=[])
        self.format_combo.grid(row=2, column=1, columnspan=2, sticky="ew", **pad)

        ttk.Label(self, text="Save to:").grid(row=3, column=0, sticky="w", **pad)
        self.dir_var = tk.StringVar(value=self.output_dir)
        ttk.Entry(self, textvariable=self.dir_var, state="readonly").grid(
            row=3, column=1, sticky="ew", **pad)
        ttk.Button(self, text="Browse…", command=self.on_browse).grid(
            row=3, column=2, sticky="ew", **pad)

        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.grid(row=4, column=0, columnspan=3, sticky="ew", **pad)

        self.progress_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.progress_var).grid(
            row=5, column=0, columnspan=3, sticky="w", **pad)

        self.download_btn = ttk.Button(self, text="Download", state="disabled",
                                       command=self.on_download)
        self.download_btn.grid(row=6, column=1, sticky="e", **pad)

        self.status_var = tk.StringVar(value="Paste a YouTube URL and press "
                                             "\"Get info\".")
        ttk.Label(self, textvariable=self.status_var, wraplength=680,
                  foreground="#444").grid(row=7, column=0, columnspan=3,
                                          sticky="w", **pad)

    # --------------------------------------------------------------- helpers
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.fetch_btn.config(state="disabled" if busy else "normal")
        if busy:
            self.download_btn.config(state="disabled")
        elif self.current_formats:
            self.download_btn.config(state="normal")

    # ---------------------------------------------------------------- events
    def on_browse(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.output_dir)
        if chosen:
            self.output_dir = chosen
            self.dir_var.set(chosen)

    def on_fetch(self) -> None:
        if self._busy:
            return
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please paste a video URL first.")
            return
        self.current_url = url
        self._set_busy(True)
        self.status_var.set("Fetching available formats…")
        self.title_var.set("")
        self.format_combo.config(values=[], state="disabled")
        self.format_combo.set("")
        self.current_formats = []
        threading.Thread(target=self._fetch_worker, args=(url,),
                         daemon=True).start()

    def _fetch_worker(self, url: str) -> None:
        try:
            title, formats = list_formats(url)
            self._queue.put(("formats", (title, formats)))
        except DownloaderError as exc:
            self._queue.put(("error", str(exc)))
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            self._queue.put(("error", f"Unexpected error: {exc}"))

    def on_download(self) -> None:
        if self._busy or not self.current_formats:
            return
        idx = self.format_combo.current()
        if idx < 0:
            messagebox.showerror("Error", "Please choose a quality.")
            return
        fmt = self.current_formats[idx]
        self._set_busy(True)
        self.progress.config(value=0)
        self.progress_var.set("")
        self.status_var.set(f"Downloading: {fmt.note}")
        threading.Thread(
            target=self._download_worker,
            args=(self.current_url, fmt.format_id, self.output_dir),
            daemon=True,
        ).start()

    def _download_worker(self, url: str, format_id: str, out_dir: str) -> None:
        try:
            path = download(
                url, format_id, out_dir,
                progress_callback=lambda d: self._queue.put(("progress", d)),
                formats=self.current_formats,
            )
            self._queue.put(("done", path))
        except DownloaderError as exc:
            self._queue.put(("error", str(exc)))
        except Exception as exc:  # noqa: BLE001
            self._queue.put(("error", f"Unexpected error: {exc}"))

    # ------------------------------------------------------------ main thread
    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle(self, kind: str, payload) -> None:
        if kind == "formats":
            title, formats = payload
            self.current_formats = formats
            self.title_var.set(title)
            self.format_combo.config(values=[f.note for f in formats],
                                     state="readonly")
            self.format_combo.current(0)
            self.status_var.set(f"{len(formats)} options available. "
                                "Pick a quality and press Download.")
            self._set_busy(False)
        elif kind == "progress":
            self._handle_progress(payload)
        elif kind == "done":
            self.progress.config(value=100)
            self.progress_var.set("")
            self.status_var.set(f"Saved to: {payload}")
            self._set_busy(False)
            messagebox.showinfo("Done", f"Download complete:\n{payload}")
        elif kind == "error":
            self.progress.config(value=0)
            self.progress_var.set("")
            self.status_var.set("Error — see dialog.")
            self._set_busy(False)
            messagebox.showerror("Error", payload)

    def _handle_progress(self, d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 100) if total else 0
            self.progress.config(value=pct)
            self.progress_var.set(
                f"{pct:5.1f}%   {_fmt_speed(d.get('speed'))}   "
                f"ETA {_fmt_eta(d.get('eta'))}"
            )
        elif d.get("status") == "finished":
            self.progress.config(value=100)
            self.progress_var.set("Merging / finalizing…")
