"""Append-only SQLite logbook for optical power readings and beam pictures.

One logbook file sits next to each layout: ``board.json`` ->
``board.logbook.sqlite``. Records are keyed by measurement-point id, so
moving parts or deleting beams never touches history. Pictures are stored
inside the database (BLOBs) so the whole log is one file to back up.

Nothing is ever updated or erased. A wrong entry is corrected by adding a new
one, optionally marked ``supersedes`` the old id; the old row stays. Deleting
a reading or picture in the app hides it: the delete (and any later restore)
is itself a row in ``deletions``, so a deleted entry can always be brought back.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS points (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_label TEXT
);
CREATE TABLE IF NOT EXISTS power (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    point_id TEXT NOT NULL REFERENCES points(id),
    measured_at TEXT NOT NULL,          -- ISO local time, user-editable
    power_mw REAL NOT NULL,             -- always stored in mW
    unit TEXT NOT NULL DEFAULT 'mW',    -- unit it was entered in
    wavelength_nm REAL,
    instrument TEXT,
    notes TEXT,
    supersedes INTEGER REFERENCES power(id),
    created_at TEXT NOT NULL            -- when the row was written
);
CREATE TABLE IF NOT EXISTS pictures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    point_id TEXT NOT NULL REFERENCES points(id),
    taken_at TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime TEXT NOT NULL,
    data BLOB NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deletions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                 -- 'power' or 'picture'
    record_id INTEGER NOT NULL,
    deleted INTEGER NOT NULL,           -- 1 = deleted, 0 = restored; the latest row wins
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS power_point ON power(point_id, measured_at);
CREATE INDEX IF NOT EXISTS pictures_point ON pictures(point_id, taken_at);
CREATE TRIGGER IF NOT EXISTS power_no_update BEFORE UPDATE ON power
    BEGIN SELECT RAISE(ABORT, 'logbook is append-only'); END;
CREATE TRIGGER IF NOT EXISTS power_no_delete BEFORE DELETE ON power
    BEGIN SELECT RAISE(ABORT, 'logbook is append-only'); END;
CREATE TRIGGER IF NOT EXISTS pictures_no_update BEFORE UPDATE ON pictures
    BEGIN SELECT RAISE(ABORT, 'logbook is append-only'); END;
CREATE TRIGGER IF NOT EXISTS pictures_no_delete BEFORE DELETE ON pictures
    BEGIN SELECT RAISE(ABORT, 'logbook is append-only'); END;
"""

UNITS_TO_MW = {"W": 1000.0, "mW": 1.0, "µW": 1e-3, "nW": 1e-6}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def format_power(mw: float | None) -> str:
    if mw is None:
        return "—"
    a = abs(mw)
    if a >= 1000:
        return f"{mw / 1000:.3g} W"
    if a >= 1:
        return f"{mw:.3g} mW"
    if a >= 1e-3:
        return f"{mw * 1e3:.3g} µW"
    return f"{mw * 1e6:.3g} nW"


@dataclass
class PowerRecord:
    id: int
    point_id: str
    measured_at: str
    power_mw: float
    unit: str
    wavelength_nm: float | None
    instrument: str | None
    notes: str | None
    supersedes: int | None
    created_at: str


@dataclass
class PictureRecord:
    id: int
    point_id: str
    taken_at: str
    filename: str
    mime: str
    notes: str | None
    created_at: str


def logbook_path_for(layout_path: str | Path) -> Path:
    p = Path(layout_path)
    return p.with_name(p.stem + ".logbook.sqlite")


_SCHEMA_OBJECTS = {"points", "power", "pictures", "deletions", "power_point", "pictures_point", "power_no_update",
                   "power_no_delete", "pictures_no_update", "pictures_no_delete"}


