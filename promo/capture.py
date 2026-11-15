"""Capture promo footage of the Optical Layout Designer.

Runs the app in-process on a COPY of 421nm_system/olego_onDy2.json (and its
power log) in promo/work/, drives each scene programmatically and grabs the
main window frame by frame (30 fps, deterministic: every frame is rendered
before it is taken, so motion is smooth whatever the PC's speed). Frames are
piped straight into ffmpeg (libx264, yuv420p, crf 18) -> promo/out/<scene>.mp4;
one still per scene goes to promo/out/stills/. --frames also keeps the PNGs
in promo/out/<scene>/frame_%05d.png.

    py -3.13 promo/capture.py                 # all scenes
    py -3.13 promo/capture.py live3d power_log
    py -3.13 promo/capture.py --frames schematic

The app source is not changed, and the app's settings (QSettings) are put
back exactly as they were when the script ends.
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QPoint, QPointF, QRectF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QMouseEvent, QPainter, QPainterPath, QPen, QPolygonF  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton, QTableWidget, QToolBar  # noqa: E402

SRC_JSON = ROOT / "421nm_system" / "olego_onDy2.json"
SRC_LOG = ROOT / "421nm_system" / "olego_onDy2.logbook.sqlite"
WORK = ROOT / "promo" / "work"
OUT = ROOT / "promo" / "out"
FPS = 30
OUT_W, OUT_H = 1920, 1080
EXTRA = 1.5  # seconds captured beyond each scene's planned length, for trimming

# planned clip lengths (s); each is captured EXTRA longer
PLAN = {"title_orbit": 3, "schematic": 8, "layout_drag": 7.5, "live3d": 7, "power_log": 5, "labsheet": 9, "dy1_layout": 2.5}


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    link = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
    if link.exists():
        return str(link)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg not found: winget install Gyan.FFmpeg")


def ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_pt(a: QPointF, b: QPointF, t: float) -> QPointF:
    return QPointF(lerp(a.x(), b.x(), t), lerp(a.y(), b.y(), t))


def pump(n: int = 2):
    for _ in range(n):
        QApplication.processEvents(QEventLoop.AllEvents, 50)


# ---- recorder ------------------------------------------------------------------------------

class Recorder:
    """Grabs the main window (plus the 3D view and open dialogs composited in),
    draws a synthetic cursor / click ripple / key badge, and feeds ffmpeg."""

    def __init__(self, win, name: str, ffmpeg: str, keep_frames: bool, still_at: float = 0.6,
                 out_name: str | None = None):
        self.win, self.name = win, name
        self.n = 0
        self.total = int(round((PLAN[name] + EXTRA) * FPS))
        self.still_frame = int(self.total * still_at)
        self.cursor: QPointF | None = None
        self.pressed = False
        self.ripple_at: int | None = None
        self.badge: str | None = None
        self.dialogs = []
        self.frames_dir = OUT / name if keep_frames else None
        if self.frames_dir:
            shutil.rmtree(self.frames_dir, ignore_errors=True)
            self.frames_dir.mkdir(parents=True)
        self.out_name = out_name or name
        self.mp4 = OUT / f"{self.out_name}.mp4"
        self.proc = subprocess.Popen(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}",
             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(self.mp4)], stdin=subprocess.PIPE)

    # where things are, in main-window coordinates (logical px)
    def at_widget(self, w, local: QPointF | None = None) -> QPointF:
        local = local if local is not None else QPointF(w.width() / 2, w.height() / 2)
        return QPointF(w.mapTo(self.win, local.toPoint()))

    def at_scene(self, view, scene_pt: QPointF) -> QPointF:
        return QPointF(view.viewport().mapTo(self.win, view.mapFromScene(scene_pt)))

    def at_global(self, gp: QPoint) -> QPointF:
        return QPointF(self.win.mapFromGlobal(gp))

    def click(self):
        self.ripple_at = self.n

    def place(self, d, x=None, y=None):
        """Show dialog d in the frames at window position (x, y) (None: centred), shrunk to fit.
        Where Windows puts the real window doesn't matter: frames use this position."""
        d.show()
        pump(6)
        sz = d.size()
        W, H = self.win.width(), self.win.height()
        if sz.width() > W - 60 or sz.height() > H - 110:
            d.resize(min(sz.width(), W - 60), min(sz.height(), H - 110))
            pump(6)
            sz = d.size()
        x = (W - sz.width()) / 2 if x is None else (W - sz.width() + x if x < 0 else x)
        y = (H - sz.height()) / 2 + 16 if y is None else y
        d._promo_pos = QPointF(x, y)
        if d not in self.dialogs:
            self.dialogs.append(d)
        print(f"  {type(d).__name__} {sz.width()}x{sz.height()} at {x:.0f},{y:.0f}", flush=True)

    def at_dialog(self, d, w=None, local: QPointF | None = None) -> QPointF:
        w = w or d
        local = local if local is not None else QPointF(w.width() / 2, w.height() / 2)
        return d._promo_pos + QPointF(w.mapTo(d, local.toPoint()) if w is not d else local)

    # ---- compositing
    def compose(self) -> QImage:
        win = self.win
        pump(3)
        pm = win.grab()
        dpr = pm.devicePixelRatio()
        img = pm.toImage().convertToFormat(QImage.Format_RGB888)
        img.setDevicePixelRatio(1.0)  # paint in device pixels; p.scale(dpr) below gives window coordinates
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        v3 = win.view3d
        if win.tabs.currentIndex() == 2 and v3:
            inter = v3.plotter.interactor
            shot = v3.plotter.screenshot(return_img=True)
            h, w = shot.shape[:2]
            buf = shot.copy(order="C")
            q = QImage(buf.data, w, h, 3 * w, QImage.Format_RGB888).copy()
            tl = inter.mapTo(win, QPoint(0, 0))
            # the native VTK window shows up in grab() at a wrong size: paint over its area, then the
            # real render, then the status bar again
            vt = v3.mapTo(win, QPoint(0, 0))
            bg = win.palette().window().color()
            p.fillRect(QRectF(vt.x() * dpr, tl.y() * dpr, v3.width() * dpr, (v3.height() - (tl.y() - vt.y())) * dpr), bg)
            p.drawImage(QRectF(tl.x() * dpr, tl.y() * dpr, inter.width() * dpr, inter.height() * dpr), q)
            sb = win.statusBar()
            st = sb.mapTo(win, QPoint(0, 0))
            sbp = sb.grab()
            p.drawPixmap(QRectF(st.x() * dpr, st.y() * dpr, sb.width() * dpr, sb.height() * dpr), sbp,
                         QRectF(0, 0, sbp.width(), sbp.height()))
        p.scale(dpr, dpr)  # from here on: logical window coordinates
        for d in self.dialogs:
            if d.isVisible() or getattr(d, "_promo_plain", False):
                self._draw_dialog(p, d)
        if self.badge:
            self._draw_badge(p, self.badge)
        if self.ripple_at is not None and self.n - self.ripple_at < 14:
            k = (self.n - self.ripple_at) / 14
            if self.cursor is not None:
                p.setPen(QPen(QColor(31, 111, 209, int(220 * (1 - k))), 3))
                p.setBrush(QColor(31, 111, 209, int(70 * (1 - k))))
                p.drawEllipse(self.cursor, 6 + 22 * k, 6 + 22 * k)
        if self.cursor is not None:
            self._draw_cursor(p, self.cursor)
        p.end()
        if img.width() != OUT_W or img.height() != OUT_H:
            img = img.scaled(OUT_W, OUT_H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        return img

    def _draw_dialog(self, p: QPainter, d):
        tl = d._promo_pos
        if getattr(d, "_promo_plain", False):  # a drop-down list: no title bar, a small shadow
            pm = d.grab()
            sz = d.size()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 40))
            p.drawRect(QRectF(tl.x() + 2, tl.y() + 3, sz.width(), sz.height()))
            p.drawPixmap(QRectF(tl.x(), tl.y(), sz.width(), sz.height()), pm, QRectF(0, 0, pm.width(), pm.height()))
            return
        bar = 32
        sz = d.size()  # (the BOM dialog has a widget called .height)
        r = QRectF(tl.x(), tl.y() - bar, sz.width(), sz.height() + bar)
        for i in range(10, 0, -1):  # soft shadow
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 6))
            p.drawRoundedRect(r.adjusted(-i, -i + 4, i, i + 4), 8 + i, 8 + i)
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        p.save()
        p.setClipPath(path)
        p.fillRect(r, QColor("#f3f3f3"))
        p.setPen(QColor("#1b1b1b"))
        f = QFont("Segoe UI")
        f.setPixelSize(12)
        p.setFont(f)
        p.drawText(QRectF(r.left() + 14, r.top(), r.width() - 60, bar), Qt.AlignVCenter | Qt.AlignLeft, d.windowTitle())
        p.drawText(QRectF(r.right() - 46, r.top(), 46, bar), Qt.AlignCenter, "✕")
        pm = d.grab()  # source rect in device pixels
        p.drawPixmap(QRectF(tl.x(), tl.y(), sz.width(), sz.height()), pm, QRectF(0, 0, pm.width(), pm.height()))
        p.restore()
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 8, 8)

    def _draw_badge(self, p: QPainter, text: str):
        f = QFont("Segoe UI")
        f.setPixelSize(22)
        f.setBold(True)
        p.setFont(f)
        keys = text.split("+")
        widths = [max(44, p.fontMetrics().horizontalAdvance(k) + 26) for k in keys]
        plus = 26
        total = sum(widths) + plus * (len(keys) - 1)
        x = self.win.width() / 2 - total / 2
        y = self.win.height() - 110
        bg = QRectF(x - 16, y - 12, total + 32, 64)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 22, 28, 200))
        p.drawRoundedRect(bg, 14, 14)
        for i, k in enumerate(keys):
            kr = QRectF(x, y, widths[i], 40)
            p.setBrush(QColor("#fafafa"))
            p.setPen(QPen(QColor("#9aa0a6"), 1.2))
            p.drawRoundedRect(kr.adjusted(0, 3, 0, 3), 7, 7)
            p.drawRoundedRect(kr, 7, 7)
            p.setPen(QColor("#111111"))
            p.drawText(kr, Qt.AlignCenter, k)
            x += widths[i]
            if i < len(keys) - 1:
                p.setPen(QColor("#ffffff"))
                p.drawText(QRectF(x, y, plus, 40), Qt.AlignCenter, "+")
                x += plus

    def _draw_cursor(self, p: QPainter, at: QPointF):
        s = 1.25
        pts = [(0, 0), (0, 17), (4, 13), (7, 20), (10, 19), (7, 12), (12.5, 12)]
        poly = QPolygonF([QPointF(at.x() + x * s, at.y() + y * s) for x, y in pts])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawPolygon(poly.translated(1.5, 2))
        p.setPen(QPen(QColor("#000000"), 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QColor("#ffffff") if not self.pressed else QColor("#dfe9fb"))
        p.drawPolygon(poly)

    # ---- output
    def frame(self):
        img = self.compose()
        self.proc.stdin.write(bytes(img.constBits())[: OUT_W * OUT_H * 3])
        if self.frames_dir:
            img.save(str(self.frames_dir / f"frame_{self.n:05d}.png"))
        if self.n == self.still_frame:
            (OUT / "stills").mkdir(parents=True, exist_ok=True)
            img.save(str(OUT / "stills" / f"{self.out_name}.png"))
        self.n += 1

    def run(self, seconds: float, step=None):
        """Capture `seconds` of frames; step(t in 0..1) is called before each."""
        n = max(1, int(round(seconds * FPS)))
        for i in range(n):
            if step:
                step(i / max(1, n - 1))
            self.frame()

    def move(self, to: QPointF, seconds: float, step=None):
        a = QPointF(self.cursor) if self.cursor is not None else QPointF(to)

        def s(t):
            self.cursor = lerp_pt(a, to, ease(t))
            if step:
                step(t)
        self.run(seconds, s)

    def finish(self):
        while self.n < self.total:  # pad to the planned length + trim room
            self.frame()
        self.proc.stdin.close()
        self.proc.wait()
        for d in self.dialogs:
            d.hide()
        return self.n / FPS


# ---- the demo copy -------------------------------------------------------------------------

def make_work_copy() -> Path:
    """promo/work/olego_onDy2.json (+ its power log), never the real ones."""
    WORK.mkdir(parents=True, exist_ok=True)
    js = WORK / "olego_onDy2.json"
    shutil.copy2(SRC_JSON, js)
    lb = WORK / "olego_onDy2.logbook.sqlite"
    for f in (lb, *(Path(str(lb) + ext) for ext in ("-journal", "-wal", "-shm"))):
        f.unlink(missing_ok=True)
    # an empty log of its own (the lab's real readings stay out of the video); made up front so
    # opening the layout doesn't ask where its log is
    import sqlite3
    from optolayout.logbook import SCHEMA
    db = sqlite3.connect(str(lb))
    db.executescript(SCHEMA)
    db.commit()
    db.close()
    return js


def add_demo_points(win, js: Path) -> dict:
    """Measurement points with a few weeks of made-up readings, in the copy only."""
    lay = win.scene.layout
    first = next((p for p in lay.points.values() if p.beam_id == "k_m1_hwp1"), None)
    pts = {
        "input": first or win.add_point_on("k_m1_hwp1"),
        "pbs": win.add_point_on("k_pbs1_m2"),
        "fc1": win.add_fiber_point("c_fc1"),
        "fc2": win.add_fiber_point("c_fc2"),
        "fc1_in": win.add_point_on("k_qwp1_fc1"),  # just before FC1: the sheet and 3D show the coupling
    }
    series = {"input": [118, 121, 120, 119, 122, 120, 121, 120.4],
              "pbs": [56, 57.5, 58, 57, 58.2, 57.8, 58.4, 58.1],
              # ~69 % coupled into fiber 1; the lab-sheet scene logs 21.6 mW (-40 %) after a beam walk
              "fc1": [34.0, 35.1, 36.2, 35.8, 36.4, 36.0, 35.9, 36.1],
              "fc1_in": [52.0, 52.4, 52.6, 52.1, 52.5, 52.2, 52.3, 52.2],
              "fc2": [21.0, 21.5, 21.4, 22.0, 21.8, 21.6, 21.9, 22.4]}
    # midnight 22 days ago: the last reading is yesterday morning, before anything logged in the video
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=22)
    for key, vals in series.items():
        for i, v in enumerate(vals):
            t = start + timedelta(days=3 * i, hours=9 + (i * 5) % 7, minutes=(i * 17) % 60)
            win.logbook.add_power(pts[key].id, v, "mW", measured_at=t.isoformat(timespec="seconds"),
                                  wavelength_nm=421.0, instrument="Thorlabs S121C")
    sheet = lay.lab_sheet  # names on the lab sheet (and the callouts), all points on it
    sheet.points = [p.id for p in pts.values()]
    sheet.names = {pts["input"].id: "After M1", pts["pbs"].id: "PBS1 out", pts["fc1"].id: "Fiber 1 out", pts["fc1_in"].id: "Fiber 1 in",
                   pts["fc2"].id: "Fiber 2 out"}
    win.scene.set_lab_sheet(sheet)
    win.save_file()
    win.refresh_measurements()
    return {k: p.id for k, p in pts.items()}


