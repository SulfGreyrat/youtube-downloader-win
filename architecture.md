# YouTube Downloader for Windows — Architecture

## 1. Overview

A desktop Windows application to download YouTube videos in any available
quality, including high-resolution video-only streams (1440p/4K) that YouTube
serves separately from audio, merged into a single MP4 via ffmpeg.

Goal: a simple, single-purpose GUI app, packaged as a standalone `.exe` for
end users who don't have Python installed.

## 2. Technology Stack

| Concern            | Choice                              | Rationale |
|---------------------|--------------------------------------|-----------|
| Download engine      | `yt-dlp` (Python library, not CLI wrapper) | Actively maintained fork of youtube-dl; exposes a clean Python API (`yt_dlp.YoutubeDL`), handles format listing, muxing, and progress hooks natively. |
| GUI toolkit          | `tkinter` (stdlib) | Ships with every standard Python install (and with PyInstaller-built exe, no extra runtime deps). No need for the richer widget set of PySide6/Qt for this scope, and it avoids ~50-80MB of extra bundled Qt binaries in the final exe. `ttk` themed widgets used for a cleaner look. |
| Merging video+audio | `ffmpeg` (external binary) | Required by yt-dlp to mux separate video-only + audio-only streams into one file. Not bundled in this repo (see section 6); yt-dlp auto-detects `ffmpeg.exe` on PATH or via `ffmpeg_location`. |
| Packaging            | `PyInstaller` (`--onefile`) | De-facto standard, single-command build to a Windows `.exe`. |
| Language             | Python 3.10+ | Required by current yt-dlp releases. |

No web scraping, no browser embedding, no network server — all functionality
goes through the yt-dlp library API.

## 3. Repository Structure

```
youtube-downloader-win/
├── architecture.md          # this file
├── README.md                # usage + build instructions
├── requirements.txt         # runtime deps
├── .gitignore                # Python / PyInstaller / venv ignores
├── LICENSE                    # MIT
├── build.spec                 # PyInstaller spec file
└── src/
    ├── main.py               # entry point, launches the GUI
    ├── gui.py                # Tkinter UI: widgets, layout, event wiring
    └── downloader.py         # yt-dlp wrapper: format listing, download, progress
```

Rationale for splitting `gui.py` / `downloader.py`: keeps yt-dlp-specific
logic (which may need adjusting as YouTube changes) isolated from UI code, and
keeps the UI testable/replaceable independently.

## 4. Module Responsibilities

### 4.1 `src/main.py`

- Entry point. Only responsibility: construct and run the Tkinter app.
- Minimal content:

```python
from gui import DownloaderApp

def main():
    app = DownloaderApp()
    app.mainloop()

if __name__ == "__main__":
    main()
```

- This is also the module PyInstaller targets (`pyinstaller build.spec`).

### 4.2 `src/downloader.py`

Wraps all yt-dlp interaction. No Tkinter imports here — keeps it UI-agnostic
and unit-testable.

Public API:

```python
class FormatInfo:
    format_id: str        # yt-dlp format id, e.g. "137" or "22"
    ext: str               # "mp4", "webm", "m4a", ...
    resolution: str        # "3840x2160", "1920x1080", "audio only", ...
    fps: float | None
    vcodec: str            # "none" if audio-only
    acodec: str            # "none" if video-only
    filesize_approx: int | None
    note: str              # human-readable label built for the combo box,
                            # e.g. "2160p60 (video only) — mp4 — ~350MB"

def list_formats(url: str) -> tuple[str, list[FormatInfo]]:
    """
    Runs YoutubeDL(...).extract_info(url, download=False).
    Returns (video_title, formats) sorted best-quality-first.
    Raises DownloaderError on invalid URL / network failure.
    """

def download(
    url: str,
    format_id: str,
    output_dir: str,
    progress_callback: Callable[[dict], None],
) -> str:
    """
    Downloads `format_id`. If format_id refers to a video-only stream,
    passes format_id + "+bestaudio/best" to yt-dlp so it auto-merges
    via ffmpeg (requires ffmpeg on PATH — see note below).
    Calls progress_callback(status_dict) on each yt-dlp progress hook tick;
    status_dict has keys: status ("downloading"/"finished"/"error"),
    downloaded_bytes, total_bytes, speed, eta.
    Returns the final output file path.
    Raises DownloaderError on failure (network, ffmpeg missing, etc).
    """

class DownloaderError(Exception):
    ...
```

Implementation notes:

- `list_formats`: build `YoutubeDL({"quiet": True, "skip_download": True})`,
  call `extract_info`, read `info["formats"]`. Filter out storyboard/thumbnail
  pseudo-formats (`vcodec == "none" and acodec == "none"`). Sort by:
  combined streams with audio+video first at top qualities, then video-only
  high-res streams, then audio-only. Simplify to: sort by
  `(height or 0, tbr or 0)` descending, label video-only entries clearly so
  the user understands muxing will happen.
- For "download best available quality" convenience option in the combo box,
  offer a synthetic top entry `"Best available (auto, video+audio merged)"`
  mapped internally to yt-dlp format string `"bestvideo+bestaudio/best"`.
- `download`: build `YoutubeDL` with options:
  ```python
  {
      "format": format_id,   # or "<id>+bestaudio/best" for video-only ids
      "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
      "merge_output_format": "mp4",
      "progress_hooks": [hook],
      "noplaylist": True,
      "quiet": True,
      "ffmpeg_location": find_ffmpeg(),  # None lets yt-dlp search PATH
  }
  ```
- `find_ffmpeg()`: helper that checks (a) `ffmpeg.exe` next to the running
  exe/script, (b) `PATH`. If not found, `download()` still attempts
  combined-stream formats but raises a clear `DownloaderError` telling the
  user to install ffmpeg when a merge is actually required.