class Logbook:
    """Opening a logbook never writes to it (someone else's log in a shared
    folder stays untouched). A logbook that doesn't exist yet lives in memory
    until the first reading, picture or delete, which creates the file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._pending: dict[str, str] = {}  # point id -> label, written with the next entry
        self.in_memory = not self.path.exists()
        if self.in_memory:
            self.db = sqlite3.connect(":memory:")
            self.db.executescript(SCHEMA)
            self._have = set(_SCHEMA_OBJECTS)
        else:
            self._open_file()
        # an older log without some tables is brought up to date at the first write

    def _open_file(self) -> None:
        # the desktop app and the web server may both write: wait for the other's short write
        self.db = sqlite3.connect(str(self.path), timeout=15)
        self._have = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master")}
        self._data_version = self.db.execute("PRAGMA data_version").fetchone()[0]
        self.in_memory = False

    def close(self) -> None:
        self.db.close()

    def changed_on_disk(self) -> bool:
        """Has another program (the web server, another PC) written to this log
        since we last looked? Only reads."""
        if self.in_memory:
            if not self.path.exists():
                return False
            self.db.close()  # created elsewhere: use it (ours held only the empty tables)
            self._open_file()
            return True
        v = self.db.execute("PRAGMA data_version").fetchone()[0]
        changed, self._data_version = v != self._data_version, v
        return changed

    def _before_write(self) -> None:
        """Create the file on the first entry, and record the point labels."""
        if self.in_memory:  # nothing but empty tables in memory: start the file (or use one made meanwhile)
            self.db.close()
            self._open_file()
        if not _SCHEMA_OBJECTS <= self._have:
            self.db.executescript(SCHEMA)
            self._have = set(_SCHEMA_OBJECTS)
        for point_id, label in self._pending.items():
            cur = self.db.execute("SELECT label FROM points WHERE id=?", (point_id,))
            if cur.fetchone() is None:
                self.db.execute("INSERT INTO points(id, label, first_seen, last_label) VALUES (?,?,?,?)",
                                (point_id, label, now_iso(), label))
            else:
                self.db.execute("UPDATE points SET last_label=? WHERE id=?", (label, point_id))
        self._pending.clear()

    # ---- points -------------------------------------------------------------
    def register_point(self, point_id: str, label: str) -> None:
        """Remember a point's id/label so its history is self-describing even
        if the layout file is lost. Written with the next entry, not now."""
        self._pending[point_id] = label

    def known_points(self) -> list[tuple[str, str]]:
        rows = dict(self.db.execute("SELECT id, COALESCE(last_label, label) FROM points ORDER BY first_seen"))
        rows.update(self._pending)
        return list(rows.items())

    # ---- power ---------------------------------------------------------------
    def add_power(self, point_id: str, value: float, unit: str = "mW", *, measured_at: str | None = None,
                  wavelength_nm: float | None = None, instrument: str = "", notes: str = "",
                  supersedes: int | None = None) -> int:
        if unit not in UNITS_TO_MW:
            raise ValueError(f"unknown unit {unit!r}")
        self._before_write()
        cur = self.db.execute(
            "INSERT INTO power(point_id, measured_at, power_mw, unit, wavelength_nm, instrument, notes,"
            " supersedes, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (point_id, measured_at or now_iso(), value * UNITS_TO_MW[unit], unit, wavelength_nm,
             instrument or None, notes or None, supersedes, now_iso()))
        self.db.commit()
        return cur.lastrowid

    def power_history(self, point_id: str, include_deleted: bool = False) -> list[PowerRecord]:
        rows = self.db.execute(
            "SELECT id, point_id, measured_at, power_mw, unit, wavelength_nm, instrument, notes, supersedes,"
            " created_at FROM power WHERE point_id=? ORDER BY measured_at, id", (point_id,))
        gone = set() if include_deleted else self.deleted_ids("power")
        return [PowerRecord(*r) for r in rows if r[0] not in gone]

    # ---- deleting (hiding) entries ------------------------------------------------
    def set_deleted(self, kind: str, record_ids, deleted: bool = True) -> None:
        """Delete (hide) or restore readings ('power') or pictures ('picture')."""
        if kind not in ("power", "picture"):
            raise ValueError(kind)
        self._before_write()
        self.db.executemany("INSERT INTO deletions(kind, record_id, deleted, at) VALUES (?,?,?,?)",
                            [(kind, int(r), int(deleted), now_iso()) for r in record_ids])
        self.db.commit()

    def deleted_ids(self, kind: str) -> set[int]:
        state: dict[int, int] = {}
        if "deletions" not in self._have:  # older log, nothing deleted yet
            return set()
        for rid, d in self.db.execute("SELECT record_id, deleted FROM deletions WHERE kind=? ORDER BY id", (kind,)):
            state[rid] = d
        return {rid for rid, d in state.items() if d}

    def latest_two(self) -> dict[str, tuple[PowerRecord, PowerRecord | None]]:
        """For every point: (latest valid reading, the one before it)."""
        out: dict[str, list[PowerRecord]] = {}
        rows = self.db.execute(
            "SELECT id, point_id, measured_at, power_mw, unit, wavelength_nm, instrument, notes, supersedes,"
            " created_at FROM power ORDER BY measured_at, id")
        gone = self.deleted_ids("power")
        recs = [PowerRecord(*r) for r in rows if r[0] not in gone]
        superseded = {r.supersedes for r in recs if r.supersedes}
        for r in recs:
            if r.id not in superseded:
                out.setdefault(r.point_id, []).append(r)
        return {pid: (v[-1], v[-2] if len(v) > 1 else None) for pid, v in out.items()}

    # ---- pictures -------------------------------------------------------------
    def add_picture(self, point_id: str, data: bytes, filename: str, mime: str = "image/png", *,
                    taken_at: str | None = None, notes: str = "") -> int:
        self._before_write()
        cur = self.db.execute(
            "INSERT INTO pictures(point_id, taken_at, filename, mime, data, notes, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (point_id, taken_at or now_iso(), filename, mime, sqlite3.Binary(data), notes or None, now_iso()))
        self.db.commit()
        return cur.lastrowid

    def pictures(self, point_id: str, include_deleted: bool = False) -> list[PictureRecord]:
        rows = self.db.execute(
            "SELECT id, point_id, taken_at, filename, mime, notes, created_at FROM pictures"
            " WHERE point_id=? ORDER BY taken_at, id", (point_id,))
        gone = set() if include_deleted else self.deleted_ids("picture")
        return [PictureRecord(*r) for r in rows if r[0] not in gone]

    def picture_data(self, picture_id: int) -> bytes:
        return self.db.execute("SELECT data FROM pictures WHERE id=?", (picture_id,)).fetchone()[0]

    def picture_counts(self) -> dict[str, int]:
        gone = self.deleted_ids("picture")
        out: dict[str, int] = {}
        for rid, pid in self.db.execute("SELECT id, point_id FROM pictures"):
            if rid not in gone:
                out[pid] = out.get(pid, 0) + 1
        return out
