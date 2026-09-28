"""CustomTkinter GUI v2: tabs Скачать / Очередь / Статистика."""

from __future__ import annotations

import ctypes
import datetime as dt
import hashlib
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
from PIL import Image

import config as appconfig
import downloader as dl
import queue_manager as qm
import stats

# ---------------------------------------------------------------- palette
BG = "#0b0d10"
BG_RAISED = "#111418"
BG_RAISED_2 = "#161a1f"
INK = "#f2f1ec"
INK_DIM = "#9a9d9f"
INK_FAINT = "#5c5f61"
BORDER = "#20242a"
ACCENT = "#ff4d4d"
ACCENT_HOVER = "#e34343"
ACCENT_INK = "#0b0d10"
SUCCESS = "#28c840"
ERROR = "#ff5f57"
WARNING = "#f5a623"
QUEUED_C = "#6b7280"
BLUE = "#4d9dff"

STATUS_COLOR = {
    qm.QUEUED: QUEUED_C, qm.PROBING: WARNING, qm.DOWNLOADING: WARNING,
    qm.MERGING: BLUE, qm.DONE: SUCCESS, qm.ERROR: ERROR, qm.CANCELLED: INK_DIM,
}

FIELD_H = 36
RADIUS = 8
THUMB_W, THUMB_H = 128, 72
URL_RE = re.compile(r"https?://[^\s<>\"']+")
YT_RE = re.compile(r"(youtube\.com|youtu\.be)", re.I)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


def resource_path(*parts: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)


def open_path(path: str) -> None:
    if path and os.path.exists(path):
        os.startfile(path)  # noqa: S606


def reveal(path: str) -> None:
    if path and os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])  # noqa: S603,S607
    elif path and os.path.isdir(os.path.dirname(path)):
        os.startfile(os.path.dirname(path))  # noqa: S606


def fmt_speed(speed) -> str:
    return f"{dl.human_size(speed)}/с" if speed else ""


def fmt_eta(eta) -> str:
    if not eta:
        return ""
    eta = int(eta)
    if eta >= 3600:
        return f"{eta // 3600} ч {eta % 3600 // 60} мин"
    return f"{eta // 60}:{eta % 60:02d}" if eta >= 60 else f"{eta} с"


def plural(n: int, one: str, few: str, many: str) -> str:
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


# ------------------------------------------------------------- thumbnails
class Thumbs:
    """Download + cache video thumbnails off the UI thread."""

    def __init__(self, root: tk.Misc):
        self.root = root
        self.dir = os.path.join(appconfig.CONFIG_DIR, "thumbs")
        os.makedirs(self.dir, exist_ok=True)
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.images: dict[str, ctk.CTkImage] = {}
        self.pending: dict[str, list] = {}
        self.results: queue.Queue = queue.Queue()

    def request(self, url: str, callback, size=(THUMB_W, THUMB_H)) -> None:
        if not url:
            return
        key = f"{url}|{size}"
        if key in self.images:
            callback(self.images[key])
            return
        if key in self.pending:
            self.pending[key].append(callback)
            return
        self.pending[key] = [callback]
        self.pool.submit(self._load, url, key, size)

    def _load(self, url: str, key: str, size) -> None:
        path = os.path.join(self.dir, hashlib.md5(url.encode()).hexdigest() + ".jpg")
        try:
            if not os.path.isfile(path):
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
                    data = r.read()
                with open(path, "wb") as fh:
                    fh.write(data)
            img = Image.open(path).convert("RGB")
            # cover-crop to 16:9
            w, h = img.size
            target = size[0] / size[1]
            if w / h > target:
                nw = int(h * target)
                img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
            else:
                nh = int(w / target)
                img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
            img = img.resize((size[0] * 2, size[1] * 2), Image.LANCZOS)
            self.results.put((key, img, size))
        except Exception:  # noqa: BLE001
            self.results.put((key, None, size))

    def pump(self) -> None:
        """Call from the Tk thread."""
        while True:
            try:
                key, img, size = self.results.get_nowait()
            except queue.Empty:
                return
            cbs = self.pending.pop(key, [])
            if img is None:
                continue
            cimg = ctk.CTkImage(light_image=img, dark_image=img, size=size)
            self.images[key] = cimg
            for cb in cbs:
                try:
                    cb(cimg)
                except tk.TclError:
                    pass


