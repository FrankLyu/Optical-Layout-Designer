"""Main window: Schematic and Layout tabs, properties, power log, files.

The schematic defines the system (parts, part numbers, beams); the layout
places it on the table. See docs/SCHEMATIC.md."""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PySide6.QtCore import QEventLoop, QLineF, QPointF, QRectF, QSettings, QSize, QStandardPaths, Qt, QTimer
from PySide6.QtGui import (QAction, QColor, QImage, QKeySequence, QPainter,
                           QPen)
from PySide6.QtWidgets import (QApplication, QProgressBar, QCheckBox, QHBoxLayout, QColorDialog, QComboBox, QDialog,
                               QDockWidget, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGraphicsView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPushButton, QTabWidget, QVBoxLayout,
                               QWidget)

from .logbook import Logbook, logbook_path_for
from .measure_ui import MeasurementDialog, PointsPanel, export_power_csv
from .mounts3d import DRILLED_STYLES
from .model import (BOARD_STYLES, WAVELENGTH_COLORS, Beam, Component, Layout, MeasurementPoint, new_id,
                    wavelengths_in_use)
from .schematic import MODE_LINK, PartsTable, SchematicPage, SchematicScene, SchSetFieldsCmd
from . import labels
from .scene import (AddPointCmd, BeamItem, ComponentItem, DeleteCmd, LayoutScene, PartPair, PointItem,
                    SetFieldsCmd)
from .icons import icon
from .symbols import SYMBOLS, make_icon

MODE_SELECT, MODE_PLACE, MODE_BEAM, MODE_POINT, MODE_RULER = "select", "place", "beam", "point", "ruler"


def swatch_icon(color: str, size: int = 12):
    from PySide6.QtGui import QIcon, QPixmap
    pm = QPixmap(size, size)
    pm.fill(QColor(color))
    return QIcon(pm)


def hole_text(table, x, y) -> str:
    if not table.has_grid:
        return "a pre-drilled hole" if table.on_board(x, y) else "off the board"
    h = table.hole_at(x, y)
    if h is None:
        return "off the board"
    name, dx, dy = h
    what = "hole" if table.grid_holes else "grid point"
    if abs(dx) < 0.05 and abs(dy) < 0.05:
        return f"{what} {name}"
    return f"near {what} {name} ({dx:+.1f}, {dy:+.1f} mm)"


class LayoutView(QGraphicsView):
    def __init__(self, scene: LayoutScene, win: "MainWindow"):
        super().__init__(scene)
        self.win = win
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self._pan_start = None
        self._press_positions: dict[str, tuple[float, float]] | None = None
        self.beam_from: str | None = None
        self._cursor_scene = QPointF()
        self.ruler: tuple[QPointF, QPointF] | None = None  # last measurement, kept until Esc
        self._ruling = False
        self.setMouseTracking(True)
        self.scale(2.0, 2.0)

    def ruler_snap(self, pos: QPointF, screen_pt) -> QPointF:
        """Snap a ruler end to a part's optical point, or to a hole, when close."""
        sc: LayoutScene = self.scene()
        z = max(sc.view_zoom, 1e-6)
        for it in self.items(screen_pt.x() - 8, screen_pt.y() - 8, 16, 16):
            if isinstance(it, ComponentItem):
                return QPointF(it.comp.x, it.comp.y)
        t = sc.layout.table
        hx = t.hole_offset + round((pos.x() - t.hole_offset) / t.hole_pitch) * t.hole_pitch
        hy = t.hole_offset + round((pos.y() - t.hole_offset) / t.hole_pitch) * t.hole_pitch
        if math.hypot(hx - pos.x(), hy - pos.y()) * z < 7 and t.hole_at(hx, hy) is not None:
            return QPointF(hx, hy)
        return pos

    # zoom / pan ----------------------------------------------------------
    def wheelEvent(self, e):
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.scale(f, f)

    def fit(self):
        self.fitInView(self.scene().table_rect().adjusted(-20, -20, 20, 30), Qt.KeepAspectRatio)

    def mousePressEvent(self, e):
        sc: LayoutScene = self.scene()
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and e.modifiers() & Qt.ControlModifier
                                              and self.win.mode == MODE_SELECT and not self.itemAt(e.position().toPoint())):
            self._pan_start = e.position()
            self.setCursor(Qt.ClosedHandCursor)
            return
        pos = self.mapToScene(e.position().toPoint())
        sc.free_drag = bool(e.modifiers() & Qt.AltModifier)  # Alt-drag: no snapping
        if e.button() == Qt.LeftButton and self.win.mode == MODE_RULER:
            p0 = pos if e.modifiers() & Qt.AltModifier else self.ruler_snap(pos, e.position().toPoint())
            self.ruler = (p0, p0)
            self._ruling = True
            self.viewport().update()
            return
        if e.button() == Qt.LeftButton and self.win.mode == MODE_POINT:
            placed = False
            beam = self._beam_at(e.position().toPoint())
            if beam is not None:
                self.win.add_point_on(beam.beam.id, pos)
                placed = True
            else:
                for it in self.items(e.position().toPoint()):  # a fiber coupler: power out of its fiber
                    if isinstance(it, ComponentItem) and sc.layout.fiber_end(it.comp.id) is not None:
                        self.win.add_fiber_point(it.comp.id)
                        placed = True
                        break
            if placed and not e.modifiers() & Qt.ShiftModifier:  # one point at a time; Shift-click for more
                self.win.set_mode(MODE_SELECT)
            return
        super().mousePressEvent(e)
        if e.button() == Qt.LeftButton:
            self._press_positions = {c: (sc.layout.components[c].x, sc.layout.components[c].y)
                                     for c in sc.selected_ids()[0]}

    def mouseMoveEvent(self, e):
        self._cursor_scene = self.mapToScene(e.position().toPoint())
        self.win.show_cursor(self._cursor_scene)
        if self._pan_start is not None:
            d = e.position() - self._pan_start
            self._pan_start = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        if self._ruling and self.ruler is not None:
            p1 = (self._cursor_scene if e.modifiers() & Qt.AltModifier
                  else self.ruler_snap(self._cursor_scene, e.position().toPoint()))
            self.ruler = (self.ruler[0], p1)
            self.win.show_ruler(*self.ruler)
            self.viewport().update()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pan_start is not None:
            self._pan_start = None
            self.setCursor(Qt.ArrowCursor)
            return
        if self._ruling:
            self._ruling = False
            return
        super().mouseReleaseEvent(e)
        sc: LayoutScene = self.scene()
        sc.free_drag = False
        if self._press_positions:
            changes = {}
            for cid, (x0, y0) in self._press_positions.items():
                c = sc.layout.components.get(cid)
                if c and (abs(c.x - x0) > 1e-6 or abs(c.y - y0) > 1e-6):
                    changes[cid] = ({"x": x0, "y": y0, "pinned": c.pinned}, {"x": c.x, "y": c.y, "pinned": True})
            if changes:
                sc.undo.push(SetFieldsCmd(sc, changes, "Move"))
        self._press_positions = None

    def _beam_at(self, pt) -> BeamItem | None:
        # generous pick radius: beams are thin
        r = 6
        for it in self.items(pt.x() - r, pt.y() - r, 2 * r, 2 * r):
            if isinstance(it, BeamItem):
                return it
        return None

    def _component_at(self, pt) -> ComponentItem | None:
        for it in self.items(pt):
            if isinstance(it, ComponentItem):
                return it
        return None

    def keyPressEvent(self, e):
        arrows = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if e.key() in arrows:
            dx, dy = arrows[e.key()]
            self.win.nudge_selected(dx, dy, fine=bool(e.modifiers() & Qt.ShiftModifier))
            return
        super().keyPressEvent(e)

    def drawForeground(self, p, rect):
        super().drawForeground(p, rect)
        if self.ruler is None or self.win.mode != MODE_RULER:
            return
        a, b = self.ruler
        z = max(self.scene().view_zoom, 1e-6)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#e8590c"), 2.0 / z)
        p.setPen(pen)
        p.drawLine(a, b)
        ln = QLineF(a, b)
        L = ln.length()
        tick = 7 / z
        if L > 0:
            n = QPointF(-ln.dy() / L, ln.dx() / L) * tick
            for q in (a, b):
                p.drawLine(q - n, q + n)
        p.setBrush(QColor("#e8590c"))
        for q in (a, b):
            p.drawEllipse(q, 2.5 / z, 2.5 / z)
        txt = f"{L:.1f} mm  ({L / 25.4:.3f} in)"
        sub = f"dx {b.x() - a.x():+.1f}  dy {b.y() - a.y():+.1f} mm"
        px = 13 / z
        w1, h1 = labels.text_size(txt, px)
        w2, h2 = labels.text_size(sub, px * 0.85, bold=False)
        m = ln.pointAt(0.5)
        box = QRectF(m.x() + 8 / z, m.y() + 8 / z, max(w1, w2) + 8 / z, h1 + h2 + 4 / z)
        p.setPen(QPen(QColor("#e8590c"), 1 / z))
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRoundedRect(box, 3 / z, 3 / z)
        p.setPen(QColor("#111111"))
        labels.draw_halo_text(p, QRectF(box.left() + 4 / z, box.top() + 2 / z, w1, h1), txt, px,
                              align=Qt.AlignLeft | Qt.AlignVCenter)
        labels.draw_halo_text(p, QRectF(box.left() + 4 / z, box.top() + 2 / z + h1, w2, h2), sub, px * 0.85,
                              bold=False, color="#444444", align=Qt.AlignLeft | Qt.AlignVCenter)

    def mouseDoubleClickEvent(self, e):
        it = self._component_at(e.position().toPoint())
        if it is not None:
            self.win.edit_in_schematic(it.comp)
            return
        super().mouseDoubleClickEvent(e)