def reopen(win, js: Path, base: Path, tab: int):
    """A fresh copy of the demo layout (each scene starts from the same state)."""
    for d in list(win._dialogs.values()):
        d.close()
    win._dialogs.clear()  # a hidden dialog doesn't take itself off the list when closed
    win.scene.undo.setClean()
    shutil.copy2(base, js)
    win.open_path(str(js))
    if win.a_lengths.isChecked():
        win.a_lengths.trigger()
    win.view.ruler = None
    win.tabs.setCurrentIndex(tab)
    win.set_mode("select")
    pump(6)
    win.fit_current()
    pump(4)
    win.statusBar().clearMessage()


def ensure_3d(win, dark=True):
    win.tabs.setCurrentIndex(2)
    pump(4)
    v3 = win.view3d
    v3._timer.stop()
    if dark and v3.theme.currentIndex() != 1:
        v3.theme.blockSignals(True)
        v3.theme.setCurrentIndex(1)
        v3.theme.blockSignals(False)
        v3._styled = False
    v3._framed = False
    v3.rebuild(restyle=True)
    v3._timer.stop()
    pump(4)
    v3.dirty = False
    win.statusBar().clearMessage()
    return v3


class Orbit:
    """Camera as focal point + distance + azimuth + elevation (degrees)."""

    def __init__(self, cam, focal=None):
        f = focal or cam.focal_point
        p = cam.position
        dx, dy, dz = p[0] - f[0], p[1] - f[1], p[2] - f[2]
        self.f = tuple(f)
        self.d0 = cam.distance
        self.d = math.sqrt(dx * dx + dy * dy + dz * dz)
        self.az = math.degrees(math.atan2(dy, dx))
        self.el = math.degrees(math.asin(dz / self.d))

    @staticmethod
    def apply(plotter, f, d, az, el):
        a, e = math.radians(az), math.radians(el)
        pos = (f[0] + d * math.cos(e) * math.cos(a), f[1] + d * math.cos(e) * math.sin(a), f[2] + d * math.sin(e))
        cam = plotter.camera
        cam.focal_point = f
        cam.position = pos
        cam.up = (0, 0, 1)
        plotter.renderer.ResetCameraClippingRange()


