"""Shared settings file used by both the GUI app and the background agent.

Both processes read/write the same JSON file so changing the output folder
in the GUI immediately takes effect for downloads triggered from the Chrome
extension, and vice versa.
"""

from __future__ import annotations

import json
import os

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                          "YouTubeDownloader")
_CONFIG_DIR = CONFIG_DIR  # backwards compatibility
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "output_dir": None,        # filled lazily
    "quality": "h1080",        # default quality for new items / extension
    "concurrency": 2,          # parallel downloads
}


def _default_output_dir() -> str:
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    return downloads if os.path.isdir(downloads) else os.path.expanduser("~")


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            stored = json.load(fh)
        if isinstance(stored, dict):
            data.update(stored)
    except (OSError, ValueError):
        pass
    if not data.get("output_dir"):
        data["output_dir"] = _default_output_dir()
    return data


def save(**changes) -> dict:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    data = load()
    data.update(changes)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_PATH)
    return data


def get(key: str):
    return load().get(key, DEFAULTS.get(key))


def get_output_dir() -> str:
    return load()["output_dir"]


def set_output_dir(path: str) -> None:
    save(output_dir=path)