def board_summary(lay, scene) -> str:
    """What the Properties panel shows when nothing is selected: the board,
    what is on it, and which colour is which wavelength."""
    t = lay.table
    on = [c for c in lay.components.values() if t.on_board(c.x, c.y)]
    waiting = len(lay.components) - len(on)
    total = sum(lay.beam_length(b) for b in lay.beams.values())
    pts = [p for p in lay.points.values() if not p.archived]
    rows = [f"{t.width:g} × {t.height:g} mm ({t.width / 25.4:g} × {t.height / 25.4:g} in)",
            BOARD_STYLES.get(t.style, ("",))[0] + (", irregular" if t.cutouts else "")
            + (f": {t.columns()} × {t.rows()} grid at {t.hole_pitch:g} mm" if t.has_grid else "")
            + (f", {len(scene.table_screw_holes())} table screws" if t.style in DRILLED_STYLES else ""),
            f"{len(on)} parts on the board" + (f", {waiting} waiting below it" if waiting else ""),
            f"{len(lay.beams)} beam segments, {total:.0f} mm of beam in total",
            f"{len(pts)} measurement points"]
    if scene.clashes:
        rows.append(f"<span style='color:#d62728'>⚠ {len(scene.clashes)} parts overlap</span>")
    html = "<br>".join(rows)
    used = wavelengths_in_use(lay)
    if used:
        html += "<br><br><b>Wavelengths</b>"
        for color, name, n in used:
            html += (f"<br><span style='color:{color}; font-size:14px'>■</span>&nbsp;{name}"
                     f" <span style='color:#777'>({n} segments)</span>")
    html += ("<br><br><span style='color:#777'>Drag parts to move them; arrows nudge one hole (Shift: 1 mm). "
             "Select two parts for the optical path between them. Parts and beams are added in the "
             "Schematic tab.</span>")
    return html


class BoardDialog(QDialog):
    """Board name, size, hole pattern and cut-outs (for irregular boards)."""

    def __init__(self, t, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Board")
        self.name = QLineEdit(t.name)
        self.width = QDoubleSpinBox()
        self.height = QDoubleSpinBox()
        for s, v in ((self.width, t.width), (self.height, t.height)):
            s.setRange(10, 10000)
            s.setDecimals(2)
            s.setSuffix(" mm")
            s.setValue(v)
        self.style = QComboBox()
        for key, (label, _p) in BOARD_STYLES.items():
            self.style.addItem(label, key)
        self.style.setCurrentIndex(max(0, self.style.findData(t.style)))
        self.cutouts = QLineEdit("; ".join(", ".join(f"{v:g}" for v in c) for c in t.cutouts))
        self.cutouts.setPlaceholderText("none; or x, y, w, h; x, y, w, h  (mm, from the top-left corner)")
        form = QFormLayout(self)
        form.addRow("Name", self.name)
        form.addRow("Width", self.width)
        form.addRow("Height", self.height)
        form.addRow("Holes", self.style)
        form.addRow("Cut-outs", self.cutouts)
        hint = QLabel("Cut-outs make an irregular board: each is a rectangle removed from it.")
        hint.setStyleSheet("color:#777")
        hint.setWordWrap(True)
        form.addRow(hint)
        from PySide6.QtWidgets import QDialogButtonBox
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _parse(self):
        out = []
        for chunk in self.cutouts.text().split(";"):
            if chunk.strip():
                vals = [float(v) for v in chunk.replace(" ", "").split(",")]
                if len(vals) != 4:
                    raise ValueError
                out.append(vals)
        return out

    def _ok(self):
        try:
            self._cut = self._parse()
        except ValueError:
            QMessageBox.warning(self, "Board", "Cut-outs: x, y, w, h for each, separated by ;")
            return
        self.accept()

    def apply(self, t):
        t.name, t.width, t.height = self.name.text().strip(), self.width.value(), self.height.value()
        style = self.style.currentData()
        if style != t.style:
            t.apply_style(style)
        t.cutouts = self._cut


class PropertiesPanel(QWidget):
    """Layout properties. What a part IS (label, part, part number) belongs to
    the schematic and is shown read-only here; the layout only sets where it
    sits and how it is turned."""

    def __init__(self, scene: LayoutScene):
        super().__init__()
        self.scene = scene
        self.obj = None
        form = QFormLayout(self)
        self.title = QLabel("Nothing selected")
        f = self.title.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.15)
        self.title.setFont(f)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.AutoText)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label = QLineEdit()  # editable for measurement points only
        self.x = self._spin(-10000, 10000, " mm")
        self.y = self._spin(-10000, 10000, " mm")
        self.angle = self._spin(-360, 360, " °")
        self.auto = QCheckBox("Aim automatically from the beams")
        self.auto.toggled.connect(self._auto_toggled)
        self.edit_btn = QPushButton("Edit part in schematic")
        self.edit_btn.clicked.connect(lambda: self.obj is not None and self.edit_in_schematic(self.obj))
        self.edit_in_schematic = lambda _obj: None
        self.log_btn = QPushButton("Open measurement log…")
        self.log_btn.clicked.connect(lambda: self.obj and self.open_log(self.obj.id))
        self.open_log = lambda _pid: None
        form.addRow(self.title)
        form.addRow(self.info)
        form.addRow("Label", self.label)
        form.addRow("X", self.x)
        form.addRow("Y", self.y)
        form.addRow("Angle", self.angle)
        form.addRow("", self.auto)
        form.addRow("", self.edit_btn)
        form.addRow("", self.log_btn)
        self.rows = {"label": self.label, "x": self.x, "y": self.y, "angle": self.angle}
        for key, w in self.rows.items():
            w.editingFinished.connect(lambda k=key: self._commit(k))
        scene.selection_info.connect(self.show_obj)
        scene.edited.connect(lambda: self.show_obj(self.obj))
        self.show_obj(None)

    @staticmethod
    def _spin(lo, hi, suffix):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(2)
        s.setSuffix(suffix)
        s.setKeyboardTracking(False)
        return s

    def _show(self, w, on):
        w.setVisible(on)
        lbl = self.layout().labelForField(w)
        if lbl is not None:
            lbl.setVisible(on)

    def show_obj(self, obj):
        lay = self.scene.layout
        if isinstance(obj, Component) and obj.id not in lay.components:
            obj = None
        if isinstance(obj, Beam) and obj.id not in lay.beams:
            obj = None
        self.obj = obj
        is_comp = isinstance(obj, Component)
        is_beam = isinstance(obj, Beam)
        is_point = isinstance(obj, MeasurementPoint)
        for w in (self.x, self.y, self.angle, self.auto):
            self._show(w, is_comp)
        self._show(self.label, is_point)
        self.edit_btn.setVisible(is_comp or is_beam)
        self.edit_btn.setText("Edit part in schematic" if is_comp else "Edit beam in schematic")
        self.log_btn.setVisible(is_point)
        for w in list(self.rows.values()) + [self.auto]:
            w.blockSignals(True)
        if is_comp:
            el = lay.schematic.elements.get(obj.sch_id) if obj.sch_id else None
            self.title.setText(obj.label or SYMBOLS[obj.type].name)
            lines = [SYMBOLS[obj.type].name, obj.part_number or "no part number",
                     "Post at " + hole_text(lay.table, obj.x, obj.y)]
            if el is not None and el.notes:
                lines.append(el.notes)
            if obj.id in self.scene.clashes:
                lines.append("⚠ Overlaps another part")
            if obj.id in self.scene.off_table():
                lines.append("Not on the table yet: drag it into place")
            self.info.setText("\n".join(lines))
            self.x.setValue(obj.x)
            self.y.setValue(obj.y)
            self.angle.setValue(obj.angle)
            self.angle.setEnabled(not obj.auto_angle)
            self.auto.setChecked(obj.auto_angle)
        elif is_beam:
            a, b = lay.components.get(obj.source), lay.components.get(obj.target)
            self.title.setText(f"Beam {a.label if a else '?'} → {b.label if b else '?'}")
            L = math.hypot(b.x - a.x, b.y - a.y) if a and b else 0
            wl = f"{obj.wavelength_nm:g} nm" if obj.wavelength_nm else "wavelength not set"
            n = len([p for p in lay.points_on(obj.id) if not p.archived])
            self.info.setText(f"{wl}\nLength {L:.1f} mm ({L / 25.4:.2f} in)\n{n} measurement point(s)")
        elif isinstance(obj, PartPair):
            a, b = lay.components.get(obj[0]), lay.components.get(obj[1])
            name = lambda c: c.label or SYMBOLS[c.type].name  # noqa: E731
            self.title.setText(f"{name(a)} ↔ {name(b)}" if a and b else "Two parts")
            if a and b:
                d = math.hypot(b.x - a.x, b.y - a.y)
                lines = [f"Straight line: {d:.1f} mm ({d / 25.4:.3f} in)",
                         f"dx {b.x - a.x:+.1f} mm, dy {b.y - a.y:+.1f} mm"]
                path = lay.optical_path(a.id, b.id)
                if path is None:
                    lines.append("No beam path connects them.")
                else:
                    L, ids = path
                    lines.insert(0, f"Optical path: {L:.1f} mm ({L / 25.4:.3f} in)")
                    lines.append("Along the beams: " + " → ".join(name(lay.components[c]) for c in ids))
                    segs = []
                    for u, v in zip(ids, ids[1:]):
                        cu, cv = lay.components[u], lay.components[v]
                        segs.append(f"{math.hypot(cv.x - cu.x, cv.y - cu.y):.1f}")
                    lines.append("Segments (mm): " + " + ".join(segs))
                self.info.setText("\n".join(lines))
        elif is_point:
            self.title.setText(f"Measurement point {obj.label}" + (" (archived)" if obj.archived else ""))
            part = lay.components.get(obj.part_id or "")
            self.info.setText(f"Power out of the fiber of {part.label or SYMBOLS[part.type].name}: it moves with "
                              "the coupler." if part is not None else "Drag the marker to slide it along its beam.")
            self.label.setText(obj.label)
        else:
            self.title.setText(lay.table.name or "Board")
            self.info.setText(board_summary(lay, self.scene))
        for w in list(self.rows.values()) + [self.auto]:
            w.blockSignals(False)

    def _auto_toggled(self, on):
        if isinstance(self.obj, Component) and self.obj.auto_angle != on:
            self.scene.undo.push(SetFieldsCmd(self.scene, {self.obj.id: ({"auto_angle": self.obj.auto_angle},
                                                                         {"auto_angle": on})}, "Auto-aim"))

    def _commit(self, key):
        if self.obj is None:
            return
        w = self.rows[key]
        val = w.text() if isinstance(w, QLineEdit) else w.value()
        if getattr(self.obj, key, None) == val:
            return
        old, new = {key: getattr(self.obj, key)}, {key: val}
        if key == "angle" and isinstance(self.obj, Component):
            old["auto_angle"], new["auto_angle"] = self.obj.auto_angle, False
        if key in ("x", "y") and isinstance(self.obj, Component):
            old["pinned"], new["pinned"] = self.obj.pinned, True
        self.scene.undo.push(SetFieldsCmd(self.scene, {self.obj.id: (old, new)}, f"Edit {key}"))


