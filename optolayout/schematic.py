"""Schematic layer: a KiCad-style functional drawing that comes before the layout.

The schematic is where the system is defined: which optical elements exist,
which real part each one is (type, part number), and how light flows between
them. Exact positions and sizes don't matter here. The layout follows it
live: every element has a part on the table and every connection is a beam;
in the layout you only move and rotate.
"""

from __future__ import annotations

import math
from copy import deepcopy

from PySide6.QtCore import QLineF, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QPainter, QPainterPath,
                           QPainterPathStroker, QPen, QPicture, QPixmap, QPolygonF, QUndoCommand)
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QGraphicsItem,
                               QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import labels
from .labels import draw_halo_text
from .model import SCH_KINDS, Component, Layout, SchElement, SchLink, new_id
from .symbols import SYMBOLS

GRID = 10.0
INK = QColor("#1a1a1a")
PAPER = QColor("#fbfbf8")
GRID_DOT = QColor("#d6d6d0")
SEL = QColor("#1f6fd1")
# element name / part number text: sheet units, kept readable on screen (times A+ / A-)
NAME_UNITS, NAME_MIN_PX, NAME_MAX_PX = 8.5, 12, 20
PN_RATIO = 0.82  # part-number line relative to the name
PN_INK = QColor("#3d3d3d")


# ---- symbols ---------------------------------------------------------------------
# Plain line-art, drawn in a local frame: element centre at the origin, optic
# normal / beam axis along +x, about 30 units across.

def _pen(w=1.6):
    return QPen(INK, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def _text(p: QPainter, rect: QRectF, s: str, px=7, bold=False):
    f = QFont("Arial")
    f.setPixelSize(px)
    f.setBold(bold)
    p.setFont(f)
    p.drawText(rect, Qt.AlignCenter, s)


def _box(p, w, h, label, fill="#ffffff", px=7):
    p.setPen(_pen())
    p.setBrush(QColor(fill))
    r = QRectF(-w / 2, -h / 2, w, h)
    p.drawRect(r)
    p.setPen(INK)
    _text(p, r, label, px, bold=True)


def _sym_mirror(p):
    p.setPen(_pen(2.6))
    p.drawLine(QPointF(0, -13), QPointF(0, 13))
    p.setPen(_pen(1.0))
    for i in range(-12, 13, 4):
        p.drawLine(QPointF(0.5, i), QPointF(-4, i + 4))


def _sym_lens(p):
    p.setPen(_pen())
    p.setBrush(QColor("#e8f3f8"))
    path = QPainterPath(QPointF(0, -14))
    path.quadTo(QPointF(7, 0), QPointF(0, 14))
    path.quadTo(QPointF(-7, 0), QPointF(0, -14))
    p.drawPath(path)


def _sym_plate(label, fill):
    def draw(p):
        p.setPen(_pen())
        p.setBrush(QColor(fill))
        p.drawRect(QRectF(-2.5, -13, 5, 26))
        p.setPen(INK)
        _text(p, QRectF(-12, -24, 24, 9), label, 7)
    return draw


def _sym_cube(dashed):
    def draw(p):
        p.setPen(_pen())
        p.setBrush(QColor("#ffffff"))
        p.drawRect(QRectF(-10, -10, 20, 20))
        p.setPen(QPen(INK, 1.4, Qt.DashLine if dashed else Qt.SolidLine))
        p.drawLine(QPointF(-10, 10), QPointF(10, -10))
    return draw


def _sym_fiber(p):
    """Coupler lens faces +x (the free-space beam); the fiber tail leaves at -x."""
    p.setPen(_pen())
    p.setBrush(QColor("#ffffff"))
    p.drawPolygon(QPolygonF([QPointF(6, -7), QPointF(-6, -3), QPointF(-6, 3), QPointF(6, 7)]))
    path = QPainterPath(QPointF(-6, 0))
    path.cubicTo(QPointF(-12, -6), QPointF(-14, 6), QPointF(-20, 0))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


def _sym_iris(p):
    p.setPen(_pen(2.2))
    p.drawLine(QPointF(0, -13), QPointF(0, -3))
    p.drawLine(QPointF(0, 3), QPointF(0, 13))


def _sym_pd(p):
    p.setPen(_pen())
    p.setBrush(QColor("#ffffff"))
    path = QPainterPath(QPointF(0, -9))
    path.arcTo(QRectF(-9, -9, 18, 18), 90, 180)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(0, -9), QPointF(0, 9))


def _sym_shutter(p):
    """A blade across the beam, hinged at the top."""
    p.setPen(_pen())
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(-5, -13, 10, 26))
    p.setPen(_pen(2.4))
    p.drawLine(QPointF(0, -9), QPointF(0, 9))
    p.setPen(INK)
    _text(p, QRectF(-12, -24, 24, 9), "SH", 7)


def _sym_dump(p):
    p.setPen(_pen())
    p.setBrush(INK)
    p.drawRect(QRectF(-3, -10, 6, 20))
    p.setBrush(Qt.NoBrush)
    for i in (-6, 0, 6):
        p.drawLine(QPointF(-3, i - 2), QPointF(-7, i + 2))


SCH_SYMBOLS = {
    "laser": lambda p: _box(p, 40, 18, "LASER", "#fff4d6"),
    "mirror": _sym_mirror,
    "lens": _sym_lens,
    "hwp": _sym_plate("λ/2", "#f4c430"),
    "qwp": _sym_plate("λ/4", "#7cc576"),
    "pbs": _sym_cube(False),
    "bs": _sym_cube(True),
    "aom": lambda p: _box(p, 28, 14, "AOM", "#e6ebf7"),
    "shutter": _sym_shutter,
    "fiber": _sym_fiber,
    "iris": _sym_iris,
    "photodiode": _sym_pd,
    "dump": _sym_dump,
}


def _sym_entry(p):
    """A beam arriving from off the board: dashed tail, open dot, arrow out."""
    p.setPen(QPen(INK, 1.2, Qt.DashLine))
    p.drawLine(QPointF(-20, 0), QPointF(-6, 0))
    p.setPen(_pen())
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(QPointF(0, 0), 5, 5)
    p.setBrush(INK)
    p.drawEllipse(QPointF(0, 0), 1.8, 1.8)


# drawings for particular parts that don't look like their kind's symbol
SCH_PART_SYMBOLS = {"beam_entry": _sym_entry}


def sch_symbol(kind: str, part: str = ""):
    return SCH_PART_SYMBOLS.get(part) or SCH_SYMBOLS[kind]


