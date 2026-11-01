"""Top-down 2D drawings of optics and their mounts, in millimetres.

The look follows Xingjian Lyu's 399 nm board drawing: each part is a flat,
coloured top view of the real mount (Radiant Dyes = red body with yellow
knobs, Thorlabs = black/grey), and 1" and 1/2" parts are drawn at their own sizes.

Every symbol is drawn in its local frame: the optical point (mirror face,
lens centre, fiber tip...) is at the origin and the optic normal / beam
direction is +x. Mounts sit behind the mirror face at -x.
Add a new component type by writing a draw function and calling register().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath,
                           QPen, QPicture)

# palette sampled from the reference drawing
RD_RED = "#ed1c24"
RD_YELLOW = "#f7d117"
BLACK = "#000000"
MIRROR = "#29abe2"
GREY_BASE = "#cfcfcf"
GREY_LIGHT = "#e9e9e9"
GREY_MID = "#a8a8a8"
GREY_DARK = "#555555"
GLASS = "#bfe6f7"
PURPLE = "#6a2c91"
AOM_BLUE = "#1f3a93"
LASER_BLUE = "#0b55a5"
OUTLINE = "#4d4d4d"


def _rect(p: QPainter, x0, x1, y0, y1, fill, outline=OUTLINE, w=0.3, radius=0.0):
    p.setPen(QPen(QColor(outline), w) if outline else Qt.NoPen)
    p.setBrush(QBrush(QColor(fill)))
    r = QRectF(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
    if radius:
        p.drawRoundedRect(r, radius, radius)
    else:
        p.drawRect(r)


def _ellipse(p: QPainter, cx, cy, rx, ry, fill, outline=OUTLINE, w=0.3):
    p.setPen(QPen(QColor(outline), w) if outline else Qt.NoPen)
    p.setBrush(QBrush(QColor(fill)))
    p.drawEllipse(QPointF(cx, cy), rx, ry)


def _scaled(draw: Callable[[QPainter], None], s: float) -> Callable[[QPainter], None]:
    def f(p: QPainter) -> None:
        p.save()
        p.scale(s, s)
        draw(p)
        p.restore()
    return f


# ---- mirrors ----------------------------------------------------------------

def _rd_mirror(p: QPainter) -> None:
    """Radiant Dyes kinematic mirror mount, 1" (top view)."""
    _ellipse(p, -21, 0, 14, 17, GREY_BASE)  # base / pedestal
    for sgn in (1, -1):  # yellow adjuster knobs behind the body
        _rect(p, -32, -23, sgn * 14, sgn * 27, RD_YELLOW, "#8a7300", radius=1.2)
        _ellipse(p, -11, sgn * 12, 3.2, 3.2, RD_YELLOW, "#8a7300")
    _rect(p, -24, -8.5, -31, 31, RD_RED, "#7a0000")
    _rect(p, -8.5, -1.2, -28, 28, BLACK, None)
    _rect(p, -1.2, 0, -22, 22, MIRROR, None)


def _tl_mirror(p: QPainter) -> None:
    """Thorlabs KM100-style kinematic mirror mount, 1" (top view)."""
    _ellipse(p, -17, 0, 11, 13, GREY_BASE)
    for sgn in (1, -1):
        _rect(p, -33, -19, sgn * 14, sgn * 18, GREY_MID, OUTLINE, radius=1)
        _rect(p, -36, -33, sgn * 12.5, sgn * 19.5, GREY_DARK, None, radius=0.8)
    _rect(p, -19, -8, -22, 22, "#3a3a3a", BLACK)
    _rect(p, -8, -1.2, -21, 21, BLACK, None)
    _rect(p, -1.2, 0, -12.7, 12.7, MIRROR, None)


def _d_mirror(p: QPainter) -> None:
    """D-shaped 1" mirror in a DMM1, on the lab's column (top view): the D's
    straight edge on the outside (+y, down on screen), the holder's arm back
    to a column and its slotted foot on the other side."""
    _rect(p, -9.2, -0.4, -29.4, -6.8, GREY_BASE)  # foot with its slot
    _rect(p, -8.2, -1.6, -27.4, -17.4, GREY_DARK, None, radius=2.0)
    _rect(p, -10.5, -1.2, -17.4, -8.0, GREY_MID)  # column
    _rect(p, -11.3, -0.6, -8.0, 5.8, BLACK, None)  # DMM1 holder
    _rect(p, -0.6, 0.4, -7.7, 5.0, MIRROR, None)  # the D mirror, straight edge at +5 (outside)


