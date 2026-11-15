"""The DOM's memory on disk (SQLite): every event and how price reacted to it."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.engine import Event

COLUMNS = (
    "id",
    "day",
    "sym",
    "kind",
    "side",
    "price",
    "t",
    "peak",
    "size",
    "filled",
    "pulled",
    "absorbed",
    "tests",
    "dist_ticks",
    "ref",
    "away",
    "through",
    "m1",
    "m5",
    "done",
)


class Store:
    def __init__(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS events (uid INTEGER PRIMARY KEY AUTOINCREMENT, id INTEGER, day TEXT, sym TEXT,"
            " kind TEXT, side TEXT, price REAL, t INTEGER, peak INTEGER, size INTEGER, filled INTEGER, pulled INTEGER,"
            " absorbed INTEGER, tests INTEGER, dist_ticks INTEGER, ref REAL, away REAL, through REAL, m1 REAL, m5 REAL,"
            " done INTEGER)"
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS events_day ON events (day, sym)")
        self.db.commit()
        self._uid: dict[int, int] = {}  # engine event id -> row

    def save(self, ev: Event, final: bool) -> None:
        row = [getattr(ev, c) for c in COLUMNS]
        uid = self._uid.get(ev.id)
        if uid is None:
            cur = self.db.execute(
                f"INSERT INTO events ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                row,
            )
            uid = int(cur.lastrowid or 0)
            self._uid[ev.id] = uid
        else:
            self.db.execute(
                f"UPDATE events SET {', '.join(f'{c} = ?' for c in COLUMNS)} WHERE uid = ?",
                [*row, uid],
            )
        if final:
            self._uid.pop(ev.id, None)
        self.db.commit()

    def day_events(self, day: str, sym: str | None = None) -> list[dict[str, Any]]:
        q = f"SELECT uid, {', '.join(COLUMNS)} FROM events WHERE day = ?"
        args: list[Any] = [day]
        if sym:
            q += " AND sym = ?"
            args.append(sym)
        cur = self.db.execute(q + " ORDER BY t", args)
        names = ["uid", *COLUMNS]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def stats(self, sym_root: str = "") -> list[dict[str, Any]]:
        """For each kind of event and side, over everything remembered: how often price then
        went away from the level (bounced) vs. through it, and the average 5-minute move."""
        cur = self.db.execute(
            "SELECT kind, side, COUNT(*), AVG(CASE WHEN m5 > 0 THEN 1.0 ELSE 0 END), AVG(m5), AVG(away), AVG(through),"
            " COUNT(DISTINCT day) FROM events WHERE done = 1 AND sym LIKE ? GROUP BY kind, side",
            [f"{sym_root}%"],
        )
        return [
            {
                "kind": k,
                "side": s,
                "n": n,
                "awayPct": round(p * 100, 1),
                "m5": round(m or 0, 2),
                "away": round(a or 0, 2),
                "through": round(th or 0, 2),
                "days": d,
            }
            for k, s, n, p, m, a, th, d in cur.fetchall()
        ]