def sch_icon(kind: str, size: int = 36) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(size / 2, size / 2)
    p.scale(size / 46, size / 46)
    SCH_SYMBOLS[kind](p)
    p.end()
    return QIcon(pm)


_INK: dict[tuple, QRectF] = {}


def symbol_ink(kind: str, angle: float, part: str = "") -> QRectF:
    """Bounding box of everything a schematic symbol draws, after rotation."""
    key = (kind, part if part in SCH_PART_SYMBOLS else "", round(angle % 360, 1))
    r = _INK.get(key)
    if r is None:
        pic = QPicture()
        p = QPainter(pic)
        p.rotate(-angle)
        sch_symbol(kind, part)(p)
        p.end()
        r = _INK[key] = QRectF(pic.boundingRect()).adjusted(-1, -1, 1, 1)
    return r


# ---- items ---------------------------------------------------------------------------

class SchElementItem(labels.CachedBounds, QGraphicsItem):
    BODY = QRectF(-22, -26, 44, 52)

    def __init__(self, el: SchElement):
        super().__init__()
        self.el = el
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(10)
        self.placed = True  # has a layout part (set by the scene)
        self.name_px = NAME_UNITS
        self.label_rect: QRectF | None = None  # name + part-number block, item coordinates (set by the scene)
        self.sync()

    def sync(self):
        self.geometry_changed()
        self.setPos(self.el.x, self.el.y)
        e = self.el
        typ = e.layout_type()
        self.setToolTip(f"<b>{e.label}</b> · {SCH_KINDS[e.kind][0]}<br>{SYMBOLS[typ].name}<br>"
                        f"{e.part_number or SYMBOLS[typ].default_part or '(no part number)'}"
                        + (f"<br><i>{e.notes}</i>" if e.notes else ""))
        self.update()

    def _rot_body(self) -> QRectF:
        """Pick / selection area: at least 30 x 30 around the drawn symbol."""
        return self.ink_rect().united(QRectF(-15, -15, 30, 30)).adjusted(-2, -2, 2, 2)

    def ink_rect(self) -> QRectF:
        """What the symbol actually draws (all its marks), rotated."""
        return symbol_ink(self.el.kind, self.el.angle, self.el.layout_type())

    def texts(self) -> tuple[str, str]:
        pn = self.el.part_number or SYMBOLS[self.el.layout_type()].default_part
        return self.el.label or SCH_KINDS[self.el.kind][0], pn

    def text_block(self, px: float) -> tuple[float, float]:
        name, pn = self.texts()
        w1, h1 = labels.text_size(name, px, bold=True)
        w2, h2 = labels.text_size(pn, px * PN_RATIO, bold=False) if pn else (0, 0)
        return max(w1, w2), h1 + h2

    def _label_rect(self) -> QRectF:
        if self.label_rect is not None:
            return self.label_rect
        w, h = self.text_block(self.name_px)
        return QRectF(-w / 2, self.ink_rect().bottom() + 1.5, w, h)

    def compute_bounds(self):
        return self._rot_body().united(self._label_rect()).adjusted(-3, -3, 3, 3)

    def shape(self):
        path = QPainterPath()
        path.addRect(self._rot_body())
        return path

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        p.save()
        p.rotate(-self.el.angle)
        sch_symbol(self.el.kind, self.el.layout_type())(p)
        p.restore()
        name, pn = self.texts()
        r = self._label_rect()
        px = self.name_px
        _w, h1 = labels.text_size(name, px)
        draw_halo_text(p, QRectF(r.left(), r.top(), r.width(), h1), name, px, color="#111111")
        if pn:
            draw_halo_text(p, QRectF(r.left(), r.top() + h1, r.width(), r.height() - h1), pn, px * PN_RATIO,
                           bold=False, color=PN_INK.name())
        if self.isSelected():
            p.setPen(QPen(SEL, 1.0, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self._rot_body().adjusted(-2, -2, 2, 2))

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            return QPointF(round(value.x() / GRID) * GRID, round(value.y() / GRID) * GRID)
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.el.x, self.el.y = self.pos().x(), self.pos().y()
            self.scene().element_moved(self.el.id)
        return super().itemChange(change, value)


class SchLinkItem(labels.CachedBounds, QGraphicsItem):
    def __init__(self, link: SchLink, scene: "SchematicScene"):
        super().__init__()
        self.link = link
        self._scene = scene
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setZValue(1)
        self.routed = False

    def line(self) -> QLineF:
        a = self._scene.sch.elements[self.link.source]
        b = self._scene.sch.elements[self.link.target]
        return QLineF(a.x, a.y, b.x, b.y)

    def refresh(self):
        self.geometry_changed()
        self.update()

    def compute_bounds(self):
        return QRectF(self.line().p1(), self.line().p2()).normalized().adjusted(-8, -8, 8, 8)

    def shape(self):
        path = QPainterPath(self.line().p1())
        path.lineTo(self.line().p2())
        s = QPainterPathStroker()
        s.setWidth(7)
        return s.createStroke(path)

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        ln = self.line()
        color = QColor(self.link.color)
        if self.isSelected():
            p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 70), 7, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(ln)
        p.setPen(QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(ln)
        if ln.length() > 30:  # direction arrow at the midpoint
            mid = ln.pointAt(0.5)
            u = QPointF(ln.dx() / ln.length(), ln.dy() / ln.length())
            n = QPointF(-u.y(), u.x())
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([mid + u * 5, mid - u * 4 + n * 4, mid - u * 4 - n * 4]))