def _newport_m05(p: QPainter) -> None:
    """Newport M05 kinematic mount for 1/2" optics (top view): compact black
    body, two adjuster screws at the back, the mirror flush with the front."""
    _ellipse(p, -9, 0, 7, 8, GREY_BASE)  # post / base
    for sgn in (1, -1):  # adjusters
        _rect(p, -19, -12.5, sgn * 5.5, sgn * 9.5, "#9a9a9a", "#555555", 0.25, radius=0.8)
        _rect(p, -21, -19, sgn * 6.0, sgn * 9.0, "#555555", None, radius=0.5)
    _rect(p, -12.5, -1.0, -11, 11, "#141414", BLACK, 0.3, radius=0.8)
    _rect(p, -1.0, 0, -6.35, 6.35, MIRROR, None)


# ---- transmissive optics in mounts ---------------------------------------------

def _optic_mount(optic_fill: str) -> Callable[[QPainter], None]:
    """Fixed lens / waveplate mount on a post, 1" (top view, beam along x)."""
    def draw(p: QPainter) -> None:
        for sgn in (1, -1):  # side rails
            _rect(p, -21, 15, sgn * 19, sgn * 22.5, GREY_LIGHT, "#888888", 0.25)
        _rect(p, -17, 9, -19, 19, "#dcdcdc", "#777777")
        _rect(p, -14, 7, -12.5, 12.5, GREY_MID, None)
        _rect(p, -1.6, 1.6, -15, 15, optic_fill, OUTLINE)
        _rect(p, 8, 14, -24, 24, BLACK, None)
        _rect(p, 14, 19, -20, 20, GREY_DARK, None)
        for sgn in (1, -1):  # split clamp bars at the back
            _rect(p, -23, -18.5, sgn * 3, sgn * 24, BLACK, None)
    return draw


def _lmr_mount(p: QPainter) -> None:
    """Thorlabs LMR1 fixed lens mount, 1" (top view): a thin black ring plate
    seen edge-on, the lens inside it, and the retaining-ring slot on top."""
    _rect(p, -4.3, 4.3, -19.5, 19.5, "#1c1c1c", BLACK, 0.3, radius=1.2)  # mount body
    _rect(p, -2.2, 2.2, -12.7, 12.7, GLASS, OUTLINE, 0.3, radius=1.0)  # lens, edge-on
    _rect(p, -4.3, -2.6, -14.5, 14.5, GREY_DARK, None)  # retaining ring
    _rect(p, -1.6, 1.6, -23.0, -19.5, GREY_MID, "#555555", 0.25)  # set screw / tab


def _cage_rotation(plate: str) -> Callable[[QPainter], None]:
    """Waveplate in a 30 mm cage-plate rotation mount (Thorlabs CRM1T), top
    view: the square cage plate edge-on with its rod bosses, and the
    graduated rotating ring sticking out on the beam side."""
    def draw(p: QPainter) -> None:
        _rect(p, -6.4, 6.4, -20.5, 20.5, "#1e1e1e", BLACK, 0.3, radius=1.0)  # cage plate
        for y in (-15, 15):  # cage-rod bosses
            _rect(p, -8.0, 8.0, y - 2.2, y + 2.2, GREY_DARK, None)
        _rect(p, 6.4, 11.5, -18.5, 18.5, "#2b2b2b", BLACK, 0.3)  # rotating ring with the scale
        for y in range(-16, 17, 4):
            _rect(p, 11.5, 12.6, y - 0.25, y + 0.25, "#d0d0d0", None)
        _rect(p, -1.2, 1.2, -12.7, 12.7, plate, "#333333", 0.25)  # the waveplate
    return draw