def board_orbit(win, v3) -> Orbit:
    """The fitted camera's direction and distance, turning about the board's centre."""
    t = win.scene.layout.table
    return Orbit(v3.plotter.camera, (t.width / 2, -t.height / 2, 20.0))


def world_to_win(rec, v3, xyz) -> QPointF:
    r = v3.plotter.renderer
    r.SetWorldPoint(xyz[0], xyz[1], xyz[2], 1.0)
    r.WorldToDisplay()
    dx, dy, _ = r.GetDisplayPoint()
    W, H = v3.plotter.render_window.GetSize()
    inter = v3.plotter.interactor
    kx, ky = W / max(1, inter.width()), H / max(1, inter.height())
    return rec.at_widget(inter, QPointF(dx / kx, (H - dy) / ky))


def send_mouse(widget, typ, pos: QPointF, buttons, mods=Qt.NoModifier):
    gp = QPointF(widget.mapToGlobal(pos.toPoint()))
    btn = Qt.LeftButton if typ != QMouseEvent.Type.MouseMove else Qt.NoButton
    QApplication.sendEvent(widget, QMouseEvent(typ, pos, gp, btn, buttons, mods))


# ---- scenes ----------------------------------------------------------------------------------

def scene_title_orbit(win, rec, ctx):
    reopen(win, ctx["js"], ctx["base"], 1)
    v3 = ensure_3d(win)
    o = board_orbit(win, v3)
    total = PLAN["title_orbit"] + EXTRA

    def step(t):  # a quarter turn, gently in and out
        Orbit.apply(v3.plotter, o.f, o.d * lerp(1.04, 0.97, t), o.az + 90 * ease(t) - 20, o.el)
    rec.run(total, step)