# ============================================================== main window
class DownloaderApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=BG)
        self.title("YT Downloader")
        self.geometry("980x680")
        self.minsize(820, 540)
        self._set_icon()

        self.f_brand = ctk.CTkFont(family="Segoe UI", size=16, weight="bold")
        self.f_h1 = ctk.CTkFont(family="Segoe UI", size=18, weight="bold")
        self.f_label = ctk.CTkFont(family="Segoe UI", size=12)
        self.f_small = ctk.CTkFont(family="Segoe UI", size=11)
        self.f_field = ctk.CTkFont(family="Segoe UI", size=13)
        self.f_bold = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        self.f_mono = ctk.CTkFont(family="Consolas", size=12)
        self.f_metric = ctk.CTkFont(family="Segoe UI", size=26, weight="bold")

        self._events: queue.Queue = queue.Queue()
        self._dirty: set[str] = set()
        self._dirty_lock = threading.Lock()
        self.thumbs = Thumbs(self)
        self.qm = qm.QueueManager(listener=self._on_queue_event)

        self._build_header()
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.pack(fill="both", expand=True, padx=20, pady=(8, 0))
        self._build_statusbar()
        self.current_tab = "download"
        self._announced: set[str] = {i.id for i in self.qm.items() if i.status in qm.FINISHED}

        self.tabs = {
            "download": DownloadTab(self.content, self),
            "queue": QueueTab(self.content, self),
            "stats": StatsTab(self.content, self),
        }
        self.show_tab("download")

        self._install_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<FocusIn>", self._on_focus, add=True)
        self._last_clip = ""
        self.after(100, self._poll)
        self.after(400, self._refresh_counts)

    # ----------------------------------------------------------- chrome
    def _set_icon(self) -> None:
        ico = resource_path("assets", "icon.ico")
        if os.path.isfile(ico):
            try:
                self.iconbitmap(ico)
                # CTk resets the icon ~200ms after start; re-apply
                self.after(250, lambda: self.iconbitmap(ico))
            except tk.TclError:
                pass

    def _build_header(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=BG, corner_radius=0, height=56)
        bar.pack(fill="x", padx=20, pady=(14, 0))
        logo_path = resource_path("assets", "icon.png")
        if os.path.isfile(logo_path):
            img = Image.open(logo_path)
            self._logo = ctk.CTkImage(light_image=img, dark_image=img, size=(26, 26))
            ctk.CTkLabel(bar, text="", image=self._logo).pack(side="left")
        ctk.CTkLabel(bar, text="YT Downloader", font=self.f_brand,
                     text_color=INK).pack(side="left", padx=(10, 0))

        self.tab_buttons: dict[str, ctk.CTkButton] = {}
        tabs = ctk.CTkFrame(bar, fg_color=BG_RAISED, corner_radius=10)
        tabs.pack(side="right")
        for key, text in (("download", "Скачать"), ("queue", "Очередь"),
                          ("stats", "Статистика")):
            b = ctk.CTkButton(tabs, text=text, width=120, height=32, corner_radius=8,
                              font=self.f_field, fg_color="transparent",
                              hover_color=BG_RAISED_2, text_color=INK_DIM,
                              command=lambda k=key: self.show_tab(k))
            b.pack(side="left", padx=3, pady=3)
            self.tab_buttons[key] = b
        ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).pack(
            fill="x", padx=20, pady=(12, 0))

    def _build_statusbar(self) -> None:
        sb = ctk.CTkFrame(self, fg_color=BG_RAISED, corner_radius=0, height=30)
        sb.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="Готов к работе")
        self.status_lbl = ctk.CTkLabel(sb, textvariable=self.status_var, font=self.f_small,
                                       text_color=INK_DIM, anchor="w")
        self.status_lbl.pack(side="left", padx=14, pady=4)
        self.status_right = tk.StringVar(value="")
        ctk.CTkLabel(sb, textvariable=self.status_right, font=self.f_small,
                     text_color=INK_DIM, anchor="e").pack(side="right", padx=14)

    def status(self, text: str, color: str = INK_DIM) -> None:
        self.status_var.set(text)
        self.status_lbl.configure(text_color=color)

    def show_tab(self, key: str) -> None:
        self.current_tab = key
        for k, tab in self.tabs.items():
            if k == key:
                tab.pack(fill="both", expand=True)
                tab.on_show()
            else:
                tab.pack_forget()
        for k, b in self.tab_buttons.items():
            active = k == key
            b.configure(fg_color=ACCENT if active else "transparent",
                        text_color=ACCENT_INK if active else INK_DIM,
                        hover_color=ACCENT_HOVER if active else BG_RAISED_2,
                        font=self.f_bold if active else self.f_field)
        self.current_tab = key

    # --------------------------------------------------------- shortcuts
    _VK_V = 86

    def _install_shortcuts(self) -> None:
        def on_ctrl(event):
            # Ctrl+V on any keyboard layout (keysym is Cyrillic under RU layout)
            if event.keycode == self._VK_V:
                w = self.focus_get()
                if isinstance(w, (tk.Entry, tk.Text)) and w is not self.tabs["download"].url_text._textbox:
                    try:
                        w.insert("insert", self.clipboard_get())
                    except tk.TclError:
                        pass
                    return "break"
                self.show_tab("download")
                self.tabs["download"].paste(append=True)
                return "break"
            return None
        self.bind_all("<Control-KeyPress>", on_ctrl, add=True)

    def _on_focus(self, _e=None) -> None:
        """Offer the clipboard link automatically when returning to the app."""
        try:
            clip = self.clipboard_get().strip()
        except tk.TclError:
            return
        if clip != self._last_clip and YT_RE.search(clip) and URL_RE.search(clip):
            self._last_clip = clip
            tab = self.tabs["download"]
            if not tab.get_text().strip():
                tab.set_text(clip)
                self.status("Ссылка из буфера обмена подставлена — нажмите «Получить инфо»")

    # ------------------------------------------------------------ events
    def _on_queue_event(self, item_id: str) -> None:   # worker threads
        with self._dirty_lock:
            self._dirty.add(item_id)

    def post(self, kind: str, payload=None) -> None:   # any thread
        self._events.put((kind, payload))

    def _poll(self) -> None:
        with self._dirty_lock:
            dirty, self._dirty = self._dirty, set()
        if dirty:
            self.tabs["queue"].update_items(dirty)
            self._refresh_counts()
            for iid in dirty:
                it = self.qm.get(iid)
                if it and it.status == qm.DONE and iid not in self._announced:
                    self._announced.add(iid)
                    self.status(f"Готово: {it.title}", SUCCESS)
                    self.tabs["stats"].mark_stale()
                elif it and it.status == qm.ERROR and iid not in self._announced:
                    self._announced.add(iid)
                    self.status(f"Ошибка: {it.title or it.url} — {it.error[:120]}", ERROR)
        while True:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                break
            for tab in self.tabs.values():
                tab.handle(kind, payload)
        self.thumbs.pump()
        self.after(150, self._poll)

    def _refresh_counts(self) -> None:
        s = self.qm.summary()
        n = s["pending"]
        self.tab_buttons["queue"].configure(text=f"Очередь ({n})" if n else "Очередь")
        if s["active"]:
            items = [i for i in self.qm.items() if i.status not in qm.FINISHED]
            total = sum(i.size for i in items) or 1
            done = sum(min(i.downloaded, i.size) for i in items)
            pct = int(done / total * 100)
            self.title(f"{pct}% · {n} в очереди — YT Downloader")
            self.status_right.set(
                f"↓ {fmt_speed(s['speed']) or '…'}   осталось {dl.human_size(s['bytes_left'])}"
                + (f" · ~{fmt_eta(s['eta'])}" if s['eta'] else ""))
        else:
            self.title("YT Downloader")
            self.status_right.set("пауза" if self.qm.paused and n else "")

    def on_close(self) -> None:
        s = self.qm.summary()
        if s["active"] and not messagebox.askyesno(
                "Закрыть?", f"Сейчас скачивается {s['active']} "
                f"{plural(s['active'], 'видео', 'видео', 'видео')}.\n"
                "Очередь сохранится и продолжится при следующем запуске.\n\nЗакрыть?"):
            return
        self.qm.shutdown()
        self.destroy()


