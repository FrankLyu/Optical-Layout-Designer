"""Automatic placement of text labels and callout boxes so they don't sit on
parts, beams or each other (a small greedy version of map-label placement).

Both the layout (part labels, measurement-point callouts) and the schematic
(element names) use it. Everything here is in scene units.
"""

from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen

_METRICS: dict[tuple[bool, str], QFontMetricsF] = {}


class CachedBounds:
    """Mixin for QGraphicsItems whose bounds depend on model data (part
    positions, angles, label spots). Qt must see the *old* bounds when
    prepareGeometryChange() runs; if the data already changed, its spatial
    index goes stale and Qt can crash later (seen when deleting parts). So the
    bounds are cached and only recomputed after geometry_changed()."""

    _br = None

    def geometry_changed(self) -> None:
        self.prepareGeometryChange()
        self._br = None

    def boundingRect(self):
        if self._br is None:
            self._br = self.compute_bounds()
        return self._br


def text_size(text: str, height: float, bold: bool = True, family: str = "Arial") -> tuple[float, float]:
    """Width and line height of text whose font pixel size is `height` scene units."""
    key = (bold, family)
    fm = _METRICS.get(key)
    if fm is None:
        f = QFont(family)
        f.setPixelSize(100)
        f.setBold(bold)
        fm = _METRICS[key] = QFontMetricsF(f)
    return fm.horizontalAdvance(text) / 100 * height, fm.height() / 100 * height


def clamp_px(mm: float, zoom: float, lo_px: float, hi_px: float) -> float:
    """A size of `mm` scene units, kept between lo_px and hi_px screen pixels."""
    zoom = max(zoom, 1e-6)
    return min(max(mm * zoom, lo_px), hi_px) / zoom


def _overlap(a: QRectF, b: QRectF) -> float:
    r = a.intersected(b)
    return 0.0 if r.isEmpty() else r.width() * r.height()


def rect_gap(a: QRectF, b: QRectF) -> float:
    """Distance between two rectangles (0 if they touch or overlap)."""
    dx = max(0.0, a.left() - b.right(), b.left() - a.right())
    dy = max(0.0, a.top() - b.bottom(), b.top() - a.bottom())
    return (dx * dx + dy * dy) ** 0.5


def _crosses(r: QRectF, seg: QLineF) -> bool:
    p1, p2 = seg.p1(), seg.p2()
    if r.contains(p1) or r.contains(p2):
        return True
    if max(p1.x(), p2.x()) < r.left() or min(p1.x(), p2.x()) > r.right():
        return False
    if max(p1.y(), p2.y()) < r.top() or min(p1.y(), p2.y()) > r.bottom():
        return False
    corners = [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]
    for i in range(4):
        if seg.intersects(QLineF(corners[i], corners[(i + 1) % 4]))[0] == QLineF.BoundedIntersection:
            return True
    return False


class Placer:
    """Greedy placement: each new box goes to its cheapest candidate, then
    becomes an obstacle for the ones after it."""

    def __init__(self, bounds: QRectF | None = None):
        self.hard: list[QRectF] = []  # parts, symbols: avoid strongly
        self.soft: list[QRectF] = []  # placed labels / callouts: avoid strongly too
        self.segments: list[QLineF] = []  # beams: avoid crossing
        self.bounds = bounds

    def add_body(self, r: QRectF) -> None:
        self.hard.append(r)

    def add_segment(self, seg: QLineF) -> None:
        self.segments.append(seg)

    def cost(self, r: QRectF, ignore: QRectF | None = None, leader: QLineF | None = None) -> float:
        area = max(r.width() * r.height(), 1e-6)
        c = 0.0
        own = rect_gap(r, ignore) if ignore is not None else None
        for b in self.hard:
            if b is ignore:
                continue
            c += 6.0 * _overlap(r, b) / area
            if own is not None and rect_gap(r, b) < own * 0.8 - 0.5:
                c += 2.0  # closer to another part than to its own: reads as that part's label
        for b in self.soft:
            c += 10.0 * _overlap(r, b) / area
        shrunk = r.adjusted(r.width() * 0.04, r.height() * 0.12, -r.width() * 0.04, -r.height() * 0.12)
        for s in self.segments:
            if _crosses(shrunk, s):
                c += 1.2
        if leader is not None:
            for b in self.hard:
                if b is not ignore and _crosses(b, leader):
                    c += 0.4
        if self.bounds is not None and not self.bounds.contains(r):
            c += 2.0 + 4.0 * (1 - _overlap(r, self.bounds) / area)
        return c

    def place(self, candidates: list[QRectF], ignore: QRectF | None = None,
              leaders: list[QLineF | None] | None = None, max_cost: float | None = None) -> int:
        """Pick a candidate (earlier ones are preferred on ties); returns its index,
        or -1 if even the best one costs more than max_cost (then nothing is placed)."""
        best, best_i = None, 0
        for i, r in enumerate(candidates):
            c = self.cost(r, ignore, leaders[i] if leaders else None) + 0.015 * i
            if best is None or c < best - 1e-9:
                best, best_i = c, i
            if c < 0.015 * (i + 1) and i < 2:
                break  # the preferred spots are free
        if max_cost is not None and best > max_cost:
            return -1
        r = candidates[best_i]
        m = r.height() * 0.4  # keep a little air between neighbouring labels
        self.soft.append(r.adjusted(-m, -m * 0.25, m, m * 0.25))
        return best_i