class MainWindow(QMainWindow):
    def __init__(self, path: str | None = None):
        super().__init__()
        self.scene = LayoutScene()
        self.view = LayoutView(self.scene, self)
        self.sch_scene = SchematicScene(self.scene.undo)
        self.sch_page = SchematicPage(self.sch_scene, lambda: self.beam_style(), WAVELENGTH_COLORS)
        self.sch_page.hint = lambda msg: self.statusBar().showMessage(msg)
        self.sch_page.back_to_select = lambda: self.set_mode(MODE_SELECT)
        self.tabs = QTabWidget()
        self.tabs.setIconSize(QSize(20, 20))
        self.tabs.addTab(self.sch_page, icon("schematic"), "Schematic")
        self.tabs.addTab(self.view, icon("layout"), "Layout")
        self.view3d_holder = QWidget()  # the 3D tab is built the first time it is opened
        QVBoxLayout(self.view3d_holder).setContentsMargins(0, 0, 0, 0)
        self.view3d = None
        self._view3d_loading = False
        try:  # an OpenGL widget from the start: adding the first one to a window that is already on screen
            # makes Windows close and reopen the whole window
            from PySide6.QtOpenGLWidgets import QOpenGLWidget
            QOpenGLWidget(self.view3d_holder).hide()
        except Exception:
            pass
        self.tabs.addTab(self.view3d_holder, icon("3d"), "3D")
        self.tabs.setCurrentIndex(1)
        self.setCentralWidget(self.tabs)
        self._syncing_sel = False
        self._fit_pending = {0, 1}  # tabs to fit once they are on screen with their real size
        self.path: Path | None = None
        self.mode = MODE_SELECT

        self.layout_docks = []
        self.settings = QSettings("optolayout", "Optical Layout Designer")
        try:
            self.scene.text_scale = self.sch_scene.text_scale = float(self.settings.value("text_scale", 1.0))
        except (TypeError, ValueError):
            pass

        self.props = PropertiesPanel(self.scene)
        self.props.open_log = self.open_point_log
        self.props.edit_in_schematic = self.edit_in_schematic
        pdock = QDockWidget("Properties", self)
        pdock.setWidget(self.props)
        self.addDockWidget(Qt.RightDockWidgetArea, pdock)
        self.layout_docks.append(pdock)

        self.logbook: Logbook | None = None
        self._no_log = False  # opened without its power log: nothing is logged
        self._log_layout: Path | None = None  # the layout file the log belongs to
        self._dialogs: dict[str, MeasurementDialog] = {}
        self.points_panel = PointsPanel()
        self.points_panel.open_point.connect(self.open_point_log)
        self.points_panel.show_archived_changed.connect(self.scene.set_show_archived)
        mdock = QDockWidget("Power log", self)
        mdock.setWidget(self.points_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, mdock)
        self.layout_docks.append(mdock)
        self._log_poll = QTimer(self)  # readings logged elsewhere (the web pages) show up here
        self._log_poll.timeout.connect(self._poll_logbook)
        self._log_poll.start(3000)
        self.scene.point_clicked.connect(self.open_point_log)
        self.scene.edited.connect(self.refresh_measurements)
        self.scene.edited.connect(self._layers_changed)
        self.sch_scene.edited.connect(self._schematic_changed)
        self.scene.selectionChanged.connect(self._layout_sel_to_sch)
        self.sch_scene.selectionChanged.connect(self._sch_sel_to_layout)
        self.tabs.currentChanged.connect(self._tab_changed)

        self._build_actions()
        self.scene.undo.cleanChanged.connect(lambda _: self._update_title())
        self.statusBar()
        self.pos_lbl = QLabel()
        self.statusBar().addPermanentWidget(self.pos_lbl)
        # web status at the right end of the menu bar: a coloured dot and the address other PCs open
        self.web_corner = corner = QWidget()  # kept: PySide doesn't give a corner widget to the menu bar
        row = QHBoxLayout(corner)
        row.setContentsMargins(0, 0, 10, 0)
        row.setSpacing(5)
        self.web_dot = QLabel("●")
        self.web_lbl = QLabel()
        self.web_lbl.setOpenExternalLinks(True)
        self.web_lbl.setTextInteractionFlags(Qt.TextBrowserInteraction)  # click to open, select to copy
        row.addWidget(self.web_dot)
        row.addWidget(self.web_lbl)
        self.menuBar().setCornerWidget(corner, Qt.TopRightCorner)
        self._web_state("grey")
        if self.a_web.isChecked() and QApplication.platformName() not in ("offscreen", "minimal"):
            QTimer.singleShot(0, lambda: self.set_web(True, remember=False))  # tests start it themselves
        if path:
            self.open_path(path)
        else:
            self.sch_scene.set_layout(self.scene.layout)
        self.resize(1400, 900)
        self._update_title()
        self._tab_changed(self.tabs.currentIndex())

    # ---- actions ------------------------------------------------------------
    def _act(self, text, slot, shortcut=None, tb=None, icon_name=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        if icon_name:
            a.setIcon(icon(icon_name))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            keys = a.shortcut().toString(QKeySequence.NativeText)
            if keys and f"({keys})" not in text:
                a.setToolTip(f"{text}  ({keys})")
        self.addAction(a)
        if tb is not None:
            tb.addAction(a)
        return a

    def _build_actions(self):
        m = self.menuBar()
        fm = m.addMenu("&File")
        self.a_new = self._act("New", self.new_file, QKeySequence.New, icon_name="new")
        self.a_open = self._act("Open…", self.open_file, QKeySequence.Open, icon_name="open")
        self.a_save = self._act("Save", self.save_file, QKeySequence.Save, icon_name="save")
        for a in (self.a_new, self.a_open, self.a_save):
            fm.addAction(a)
        fm.addAction(self._act("Save As…", self.save_as, QKeySequence.SaveAs))
        fm.addSeparator()
        fm.addAction(self._act("Export SVG (current tab)…", lambda: self.export("svg"), "Ctrl+E"))
        fm.addAction(self._act("Export PNG (current tab)…", lambda: self.export("png"), "Ctrl+Shift+E"))
        fm.addAction(self._act("Export power log (CSV)…", self.export_csv))
        fm.addAction(self._act("Export bill of materials (CSV)…", self.export_bom))
        fm.addSeparator()
        fm.addAction(self._act("Board size, holes and shape…", self.edit_table))
        # the web pages (web/), served while the app is open; gone if the web folder is deleted
        self.web = None
        self.web_config = None  # None: web/config.json
        self.a_web = self._act("Web access (share on network)", lambda on: self.set_web(on))
        self.a_web.setCheckable(True)
        self.a_web.setChecked(self.settings.value("web_on", True, type=bool))
        self.a_web.setToolTip("Serve the layouts and the power log to other PCs' browsers while this app is open")
        if (Path(__file__).resolve().parents[1] / "web" / "embed.py").exists():
            fm.addSeparator()
            fm.addAction(self.a_web)

        em = m.addMenu("&Edit")
        undo = self.scene.undo.createUndoAction(self, "Undo")
        undo.setShortcut(QKeySequence.Undo)
        redo = self.scene.undo.createRedoAction(self, "Redo")
        redo.setShortcut(QKeySequence.Redo)
        undo.setIcon(icon("undo"))
        redo.setIcon(icon("redo"))
        em.addAction(undo)
        em.addAction(redo)
        em.addSeparator()
        em.addAction(self._act("Delete", self.delete_selected, QKeySequence.Delete))
        em.addAction(self._act("Duplicate (schematic)", self.duplicate_selected, "Ctrl+D"))
        em.addAction(self._act("Select all", self.select_all, QKeySequence.SelectAll))
        em.addSeparator()
        em.addAction(self._act("Rotate +45°", lambda: self.rotate_selected(45), "R"))
        em.addAction(self._act("Rotate −45°", lambda: self.rotate_selected(-45), "Shift+R"))
        em.addAction(self._act("Rotate +5°", lambda: self.rotate_selected(5), "]"))
        em.addAction(self._act("Rotate −5°", lambda: self.rotate_selected(-5), "["))
        em.addAction(self._act("Aim automatically from beams", self.auto_aim_selected, "A"))
        em.addSeparator()
        em.addAction(self._act("Parts table…", self.show_parts_table, "Ctrl+T", icon_name="table"))
        self.a_bom = self._act("Bill of materials…", self.show_bom, "Ctrl+Shift+B", icon_name="bom")
        em.addAction(self.a_bom)

        vm = m.addMenu("&View")
        vm.addAction(self._act("Schematic", lambda: self.tabs.setCurrentIndex(0), "Ctrl+1", icon_name="schematic"))
        vm.addAction(self._act("Layout", lambda: self.tabs.setCurrentIndex(1), "Ctrl+2", icon_name="layout"))
        vm.addAction(self._act("3D", lambda: self.tabs.setCurrentIndex(2), "Ctrl+3", icon_name="3d"))
        vm.addAction(self._act("Toggle schematic / layout", self.toggle_tab, "Ctrl+Tab"))
        vm.addSeparator()
        vm.addAction(self._act("Fit to window", self.fit_current, "F", icon_name="fit"))
        vm.addAction(self._act("Zoom to selection", self.zoom_to_selection, "Z"))
        vm.addSeparator()
        vm.addAction(self._act("Bigger text", lambda: self.scale_text(1.15), "Ctrl+="))
        vm.addAction(self._act("Smaller text", lambda: self.scale_text(1 / 1.15), "Ctrl+-"))
        vm.addAction(self._act("Reset text size", lambda: self.scale_text(None), "Ctrl+0"))
        vm.addSeparator()
        self.a_lengths = self._act("Beam lengths on the layout", self.toggle_lengths, "Ctrl+L")
        self.a_lengths.setCheckable(True)
        vm.addAction(self.a_lengths)
        self.a_coords = self._act("Hole coordinates around the board", self.toggle_coords)
        self.a_coords.setCheckable(True)
        self.a_coords.setChecked(True)
        vm.addAction(self.a_coords)

        lm = m.addMenu("&Layout")
        lm.addAction(self._act("Arrange like the schematic…", self.arrange_like_schematic))
        lm.addAction(self._act("Show overlapping parts", self.show_clashes))

        self.a_sheet = self._act("Lab sheet…", self.show_lab_sheet, "Ctrl+P", icon_name="sheet")
        fm.insertAction(fm.actions()[fm.actions().index(self.a_save) + 2], self.a_sheet)  # after Save As

        tb = self.addToolBar("Tools")
        tb.setObjectName("tools")
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)  # icons with a short name under each
        tb.setIconSize(QSize(24, 24))
        for a in (self.a_new, self.a_open, self.a_save):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(undo)
        tb.addAction(redo)
        tb.addSeparator()
        self.a_select = self._act("Select / move (S)", lambda: self.set_mode(MODE_SELECT), "S", tb, "select")
        self.a_beam = self._act("Draw beam (B)", lambda: self.set_mode(MODE_BEAM), "B", tb, "beam")
        self.a_point = self._act("Power point (M)", lambda: self.set_mode(MODE_POINT), "M", tb, "point")
        self.a_ruler = self._act("Ruler (L)", lambda: self.set_mode(MODE_RULER), "L", tb, "ruler")
        self._act("Cancel", lambda: self.set_mode(MODE_SELECT), "Esc")
        for a in (self.a_select, self.a_beam, self.a_point, self.a_ruler):
            a.setCheckable(True)
        # tools that only make sense on one tab are hidden on the other
        self.sch_only = [self.a_beam, tb.addSeparator(), tb.addWidget(QLabel(" New beams: "))]
        self.wl_combo = QComboBox()
        for name, (wl, color) in WAVELENGTH_COLORS.items():
            self.wl_combo.addItem(swatch_icon(color), name, (wl, color))
        self.sch_only.append(tb.addWidget(self.wl_combo))
        self.layout_only = [self.a_point, self.a_ruler, tb.addSeparator(), tb.addWidget(QLabel(" Snap: "))]
        self.snap_combo = QComboBox()
        self.snap_combo.addItem("Holes (25.4 mm)", LayoutScene.SNAP_HOLES)
        self.snap_combo.addItem("Half holes (12.7 mm)", LayoutScene.SNAP_HALF)
        self.snap_combo.addItem("Free", LayoutScene.SNAP_FREE)
        self.snap_combo.currentIndexChanged.connect(
            lambda i: setattr(self.scene, "snap_mode", self.snap_combo.itemData(i)))
        self.layout_only.append(tb.addWidget(self.snap_combo))
        tb.addSeparator()
        self._act("Fit to window (F)", self.fit_current, None, tb, "fit")
        self._act("Parts table (Ctrl+T)", self.show_parts_table, None, tb, "table")
        tb.addAction(self.a_bom)
        self.a_bigger = self._act("Bigger text (Ctrl+=)", lambda: self.scale_text(1.15), None, tb, "bigger")
        self.a_smaller = self._act("Smaller text (Ctrl+−)", lambda: self.scale_text(1 / 1.15), None, tb, "smaller")
        tb.addSeparator()
        tb.addAction(self.a_sheet)
        # layouts in the same folder, to switch between them (switcher.py)
        from .switcher import LayoutSwitcher
        tb.addSeparator()
        tb.addWidget(QLabel(" Layout: "))
        self.switcher = LayoutSwitcher(lambda: self.path, self._last_folder, lambda p: self.switch_to(p),
                                       lambda: self.open_file())
        tb.addWidget(self.switcher)
        # short names under the toolbar icons; menus and tooltips keep the full text
        short = {"New": "New", "Open…": "Open", "Save": "Save", "Select / move (S)": "Select",
                 "Draw beam (B)": "Beam", "Power point (M)": "Power", "Ruler (L)": "Ruler",
                 "Fit to window (F)": "Fit", "Parts table (Ctrl+T)": "Parts", "Bill of materials…": "BOM",
                 "Bigger text (Ctrl+=)": "A+", "Smaller text (Ctrl+−)": "A−", "Lab sheet…": "Sheet"}
        for a in tb.actions():
            if a.text() in short:
                a.setToolTip(a.toolTip())  # fix the tooltip before the short name could become it
                a.setIconText(short[a.text()])
        undo.setIconText("Undo")
        redo.setIconText("Redo")

    def update_snap_labels(self):
        """The snap choices name this board's hole spacing."""
        t = self.scene.layout.table
        what = "Holes" if t.grid_holes else "Grid"
        self.snap_combo.setItemText(0, f"{what} ({t.hole_pitch:g} mm)" if t.has_grid else "Holes (none: pre-drilled)")
        self.snap_combo.setItemText(1, f"Half {what.lower()} ({t.hole_pitch / 2:g} mm)"
                                    + (", incl. centre holes" if t.center_holes else ""))

    def beam_style(self):
        return self.wl_combo.currentData()

    def on_schematic(self) -> bool:
        return self.tabs.currentIndex() == 0

    def set_mode(self, mode):
        sch = self.on_schematic()
        if sch and mode in (MODE_POINT, MODE_RULER):
            self.statusBar().showMessage("Measurement points and the ruler are in the Layout tab (Ctrl+2).", 5000)
            return
        if not sch and mode == MODE_BEAM:
            self.statusBar().showMessage("Beams are drawn in the Schematic tab (Ctrl+1); the layout follows.", 5000)
            mode = MODE_SELECT
        self.a_select.setChecked(mode == MODE_SELECT)
        self.a_beam.setChecked(mode == MODE_BEAM)
        self.a_point.setChecked(mode == MODE_POINT)
        self.a_ruler.setChecked(mode == MODE_RULER)
        if sch:
            self.sch_page.set_mode(MODE_LINK if mode == MODE_BEAM else mode)
            return
        self.mode = mode
        if mode != MODE_RULER:
            self.view.ruler = None
        self.view.setCursor(Qt.CrossCursor if mode == MODE_RULER else Qt.ArrowCursor)
        self.view.setDragMode(QGraphicsView.RubberBandDrag if mode == MODE_SELECT else QGraphicsView.NoDrag)
        hints = {MODE_SELECT: "Layout: drag parts to move them (Alt-drag: no snapping). Arrows nudge one hole, "
                              "Shift+arrows 1 mm. R / [ ] rotate, A aims from the beams. Double-click a part to "
                              "edit it in the schematic.",
                 MODE_POINT: "Click a beam to add a power measurement point (midpoint by default; drag it along "
                             "the beam afterwards), or a fiber coupler for the power out of its fiber. The tool "
                             "then goes back to Select; Shift+click to add several. Esc to stop.",
                 MODE_RULER: "Ruler: drag to measure. Ends snap to parts and holes (Alt: no snapping). Select two "
                             "parts to see the optical path between them. Esc to stop."}
        self.statusBar().showMessage(hints[mode])
        self.view.viewport().update()

    def show_cursor(self, pt):
        h = self.scene.layout.table.hole_at(pt.x(), pt.y())
        hole = f"   hole {h[0]}" if h and abs(h[1]) < 6 and abs(h[2]) < 6 else ""
        self.pos_lbl.setText(f"x = {pt.x():7.1f} mm   y = {pt.y():7.1f} mm{hole}")

    def show_ruler(self, a, b):
        L = math.hypot(b.x() - a.x(), b.y() - a.y())
        self.statusBar().showMessage(f"Ruler: {L:.1f} mm ({L / 25.4:.3f} in), dx {b.x() - a.x():+.1f} mm, "
                                     f"dy {b.y() - a.y():+.1f} mm")

    def toggle_lengths(self, on):
        self.scene.show_lengths = bool(on)
        self.scene.layout_annotations()
        self.scene.update()

    def toggle_coords(self, on):
        self.scene.show_coords = bool(on)
        self.scene.update()

    # ---- edits ----------------------------------------------------------------
    def delete_selected(self):
        if self.on_schematic():
            self.sch_page.delete_selected()
            return
        points = self.scene.selected_points()
        if points:
            self.scene.undo.push(DeleteCmd(self.scene, [], [], points))
        elif any(self.scene.selected_ids()):
            self.statusBar().showMessage("Parts and beams are removed in the Schematic tab; the layout follows.",
                                         6000)

    def duplicate_selected(self):
        if not self.on_schematic():
            self._sch_sel_to_front()
        self.sch_page.duplicate_selected()

    def _sch_sel_to_front(self):
        self.tabs.setCurrentIndex(0)

    def select_all(self):
        sc = self.sch_scene if self.on_schematic() else self.scene
        for it in sc.items():
            if it.flags() & it.GraphicsItemFlag.ItemIsSelectable and not isinstance(it, PointItem):
                it.setSelected(True)

    def nudge_selected(self, dx, dy, fine=False):
        sc = self.scene
        t = sc.layout.table
        if fine or sc.snap_mode == LayoutScene.SNAP_FREE:
            step = 1.0
        else:
            step = t.hole_pitch if sc.snap_mode == LayoutScene.SNAP_HOLES else t.hole_pitch / 2
        comps, _ = sc.selected_ids()
        lc = sc.layout.components
        ch = {c: ({"x": lc[c].x, "y": lc[c].y, "pinned": lc[c].pinned},
                  {"x": lc[c].x + dx * step, "y": lc[c].y + dy * step, "pinned": True}) for c in comps}
        if ch:
            sc.undo.push(SetFieldsCmd(sc, ch, "Nudge"))

    def auto_aim_selected(self):
        if self.on_schematic():
            els, _ = self.sch_scene.selected_ids()
            ch = {e: ({"auto_angle": self.sch_scene.sch.elements[e].auto_angle}, {"auto_angle": True}) for e in els}
            if ch:
                self.scene.undo.push(SchSetFieldsCmd(self.sch_scene, ch, "Auto-aim"))
            return
        comps, _ = self.scene.selected_ids()
        ch = {c: ({"auto_angle": self.scene.layout.components[c].auto_angle}, {"auto_angle": True}) for c in comps}
        if ch:
            self.scene.undo.push(SetFieldsCmd(self.scene, ch, "Auto-aim"))

    def show_parts_table(self):
        if getattr(self, "_parts_table", None) is None:
            self._parts_table = PartsTable(self.sch_scene, self)
        else:
            self._parts_table.reload()
        self._parts_table.show()
        self._parts_table.raise_()

    def show_bom(self):
        if getattr(self, "_bom", None) is None:
            from .bom import BomDialog
            self._bom = BomDialog(lambda: self.scene.layout, self.scene.edited, self)
        self._bom.show()
        self._bom.raise_()

    def export_bom(self):
        from .bom import bill_of_materials, write_bom_csv
        p, _ = QFileDialog.getSaveFileName(self, "Export bill of materials", "bom.csv", "CSV (*.csv)")
        if p:
            write_bom_csv(bill_of_materials(self.scene.layout), p)
            self.statusBar().showMessage(f"Bill of materials written to {p}", 5000)

    def toggle_tab(self):
        self.tabs.setCurrentIndex(1 if self.tabs.currentIndex() != 1 else 0)

    def fit_current(self):
        if self.tabs.currentIndex() == 2:
            if self.view3d is not None:
                self.view3d.fit()
        elif self.on_schematic():
            self.sch_page.view.fit()
        else:
            self.view.fit()

    def zoom_to_selection(self):
        view, sc = (self.sch_page.view, self.sch_scene) if self.on_schematic() else (self.view, self.scene)
        sel = sc.selectedItems()
        if not sel:
            return self.fit_current()
        r = sel[0].sceneBoundingRect()
        for it in sel[1:]:
            r = r.united(it.sceneBoundingRect())
        view.fitInView(r.adjusted(-60, -60, 60, 60), Qt.KeepAspectRatio)

    def scale_text(self, k):
        v = 1.0 if k is None else min(4.0, max(0.4, self.scene.text_scale * k))
        self.scene.set_text_scale(v)
        self.sch_scene.set_text_scale(v)
        self.settings.setValue("text_scale", v)
        self.statusBar().showMessage(f"Text size {v * 100:.0f} %", 3000)

    def edit_in_schematic(self, obj):
        """Cross-probe: jump to the schematic with this part (or beam) selected."""
        self.tabs.setCurrentIndex(0)
        self.sch_scene.clearSelection()
        if isinstance(obj, Component) and obj.sch_id in self.sch_scene.el_items:
            it = self.sch_scene.el_items[obj.sch_id]
        elif isinstance(obj, Beam) and obj.id in self.sch_scene.link_items:
            it = self.sch_scene.link_items[obj.id]
        else:
            return
        it.setSelected(True)
        self.sch_page.view.centerOn(it)
        self.sch_page.props.label.setFocus()

    def arrange_like_schematic(self):
        """Move every part to the schematic's arrangement, scaled onto the table (undoable)."""
        lay = self.scene.layout
        if not lay.components:
            return
        r = QMessageBox.question(self, "Arrange like the schematic",
                                 "Move every part to where the schematic arrangement puts it on the table?\n"
                                 "Your current positions are replaced (Ctrl+Z undoes it).")
        if r != QMessageBox.Yes:
            return
        self._arrange()

    def _arrange(self):
        lay = self.scene.layout
        saved = {c.id: (c.x, c.y) for c in lay.components.values()}
        ch = {}
        placed = []
        for c in lay.components.values():
            el = lay.schematic.elements.get(c.sch_id)
            if el is None:
                continue
            others = lay.components
            lay.components = {o.id: o for o in placed}  # only already-arranged parts block holes
            x, y = self.scene._new_part_position(c, el, True)
            lay.components = others
            placed.append(type(c)(**{**c.__dict__, "x": x, "y": y}))
            ch[c.id] = ({"x": saved[c.id][0], "y": saved[c.id][1], "pinned": c.pinned},
                        {"x": x, "y": y, "pinned": False})
        if ch:
            self.scene.undo.push(SetFieldsCmd(self.scene, ch, "Arrange like schematic"))

    def show_clashes(self):
        self.tabs.setCurrentIndex(1)
        self.scene.clearSelection()
        for cid in self.scene.clashes:
            self.scene.comp_items[cid].setSelected(True)
        n = len(self.scene.clashes)
        self.statusBar().showMessage(f"{n} part(s) overlap another part" if n else "No overlapping parts", 6000)
        if n:
            self.zoom_to_selection()

    # ---- schematic <-> layout ----------------------------------------------------
    def request_fit(self, *tabs):
        self._fit_pending.update(tabs or (0, 1))
        QTimer.singleShot(0, self._fit_pending_views)

    def _fit_pending_views(self):
        """Fit a tab the first time it is shown after a file opens. A hidden tab
        has no real size yet, so fitting it then leaves it zoomed into a corner."""
        idx = self.tabs.currentIndex()
        if idx in self._fit_pending and self.isVisible():
            self._fit_pending.discard(idx)
            self.fit_current()

    def _ensure_view3d(self):
        """Build the 3D view on first use (it loads VTK, which takes a moment)."""
        if self.view3d is not None or self._view3d_loading:
            return
        lay = self.view3d_holder.layout()
        self._view3d_loading = True
        loading = QWidget()
        lv = QVBoxLayout(loading)
        lv.addStretch(1)
        msg = QLabel("Loading the 3D engine…")
        msg.setAlignment(Qt.AlignCenter)
        lv.addWidget(msg)
        bar = QProgressBar()
        bar.setRange(0, 0)  # busy
        bar.setFixedWidth(320)
        bar.setTextVisible(False)
        lv.addWidget(bar, 0, Qt.AlignHCenter)
        lv.addStretch(1)
        lay.addWidget(loading)
        for _ in range(3):  # paint the message before the import blocks for a moment
            QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
        try:
            from .view3d import make_view3d_widget
            self.view3d = make_view3d_widget(lambda: self.scene.layout, lambda: self.scene.latest,
                                             self.open_point_log)
        except Exception as e:  # pyvista missing or no OpenGL
            self._drop(loading)
            self._view3d_loading = False
            msg = QLabel(f"The 3D view needs pyvista and pyvistaqt:\n\n    py -3.13 -m pip install pyvista "
                         f"pyvistaqt\n\n({type(e).__name__}: {e})")
            msg.setAlignment(Qt.AlignCenter)
            msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(msg)
            self.view3d = False
            return
        self._drop(loading)
        self._view3d_loading = False
        lay.addWidget(self.view3d)
        self.scene.edited.connect(self.view3d.schedule)

    def _drop(self, widget):
        """Take a widget out now (deleteLater alone waits for the event loop)."""
        self.view3d_holder.layout().removeWidget(widget)
        widget.hide()
        widget.deleteLater()

    def _tab_changed(self, idx):
        QTimer.singleShot(0, self._fit_pending_views)
        sch = idx == 0
        if idx == 2:
            self._ensure_view3d()
        for d in self.layout_docks:
            d.setVisible(idx == 1)
        for a in self.layout_only:
            a.setVisible(idx == 1)
            a.setEnabled(idx == 1)
        for a in self.sch_only:
            a.setVisible(sch)
            a.setEnabled(sch)
        self.set_mode(MODE_SELECT)
        if idx == 2:
            self.statusBar().showMessage("3D: drag to rotate, wheel to zoom, Shift+drag to pan; F fits the board. "
                                         "It follows the Layout tab, where parts are moved.")
        if sch:
            self.sch_scene.refresh_status()
        else:
            sel = self.scene.selectedItems()
            if sel:
                self.view.ensureVisible(sel[0], 80, 80)

    def _schematic_changed(self):
        created = self.scene.sync_from_schematic()
        if created:
            waiting = [c for c in created if c in self.scene.off_table()]
            if waiting:
                self.statusBar().showMessage(
                    f"{len(waiting)} new part(s) are waiting below the table in the Layout tab: drag them into "
                    "place.", 8000)
        self._layers_changed()

    def _layers_changed(self):
        self.sch_scene.refresh_status()
        self.sch_scene.update()
        self.scene.update()

    def _layout_sel_to_sch(self):
        """Cross-probe: selecting parts in the layout selects their schematic elements."""
        if self._syncing_sel:
            return
        try:
            comps, _ = self.scene.selected_ids()
        except RuntimeError:
            return
        ids = {self.scene.layout.components[c].sch_id for c in comps}
        self._syncing_sel = True
        try:
            for eid, it in self.sch_scene.el_items.items():
                it.setSelected(eid in ids)
        finally:
            self._syncing_sel = False

    def _sch_sel_to_layout(self):
        if self._syncing_sel:
            return
        try:
            els, _ = self.sch_scene.selected_ids()
        except RuntimeError:
            return
        els = set(els)
        self._syncing_sel = True
        try:
            for cid, it in self.scene.comp_items.items():
                it.setSelected(bool(self.scene.layout.components[cid].sch_id) and
                               self.scene.layout.components[cid].sch_id in els)
        finally:
            self._syncing_sel = False

    # ---- power logger --------------------------------------------------------
    def add_point_on(self, beam_id: str, click: QPointF | None = None) -> MeasurementPoint:
        lay = self.scene.layout
        t = 0.5
        if click is not None and lay.points_on(beam_id):
            # midpoint is taken: put the new point where the user clicked
            line = self.scene.beam_items[beam_id].line()
            d = line.p2() - line.p1()
            L2 = d.x() ** 2 + d.y() ** 2 or 1
            q = click - line.p1()
            t = min(0.97, max(0.03, (q.x() * d.x() + q.y() * d.y()) / L2))
        pt = MeasurementPoint(id=new_id("mp"), label=lay.next_point_label(), beam_id=beam_id, t=t)
        self.scene.undo.push(AddPointCmd(self.scene, pt))
        if self.logbook:
            self.logbook.register_point(pt.id, pt.label)
        return lay.points[pt.id]

    def add_fiber_point(self, comp_id: str) -> MeasurementPoint:
        """A point at a fiber coupler's fiber end: the power after fiber coupling.
        One per coupler; clicking a coupler that has one opens its log."""
        lay = self.scene.layout
        have = [p for p in lay.points_at_part(comp_id) if not p.archived]
        if have:
            self.open_point_log(have[0].id)
            return have[0]
        pt = MeasurementPoint(id=new_id("mp"), label=lay.next_point_label(), beam_id=None, part_id=comp_id)
        self.scene.undo.push(AddPointCmd(self.scene, pt))
        if self.logbook:
            self.logbook.register_point(pt.id, pt.label)
        return lay.points[pt.id]

    def _ensure_logbook(self) -> bool:
        if self.logbook:
            return True
        if self._no_log:
            QMessageBox.information(self, "Power log", "This layout was opened without its power log, so nothing "
                                                       "is logged. Open it again to pick a log, or Save As to start "
                                                       "a new one.")
            return False
        QMessageBox.information(self, "Power log", "Save the layout first: the power log is stored next to it "
                                                   "(<layout>.logbook.sqlite).")
        self.save_as()
        return self.logbook is not None

    def open_point_log(self, pid: str):
        pt = self.scene.layout.points.get(pid)
        if pt is None or not self._ensure_logbook():
            return
        dlg = self._dialogs.get(pid)
        if dlg is None:
            lay = self.scene.layout
            b = lay.beams.get(pt.beam_id or "")
            part = lay.components.get(pt.part_id or "")
            if b:
                names = [lay.components[c].label or SYMBOLS[lay.components[c].type].name for c in (b.source, b.target)]
                desc = f"on beam {names[0]} → {names[1]}"
            elif part is not None:
                desc = f"out of the fiber of {part.label or SYMBOLS[part.type].name} (power after fiber coupling)"
                b = next((x for x in lay.beams.values() if x.target == part.id), None)  # for the wavelength
            else:
                desc = "not on a beam"
            dlg = MeasurementDialog(self.logbook, pt, desc, b.wavelength_nm if b else None, self)
            self._title_log(dlg)
            dlg.changed.connect(self.refresh_measurements)
            dlg.finished.connect(lambda _r, pid=pid: self._dialogs.pop(pid, None))
            self._dialogs[pid] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _title_log(self, dlg):
        """A log window's title, with the point's lab sheet name if it has one."""
        name = self.scene.layout.point_name(dlg.point.id)
        dlg.setWindowTitle(f"{dlg.point.label}{f' · {name}' if name else ''} — measurement log")

    def show_lab_sheet(self):
        """Printable sheet of chosen points: names, latest power, the layout picture."""
        from .labsheet import PICTURE_PX, LabSheetDialog
        if not [p for p in self.scene.layout.points.values() if not p.archived]:
            QMessageBox.information(self, "Lab sheet", "There are no measurement points yet: add some in the "
                                                       "Layout tab (M) first.")
            return
        dlg = LabSheetDialog(self.scene.layout, self.logbook, self.path.name if self.path else "untitled",
                             lambda: render_scene_image(self.scene, PICTURE_PX), self.store_lab_sheet, self)
        dlg.exec()

    def store_lab_sheet(self, sheet):
        from .scene import SetLabSheetCmd
        self.scene.undo.push(SetLabSheetCmd(self.scene, sheet))
        for d in self._dialogs.values():
            self._title_log(d)

    def _poll_logbook(self):
        """Refresh the power labels and open log windows when another program wrote to the log."""
        try:
            changed = self.logbook is not None and self.logbook.changed_on_disk()
        except Exception:  # noqa: BLE001 - a busy or vanished file: look again next time
            return
        if changed:
            self.refresh_measurements()
            for d in self._dialogs.values():
                d.reload()

    def refresh_measurements(self):
        lay = self.scene.layout
        latest = self.logbook.latest_two() if self.logbook else {}
        pics = self.logbook.picture_counts() if self.logbook else {}
        self.scene.set_latest(latest)
        self.points_panel.refresh(list(lay.points.values()), latest, pics)
        if getattr(self, "view3d", None):
            self.view3d.schedule()  # new readings show on the 3D sensors

    def ask_missing_log(self, path: Path) -> str:
        """The layout has measurement points but no log next to it: "choose",
        "new" or "none". Nobody can answer on a headless (test) display: new."""
        if QApplication.platformName() in ("offscreen", "minimal"):
            return "new"
        box = QMessageBox(QMessageBox.Question, "Power log",
                          f"No power log found for {path.name} (expected {logbook_path_for(path).name} next to it).",
                          QMessageBox.NoButton, self)
        box.setInformativeText("Its readings may be in a log file somewhere else. A new log is only created "
                               "when the first reading is logged.")
        choose = box.addButton("Choose log file…", QMessageBox.AcceptRole)
        new = box.addButton("Start new log", QMessageBox.YesRole)
        box.addButton("Open without log", QMessageBox.RejectRole)
        box.setDefaultButton(choose)
        box.exec()
        return "choose" if box.clickedButton() is choose else "new" if box.clickedButton() is new else "none"

    def _attach_for_open(self, path: Path):
        """Attach the layout's log; if it is missing and the layout has points, ask."""
        self._no_log = False
        lb = logbook_path_for(path)
        if lb.exists() or not self.scene.layout.points:
            return self._attach_logbook(path)
        while True:
            choice = self.ask_missing_log(path)
            if choice == "new":
                return self._attach_logbook(path)
            if choice == "none":
                self._no_log = True
                self._log_layout = path
                return self.refresh_measurements()
            src, _ = QFileDialog.getOpenFileName(self, "Choose the power log", str(path.parent),
                                                 "Power log (*.sqlite);;All files (*)")
            how = self.ask_copy_or_use(Path(src), path) if src else None
            if how == "copy":
                import shutil
                shutil.copy2(src, lb)
                return self._attach_logbook(path)
            if how == "use":
                return self._attach_logbook(path, Path(src))

    def ask_copy_or_use(self, src: Path, path: Path) -> str | None:
        """A log file picked for a layout: "copy" it next to the layout, "use" it where it is, or None."""
        box = QMessageBox(QMessageBox.Question, "Power log", f"Use {src.name} for {path.name}:",
                          QMessageBox.Cancel, self)
        copy = box.addButton(f"Copy it as {logbook_path_for(path).name}", QMessageBox.AcceptRole)
        use = box.addButton("Use it where it is", QMessageBox.YesRole)
        box.setInformativeText("A copy sits next to the layout and opens with it from now on. Used where it "
                               "is, new readings go into that file, for this session only.")
        box.exec()
        return "copy" if box.clickedButton() is copy else "use" if box.clickedButton() is use else None

    def _attach_logbook(self, path: Path, log_path: Path | None = None):
        self._no_log = False
        self._log_layout = path
        old = self.logbook
        new_path = log_path or logbook_path_for(path)
        if (old is not None and not old.in_memory and old.path.resolve() != new_path.resolve()
                and not new_path.exists()):
            # Save As to a new place: carry the history along
            import sqlite3
            dst = sqlite3.connect(str(new_path))
            old.db.backup(dst)
            dst.close()
        if old is not None:
            old.close()
        for d in list(self._dialogs.values()):
            d.close()
        self.logbook = Logbook(new_path)
        for pt in self.scene.layout.points.values():
            self.logbook.register_point(pt.id, pt.label)
        self.refresh_measurements()

    def export_csv(self):
        if not self._ensure_logbook():
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export power log", "power_log.csv", "CSV (*.csv)")
        if p:
            labels = {pid: pt.label for pid, pt in self.scene.layout.points.items()}
            labels.update({pid: lbl for pid, lbl in self.logbook.known_points() if pid not in labels})
            n = export_power_csv(self.logbook, labels, p)
            self.statusBar().showMessage(f"Exported {n} readings to {p}", 5000)

    def rotate_selected(self, delta):
        if self.on_schematic():
            self.sch_page.rotate_selected(delta)
            return
        comps, _ = self.scene.selected_ids()
        changes = {}
        for cid in comps:
            c = self.scene.layout.components[cid]
            changes[cid] = ({"angle": c.angle, "auto_angle": c.auto_angle},
                            {"angle": (c.angle + delta) % 360, "auto_angle": False})
        if changes and any(c["auto_angle"] for c, _n in changes.values()):
            self.statusBar().showMessage("Rotated by hand: automatic aiming is off for these parts (A turns it "
                                         "back on).", 6000)
        if changes:
            self.scene.undo.push(SetFieldsCmd(self.scene, changes, "Rotate"))

    def edit_table(self):
        t = self.scene.layout.table
        dlg = BoardDialog(t, self)
        if dlg.exec() == QDialog.Accepted:
            old_style = t.style
            dlg.apply(t)
            if self.view3d is not None and t.style != old_style:
                self.view3d.board_changed(old_style)
            self.scene.set_layout(self.scene.layout)
            self.update_snap_labels()
            self.request_fit(1)

    # ---- files ----------------------------------------------------------------
    def _update_title(self):
        name = self.path.name if self.path else "untitled"
        try:
            star = "" if self.scene.undo.isClean() else " *"
        except RuntimeError:  # undo stack already destroyed during shutdown
            return
        self.setWindowTitle(f"{name}{star} — Optical Layout Designer")

    def save_prompt(self) -> QMessageBox:
        """Word-style: Save / Don't Save / Cancel; Enter saves, Esc cancels."""
        box = QMessageBox(QMessageBox.Warning, "Optical Layout Designer",
                          f"Do you want to save changes to {self.path.name if self.path else 'untitled'}?",
                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, self)
        box.button(QMessageBox.Discard).setText("Don't Save")
        box.setDefaultButton(QMessageBox.Save)
        box.setEscapeButton(QMessageBox.Cancel)
        return box

    def _confirm_discard(self) -> bool:
        """True when it is fine to drop the current layout (saved first if asked)."""
        if self.scene.undo.isClean():
            return True
        r = self.save_prompt().exec()
        if r == QMessageBox.Save:
            self.save_file()  # Save As when untitled; cancelling that keeps the window
            return self.scene.undo.isClean()
        return r == QMessageBox.Discard

    def new_file(self):
        if self._confirm_discard():
            self.scene.set_layout(Layout())
            self.sch_scene.set_layout(self.scene.layout)
            self.props.show_obj(None)
            self.path = None
            self._no_log, self._log_layout = False, None
            if self.logbook:
                self.logbook.close()
                self.logbook = None
            self.switcher.refresh()
            self.refresh_measurements()
            self._update_title()
            self.request_fit()

    def _last_folder(self) -> Path | None:
        f = self.settings.value("last_folder", "")
        return Path(f) if f else None

    def switch_to(self, p: Path) -> bool:
        """Open another layout (the folder drop-down); False if the user cancelled."""
        if not self._confirm_discard():
            return False
        self.open_path(p)
        return True

    def open_file(self):
        if not self._confirm_discard():
            return
        start = self.path.parent if self.path else self._last_folder()
        p, _ = QFileDialog.getOpenFileName(self, "Open layout", str(start or ""), "Layout (*.json)")
        if p:
            self.open_path(p)

    def open_path(self, p):
        if self.logbook:
            self.logbook.close()
            self.logbook = None
        lay = Layout.load(p)
        if lay.components and not lay.schematic.elements:
            lay.schematic_from_layout()  # older file: build its schematic once
        self.scene.set_layout(lay)
        self.sch_scene.set_layout(self.scene.layout)
        self.scene.sync_from_schematic()
        self.props.show_obj(None)  # the board summary of the file just opened
        self.update_snap_labels()
        if self.view3d:
            self.view3d.reset_for_new_file()
        self.path = Path(p)
        self._attach_for_open(self.path)
        self._update_title()
        self.settings.setValue("last_folder", str(self.path.parent))
        self.switcher.refresh()
        lay = self.scene.layout
        self.tabs.setCurrentIndex(0 if lay.schematic.elements and not lay.components else 1)
        self.request_fit()
        self.scene.undo.setClean()

    def save_file(self):
        if self.path is None:
            return self.save_as()
        self.scene.layout.save(self.path)
        self.settings.setValue("last_folder", str(self.path.parent))
        if self._log_layout != self.path or (self.logbook is None and not self._no_log):  # new file or Save As
            self._attach_logbook(self.path)
            self.switcher.refresh()
        else:
            for pt in self.scene.layout.points.values():
                self.logbook.register_point(pt.id, pt.label)
        self.scene.undo.setClean()
        self._update_title()

    def save_as(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save layout", "layout.json", "Layout (*.json)")
        if p:
            self.path = Path(p)
            self.save_file()

    def export(self, kind):
        if self.tabs.currentIndex() == 2:  # 3D: save what the view shows
            if self.view3d:
                p, _ = QFileDialog.getSaveFileName(self, "Save 3D view", "board_3d.png", "PNG (*.png)")
                if p:
                    self.view3d.plotter.screenshot(p)
            return
        sch = self.on_schematic()
        p, _ = QFileDialog.getSaveFileName(self, "Export", f"{'schematic' if sch else 'layout'}.{kind}", f"*.{kind}")
        if p:
            export_scene(self.sch_scene if sch else self.scene, p)

    def _web_state(self, state: str) -> None:
        """The dot in front of the web status: green serving, grey off or served elsewhere, red unavailable."""
        color = {"green": "#2e9e44", "grey": "#9aa0a6", "red": "#d62728"}[state]
        self.web_dot.setStyleSheet(f"color: {color}; font-size: 14px")
        self.web_corner.adjustSize()
        self.menuBar().setCornerWidget(self.web_corner, Qt.TopRightCorner)  # makes the menu bar re-measure it

    def set_web(self, on: bool, remember: bool = True) -> None:
        """Start or stop serving the web pages (see web/embed.py)."""
        if remember:
            self.settings.setValue("web_on", bool(on))
        self.a_web.setChecked(on)
        if not on:
            if self.web is not None:
                self.web.stop()
            self.web_lbl.setText("Web: off")
            self._web_state("grey")
            self.web_lbl.setToolTip("File > Web access turns it on")
            return
        if self.web is not None and self.web.status == "running":
            return
        try:
            from web.embed import WebShare
        except ImportError as e:
            self.web_lbl.setText("Web: unavailable")
            self.web_lbl.setToolTip(f"The web folder can't be loaded ({e})")
            self._web_state("red")
            return
        self.web = WebShare(self.web_config)  # exactly the folders in web/config.json
        status = self.web.start()
        url = self.web.url
        if status == "running":
            self.web_lbl.setText(f'Web: <a href="{url}">{url}</a>')
            self._web_state("green")
            self.web_lbl.setToolTip("Other PCs on the lab network open this address. Right-click or select to copy.")
        elif status == "busy":
            self.web_lbl.setText(f'Web: already running at <a href="{url}">{url}</a>')
            self._web_state("grey")
            self.web_lbl.setToolTip("Another window of this app, or start_web.bat, is serving the pages on this "
                                    "port already.")
        else:
            self.web_lbl.setText("Web: unavailable")
            self.web_lbl.setToolTip(self.web.error)
            self._web_state("red")
            self.statusBar().showMessage(f"Web access unavailable: {self.web.error}", 10000)

    def closeEvent(self, e):
        if self._confirm_discard():
            if self.web is not None:
                self.web.stop()
            e.accept()
        else:
            e.ignore()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._fit_pending_views)


