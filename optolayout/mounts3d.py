"""How each 2D part type stands on the table in 3D: which model, how high its
optic sits above the mount's base, and whether it goes on a post.

Plain data (no CAD libraries), shared by the 3D generator (cad3d.py) and the
bill of materials (bom.py), so the BOM lists exactly the posts the 3D model uses.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BEAM_HEIGHT = 50.8  # mm (2 in)
FLANGE_H = 6.35  # pedestal flange thickness (mm)
STOCK_POST_IN = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0)  # Ø1" pedestal post lengths


@dataclass(frozen=True)
class Model3D:
    step: str | None  # vendor STEP in component_library/step, or None = no model yet
    base_height: float  # optic centre above the mount's bottom face (mm)
    rot_x: float = 0.0  # extra pose fix before placing (deg about x)
    mirror_disc: float = 0.0  # add a Ø mirror (mm) at the optic face
    d_mirror: float = 0.0  # add a D-shaped mirror of this Ø, its straight edge 5 mm to the right of the optic (-y)
    glass_disc: float = 0.0  # add a Ø lens / plate (mm) centred on the optic
    proc: str = ""  # procedural model name when step is None
    post: bool = True  # stands on a Ø1" pedestal post with a clamping fork
    extras: tuple[tuple[str, str], ...] = ()  # (part number, description) of adapters it needs


# 2D type -> 3D model. Radiant Dyes has no public CAD yet: KM100 stands in.
MODELS: dict[str, Model3D] = {
    "mirror_1in": Model3D("KM100.step", 25.40, mirror_disc=25.4),
    # our lab's Radiant Dyes mounts are MDI-HS (1")
    "mirror_rd_1in": Model3D("MDI-HS-2-3030.stp", 26.50, mirror_disc=25.4),
    "mirror_half_in": Model3D("KM05.step", 14.73, mirror_disc=12.7),
    "mirror_rd_half_in": Model3D("MDI-HS-2-3030.stp", 26.50, mirror_disc=25.4),  # we only use MDI-HS
    "hwp": Model3D("RSP1.step", 27.73),
    "qwp": Model3D("RSP1.step", 27.73),
    "hwp_half": Model3D("RSP05.step", 13.98),
    "qwp_half": Model3D("RSP05.step", 13.98),
    "fiber": Model3D("PAF2-A4A_on_HCA3.step", 26.99, extras=(("HCA3", "Fiber port adapter for PAF2"),)),
    "iris": Model3D("IDA12.step", 12.83, rot_x=90.0),
    # no 3D model yet; listed so the bill of materials includes their posts
    "lens_lmr1": Model3D("LMR1-Step.step", 22.10, glass_disc=25.4),
    "lens_1in": Model3D("CP33-Step.step", 20.32, glass_disc=25.4),
    "lens_half_in": Model3D(None, 15.2, proc="lens_mount_half_in"),
    "shutter": Model3D("3DSR475.stp", 4.75),  # stands vertical, aperture near its base
    "hwp_crm": Model3D("CRM1T-Step.step", 22.40, glass_disc=25.4),
    "mirror_newport_half": Model3D("Newport-M05.stp", 12.66, mirror_disc=12.7),
    "mirror_polaris_half": Model3D("POLARIS-K05S1.step", 12.70, mirror_disc=12.7),
    # the lab's D-shaped mirror: DMM1 on its own column, which already puts the mirror 1" up
    "mirror_d": Model3D("DMM1_lab.step", 25.4, d_mirror=25.4),
    "qwp_crm": Model3D("CRM1T-Step.step", 22.40, glass_disc=25.4),
    # fiber coupler on a 30 mm cage: asphere in a CP33, rods, a second CP33 holding the FC/APC adapter
    "fiber_cage": Model3D("CP33-Step.step", 20.32, proc="fiber_cage"),
    "pbs": Model3D(None, 19.05, proc="cube_1in"),
    "pbs_mounted": Model3D(None, 19.05, proc="cube_1in_clamp"),
    "bs": Model3D(None, 19.05, proc="cube_1in"),
    "pbs_half": Model3D(None, 12.7, proc="cube_half_in"),
    "aom": Model3D(None, 16.0, proc="aom"),
    "laser": Model3D(None, 0.0, proc="laser", post=False),  # box on the table, output at beam height
    "dump": Model3D(None, 15.0, proc="dump"),
    "photodiode": Model3D(None, 20.0, proc="photodiode"),
}


# What each vendor model really covers on the table, seen from above: x and y
# extent (mm) of its light mesh in the library frame (3D: y to the left of the
# beam). The overlap check uses these instead of the 2D drawings, which are
# drawn a little generous. Cables that leave upwards (SR475) take no room.
MESH_FOOTPRINT = {
    "3DSR475": (-12.7, 12.7, -15.3, 25.4),
    "DMM1_lab": (-11.3, 0.4, -5.8, 29.4),
    "POLARIS-K05S1": (-14.3, 5.2, -12.7, 12.7),
    "CP33-Step": (-4.4, 4.4, -20.3, 20.3),
    "CRM1T-Step": (-7.9, 8.0, -20.4, 20.3),
    "IDA12": (-1.1, 4.7, -16.3, 21.3),
    "KM05": (-13.6, 5.4, -14.7, 14.7),
    "KM100": (-31.8, 7.5, -26.4, 26.0),
    "LMR1-Step": (-5.1, 5.1, -15.2, 15.2),
    "MDI-HS-2-3030": (-40.5, 0.0, -22.4, 26.6),
    "Newport-M05": (-22.1, 0.0, -12.7, 12.7),
    "PAF2-A4A_on_HCA3": (-12.2, 11.8, -19.0, 19.0),
    "RSP05": (-5.7, 5.7, -11.0, 11.0),
    "RSP1": (-0.9, 14.6, -28.1, 28.1),
}


# Olego boards: each mount stands on its own pillar (designed with the board),
# screwed to the 4-40 holes through a square flange. Which pillar each part
# type uses is below; each pillar's measurements (height, the seat the mount
# lands on, flange size) come from mesh/Olego/pillars.json, written by
# tools/simplify_cad.py. See docs/OLEGO_MATING.md.
OLEGO_PILLARS: dict[str, str] = {
    "mirror_rd_1in": "Olego_MDI_HS",
    "mirror_rd_half_in": "Olego_MDI_HS",
    "mirror_newport_half": "Olego_M05",  # Olego_M05_0deg is for a mirror sending the beam straight back
    "mirror_polaris_half": "Olego_polaris_0.5inch_mirror",
    "lens_1in": "Olego_CP33",
    "hwp_crm": "Olego_CP33",  # cage plates all use the CP33 pillar
    "qwp_crm": "Olego_CP33",
    "fiber_cage": "Olego_CP33",
    "lens_lmr1": "Olego_LMR1",
    "hwp_half": "Olego_RSP05",
    "qwp_half": "Olego_RSP05",
    "pbs_half": "Olego_PBS_0.5in",
    "shutter": "Olego_SR475",
    "photodiode": "PD36A2_mount",
}

OLEGO_BEAM_HEIGHT = 50.8  # the Olego pillars + mounts put the optics at 2"

# When the mount doesn't simply stand on the seat with its base face:
#  - a cube sits in the pillar's seat: optic = seat + half the cube
#  - the CRM1T's tapped boss stands proud of its plate; it lines up with the CP33s
#  - parts still drawn as simple shapes (no CAD, so no real base height) go at 2"
OLEGO_OPTIC_RULE = {"pbs_half": ("seat+", 6.35), "hwp_crm": ("fixed", OLEGO_BEAM_HEIGHT),
                    "qwp_crm": ("fixed", OLEGO_BEAM_HEIGHT), "photodiode": ("fixed", OLEGO_BEAM_HEIGHT)}

# used when pillars.json is missing (measured 2026-10-11): stem -> (height, seat, flange side)
_PILLAR_FALLBACK = {
    "Olego_CP33": (31.50, 30.50, 31.5), "Olego_LMR1": (29.90, 27.90, 31.0), "Olego_M05": (39.60, 38.10, 31.5),
    "Olego_M05_0deg": (39.60, 38.10, 31.5), "Olego_MDI_HS": (25.32, 24.30, 31.5),
    "Olego_PBS_0.5in": (45.47, 44.50, 18.8), "Olego_RSP05": (37.85, 36.80, 18.8), "Olego_SR475": (44.00, 44.00, 31.4),
    "Olego_polaris_0.5inch_mirror": (39.37, 38.10, 31.5), "PD36A2_mount": (30.80, 25.80, 31.5),
}
_pillar_info: dict | None = None


def pillar_info(stem: str) -> tuple[float, float, float]:
    """(height, seat, flange side) of an Olego pillar, mm."""
    global _pillar_info
    if _pillar_info is None:
        import json
        from pathlib import Path
        f = Path(__file__).resolve().parents[1] / "component_library" / "mesh" / "Olego" / "pillars.json"
        try:
            _pillar_info = {k: (v["height"], v["seat"], v["flange"]) for k, v in json.loads(f.read_text()).items()}
        except (OSError, ValueError, KeyError):
            _pillar_info = {}
    return _pillar_info.get(stem) or _PILLAR_FALLBACK.get(stem, (0.0, 0.0, 31.5))


# Where a mount's base face is (its tapped hole, roughly), relative to the
# optic, in the library frame (3D: x along the beam, y to the left): the
# pillar goes there, not under the optic. Measured from the meshes.
MOUNT_BASE_OFFSET = {
    "MDI-HS-2-3030": (-20.5, 2.35),
    "Newport-M05": (-9.4, 0.0),
    "POLARIS-K05S1": (-4.2, 0.0),
    "3DSR475": (0.0, 5.06),
}


def base_offset(typ: str) -> tuple[float, float]:
    m = MODELS.get(typ)
    if m is None or not m.step:
        return 0.0, 0.0
    return MOUNT_BASE_OFFSET.get(m.step.rsplit(".", 1)[0], (0.0, 0.0))


def pillar_xy(typ: str, x: float, y: float, angle: float) -> tuple[float, float]:
    """Layout (2D, y down) position of the pillar under a part at x, y turned by angle."""
    import math
    dx, dy = base_offset(typ)
    a = math.radians(angle)
    return x + math.cos(a) * dx - math.sin(a) * dy, y - (math.sin(a) * dx + math.cos(a) * dy)


# Boards drilled per part ("pyopticl", "lightflow"): no posts and no hole grid.
# Each part screws to the plate through holes drilled where it stands, on a
# block (printed adapter or machined pedestal) where the mount alone would put
# its optic too low. The plate goes on the table by 1/4-20 screws on its 1"
# design grid, placed clear of the parts. See docs/PYOPTICL_BOARD.md and
# docs/LIGHTFLOW_BOARD.md.
DRILLED_STYLES = ("pyopticl", "lightflow")
BOARD_BEAM_HEIGHT = {"olego": OLEGO_BEAM_HEIGHT, "pyopticl": 12.7, "lightflow": 25.4}
PLATE_T = {"pyopticl": 25.4, "lightflow": 12.7}  # plate thickness; other boards: 12.7 (see view3d)
SCREW_D = 4.4  # 8-32 clearance (0.172")
DOWEL_D = 2.0
TABLE_SCREW = {"pyopticl": (6.6, 10.8), "lightflow": (6.6, 0.0)}  # 1/4-20 clearance, counterbore (0: none)
BLOCK_COLOR = {"pyopticl": "#80b380", "lightflow": "#a9adb4"}  # printed adapters (PyOpticL's green), machined pedestals

# PyOpticL (UMass ion-trap group, github.com/UMassIonTrappers/PyOpticL,
# PyOpticL/library/__init__.py Baseplate, adapters.py, thorlabs.py): a 1" plate,
# the optical plane 1/2" above its top. A mount whose base is 1/2" under its
# optic (Polaris K05S1, Newport M05) screws straight on with one 8-32 from
# below; RSP05 / RSP1 / cubes sit on a printed surface adapter (two 8-32s
# across the beam), sunk in a pocket when the mount is taller than 1/2".
PYOPTICL_BEAM_HEIGHT = BOARD_BEAM_HEIGHT["pyopticl"]
PYOPTICL_PLATE_T = PLATE_T["pyopticl"]
PYOPTICL_POCKET_PAD = 5.0  # a pocket is the mount's footprint plus this all round (PyOpticL drill())


@dataclass(frozen=True)
class SurfaceAdapter:
    """PyOpticL Surface_Adapter: a printed block, two bolts bolt_spacing apart
    across the beam, its top face under the mount's base, bottom sunk in a pocket."""
    height: float
    bolt_spacing: float
    min_length: float = 0.0
    extra: float = 6.0  # wall around the bolts
    top: float | None = None  # its top face above the plate; None: right under the mount's base

    @property
    def length(self) -> float:  # along the beam
        return max(self.min_length, 2 * self.extra)

    @property
    def width(self) -> float:  # across the beam
        return self.bolt_spacing + 2 * self.extra