class SchematicScene(QGraphicsScene):
    selection_info = Signal(object)  # SchElement | SchLink | None
    edited = Signal()

    def __init__(self, undo):
        super().__init__()
        self.undo = undo  # shared with the layout so Save / title / Ctrl+Z see one history
        self.text_scale = 1.0
        self.layout: Layout = Layout()
        self.el_items: dict[str, SchElementItem] = {}
        self.link_items: dict[str, SchLinkItem] = {}
        self.selectionChanged.connect(self._on_selection)
        self.setSceneRect(QRectF(-2000, -2000, 4000, 4000))
        self.view_zoom = 1.6
        self.exporting = False
        self._ann_timer = QTimer(self)
        self._ann_timer.setSingleShot(True)
        self._ann_timer.setInterval(0)
        self._ann_timer.timeout.connect(self.layout_annotations)

    @property
    def sch(self):
        return self.layout.schematic

    def set_layout(self, layout: Layout):
        self.clear()
        self.el_items.clear()
        self.link_items.clear()
        self.layout = layout
        for e in self.sch.elements.values():
            self._add_el_item(e)
        for k in self.sch.links.values():
            self._add_link_item(k)
        self.orient_all()
        self.refresh_status()
        self.layout_annotations()

    def set_text_scale(self, k: float):
        self.text_scale = k
        self.layout_annotations()

    def set_view_zoom(self, z: float) -> None:
        if z > 0 and abs(z - self.view_zoom) > 0.01 * self.view_zoom:
            self.view_zoom = z
            self._ann_timer.start()

    def schedule_annotations(self) -> None:
        self._ann_timer.start()

    def layout_annotations(self) -> None:
        """Size element names for the zoom and put each name block where it
        doesn't sit on a symbol, a beam or another name."""
        k = self.text_scale
        px = labels.clamp_px(NAME_UNITS * k, self.view_zoom, NAME_MIN_PX * k, NAME_MAX_PX * k)
        placer = labels.Placer()
        inks = {}
        for eid, it in self.el_items.items():
            inks[eid] = it.ink_rect().translated(it.el.x, it.el.y)
            placer.add_body(inks[eid])
        for it in self.link_items.values():
            placer.add_segment(it.line())
        for it in sorted(self.el_items.values(), key=lambda i: (i.el.y, i.el.x)):
            it.geometry_changed()
            it.name_px = px
            w, h = it.text_block(px)
            cands = labels.around(inks[it.el.id], w, h, px * 0.25)
            i = placer.place(cands, ignore=inks[it.el.id])
            it.label_rect = cands[i].translated(-it.el.x, -it.el.y)
            it.update()

    def begin_export(self) -> None:
        self._saved_zoom = self.view_zoom
        self.exporting = True
        r = self.items_rect()
        self.view_zoom = 1600 / max(r.width(), r.height() * 1.5, 1)
        self.layout_annotations()

    def end_export(self) -> None:
        self.exporting = False
        self.view_zoom = getattr(self, "_saved_zoom", self.view_zoom)
        self.layout_annotations()

    def items_rect(self) -> QRectF:
        r = self.itemsBoundingRect()
        return r if not r.isEmpty() else QRectF(-200, -150, 400, 300)

    def refresh_status(self):
        """Mark elements with no layout part and links not yet built with beams."""
        placed = {c.sch_id for c in self.layout.components.values() if c.sch_id}
        for eid, it in self.el_items.items():
            it.placed = eid in placed
            it.update()
        for lid, it in self.link_items.items():
            it.routed = self.layout.is_routed(self.sch.links[lid])
            it.update()

    # ---- mutators (used by commands) --------------------------------------------
    def _add_el_item(self, e):
        it = SchElementItem(e)
        self.addItem(it)
        self.el_items[e.id] = it

    def _add_link_item(self, k):
        it = SchLinkItem(k, self)
        self.addItem(it)
        self.link_items[k.id] = it

    def add_element(self, e: SchElement):
        self.sch.elements[e.id] = e
        self._add_el_item(e)
        self.schedule_annotations()
        self.edited.emit()

    def remove_element(self, eid: str):
        self.removeItem(self.el_items.pop(eid))
        del self.sch.elements[eid]
        self.schedule_annotations()
        self.edited.emit()

    def add_link(self, k: SchLink):
        self.sch.links[k.id] = k
        self._add_link_item(k)
        self.orient_all({k.source, k.target})
        self.schedule_annotations()
        self.edited.emit()

    def remove_link(self, lid: str):
        self.removeItem(self.link_items.pop(lid))
        k = self.sch.links.pop(lid)
        self.orient_all({k.source, k.target})
        self.schedule_annotations()
        self.edited.emit()

    def set_fields(self, oid: str, fields: dict):
        if oid in self.sch.elements:
            e = self.sch.elements[oid]
            for k, v in fields.items():
                setattr(e, k, v)
            it = self.el_items[oid]
            it.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
            it.sync()
            it.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
            self.element_moved(oid)
        else:
            k = self.sch.links[oid]
            ends = {k.source, k.target}
            for key, v in fields.items():
                setattr(k, key, v)
            self.link_items[oid].refresh()
            self.orient_all(ends | {k.source, k.target})
        self._on_selection()
        self.edited.emit()

    def element_moved(self, eid: str):
        touched = {eid}
        for k in self.sch.links_touching(eid):
            touched.update((k.source, k.target))
        self.orient_all(touched)
        for e in touched:
            for k in self.sch.links_touching(e):
                if k.id in self.link_items:
                    self.link_items[k.id].refresh()
        self.schedule_annotations()

    # ---- selection -----------------------------------------------------------------
    def selected_ids(self) -> tuple[list[str], list[str]]:
        sel = self.selectedItems()
        return ([i.el.id for i in sel if isinstance(i, SchElementItem)],
                [i.link.id for i in sel if isinstance(i, SchLinkItem)])

    def _on_selection(self):
        try:
            sel = self.selectedItems()
        except RuntimeError:
            return
        if len(sel) == 1:
            it = sel[0]
            self.selection_info.emit(it.el if isinstance(it, SchElementItem) else it.link)
        else:
            self.selection_info.emit(None)

    def drawBackground(self, p: QPainter, rect: QRectF):
        if not self.exporting:
            self.set_view_zoom(abs(p.worldTransform().m11()) or abs(p.worldTransform().m12()))
        p.fillRect(rect, PAPER)
        step = GRID * 2
        p.setPen(QPen(GRID_DOT, 1.2))
        x0 = math.floor(rect.left() / step) * step
        y0 = math.floor(rect.top() / step) * step
        if rect.width() / step * rect.height() / step > 40000:
            return
        y = y0
        while y < rect.bottom():
            x = x0
            while x < rect.right():
                p.drawPoint(QPointF(x, y))
                x += step
            y += step

    def orient_all(self, only=None):
        """Auto-aim schematic symbols from their connections, like the layout."""
        from .orient import auto_angle
        sch = self.sch
        for eid in (only if only is not None else list(sch.elements)):
            e = sch.elements.get(eid)
            if e is None or not e.auto_angle:
                continue
            ins = [(sch.elements[k.source].x, sch.elements[k.source].y) for k in sch.links.values()
                   if k.target == eid and k.source in sch.elements]
            outs = [(sch.elements[k.target].x, sch.elements[k.target].y) for k in sch.links.values()
                    if k.source == eid and k.target in sch.elements]
            a = auto_angle(e.kind, (e.x, e.y), ins, outs)
            if a is not None and abs(((a - e.angle) + 180) % 360 - 180) > 1e-6:
                e.angle = a
                it = self.el_items.get(eid)
                if it is not None:
                    it.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
                    it.sync()
                    it.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

    def link_at(self, pt: QPointF, r: float = 6) -> "SchLinkItem | None":
        for it in self.items(QRectF(pt.x() - r, pt.y() - r, 2 * r, 2 * r)):
            if isinstance(it, SchLinkItem):
                return it
        return None