def render_scene_image(scene: LayoutScene, width_px: int) -> QImage:
    """The board as export_scene draws it, as an image width_px wide."""
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        src = export_rect(scene)
        export_scene(scene, tmp, px_per_mm=width_px / max(src.width(), 1))
        return QImage(tmp)
    finally:
        os.remove(tmp)


def export_rect(scene) -> QRectF:
    """The area an export shows: the board with its labels and legend."""
    if hasattr(scene, "table_rect"):
        m = 30 if getattr(scene, "show_coords", False) else 10  # room for the hole letters / numbers
        src = scene.table_rect().adjusted(-m, -m, m, m + 10)
        if hasattr(scene, "name_rect"):
            src = src.united(scene.name_rect().adjusted(-5, -5, 5, 5))
        if hasattr(scene, "legend_rect") and not scene.legend_rect().isEmpty():
            src = src.united(scene.legend_rect().adjusted(-5, -5, 5, 5))
        for it in getattr(scene, "point_items", {}).values():  # callouts off the board (fiber ends)
            src = src.united(it.sceneBoundingRect().adjusted(-5, -5, 5, 5))
        return src
    return scene.items_rect().adjusted(-30, -30, 30, 30)  # schematic: everything drawn, with a margin


def export_scene(scene: LayoutScene, path: str, px_per_mm: float = 4.0) -> None:
    """Export the table area to SVG (vector, mm units) or PNG/JPG."""
    sel = scene.selectedItems()
    scene.clearSelection()
    rats = getattr(scene, "show_ratsnest", None)
    if rats is not None:
        scene.show_ratsnest = False
    if hasattr(scene, "begin_export"):  # size labels for the export, not the current zoom
        scene.begin_export()
    src = export_rect(scene)
    if path.lower().endswith(".svg"):
        from PySide6.QtSvg import QSvgGenerator
        gen = QSvgGenerator()
        gen.setFileName(path)
        gen.setTitle("Optical layout")
        gen.setSize(QSize(int(src.width()), int(src.height())))
        gen.setViewBox(QRectF(0, 0, src.width(), src.height()))
        gen.setResolution(int(25.4))  # 1 SVG unit = 1 mm
        p = QPainter(gen)
        scene.render(p, QRectF(0, 0, src.width(), src.height()), src)
        p.end()
    else:
        img = QImage(int(src.width() * px_per_mm), int(src.height() * px_per_mm), QImage.Format_ARGB32)
        img.fill(Qt.white)
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        scene.render(p, QRectF(0, 0, img.width(), img.height()), src)
        p.end()
        img.save(path)
    for it in sel:
        it.setSelected(True)
    if rats is not None:
        scene.show_ratsnest = rats
    if hasattr(scene, "end_export"):
        scene.end_export()


