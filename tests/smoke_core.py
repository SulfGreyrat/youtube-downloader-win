"""Core smoke test (no GUI): real downloads through QueueManager.

Uses an isolated APPDATA and %TEMP%/ytdl_test, so it never touches the real
history/queue. Run: .buildenv/Scripts/python.exe tests/smoke_core.py
"""

import os
import sys
import tempfile
import time

TMP = os.path.join(tempfile.gettempdir(), "ytdl_test")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import shutil  # noqa: E402

shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP)

import yt_dlp  # noqa: E402

import downloader as dl  # noqa: E402
import queue_manager as qm  # noqa: E402
import stats  # noqa: E402

OUT = os.path.join(TMP, "out")


def find_russian_short() -> str:
    with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True}) as y:
        res = y.extract_info("ytsearch15:мультик короткий | смешно?", download=False)
    for e in res["entries"]:
        if e.get("duration") and 15 < e["duration"] < 100 and any(
                "а" <= c.lower() <= "я" for c in (e.get("title") or "")):
            return f"https://www.youtube.com/watch?v={e['id']}", e["title"]
    raise SystemExit("no short russian video found")


def main() -> None:
    ru_url, ru_title = find_russian_short()
    print("RU video:", ru_url, ru_title)

    info = dl.probe(ru_url)
    print("probe:", info.title, dl.human_duration(info.duration))
    for o in info.options:
        print(f"   {o.quality:6} {o.label:32} {dl.human_size(o.size)}")
    assert info.options and info.options[0].size, "no sizes"

    events = []
    q = qm.QueueManager(listener=events.append)
    a = q.add("https://www.youtube.com/watch?v=jNQXAC9IVRw", "best", OUT)  # bare URL
    b = q.add(ru_url, "h360", OUT, info=info)
    c = q.add("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "best", OUT)
    time.sleep(0.5)
    q.cancel(c.id)

    t0 = time.time()
    while time.time() - t0 < 300:
        st = {i.title[:25] or i.url[-11:]: (i.status, f"{i.progress:.0%}") for i in q.items()}
        if all(i.status in qm.FINISHED for i in q.items()):
            break
        time.sleep(2)
    print("statuses:", {i.title: i.status for i in q.items()})
    q.shutdown()

    for it in (a, b):
        it = next(i for i in q.items() if i.id == it.id)
        assert it.status == qm.DONE, (it.title, it.status, it.error)
        name = os.path.basename(it.path)
        print(f"file: {name}  {dl.human_size(os.path.getsize(it.path))}"
              f"  (expected {dl.human_size(it.size)})")
        assert os.path.isfile(it.path)
        assert "_" not in name or "_" in it.title, f"mangled name: {name}"
        assert ".f" not in name.rsplit(".", 2)[-2] if name.count(".") > 1 else True
    OUT_ = OUT
    ru_path = next(i for i in q.items() if i.id == b.id).path
    assert any("а" <= ch.lower() <= "я" for ch in os.path.basename(ru_path)), "cyrillic lost"
    cc = next(i for i in q.items() if i.id == c.id)
    assert cc.status == qm.CANCELLED, cc.status
    leftovers = [f for f in os.listdir(OUT) if f.endswith((".part", ".ytdl")) or ".f" in f]
    print("dir:", os.listdir(OUT))
    assert not leftovers, leftovers

    # queue persistence
    q2 = qm.QueueManager(autostart=False)
    assert len(q2.items()) == 3, len(q2.items())
    print("restored queue:", [(i.title[:20], i.status) for i in q2.items()])

    t = stats.totals()
    print("stats all:", t, "today:", stats.totals(1))
    assert t["count"] == 2 and t["bytes"] > 0 and t["seconds"] > 0
    days = stats.per_day(30)
    assert len(days) == 30 and days[-1]["count"] == 2
    print("history:", [(h["title"], h["quality"]) for h in stats.history()])
    print("OK")


if __name__ == "__main__":
    main()