def _waveplate(plate: str) -> Callable[[QPainter], None]:
    """Waveplate in a rotation mount (top view): black mount ring seen edge-on
    with the plate attached directly to its face, as in the reference."""
    def draw(p: QPainter) -> None:
        _rect(p, -9, 0, -20.5, 20.5, BLACK, None)
        _rect(p, 0, 7.5, -18, 18, plate, "#333333", 0.3)
    return draw


# ---- cubes ------------------------------------------------------------------------

def _cube(s: float, fill: str = GLASS) -> Callable[[QPainter], None]:
    def draw(p: QPainter) -> None:
        h = s / 2
        _rect(p, -h, h, -h, h, fill, OUTLINE, 0.35)
        p.setPen(QPen(QColor(OUTLINE), 0.35))
        p.drawLine(QPointF(-h, h), QPointF(h, -h))
    return draw


def _mounted_cube(p: QPainter) -> None:
    """PBS cube held by a clamp bar (as in the reference). Place waveplates
    on either side as separate parts to get the purple/black look."""
    _rect(p, -16, 16, -15.5, 15.5, "#f2f2f2", "#777777")
    _rect(p, -12.7, 12.7, -12.7, 12.7, "#9cc6dc", OUTLINE)
    p.setPen(QPen(QColor(OUTLINE), 0.35))
    p.drawLine(QPointF(-12.7, -12.7), QPointF(12.7, 12.7))
    _rect(p, -4, 4, -20, 20, QColor(0, 0, 0, 165), None)  # translucent clamp


# ---- active / sources / fibers ---------------------------------------------------

def _aom(p: QPainter) -> None:
    """AOM housing: the beam crosses its short side."""
    _rect(p, -4, 4, 33, 39, "#222222", None)  # RF connector
    _rect(p, -12.5, 12.5, -33, 33, AOM_BLUE, "#0d1d4d", 0.4)
    p.save()
    p.rotate(90)
    f = QFont("Arial")
    f.setPixelSize(5)
    p.setFont(f)
    p.setPen(QPen(QColor("#ffffff")))
    p.drawText(QRectF(-30, -5, 20, 10), Qt.AlignVCenter | Qt.AlignLeft, "AOM")
    p.restore()


LASER_BOX = QRectF(-160, -60, 160, 120)  # the layout writes the laser's name inside this box


def _laser(p: QPainter) -> None:
    _rect(p, -160, 0, -60, 60, LASER_BLUE, BLACK, 1.0)
    _rect(p, 0, 1.5, -16, 16, RD_RED, None)  # output window


def _fiber(p: QPainter) -> None:
    """Fiber launcher on a kinematic stage; beam leaves/enters at +x."""
    _rect(p, -50, -10, -18, 18, GREY_LIGHT, "#888888", 0.25)
    for y in (-14, 14):
        _rect(p, -52, -10, y - 1.5, y + 1.5, "#f4f4f4", "#888888", 0.25)
    _rect(p, -48, -14, -6, 6, "#e2e2e2", "#777777")
    path = QPainterPath()
    path.moveTo(-56, -14)
    path.arcTo(QRectF(-70, -14, 28, 28), 90, 180)
    path.closeSubpath()
    p.setPen(QPen(QColor("#888888"), 0.25))
    p.setBrush(QBrush(QColor("#dcdcdc")))
    p.drawPath(path)
    _rect(p, -76, -70, -3.5, 3.5, "#f0f0f0", "#888888", 0.25)
    _rect(p, -60, -55, -24, 24, BLACK, None)
    _rect(p, -36, -27, -24, 24, BLACK, None)
    _rect(p, -36, -20, 22, 40, BLACK, None)  # adjuster bracket
    _rect(p, -56, -36, 28, 38, "#777777", None, radius=1)  # knob
    _rect(p, -10, -5, -19, 19, PURPLE, None)
    _rect(p, -5, 0, -22, 22, BLACK, None)