# ---- undo commands ----------------------------------------------------------------

class AddElementCmd(QUndoCommand):
    def __init__(self, scene: SchematicScene, el: SchElement):
        super().__init__(f"Add {el.label}")
        self.scene, self.el = scene, el

    def redo(self):
        self.scene.add_element(deepcopy(self.el))

    def undo(self):
        self.scene.remove_element(self.el.id)


class AddLinkCmd(QUndoCommand):
    def __init__(self, scene: SchematicScene, link: SchLink):
        super().__init__("Add connection")
        self.scene, self.link = scene, link

    def redo(self):
        self.scene.add_link(deepcopy(self.link))

    def undo(self):
        self.scene.remove_link(self.link.id)


class InsertElementCmd(QUndoCommand):
    """Drop an element onto a connection A->B: it becomes A->new->B. The
    A->new part keeps the connection's id (so its beam and any measurement
    points on it stay); new->B gets a new id."""

    def __init__(self, scene: SchematicScene, el: SchElement, link_id: str):
        super().__init__(f"Insert {el.label}")
        self.scene, self.el = scene, el
        k = scene.sch.links[link_id]
        self.old = deepcopy(k)
        self.second = SchLink(id=new_id("k"), source=el.id, target=k.target, color=k.color,
                              wavelength_nm=k.wavelength_nm)

    def redo(self):
        self.scene.add_element(deepcopy(self.el))
        self.scene.set_fields(self.old.id, {"target": self.el.id})
        self.scene.add_link(deepcopy(self.second))

    def undo(self):
        self.scene.remove_link(self.second.id)
        self.scene.set_fields(self.old.id, {"target": self.old.target})
        self.scene.remove_element(self.el.id)


class DuplicateCmd(QUndoCommand):
    """Copy elements, and the connections among them, offset on the sheet."""

    def __init__(self, scene: SchematicScene, el_ids, dx=40.0, dy=40.0):
        super().__init__("Duplicate")
        self.scene = scene
        sch = scene.sch
        idmap = {}
        self.els, self.links = [], []
        labels = {e.label for e in sch.elements.values()}
        for eid in el_ids:
            e = deepcopy(sch.elements[eid])
            idmap[eid] = e.id = new_id("s")
            e.x += dx
            e.y += dy
            prefix = SCH_KINDS[e.kind][1]
            n = 1
            while f"{prefix}{n}" in labels:
                n += 1
            e.label = f"{prefix}{n}"
            labels.add(e.label)
            self.els.append(e)
        for k in sch.links.values():
            if k.source in idmap and k.target in idmap:
                c = deepcopy(k)
                c.id, c.source, c.target = new_id("k"), idmap[k.source], idmap[k.target]
                self.links.append(c)
        self.new_ids = list(idmap.values())

    def redo(self):
        for e in self.els:
            self.scene.add_element(deepcopy(e))
        for k in self.links:
            self.scene.add_link(deepcopy(k))

    def undo(self):
        for k in self.links:
            self.scene.remove_link(k.id)
        for e in self.els:
            self.scene.remove_element(e.id)


class SchDeleteCmd(QUndoCommand):
    """Delete schematic elements (with their connections) and connections.
    The layout follows (its part and beams go too); undo brings them back
    where they were."""

    def __init__(self, scene: SchematicScene, el_ids, link_ids, on_layout=None):
        super().__init__("Delete from schematic")
        self.scene = scene
        sch = scene.sch
        lids = set(link_ids)
        for eid in el_ids:
            lids.update(k.id for k in sch.links_touching(eid))
        self.els = [deepcopy(sch.elements[e]) for e in el_ids]
        self.links = [deepcopy(sch.links[k]) for k in lids]


    def redo(self):
        for k in self.links:
            self.scene.remove_link(k.id)
        for e in self.els:
            self.scene.remove_element(e.id)

    def undo(self):
        for e in self.els:
            self.scene.add_element(deepcopy(e))
        for k in self.links:
            self.scene.add_link(deepcopy(k))


class SchSetFieldsCmd(QUndoCommand):
    def __init__(self, scene: SchematicScene, changes: dict[str, tuple[dict, dict]], text: str):
        super().__init__(text)
        self.scene, self.changes = scene, changes

    def redo(self):
        for oid, (_, new) in self.changes.items():
            self.scene.set_fields(oid, new)

    def undo(self):
        for oid, (old, _) in self.changes.items():
            self.scene.set_fields(oid, old)


# ---- schematic -> layout ----------------------------------------------------------------

def _inside_table(x, y, typ, angle, layout):
    """Shift a new part by whole hole pitches until its drawn outline is on the table."""
    b = SYMBOLS[typ].bounds
    a = math.radians(-angle)
    pts = [(q.x() * math.cos(a) - q.y() * math.sin(a), q.x() * math.sin(a) + q.y() * math.cos(a))
           for q in (b.topLeft(), b.topRight(), b.bottomLeft(), b.bottomRight())]
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    t = layout.table
    pitch = t.hole_pitch
    for _ in range(40):
        if x + min(xs) < 0:
            x += pitch
        elif x + max(xs) > t.width:
            x -= pitch
        else:
            break
    for _ in range(40):
        if y + min(ys) < 0:
            y += pitch
        elif y + max(ys) > t.height:
            y -= pitch
        else:
            break
    return x, y