def _type(widget, text: str, rec, cps: float = 16.0, step=None):
    """Type text into widget one character at a time, at cps characters per second."""
    from PySide6.QtGui import QKeyEvent
    per = max(1, round(FPS / cps))
    for ch in text:
        for typ in (QKeyEvent.Type.KeyPress, QKeyEvent.Type.KeyRelease):
            QApplication.sendEvent(widget, QKeyEvent(typ, 0, Qt.NoModifier, ch))
        rec.run(per / FPS, step)


def scene_schematic(win, rec, ctx):
    """One mirror: placed from the palette, its exact mount picked in the New-part dialog."""
    from optolayout.model import SchElement, new_id
    from optolayout.schematic import AddElementCmd, NewPartDialog
    reopen(win, ctx["js"], ctx["base"], 0)
    page, sc, view = win.sch_page, win.sch_scene, win.sch_page.view
    view.fitInView(sc.items_rect().united(QRectF(380, 380, 120, 120)).adjusted(-50, -40, 50, 40), Qt.KeepAspectRatio)
    pump(4)
    sc.layout_annotations()
    rec.cursor = rec.at_widget(view, QPointF(view.width() * 0.62, view.height() * 0.55))
    rec.run(0.4)
    kind, x, y = "mirror", 450, 410
    item = next(page.palette.item(r) for r in range(page.palette.count())
                if page.palette.item(r).data(Qt.UserRole) == kind)
    rec.move(rec.at_widget(page.palette.viewport(), QPointF(page.palette.visualItemRect(item).center())), 0.8)
    rec.click()
    page.palette.setCurrentItem(item)
    page._pick(item)
    win.a_select.setChecked(False)
    view._inside = True

    def follow(_t):
        view._cursor = view.mapToScene(view.viewport().mapFrom(win, rec.cursor.toPoint()))
        view.viewport().update()
    rec.run(0.15, follow)
    rec.move(rec.at_scene(view, QPointF(x, y)), 0.9, follow)
    rec.click()
    rec.run(0.15, follow)
    el = SchElement(id=new_id("s"), kind=kind, x=x, y=y, angle=0.0, label=sc.sch.next_label(kind), auto_angle=True)
    dlg = NewPartDialog(el, sc.sch, page)
    vtl = view.mapTo(win, QPoint(0, 0))
    rec.place(dlg, vtl.x() + view.width() * 0.5 - 190, vtl.y() + view.height() * 0.24)
    rec.run(0.6)
    # open the Size / mount list and go down it to the mount wanted
    combo = dlg.part
    rec.move(rec.at_dialog(dlg, combo), 0.6)
    rec.click()
    combo.showPopup()
    pump(6)
    popup = combo.view().window()
    sz = popup.size()
    popup.hide()  # drawn into the frames instead (a real popup grabs the mouse)
    popup.resize(sz)
    cpos = rec.at_dialog(dlg, combo, QPointF(0, combo.height()))
    popup._promo_pos = cpos
    popup._promo_plain = True
    rec.dialogs.append(popup)
    lv = combo.view()
    target = combo.findData("mirror_polaris_half")

    def item_at(i):
        r = lv.visualRect(combo.model().index(i, 0))
        return cpos + QPointF(lv.viewport().mapTo(popup, r.center()))
    rec.run(0.3)
    for i in range(1, target + 1):
        lv.setCurrentIndex(combo.model().index(i, 0))
        rec.move(item_at(i), 0.32)
        rec.run(0.12)
    rec.run(0.3)
    rec.click()
    rec.dialogs.remove(popup)
    combo.setCurrentIndex(target)  # the part number follows (POLARIS-K05S1)
    rec.run(1.0)
    rec.move(rec.at_dialog(dlg, dlg.part_number), 0.5)
    rec.run(0.5)
    rec.move(rec.at_dialog(dlg, dlg.ok), 0.6)
    rec.click()
    rec.run(0.12)
    dlg.accept()
    dlg.hide()
    rec.dialogs.remove(dlg)
    sc.undo.push(AddElementCmd(sc, el))
    page.placed(el.id)
    view._inside = False
    rec.move(rec.at_widget(view, QPointF(view.width() * 0.72, view.height() * 0.75)), 0.9)


