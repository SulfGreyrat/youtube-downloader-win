"""Download history + statistics (SQLite in %APPDATA%/YouTubeDownloader).

Shared by the GUI and the background agent (Chrome extension downloads are
counted too). Each call opens its own connection -> safe across threads and
processes.
"""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
import time

import config

DB_PATH = os.path.join(config.CONFIG_DIR, "history.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL    NOT NULL,          -- unix time of completion
    day       TEXT    NOT NULL,          -- local date YYYY-MM-DD
    url       TEXT,
    video_id  TEXT,
    title     TEXT,
    channel   TEXT,
    duration  REAL    DEFAULT 0,         -- seconds of video
    size      INTEGER DEFAULT 0,         -- bytes on disk
    quality   TEXT,
    path      TEXT,
    source    TEXT    DEFAULT 'app'      -- app | extension
);
CREATE INDEX IF NOT EXISTS idx_downloads_day ON downloads(day);
"""


def _conn() -> sqlite3.Connection:
    os.makedirs(config.CONFIG_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.executescript(_SCHEMA)
    return con


def record(*, url: str, video_id: str, title: str, channel: str, duration: float,
           size: int, quality: str, path: str, source: str = "app",
           ts: float | None = None) -> None:
    ts = ts or time.time()
    day = dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    with _conn() as con:
        con.execute(
            "INSERT INTO downloads(ts, day, url, video_id, title, channel, duration,"
            " size, quality, path, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ts, day, url, video_id, title, channel, float(duration or 0),
             int(size or 0), quality, path, source))


def _since_day(days: int | None) -> str:
    if days is None:
        return "0000-00-00"
    return (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()


def totals(days: int | None = None) -> dict:
    """Aggregates for the last `days` days (1 = today) or all time (None)."""
    with _conn() as con:
        n, size, dur = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(size),0), COALESCE(SUM(duration),0)"
            " FROM downloads WHERE day >= ?", (_since_day(days),)).fetchone()
    return {"count": n, "bytes": size, "seconds": dur}


def per_day(days: int = 30) -> list[dict]:
    """One row per day (oldest first), zero-filled."""
    start = dt.date.today() - dt.timedelta(days=days - 1)
    with _conn() as con:
        rows = con.execute(
            "SELECT day, COUNT(*), SUM(size), SUM(duration) FROM downloads"
            " WHERE day >= ? GROUP BY day", (start.isoformat(),)).fetchall()
    by_day = {r[0]: r for r in rows}
    out = []
    for i in range(days):
        d = (start + dt.timedelta(days=i)).isoformat()
        r = by_day.get(d)
        out.append({"day": d, "count": r[1] if r else 0,
                     "bytes": (r[2] or 0) if r else 0,
                     "seconds": (r[3] or 0) if r else 0})
    return out


def history(limit: int = 500, search: str = "") -> list[dict]:
    q = ("SELECT id, ts, title, channel, duration, size, quality, path, source, url"
         " FROM downloads")
    args: tuple = ()
    if search:
        q += " WHERE title LIKE ? OR channel LIKE ?"
        args = (f"%{search}%", f"%{search}%")
    q += " ORDER BY ts DESC LIMIT ?"
    with _conn() as con:
        rows = con.execute(q, args + (limit,)).fetchall()
    keys = ("id", "ts", "title", "channel", "duration", "size", "quality", "path",
            "source", "url")
    return [dict(zip(keys, r)) for r in rows]


def top_channels(limit: int = 5) -> list[tuple[str, int]]:
    with _conn() as con:
        return con.execute(
            "SELECT channel, COUNT(*) c FROM downloads WHERE channel != ''"
            " GROUP BY channel ORDER BY c DESC LIMIT ?", (limit,)).fetchall()


def delete(row_id: int) -> None:
    with _conn() as con:
        con.execute("DELETE FROM downloads WHERE id = ?", (row_id,))