# which part types PyOpticL puts on a surface adapter (thorlabs.py / optics.py defaults)
PYOPTICL_ADAPTERS: dict[str, SurfaceAdapter] = {
    "hwp_half": SurfaceAdapter(10.0, 25.0),  # RSP05
    "qwp_half": SurfaceAdapter(10.0, 25.0),
    "hwp": SurfaceAdapter(10.0, 40.0),  # RSP1
    "qwp": SurfaceAdapter(10.0, 40.0),
    "photodiode": SurfaceAdapter(10.0, 40.0),  # PDA10A2
    # Beamsplitter_Cube_on_Surface_Adapter: the cube sits 1 mm deep in a block that stands on the plate
    "pbs_half": SurfaceAdapter(12.7 - 6.35 + 1.0, 25.0, 12.7 + 3.0 + 2.0, top=12.7 - 6.35 + 1.0),
    "pbs": SurfaceAdapter(1.0, 25.0, 25.4 + 3.0 + 2.0, top=1.0),
    "bs": SurfaceAdapter(1.0, 25.0, 25.4 + 3.0 + 2.0, top=1.0),
}
PYOPTICL_SCREWS = {"fiber": 3}  # 8-32s holding the mount, when not one (HCA3: three, into the pocket wall)


# LightFlow optical circuit boards (LightFlow Optics, from the QITI group, IQC
# Waterloo): a 1/2" aluminium board, every optic 1" above it. Each mount stands
# on a machined pedestal, held by 8-32 screws in holes drilled per part and
# located by M2 dowel pins; the board is held down by 1/4-20 clearance holes.
# The pedestals are the ones our lab uses, measured from the parts in
# component_library/lightflow small mount - new (STEP exports of the .SLDPRT
# files, 2026-10-19). Parts the lab has no pedestal for use the LightFlow
# library elements in Open Quantum Design's boards (github.com/OpenQuantumDesign/
# oqd-OCB, Optical Modules/json). See docs/LIGHTFLOW_BOARD.md.
@dataclass(frozen=True)
class LightFlowElement:
    name: str  # the lab part file, or the LightFlow library element
    source: str  # "lab" or "OQD"
    rect: tuple[float, float, float, float]  # footprint x0, x1, y0, y1 in the library frame (x along the beam, y left)
    screws: tuple[tuple[float, float], ...]  # 8-32 holes in the board, from the optic (library frame)
    dowels: tuple[tuple[float, float], ...] = ()  # M2 dowel holes
    top: float | None = None  # pedestal top above the board; None: under the mount's base (1" - base height)
    boxes: tuple[tuple[float, float, float, float, float, float], ...] = ()  # the solid, when not one block
    roll: float = 0.0  # the mount turned about the beam on this pedestal (deg)
    mesh: str = ""  # its real shape, mesh/LightFlow/<mesh>.ply (from step/LightFlow via tools/simplify_cad.py)