def plan_update(layout: Layout, margin: float = 50.8) -> dict:
    """Work out what "Update layout from schematic" would do, without changing anything.

    New parts keep the schematic's rough arrangement: the schematic's extent is
    scaled into the table and snapped to holes. Returns
    {"new": [Component], "relabel": {comp_id: (old, new)}, "orphans": [comp_id],
     "unrouted": [(comp_id or None, comp_id or None, SchLink)]}.
    """
    sch, t = layout.schematic, layout.table
    els = list(sch.elements.values())
    new: list[Component] = []
    relabel = {}
    if els:
        xs, ys = [e.x for e in els], [e.y for e in els]
        x0, y0 = min(xs), min(ys)
        w, h = max(max(xs) - x0, 1), max(max(ys) - y0, 1)
        k = min((t.width - 2 * margin) / w, (t.height - 2 * margin) / h)
        k = min(k, 2.5)  # don't blow a tiny schematic up across a huge table
        cx = (t.width - k * w) / 2
        cy = (t.height - k * h) / 2
        taken = {(round(c.x, 1), round(c.y, 1)) for c in layout.components.values()}
        pitch, off = t.hole_pitch, t.hole_offset
        for e in els:
            c = layout.component_for(e.id)
            if c is not None:
                if e.label and c.label != e.label:
                    relabel[c.id] = (c.label, e.label)
                continue
            x = off + round((cx + (e.x - x0) * k - off) / pitch) * pitch
            y = off + round((cy + (e.y - y0) * k - off) / pitch) * pitch
            typ = SCH_KINDS[e.kind][2][0]
            x, y = _inside_table(x, y, typ, e.angle, layout)
            while (round(x, 1), round(y, 1)) in taken:  # never stack two parts on one hole
                x += pitch
            taken.add((round(x, 1), round(y, 1)))
            new.append(Component(id=new_id("c"), type=typ, x=x, y=y, angle=e.angle, label=e.label,
                                 part_number=SYMBOLS[typ].default_part, sch_id=e.id))
    orphans = [c.id for c in layout.components.values() if c.sch_id and c.sch_id not in sch.elements]
    unrouted = []
    for link in sch.links.values():
        if not layout.is_routed(link):
            a, b = layout.component_for(link.source), layout.component_for(link.target)
            unrouted.append((a.id if a else None, b.id if b else None, link))
    return {"new": new, "relabel": relabel, "orphans": orphans, "unrouted": unrouted}


# ---- editor page -------------------------------------------------------------------------

MODE_SELECT, MODE_PLACE, MODE_LINK = "select", "place", "link"


class SchematicView(QGraphicsView):
    def __init__(self, scene: SchematicScene, page: "SchematicPage"):
        super().__init__(scene)
        self.page = page
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setMouseTracking(True)
        self.link_from: str | None = None
        self._cursor = QPointF()
        self._inside = False
        self._pan = None
        self._press: dict[str, tuple[float, float]] | None = None
        self.scale(1.6, 1.6)

    def wheelEvent(self, e):
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.scale(f, f)

    def fit(self):
        self.fitInView(self.scene().items_rect().adjusted(-60, -60, 60, 60), Qt.KeepAspectRatio)

    def _el_at(self, pt):
        for it in self.items(pt):
            if isinstance(it, SchElementItem):
                return it
        return None

    def mousePressEvent(self, e):
        sc: SchematicScene = self.scene()
        if e.button() == Qt.MiddleButton:
            self._pan = e.position()
            self.setCursor(Qt.ClosedHandCursor)
            return
        pos = self.mapToScene(e.position().toPoint())
        pg = self.page
        if e.button() == Qt.LeftButton and pg.mode == MODE_PLACE:
            link = sc.link_at(pos) if self._el_at(e.position().toPoint()) is None else None
            if link is not None:  # dropped on a connection: insert into the beam path
                ln = link.line()
                d = ln.p2() - ln.p1()
                L2 = d.x() ** 2 + d.y() ** 2 or 1
                t = ((pos - ln.p1()).x() * d.x() + (pos - ln.p1()).y() * d.y()) / L2
                pos = ln.pointAt(min(0.9, max(0.1, t)))
            el = SchElement(id=new_id("s"), kind=pg.place_kind, x=round(pos.x() / GRID) * GRID,
                            y=round(pos.y() / GRID) * GRID, angle=pg.place_angle,
                            label=sc.sch.next_label(pg.place_kind), auto_angle=True)
            if link is not None:
                el.x, el.y = pos.x(), pos.y()  # exactly on the line
            if not pg.ask_part(el):
                return  # cancelled: nothing placed, still placing
            if link is not None:
                sc.undo.push(InsertElementCmd(sc, el, link.link.id))
            else:
                sc.undo.push(AddElementCmd(sc, el))
            pg.placed(el.id)
            return
        if e.button() == Qt.LeftButton and pg.mode == MODE_LINK:
            it = self._el_at(e.position().toPoint())
            if it is None:
                self.link_from = None
            elif self.link_from is None:
                self.link_from = it.el.id
            elif it.el.id != self.link_from:
                wl, color = pg.beam_style()
                sc.undo.push(AddLinkCmd(sc, SchLink(id=new_id("k"), source=self.link_from, target=it.el.id,
                                                    color=color, wavelength_nm=wl)))
                self.link_from = it.el.id
            self.viewport().update()
            return
        super().mousePressEvent(e)
        if e.button() == Qt.LeftButton:
            self._press = {i: (sc.sch.elements[i].x, sc.sch.elements[i].y) for i in sc.selected_ids()[0]}

    def mouseMoveEvent(self, e):
        self._cursor = self.mapToScene(e.position().toPoint())
        if self._pan is not None:
            d = e.position() - self._pan
            self._pan = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        if self.page.mode in (MODE_LINK, MODE_PLACE):
            self.viewport().update()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pan is not None:
            self._pan = None
            self.setCursor(Qt.ArrowCursor)
            return
        super().mouseReleaseEvent(e)
        sc: SchematicScene = self.scene()
        if self._press:
            ch = {}
            for eid, (x0, y0) in self._press.items():
                el = sc.sch.elements.get(eid)
                if el and (el.x, el.y) != (x0, y0):
                    ch[eid] = ({"x": x0, "y": y0}, {"x": el.x, "y": el.y})
            if ch:
                sc.undo.push(SchSetFieldsCmd(sc, ch, "Move"))
        self._press = None

    def keyPressEvent(self, e):
        arrows = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if e.key() in arrows:
            dx, dy = arrows[e.key()]
            step = GRID * (5 if e.modifiers() & Qt.ShiftModifier else 1)
            self.page.nudge(dx * step, dy * step)
            return
        super().keyPressEvent(e)

    def mouseDoubleClickEvent(self, e):
        it = self._el_at(e.position().toPoint())
        if it is not None:
            self.page.props.label.setFocus()
            self.page.props.label.selectAll()
            return
        super().mouseDoubleClickEvent(e)

    def enterEvent(self, e):
        self._inside = True
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._inside = False
        self.viewport().update()
        super().leaveEvent(e)

    def drawForeground(self, p, rect):
        super().drawForeground(p, rect)
        if self.page.mode == MODE_PLACE:
            it = self.scene().link_at(self._cursor)
            at = QPointF(round(self._cursor.x() / GRID) * GRID, round(self._cursor.y() / GRID) * GRID)
            if it is not None:  # hint where a click would insert into a beam
                ln = it.line()
                p.setPen(QPen(QColor(it.link.color), 5, Qt.SolidLine, Qt.RoundCap))
                p.setOpacity(0.35)
                p.drawLine(ln)
                p.setOpacity(1)
                d = ln.p2() - ln.p1()
                L2 = d.x() ** 2 + d.y() ** 2 or 1
                t = ((self._cursor - ln.p1()).x() * d.x() + (self._cursor - ln.p1()).y() * d.y()) / L2
                at = ln.pointAt(min(0.9, max(0.1, t)))
            if getattr(self, "_inside", True):  # dim copy of the symbol following the cursor
                p.save()
                p.setRenderHint(QPainter.Antialiasing)
                p.setOpacity(0.4)
                p.translate(at)
                p.rotate(-self.page.place_angle)
                SCH_SYMBOLS[self.page.place_kind](p)
                p.restore()
        if self.page.mode == MODE_LINK and self.link_from:
            el = self.scene().sch.elements.get(self.link_from)
            if el:
                p.setPen(QPen(QColor(self.page.beam_style()[1]), 1.4, Qt.DashLine))
                p.drawLine(QPointF(el.x, el.y), self._cursor)