def scene_layout_drag(win, rec, ctx):
    """Drag a mirror on the hole grid (beams follow), then drop a power point on a beam."""
    reopen(win, ctx["js"], ctx["base"], 1)
    view, sc = win.view, win.scene
    vp = view.viewport()
    view.fitInView(QRectF(-30, 40, 320, 400), Qt.KeepAspectRatio)
    pump(4)
    sc.layout_annotations()
    m6 = sc.layout.components["c_m6"]
    start = QPointF(m6.x, m6.y)
    end = QPointF(m6.x + 3 * 12.7, m6.y)
    rec.cursor = rec.at_widget(view, QPointF(view.width() * 0.8, view.height() * 0.3))
    rec.run(0.3)
    rec.move(rec.at_scene(view, start), 0.6)
    rec.click()
    rec.pressed = True
    send_mouse(vp, QMouseEvent.Type.MouseButtonPress, QPointF(view.mapFromScene(start)), Qt.LeftButton,
               Qt.AltModifier)

    def drag(t):
        sp = lerp_pt(start, end, ease(t))
        send_mouse(vp, QMouseEvent.Type.MouseMove, QPointF(view.mapFromScene(sp)), Qt.LeftButton, Qt.AltModifier)
        rec.cursor = rec.at_scene(view, sp)
    rec.run(2.0, drag)
    send_mouse(vp, QMouseEvent.Type.MouseButtonRelease, QPointF(view.mapFromScene(end)), Qt.NoButton)
    rec.pressed = False
    sc.free_drag = False
    sc.clearSelection()
    rec.run(0.5)
    # the Power tool, then a click on the beam from PBS2 to the moved mirror
    btn = win.findChild(QToolBar, "tools").widgetForAction(win.a_point)
    rec.move(rec.at_widget(btn), 0.8)
    rec.click()
    rec.badge = "M"
    win.a_point.trigger()
    rec.run(0.4)
    rec.badge = None
    pbs2 = sc.layout.components["c_pbs2"]
    on_beam = QPointF(lerp(pbs2.x, m6.x, 0.5), pbs2.y)
    rec.move(rec.at_scene(view, on_beam), 0.9)
    rec.click()
    q = QPointF(view.mapFromScene(on_beam))
    send_mouse(vp, QMouseEvent.Type.MouseButtonPress, q, Qt.LeftButton)
    send_mouse(vp, QMouseEvent.Type.MouseButtonRelease, q, Qt.NoButton)
    sc.layout_annotations()
    rec.run(0.6)
    rec.move(rec.cursor + QPointF(70, 60), 0.8)