def _lf_rect(size: tuple[float, float], origin: tuple[float, float]) -> tuple[float, float, float, float]:
    """A LightFlow element's footprint from its size and origin fractions (x from
    the -x side, y from the +y side, as in the .json exports)."""
    (w, h), (ox, oy) = size, origin
    return -w * ox, w * (1 - ox), -h * (1 - oy), h * oy


_CAGE = LightFlowElement("cagemount", "lab", (-7.5, 7.5, -30.5, 30.5), ((0.0, -25.1), (0.0, 25.1)),
                         ((0.0, -10.0), (0.0, 10.0), (5.45, -10.0), (5.45, 10.0)), top=5.1, mesh="LF_cagemount")
_RSP05 = LightFlowElement("RSP05", "lab", (-0.64 - 5.1, -0.64 + 5.1, -18.0, 18.0), ((-0.64, -13.0), (-0.64, 13.0)),
                          top=11.43, mesh="LF_RSP05")
LIGHTFLOW_ELEMENTS: dict[str, LightFlowElement] = {
    # Polaris K05S1: one 8-32 from under the board through the pedestal into the mount, two dowels across the beam
    "mirror_polaris_half": LightFlowElement("polarismount", "lab", (-8.02 - 5.1, -8.02 + 5.1, -12.5, 12.5),
                                            ((-8.02, 0.0),), ((-8.02, -5.0), (-8.02, 5.0)), top=12.7,
                                            mesh="LF_polarismount"),
    "mirror_newport_half": LightFlowElement("newport_M05", "lab", (-9.4 - 6.0, -9.4 + 6.0, -12.5, 12.5),
                                            ((-9.4, 0.0),), ((-9.4, -5.0), (-9.4, 5.0)), top=12.7,
                                            mesh="LF_newport_M05"),
    # RSP05: the mount on a centre screw from below the pedestal, the pedestal on two 8-32s 26 mm apart
    "hwp_half": _RSP05,
    "qwp_half": _RSP05,
    # 1/2" cube on its seat, 6.35 mm under the beam
    "pbs_half": LightFlowElement("halfinchpbsmount", "lab", (-8.0, 8.0, -19.0, 19.0), ((0.0, -13.5), (0.0, 13.5)),
                                 ((0.0, -5.0), (0.0, 5.0)), top=25.4 - 6.35,
                                 mesh="LF_halfinchpbsmount"),
    # 30 mm cage plates (CP33, CRM1T): a 5.1 mm plate, two 8-32s 50.2 mm apart, the plate on a centre screw
    "lens_1in": _CAGE,
    "fiber_cage": _CAGE,
    "hwp_crm": _CAGE,
    "qwp_crm": _CAGE,
    # IDA12 iris on its side, screwed into a column at beam height; the column's foot is slotted
    "iris": LightFlowElement("irismount", "lab", (-4.7, 4.7, -22.23, -0.83), ((-0.16, -6.33),),
                             ((-0.15, -22.18), (-0.15, -16.28)),
                             boxes=((-4.7, 4.7, -22.23, -0.83, 0.0, 6.0), (-4.7, 4.7, -22.23, -12.83, 0.0, 35.4)),
                             roll=-90.0, mesh="LF_irismount"),
    "shutter": LightFlowElement("Shutter SRS475", "lab", _lf_rect((26.0, 60.0), (0.5, 0.583)),
                                ((0.0, -20.05), (0.0, 29.95)), mesh="LF_SRSshutter-new"),
    # Intraaction AOM on its 12.9 mm plate (IntraactionATM.json, IntraactionAOM-ATM)
    "aom": LightFlowElement("IntraactionATM", "lab", _lf_rect((53.4, 50.7), (0.5, 0.669)),
                            ((-22.75, 0.0), (22.75, 0.0)), ((0.0, 0.0),), top=12.9,
                            mesh="LF_IntraactionAOM-ATM"),
    # no lab pedestal: LightFlow library elements from the OQD boards
    "fiber": LightFlowElement("Schafter Kirchhoff collimator Ver 2", "OQD", _lf_rect((40.236, 42.0), (1.0, 0.5)),
                              ((-23.5, 15.0), (-23.5, -15.0)), ((-23.5, 5.0), (-23.5, -5.0))),
    "photodiode": LightFlowElement("1 inch photodiode", "OQD", _lf_rect((28.25, 27.0), (1.0, 0.501)),
                                   ((-21.714, 6.35), (-21.714, -6.35))),
    # D-shaped mirror (DMM1) on the lab's column ("Left D-Shaped Mirror Mount"): no pedestal, the column's
    # slotted foot takes one 8-32 and two dowels, all on the far side from the D's straight edge
    "mirror_d": LightFlowElement("Left D-Shaped Mirror Mount", "lab", (-11.3, 0.4, -5.8, 29.4), ((-4.48, 23.9),),
                                 ((-4.48, 13.95), (-4.48, 8.05))),
    "dump": LightFlowElement("Small Beam Block", "OQD", _lf_rect((12.5, 11.0), (1.0, 0.5)), ((-8.25, 0.0),)),
}


