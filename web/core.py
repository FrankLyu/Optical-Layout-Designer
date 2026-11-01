"""Everything the web pages need from the desktop code: layouts (read-only),
the 2D drawing and the power log.

Layout files are never written. The logbook is shared with the desktop app:
readings and pictures go in through the same Logbook API, so they are the
same entries the desktop makes.

Qt (used for the 2D drawing and to build the layout the way the desktop does)
must run on the main thread: run_qt() hands work to it. The server runs in
another thread (see server.py)."""

from __future__ import annotations

import json
import queue
import sys
import threading
from concurrent.futures import Future
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from optolayout.logbook import Logbook, format_power, logbook_path_for  # noqa: E402
from optolayout.model import Layout  # noqa: E402

WEB = Path(__file__).resolve().parent
# without a config.json: this PC only, since there is no password (see config.example.json)
DEFAULT_CONFIG = {"folders": ["../examples"], "password": "", "host": "127.0.0.1", "port": 8000}


def load_config(path: Path | None = None) -> dict:
    """web/config.json; folders are relative to the web folder, so the whole
    project folder can be moved to another PC."""
    path = path or WEB / "config.json"
    cfg = dict(DEFAULT_CONFIG)
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    base = path.parent
    cfg["folders"] = [(base / f).resolve() if not Path(f).is_absolute() else Path(f) for f in cfg["folders"]]
    return cfg


# ---- the Qt main thread ------------------------------------------------------------

_jobs: queue.Queue = queue.Queue()
_qt_running = False
_direct_lock = threading.RLock()


def run_qt(fn, *args, timeout: float = 120):
    """Run fn on the Qt main thread and return its result. Without a running
    Qt loop (tests), run it here, one at a time."""
    on_main = threading.current_thread() is threading.main_thread()
    if not _qt_running and not on_main:  # Qt from another thread crashes: nobody serves the queue now
        raise RuntimeError("the web server's Qt loop is not running")
    if on_main:
        with _direct_lock:
            ensure_qapp()
            return fn(*args)
    fut: Future = Future()
    _jobs.put((fn, args, fut))
    return fut.result(timeout)


def ensure_qapp():
    import os
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:  # inside the desktop app: use its own
        return app
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if os.name == "nt":  # offscreen Qt on Windows finds no fonts by itself: text would draw as empty boxes
        os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
    return QApplication([])


def serve_jobs() -> None:
    """Run the queued run_qt() jobs (call on the Qt main thread)."""
    while True:
        try:
            fn, args, fut = _jobs.get_nowait()
        except queue.Empty:
            return
        if fut.set_running_or_notify_cancel():
            try:
                fut.set_result(fn(*args))
            except BaseException as e:  # noqa: BLE001 - handed back to the request
                fut.set_exception(e)


def set_qt_served(on: bool) -> None:
    """A Qt event loop on the main thread calls serve_jobs() (the desktop app does, see embed.py)."""
    global _qt_running
    _qt_running = on


def qt_loop(should_stop) -> None:
    """Serve run_qt() jobs on this (main) thread until should_stop() is true."""
    global _qt_running
    from PySide6.QtCore import QTimer
    app = ensure_qapp()

    def work():
        if should_stop():
            app.quit()
            return
        serve_jobs()

    timer = QTimer()
    timer.timeout.connect(work)
    timer.start(15)
    _qt_running = True
    try:
        app.exec()
    finally:
        _qt_running = False


def with_qt_loop(fn):
    """Run fn on another thread while this (main) thread serves Qt, as the
    server does; returns fn's result (for tests and scripts)."""
    global _qt_running
    box = {}

    def body():
        try:
            box["result"] = fn()
        except BaseException as e:  # noqa: BLE001 - re-raised below
            box["error"] = e

    _qt_running = True  # requests from the thread queue their Qt work from the start
    t = threading.Thread(target=body)
    t.start()
    qt_loop(lambda: not t.is_alive())
    t.join()
    if "error" in box:
        raise box["error"]
    return box.get("result")


# ---- layouts --------------------------------------------------------------------------

def is_layout_file(p: Path) -> bool:
    from optolayout.switcher import is_layout_file as check
    return check(p)


def list_layouts(folders: list[Path]) -> list[dict]:
    out = []
    for fi, folder in enumerate(folders):
        if not folder.is_dir():
            continue
        for p in sorted(folder.glob("*.json"), key=lambda p: p.name.lower()):
            if not is_layout_file(p):
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            pts = [m for m in d.get("measurement_points", []) if not m.get("archived")]
            out.append({"folder": folder.name, "fi": fi, "name": p.name, "stem": p.stem,
                        "title": d.get("table", {}).get("name", ""), "points": len(pts),
                        "has_log": logbook_path_for(p).exists(), "modified": p.stat().st_mtime})
    return out


