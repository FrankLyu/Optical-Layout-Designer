"""QGraphicsScene that mirrors a Layout, plus the undoable edit commands.

All edits go through LayoutScene methods so the model and the drawing stay in
sync; the QUndoCommands below call those methods.
"""

from __future__ import annotations

import math
from copy import deepcopy

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath,
                           QPainterPathStroker, QPen, QPolygonF, QUndoCommand, QUndoStack)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene

from . import labels
from .labels import draw_halo_text
from .model import SCH_KINDS, Beam, Component, Layout, MeasurementPoint, kind_of_type
from .orient import auto_angle
from .mounts3d import DRILLED_STYLES
from .symbols import SYMBOLS

# Text and callouts scale with the zoom like the drawing, but are kept between
# a smallest and largest size on screen so they stay readable when the whole
# board is fitted and don't swamp the parts when zoomed in. All sizes are
# multiplied by the View → text size factor (A+ / A−).
LABEL_MM, LABEL_MIN_PX, LABEL_MAX_PX = 7.5, 13, 22  # part labels
POINT_MM, POINT_MIN_PX, POINT_MAX_PX = 8.0, 14, 26  # measurement-point callouts (one text line)
EXPORT_VIEW_PX = 1600  # exports look like the board fitted into this many pixels
STAGING_GAP = 40  # mm between the table edge and the "new parts" strip
BEAM_WIDTH = 1.6  # mm
BEAM_MIN_PX = 2.2  # beams never get thinner than this on screen
CHANGE_ALERT_PCT = 10.0  # colour a marker when power changed by more than this


def block_outline(c: Component, style: str) -> "QPolygonF | None":
    """The adapter or pedestal under a part on a board drilled per part (PyOpticL,
    LightFlow), in scene coordinates."""
    from .mounts3d import _to_layout, mount_block
    b = mount_block(c.type, style)
    if b is None:
        return None
    return QPolygonF([QPointF(*_to_layout(c.x, c.y, lx, ly, c.angle))
                      for lx, ly in ((b.x0, b.y0), (b.x1, b.y0), (b.x1, b.y1), (b.x0, b.y1))])