# Bodies drawn differently on a LightFlow board, library frame (x0, x1, y0, y1, z0, z1 from the optic):
# the lab's Intraaction AOM spans its plate across the beam (50.7 mm), is 25 mm along the beam and
# sits on the plate (top 12.9 mm, so 12.5 mm under the beam).
LIGHTFLOW_BODY = {"aom": (-12.5, 12.5, -16.78, 33.92, -12.5, 12.5)}


@dataclass(frozen=True)
class Block:
    """What a part stands on, on a board drilled per part: a box in the part's
    library frame (x along the beam, y left), z0..z1 above the plate top."""
    x0: float
    x1: float
    y0: float
    y1: float
    z0: float
    z1: float
    kind: str  # "adapter" (printed, PyOpticL) or "pedestal" (machined, LightFlow)


def _mount_base(typ: str) -> float | None:
    m = MODELS.get(typ)
    return m.base_height if m is not None and m.post else None


def mount_boxes(typ: str, style: str) -> list[Block]:
    """The solid(s) of the adapter or pedestal under a part on a board drilled per part."""
    base = _mount_base(typ)
    if base is None:
        return []
    if style == "pyopticl":
        a = PYOPTICL_ADAPTERS.get(typ)
        if a is None:
            return []
        top = a.top if a.top is not None else PYOPTICL_BEAM_HEIGHT - base
        bx, by = base_offset(typ)
        return [Block(bx - a.length / 2, bx + a.length / 2, by - a.width / 2, by + a.width / 2,
                      top - a.height, top, "adapter")]
    if style == "lightflow":
        e = LIGHTFLOW_ELEMENTS.get(typ)
        if e is not None and e.boxes:
            return [Block(*b, "pedestal") for b in e.boxes]
        top = e.top if e is not None and e.top is not None else BOARD_BEAM_HEIGHT["lightflow"] - base
        if top < 0.5:  # the mount alone reaches 1" (or more): it screws straight onto the board
            return []
        if e is not None:
            x0, x1, y0, y1 = e.rect
        else:  # no pedestal known: one the size of the mount's footprint
            fp = footprint(typ) or (-10.0, 10.0, -10.0, 10.0)
            x0, x1, y0, y1 = fp[0], fp[1], -fp[3], -fp[2]
        return [Block(x0, x1, y0, y1, 0.0, top, "pedestal")]
    return []