# ============================================================ base tab class
class Tab(ctk.CTkFrame):
    def __init__(self, master, app: DownloaderApp):
        super().__init__(master, fg_color=BG, corner_radius=0)
        self.app = app

    def on_show(self) -> None:
        pass

    def handle(self, kind: str, payload) -> None:
        pass

    def section(self, master, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(master, text=text, font=self.app.f_label,
                            text_color=INK_DIM, anchor="w")

    def btn(self, master, text, cmd, primary=False, width=110, **kw) -> ctk.CTkButton:
        if primary:
            return ctk.CTkButton(master, text=text, command=cmd, width=width, height=FIELD_H,
                                 corner_radius=RADIUS, fg_color=ACCENT,
                                 hover_color=ACCENT_HOVER, text_color=ACCENT_INK,
                                 text_color_disabled="#6b3a3a", font=self.app.f_bold, **kw)
        return ctk.CTkButton(master, text=text, command=cmd, width=width, height=FIELD_H,
                             corner_radius=RADIUS, fg_color="transparent", border_width=1,
                             border_color=BORDER, text_color=INK, hover_color=BG_RAISED_2,
                             text_color_disabled=INK_FAINT, font=self.app.f_field, **kw)


# ============================================================== Скачать
class DownloadTab(Tab):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.info: dl.VideoInfo | dl.PlaylistInfo | None = None
        self.multi: list[str] = []
        self.quality_var = tk.StringVar(value=appconfig.get("quality") or "h1080")
        self._busy = False

        body = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0,
                                      scrollbar_button_color=BORDER)
        body.pack(fill="both", expand=True)
        self.body = body

        self.section(body, "ССЫЛКИ  ·  можно вставить несколько (каждая с новой строки) "
                           "или плейлист").pack(fill="x", pady=(8, 6))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        self.url_text = ctk.CTkTextbox(row, height=64, corner_radius=RADIUS,
                                       fg_color=BG_RAISED, border_color=BORDER,
                                       border_width=1, text_color=INK, font=self.app.f_field,
                                       wrap="none")
        self.url_text.pack(side="left", fill="x", expand=True)
        self.url_text.bind("<Return>", lambda e: (self.on_fetch(), "break")[1])
        self.url_text.bind("<Button-3>", self._url_menu)
        col = ctk.CTkFrame(row, fg_color="transparent")
        col.pack(side="left", padx=(10, 0), fill="y")
        self.fetch_btn = self.btn(col, "Получить инфо", self.on_fetch, primary=True, width=140)
        self.fetch_btn.pack(fill="x")
        brow = ctk.CTkFrame(col, fg_color="transparent")
        brow.pack(fill="x", pady=(6, 0))
        self.btn(brow, "Вставить", lambda: self.paste(append=True), width=86,
                 ).pack(side="left")
        self.btn(brow, "✕", self.clear, width=46).pack(side="left", padx=(8, 0))

        # ---- preview card
        self.card = ctk.CTkFrame(body, fg_color=BG_RAISED, corner_radius=12,
                                 border_width=1, border_color=BORDER)
        self.card_inner = ctk.CTkFrame(self.card, fg_color="transparent")
        self.card_inner.pack(fill="both", expand=True, padx=16, pady=14)

        # ---- empty-state hint
        self.hint = ctk.CTkLabel(
            body, justify="left", anchor="w", font=self.app.f_label, text_color=INK_FAINT,
            text="1. Скопируйте ссылку на YouTube-видео — она подставится сама, "
                 "когда вернётесь в окно (или Ctrl+V).\n"
                 "2. «Получить инфо» — покажет длительность и вес для каждого качества.\n"
                 "3. «В очередь» — скачивание пойдёт в фоне, смотрите вкладку «Очередь».")
        self.hint.pack(fill="x", pady=(18, 0))

        # ---- save-to + settings
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", side="bottom", pady=(10, 12))
        self.section(bottom, "СОХРАНЯТЬ В").pack(fill="x", pady=(0, 6))
        drow = ctk.CTkFrame(bottom, fg_color="transparent")
        drow.pack(fill="x")
        self.dir_var = tk.StringVar(value=appconfig.get_output_dir())
        ctk.CTkEntry(drow, textvariable=self.dir_var, state="readonly", height=FIELD_H,
                     corner_radius=RADIUS, fg_color=BG_RAISED, border_color=BORDER,
                     border_width=1, text_color=INK, font=self.app.f_field,
                     ).pack(side="left", fill="x", expand=True)
        self.btn(drow, "Изменить…", self.on_browse).pack(side="left", padx=(10, 0))
        self.btn(drow, "Открыть", lambda: open_path(self.dir_var.get()),
                 width=90).pack(side="left", padx=(8, 0))

    # ------------------------------------------------------------ helpers
    def get_text(self) -> str:
        return self.url_text.get("1.0", "end")

    def set_text(self, text: str) -> None:
        self.url_text.delete("1.0", "end")
        self.url_text.insert("1.0", text)

    def paste(self, append=False) -> None:
        try:
            clip = self.clipboard_get()
        except tk.TclError:
            clip = ""
        urls = URL_RE.findall(clip)
        if not urls:
            self.app.status("В буфере нет ссылки — скопируйте ссылку на видео.", ERROR)
            return
        self.app._last_clip = clip.strip()
        cur = self.get_text().strip()
        new = "\n".join(u for u in urls if u not in cur)
        self.set_text((cur + "\n" + new).strip() if append and cur else "\n".join(urls))
        self.url_text.focus_set()
        n = len(URL_RE.findall(self.get_text()))
        self.app.status(f"Ссылок в поле: {n}. Нажмите «Получить инфо» (Enter).")

    def clear(self) -> None:
        self.set_text("")
        self._reset_card()

    def _url_menu(self, event):
        m = tk.Menu(self, tearoff=0, bg=BG_RAISED, fg=INK, activebackground=BORDER,
                    activeforeground=INK, bd=0)
        m.add_command(label="Вставить", command=lambda: self.paste(append=True))
        m.add_command(label="Очистить", command=self.clear)
        m.tk_popup(event.x_root, event.y_root)
        return "break"

    def on_browse(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.dir_var.get())
        if chosen:
            self.dir_var.set(os.path.normpath(chosen))
            appconfig.set_output_dir(os.path.normpath(chosen))

    def _reset_card(self) -> None:
        self.info, self.multi = None, []
        for w in self.card_inner.winfo_children():
            w.destroy()
        self.card.pack_forget()
        self.hint.pack(fill="x", pady=(18, 0))

    def _set_busy(self, busy: bool, text="Получаю информацию…") -> None:
        self._busy = busy
        self.fetch_btn.configure(state="disabled" if busy else "normal",
                                 text=text if busy else "Получить инфо")

    # ------------------------------------------------------------- fetch
    def on_fetch(self) -> None:
        if self._busy:
            return
        urls = list(dict.fromkeys(URL_RE.findall(self.get_text())))
        if not urls:
            self.app.status("Вставьте ссылку на видео.", ERROR)
            return
        self._reset_card()
        if len(urls) > 1:
            self.multi = urls
            self._render_multi()
            return
        self._set_busy(True)
        self.app.status("Получаю информацию о видео…")
        threading.Thread(target=self._fetch_worker, args=(urls[0],), daemon=True).start()

    def _fetch_worker(self, url: str) -> None:
        try:
            self.app.post("probe_ok", dl.probe(url))
        except dl.DownloaderError as exc:
            self.app.post("probe_err", str(exc))
        except Exception as exc:  # noqa: BLE001
            self.app.post("probe_err", f"Непредвиденная ошибка: {exc}")

    def handle(self, kind, payload) -> None:
        if kind == "probe_ok":
            self._set_busy(False)
            self.info = payload
            if isinstance(payload, dl.PlaylistInfo):
                self._render_playlist(payload)
            else:
                self._render_video(payload)
        elif kind == "probe_err":
            self._set_busy(False)
            self.app.status("Не удалось получить информацию", ERROR)
            messagebox.showerror("Ошибка", payload)

    # ------------------------------------------------------------ render
    def _show_card(self) -> None:
        self.hint.pack_forget()
        self.card.pack(fill="x", pady=(16, 0))

    def _render_video(self, info: dl.VideoInfo) -> None:
        self._show_card()
        top = ctk.CTkFrame(self.card_inner, fg_color="transparent")
        top.pack(fill="x")
        thumb = ctk.CTkLabel(top, text="", width=192, height=108, fg_color=BG_RAISED_2,
                             corner_radius=8)
        thumb.pack(side="left")
        self.app.thumbs.request(info.thumbnail, lambda img: thumb.configure(image=img),
                                size=(192, 108))
        meta = ctk.CTkFrame(top, fg_color="transparent")
        meta.pack(side="left", fill="both", expand=True, padx=(16, 0))
        ctk.CTkLabel(meta, text=info.title, font=self.app.f_h1, text_color=INK,
                     wraplength=560, justify="left", anchor="w").pack(fill="x")
        ctk.CTkLabel(meta, text=info.channel, font=self.app.f_field, text_color=INK_DIM,
                     anchor="w").pack(fill="x", pady=(2, 0))
        chips = ctk.CTkFrame(meta, fg_color="transparent")
        chips.pack(fill="x", pady=(10, 0))
        self._chip(chips, f"⏱  {dl.human_duration(info.duration)}")
        self.size_chip = self._chip(chips, "")

        self.section(self.card_inner, "КАЧЕСТВО  ·  вес = видео + звук").pack(
            fill="x", pady=(16, 6))
        grid = ctk.CTkFrame(self.card_inner, fg_color="transparent")
        grid.pack(fill="x")
        keys = [o.quality for o in info.options]
        pref = self.quality_var.get()
        if pref not in keys:
            # nearest lower resolution to the saved preference
            if pref.startswith("h"):
                lower = [k for k in keys if k.startswith("h") and int(k[1:]) <= int(pref[1:])]
                pref = lower[0] if lower else keys[0]
            else:
                pref = keys[0]
        self.quality_var.set(pref)
        for n, o in enumerate(info.options):
            rb = ctk.CTkRadioButton(
                grid, text=f"{o.label}", variable=self.quality_var, value=o.quality,
                font=self.app.f_field, text_color=INK, fg_color=ACCENT,
                hover_color=ACCENT_HOVER, border_color=INK_FAINT,
                command=self._update_size_chip)
            rb.grid(row=n // 2, column=(n % 2) * 2, sticky="w", pady=4, padx=(0, 8))
            ctk.CTkLabel(grid, text=dl.human_size(o.size), font=self.app.f_mono,
                         text_color=INK_DIM, anchor="e", width=80).grid(
                row=n // 2, column=(n % 2) * 2 + 1, sticky="e", padx=(0, 28))
        grid.grid_columnconfigure((0, 2), weight=1)
        self._update_size_chip()

        act = ctk.CTkFrame(self.card_inner, fg_color="transparent")
        act.pack(fill="x", pady=(16, 0))
        self.btn(act, "В очередь", self.add_current, primary=True, width=160).pack(side="right")
        self.free_lbl = ctk.CTkLabel(act, text=self._free_space_text(), font=self.app.f_small,
                                     text_color=INK_DIM, anchor="w")
        self.free_lbl.pack(side="left")
        self.app.status(f"{len(info.options)} вариантов качества. Выберите и нажмите «В очередь».")

    def _chip(self, master, text) -> ctk.CTkLabel:
        lbl = ctk.CTkLabel(master, text=text, font=self.app.f_bold, text_color=INK,
                           fg_color=BG_RAISED_2, corner_radius=6, height=28)
        lbl.pack(side="left", padx=(0, 8), ipadx=10)
        return lbl

    def _update_size_chip(self) -> None:
        if isinstance(self.info, dl.VideoInfo):
            size = self.info.size_for(self.quality_var.get())
            self.size_chip.configure(text=f"💾  {dl.human_size(size)}")
            appconfig.save(quality=self.quality_var.get())

    def _free_space_text(self) -> str:
        try:
            import shutil
            free = shutil.disk_usage(self.dir_var.get()).free
            return f"Свободно на диске: {dl.human_size(free)}"
        except OSError:
            return ""

    def _quality_menu(self, master) -> ctk.CTkOptionMenu:
        values = ["Лучшее", "2160p", "1440p", "1080p", "720p", "480p", "360p", "Только аудио"]
        keymap = {"Лучшее": "best", "Только аудио": "audio"}
        inv = {v: k for k, v in keymap.items()}
        cur = self.quality_var.get()
        cur_label = inv.get(cur, f"{cur[1:]}p" if cur.startswith("h") else "1080p")

        def on_pick(v):
            self.quality_var.set(keymap.get(v, "h" + v.rstrip("p")))
            appconfig.save(quality=self.quality_var.get())

        menu = ctk.CTkOptionMenu(master, values=values, command=on_pick, height=FIELD_H,
                                 corner_radius=RADIUS, fg_color=BG_RAISED_2,
                                 button_color=BG_RAISED_2, button_hover_color=BORDER,
                                 text_color=INK, dropdown_fg_color=BG_RAISED,
                                 dropdown_text_color=INK, dropdown_hover_color=BORDER,
                                 font=self.app.f_field, width=150)
        menu.set(cur_label if cur_label in values else "1080p")
        on_pick(menu.get())
        return menu

    def _render_list_card(self, title: str, subtitle: str, rows: list[tuple[str, str]],
                          add_label: str, on_add) -> None:
        self._show_card()
        ctk.CTkLabel(self.card_inner, text=title, font=self.app.f_h1, text_color=INK,
                     anchor="w", wraplength=700, justify="left").pack(fill="x")
        ctk.CTkLabel(self.card_inner, text=subtitle, font=self.app.f_field,
                     text_color=INK_DIM, anchor="w").pack(fill="x", pady=(2, 10))
        lst = ctk.CTkFrame(self.card_inner, fg_color=BG_RAISED_2, corner_radius=8)
        lst.pack(fill="x")
        for n, (left, right) in enumerate(rows[:12]):
            r = ctk.CTkFrame(lst, fg_color="transparent")
            r.pack(fill="x", padx=12, pady=(6 if n == 0 else 0, 4))
            ctk.CTkLabel(r, text=left, font=self.app.f_label, text_color=INK,
                         anchor="w").pack(side="left")
            ctk.CTkLabel(r, text=right, font=self.app.f_mono, text_color=INK_DIM,
                         anchor="e").pack(side="right")
        if len(rows) > 12:
            ctk.CTkLabel(lst, text=f"… и ещё {len(rows) - 12}", font=self.app.f_label,
                         text_color=INK_DIM, anchor="w").pack(fill="x", padx=12, pady=(0, 8))
        act = ctk.CTkFrame(self.card_inner, fg_color="transparent")
        act.pack(fill="x", pady=(14, 0))
        self.section(act, "Качество для всех:").pack(side="left")
        self._quality_menu(act).pack(side="left", padx=(10, 0))
        self.btn(act, add_label, on_add, primary=True, width=200).pack(side="right")
        ctk.CTkLabel(self.card_inner, text="Вес каждого видео появится в очереди, как только "
                     "загрузятся его данные.", font=self.app.f_small, text_color=INK_FAINT,
                     anchor="w").pack(fill="x", pady=(8, 0))

    def _render_playlist(self, pl: dl.PlaylistInfo) -> None:
        dur = sum(e.get("duration") or 0 for e in pl.entries)
        rows = [(f"{n}. {(e['title'] or e['url'])[:80]}", dl.human_duration(e.get("duration")))
                for n, e in enumerate(pl.entries, 1)]
        self._render_list_card(
            f"Плейлист: {pl.title}",
            f"{len(pl.entries)} видео · общая длительность {dl.human_hours(dur)}",
            rows, f"Добавить все ({len(pl.entries)})", self.add_playlist)
        self.app.status("Это плейлист — можно добавить все видео разом.")

    def _render_multi(self) -> None:
        rows = [(f"{n}. {u[:90]}", "") for n, u in enumerate(self.multi, 1)]
        self._render_list_card(f"Ссылок: {len(self.multi)}",
                               "Все добавятся в очередь, данные подтянутся автоматически.",
                               rows, f"Добавить все ({len(self.multi)})", self.add_multi)

    # --------------------------------------------------------------- add
    def _after_add(self, n: int) -> None:
        self.set_text("")
        self._reset_card()
        self.app.status(f"В очередь добавлено: {n} {plural(n, 'видео', 'видео', 'видео')}",
                        SUCCESS)
        self.app._refresh_counts()
        self.app.show_tab("queue")

    def add_current(self) -> None:
        if not isinstance(self.info, dl.VideoInfo):
            return
        self.app.qm.add(self.info.url, self.quality_var.get(), self.dir_var.get(),
                        info=self.info)
        self._after_add(1)

    def add_playlist(self) -> None:
        if not isinstance(self.info, dl.PlaylistInfo):
            return
        for e in self.info.entries:
            self.app.qm.add(e["url"], self.quality_var.get(), self.dir_var.get(), meta=e)
        self._after_add(len(self.info.entries))

    def add_multi(self) -> None:
        for u in self.multi:
            self.app.qm.add(u, self.quality_var.get(), self.dir_var.get())
        self._after_add(len(self.multi))


# ============================================================== Очередь
class QueueCard(ctk.CTkFrame):
    def __init__(self, master, tab: "QueueTab", item: qm.Item):
        super().__init__(master, fg_color=BG_RAISED, corner_radius=10, border_width=1,
                         border_color=BORDER)
        self.tab, self.app, self.id = tab, tab.app, item.id
        self._thumb_url = None
        f = self.app

        self.thumb = ctk.CTkLabel(self, text="▶", width=THUMB_W, height=THUMB_H,
                                  fg_color=BG_RAISED_2, corner_radius=6,
                                  text_color=INK_FAINT, font=f.f_h1)
        self.thumb.grid(row=0, column=0, rowspan=3, padx=(10, 12), pady=10, sticky="n")

        self.title = ctk.CTkLabel(self, text="", font=f.f_bold, text_color=INK, anchor="w",
                                  justify="left")
        self.title.grid(row=0, column=1, sticky="ew", pady=(10, 0))
        self.meta = ctk.CTkLabel(self, text="", font=f.f_label, text_color=INK_DIM, anchor="w")
        self.meta.grid(row=1, column=1, sticky="ew")

        prow = ctk.CTkFrame(self, fg_color="transparent")
        prow.grid(row=2, column=1, sticky="ew", pady=(4, 10))
        self.bar = ctk.CTkProgressBar(prow, height=6, corner_radius=3, fg_color=BORDER,
                                      progress_color=ACCENT)
        self.bar.pack(fill="x")
        srow = ctk.CTkFrame(prow, fg_color="transparent")
        srow.pack(fill="x", pady=(4, 0))
        self.state = ctk.CTkLabel(srow, text="", font=f.f_label, anchor="w")
        self.state.pack(side="left")
        self.nums = ctk.CTkLabel(srow, text="", font=f.f_mono, text_color=INK_DIM, anchor="e")
        self.nums.pack(side="right")

        self.actions = ctk.CTkFrame(self, fg_color="transparent")
        self.actions.grid(row=0, column=2, rowspan=3, padx=10, sticky="e")
        self.grid_columnconfigure(1, weight=1)
        self.bind("<Configure>", self._on_resize)
        self._action_sig = None
        self.refresh(item)

    def _on_resize(self, e) -> None:
        self.title.configure(wraplength=max(200, e.width - THUMB_W - 260))

    def _icon_btn(self, text, cmd, tip_color=INK) -> ctk.CTkButton:
        b = ctk.CTkButton(self.actions, text=text, command=cmd, width=34, height=30,
                          corner_radius=6, fg_color="transparent", border_width=1,
                          border_color=BORDER, hover_color=BG_RAISED_2, text_color=tip_color,
                          font=self.app.f_field)
        b.pack(side="left", padx=2)
        return b

    def _build_actions(self, it: qm.Item) -> None:
        sig = (it.status,)
        if sig == self._action_sig:
            return
        self._action_sig = sig
        for w in self.actions.winfo_children():
            w.destroy()
        m = self.app.qm
        if it.status == qm.DONE:
            self._icon_btn("▶", lambda: open_path(it.path))
            self._icon_btn("📂", lambda: reveal(it.path))
            self._icon_btn("✕", lambda: m.remove(self.id), INK_DIM)
        elif it.status in (qm.ERROR, qm.CANCELLED):
            self._icon_btn("↻", lambda: m.retry(self.id))
            self._icon_btn("✕", lambda: m.remove(self.id), INK_DIM)
        elif it.status == qm.QUEUED:
            self._icon_btn("↑", lambda: m.move(self.id, -1))
            self._icon_btn("↓", lambda: m.move(self.id, +1))
            self._icon_btn("✕", lambda: m.remove(self.id), INK_DIM)
        else:
            self._icon_btn("■", lambda: m.cancel(self.id), ERROR)

    def refresh(self, it: qm.Item) -> None:
        self.title.configure(text=it.title or it.url)
        meta = [dl.quality_label(it.quality)]
        if it.channel:
            meta.insert(0, it.channel)
        meta.append(f"⏱ {dl.human_duration(it.duration)}")
        meta.append(f"💾 {dl.human_size(it.size) if it.size else '…'}")
        self.meta.configure(text="   ·   ".join(meta))

        color = STATUS_COLOR.get(it.status, INK_DIM)
        label = qm.STATUS_RU.get(it.status, it.status)
        if it.status == qm.ERROR and it.error:
            label += f": {it.error.splitlines()[0][:110]}"
        if it.status == qm.DONE and it.finished:
            label += dt.datetime.fromtimestamp(it.finished).strftime("  ·  %d.%m %H:%M")
        self.state.configure(text=f"●  {label}", text_color=color)

        if it.status in (qm.DOWNLOADING, qm.MERGING, qm.PROBING):
            self.bar.configure(progress_color=ACCENT if it.status != qm.MERGING else BLUE)
            self.bar.set(it.progress)
            parts = [f"{dl.human_size(it.downloaded)} / {dl.human_size(it.size)}",
                     f"{it.progress:.0%}"]
            if it.speed:
                parts.append(fmt_speed(it.speed))
            if it.eta:
                parts.append(f"≈ {fmt_eta(it.eta)}")
            self.nums.configure(text="   ".join(parts))
        elif it.status == qm.DONE:
            self.bar.configure(progress_color=SUCCESS)
            self.bar.set(1)
            self.nums.configure(text=dl.human_size(it.size))
        else:
            self.bar.configure(progress_color=ACCENT)
            self.bar.set(it.progress if it.status == qm.CANCELLED else 0)
            self.nums.configure(text="")
        self.configure(border_color=ACCENT if it.status in qm.ACTIVE else BORDER)
        self._build_actions(it)

        if it.thumbnail and it.thumbnail != self._thumb_url:
            self._thumb_url = it.thumbnail
            self.app.thumbs.request(it.thumbnail,
                                    lambda img: self.thumb.configure(image=img, text=""))


class QueueTab(Tab):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.cards: dict[str, QueueCard] = {}
        self._order: list[str] = []

        # summary metrics
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(8, 0))
        self.m_count = self._metric(top, "В ОЧЕРЕДИ")
        self.m_size = self._metric(top, "ОБЩИЙ ВЕС")
        self.m_dur = self._metric(top, "ДЛИТЕЛЬНОСТЬ")
        self.m_speed = self._metric(top, "СКОРОСТЬ · ОСТАЛОСЬ")

        ctl = ctk.CTkFrame(self, fg_color="transparent")
        ctl.pack(fill="x", pady=(12, 8))
        self.pause_btn = self.btn(ctl, "⏸  Пауза", self.toggle_pause, width=130)
        self.pause_btn.pack(side="left")
        self.section(ctl, "Одновременно:").pack(side="left", padx=(16, 6))
        self.conc = ctk.CTkSegmentedButton(
            ctl, values=["1", "2", "3", "4"], command=lambda v: app.qm.set_concurrency(int(v)),
            selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=BG_RAISED, unselected_hover_color=BG_RAISED_2,
            fg_color=BG_RAISED, text_color=INK, font=self.app.f_field, height=32)
        self.conc.set(str(app.qm.concurrency))
        self.conc.pack(side="left")
        self.btn(ctl, "Очистить готовые", app.qm.clear_finished, width=150).pack(side="right")
        self.btn(ctl, "↻ Повторить ошибки", app.qm.retry_failed, width=160).pack(
            side="right", padx=(0, 8))

        self.list = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0,
                                           scrollbar_button_color=BORDER)
        self.list.pack(fill="both", expand=True, pady=(0, 8))
        self.empty = ctk.CTkLabel(
            self.list, text="Очередь пуста.\nДобавьте видео на вкладке «Скачать».",
            font=self.app.f_field, text_color=INK_FAINT, justify="center")
        self.rebuild()

    def _metric(self, master, label) -> ctk.CTkLabel:
        box = ctk.CTkFrame(master, fg_color=BG_RAISED, corner_radius=10, border_width=1,
                           border_color=BORDER)
        box.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(box, text=label, font=self.app.f_small, text_color=INK_DIM,
                     anchor="w").pack(fill="x", padx=14, pady=(10, 0))
        v = ctk.CTkLabel(box, text="—", font=self.app.f_h1, text_color=INK, anchor="w")
        v.pack(fill="x", padx=14, pady=(0, 10))
        return v

    def toggle_pause(self) -> None:
        self.app.qm.set_paused(not self.app.qm.paused)

    def on_show(self) -> None:
        self.rebuild()

    def rebuild(self) -> None:
        items = self.app.qm.items()
        ids = [i.id for i in items]
        for gone in set(self.cards) - set(ids):
            self.cards.pop(gone).destroy()
        if ids != self._order:
            for c in self.cards.values():
                c.pack_forget()
            for it in items:
                card = self.cards.get(it.id) or QueueCard(self.list, self, it)
                self.cards[it.id] = card
                card.pack(fill="x", pady=(0, 8))
            self._order = ids
        for it in items:
            self.cards[it.id].refresh(it)
        if items:
            self.empty.pack_forget()
        else:
            self.empty.pack(pady=60)
        self._update_summary()

    def update_items(self, ids: set[str]) -> None:
        if "*" in ids or any(i not in self.cards for i in ids) or \
                any(self.app.qm.get(i) is None for i in ids):
            self.rebuild()
            return
        for iid in ids:
            it = self.app.qm.get(iid)
            if it:
                self.cards[iid].refresh(it)
        self._update_summary()

    def _update_summary(self) -> None:
        s = self.app.qm.summary()
        self.m_count.configure(
            text=f"{s['pending']}" + (f"  ·  качается {s['active']}" if s["active"] else ""))
        size = dl.human_size(s["bytes"]) if s["bytes"] else "—"
        if s["unknown"]:
            size += f"  (+{s['unknown']} ?)"
        self.m_size.configure(text=size)
        self.m_dur.configure(text=dl.human_hours(s["seconds"]) if s["seconds"] else "—")
        if s["active"] and s["speed"]:
            self.m_speed.configure(text=f"{fmt_speed(s['speed'])} · {fmt_eta(s['eta'])}")
        elif s["pending"]:
            self.m_speed.configure(text="пауза" if self.app.qm.paused else "ожидание…")
        else:
            self.m_speed.configure(text="—")
        self.pause_btn.configure(text="▶  Продолжить" if self.app.qm.paused else "⏸  Пауза")


