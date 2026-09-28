"""GUI smoke: start the app against the test APPDATA, screenshot every tab,
probe a real URL, then close. Run after tests/smoke_core.py.
"""

import os
import sys
import tempfile

TMP = os.path.join(tempfile.gettempdir(), "ytdl_test")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import main as entry  # noqa: E402

entry._windows_setup()
from gui import DownloaderApp  # noqa: E402

OUT = os.path.join(TMP, "shots")
os.makedirs(OUT, exist_ok=True)
app = DownloaderApp()
app.geometry("1000x720+40+40")


def shot(name):
    import ctypes
    from ctypes import wintypes

    from PIL import Image
    app.update()
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = user32.GetParent(app.winfo_id())
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)  # PW_RENDERFULLCONTENT: works when occluded

    class BMI(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("a", wintypes.DWORD), ("b", wintypes.LONG), ("c", wintypes.LONG),
                    ("d", wintypes.DWORD), ("e", wintypes.DWORD)]
    bmi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).save(
        os.path.join(OUT, name + ".png"))
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    print("shot", name)


steps = []


def step(delay, fn):
    steps.append((delay, fn))


def run(i=0):
    if i >= len(steps):
        app.qm.shutdown()
        app.destroy()
        return
    d, fn = steps[i]
    app.after(d, lambda: (fn(), run(i + 1)))


step(1500, lambda: shot("1_download_empty"))
step(100, lambda: (app.tabs["download"].set_text(
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ"), app.tabs["download"].on_fetch()))
step(25000, lambda: shot("2_download_info"))
step(100, lambda: app.tabs["download"].add_current())
step(100, lambda: app.qm.add("https://www.youtube.com/watch?v=jNQXAC9IVRw", "best",
                             app.tabs["download"].dir_var.get()))
step(9000, lambda: shot("3_queue"))
step(100, lambda: [app.qm.cancel(i.id) for i in app.qm.items() if i.status in ("downloading", "merging", "probing", "queued")])
step(3000, lambda: app.show_tab("stats"))
step(1500, lambda: shot("4_stats"))
run()
app.mainloop()
print("closed OK")