def mount_block(typ: str, style: str) -> Block | None:
    """The adapter or pedestal under a part (its bounding box), else None."""
    bs = mount_boxes(typ, style)
    if not bs:
        return None
    return Block(min(b.x0 for b in bs), max(b.x1 for b in bs), min(b.y0 for b in bs), max(b.y1 for b in bs),
                 min(b.z0 for b in bs), max(b.z1 for b in bs), bs[0].kind)


def mount_roll(typ: str, style: str) -> float:
    """How far the mount is turned about the beam on its pedestal (deg): the lab's iris stands on its side."""
    e = LIGHTFLOW_ELEMENTS.get(typ) if style == "lightflow" else None
    return e.roll if e is not None else 0.0


def sunk_depth(typ: str, style: str) -> float:
    """How deep (mm) the part's base, or its block's bottom, sits below the plate top (0 if on it)."""
    base = _mount_base(typ)
    if base is None or style not in DRILLED_STYLES:
        return 0.0
    b = mount_block(typ, style)
    bottom = b.z0 if b is not None else BOARD_BEAM_HEIGHT[style] - base
    return -bottom if bottom < -0.3 else 0.0


def _to_layout(x: float, y: float, lx: float, ly: float, angle: float) -> tuple[float, float]:
    """A point lx, ly in a part's library frame (y to the left of the beam) to layout x, y (y down)."""
    import math
    a = math.radians(angle)
    return x + math.cos(a) * lx - math.sin(a) * ly, y - (math.sin(a) * lx + math.cos(a) * ly)