class SchPropsPanel(QWidget):
    """Everything about a part is defined here: kind, which real part,
    part number, label, notes. The layout only places it."""

    def __init__(self, scene: SchematicScene, wavelengths: dict):
        super().__init__()
        self.scene = scene
        self.obj = None
        form = QFormLayout(self)
        self.title = QLabel("Nothing selected")
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.kind = QComboBox()
        for k, (name, _p, _t) in SCH_KINDS.items():
            self.kind.addItem(sch_icon(k, 22), name, k)
        self.part = QComboBox()
        self.part_number = QLineEdit()
        self.label = QLineEdit()
        self.auto = QCheckBox("Aim automatically from the beams")
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(70)
        self.wavelength = QComboBox()
        for name, (wl, color) in wavelengths.items():
            self.wavelength.addItem(name, (wl, color))
        self.status = QLabel("—")
        self.status.setWordWrap(True)
        form.addRow(self.title)
        form.addRow("Label", self.label)
        form.addRow("Kind", self.kind)
        form.addRow("Part", self.part)
        form.addRow("Part no.", self.part_number)
        form.addRow("", self.auto)
        form.addRow("Wavelength", self.wavelength)
        form.addRow("Notes", self.notes)
        form.addRow("Layout", self.status)
        self.rows = {"kind": self.kind, "part": self.part, "part_number": self.part_number, "auto": self.auto,
                     "wavelength": self.wavelength, "notes": self.notes}
        self.kind.activated.connect(self._kind_changed)
        self.part.activated.connect(self._part_changed)
        self.part_number.editingFinished.connect(self._pn_changed)
        self.label.editingFinished.connect(lambda: self._commit("label", self.label.text().strip()))
        self.auto.toggled.connect(self._auto_changed)
        self.wavelength.activated.connect(self._wl_changed)
        self.notes.focusOutEvent = self._notes_out
        scene.selection_info.connect(self.show_obj)
        scene.edited.connect(lambda: self.show_obj(self.obj))
        self.show_obj(None)

    def _notes_out(self, ev):
        QPlainTextEdit.focusOutEvent(self.notes, ev)
        if isinstance(self.obj, SchElement):
            self._commit("notes", self.notes.toPlainText())

    def _set_rows(self, el: bool, link: bool):
        form = self.layout()
        for key, w in self.rows.items():
            show = link if key == "wavelength" else el
            w.setVisible(show)
            lbl = form.labelForField(w)
            if lbl is not None:
                lbl.setVisible(show)

    def show_obj(self, obj):
        if obj is not None and obj.id not in self.scene.sch.elements and obj.id not in self.scene.sch.links:
            obj = None
        self.obj = obj
        is_el = isinstance(obj, SchElement)
        is_link = isinstance(obj, SchLink)
        self._set_rows(is_el, is_link)
        self.label.setEnabled(obj is not None)
        for w in (self.label, self.part, self.part_number, self.auto, self.kind, self.wavelength):
            w.blockSignals(True)
        self.label.setText(obj.label if obj else "")
        lay = self.scene.layout
        if is_el:
            self.title.setText(f"{obj.label or '—'} · {SCH_KINDS[obj.kind][0]}")
            self.kind.setCurrentIndex(self.kind.findData(obj.kind))
            self.part.clear()
            for t in SCH_KINDS[obj.kind][2]:
                self.part.addItem(SYMBOLS[t].name, t)
            self.part.setCurrentIndex(self.part.findData(obj.layout_type()))
            default = SYMBOLS[obj.layout_type()].default_part
            self.part_number.setPlaceholderText("part number")
            self.part_number.setText(obj.part_number or default)
            self.part_number.setToolTip(f"Default for this part: {default}. Type to override; clear to go back."
                                        if default else "No default part number for this part: type one in.")
            self.auto.setChecked(obj.auto_angle)
            self.notes.setPlainText(obj.notes)
            c = lay.component_for(obj.id)
            if c is None:
                self.status.setText("—")
            else:
                t = lay.table
                on = t.on_board(c.x, c.y)
                self.status.setText(f"x {c.x:.1f}, y {c.y:.1f} mm, {c.angle:.1f}°"
                                    + ("" if on else "\nWaiting below the table"))
        elif is_link:
            a, b = self.scene.sch.elements.get(obj.source), self.scene.sch.elements.get(obj.target)
            self.title.setText(f"Beam {a.label if a else '?'} → {b.label if b else '?'}")
            i = next((i for i in range(self.wavelength.count())
                      if self.wavelength.itemData(i)[1] == obj.color), -1)
            self.wavelength.setCurrentIndex(max(i, 0))
            bm = lay.beams.get(obj.id)
            if bm is not None and bm.source in lay.components and bm.target in lay.components:
                ca, cb = lay.components[bm.source], lay.components[bm.target]
                L = math.hypot(cb.x - ca.x, cb.y - ca.y)
                self.status.setText(f"{L:.1f} mm ({L / 25.4:.2f} in) on the table")
            else:
                self.status.setText("—")
        else:
            self.title.setText("Nothing selected")
            self.notes.setPlainText("")
            self.status.setText("Click a symbol or a beam. Pick a symbol on the left to add one.")
        for w in (self.label, self.part, self.part_number, self.auto, self.kind, self.wavelength):
            w.blockSignals(False)

    def _part_changed(self, _i):
        """Picking another part brings its default part number, unless one was typed in."""
        if not isinstance(self.obj, SchElement):
            return
        t = self.part.currentData()
        if t == self.obj.layout_type():
            return
        old = {"part": self.obj.part, "part_number": self.obj.part_number}
        new = {"part": t, "part_number": "" if self.obj.part_number == SYMBOLS[self.obj.layout_type()].default_part
               else self.obj.part_number}
        self.scene.undo.push(SchSetFieldsCmd(self.scene, {self.obj.id: (old, new)}, "Change part"))

    def _kind_changed(self, _i):
        if not isinstance(self.obj, SchElement):
            return
        k = self.kind.currentData()
        if k != self.obj.kind:
            self.scene.undo.push(SchSetFieldsCmd(self.scene, {self.obj.id: (
                {"kind": self.obj.kind, "part": self.obj.part, "part_number": self.obj.part_number},
                {"kind": k, "part": "", "part_number": ""})}, "Change kind"))

    def _pn_changed(self):
        """Stored as "" while it equals the part's default, so changing the part
        brings that part's default along; anything else typed is an override."""
        if not isinstance(self.obj, SchElement):
            return
        txt = self.part_number.text().strip()
        if txt == SYMBOLS[self.obj.layout_type()].default_part:
            txt = ""
        self._commit("part_number", txt)

    def _auto_changed(self, on):
        if isinstance(self.obj, SchElement):
            self._commit("auto_angle", bool(on))

    def _wl_changed(self, _i):
        if isinstance(self.obj, SchLink):
            wl, color = self.wavelength.currentData()
            self.scene.undo.push(SchSetFieldsCmd(self.scene, {self.obj.id: (
                {"wavelength_nm": self.obj.wavelength_nm, "color": self.obj.color},
                {"wavelength_nm": wl, "color": color})}, "Wavelength"))

    def _commit(self, key, val):
        if self.obj is None or getattr(self.obj, key, None) == val:
            return
        self.scene.undo.push(SchSetFieldsCmd(self.scene, {self.obj.id: ({key: getattr(self.obj, key)},
                                                                        {key: val})}, f"Edit {key}"))