def _shutter(p: QPainter) -> None:
    """Stanford Research SR475 shutter head standing on end (top view): the
    25 x 41 mm housing the beam passes through near one side. Its cable leaves
    from the top, so it takes no room on the table (drawn as a dot)."""
    _rect(p, -12.7, 12.7, -25.4, 15.3, "#2b2b2b", BLACK, 0.35, radius=1.5)
    _rect(p, -12.7, 12.7, -2.5, 2.5, "#4a4a4a", None)  # aperture channel
    _rect(p, -1.0, 1.0, -5.5, 5.5, "#c9a227", None)  # blade
    _ellipse(p, 0, -15, 2.6, 2.6, "#555555", "#222222", 0.3)  # cable, going up


def _beam_entry(p: QPainter) -> None:
    """Where a beam comes onto the board from outside it (another table, a
    periscope from above...): nothing stands there, so just a marker."""
    p.setPen(QPen(QColor("#444444"), 0.6))
    p.setBrush(QBrush(QColor("#ffffff")))
    p.drawEllipse(QPointF(0, 0), 4.5, 4.5)
    p.setBrush(QBrush(QColor("#444444")))
    p.drawEllipse(QPointF(0, 0), 1.6, 1.6)
    p.setPen(QPen(QColor("#444444"), 0.6, Qt.DashLine))
    p.drawLine(QPointF(-14, 0), QPointF(-5, 0))  # comes from off the board


def _fiber_cage(p: QPainter) -> None:
    """Fiber coupler on a 30 mm cage (top view): CP33 with a small asphere at
    the front, four rods back to a CP33 holding the FC/APC adapter, the
    connector with its green APC boot, and the fiber."""
    for y in (-15, 15):  # cage rods
        _rect(p, -29.4, 4.4, y - 3, y + 3, "#c9ccd1", "#8a8a8a", 0.25)
    for x in (0.0, -25.0):  # the two cage plates
        _rect(p, x - 4.4, x + 4.4, -20.3, 20.3, "#1c1c1c", BLACK, 0.3, radius=0.8)
    _rect(p, -1.5, 1.5, -4, 4, GLASS, OUTLINE, 0.25)  # asphere
    _rect(p, -33.5, -29.4, -9, 9, "#2b2b2b", None)  # FC/APC adapter
    _rect(p, -46, -33.5, -3.6, 3.6, "#c9ccd1", "#777777", 0.25)  # connector
    _rect(p, -60, -46, -2.6, 2.6, "#2e9e3e", None)  # APC boot
    _rect(p, -80, -60, -1.2, 1.2, "#1f5fbf", None)  # fiber


def _iris(p: QPainter) -> None:
    _ellipse(p, -6, 0, 6, 6, GREY_BASE)
    _rect(p, -2, 2, -16, -2.5, BLACK, None)
    _rect(p, -2, 2, 2.5, 16, BLACK, None)
    _rect(p, -1, 1, 16, 21, GREY_DARK, None)  # lever


def _dump(p: QPainter) -> None:
    _ellipse(p, 9, 0, 9, 9, "#2b2b2b", BLACK)
    _rect(p, 0, 4, -6, 6, "#555555", None)


def _photodiode(p: QPainter) -> None:
    _rect(p, 0, 14, -10, 10, "#3c4a5c", BLACK, 0.3)
    _rect(p, 0, 1.6, -3.5, 3.5, MIRROR, None)
    _rect(p, 14, 20, -3, 3, "#222222", None)


# ---- registry ----------------------------------------------------------------------

@dataclass
class SymbolDef:
    key: str
    name: str
    draw: Callable[[QPainter], None]
    default_part: str = ""
    group: str = ""
    physical: bool = True  # False: a marker only (nothing stands on the table, not in the BOM)
    _bounds: QRectF | None = None

    @property
    def bounds(self) -> QRectF:
        """Local bounding rect (mm), measured from the drawing on first use
        (needs a running QApplication because symbols draw text)."""
        if self._bounds is None:
            pic = QPicture()
            p = QPainter(pic)
            self.draw(p)
            p.end()
            self._bounds = QRectF(pic.boundingRect()).adjusted(-0.5, -0.5, 0.5, 0.5)
        return self._bounds


SYMBOLS: dict[str, SymbolDef] = {}


def register(key: str, name: str, draw, default_part: str = "", group: str = "", physical: bool = True) -> None:
    SYMBOLS[key] = SymbolDef(key, name, draw, default_part, group, physical)