def drilled_holes(typ: str, style: str, x: float, y: float, angle: float) -> list[tuple[float, float, float]]:
    """(x, y, diameter) on the layout of the holes drilled for a part: its 8-32 screws, then any dowel pins."""
    if _mount_base(typ) is None:
        return []
    bx, by = base_offset(typ)
    if style == "lightflow" and typ in LIGHTFLOW_ELEMENTS:
        e = LIGHTFLOW_ELEMENTS[typ]
        return ([(*_to_layout(x, y, sx, sy, angle), SCREW_D) for sx, sy in e.screws]
                + [(*_to_layout(x, y, sx, sy, angle), DOWEL_D) for sx, sy in e.dowels])
    if style == "pyopticl" and typ in PYOPTICL_ADAPTERS:
        s = PYOPTICL_ADAPTERS[typ].bolt_spacing / 2
        return [(*_to_layout(x, y, bx, by + d, angle), SCREW_D) for d in (-s, s)]
    n = PYOPTICL_SCREWS.get(typ, 1) if style == "pyopticl" else 1
    return [(*_to_layout(x, y, bx, by + (k - (n - 1) / 2) * 12.7, angle), SCREW_D) for k in range(n)]


def screw_count(typ: str, style: str) -> int:
    return sum(1 for h in drilled_holes(typ, style, 0.0, 0.0, 0.0) if h[2] == SCREW_D)