def around(body: QRectF, w: float, h: float, gap: float) -> list[QRectF]:
    """Candidate spots for a w x h label next to a part's body: below, above,
    right, left, then the corners, then the same a step further out."""
    out = []
    for g in (gap, gap + h * 1.1):
        cx, cy = body.center().x(), body.center().y()
        out += [
            QRectF(cx - w / 2, body.bottom() + g, w, h),
            QRectF(cx - w / 2, body.top() - g - h, w, h),
            QRectF(body.right() + g, cy - h / 2, w, h),
            QRectF(body.left() - g - w, cy - h / 2, w, h),
            QRectF(body.right() + g * 0.5, body.bottom() + g * 0.5, w, h),
            QRectF(body.left() - g * 0.5 - w, body.bottom() + g * 0.5, w, h),
            QRectF(body.right() + g * 0.5, body.top() - g * 0.5 - h, w, h),
            QRectF(body.left() - g * 0.5 - w, body.top() - g * 0.5 - h, w, h),
        ]
    return out


def callout_spots(p: QPointF, w: float, h: float, u: float) -> list[QRectF]:
    """Candidate boxes for a callout whose marker is at p, at growing distances
    in eight directions (up-right first, as a reader expects)."""
    out = []
    for d in (1.0, 2.2, 3.6, 5.2):
        e = d * u
        out += [
            QRectF(p.x() + e * 0.7, p.y() - e * 0.7 - h, w, h),  # NE
            QRectF(p.x() + e * 0.7, p.y() + e * 0.7, w, h),  # SE
            QRectF(p.x() - e * 0.7 - w, p.y() - e * 0.7 - h, w, h),  # NW
            QRectF(p.x() - e * 0.7 - w, p.y() + e * 0.7, w, h),  # SW
            QRectF(p.x() + e, p.y() - h / 2, w, h),  # E
            QRectF(p.x() - e - w, p.y() - h / 2, w, h),  # W
            QRectF(p.x() - w / 2, p.y() - e - h, w, h),  # N
            QRectF(p.x() - w / 2, p.y() + e, w, h),  # S
        ]
    return out


def nearest_on_rect(r: QRectF, p: QPointF) -> QPointF:
    return QPointF(min(max(p.x(), r.left()), r.right()), min(max(p.y(), r.top()), r.bottom()))


def draw_halo_text(p: QPainter, rect: QRectF, text: str, px: float, bold=True, color="#111111",
                   align=Qt.AlignHCenter | Qt.AlignVCenter) -> None:
    """Text with a thin white halo, so it stays readable over holes and beams."""
    f = QFont("Arial")
    f.setPixelSize(max(1, round(px * 100)))  # lay out at 100x, then scale down: smooth at any size
    f.setBold(bold)
    p.save()
    p.translate(rect.topLeft())
    p.scale(0.01, 0.01)
    r = QRectF(0, 0, rect.width() * 100, rect.height() * 100)
    path = QPainterPath()
    fm = QFontMetricsF(f)
    w = fm.horizontalAdvance(text)
    x = r.left() if align & Qt.AlignLeft else r.right() - w if align & Qt.AlignRight else r.center().x() - w / 2
    y = r.center().y() + (fm.ascent() - fm.descent()) / 2
    path.addText(QPointF(x, y), f, text)
    p.setPen(QPen(QColor(255, 255, 255, 230), px * 100 * 0.22, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path)
    p.restore()