def layout_path(folders: list[Path], fi: int, name: str) -> Path | None:
    """The layout file for a URL, only if it is a layout listed in a configured folder."""
    if not 0 <= fi < len(folders) or "/" in name or "\\" in name or not name.endswith(".json"):
        return None
    p = folders[fi] / name
    return p if p.is_file() and is_layout_file(p) else None


def log_stamp(path: Path) -> str:
    lb = logbook_path_for(path)
    parts = [lb, lb.with_name(lb.name + "-journal"), lb.with_name(lb.name + "-wal")]
    return "-".join(str(q.stat().st_mtime_ns) if q.exists() else "0" for q in parts)


def stamp(path: Path) -> str:
    """Changes when the layout file or its power log changes."""
    return f"{path.stat().st_mtime_ns}-{log_stamp(path)}"


class Loaded:
    """A layout built the way the desktop builds it (schematic synced into a
    LayoutScene). Only ever read."""

    def __init__(self, path: Path):
        from optolayout.scene import LayoutScene
        self.path = path
        self.mtime = path.stat().st_mtime_ns
        lay = Layout.load(path)
        if lay.components and not lay.schematic.elements:
            lay.schematic_from_layout()  # older file, as the desktop does on opening
        self.scene = LayoutScene()
        self.scene.set_layout(lay)
        self.scene.sync_from_schematic()
        self.scene.show_coords = True
        self.layout = self.scene.layout
        self.renders: dict = {}  # (kind, stamp) -> bytes / data


_loaded: dict[Path, Loaded] = {}


def loaded(path: Path) -> Loaded:
    """Qt thread only. Re-read when the file has changed on disk."""
    cur = _loaded.get(path)
    if cur is None or cur.mtime != path.stat().st_mtime_ns:
        cur = _loaded[path] = Loaded(path)
    return cur


def open_log(path: Path) -> Logbook:
    """The layout's power log. Opening it never writes; a log that doesn't
    exist yet is created by the first reading."""
    return Logbook(logbook_path_for(path))


def _latest(path: Path) -> dict:
    lb = open_log(path)
    try:
        return lb.latest_two()
    finally:
        lb.close()


def point_info(lay: Layout, pt, latest: dict) -> dict:
    rec = latest.get(pt.id)
    last, prev = (rec[0], rec[1]) if rec else (None, None)
    pct = (last.power_mw - prev.power_mw) / prev.power_mw * 100 if last and prev and prev.power_mw else None
    eff = lay.coupling_efficiency(pt, latest)
    return {"id": pt.id, "label": pt.label, "name": lay.point_name(pt.id), "archived": pt.archived,
            "power_mw": last.power_mw if last else None, "power": format_power(last.power_mw) if last else "",
            "when": last.measured_at[:16].replace("T", " ") if last else "",
            "change_pct": round(pct, 1) if pct is not None else None,
            "coupled_pct": round(eff * 100) if eff is not None else None,
            "fiber": bool(pt.part_id)}


def _src_rect(scene):
    from optolayout.app import export_rect
    return export_rect(scene)