def scene_labsheet(win, rec, ctx):
    """Log a reading with a note in the fiber point's log, then the lab sheet with it."""
    from optolayout.app import render_scene_image
    from optolayout.labsheet import PICTURE_PX, LabSheetDialog
    reopen(win, ctx["js"], ctx["base"], 1)
    pid = ctx["points"]["fc1"]
    panel = win.points_panel
    rec.cursor = rec.at_widget(win.view, QPointF(win.view.width() * 0.55, win.view.height() * 0.5))
    rec.run(0.3)
    # the fiber point's row in the Power log panel: double-click opens its log
    tbl = panel.findChildren(QTableWidget)[0]
    label = win.scene.layout.points[pid].label
    row = next(r for r in range(tbl.rowCount()) if tbl.item(r, 0) and tbl.item(r, 0).text() == label)
    cell = tbl.visualItemRect(tbl.item(row, 0)).center()
    rec.move(rec.at_widget(tbl.viewport(), QPointF(cell)), 0.8)
    rec.click()
    rec.run(0.1)
    rec.click()
    win.open_point_log(pid)
    dlg = win._dialogs[pid]
    dlg.resize(820, 560)  # its bottom stays clear of the caption the edit puts there
    rec.place(dlg, 90, 96)
    rec.run(0.5)
    rec.move(rec.at_dialog(dlg, dlg.value), 0.6)
    rec.click()
    dlg.value.lineEdit().selectAll()
    _type(dlg.value, "21.6", rec, cps=8)
    dlg.value.interpretText()
    rec.move(rec.at_dialog(dlg, dlg.notes), 0.6)
    rec.click()
    if ctx.get("lang") == "zh":
        _type(dlg.notes, "单镜简单调光前，光纤耦合效率下降了 40%", rec, cps=7)
    else:
        _type(dlg.notes, "Before a one-mirror beam walk, fiber coupling efficiency dropped by 40%", rec, cps=24)
    rec.run(0.3)
    add = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Add reading")
    rec.move(rec.at_dialog(dlg, add), 0.5)
    rec.click()
    dlg.instrument.setText("Thorlabs S121C")
    dlg._add_reading()
    win.refresh_measurements()
    dlg.table.scrollToBottom()
    rec.run(1.2)
    rec.move(dlg._promo_pos + QPointF(dlg.size().width() - 23, -16), 0.6)  # its close button
    rec.click()
    rec.run(0.1)
    dlg.close()
    rec.dialogs.remove(dlg)
    rec.run(0.3)
    rec.badge = "Ctrl+P"
    rec.run(0.35)
    sheet = LabSheetDialog(win.scene.layout, win.logbook, win.path.name,
                           lambda: render_scene_image(win.scene, PICTURE_PX), lambda _s: None, win)
    sheet.resize(980, 520)
    rec.place(sheet, None, 100)
    rec.badge = None
    rec.run(0.3)
    srow = next(i for i, p in enumerate(sheet.points) if p.id == pid)
    r = sheet.table.visualItemRect(sheet.table.item(srow, 2))
    rec.move(rec.at_dialog(sheet, sheet.table.viewport(), QPointF(r.center())), 0.8)
    rec.run(1.0)
    copy = next(b for b in sheet.findChildren(QPushButton) if b.text().startswith("Copy for"))
    rec.move(rec.at_dialog(sheet, copy), 0.8)
    rec.run(max(0.0, PLAN["labsheet"] + EXTRA - rec.n / FPS))
    sheet.hide()