def install_error_handler(win_getter) -> None:
    """Report unexpected errors in a message box and keep running, instead of
    the app disappearing. Each error is also written to a log file next to the
    settings (path shown in the message)."""
    import traceback
    log = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or ".") / "errors.log"
    showing = [False]

    def hook(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))
        sys.__stderr__ and sys.__stderr__.write(text)
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as fh:
                from datetime import datetime
                fh.write(f"---- {datetime.now():%Y-%m-%d %H:%M:%S}\n{text}\n")
        except OSError:
            pass
        if showing[0]:
            return  # one box at a time
        showing[0] = True
        try:
            box = QMessageBox(win_getter())
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Something went wrong")
            box.setText(f"{etype.__name__}: {value}\n\nThe app keeps running; Ctrl+Z undoes the last edit if the "
                        "drawing looks wrong. Save soon to be safe.")
            box.setDetailedText(text + f"\nLogged to {log}")
            box.exec()
        finally:
            showing[0] = False

    sys.excepthook = hook


def set_gl_format() -> None:
    """The OpenGL format the 3D tab (VTK) needs, made the default before any
    window exists. pyvistaqt sets it only when the 3D tab is first opened, which
    is too late on macOS: there the main window already has an old OpenGL 2.1
    context and the 3D view stays black."""
    from PySide6.QtGui import QSurfaceFormat
    fmt = QSurfaceFormat()  # desktop OpenGL 3.2 core, as pyvistaqt asks for
    fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setVersion(3, 2)
    fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
    for setter in (fmt.setRedBufferSize, fmt.setGreenBufferSize, fmt.setBlueBufferSize, fmt.setAlphaBufferSize,
                   fmt.setDepthBufferSize):
        setter(8)
    fmt.setStencilBufferSize(0)
    fmt.setSamples(0)  # VTK does its own anti-aliasing
    QSurfaceFormat.setDefaultFormat(fmt)


def main():
    set_gl_format()  # before the QApplication, as Qt asks
    app = QApplication(sys.argv)
    app.setApplicationName("Optical Layout Designer")
    install_error_handler(lambda: QApplication.activeWindow())
    w = MainWindow(sys.argv[1] if len(sys.argv) > 1 else None)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