class PartsTable(QDialog):
    """All parts in one spreadsheet (like KiCad's Symbol Fields Table): edit
    labels, parts and part numbers in bulk. Selecting a row selects the part."""

    COLS = ["Label", "Kind", "Part", "Part no.", "Notes"]

    def __init__(self, scene: SchematicScene, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parts table")
        self.scene = scene
        self.resize(820, 520)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(False)
        hint = QLabel("Double-click a cell to edit. Part and kind use drop-downs. Changes go on the undo stack.")
        hint.setWordWrap(True)
        export = QPushButton("Export parts list (CSV)…")
        export.clicked.connect(self._export)
        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addWidget(self.table)
        lay.addWidget(export)
        self._loading = False
        self.table.itemChanged.connect(self._item_changed)
        self.table.itemSelectionChanged.connect(self._sel)
        scene.edited.connect(self.reload)
        self.reload()

    def _rows(self):
        def key(e):
            import re
            m = re.match(r"([A-Za-z]+)(\d+)$", e.label or "")
            return (m.group(1), int(m.group(2))) if m else (e.label or "~", 0)
        return sorted(self.scene.sch.elements.values(), key=key)

    def reload(self):
        if self._loading:
            return
        self._loading = True
        els = self._rows()
        self.table.setRowCount(len(els))
        for r, e in enumerate(els):
            default = SYMBOLS[e.layout_type()].default_part
            vals = [e.label, None, None, e.part_number or default, e.notes]
            for c, v in enumerate(vals):
                if v is None:
                    continue
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, e.id)
                if c == 3 and not e.part_number:
                    it.setForeground(QColor("#777777"))
                    it.setToolTip("Default for this part; type to override")
                self.table.setItem(r, c, it)
            kind = QComboBox()
            for k, (name, _p, _t) in SCH_KINDS.items():
                kind.addItem(name, k)
            kind.setCurrentIndex(kind.findData(e.kind))
            kind.activated.connect(lambda _i, eid=e.id, w=kind: self._set(eid, {"kind": w.currentData(),
                                                                                "part": "", "part_number": ""}))
            self.table.setCellWidget(r, 1, kind)
            part = QComboBox()
            for t in SCH_KINDS[e.kind][2]:
                part.addItem(SYMBOLS[t].name, t)
            part.setCurrentIndex(part.findData(e.layout_type()))
            part.activated.connect(lambda _i, eid=e.id, w=part: self._set_part(eid, w.currentData()))
            self.table.setCellWidget(r, 2, part)
        self.table.resizeColumnsToContents()
        self._loading = False

    def _set(self, eid, fields):
        e = self.scene.sch.elements.get(eid)
        if e is None:
            return
        old = {k: getattr(e, k) for k in fields}
        if old != fields:
            self.scene.undo.push(SchSetFieldsCmd(self.scene, {eid: (old, fields)}, "Edit parts table"))

    def _set_part(self, eid, t):
        e = self.scene.sch.elements.get(eid)
        if e is None or t == e.layout_type():
            return
        keep = e.part_number if e.part_number != SYMBOLS[e.layout_type()].default_part else ""
        self._set(eid, {"part": t, "part_number": keep})

    def _item_changed(self, it):
        if self._loading:
            return
        key = {0: "label", 3: "part_number", 4: "notes"}.get(it.column())
        if key:
            val = it.text().strip()
            e = self.scene.sch.elements.get(it.data(Qt.UserRole))
            if key == "part_number" and e is not None and val == SYMBOLS[e.layout_type()].default_part:
                val = ""
            self._set(it.data(Qt.UserRole), {key: val})

    def _sel(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        els = self._rows()
        ids = {els[r].id for r in rows if r < len(els)}
        for eid, item in self.scene.el_items.items():
            item.setSelected(eid in ids)

    def _export(self):
        import csv
        p, _ = QFileDialog.getSaveFileName(self, "Export parts list", "parts.csv", "CSV (*.csv)")
        if not p:
            return
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["Label", "Kind", "Part", "Part no.", "Notes"])
            for e in self._rows():
                t = e.layout_type()
                w.writerow([e.label, SCH_KINDS[e.kind][0], SYMBOLS[t].name,
                            e.part_number or SYMBOLS[t].default_part, e.notes])