- Progress hook translates yt-dlp's raw dict into the simplified
  `progress_callback` shape; must be safe to call from the yt-dlp download
  thread (it will just push values, GUI thread reads them — see 4.3
  threading notes).

### 4.3 `src/gui.py`

`class DownloaderApp(tk.Tk)` — the single window.

Widgets (top to bottom):

1. URL entry (`ttk.Entry`) + "Get info" / "Fetch formats" button.
2. Video title label (populated after fetch).
3. Format combo box (`ttk.Combobox`, read-only) populated from
   `downloader.list_formats()` results — display `FormatInfo.note` strings.
4. Output folder row: `ttk.Entry` (read-only, shows chosen path) + "Browse…"
   button opening `tkinter.filedialog.askdirectory`. Defaults to
   `~/Downloads`.
5. Progress bar (`ttk.Progressbar`, determinate) + percentage/speed/ETA label.
6. "Download" button.
7. Status/log label at the bottom for errors and completion messages.

Threading model (critical — Tkinter is not thread-safe):

- "Fetch formats" and "Download" both run `downloader.*` calls in a
  `threading.Thread(daemon=True)` so the UI stays responsive.
- The worker thread never touches Tkinter widgets directly. Instead:
  - `list_formats` result is pushed to a `queue.Queue`, and the main thread
    polls it via `self.after(100, self._poll_queue)`.
  - `download`'s `progress_callback` similarly pushes progress dicts to a
    queue; a `self.after(...)` loop updates the progress bar/labels from the
    main thread.
- Buttons are disabled while a fetch/download is in-flight and re-enabled on
  completion or error, to prevent overlapping operations.
- Errors (`DownloaderError` or unexpected exceptions) caught in the worker
  thread, pushed through the queue, and shown via
  `tkinter.messagebox.showerror` on the main thread.

State held in `DownloaderApp`:

```python
self.current_url: str
self.current_formats: list[FormatInfo]
self.output_dir: str
self._queue: queue.Queue
```

## 5. Data / Control Flow

1. User pastes URL, clicks "Get info".
2. GUI spawns thread → `downloader.list_formats(url)`.
3. On success: combo box populated, title shown, "Download" enabled.
   On failure: error dialog, state reset.
4. User picks a format (or leaves default "Best available"), picks output
   folder, clicks "Download".
5. GUI spawns thread → `downloader.download(url, format_id, output_dir, cb)`.
6. Progress hook fires repeatedly → queue → progress bar updates on main
   thread via `after()` polling.
7. On finish: status label shows final file path; on error: error dialog.

## 6. ffmpeg Dependency

- Not bundled in the repository (binary, license, size). README instructs
  users to either:
  - install ffmpeg and add it to PATH (`winget install ffmpeg` or manual
    download from ffmpeg.org and add `bin/` to PATH), or
  - drop `ffmpeg.exe` in the same folder as the app's exe (picked up by
    `find_ffmpeg()` in section 4.2).
- Only strictly required when merging separate video-only + audio-only
  streams (i.e. anything above the highest "progressive" combined-stream
  resolution YouTube offers, typically 720p). Combined-stream formats
  (audio+video already muxed by YouTube) work without ffmpeg.

## 7. Packaging (.exe)

`build.spec` (PyInstaller spec, generated once via
`pyi-makespec --onefile --windowed --name YouTubeDownloader src/main.py`
then hand-edited):

- `--onefile`: single exe, easiest to distribute.
- `--windowed` (`console=False` in spec): no console window behind the GUI.
- `--name YouTubeDownloader`.
- `pathex` includes `src/` so `gui`/`downloader` are importable.
- No `--add-data` needed (no bundled assets); ffmpeg stays external per
  section 6.

Build command (documented in README):

```
pip install -r requirements.txt pyinstaller
pyinstaller build.spec
```

Output: `dist/YouTubeDownloader.exe`.

## 8. requirements.txt

```
yt-dlp>=2024.1.0
```

(`tkinter` is stdlib, not pip-installable, so it's not listed; README notes
that on some minimal Python installs on Linux `tkinter` needs a system
package — not relevant for the Windows target here but mentioned for
completeness. `pyinstaller` is a build-time-only dependency, listed
separately in README's build section rather than requirements.txt to keep
runtime deps minimal.)

## 9. Error Handling & Edge Cases

- Invalid / non-YouTube URL → `DownloaderError` with a clear message,
  surfaced via `messagebox.showerror`.
- Age-restricted / region-locked / private videos → yt-dlp raises
  `DownloadError`; wrapped into `DownloaderError` and shown to the user
  as-is (yt-dlp's messages are already descriptive).
- Network interruption mid-download → yt-dlp raises; caught, status label
  reset, partial file cleanup left to yt-dlp's own `.part` file handling.
- No ffmpeg + video-only format selected → pre-flight check in
  `download()` before starting: if merge is needed and `find_ffmpeg()`
  returns falsy, raise `DownloaderError` immediately with install
  instructions, instead of letting yt-dlp fail deep into the download.
- Output folder without write permission → caught as an OS error, wrapped
  and shown.

## 10. Out of Scope (for this iteration)

- Playlist downloads (`noplaylist: True` is forced).
- Subtitle download/embedding.
- Download queue / multiple concurrent downloads.
- Auto-update mechanism for the app or for yt-dlp itself (README will note
  that yt-dlp extractors can go stale and recommend periodically upgrading
  via `pip install -U yt-dlp` and rebuilding, since YouTube changes break
  older yt-dlp versions).
- git init / commit / push (explicitly deferred to a follow-up devops task).
