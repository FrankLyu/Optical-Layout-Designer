"""Toolbar and tab icons, drawn with QPainter (no image files). Each icon is
drawn on a 32 x 32 grid and rendered at 2x so it stays sharp on HiDPI screens."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

INK = "#3b4252"  # outlines
BLUE = "#2f6fde"
BEAM = "#9b4ddc"  # the 421 nm violet used for beams
RED = "#d62728"
GREEN = "#2e9e44"
AMBER = "#f0a020"
BOARD = "#aab0b8"


def _pen(color=INK, w=2.0, cap=Qt.RoundCap):
    return QPen(QColor(color), w, Qt.SolidLine, cap, Qt.RoundJoin)


def _poly(*pts):
    return QPolygonF([QPointF(x, y) for x, y in pts])


def _arrow_head(p: QPainter, tip, back, color, size=5.0):
    """A filled arrow head at tip, pointing away from back."""
    import math
    a = math.atan2(tip[1] - back[1], tip[0] - back[0])
    l_ = (tip[0] - size * math.cos(a - 0.45), tip[1] - size * math.sin(a - 0.45))
    r_ = (tip[0] - size * math.cos(a + 0.45), tip[1] - size * math.sin(a + 0.45))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPolygon(_poly(tip, l_, r_))


# ---- the drawings -------------------------------------------------------------------------

def _new(p):
    p.setPen(_pen(INK, 1.6))
    p.setBrush(QColor("white"))
    p.drawPolygon(_poly((7, 3), (19, 3), (25, 9), (25, 29), (7, 29)))
    p.drawPolyline(_poly((19, 3), (19, 9), (25, 9)))
    p.setPen(_pen(GREEN, 3.0))
    p.drawLine(QPointF(22, 18), QPointF(22, 30))
    p.drawLine(QPointF(16, 24), QPointF(28, 24))


def _open(p):
    p.setPen(_pen("#9a6b12", 1.6))
    p.setBrush(QColor("#f3c45a"))
    p.drawPolygon(_poly((3, 8), (12, 8), (15, 11), (28, 11), (28, 26), (3, 26)))
    p.setBrush(QColor("#f8d77f"))
    p.drawPolygon(_poly((3, 26), (8, 15), (31, 15), (28, 26)))


def _save(p):
    p.setPen(_pen("#1d4f9e", 1.6))
    p.setBrush(QColor(BLUE))
    p.drawPolygon(_poly((4, 4), (24, 4), (28, 8), (28, 28), (4, 28)))
    p.setBrush(QColor("white"))
    p.drawRect(QRectF(9, 4, 13, 8))
    p.setBrush(QColor("#e8eefb"))
    p.drawRect(QRectF(8, 17, 16, 11))
    p.setPen(_pen("#1d4f9e", 2.0))
    p.drawLine(QPointF(18, 6), QPointF(18, 10))


def _undo(p, flip=False):
    if flip:
        p.translate(32, 0)
        p.scale(-1, 1)
    path = QPainterPath(QPointF(26, 25))
    path.cubicTo(QPointF(27, 13), QPointF(18, 9), QPointF(9, 12))
    p.setPen(_pen(BLUE, 3.0))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    _arrow_head(p, (5, 13.5), (12, 11.5), BLUE, 8)


def _select(p):
    p.setPen(_pen("white", 1.6))
    p.setBrush(QColor(INK))
    p.drawPolygon(_poly((8, 3), (8, 26), (13.5, 20.5), (17.5, 29), (21, 27.5), (17, 19.5), (24.5, 19.5)))


def _beam(p):
    # two mirrors joined by a violet beam
    p.setPen(_pen(BEAM, 3.0))
    p.drawLine(QPointF(3, 25), QPointF(10, 25))
    p.drawLine(QPointF(10, 25), QPointF(10, 8))
    p.drawLine(QPointF(10, 8), QPointF(24, 8))
    _arrow_head(p, (30, 8), (24, 8), BEAM, 7)
    p.setPen(_pen(INK, 3.2, Qt.FlatCap))
    p.drawLine(QPointF(6.5, 28.5), QPointF(13.5, 21.5))
    p.drawLine(QPointF(6.5, 4.5), QPointF(13.5, 11.5))


def _point(p):
    p.setPen(_pen(BEAM, 3.0))
    p.drawLine(QPointF(2, 16), QPointF(12, 16))
    p.setPen(_pen(INK, 1.6))
    p.setBrush(QColor("#2f343b"))
    p.drawEllipse(QPointF(19, 16), 10, 10)
    p.setBrush(QColor("#c9ccd1"))
    p.drawEllipse(QPointF(19, 16), 5.5, 5.5)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(AMBER))
    p.drawEllipse(QPointF(19, 16), 3, 3)


def _ruler(p):
    p.translate(16, 16)
    p.rotate(-35)
    p.setPen(_pen("#8a6a10", 1.4))
    p.setBrush(QColor("#f2cf5b"))
    p.drawRect(QRectF(-15, -5, 30, 10))
    p.setPen(_pen("#5c460a", 1.2, Qt.FlatCap))
    for i, x in enumerate(range(-12, 14, 3)):
        p.drawLine(QPointF(x, -5), QPointF(x, -5 + (5 if i % 2 == 0 else 3)))


def _fit(p):
    p.setPen(_pen(INK, 2.4, Qt.SquareCap))
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        cx, cy = 16 - 12 * sx, 16 - 12 * sy
        p.drawLine(QPointF(cx, cy), QPointF(cx + 6 * sx, cy))
        p.drawLine(QPointF(cx, cy), QPointF(cx, cy + 6 * sy))
    p.setPen(_pen(INK, 1.2))
    p.setBrush(QColor(BOARD))
    p.drawRect(QRectF(9, 11, 14, 10))


def _table(p):
    p.setPen(_pen(INK, 1.4))
    p.setBrush(QColor("white"))
    p.drawRect(QRectF(3, 5, 26, 22))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(BLUE))
    p.drawRect(QRectF(3.7, 5.7, 24.6, 5.3))
    p.setPen(_pen(INK, 1.1, Qt.FlatCap))
    for y in (16.5, 22):
        p.drawLine(QPointF(3, y), QPointF(29, y))
    p.drawLine(QPointF(12, 5), QPointF(12, 27))


def _bom(p):
    p.setPen(_pen(INK, 1.4))
    p.setBrush(QColor("white"))
    p.drawRect(QRectF(6, 5, 20, 24))
    p.setBrush(QColor("#c9ccd1"))
    p.drawRect(QRectF(11, 3, 10, 5))
    for y in (13, 18.5, 24):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(BLUE))
        p.drawEllipse(QPointF(10.5, y), 1.6, 1.6)
        p.setPen(_pen(INK, 1.4))
        p.drawLine(QPointF(14, y), QPointF(22, y))


def _sheet(p):
    # a page with a small layout picture and a table: the printable lab sheet
    p.setPen(_pen(INK, 1.4))
    p.setBrush(QColor("white"))
    p.drawPolygon(_poly((6, 2), (21, 2), (27, 8), (27, 30), (6, 30)))
    p.drawPolyline(_poly((21, 2), (21, 8), (27, 8)))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#d5d9df"))
    p.drawRect(QRectF(9, 6, 10, 8))
    p.setPen(_pen(BEAM, 1.6))
    p.drawLine(QPointF(10, 12), QPointF(16, 12))
    p.drawLine(QPointF(16, 12), QPointF(16, 8))
    p.setPen(_pen(BLUE, 1.2, Qt.FlatCap))
    for y in (18, 22, 26):
        p.drawLine(QPointF(9, y), QPointF(24, y))
    p.drawLine(QPointF(14, 16), QPointF(14, 28))


def _text(p, sign):
    f = QFont()
    f.setPixelSize(22)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(INK))
    p.drawText(QRectF(0, 3, 22, 28), Qt.AlignCenter, "A")
    p.setPen(_pen(GREEN if sign > 0 else RED, 2.6))
    p.drawLine(QPointF(21, 10), QPointF(30, 10))
    if sign > 0:
        p.drawLine(QPointF(25.5, 5.5), QPointF(25.5, 14.5))


def _schematic(p):
    # laser box, two mirrors and a beam: the optics schematic
    p.setPen(_pen(INK, 1.4))
    p.setBrush(QColor("#e9edf3"))
    p.drawRect(QRectF(2, 20, 9, 7))
    p.setPen(_pen(RED, 2.2))
    p.drawLine(QPointF(11, 23.5), QPointF(23, 23.5))
    p.drawLine(QPointF(23, 23.5), QPointF(23, 8))
    p.drawLine(QPointF(23, 8), QPointF(30, 8))
    p.setPen(_pen(INK, 2.6, Qt.FlatCap))
    p.drawLine(QPointF(19.5, 27), QPointF(26.5, 20))
    p.drawLine(QPointF(19.5, 4.5), QPointF(26.5, 11.5))


def _layout(p):
    p.setPen(_pen("#6b7280", 1.2))
    p.setBrush(QColor("#d5d9df"))
    p.drawRoundedRect(QRectF(2, 4, 28, 24), 2, 2)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#6b7280"))
    for x in range(6, 30, 5):
        for y in range(8, 28, 5):
            p.drawEllipse(QPointF(x, y), 0.9, 0.9)
    p.setPen(_pen(BEAM, 2.2))
    p.drawLine(QPointF(5, 21), QPointF(21, 21))
    p.drawLine(QPointF(21, 21), QPointF(21, 9))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(INK))
    p.drawRect(QRectF(18, 18, 6, 6))
    p.drawRect(QRectF(18.5, 6.5, 5, 5))


def _cube(p):
    top = _poly((16, 3), (29, 9.5), (16, 16), (3, 9.5))
    left = _poly((3, 9.5), (16, 16), (16, 30), (3, 23.5))
    right = _poly((16, 16), (29, 9.5), (29, 23.5), (16, 30))
    p.setPen(_pen("#1d4f9e", 1.3))
    for poly, c in ((top, "#9cc0f5"), (left, "#4f86e6"), (right, BLUE)):
        p.setBrush(QColor(c))
        p.drawPolygon(poly)


_DRAW = {"new": _new, "open": _open, "save": _save, "undo": _undo, "redo": lambda p: _undo(p, flip=True),
         "select": _select, "beam": _beam, "point": _point, "ruler": _ruler, "fit": _fit, "table": _table,
         "bom": _bom, "bigger": lambda p: _text(p, 1), "smaller": lambda p: _text(p, -1),
         "schematic": _schematic, "layout": _layout, "3d": _cube, "sheet": _sheet}


@lru_cache(maxsize=None)
def icon(name: str) -> QIcon:
    """The named icon (see _DRAW); an empty icon for unknown names."""
    draw = _DRAW.get(name)
    if draw is None:
        return QIcon()
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.scale(2, 2)
    p.setBrush(QBrush(Qt.NoBrush))
    draw(p)
    p.end()
    pm.setDevicePixelRatio(1.0)
    return QIcon(pm)


NAMES = tuple(_DRAW)