class NewPartDialog(QDialog):
    """Asked when a part is placed: what it is (size and mount), its part
    number, label and notes. Cancel places nothing."""

    def __init__(self, el: SchElement, sch, parent=None):
        super().__init__(parent)
        self.el, self.sch = el, sch
        name = SCH_KINDS[el.kind][0]
        self.setWindowTitle(f"New {name.lower()}")
        self.label = QLineEdit(el.label)
        self.part = QComboBox()
        for t in SCH_KINDS[el.kind][2]:
            self.part.addItem(SYMBOLS[t].name, t)
        self.part.setCurrentIndex(max(0, self.part.findData(el.layout_type())))
        self.part_number = QLineEdit(el.part_number or SYMBOLS[el.layout_type()].default_part)
        self.part_number.setPlaceholderText("part number")
        self._pn_typed = bool(el.part_number)
        self.part_number.textEdited.connect(lambda _t: setattr(self, "_pn_typed", True))
        self.part.currentIndexChanged.connect(self._part_changed)
        self.notes = QPlainTextEdit(el.notes)
        self.notes.setFixedHeight(70)
        self.notes.setPlaceholderText("optional, e.g. AR coating, focal length, what it is for")
        form = QFormLayout()
        form.addRow("Label", self.label)
        form.addRow("Size / mount", self.part)
        form.addRow("Part no.", self.part_number)
        form.addRow("Notes", self.notes)
        self.warn = QLabel("")
        self.warn.setStyleSheet("color:#d62728")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Place")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok = buttons.button(QDialogButtonBox.Ok)
        self.label.textChanged.connect(self._check)
        v = QVBoxLayout(self)
        v.addLayout(form)
        v.addWidget(self.warn)
        v.addWidget(buttons)
        self.resize(380, 0)
        self._check()
        self.label.selectAll()

    def _part_changed(self, _i):
        if not self._pn_typed:
            self.part_number.setText(SYMBOLS[self.part.currentData()].default_part)

    def _check(self):
        txt = self.label.text().strip()
        clash = any(e.label == txt for e in self.sch.elements.values())
        self.warn.setText("A label is needed." if not txt else f"{txt} is already used." if clash else "")
        self.ok.setEnabled(bool(txt) and not clash)

    def accept(self):
        e = self.el
        t = self.part.currentData()
        e.label = self.label.text().strip()
        e.part = t
        pn = self.part_number.text().strip()
        e.part_number = "" if pn == SYMBOLS[t].default_part else pn
        e.notes = self.notes.toPlainText().strip()
        super().accept()


class SchematicPage(QWidget):
    """Palette | schematic canvas | properties. Lives in the main window's
    Schematic tab."""

    def __init__(self, scene: SchematicScene, beam_style, wavelengths: dict | None = None):
        super().__init__()
        self.scene = scene
        self.beam_style = beam_style  # () -> (wavelength, colour), shared with the layout toolbar
        self.mode = MODE_SELECT
        self.place_kind = "mirror"
        self.place_angle = 0.0
        self.view = SchematicView(scene, self)
        self.palette = QListWidget()
        self.palette.setIconSize(QSize(30, 30))
        for k, (name, _p, _t) in SCH_KINDS.items():
            it = QListWidgetItem(sch_icon(k), name)
            it.setData(Qt.UserRole, k)
            self.palette.addItem(it)
        self.palette.itemClicked.connect(self._pick)
        from .model import WAVELENGTH_COLORS
        self.props = SchPropsPanel(scene, wavelengths or WAVELENGTH_COLORS)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel(" Schematic symbols"))
        lv.addWidget(self.palette)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(QLabel(" Properties"))
        rv.addWidget(self.props)
        rv.addStretch(1)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(self.view)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([190, 900, 240])
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(split)
        self.hint = lambda _s: None
        self.back_to_select = lambda: self.set_mode(MODE_SELECT)  # the main window also unchecks its tool

    def ask_part(self, el: SchElement) -> bool:
        """Fill in what the new part is before it goes down (fields set on el)."""
        return NewPartDialog(el, self.scene.sch, self).exec() == QDialog.Accepted

    def placed(self, eid: str):
        """After placing one part: back to Select, with the new part selected."""
        self.back_to_select()
        self.scene.clearSelection()
        it = self.scene.el_items.get(eid)
        if it is not None:
            it.setSelected(True)

    def _pick(self, item):
        self.place_kind = item.data(Qt.UserRole)
        self.set_mode(MODE_PLACE)

    def set_mode(self, mode):
        self.mode = mode
        self.view.link_from = None
        self.view.setDragMode(QGraphicsView.RubberBandDrag if mode == MODE_SELECT else QGraphicsView.NoDrag)
        if mode != MODE_PLACE:
            self.palette.clearSelection()
        self.hint({MODE_SELECT: "Schematic: drag symbols, arrows nudge, R rotates, Del deletes, Ctrl+D duplicates. "
                                "B draws beams. Double-click to rename.",
                   MODE_PLACE: f"Click to place a {SCH_KINDS[self.place_kind][0].lower()}; click on a beam to "
                               "insert it into that beam. You then say what it is; R rotates it first, Esc cancels.",
                   MODE_LINK: "Click an element, then the next one the light goes to (chains). "
                              "Click empty space to restart. Esc stops."}[mode])
        self.view.viewport().update()

    def delete_selected(self, on_layout=None):
        els, links = self.scene.selected_ids()
        if els or links:
            self.scene.undo.push(SchDeleteCmd(self.scene, els, links))

    def duplicate_selected(self):
        els, _ = self.scene.selected_ids()
        if els:
            cmd = DuplicateCmd(self.scene, els)
            self.scene.undo.push(cmd)
            self.scene.clearSelection()
            for eid in cmd.new_ids:
                self.scene.el_items[eid].setSelected(True)

    def nudge(self, dx, dy):
        els, _ = self.scene.selected_ids()
        ch = {e: ({"x": self.scene.sch.elements[e].x, "y": self.scene.sch.elements[e].y},
                  {"x": self.scene.sch.elements[e].x + dx, "y": self.scene.sch.elements[e].y + dy}) for e in els}
        if ch:
            self.scene.undo.push(SchSetFieldsCmd(self.scene, ch, "Nudge"))

    def rotate_selected(self, delta):
        if self.mode == MODE_PLACE:
            self.place_angle = (self.place_angle + delta) % 360
            return
        els, _ = self.scene.selected_ids()
        ch = {e: ({"angle": self.scene.sch.elements[e].angle, "auto_angle": self.scene.sch.elements[e].auto_angle},
                  {"angle": (self.scene.sch.elements[e].angle + delta) % 360, "auto_angle": False}) for e in els}
        if ch:
            self.scene.undo.push(SchSetFieldsCmd(self.scene, ch, "Rotate"))
