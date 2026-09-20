"""Smoke test: launch the GUI, let it idle, then close it."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from gui import DownloaderApp  # noqa: E402

app = DownloaderApp()
app.after(2500, app.destroy)
app.mainloop()
print("GUI smoke test OK: window created, idle loop ran, closed cleanly.")