class ComponentItem(labels.CachedBounds, QGraphicsItem):
    def __init__(self, comp: Component):
        super().__init__()
        self.comp = comp
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.label_px = LABEL_MM
        self.label_rect: QRectF | None = None
        self.sync()

    @property
    def sym(self):
        return SYMBOLS[self.comp.type]

    def sync(self) -> None:
        self.geometry_changed()
        self.setPos(self.comp.x, self.comp.y)
        c = self.comp
        tip = f"<b>{c.label or '—'}</b><br>{SYMBOLS[c.type].name}"
        if c.part_number:
            tip += f"<br>{c.part_number}"
        tip += f"<br>x {c.x:.1f} mm, y {c.y:.1f} mm, {c.angle:.1f}°" + (" (auto)" if c.auto_angle else "")
        self.setToolTip(tip)
        self.update()

    def _body_rect(self) -> QRectF:
        # rotated symbol bounds, in item coordinates
        b = self.sym.bounds
        a = math.radians(-self.comp.angle)
        pts = [b.topLeft(), b.topRight(), b.bottomLeft(), b.bottomRight()]
        rot = [QPointF(p.x() * math.cos(a) - p.y() * math.sin(a),
                       p.x() * math.sin(a) + p.y() * math.cos(a)) for p in pts]
        xs, ys = [p.x() for p in rot], [p.y() for p in rot]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def _label_px(self) -> float:
        return self.label_px

    def _label_rect(self) -> QRectF:
        """Where the label sits, in item coordinates (chosen by the scene so it
        avoids other parts, beams and labels; below the part until then)."""
        if self.label_rect is not None:
            return self.label_rect if not self.label_rect.isEmpty() else QRectF(0, 0, 0, 0)
        body = self._body_rect()
        w, h = labels.text_size(self.comp.label, self.label_px)
        return QRectF(-w / 2, body.bottom() + 1, w, h)

    def body_scene_rect(self) -> QRectF:
        return self._body_rect().translated(self.comp.x, self.comp.y)

    def outline(self) -> "QPolygonF":
        """What the part covers on the table, rotated, in scene coordinates (for
        overlap checks): the real mount's footprint when its CAD is in the
        library, else the 2D drawing."""
        from .mounts3d import footprint, pillar_flange, pillar_xy
        fp = footprint(self.comp.type)
        b = (QRectF(fp[0], fp[2], fp[1] - fp[0], fp[3] - fp[2]) if fp is not None else self.sym.bounds)
        b = b.adjusted(1, 1, -1, -1)
        a = math.radians(-self.comp.angle)
        pts = []
        for q in (b.topLeft(), b.topRight(), b.bottomRight(), b.bottomLeft()):
            pts.append(QPointF(self.comp.x + q.x() * math.cos(a) - q.y() * math.sin(a),
                               self.comp.y + q.x() * math.sin(a) + q.y() * math.cos(a)))
        poly = QPolygonF(pts)
        sc = self.scene()
        side = pillar_flange(self.comp.type, sc.layout.table.style) if sc is not None else None
        if side:  # an Olego pillar's flange sits square to the board under the mount's base
            h = side / 2 - 0.5
            px, py = pillar_xy(self.comp.type, self.comp.x, self.comp.y, self.comp.angle)
            poly = poly.united(QPolygonF([QPointF(px + dx, py + dy)
                                          for dx, dy in ((-h, -h), (h, -h), (h, h), (-h, h))]))
        if sc is not None:
            r = block_outline(self.comp, sc.layout.table.style)
            if r is not None:  # the printed adapter or machined pedestal under the mount
                poly = poly.united(r)
        return poly

    def compute_bounds(self) -> QRectF:
        return self._body_rect().united(self._label_rect()).adjusted(-2, -2, 2, 2)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self._body_rect().adjusted(-1.5, -1.5, 1.5, 1.5))
        return path

    def paint(self, p: QPainter, option, widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        p.save()
        p.rotate(-self.comp.angle)
        self.sym.draw(p)
        p.restore()
        if self.comp.type == "laser":
            self._paint_laser_name(p)
        elif self.comp.label:
            draw_halo_text(p, self._label_rect(), self.comp.label, self._label_px())
        sc = self.scene()
        if sc is not None and self.comp.id in sc.clashes:
            p.setPen(QPen(QColor("#d62728"), 0.9, Qt.DashLine))
            p.setBrush(QColor(214, 39, 40, 28))
            p.drawRect(self._body_rect().adjusted(-1, -1, 1, 1))
        if self.isSelected():
            p.setPen(QPen(QColor("#1f6fd1"), 0.6, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self._body_rect().adjusted(-2, -2, 2, 2))

    def _paint_laser_name(self, p: QPainter) -> None:
        """A laser carries its name inside its box (as in the reference drawing)."""
        from .symbols import LASER_BOX
        box = LASER_BOX.adjusted(8, 8, -8, -8)
        name = self.comp.label or "LASER"
        px = min(self.label_px * 1.15, box.height() * 0.3)
        w, _h = labels.text_size(name, px)
        if w > box.width():
            px *= box.width() / w
        p.save()
        p.rotate(-self.comp.angle)
        a = self.comp.angle % 360
        if 90 < a < 270:  # keep the text upright
            p.rotate(180)
            box = QRectF(-box.right(), -box.bottom(), box.width(), box.height())
        f = QFont("Arial")
        f.setPixelSize(max(1, round(px * 100)))
        f.setBold(True)
        p.translate(box.topLeft())
        p.scale(0.01, 0.01)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(0, 0, box.width() * 100, box.height() * 100), Qt.AlignCenter, name)
        p.restore()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            return self.scene().snap(value)
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.comp.x, self.comp.y = self.pos().x(), self.pos().y()
            self.scene().component_moved(self.comp.id)
        return super().itemChange(change, value)


class BeamItem(labels.CachedBounds, QGraphicsItem):
    def __init__(self, beam: Beam, scene: "LayoutScene"):
        super().__init__()
        self.beam = beam
        self._scene = scene
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setZValue(1)
        self.len_rect: QRectF | None = None  # beam length label, placed by the scene
        self.len_text = ""
        self.len_px = 6.0

    def line(self) -> QLineF:
        a = self._scene.layout.components[self.beam.source]
        b = self._scene.layout.components[self.beam.target]
        return QLineF(a.x, a.y, b.x, b.y)

    def refresh(self) -> None:
        self.geometry_changed()
        self.update()

    def compute_bounds(self) -> QRectF:
        m = self._scene.beam_width() * 2 + 8
        r = QRectF(self.line().p1(), self.line().p2()).normalized().adjusted(-m, -m, m, m)
        return r.united(self.len_rect) if self.len_rect is not None else r

    def shape(self) -> QPainterPath:
        path = QPainterPath(self.line().p1())
        path.lineTo(self.line().p2())
        s = QPainterPathStroker()
        s.setWidth(4)
        return s.createStroke(path)

    def paint(self, p: QPainter, option, widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(self.beam.color)
        ln = self.line()
        w = self._scene.beam_width()
        if self.isSelected():
            p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 80), w * 3.2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(ln)
        p.setPen(QPen(color, w, Qt.SolidLine, Qt.FlatCap))
        p.drawLine(ln)
        # direction arrow(s), as in the schematic: one at the middle, more on long runs
        a = w * 3.2
        L = ln.length()
        if L > a * 5:
            u = QPointF(ln.dx() / L, ln.dy() / L)
            n = QPointF(-u.y(), u.x())
            k = max(1, int(L // 260))
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            for i in range(k):
                m = ln.pointAt((i + 0.5) / k) + u * (a * 0.4)
                p.drawPolygon(QPolygonF([m, m - u * a * 1.3 + n * a * 0.6, m - u * a * 1.3 - n * a * 0.6]))
        if self.len_rect is not None and self._scene.show_lengths:
            draw_halo_text(p, self.len_rect, self.len_text, self.len_px, bold=False, color=color.darker(160).name())


class PointItem(labels.CachedBounds, QGraphicsItem):
    """Measurement-point marker with a callout box. Drag the marker to slide it
    along its beam; click it (or its box) to open its log.

    The box sits off the marker, tied to it by a thin leader line; the scene
    picks the spot so it doesn't cover parts, labels or other callouts. Sizes
    scale with the zoom within limits (see POINT_MM) and follow A+ / A-."""

    def __init__(self, point: MeasurementPoint, scene: "LayoutScene"):
        super().__init__()
        self.point = point
        self._scene = scene
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setZValue(20)
        self.setCursor(Qt.PointingHandCursor)
        self._press_t = None
        self._moved = False
        self.u = POINT_MM
        self.box: QRectF | None = None  # callout box, item coordinates (set by the scene)
        self.refresh()

    def set_screen_mode(self, on: bool) -> None:  # kept for older callers; sizes now come from the scene
        pass

    def _u(self) -> float:
        return self.u

    def refresh(self) -> None:
        self.geometry_changed()
        self.setPos(*self._scene.layout.point_xy(self.point))
        self.update()

    def _texts(self) -> tuple[str, str]:
        latest = self._scene.latest.get(self.point.id)
        from .logbook import format_power
        power = format_power(latest[0].power_mw) if latest else ""
        eff = self._scene.layout.coupling_efficiency(self.point, self._scene.latest)
        if eff is not None:
            power += f", {eff * 100:.0f} % coupled"
        name = self._scene.layout.point_name(self.point.id)
        return self.point.label + (f" · {name}" if name else ""), power

    def _change_pct(self) -> float | None:
        latest = self._scene.latest.get(self.point.id)
        if not latest or latest[1] is None or latest[1].power_mw == 0:
            return None
        return (latest[0].power_mw - latest[1].power_mw) / latest[1].power_mw * 100

    def box_size(self) -> tuple[float, float]:
        u = self.u
        label, power = self._texts()
        w1, h1 = labels.text_size(label, u, bold=True)
        w2, _h2 = labels.text_size(power, u, bold=False) if power else (0, 0)
        lines = 2 if power else 1
        return max(w1, w2) + 0.7 * u, lines * h1 + 0.35 * u

    def _geom(self):
        u = self.u
        r = 0.45 * u
        label, power = self._texts()
        box = self.box
        if box is None:
            w, h = self.box_size()
            box = QRectF(r * 1.6, -r * 1.6 - h, w, h)
        return u, r, box, label, power

    def compute_bounds(self) -> QRectF:
        u, r, box, _l, _p = self._geom()
        return QRectF(-r * 1.8, -r * 1.8, r * 3.6, r * 3.6).united(box).adjusted(-1, -1, 1, 1)

    def shape(self) -> QPainterPath:
        u, r, box, _l, _p = self._geom()
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), r * 1.4, r * 1.4)
        path.addRect(box)
        return path

    def paint(self, p: QPainter, option, widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        u, r, box, label, power = self._geom()
        pct = self._change_pct()
        ring = QColor("#222222")
        if pct is not None and abs(pct) >= CHANGE_ALERT_PCT:
            ring = QColor("#d62728") if pct < 0 else QColor("#2ca02c")
        lw = 0.11 * u
        # leader line from the marker's edge to the nearest point of the box
        tip = labels.nearest_on_rect(box, QPointF(0, 0))
        d = (tip.x() ** 2 + tip.y() ** 2) ** 0.5
        if d > r * 1.2:
            p.setPen(QPen(QColor("#555555"), lw * 0.8))
            p.drawLine(QPointF(tip.x() * r / d, tip.y() * r / d), tip)
        if self.point.archived:
            p.setPen(QPen(QColor("#888888"), lw * 0.7, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
        else:
            p.setPen(QPen(ring, lw))
            p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(0, 0), r, r)
        p.setBrush(QBrush(ring))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(0, 0), r * 0.35, r * 0.35)
        p.setPen(QPen(QColor(0, 0, 0, 90), lw * 0.6))
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.drawRoundedRect(box, 0.2 * u, 0.2 * u)
        _w, lh = labels.text_size(label, u)
        pad = 0.35 * u
        f = QFont("Arial")
        f.setPixelSize(max(1, round(u * 100)))  # lay out at 100x and scale down: crisp at any zoom
        f.setBold(True)
        p.save()
        p.translate(box.left() + pad, box.top() + 0.175 * u)
        p.scale(0.01, 0.01)
        p.setFont(f)
        p.setPen(QPen(QColor("#111111")))
        p.drawText(QRectF(0, 0, box.width() * 100, lh * 100), Qt.AlignLeft | Qt.AlignVCenter, label)
        if power:
            f.setBold(False)
            p.setFont(f)
            p.setPen(QPen(ring if pct is not None and abs(pct) >= CHANGE_ALERT_PCT else QColor("#333333")))
            p.drawText(QRectF(0, lh * 100, box.width() * 100, lh * 100), Qt.AlignLeft | Qt.AlignVCenter, power)
        p.restore()
        if self.isSelected():
            p.setPen(QPen(QColor("#1f6fd1"), lw, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(0, 0), r * 1.6, r * 1.6)
            p.drawRoundedRect(box.adjusted(-lw * 2, -lw * 2, lw * 2, lw * 2), 0.25 * u, 0.25 * u)

    # drag along the beam -----------------------------------------------------------
    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        self._press_t = self.point.t
        self._moved = False
        e.accept()

    def mouseMoveEvent(self, e):
        b = self._scene.layout.beams.get(self.point.beam_id or "")
        if b is None:
            return
        line = self._scene.beam_items[b.id].line()
        d = line.p2() - line.p1()
        L2 = d.x() ** 2 + d.y() ** 2
        if L2 == 0:
            return
        q = e.scenePos() - line.p1()
        t = min(0.97, max(0.03, (q.x() * d.x() + q.y() * d.y()) / L2))
        if abs(t - self.point.t) > 1e-4:
            self._moved = True
            self.point.t = t
            self.refresh()

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self._moved and self._press_t is not None:
            t_new = self.point.t
            self.point.t = self._press_t
            self._scene.undo.push(SetFieldsCmd(self._scene, {self.point.id: ({"t": self._press_t},
                                                                             {"t": t_new})}, "Move point"))
            self._scene.schedule_annotations()
        elif e.button() == Qt.LeftButton:
            self._scene.point_clicked.emit(self.point.id)
        self._press_t = None


class PartPair(tuple):
    """Two selected parts: Properties shows the optical path between them."""

    def __new__(cls, a: str, b: str):
        return super().__new__(cls, (a, b))


class LayoutScene(QGraphicsScene):
    selection_info = Signal(object)  # Component | Beam | MeasurementPoint | None
    edited = Signal()
    point_clicked = Signal(str)

    SNAP_HOLES, SNAP_HALF, SNAP_FREE = "holes", "half", "free"

    def __init__(self, layout: Layout | None = None):
        super().__init__()
        self.undo = QUndoStack(self)
        self.snap_mode = self.SNAP_HOLES
        self.comp_items: dict[str, ComponentItem] = {}
        self.beam_items: dict[str, BeamItem] = {}
        self.point_items: dict[str, PointItem] = {}
        self.latest: dict = {}  # point id -> (latest PowerRecord, previous or None)
        self.show_archived = False
        self.show_ratsnest = True
        self.text_scale = 1.0
        self.free_drag = False
        self.clashes: set[str] = set()  # parts whose outlines overlap another part
        self.view_zoom = 1.0  # screen pixels per mm in the view (tracked while painting)
        self.show_lengths = False  # beam-segment lengths on the drawing (View menu)
        self.show_coords = True  # hole column letters / row numbers around the board
        self.exporting = False
        self._ann_timer = QTimer(self)
        self._ann_timer.setSingleShot(True)
        self._ann_timer.setInterval(0)
        self._ann_timer.timeout.connect(self.layout_annotations)
        self._parked: dict[str, Component] = {}  # parts of deleted schematic elements, kept for undo
        self.selectionChanged.connect(self._on_selection)
        self.set_layout(layout or Layout())

    # ---- whole-layout -----------------------------------------------------
    def set_layout(self, layout: Layout) -> None:
        self.clear()
        self.comp_items.clear()
        self.beam_items.clear()
        self.point_items.clear()
        self.layout = layout
        t = layout.table
        self.setSceneRect(QRectF(-80, -80, t.width + 160, t.height + 260))
        for c in layout.components.values():
            self._add_comp_item(c)
        for b in layout.beams.values():
            self._add_beam_item(b)
        for pt in layout.points.values():
            self._sync_point_item(pt.id)
        self._parked.clear()
        self.undo.clear()
        self.orient_all()
        self.check_clashes()
        self.layout_annotations()
        self.update()

    def board_path(self) -> QPainterPath:
        """The board's outline: its rectangle minus any cut-outs."""
        t = self.layout.table
        path = QPainterPath()
        path.addRect(self.table_rect())
        for cx, cy, cw, ch in t.cutouts:
            hole = QPainterPath()
            hole.addRect(QRectF(cx, cy, cw, ch))
            path = path.subtracted(hole)
        return path

    def table_rect(self) -> QRectF:
        return QRectF(0, 0, self.layout.table.width, self.layout.table.height)

    # ---- snapping ---------------------------------------------------------
    def snap(self, pt: QPointF) -> QPointF:
        t = self.layout.table
        if self.snap_mode == self.SNAP_FREE or self.free_drag:
            return pt
        pitch = t.hole_pitch if self.snap_mode == self.SNAP_HOLES else t.hole_pitch / 2
        off = t.hole_offset
        return QPointF(off + round((pt.x() - off) / pitch) * pitch,
                       off + round((pt.y() - off) / pitch) * pitch)

    # ---- low-level mutators (used by commands) -----------------------------
    def _add_comp_item(self, c: Component) -> None:
        item = ComponentItem(c)
        self.addItem(item)
        self.comp_items[c.id] = item

    def _add_beam_item(self, b: Beam) -> None:
        item = BeamItem(b, self)
        self.addItem(item)
        self.beam_items[b.id] = item

    # ---- labels and callouts --------------------------------------------------
    def beam_width(self) -> float:
        return max(BEAM_WIDTH, BEAM_MIN_PX / max(self.view_zoom, 1e-6))

    def set_view_zoom(self, z: float) -> None:
        if z > 0 and abs(z - self.view_zoom) > 0.01 * self.view_zoom:
            self.view_zoom = z
            self.schedule_annotations()

    def schedule_annotations(self) -> None:
        """Re-place labels and callouts once the current burst of edits is done."""
        self._ann_timer.start()

    def layout_annotations(self) -> None:
        """Size part labels and measurement callouts for the current zoom, then
        place each where it covers the fewest parts, beams and other labels."""
        z, k = self.view_zoom, self.text_scale
        lab = labels.clamp_px(LABEL_MM * k, z, LABEL_MIN_PX * k, LABEL_MAX_PX * k)
        u = labels.clamp_px(POINT_MM * k, z, POINT_MIN_PX * k, POINT_MAX_PX * k)
        lay = self.layout
        tr = self.table_rect()
        placer = labels.Placer(tr)
        for a, b in ((tr.topLeft(), tr.topRight()), (tr.topRight(), tr.bottomRight()),
                     (tr.bottomRight(), tr.bottomLeft()), (tr.bottomLeft(), tr.topLeft())):
            placer.add_segment(QLineF(a, b))  # keep text off the board edge
        self.name_px = lab * 0.85
        bodies = {}
        for cid, it in self.comp_items.items():
            bodies[cid] = it.body_scene_rect()
            placer.add_body(bodies[cid])
        for b in lay.beams.values():
            a, c = lay.components.get(b.source), lay.components.get(b.target)
            if a is not None and c is not None:
                placer.add_segment(QLineF(a.x, a.y, c.x, c.y))
        # markers block labels too
        pts = [it for it in self.point_items.values()]
        for it in pts:
            r = 0.45 * u * 1.5
            placer.add_body(QRectF(it.pos().x() - r, it.pos().y() - r, 2 * r, 2 * r))
        order = sorted(self.comp_items.values(), key=lambda it: (-bodies[it.comp.id].width() * bodies[it.comp.id].height()))
        for it in order:
            it.geometry_changed()
            it.label_px = lab
            if not it.comp.label or it.comp.type == "laser":  # lasers are named inside their box
                it.label_rect = QRectF()
                continue
            w, h = labels.text_size(it.comp.label, lab)
            cands = labels.around(bodies[it.comp.id], w, h, lab * 0.2)
            i = placer.place(cands, ignore=bodies[it.comp.id])
            it.label_rect = cands[i].translated(-it.comp.x, -it.comp.y)
            it.update()
        self.coord_px = labels.clamp_px(5.5 * k, z, 9 * k, 14 * k)
        for it in sorted(pts, key=lambda it: it.point.label):
            it.geometry_changed()
            it.u = u
            w, h = it.box_size()
            pos = it.pos()
            cands = labels.callout_spots(pos, w, h, u)
            leaders = [QLineF(pos, labels.nearest_on_rect(c, pos)) for c in cands]
            i = placer.place(cands, leaders=leaders)
            it.box = cands[i].translated(-pos.x(), -pos.y())
            it.update()
        len_px = lab * 0.8
        for it in self.beam_items.values():
            it.len_rect = None
            L = lay.beam_length(it.beam)
            if self.show_lengths and L > 1:
                it.len_text = f"{L:.1f} mm" if L < 100 else f"{L:.0f} mm"
                it.len_px = len_px
                w, h = labels.text_size(it.len_text, len_px, bold=False)
                ln = it.line()
                u = QPointF(ln.dx() / L, ln.dy() / L)
                n = QPointF(-u.y(), u.x())
                cands = []
                for t in (0.5, 0.35, 0.65, 0.2, 0.8):
                    m = ln.pointAt(t)
                    for side in (1, -1):
                        # centre the text box just off the beam, on one side
                        off = n * side * (abs(n.x()) * w / 2 + abs(n.y()) * h / 2 + h * 0.3)
                        c = m + off
                        cands.append(QRectF(c.x() - w / 2, c.y() - h / 2, w, h))
                i = placer.place(cands, max_cost=0.6)  # no room (short beam between parts): leave it out
                it.len_rect = cands[i] if i >= 0 else None
            it.refresh()

    def begin_export(self, out_width_px: float | None = None) -> None:
        """Size text for an export as if the board were fitted to EXPORT_VIEW_PX."""
        self._saved_zoom = self.view_zoom
        self.exporting = True
        t = self.layout.table
        self.view_zoom = (out_width_px or EXPORT_VIEW_PX) / max(t.width, t.height * 1.5, 1)
        self.layout_annotations()

    def end_export(self) -> None:
        self.exporting = False
        self.view_zoom = getattr(self, "_saved_zoom", self.view_zoom)
        self.layout_annotations()

    def _sync_point_item(self, pid: str) -> None:
        """Create, refresh or drop the marker for a point to match the model."""
        pt = self.layout.points.get(pid)
        visible = pt is not None and (not pt.archived or self.show_archived)
        item = self.point_items.get(pid)
        if visible and item is None:
            item = PointItem(pt, self)
            self.addItem(item)
            self.point_items[pid] = item
        elif visible:
            item.point = pt
            item.refresh()
        elif item is not None:
            self.removeItem(self.point_items.pop(pid))
        self.schedule_annotations()

    def set_show_archived(self, on: bool) -> None:
        self.show_archived = on
        for pid in self.layout.points:
            self._sync_point_item(pid)

    def set_latest(self, latest: dict) -> None:
        self.latest = latest
        for it in self.point_items.values():
            it.update()
        self.schedule_annotations()  # box sizes depend on the readings

    def set_lab_sheet(self, sheet) -> None:
        """Lab sheet settings; point names show in the callouts."""
        self.layout.lab_sheet = sheet
        for pid in list(self.point_items):
            self._sync_point_item(pid)
        self.edited.emit()

    def add_point(self, pt: MeasurementPoint) -> None:
        self.layout.points[pt.id] = pt
        self._sync_point_item(pt.id)
        self.edited.emit()

    def remove_point(self, pid: str) -> None:
        """Only used to undo creating a point; user deletes archive instead."""
        del self.layout.points[pid]
        self._sync_point_item(pid)
        self.edited.emit()

    def add_component(self, c: Component) -> None:
        self.layout.components[c.id] = c
        self._add_comp_item(c)
        self.edited.emit()

    def remove_component(self, cid: str) -> None:
        item = self.comp_items.pop(cid)
        self.removeItem(item)
        del self.layout.components[cid]
        self.edited.emit()

    def add_beam(self, b: Beam) -> None:
        self.layout.beams[b.id] = b
        self._add_beam_item(b)
        self.edited.emit()

    def remove_beam(self, bid: str) -> None:
        item = self.beam_items.pop(bid)
        self.removeItem(item)
        del self.layout.beams[bid]
        self.edited.emit()

    def set_fields(self, obj_id: str, fields: dict) -> None:
        if obj_id in self.layout.points:
            pt = self.layout.points[obj_id]
            for k, v in fields.items():
                setattr(pt, k, v)
            self._sync_point_item(obj_id)
        elif obj_id in self.layout.components:
            c = self.layout.components[obj_id]
            for k, v in fields.items():
                setattr(c, k, v)
            item = self.comp_items[obj_id]
            item.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
            item.sync()
            item.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
            self.component_moved(obj_id)
        else:
            b = self.layout.beams[obj_id]
            for k, v in fields.items():
                setattr(b, k, v)
            self.beam_items[obj_id].refresh()
            for pt in self.layout.points_on(obj_id):
                self._sync_point_item(pt.id)
        self._on_selection()
        self.edited.emit()

    def component_moved(self, cid: str) -> None:
        touched = {cid}
        for b in self.layout.beams_touching(cid):
            touched.update((b.source, b.target))
        self.orient_all(touched)
        for c in touched:
            for b in self.layout.beams_touching(c):
                if b.id in self.beam_items:
                    self.beam_items[b.id].refresh()
                for pt in self.layout.points_on(b.id):
                    if pt.id in self.point_items:
                        self.point_items[pt.id].refresh()
            for pt in self.layout.points_at_part(c):
                if pt.id in self.point_items:
                    self.point_items[pt.id].refresh()
        self.check_clashes()
        self.schedule_annotations()

    # ---- derived state: orientation, clashes ---------------------------------
    def orient_all(self, only: set[str] | None = None) -> None:
        """Re-aim every auto-oriented part from its beams (see orient.py)."""
        lay = self.layout
        for cid in (only if only is not None else list(lay.components)):
            c = lay.components.get(cid)
            if c is None or not c.auto_angle:
                continue
            kind = kind_of_type(c.type)
            if kind is None:
                continue
            ins = [(lay.components[b.source].x, lay.components[b.source].y)
                   for b in lay.beams.values() if b.target == cid and b.source in lay.components]
            outs = [(lay.components[b.target].x, lay.components[b.target].y)
                    for b in lay.beams.values() if b.source == cid and b.target in lay.components]
            a = auto_angle(kind, (c.x, c.y), ins, outs, c.type)
            if a is not None and abs(((a - c.angle) + 180) % 360 - 180) > 1e-6:
                c.angle = a
                it = self.comp_items.get(cid)
                if it is not None:
                    it.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
                    it.sync()
                    it.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

    def check_clashes(self) -> None:
        """Mark parts whose outlines overlap (like a courtyard check in KiCad)."""
        items = [it for it in self.comp_items.values() if SYMBOLS[it.comp.type].physical]
        polys = [(it.comp.id, it.outline()) for it in items]
        clash = set()
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                if polys[i][1].intersects(polys[j][1]):
                    clash.update((polys[i][0], polys[j][0]))
        if clash != self.clashes:
            changed = clash ^ self.clashes
            self.clashes = clash
            for cid in changed:
                if cid in self.comp_items:
                    self.comp_items[cid].update()

    def staging_rect(self) -> QRectF:
        t = self.layout.table
        return QRectF(0, t.height + STAGING_GAP, t.width, 110)

    def off_table(self) -> list[str]:
        t = self.layout.table
        return [c.id for c in self.layout.components.values() if not t.on_board(c.x, c.y)]

    def set_text_scale(self, k: float) -> None:
        self.text_scale = k
        self.layout_annotations()

    # ---- schematic -> layout --------------------------------------------------
    def sync_from_schematic(self) -> list[str]:
        """Make the layout follow the schematic. The schematic owns which parts
        and beams exist and their fields (part, part number, label); the layout
        owns only where parts sit and, if not automatic, their angle.

        Runs after every schematic edit. It is derived state, so it isn't on the
        undo stack: undoing the schematic edit and syncing again restores the
        layout (parts of deleted elements are parked, positions kept).
        Returns ids of parts that were newly created."""
        lay, sch = self.layout, self.layout.schematic
        created: list[str] = []
        changed = False
        # parts
        by_el = {c.sch_id: c for c in lay.components.values() if c.sch_id}
        for eid, el in sch.elements.items():
            typ = el.layout_type()
            pn = el.part_number or SYMBOLS[typ].default_part
            c = by_el.get(eid)
            if c is None:
                c = self._parked.pop(eid, None)
                if c is None:
                    c = Component(id=f"c_{eid}", type=typ, x=0, y=0, angle=el.angle, sch_id=eid,
                                  auto_angle=el.auto_angle)
                    c.x, c.y = self._new_part_position(c, el, False)
                    created.append(c.id)
                c.type, c.part_number, c.label = typ, pn, el.label
                self.layout.components[c.id] = c
                self._add_comp_item(c)
                changed = True
            elif (c.type, c.part_number, c.label) != (typ, pn, el.label):
                c.type, c.part_number, c.label = typ, pn, el.label
                self.comp_items[c.id].sync()
                changed = True
        for c in list(lay.components.values()):
            if c.sch_id and c.sch_id not in sch.elements:
                self._parked[c.sch_id] = c
                for pt in lay.points_at_part(c.id):
                    if not pt.archived:
                        pt.x, pt.y = lay.point_xy(pt)
                        pt.archived = True
                        self._sync_point_item(pt.id)
                self.removeItem(self.comp_items.pop(c.id))
                del lay.components[c.id]
                changed = True
        # beams: one per schematic connection, same id
        if sch.links:
            want = {}
            for k in sch.links.values():
                a, b = lay.component_for(k.source), lay.component_for(k.target)
                if a is not None and b is not None:
                    want[k.id] = (a.id, b.id, k.color, k.wavelength_nm, k.label)
            for bid in list(lay.beams):
                if bid not in want:
                    for pt in lay.points_on(bid):  # keep beam_id so the point returns on undo
                        if not pt.archived:
                            pt.x, pt.y = lay.point_xy(pt)
                            pt.archived = True
                            self._sync_point_item(pt.id)
                    self.removeItem(self.beam_items.pop(bid))
                    del lay.beams[bid]
                    changed = True
            for lid, (a, b, color, wl, label) in want.items():
                bm = lay.beams.get(lid)
                if bm is None:
                    bm = Beam(id=lid, source=a, target=b, color=color, wavelength_nm=wl, label=label)
                    lay.beams[lid] = bm
                    self._add_beam_item(bm)
                    changed = True
                elif (bm.source, bm.target, bm.color, bm.wavelength_nm, bm.label) != (a, b, color, wl, label):
                    bm.source, bm.target, bm.color, bm.wavelength_nm, bm.label = a, b, color, wl, label
                    self.beam_items[lid].refresh()
                    changed = True
            for pt in lay.points.values():
                if pt.archived and (pt.beam_id in lay.beams or (pt.part_id and pt.part_id in lay.components)):
                    pt.archived = False
                    self._sync_point_item(pt.id)
                    changed = True
        if lay.components and not any(c.pinned for c in lay.components.values()):
            # nothing placed by hand yet: the layout keeps copying the schematic's arrangement
            if self._arrange_unpinned():
                changed = True
        if changed:
            self.orient_all()
            for it in self.beam_items.values():
                it.refresh()
            for it in self.point_items.values():
                it.refresh()
            self.check_clashes()
            self.schedule_annotations()
            self.edited.emit()
        return created

    def _arrange_unpinned(self) -> bool:
        lay = self.layout
        saved = lay.components
        done: dict[str, Component] = {}
        moved = False
        try:
            for c in list(saved.values()):
                el = lay.schematic.elements.get(c.sch_id)
                if el is None:
                    continue
                lay.components = done  # only parts already arranged block a hole
                x, y = self._new_part_position(c, el, True)
                done[c.id] = c
                if (x, y) != (c.x, c.y):
                    c.x, c.y = x, y
                    moved = True
        finally:
            lay.components = saved
        if moved:
            for c in saved.values():
                it = self.comp_items.get(c.id)
                if it is not None:
                    it.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
                    it.sync()
                    it.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        return moved

    def _new_part_position(self, c: Component, el, first_fill: bool) -> tuple[float, float]:
        """Where a new part appears: on a first fill, the schematic's arrangement
        scaled onto the table; afterwards, in the "new parts" strip below the
        table, ready to be dragged into place."""
        t = self.layout.table
        pitch, off = t.hole_pitch, t.hole_offset
        taken = {(round(o.x, 1), round(o.y, 1)) for o in self.layout.components.values()}
        if first_fill:
            from .schematic import _inside_table
            els = list(self.layout.schematic.elements.values())
            xs, ys = [e.x for e in els], [e.y for e in els]
            x0, y0 = min(xs), min(ys)
            w, h = max(max(xs) - x0, 1), max(max(ys) - y0, 1)
            m = 50.8
            k = min((t.width - 2 * m) / w, (t.height - 2 * m) / h, 2.5)
            cx, cy = (t.width - k * w) / 2, (t.height - k * h) / 2
            x = off + round((cx + (el.x - x0) * k - off) / pitch) * pitch
            y = off + round((cy + (el.y - y0) * k - off) / pitch) * pitch
            x, y = _inside_table(x, y, c.type, c.angle, self.layout)
            while (round(x, 1), round(y, 1)) in taken:
                x += pitch
            return x, y
        r = self.staging_rect()
        x, y = r.left() + 40, r.center().y()
        while (round(x, 1), round(y, 1)) in taken:
            x += 2 * pitch
            if x > r.right() - 20:
                x, y = r.left() + 40, y + 2 * pitch
        return x, y

    # ---- selection --------------------------------------------------------
    def selected_ids(self) -> tuple[list[str], list[str]]:
        comps = [i.comp.id for i in self.selectedItems() if isinstance(i, ComponentItem)]
        beams = [i.beam.id for i in self.selectedItems() if isinstance(i, BeamItem)]
        return comps, beams

    def selected_points(self) -> list[str]:
        return [i.point.id for i in self.selectedItems() if isinstance(i, PointItem)]

    def _on_selection(self) -> None:
        try:
            sel = self.selectedItems()
        except RuntimeError:
            return
        if len(sel) == 1:
            it = sel[0]
            obj = (it.comp if isinstance(it, ComponentItem) else it.beam if isinstance(it, BeamItem)
                   else it.point)
            self.selection_info.emit(obj)
        elif len(sel) == 2 and all(isinstance(it, ComponentItem) for it in sel):
            self.selection_info.emit(PartPair(sel[0].comp.id, sel[1].comp.id))
        else:
            self.selection_info.emit(None)

    # ---- drawing ----------------------------------------------------------
    def drawBackground(self, p: QPainter, rect: QRectF) -> None:
        if not self.exporting:
            self.set_view_zoom(abs(p.worldTransform().m11()) or abs(p.worldTransform().m12()))
        p.fillRect(rect, QColor("#ffffff"))
        t = self.layout.table
        tr = self.table_rect()
        # mounting holes, only those in view
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#e6e6e6")))
        r = t.hole_diameter / 2  # every hole the same size (Olego: centre holes too)
        vis = rect.intersected(tr) if t.has_grid and t.grid_holes else QRectF()
        cut = t.in_cutout if t.cutouts else (lambda _x, _y: False)
        if not vis.isEmpty():
            pitch, off = t.hole_pitch, t.hole_offset
            i0 = max(0, math.floor((vis.left() - off) / pitch))
            i1 = math.ceil((vis.right() - off) / pitch)
            j0 = max(0, math.floor((vis.top() - off) / pitch))
            j1 = math.ceil((vis.bottom() - off) / pitch)
            for i in range(i0, i1 + 1):
                x = off + i * pitch
                if x > t.width - t.edge_margin + 1e-6:
                    break
                for j in range(j0, j1 + 1):
                    y = off + j * pitch
                    if y > t.height - t.edge_margin + 1e-6:
                        break
                    if t.hole_ok(x, y):
                        p.drawEllipse(QPointF(x, y), r, r)
                    cx, cy = x + pitch / 2, y + pitch / 2
                    if t.center_holes and t.center_hole_ok(cx, cy):
                        p.drawEllipse(QPointF(cx, cy), r, r)
        if t.style in DRILLED_STYLES:
            self.draw_drilled(p, rect)
        elif not t.has_grid:  # pre-drilled: a hole under each part's post
            for c in self.layout.components.values():
                if SYMBOLS[c.type].physical and t.on_board(c.x, c.y) and rect.contains(QPointF(c.x, c.y)):
                    p.drawEllipse(QPointF(c.x, c.y), r, r)
        p.setPen(QPen(QColor("#111111"), 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawPath(self.board_path())
        r = self.name_rect()
        draw_halo_text(p, r, t.name, getattr(self, "name_px", 8), color="#333333", align=Qt.AlignLeft | Qt.AlignVCenter)
        if self.show_coords and t.has_grid:
            self.draw_coords(p, rect)
        self.draw_legend(p)
        self.draw_staging(p)

    def table_screw_holes(self) -> list[tuple[float, float]]:
        """The plate's 1/4-20 table holes (worked out from where the parts are; cached)."""
        from .mounts3d import table_screw_holes
        t = self.layout.table
        parts = tuple((c.type, c.x, c.y, c.angle) for c in self.layout.components.values()
                      if SYMBOLS[c.type].physical and t.on_board(c.x, c.y))
        key = (parts, t.style, t.width, t.height, tuple(map(tuple, t.cutouts)))
        if getattr(self, "_table_holes_key", None) != key:
            self._table_holes_key, self._table_holes = key, table_screw_holes(t, parts)
        return self._table_holes

    def draw_drilled(self, p: QPainter, rect: QRectF) -> None:
        """A board drilled per part (PyOpticL, LightFlow): faint 1" design grid,
        the adapters or pedestals, the 8-32 (and dowel) holes drilled for each
        part and the 1/4-20 table holes."""
        from .mounts3d import BLOCK_COLOR, TABLE_SCREW, drilled_holes
        t = self.layout.table
        p.setPen(QPen(QColor("#d4d4d4"), 0.35))
        p.setBrush(Qt.NoBrush)
        vis = rect.intersected(self.table_rect())
        if not vis.isEmpty():
            pitch, off, k = t.hole_pitch, t.hole_offset, 1.2
            for i in range(max(0, math.floor((vis.left() - off) / pitch)), t.columns()):
                x = off + i * pitch
                if x > vis.right() + pitch:
                    break
                for j in range(max(0, math.floor((vis.top() - off) / pitch)), t.rows()):
                    y = off + j * pitch
                    if y > vis.bottom() + pitch:
                        break
                    if t.on_board(x, y):
                        p.drawLine(QPointF(x - k, y), QPointF(x + k, y))
                        p.drawLine(QPointF(x, y - k), QPointF(x, y + k))
        ad = QColor(BLOCK_COLOR[t.style])
        ad.setAlpha(110)
        p.setPen(QPen(QColor(BLOCK_COLOR[t.style]).darker(130), 0.4))
        p.setBrush(ad)
        parts = [c for c in self.layout.components.values() if SYMBOLS[c.type].physical and t.on_board(c.x, c.y)]
        for c in parts:
            r = block_outline(c, t.style)
            if r is not None and rect.intersects(r.boundingRect()):
                p.drawPolygon(r)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#c8c8c8"))
        for c in parts:
            for x, y, d in drilled_holes(c.type, t.style, c.x, c.y, c.angle):
                p.drawEllipse(QPointF(x, y), d / 2, d / 2)
        d, cb = TABLE_SCREW[t.style]
        for x, y in self.table_screw_holes():
            if cb:
                p.setPen(QPen(QColor("#9a9a9a"), 0.5))
                p.setBrush(QColor("#eeeeee"))
                p.drawEllipse(QPointF(x, y), cb / 2, cb / 2)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#b8b8b8"))
            p.drawEllipse(QPointF(x, y), d / 2, d / 2)

    def name_rect(self) -> QRectF:
        """The board's name, above its top-left corner (clear of the hole letters)."""
        px = getattr(self, "name_px", 8)
        w, h = labels.text_size(self.layout.table.name, px)
        top = -(getattr(self, "coord_px", 6.0) * 1.6 if self.show_coords else 0) - h - px * 0.3
        return QRectF(0, top, w + 2, h)

    def legend_entries(self) -> list[tuple[str, str]]:
        """(colour, name) per beam colour in use, when the board mixes wavelengths."""
        from .model import wavelengths_in_use
        used = wavelengths_in_use(self.layout)
        return [(c, n) for c, n, _k in used] if len(used) > 1 else []

    def legend_rect(self) -> QRectF:
        """Above the board's top-right corner (clear of the hole letters)."""
        ents = self.legend_entries()
        if not ents:
            return QRectF()
        px = getattr(self, "coord_px", 6.0) * 1.1
        sw = px * 1.8
        w = sum(sw + px * 0.4 + labels.text_size(n, px, bold=False)[0] + px * 1.2 for _c, n in ents)
        h = px * 1.4
        top = -(getattr(self, "coord_px", 6.0) * 1.6 if self.show_coords else 0) - h - px * 0.6
        return QRectF(self.layout.table.width - w, top, w, h)

    def draw_legend(self, p: QPainter) -> None:
        r = self.legend_rect()
        if r.isEmpty():
            return
        px = getattr(self, "coord_px", 6.0) * 1.1
        sw = px * 1.8
        x = r.left()
        for color, name in self.legend_entries():
            p.setPen(QPen(QColor(color), max(BEAM_WIDTH, px * 0.28), Qt.SolidLine, Qt.FlatCap))
            p.drawLine(QPointF(x, r.center().y()), QPointF(x + sw, r.center().y()))
            x += sw + px * 0.4
            w, h = labels.text_size(name, px, bold=False)
            draw_halo_text(p, QRectF(x, r.top(), w + 1, r.height()), name, px, bold=False, color="#333333",
                           align=Qt.AlignLeft | Qt.AlignVCenter)
            x += w + px * 1.2

    def draw_coords(self, p: QPainter, rect: QRectF) -> None:
        """Column letters along the top and bottom edges, row numbers down the
        sides, so a hole can be called out as "C7" (also shown in Properties)."""
        t = self.layout.table
        px = getattr(self, "coord_px", 6.0)
        pitch, off = t.hole_pitch, t.hole_offset
        wide = labels.text_size("WW", px, bold=False)[0]
        step = 1
        while step * pitch < wide * 1.25 and step < 50:
            step = {1: 2, 2: 5}.get(step, step * 2)
        gap = px * 0.35
        col = QColor("#7a7a7a")
        for i in range(0, t.columns(), step):
            x = off + i * pitch
            name = t.column_name(i)
            w, h = labels.text_size(name, px, bold=False)
            for y0 in (-gap - h, t.height + gap):
                r = QRectF(x - w / 2 - 1, y0, w + 2, h)
                if r.intersects(rect):
                    draw_halo_text(p, r, name, px, bold=False, color=col.name())
        for j in range(0, t.rows(), step):
            y = off + j * pitch
            name = str(j + 1)
            w, h = labels.text_size(name, px, bold=False)
            for r in (QRectF(-gap - w - 1, y - h / 2, w + 1, h), QRectF(t.width + gap, y - h / 2, w + 1, h)):
                if r.intersects(rect):
                    draw_halo_text(p, r, name, px, bold=False, color=col.name(),
                                   align=Qt.AlignRight | Qt.AlignVCenter if r.left() < 0 else Qt.AlignLeft | Qt.AlignVCenter)


    def draw_staging(self, p: QPainter) -> None:
        """The "new parts" strip under the table, shown while parts wait there."""
        if not self.show_ratsnest:
            return
        r = self.staging_rect()
        waiting = [c for c in self.layout.components.values() if r.adjusted(-40, -40, 40, 60).contains(QPointF(c.x, c.y))]
        if not waiting:
            return
        p.setPen(QPen(QColor("#9a9a9a"), 0.8, Qt.DashLine))
        p.setBrush(QColor("#f6f6f2"))
        p.drawRoundedRect(r, 4, 4)
        f = QFont("Arial")
        f.setPixelSize(8)
        p.setFont(f)
        p.setPen(QPen(QColor("#777777")))
        p.drawText(r.adjusted(6, 3, -6, -3), Qt.AlignLeft | Qt.AlignTop,
                   "New parts from the schematic: drag them onto the table")


# ---- undo commands ---------------------------------------------------------

class AddComponentCmd(QUndoCommand):
    def __init__(self, scene: LayoutScene, comp: Component):
        super().__init__(f"Add {comp.label or comp.type}")
        self.scene, self.comp = scene, comp

    def redo(self):
        self.scene.add_component(deepcopy(self.comp))

    def undo(self):
        self.scene.remove_component(self.comp.id)


class AddBeamCmd(QUndoCommand):
    def __init__(self, scene: LayoutScene, beam: Beam):
        super().__init__("Add beam")
        self.scene, self.beam = scene, beam

    def redo(self):
        self.scene.add_beam(deepcopy(self.beam))

    def undo(self):
        self.scene.remove_beam(self.beam.id)


class AddPointCmd(QUndoCommand):
    def __init__(self, scene: LayoutScene, pt: MeasurementPoint):
        super().__init__(f"Add measurement point {pt.label}")
        self.scene, self.pt = scene, pt

    def redo(self):
        self.scene.add_point(deepcopy(self.pt))

    def undo(self):
        self.scene.remove_point(self.pt.id)


class SetLabSheetCmd(QUndoCommand):
    """Change the lab sheet's points, names and options (saved with the layout)."""

    def __init__(self, scene: LayoutScene, new):
        super().__init__("Lab sheet settings")
        self.scene, self.old, self.new = scene, deepcopy(scene.layout.lab_sheet), deepcopy(new)

    def redo(self):
        self.scene.set_lab_sheet(deepcopy(self.new))

    def undo(self):
        self.scene.set_lab_sheet(deepcopy(self.old))


class DeleteCmd(QUndoCommand):
    """Delete components (and the beams attached to them) and beams.

    Measurement points are never deleted: points on removed beams, and points
    the user deletes directly, are archived with their last position so their
    logbook history stays reachable. Undo un-archives them.
    """

    def __init__(self, scene: LayoutScene, comp_ids: list[str], beam_ids: list[str],
                 point_ids: list[str] = ()):
        super().__init__("Delete")
        self.scene = scene
        lay = scene.layout
        bids = set(beam_ids)
        for cid in comp_ids:
            bids.update(b.id for b in lay.beams_touching(cid))
        self.comps = [deepcopy(lay.components[c]) for c in comp_ids]
        self.beams = [deepcopy(lay.beams[b]) for b in bids]
        pids = (set(point_ids) | {p.id for b in bids for p in lay.points_on(b)}
                | {p.id for c in comp_ids for p in lay.points_at_part(c)})
        self.points = {}
        for pid in pids:
            p = lay.points[pid]
            if p.archived:
                continue
            x, y = lay.point_xy(p)
            old = {"beam_id": p.beam_id, "part_id": p.part_id, "archived": False, "x": p.x, "y": p.y}
            self.points[pid] = (old, {"beam_id": None, "part_id": None, "archived": True, "x": x, "y": y})

    def redo(self):
        for pid, (_, new) in self.points.items():
            self.scene.set_fields(pid, new)
        for b in self.beams:
            self.scene.remove_beam(b.id)
        for c in self.comps:
            self.scene.remove_component(c.id)

    def undo(self):
        for c in self.comps:
            self.scene.add_component(deepcopy(c))
        for b in self.beams:
            self.scene.add_beam(deepcopy(b))
        for pid, (old, _) in self.points.items():
            self.scene.set_fields(pid, old)


class SetFieldsCmd(QUndoCommand):
    """Change fields on one or more objects: {id: (old_fields, new_fields)}."""

    def __init__(self, scene: LayoutScene, changes: dict[str, tuple[dict, dict]], text: str):
        super().__init__(text)
        self.scene, self.changes = scene, changes

    def redo(self):
        for oid, (_, new) in self.changes.items():
            self.scene.set_fields(oid, new)

    def undo(self):
        for oid, (old, _) in self.changes.items():
            self.scene.set_fields(oid, old)