def scene_live3d(win, rec, ctx):
    reopen(win, ctx["js"], ctx["base"], 1)
    rec.cursor = None
    rec.run(0.35)
    rec.badge = "Ctrl+3"
    rec.run(0.35)
    v3 = ensure_3d(win)
    rec.badge = None
    o = board_orbit(win, v3)
    m1 = win.scene.layout.components["c_m1"]
    f1 = (m1.x, -m1.y, 30.0)
    total = PLAN["live3d"] + EXTRA - 0.7

    def step(t):
        a = ease(min(1, t / 0.5))  # orbit first
        b = ease((t - 0.35) / 0.6)  # then dive in towards M1's mount and its pillar
        f = tuple(lerp(o.f[i], f1[i], b) for i in range(3))
        d = o.d * math.exp(lerp(0, math.log(0.36), b))
        az = o.az + 60 * a + 75 * b
        el = lerp(o.el, 20, b) + 6 * a * (1 - b)
        Orbit.apply(v3.plotter, f, d, az, el)
    rec.run(total, step)


def _hover(v3, pid):
    """What moving the mouse over a sensor does (View3D._on_move), for one point."""
    from optolayout.view3d import show_point_labels
    heads = getattr(v3.plotter, "_opto_meter_heads", {})
    beads = getattr(v3.plotter, "_opto_meter_beads", {})
    for act in heads.get(pid, []):
        act.SetVisibility(True)
    if pid in beads:
        beads[pid].SetVisibility(False)
    v3._hover = pid
    show_point_labels(v3.plotter, v3._meters(), [pid], name="mp_hover", dark=v3._dark())


def scene_power_log(win, rec, ctx):
    reopen(win, ctx["js"], ctx["base"], 1)
    v3 = ensure_3d(win)
    pid = ctx["points"]["fc1"]
    pos = v3._meters()[pid][0]
    bead = (pos[0], pos[1], pos[2] - 16.0)
    o = board_orbit(win, v3)
    f0 = tuple(lerp(o.f[i], bead[i], 0.8) for i in range(3))
    f1 = tuple(lerp(o.f[i], bead[i], 1.0) for i in range(3))
    cam_t = [0.0]
    total = PLAN["power_log"] + EXTRA

    def cam(t):
        f = tuple(lerp(f0[i], f1[i], ease(t)) for i in range(3))
        Orbit.apply(v3.plotter, f, o.d * lerp(0.62, 0.42, ease(t)), o.az + 25 * ease(t), lerp(o.el, o.el - 8, ease(t)))

    def advance(dt):
        cam_t[0] = min(1.0, cam_t[0] + dt / total)
        cam(cam_t[0])

    rec.cursor = rec.at_widget(v3.plotter.interactor, QPointF(v3.plotter.interactor.width() * 0.75,
                                                              v3.plotter.interactor.height() * 0.3))
    cam(0)
    rec.run(0.3, lambda _t: advance(1 / FPS))
    start = QPointF(rec.cursor)

    def approach(t):
        advance(1 / FPS)
        rec.cursor = lerp_pt(start, world_to_win(rec, v3, bead), ease(t))
    rec.run(1.1, approach)
    _hover(v3, pid)
    v3.plotter.interactor.setCursor(Qt.PointingHandCursor)

    def stay(_t):
        advance(1 / FPS)
        rec.cursor = world_to_win(rec, v3, bead)
    rec.run(1.4, stay)
    rec.click()
    win.open_point_log(pid)
    dlg = win._dialogs[pid]
    dlg.resize(700, 690)
    rec.place(dlg, -40, 120)
    rec.run(0.4, stay)
    rec.move(rec.at_dialog(dlg), 0.8,
             lambda _t: advance(1 / FPS))
    rec.run(total - rec.n / FPS, lambda _t: advance(1 / FPS))


