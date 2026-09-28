"""Entry point for the YouTube Downloader GUI app."""

from __future__ import annotations

import ctypes
import os
import sys

# Make sibling modules importable when run as `python src/main.py`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

APP_ID = "SulfGreyrat.YTDownloader.2"


def _windows_setup() -> bool:
    """Own taskbar icon + single instance. Returns False if already running."""
    if sys.platform != "win32":
        return True
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:  # noqa: BLE001
        pass
    try:  # crisp text on HiDPI screens
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, "Local\\" + APP_ID)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        _focus_existing()
        return False
    return True


def _focus_existing() -> None:
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value.endswith("YT Downloader"):
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    for hwnd in found:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)


def main() -> None:
    if not _windows_setup():
        return
    from gui import DownloaderApp

    app = DownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
