"""CustomTkinter GUI for the YouTube downloader (dark theme, see ui-design.md)."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from downloader import DownloaderError, FormatInfo, download, list_formats

# ---------------------------------------------------------------- palette
BG = "#0b0d10"
BG_RAISED = "#111418"
INK = "#f2f1ec"
INK_DIM = "#9a9d9f"
BORDER = "#20242a"
ACCENT = "#ff4d4d"
ACCENT_HOVER = "#e34343"
ACCENT_INK = "#0b0d10"
SUCCESS = "#28c840"
ERROR = "#ff5f57"
DISABLED_FG = "#3a2626"
DISABLED_INK = "#6b6f71"
MENU_DISABLED_INK = "#5c5f61"
OUTLINE_HOVER = "#161a1f"

FIELD_H = 36
RADIUS = 8

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


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


class DownloaderApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=BG)
        self.title("YouTube Downloader")
        self.geometry("760x460")
        self.resizable(False, False)

        self.current_url: str = ""
        self.current_formats: list[FormatInfo] = []
        self.output_dir: str = _default_output_dir()
        self._queue: queue.Queue = queue.Queue()
        self._busy = False

        self.font_brand = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        self.font_label = ctk.CTkFont(family="Segoe UI", size=12)
        self.font_field = ctk.CTkFont(family="Segoe UI", size=13)
        self.font_bold = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        self.font_mono = ctk.CTkFont(family="Consolas", size=12)

        self._build_widgets()
        self.after(100, self._poll_queue)

    # ---------------------------------------------------------------- layout
    def _section_label(self, master, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(master, text=text, font=self.font_label,
                            text_color=INK_DIM, anchor="w")

    def _build_widgets(self) -> None:
        root = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        root.pack(fill="both", expand=True, padx=24, pady=24)

        # -- brand row -----------------------------------------------------
        brand = ctk.CTkFrame(root, fg_color="transparent")
        brand.pack(fill="x")
        ctk.CTkLabel(brand, text="\u25cf", font=self.font_brand,
                     text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(brand, text="YT Downloader", font=self.font_brand,
                     text_color=INK).pack(side="left", padx=(8, 0))
        ctk.CTkFrame(root, fg_color=BORDER, height=1,
                     corner_radius=0).pack(fill="x", pady=(10, 14))

        # -- URL block -----------------------------------------------------
        self._section_label(root, "VIDEO URL").pack(fill="x", pady=(0, 6))
        url_row = ctk.CTkFrame(root, fg_color="transparent")
        url_row.pack(fill="x")
        self.url_var = tk.StringVar()
        self.url_entry = ctk.CTkEntry(
            url_row, textvariable=self.url_var, height=FIELD_H,
            corner_radius=RADIUS, fg_color=BG_RAISED, border_color=BORDER,
            border_width=1, text_color=INK, font=self.font_field,
            placeholder_text="Paste a YouTube video URL\u2026",
            placeholder_text_color=INK_DIM,
        )
        self.url_entry.pack(side="left", fill="x", expand=True)
        self.url_entry.bind("<FocusIn>",
                            lambda _e: self.url_entry.configure(border_color=ACCENT))
        self.url_entry.bind("<FocusOut>",
                            lambda _e: self.url_entry.configure(border_color=BORDER))
        self.fetch_btn = ctk.CTkButton(
            url_row, text="Get info", command=self.on_fetch, width=110,
            height=FIELD_H, corner_radius=RADIUS, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, text_color=ACCENT_INK, font=self.font_bold,
            text_color_disabled=DISABLED_INK,
        )
        self.fetch_btn.pack(side="left", padx=(10, 0))

        # -- video title ---------------------------------------------------
        self.title_var = tk.StringVar(value="")
        ctk.CTkLabel(root, textvariable=self.title_var, font=self.font_bold,
                     text_color=INK, wraplength=680, justify="left",
                     anchor="w").pack(fill="x", pady=(16, 0))

        # -- quality block --------------------------------------------------
        self._section_label(root, "QUALITY").pack(fill="x", pady=(16, 6))
        self.format_var = tk.StringVar(value="\u2014")
        self.format_combo = ctk.CTkOptionMenu(
            root, variable=self.format_var, values=["\u2014"], state="disabled",
            height=FIELD_H, corner_radius=RADIUS, fg_color=BG_RAISED,
            button_color=BG_RAISED, button_hover_color="#1a1e24",
            text_color=INK, text_color_disabled=MENU_DISABLED_INK,
            dropdown_fg_color=BG_RAISED, dropdown_text_color=INK,
            dropdown_hover_color=BORDER, font=self.font_field,
            dropdown_font=self.font_field, anchor="w",
        )
        self.format_combo.pack(fill="x")

        # -- save-to block ---------------------------------------------------
        self._section_label(root, "SAVE TO").pack(fill="x", pady=(16, 6))
        dir_row = ctk.CTkFrame(root, fg_color="transparent")
        dir_row.pack(fill="x")
        self.dir_var = tk.StringVar(value=self.output_dir)
        ctk.CTkEntry(
            dir_row, textvariable=self.dir_var, state="readonly", height=FIELD_H,
            corner_radius=RADIUS, fg_color=BG_RAISED, border_color=BORDER,
            border_width=1, text_color=INK, font=self.font_field,
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            dir_row, text="Browse\u2026", command=self.on_browse, width=110,
            height=FIELD_H, corner_radius=RADIUS, fg_color="transparent",
            border_width=1, border_color=BORDER, text_color=INK,
            hover_color=OUTLINE_HOVER, font=self.font_field,
        ).pack(side="left", padx=(10, 0))

        # -- progress block ---------------------------------------------------
        self.progress = ctk.CTkProgressBar(
            root, height=6, corner_radius=4, mode="determinate",
            fg_color=BORDER, progress_color=ACCENT,
        )
        self.progress.set(0)
        self.progress.pack(fill="x", pady=(20, 8))

        prog_row = ctk.CTkFrame(root, fg_color="transparent")
        prog_row.pack(fill="x")
        self.progress_var = tk.StringVar(value="")
        self.eta_var = tk.StringVar(value="")
        ctk.CTkLabel(prog_row, textvariable=self.progress_var, font=self.font_mono,
                     text_color=INK_DIM, anchor="w").pack(side="left")
        ctk.CTkLabel(prog_row, textvariable=self.eta_var, font=self.font_mono,
                     text_color=INK_DIM, anchor="e").pack(side="right")

        # -- status + download ------------------------------------------------
        bottom = ctk.CTkFrame(root, fg_color="transparent")
        bottom.pack(fill="x", side="bottom")
        self.download_btn = ctk.CTkButton(
            bottom, text="Download", command=self.on_download, state="disabled",
            width=140, height=FIELD_H, corner_radius=RADIUS, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, text_color=ACCENT_INK, font=self.font_bold,
            text_color_disabled=DISABLED_INK,
        )
        self.download_btn.pack(side="right", padx=(10, 0))
        self.status_var = tk.StringVar(value="Paste a YouTube URL and press "
                                             "\"Get info\".")
        self.status_label = ctk.CTkLabel(
            bottom, textvariable=self.status_var, font=self.font_label,
            text_color=INK_DIM, wraplength=520, justify="left", anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        self._sync_button_styles()

    # --------------------------------------------------------------- helpers
    def _status(self, text: str, color: str = INK_DIM) -> None:
        self.status_var.set(text)
        self.status_label.configure(text_color=color)

    def _sync_button_styles(self) -> None:
        """CTk's disabled dimming is inconsistent — set the fill explicitly."""
        for btn in (self.fetch_btn, self.download_btn):
            disabled = btn.cget("state") == "disabled"
            btn.configure(fg_color=DISABLED_FG if disabled else ACCENT)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.fetch_btn.configure(state="disabled" if busy else "normal")
        if busy:
            self.download_btn.configure(state="disabled")
        elif self.current_formats:
            self.download_btn.configure(state="normal")
        self._sync_button_styles()

    def _selected_index(self) -> int:
        try:
            return self.format_combo.cget("values").index(self.format_var.get())
        except ValueError:
            return -1

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
        self._status("Fetching available formats\u2026")
        self.title_var.set("")
        self.format_combo.configure(values=["\u2014"], state="disabled")
        self.format_var.set("\u2014")
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
        idx = self._selected_index()
        if idx < 0:
            messagebox.showerror("Error", "Please choose a quality.")
            return
        fmt = self.current_formats[idx]
        self._set_busy(True)
        self.progress.set(0)
        self.progress_var.set("")
        self.eta_var.set("")
        self._status(f"Downloading: {fmt.note}")
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
            notes = [f.note for f in formats] or ["\u2014"]
            self.format_combo.configure(values=notes, state="normal")
            self.format_var.set(notes[0])
            self._status(f"{len(formats)} options available. "
                         "Pick a quality and press Download.")
            self._set_busy(False)
        elif kind == "progress":
            self._handle_progress(payload)
        elif kind == "done":
            self.progress.set(1)
            self.progress_var.set("")
            self.eta_var.set("")
            self._status(f"Saved to: {payload}", SUCCESS)
            self._set_busy(False)
            messagebox.showinfo("Done", f"Download complete:\n{payload}")
        elif kind == "error":
            self.progress.set(0)
            self.progress_var.set("")
            self.eta_var.set("")
            self._status("Error — see dialog.", ERROR)
            self._set_busy(False)
            messagebox.showerror("Error", payload)

    def _handle_progress(self, d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 100) if total else 0
            self.progress.set(pct / 100)
            self.progress_var.set(f"{pct:5.1f}%   {_fmt_speed(d.get('speed'))}")
            self.eta_var.set(f"ETA {_fmt_eta(d.get('eta'))}")
        elif d.get("status") == "finished":
            self.progress.set(1)
            self.progress_var.set("Merging / finalizing\u2026")
            self.eta_var.set("")