def scene_dy1_layout(win, rec, ctx):
    """The layout the photo-to-layout skill made (a copy of 421nm_system/Dy1-lowpower.json), in 2D."""
    src = ROOT / "421nm_system" / "Dy1-lowpower.json"
    dst = WORK / "Dy1-lowpower.json"
    shutil.copy2(src, dst)
    for d in list(win._dialogs.values()):
        d.close()
    win._dialogs.clear()
    win.scene.undo.setClean()
    if win.a_lengths.isChecked():
        win.a_lengths.trigger()
    win.open_path(str(dst))
    win.tabs.setCurrentIndex(1)
    win.set_mode("select")
    pump(6)
    win.fit_current()
    pump(4)
    win.statusBar().clearMessage()
    view = win.view
    rec.cursor = None
    pump(10)  # lets the app's own fit-on-open happen first
    tr = win.scene.table_rect()
    view.fitInView(tr.adjusted(-30, -70, 150, 30), Qt.KeepAspectRatio)  # with the fibers leaving on the right
    win.scene.layout_annotations()
    pump(4)
    rec.run(PLAN["dy1_layout"] + EXTRA)


SCENES = {"title_orbit": scene_title_orbit, "schematic": scene_schematic, "layout_drag": scene_layout_drag,
          "live3d": scene_live3d, "power_log": scene_power_log, "labsheet": scene_labsheet,
          "dy1_layout": scene_dy1_layout}


# ---- main ------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenes", nargs="*", default=list(SCENES))
    ap.add_argument("--frames", action="store_true", help="also keep the PNG frames in promo/out/<scene>/")
    ap.add_argument("--lang", default="en", choices=["en", "zh"],
                    help="zh: the Chinese note in the lab-sheet scene, written to labsheet_zh.mp4")
    args = ap.parse_args()
    ffmpeg = find_ffmpeg()
    OUT.mkdir(parents=True, exist_ok=True)

    from optolayout.app import MainWindow, set_gl_format
    set_gl_format()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Optical Layout Designer")
    settings = QSettings("optolayout", "Optical Layout Designer")
    saved = {k: settings.value(k) for k in settings.allKeys()}
    results = {}
    win = None
    try:
        js = make_work_copy()
        win = MainWindow(str(js))
        scr = app.primaryScreen()
        dpr = scr.devicePixelRatio()
        w, h = OUT_W / dpr, OUT_H / dpr
        avail = scr.availableGeometry()
        if w > avail.width() or h + 40 > avail.height():
            w, h = 1600 / dpr, 900 / dpr
        win.resize(int(round(w)), int(round(h)))
        win.show()
        win.move(avail.left(), avail.top())
        win.raise_()
        win.activateWindow()
        pump(10)
        points = add_demo_points(win, js)
        base = WORK / "olego_onDy2.base.json"
        shutil.copy2(js, base)
        ctx = {"js": js, "base": base, "points": points, "lang": args.lang}
        for name in args.scenes:
            print(f"scene {name} …", flush=True)
            zh = args.lang != "en" and name == "labsheet"  # the only scene with synthetic text
            rec = Recorder(win, name, ffmpeg, args.frames, out_name=f"{name}_{args.lang}" if zh else None)
            try:
                SCENES[name](win, rec, ctx)
                results[name] = (rec.finish(), None)
            except Exception as e:  # noqa: BLE001 - report and go on with the next scene
                import traceback
                traceback.print_exc()
                try:
                    rec.finish()
                except Exception:  # noqa: BLE001
                    pass
                results[name] = (None, f"{type(e).__name__}: {e}")
            win.badge = None
    finally:
        if win is not None:
            try:
                for d in list(win._dialogs.values()):
                    d.close()
                win.scene.undo.setClean()
                if win.web is not None:
                    win.web.stop()
                if win.logbook:
                    win.logbook.close()
                win.close()
            except Exception:  # noqa: BLE001
                pass
        if win is not None:
            win.settings.sync()  # its own pending writes first, so they can't land after the restore
            win.deleteLater()
            pump(4)
        settings.sync()
        settings.clear()
        for k, v in saved.items():
            settings.setValue(k, v)
        settings.sync()
    print("\nresults:")
    for name, (dur, err) in results.items():
        print(f"  {name:13s} {'%.2f s' % dur if dur else '-':>8s}  {OUT / (name + '.mp4')}" + (f"  ERROR {err}" if err else ""))


if __name__ == "__main__":
    main()
