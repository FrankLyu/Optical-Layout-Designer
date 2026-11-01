"""Make examples/small_board.json: the small irregular Olego board, reconstructed
from a top-down photo (2026-10-11).

Positions were read off the photo (pixel coordinates in a 1500 x 2000 copy)
and mapped to the board with a perspective fit through its four corners, then
snapped to the 1/4" half-grid. The AOMs are left out for now.

Beam path, as traced:
  beam from the 2nd table (right edge) -> M1 (Radiant Dyes, right) -> HWP1 (cage
  rotation mount) -> PBS1 -> M2 -> telescope L1 f=150 / L2 f=-75 (two CP33 cage
  plates) -> M3 -> HWP2 -> PBS2 -> M4 -> M5 (Radiant Dyes, left) -> SR475 shutter
  -> HWP3 -> QWP1 (cage rotation mount, "420 QWP") -> fiber coupler FC1 (bottom)
  PBS1 reflected -> off the board's right edge (a viewing card on the main table)
  PBS2 reflected -> M6 -> SRS detector with ND2 filter (NDUV20A)
  M7 -> (AOM) -> M8 -> M9 -> HWP4 -> fiber coupler FC2 (A375TM-A, top); where M7
  gets its light is not visible in the photo.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from optolayout.model import Component, Layout, SchElement, SchLink, Table  # noqa: E402

W, H_UPPER, H = 254.0, 355.6, 482.6  # 10 x 14 in main area + 4 x 5 in strip (olego_onDy2_board.SLDPRT)
# board corners in the photo -> mm (upper rectangle)
PHOTO = [(403, 272), (1140, 287), (1172, 1290), (386, 1292)]
BOARD = [(0, 0), (W, 0), (W, H_UPPER), (0, H_UPPER)]


def homography(src, dst):
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.array(A, float))
    return vt[-1].reshape(3, 3)


HM = homography(PHOTO, BOARD)
STEP = 6.35  # 1/4": the grid holes plus the centre holes


def to_mm(px, py, snap=True):
    u, v, w = HM @ [px, py, 1]
    x, y = u / w, v / w
    if snap:
        x, y = round(x / STEP) * STEP, round(y / STEP) * STEP
    return min(max(x, 0.0), W), min(max(y, 0.0), H)


lay = Layout(table=Table(name="Olego board, 399 nm (from photo)", width=W, height=H,
                         cutouts=[[101.6, H_UPPER, W - 101.6, H - H_UPPER]]))
lay.table.apply_style("olego")
sch = lay.schematic

# id: (kind, layout type, label, photo x, photo y, part number, notes)
PARTS = {
    "in": ("laser", "beam_entry", "From 2nd table", 1172, 790, "", "Beam arrives from the 2nd table from the right"),
    "m1": ("mirror", "mirror_rd_1in", "M1", 1135, 790, "", ""),
    "hwp1": ("hwp", "hwp_crm", "HWP1", 1140, 945, "", "Cage rotation mount on a pedestal"),
    "pbs1": ("pbs", "pbs", "PBS1", 1140, 1055, "", "Marked 420"),
    "m2": ("mirror", "mirror_rd_1in", "M2", 1150, 1150, "", ""),
    "l1": ("lens", "lens_1in", "L1", 1020, 1150, "", "f = 150 mm UV (EO 32494); telescope, cage rods to L2"),
    "l2": ("lens", "lens_1in", "L2", 705, 1150, "", "f = -75 mm UVFS; telescope with L1"),
    "m3": ("mirror", "mirror_newport_half", "M3", 590, 1150, "", ""),
    "hwp2": ("hwp", "hwp_half", "HWP2", 615, 1050, "", "Labelled 421 HWP"),
    "pbs2": ("pbs", "pbs_half", "PBS2", 615, 985, "", ""),
    "m6": ("mirror", "mirror_newport_half", "M6", 905, 985, "", "Small black kinematic mount with red knob"),
    "det": ("photodiode", "photodiode", "DET", 905, 870, "SRS + NDUV20A", "SRS unit with NDUV20A ND 2.0 filter tube"),
    "m4": ("mirror", "mirror_newport_half", "M4", 630, 835, "", ""),
    "m5": ("mirror", "mirror_rd_1in", "M5", 470, 815, "", ""),
    "sh": ("shutter", "shutter", "SH1", 470, 1050, "", "SR475 #5136"),
    "hwp3": ("hwp", "hwp_half", "HWP3", 475, 1335, "", ""),
    "qwp1": ("qwp", "qwp_crm", "QWP1", 475, 1475, "", "Labelled 420 QWP; cage rods down to FC1"),
    "fc1": ("fiber", "fiber", "FC1", 470, 1650, "", "Fiber leaves through the enclosure floor"),
    "m7": ("mirror", "mirror_rd_1in", "M7", 945, 575, "", "Feeds the AOM (removed for now)"),
    "m8": ("mirror", "mirror_rd_1in", "M8", 530, 475, "", "Large Radiant Dyes mount"),
    "m9": ("mirror", "mirror_rd_1in", "M9", 480, 345, "", "Large Radiant Dyes mount"),
    "hwp4": ("hwp", "hwp_half", "HWP4", 705, 335, "", ""),
    "fc2": ("fiber", "fiber", "FC2", 880, 320, "A375TM-A", "f = 7.5 mm asphere in a cage XY mount, Z micrometer"),
    # in the lower part, not on a beam in the photo
    "pbs3": ("pbs", "pbs_half", "PBS3", 645, 1310, "", "Not on a beam in the photo"),
    "hwp5": ("hwp", "hwp_half", "HWP5", 645, 1460, "", "Labelled 421; not on a beam in the photo"),
    "pbs4": ("pbs", "pbs_half", "PBS4", 645, 1580, "", "Not on a beam in the photo"),
    "pbs5": ("pbs", "pbs_half", "PBS5", 645, 1720, "", "Not on a beam in the photo"),
}
BEAMS = [
    ("in", "m1", "hwp1", "pbs1", "m2", "l1", "l2", "m3", "hwp2", "pbs2", "m4", "m5", "sh", "hwp3", "qwp1", "fc1"),
    ("pbs2", "m6", "det"),
    ("m7", "m8", "m9", "hwp4", "fc2"),
]

for eid, (kind, typ, label, px, py, pn, notes) in PARTS.items():
    x, y = to_mm(px, py)
    if eid == "in":
        x = W  # at the board's edge
    # the schematic keeps the same arrangement, spread out a little
    sch.elements[eid] = SchElement(id=eid, kind=kind, x=round(x * 1.6 / 10) * 10, y=round(y * 1.6 / 10) * 10,
                                   label=label, part=typ, part_number=pn, notes=notes)
    lay.components[f"c_{eid}"] = Component(id=f"c_{eid}", type=typ, x=x, y=y, label=label, sch_id=eid,
                                           pinned=True, auto_angle=True)
# parts on one straight beam share a row or column (the photo is a few mm off)
ROWS = [["in", "m1"], ["m2", "l1", "l2", "m3"], ["pbs2", "m6"], ["m4", "m5"], ["m9", "hwp4", "fc2"]]
COLS = [["m1", "hwp1", "pbs1", "m2"], ["m3", "hwp2", "pbs2", "m4"], ["m5", "sh", "hwp3", "qwp1", "fc1"], ["m6", "det"]]
for ids, attr in [(ids, "y") for ids in ROWS] + [(ids, "x") for ids in COLS]:
    parts = [lay.components[f"c_{eid}"] for eid in ids if f"c_{eid}" in lay.components]
    v = round(sum(getattr(c, attr) for c in parts) / len(parts) / STEP) * STEP
    for c in parts:
        setattr(c, attr, v)
lay.components["c_in"].x = W  # the beam arrives at the board's edge
for eid, el in sch.elements.items():
    c = lay.components[f"c_{eid}"]
    el.x, el.y = round(c.x * 1.6 / 10) * 10, round(c.y * 1.6 / 10) * 10

for chain in BEAMS:
    for a, b in zip(chain, chain[1:]):
        sch.links[f"k_{a}_{b}"] = SchLink(id=f"k_{a}_{b}", source=a, target=b, color="#b77fd0", wavelength_nm=399.0)

if __name__ == "__main__":
    for eid in PARTS:
        c = lay.components[f"c_{eid}"]
        print(f"{eid:6s} {c.x:7.2f} {c.y:7.2f}")
    print("board bottom in the photo maps to y =", round(to_mm(400, 1762, False)[1], 1),
          "; notch edge x =", round(to_mm(712, 1500, False)[0], 1))
    out = Path(__file__).with_name("small_board.json")
    lay.save(out)
    print("wrote", out)
