"""Shared settings file used by both the GUI app and the background server.

Both processes read/write the same JSON file so changing the output folder
in the GUI immediately takes effect for downloads triggered from the Chrome
extension, and vice versa.
"""

from __future__ import annotations

import json
import os

_CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                           "YouTubeDownloader")
CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.json")


def _default_output_dir() -> str:
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    return downloads if os.path.isdir(downloads) else os.path.expanduser("~")


def load() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and data.get("output_dir"):
            return data
    except (OSError, ValueError):
        pass
    return {"output_dir": _default_output_dir()}


def get_output_dir() -> str:
    return load().get("output_dir") or _default_output_dir()


def set_output_dir(path: str) -> None:
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    data = load()
    data["output_dir"] = path
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