# ============================================================ Статистика
class BarChart(tk.Canvas):
    """30-day bar chart with hover tooltip, drawn on a plain Canvas."""

    def __init__(self, master, app):
        super().__init__(master, bg=BG_RAISED, highlightthickness=0, height=220)
        self.app = app
        self.data: list[dict] = []
        self.metric = "bytes"
        self.bars: list[tuple] = []
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda e: self.delete("tip"))

    def set(self, data, metric) -> None:
        self.data, self.metric = data, metric
        self.draw()

    def _fmt(self, v) -> str:
        if self.metric == "bytes":
            return dl.human_size(v) if v else "0"
        if self.metric == "seconds":
            return dl.human_hours(v) if v else "0"
        return str(int(v))

    def draw(self) -> None:
        self.delete("all")
        self.bars = []
        w, h = self.winfo_width(), self.winfo_height()
        if w < 50 or not self.data:
            return
        left, right, top, bottom = 64, 14, 16, 30
        vals = [d[self.metric] for d in self.data]
        vmax = max(vals) or 1
        pw, ph = w - left - right, h - top - bottom
        for i in range(5):
            y = top + ph * i / 4
            self.create_line(left, y, w - right, y, fill=BORDER)
            self.create_text(left - 8, y, text=self._fmt(vmax * (4 - i) / 4), anchor="e",
                             fill=INK_DIM, font=("Segoe UI", 8))
        n = len(self.data)
        slot = pw / n
        bw = max(3, slot * 0.66)
        today = dt.date.today().isoformat()
        for i, d in enumerate(self.data):
            x0 = left + slot * i + (slot - bw) / 2
            v = d[self.metric]
            bh = ph * v / vmax if v else 0
            color = ACCENT if d["day"] == today else "#c43c3c"
            if v:
                self.create_rectangle(x0, top + ph - bh, x0 + bw, top + ph, fill=color,
                                      outline="")
            else:
                self.create_line(x0, top + ph - 1, x0 + bw, top + ph - 1, fill=BORDER)
            self.bars.append((left + slot * i, left + slot * (i + 1), d))
            day = dt.date.fromisoformat(d["day"])
            if i % max(1, n // 10) == 0 or i == n - 1:
                self.create_text(x0 + bw / 2, h - bottom + 14, text=day.strftime("%d.%m"),
                                 fill=INK_DIM, font=("Segoe UI", 8))

    def _hover(self, e) -> None:
        self.delete("tip")
        for x0, x1, d in self.bars:
            if x0 <= e.x < x1:
                day = dt.date.fromisoformat(d["day"]).strftime("%d.%m.%Y")
                txt = (f"{day}\n{d['count']} видео · {dl.human_size(d['bytes']) if d['bytes'] else '0'}"
                       f"\n{dl.human_hours(d['seconds']) if d['seconds'] else '0 мин'}")
                tx = min(max(e.x + 12, 4), self.winfo_width() - 150)
                t = self.create_text(tx + 8, 12 + 6, text=txt, anchor="nw", fill=INK,
                                     font=("Segoe UI", 9), tags="tip")
                bx = self.bbox(t)
                r = self.create_rectangle(bx[0] - 8, bx[1] - 6, bx[2] + 8, bx[3] + 6,
                                          fill=BG, outline=BORDER, tags="tip")
                self.tag_lower(r, t)
                self.create_line((x0 + x1) / 2, 16, (x0 + x1) / 2, self.winfo_height() - 30,
                                 fill=INK_FAINT, dash=(2, 3), tags="tip")
                return


class StatsTab(Tab):
    PERIODS = {"Сегодня": 1, "7 дней": 7, "30 дней": 30, "Всё время": None}
    METRICS = {"Объём": "bytes", "Видео": "count", "Время": "seconds"}

    def __init__(self, master, app):
        super().__init__(master, app)
        self._stale = True

        body = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0,
                                      scrollbar_button_color=BORDER)
        body.pack(fill="both", expand=True)

        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x", pady=(8, 10))
        ctk.CTkLabel(head, text="Статистика", font=self.app.f_h1, text_color=INK).pack(
            side="left")
        self.period = self._seg(head, list(self.PERIODS), "Всё время", self.refresh)
        self.period.pack(side="right")

        cards = ctk.CTkFrame(body, fg_color="transparent")
        cards.pack(fill="x")
        self.c_count = self._metric(cards, "СКАЧАНО ВИДЕО")
        self.c_size = self._metric(cards, "ОБЪЁМ ДАННЫХ")
        self.c_time = self._metric(cards, "ВРЕМЯ ВИДЕО")
        self.c_avg = self._metric(cards, "СРЕДНЕЕ ЗА ДЕНЬ", last=True)

        chart_box = ctk.CTkFrame(body, fg_color=BG_RAISED, corner_radius=12, border_width=1,
                                 border_color=BORDER)
        chart_box.pack(fill="x", pady=(14, 0))
        ch = ctk.CTkFrame(chart_box, fg_color="transparent")
        ch.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(ch, text="По дням — последние 30 дней", font=self.app.f_bold,
                     text_color=INK).pack(side="left")
        self.metric = self._seg(ch, list(self.METRICS), "Объём", self.refresh)
        self.metric.pack(side="right")
        self.chart = BarChart(chart_box, app)
        self.chart.pack(fill="x", padx=10, pady=(0, 12))
        self.top_lbl = ctk.CTkLabel(chart_box, text="", font=self.app.f_small,
                                    text_color=INK_DIM, anchor="w", justify="left")
        self.top_lbl.pack(fill="x", padx=16, pady=(0, 12))

        hh = ctk.CTkFrame(body, fg_color="transparent")
        hh.pack(fill="x", pady=(16, 6))
        ctk.CTkLabel(hh, text="История загрузок", font=self.app.f_bold,
                     text_color=INK).pack(side="left")
        self.search_var = tk.StringVar()
        se = ctk.CTkEntry(hh, width=260, height=32,
                          corner_radius=RADIUS, fg_color=BG_RAISED, border_color=BORDER,
                          text_color=INK, placeholder_text="🔍  Поиск по названию или каналу",
                          placeholder_text_color=INK_FAINT, font=self.app.f_label)
        se.pack(side="right")
        se.bind("<KeyRelease>", lambda _e: (self.search_var.set(se.get()),
                                            self._fill_history()))

        self._style_tree()
        tf = ctk.CTkFrame(body, fg_color=BG_RAISED, corner_radius=10)
        tf.pack(fill="both", expand=True, pady=(0, 12))
        cols = ("date", "title", "dur", "size", "q", "src")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=12,
                                 style="Dark.Treeview")
        k = self._scale
        for c, text, w, anchor, stretch in (
                ("date", "Дата", 120, "w", False), ("title", "Название", 360, "w", True),
                ("dur", "Длит.", 64, "e", False), ("size", "Вес", 84, "e", False),
                ("q", "Качество", 84, "center", False), ("src", "Откуда", 90, "center", False)):
            self.tree.heading(c, text=text, anchor=anchor)
            self.tree.column(c, width=int(w * k), minwidth=int(w * k * 0.8),
                             anchor=anchor, stretch=stretch)
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree.tag_configure("odd", background=BG_RAISED)
        self.tree.tag_configure("even", background=BG_RAISED_2)
        self.tree.tag_configure("missing", foreground=INK_FAINT)
        self.tree.bind("<Double-1>", lambda e: self._open_sel(False))
        self.tree.bind("<Button-3>", self._tree_menu)
        self._rows: dict[str, dict] = {}

        self.after(10000, self._auto_refresh)

    def _seg(self, master, values, default, cmd) -> ctk.CTkSegmentedButton:
        s = ctk.CTkSegmentedButton(master, values=values, command=lambda _v: cmd(),
                                   selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
                                   unselected_color=BG_RAISED,
                                   unselected_hover_color=BG_RAISED_2, fg_color=BG_RAISED,
                                   text_color=INK, font=self.app.f_label, height=30)
        s.set(default)
        return s

    def _metric(self, master, label, last=False):
        box = ctk.CTkFrame(master, fg_color=BG_RAISED, corner_radius=12, border_width=1,
                           border_color=BORDER)
        box.pack(side="left", fill="x", expand=True, padx=(0, 0 if last else 10))
        ctk.CTkLabel(box, text=label, font=self.app.f_small, text_color=INK_DIM,
                     anchor="w").pack(fill="x", padx=16, pady=(12, 0))
        v = ctk.CTkLabel(box, text="0", font=self.app.f_metric, text_color=INK, anchor="w")
        v.pack(fill="x", padx=16)
        sub = ctk.CTkLabel(box, text="", font=self.app.f_small, text_color=INK_DIM, anchor="w")
        sub.pack(fill="x", padx=16, pady=(0, 12))
        return v, sub

    def _style_tree(self) -> None:
        # ttk ignores CTk's DPI scaling -> scale pixel sizes ourselves
        self._scale = ctk.ScalingTracker.get_widget_scaling(self)
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure("Dark.Treeview", background=BG_RAISED, fieldbackground=BG_RAISED,
                     foreground=INK, rowheight=int(28 * self._scale), borderwidth=0,
                     font=("Segoe UI", 10))
        st.configure("Dark.Treeview.Heading", background=BG_RAISED_2, foreground=INK_DIM,
                     relief="flat", borderwidth=0, font=("Segoe UI", 9, "bold"))
        st.map("Dark.Treeview", background=[("selected", "#3a1d1f")],
               foreground=[("selected", INK)])
        st.map("Dark.Treeview.Heading", background=[("active", BORDER)])
        st.layout("Dark.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    # -------------------------------------------------------------- data
    def mark_stale(self) -> None:
        self._stale = True
        if getattr(self.app, "current_tab", "") == "stats":
            self.refresh()

    def on_show(self) -> None:
        self.refresh()

    def _auto_refresh(self) -> None:
        # picks up downloads made through the Chrome extension agent too
        if getattr(self.app, "current_tab", "") == "stats":
            self.refresh()
        self.after(10000, self._auto_refresh)

    def refresh(self) -> None:
        days = self.PERIODS[self.period.get()]
        t = stats.totals(days)
        (vc, sc), (vs, ss), (vt, st), (va, sa) = (self.c_count, self.c_size,
                                                  self.c_time, self.c_avg)
        vc.configure(text=str(t["count"]))
        vs.configure(text=dl.human_size(t["bytes"]) if t["bytes"] else "0")
        vt.configure(text=dl.human_hours(t["seconds"]) if t["seconds"] else "0")
        today, week = stats.totals(1), stats.totals(7)
        sc.configure(text=f"сегодня {today['count']} · за 7 дней {week['count']}")
        ss.configure(text=f"сегодня {dl.human_size(today['bytes']) if today['bytes'] else '0'}")
        mins = t["seconds"] / 60
        st.configure(text=f"{mins:,.0f} мин · {t['seconds'] / 3600:.1f} ч".replace(",", " ")
                     if t["seconds"] else "")

        series = stats.per_day(30)
        span = days or max(1, self._span_days())
        va.configure(text=dl.human_size(t["bytes"] / span) if t["bytes"] else "0")
        sa.configure(text=f"{t['count'] / span:.1f} видео · "
                          f"{dl.human_hours(t['seconds'] / span)}" if t["count"] else "")
        self.chart.set(series, self.METRICS[self.metric.get()])
        top = stats.top_channels(3)
        active_days = sum(1 for d in series if d["count"])
        txt = f"Активных дней за 30: {active_days}"
        if top:
            txt += "   ·   Топ каналов: " + ", ".join(f"{c} ({n})" for c, n in top)
        self.top_lbl.configure(text=txt)
        self._fill_history()
        self._stale = False

    def _span_days(self) -> int:
        h = stats.history(limit=1_000_000)
        if not h:
            return 1
        first = dt.date.fromtimestamp(min(r["ts"] for r in h))
        return (dt.date.today() - first).days + 1

    def _fill_history(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        for n, r in enumerate(stats.history(limit=1000, search=self.search_var.get().strip())):
            tags = ["odd" if n % 2 else "even"]
            if not os.path.exists(r["path"] or ""):
                tags.append("missing")
            iid = str(r["id"])
            self._rows[iid] = r
            self.tree.insert("", "end", iid=iid, tags=tags, values=(
                dt.datetime.fromtimestamp(r["ts"]).strftime("%d.%m.%Y %H:%M"),
                r["title"], dl.human_duration(r["duration"]), dl.human_size(r["size"]),
                r["quality"] or "", "Chrome" if r["source"] == "extension" else "Прилож."))

    def _sel(self):
        s = self.tree.selection()
        return self._rows.get(s[0]) if s else None

    def _open_sel(self, folder: bool) -> None:
        r = self._sel()
        if not r:
            return
        if not os.path.exists(r["path"] or ""):
            self.app.status("Файл перемещён или удалён.", ERROR)
            return
        (reveal if folder else open_path)(r["path"])

    def _tree_menu(self, e) -> None:
        row = self.tree.identify_row(e.y)
        if not row:
            return
        self.tree.selection_set(row)
        r = self._rows[row]
        m = tk.Menu(self, tearoff=0, bg=BG_RAISED, fg=INK, activebackground=BORDER,
                    activeforeground=INK, bd=0)
        m.add_command(label="Открыть видео", command=lambda: self._open_sel(False))
        m.add_command(label="Показать в папке", command=lambda: self._open_sel(True))
        m.add_command(label="Скопировать ссылку", command=lambda: (
            self.clipboard_clear(), self.clipboard_append(r["url"] or "")))
        m.add_command(label="Скачать снова", command=lambda: (
            self.app.tabs["download"].set_text(r["url"] or ""), self.app.show_tab("download")))
        m.add_separator()
        m.add_command(label="Удалить из истории", command=lambda: (
            stats.delete(r["id"]), self.refresh()))
        m.tk_popup(e.x_root, e.y_root)
