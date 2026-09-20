# YouTube Downloader for Windows

A small desktop app (Python + tkinter + yt-dlp) that downloads a YouTube video
in **any** available quality, including 1440p/4K video-only streams which are
merged with the best audio track into a single MP4 via ffmpeg.

## Features

- Paste a URL, press **Get info** → full list of available formats/qualities.
- Synthetic **"Best available (auto, video+audio merged)"** option at the top.
- Choose the output folder (defaults to `~/Downloads`).
- Progress bar with percentage, speed and ETA; UI stays responsive
  (download runs in a worker thread).
- Clear errors for invalid URLs, private/region-locked videos, missing ffmpeg
  and unwritable output folders.

## Requirements

- Python 3.10+ (Windows builds include `tkinter` out of the box)
- `yt-dlp` (see `requirements.txt`)
- **ffmpeg** — only needed when merging separate video+audio streams, i.e. for
  anything above ~720p. Two options:
  - `winget install Gyan.FFmpeg` and restart your terminal/app, or
  - drop `ffmpeg.exe` next to `YouTubeDownloader.exe` (or next to `src/`).

## Run from source

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

## Build a standalone .exe

```
pip install -r requirements.txt pyinstaller
pyinstaller build.spec
```

Result: `dist/YouTubeDownloader.exe` — a single-file, windowed (no console)
executable. It does **not** bundle ffmpeg; ship `ffmpeg.exe` alongside it or
tell users to install it (see above).

## Usage

1. Paste the video URL.
2. Press **Get info** — the title appears and the quality dropdown fills up.
   Entries marked *(video only, will be merged with audio)* require ffmpeg.
3. Pick the output folder with **Browse…**.
4. Press **Download**. The progress bar shows percentage, speed and ETA; when
   finished, the final file path is shown in the status line.

## Notes / limitations

- Playlists are not supported (`noplaylist` is forced — only the single video).
- No subtitles, no download queue, no auto-update.
- YouTube changes break older yt-dlp versions. If downloads start failing,
  run `pip install -U yt-dlp` (and rebuild the exe).
- On minimal Linux Python installs `tkinter` needs a system package
  (`python3-tk`); irrelevant on Windows.

## License

MIT — see `LICENSE`.
