"""Entry point for the YouTube Downloader GUI app."""

from __future__ import annotations

import os
import sys

# Make sibling modules importable when run as `python src/main.py`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui import DownloaderApp  # noqa: E402


def main() -> None:
    app = DownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