def render_2d(path: Path) -> dict:
    """Qt thread. The board drawn as the desktop exports it (SVG, mm units),
    plus where each measurement point and its callout sit in that drawing."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize
    from PySide6.QtGui import QPainter
    from PySide6.QtSvg import QSvgGenerator
    ld = loaded(path)
    key = ("2d", stamp(path))
    if key in ld.renders:
        return ld.renders[key]
    sc = ld.scene
    sc.set_latest(_latest(path))
    sc.clearSelection()
    sc.show_ratsnest = False
    sc.begin_export()
    try:
        src = _src_rect(sc)
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        gen = QSvgGenerator()
        gen.setOutputDevice(buf)
        gen.setTitle(sc.layout.table.name or "Optical layout")
        gen.setSize(QSize(int(src.width()), int(src.height())))
        gen.setViewBox(QRectF(0, 0, src.width(), src.height()))
        gen.setResolution(int(25.4))  # 1 SVG unit = 1 mm
        p = QPainter(gen)
        sc.render(p, QRectF(0, 0, src.width(), src.height()), src)
        p.end()
        svg = bytes(QByteArray(buf.data()))
        latest = sc.latest
        pts = []
        for pid, it in sc.point_items.items():
            pt = sc.layout.points[pid]
            if pt.archived:
                continue
            r = it.sceneBoundingRect()
            info = point_info(sc.layout, pt, latest)
            info.update(x=it.pos().x() - src.left(), y=it.pos().y() - src.top(),
                        box=[r.left() - src.left(), r.top() - src.top(), r.width(), r.height()])
            pts.append(info)
    finally:
        sc.end_export()
        sc.show_ratsnest = True
    out = {"svg": svg, "width": src.width(), "height": src.height(), "points": pts}
    ld.renders = {key: out}  # keep only the newest
    return out


def render_png(path: Path, width_px: int = 1400) -> bytes:
    """Qt thread. The board as a PNG (the lab sheet's picture)."""
    from optolayout.app import render_scene_image
    from optolayout.labsheet import png_bytes
    ld = loaded(path)
    ld.scene.set_latest(_latest(path))
    return png_bytes(render_scene_image(ld.scene, width_px))


def layout_info(path: Path) -> dict:
    """Qt thread. Title, board size, points with their latest readings."""
    ld = loaded(path)
    latest = _latest(path)
    lay = ld.layout
    pts = sorted((point_info(lay, p, latest) for p in lay.points.values() if not p.archived),
                 key=lambda d: _label_key(d["label"]))
    t = lay.table
    return {"title": t.name or path.stem, "file": path.name, "width": t.width, "height": t.height,
            "style": t.style, "points": pts, "stamp": stamp(path), "has_log": logbook_path_for(path).exists()}


def _label_key(label: str):
    digits = "".join(ch for ch in label if ch.isdigit())
    return (int(digits) if digits else 1 << 30, label)


# ---- power log ---------------------------------------------------------------------------

def point_log(path: Path, pid: str) -> dict | None:
    lay = run_qt(lambda: loaded(path).layout)
    pt = lay.points.get(pid)
    if pt is None:
        return None
    lb = open_log(path)
    try:
        latest = lb.latest_two()
        hist = lb.power_history(pid)
        pics = lb.pictures(pid)
    finally:
        lb.close()
    b = lay.beams.get(pt.beam_id or "")
    part = lay.components.get(pt.part_id or "")
    from optolayout.symbols import SYMBOLS
    name = lambda c: c.label or SYMBOLS[c.type].name  # noqa: E731
    if b and b.source in lay.components and b.target in lay.components:
        desc = f"on beam {name(lay.components[b.source])} → {name(lay.components[b.target])}"
    elif part is not None:
        desc = f"out of the fiber of {name(part)} (power after fiber coupling)"
    else:
        desc = "not on a beam"
    info = point_info(lay, pt, latest)
    info.update(desc=desc, layout_title=lay.table.name or path.stem,
                history=[{"id": r.id, "when": r.measured_at[:16].replace("T", " "), "iso": r.measured_at,
                          "power_mw": r.power_mw, "power": format_power(r.power_mw), "unit": r.unit,
                          "meter": r.instrument or "", "notes": r.notes or ""} for r in hist],
                pictures=[{"id": p.id, "when": p.taken_at[:16].replace("T", " "), "notes": p.notes or "",
                           "filename": p.filename, "mime": p.mime} for p in reversed(pics)])
    return info


def add_reading(path: Path, pid: str, value: float, unit: str, meter: str, notes: str) -> int:
    """A reading, exactly as the desktop log window adds it."""
    lay = run_qt(lambda: loaded(path).layout)
    pt = lay.points[pid]
    lb = open_log(path)
    try:
        lb.register_point(pt.id, pt.label)
        return lb.add_power(pt.id, value, unit, instrument=meter.strip(), notes=notes.strip())
    finally:
        lb.close()


def add_picture(path: Path, pid: str, data: bytes, filename: str, mime: str, notes: str) -> int:
    lay = run_qt(lambda: loaded(path).layout)
    pt = lay.points[pid]
    lb = open_log(path)
    try:
        lb.register_point(pt.id, pt.label)
        return lb.add_picture(pt.id, data, filename, mime, notes=notes.strip())
    finally:
        lb.close()


def picture(path: Path, pid: str, pic_id: int) -> tuple[bytes, str] | None:
    lb = open_log(path)
    try:
        for p in lb.pictures(pid):
            if p.id == pic_id:
                return lb.picture_data(pic_id), p.mime
        return None
    finally:
        lb.close()


def lab_sheet_html(path: Path, points: list[str] | None, include_log: bool, history: int,
                   include_picture: bool) -> str:
    """The lab sheet (as the desktop makes it), with the picture embedded."""
    import base64
    from dataclasses import replace
    from datetime import datetime
    from optolayout.labsheet import sheet_html, sheet_table
    lay = run_qt(lambda: loaded(path).layout)
    s = replace(lay.lab_sheet, include_log=include_log, history=max(1, history), include_picture=include_picture)
    if points is not None:
        s.points = points
    lb = open_log(path)
    try:
        headers, rows = sheet_table(lay, lb, s)
    finally:
        lb.close()
    src = size = None
    if include_picture:
        png = run_qt(render_png, path)
        from PySide6.QtGui import QImage
        img = QImage.fromData(png)
        k = min(640 / max(img.width(), 1), 560 / max(img.height(), 1))
        size = (round(img.width() * k), round(img.height() * k))
        src = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return sheet_html(f"Lab sheet: {path.name}", f"Layout file {path.name} · {datetime.now():%Y-%m-%d %H:%M}",
                      headers, rows, src, size)