HALF = 0.62  # 1/2" parts drawn at this fraction of the 1" drawing

register("mirror_rd_1in", 'Mirror 1" (Radiant Dyes)', _rd_mirror, "Radiant Dyes MNI-HS", "Mirrors")
register("mirror_rd_half_in", 'Mirror 1/2" (Radiant Dyes)', _scaled(_rd_mirror, HALF), "Radiant Dyes MNI 1/2\"",
         "Mirrors")
register("mirror_1in", 'Mirror 1" (Thorlabs)', _tl_mirror, "KM100", "Mirrors")
register("mirror_half_in", 'Mirror 1/2" (Thorlabs)', _scaled(_tl_mirror, 0.58), "KM05", "Mirrors")
register("mirror_newport_half", 'Mirror 1/2" (Newport M05)', _newport_m05, "M05", "Mirrors")
register("mirror_polaris_half", 'Mirror 1/2" (Thorlabs Polaris)', _scaled(_tl_mirror, 0.55), "POLARIS-K05S1",
         "Mirrors")
register("mirror_d", 'D-shaped mirror 1" (DMM1, lab column)', _d_mirror, "DMM1", "Mirrors")
register("lens_lmr1", 'Lens 1" in LMR1', _lmr_mount, "LMR1", "Lenses & plates")
register("lens_1in", 'Lens 1" in cage plate CP33', _optic_mount(GLASS), "CP33", "Lenses & plates")
register("lens_half_in", 'Lens 1/2" in LMR05', _scaled(_lmr_mount, HALF), "LMR05", "Lenses & plates")
register("hwp", 'Half-wave plate 1"', _waveplate("#f4c430"), "RSP1", "Lenses & plates")
register("hwp_half", 'Half-wave plate 1/2"', _scaled(_waveplate("#f4c430"), HALF), "RSP05", "Lenses & plates")
register("qwp", 'Quarter-wave plate 1"', _waveplate("#7cc576"), "RSP1", "Lenses & plates")
register("hwp_crm", 'Half-wave plate 1" in cage rotation mount', _cage_rotation("#f4c430"), "CRM1T", "Lenses & plates")
register("qwp_crm", 'Quarter-wave plate 1" in cage rotation mount', _cage_rotation("#7cc576"), "CRM1T",
         "Lenses & plates")
register("qwp_half", 'Quarter-wave plate 1/2"', _scaled(_waveplate("#7cc576"), HALF), "RSP05", "Lenses & plates")
register("pbs", 'PBS cube 1"', _cube(25.4), "PBS251", "Cubes")
register("pbs_half", 'PBS cube 1/2"', _cube(12.7), "PBS121", "Cubes")
register("pbs_mounted", "PBS, clamp mount", _mounted_cube, "PBS251", "Cubes")
register("bs", 'Beam splitter 1" (NPBS)', _cube(25.4, "#eef4f7"), "BS013", "Cubes")
register("aom", "AOM", _aom, "", "Active")  # model depends on wavelength / frequency: set it per part
register("laser", "Laser box", _laser, "", "Sources & fibers")
register("beam_entry", "Beam entering at the table edge", _beam_entry, "", "Sources & fibers", physical=False)
register("shutter", "Shutter SR475", _shutter, "SR475", "Active")
register("fiber", "Fiber launcher", _fiber, "PAF2-A4A", "Sources & fibers")
register("fiber_cage", "Fiber coupler, cage (asphere + FC/APC)", _fiber_cage, "2x CP33 + SM1FCA", "Sources & fibers")
register("iris", "Iris", _iris, "IDA12", "Other")
register("dump", "Beam dump", _dump, "LB1", "Other")
register("photodiode", "Photodiode", _photodiode, "PDA36A2", "Other")


def make_icon(key: str, size: int = 40):
    """Render a symbol into a QIcon for the toolbox."""
    from PySide6.QtGui import QIcon, QPixmap

    sym = SYMBOLS[key]
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    b = sym.bounds
    scale = (size - 4) / max(b.width(), b.height())
    p.translate(size / 2, size / 2)
    p.scale(scale, scale)
    p.translate(-b.center())
    sym.draw(p)
    p.end()
    return QIcon(pm)