def table_screw_holes(table, parts) -> list[tuple[float, float]]:
    """Where the 1/4-20 screws that hold a plate drilled per part down go: on
    its 1" design grid, near each corner (and every ~8" along long edges),
    clear of every part. parts: (type, x, y, angle) of the parts on the plate."""
    import math
    boxes = []
    for typ, x, y, ang in parts:
        fp = footprint(typ) or (-12.0, 12.0, -12.0, 12.0)
        b = mount_block(typ, table.style)
        if b is not None:
            fp = (min(fp[0], b.x0), max(fp[1], b.x1), min(fp[2], -b.y1), max(fp[3], -b.y0))
        boxes.append((x, y, math.radians(ang), fp))
    d, cb = TABLE_SCREW.get(table.style, (6.6, 0.0))
    clear = max(d, cb) / 2 + 2.0

    def free(px, py):
        if not table.hole_ok(px, py) or not table.on_board(px, py):
            return False
        if min(px, py, table.width - px, table.height - py) < clear:
            return False
        for x, y, a, (x0, x1, y0, y1) in boxes:  # point in the part's 2D symbol frame (y down, angle ccw)
            dx, dy = px - x, py - y
            u, v = math.cos(a) * dx - math.sin(a) * dy, math.sin(a) * dx + math.cos(a) * dy
            if x0 - clear < u < x1 + clear and y0 - clear < v < y1 + clear:
                return False
        return True

    p, o = table.hole_pitch, table.hole_offset
    grid = [(o + i * p, o + j * p) for i in range(table.columns()) for j in range(table.rows())]
    grid = [g for g in grid if free(*g)]
    W, H = table.width, table.height
    targets = [(0, 0), (W, 0), (0, H), (W, H)]
    for (ax, ay), (bx, by) in (((0, 0), (W, 0)), ((0, H), (W, H)), ((0, 0), (0, H)), ((W, 0), (W, H))):
        n = int(math.hypot(bx - ax, by - ay) // 203.2)  # one more every 8"
        targets += [(ax + (bx - ax) * k / (n + 1), ay + (by - ay) * k / (n + 1)) for k in range(1, n + 1)]
    out = []
    for tx, ty in targets:
        best = min(grid, key=lambda g: math.hypot(g[0] - tx, g[1] - ty), default=None)
        if best is not None and best not in out and math.hypot(best[0] - tx, best[1] - ty) < 0.35 * max(W, H):
            out.append(best)
    return out


def pillar_flange(typ: str, board_style: str) -> float | None:
    """Side of the pillar flange under this part on an Olego board, else None."""
    if board_style != "olego" or typ not in OLEGO_PILLARS:
        return None
    return pillar_info(OLEGO_PILLARS[typ])[2]


def optic_height(typ: str, board_style: str, beam_height: float = DEFAULT_BEAM_HEIGHT) -> float:
    """Height of a part's optic above the board. On an Olego pillar the mount
    lands on the pillar's seat (its wide lower step, not the small raised
    locating step), so the optic is at seat + the mount's base_height;
    on a board drilled per part (PyOpticL, LightFlow) it is the board's
    standard height; otherwise the post is cut to the beam height."""
    if board_style in DRILLED_STYLES:
        return BOARD_BEAM_HEIGHT[board_style]
    if board_style == "olego" and typ in OLEGO_PILLARS:
        seat = pillar_info(OLEGO_PILLARS[typ])[1]
        rule = OLEGO_OPTIC_RULE.get(typ)
        if rule is not None:
            return rule[1] if rule[0] == "fixed" else seat + rule[1]
        m = MODELS.get(typ)
        return seat + (m.base_height if m else 0.0)
    return beam_height


TYPE_FOOTPRINT = {"fiber_cage": (-62.0, 4.4, -20.3, 20.3)}  # assemblies built in view3d


def footprint(typ: str) -> tuple[float, float, float, float] | None:
    """(xmin, xmax, ymin, ymax) of a part on the table in the 2D symbol frame
    (y down on screen), from its vendor model; None if it has none."""
    if typ in TYPE_FOOTPRINT:
        x0, x1, y0, y1 = TYPE_FOOTPRINT[typ]
        return x0, x1, -y1, -y0
    m = MODELS.get(typ)
    if m is None or not m.step:
        return None
    fp = MESH_FOOTPRINT.get(m.step.rsplit(".", 1)[0])
    if fp is None:
        return None
    x0, x1, y0, y1 = fp
    return x0, x1, -y1, -y0  # 3D y points left of the beam, 2D y points down


def post_length(model: Model3D, beam_height: float = DEFAULT_BEAM_HEIGHT) -> float:
    """Length of the Ø1" pedestal post (flange included) that puts the optic at beam height."""
    return beam_height - model.base_height


def nearest_stock(length_mm: float) -> float:
    """The stock post length (inches) closest to what is needed."""
    return min(STOCK_POST_IN, key=lambda L: abs(L * 25.4 - length_mm))
