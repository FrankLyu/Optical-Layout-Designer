"""Make 421nm_system/Dy1-lowpower.json: the 421 nm low-power LightFlow board.

Reconstructed from a top-down photo (2026-10-19): positions were read off the
photo with a perspective fit through the board's corners (board size about
17 x 16 in, an estimate), then the mirrors that turn the beam were moved onto
the beam lines Jiahao drew over the first draft.

Beam path:
  The 30 mW 421 nm laser comes in from the left edge -> M10 -> M1 -> HWP1 -> PBS1
  -> double pass 1: AOM1 -> HWP2 -> cage telescope L1/L2 -> IR1 -> M2 (retro).
  The returning light leaves PBS1 upwards -> M3 -> IR2 -> HWP3 -> PBS2.
  PBS2 transmits -> HWP4 -> PBS3, which splits into two fiber couplers:
    transmitted: HWP5 -> M4 -> M19 -> FC5;  reflected: HWP10 -> HWP9 -> M16 -> M20 -> M18 -> FC4.
  PBS2 reflects up -> HWP11 -> PBS4 -> M11 -> M6 -> double pass 2: AOM2 (upper left)
  -> HWP8 -> L3 -> M9 (retro). The returning light reflects off PBS4 -> PBS5, which
  splits into two fiber couplers:  M12 -> M15 -> M14 -> FC2  and  M13 -> M7 -> FC1.
  AOM2's 0th order is picked off near the retro mirror by the D-shaped mirror DM1
  -> M8 -> L4 -> M21 -> AOM3 -> M17 -> M5 -> HWP6 -> HWP7 -> SR475 shutter -> FC3
  (the top fiber coupler on the right edge).
In the schematic a double pass is drawn one way only: the retro mirror ends the
chain and the returning light starts again at the PBS that sends it on.

Red Radiant Dyes mounts are drawn as Newport M05 for now. PBS4 and PBS5 are the
lab's plate beam splitters (planebeamsplitter mount), drawn as 1/2" cubes. The
five fiber couplers stand on the table at the board's top and right edges; they
are drawn just inside the edge.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from optolayout.model import Component, Layout, SchElement, SchLink, Table  # noqa: E402

IN = 25.4
W, H = 17 * IN, 16 * IN
lay = Layout(table=Table(name="Dy1-lowpower", width=W, height=H))
lay.table.apply_style("lightflow")
sch = lay.schematic

PM, RED, HWP, PBS = "mirror_polaris_half", "mirror_newport_half", "hwp_half", "pbs_half"
# beam lines (mm from the board's top-left corner)
X_IN, Y_IN = 32.4, 322.3  # input mirror M10 (the laser comes in from the left at this height)
Y1, Y2 = 361.9, 298.4  # DP1 row, middle row
X_DP2, X_UP = 31.8, 177.8  # DP2 column (upper left), PBS2 -> PBS4 column
Y_TOP, Y_SPLIT, Y_FC1 = 6.3, 62.0, 26.0  # top row (M11 -> M6), PBS4 -> PBS5, PBS5 -> M7
Y_0TH, X_0TH, Y_AOM3 = 225.7, 82.3, 175.8  # 0th order: DM1 -> M8, M8 column, AOM3 row
X_M17, Y_SH = 277.6, 120.6  # M17 column, shutter row
X_PBS3, Y_M16, X_M20, Y_FC4 = 254.0, 243.0, 338.1, 198.9  # PBS3's reflection to FC4
X_M4, Y_FC5 = 317.5, 272.4  # PBS3's transmission to FC5
X_PBS5, X_M12, Y_M15, X_FC2 = 300.7, 372.4, 31.0, 255.0
X_FC1 = 111.7
X_FC = 412.8  # fiber couplers on the right edge

# id: (kind, layout type, label, x, y, angle (unlinked ends), notes)
PARTS = {
    "in": ("laser", "beam_entry", "421 nm, 30 mW", 0.0, Y_IN, 0, "Laser comes onto the board from the left"),
    "m10": ("mirror", PM, "M10", X_IN, Y_IN, 0, "Takes the laser"),
    "m1": ("mirror", PM, "M1", X_IN, Y1, 0, ""),
    "hwp1": ("hwp", HWP, "HWP1", 57.1, Y1, 0, ""),
    "pbs1": ("pbs", PBS, "PBS1", 95.2, Y1, 0, "Double pass 1 in; its returning light leaves upwards"),
    "aom1": ("aom", "aom", "AOM1", 152.4, Y1, 0, "IntraAction ATM-350, double pass 1"),
    "hwp2": ("hwp", HWP, "HWP2", 222.2, Y1, 0, "Double pass 1 (quarter-wave twice)"),
    "l1": ("lens", "lens_1in", "L1", 254.0, Y1, 0, "Cage telescope"),
    "l2": ("lens", "lens_1in", "L2", 273.1, Y1, 0, "Cage telescope"),
    "ir1": ("iris", "iris", "IR1", 368.3, Y1, 0, ""),
    "m2": ("mirror", PM, "M2", 400.0, Y1, 180, "Retro mirror of double pass 1"),
    "m3": ("mirror", PM, "M3", 95.2, Y2, 0, ""),
    "ir2": ("iris", "iris", "IR2", 133.3, Y2, 0, ""),
    "hwp3": ("hwp", HWP, "HWP3", 146.0, Y2, 0, ""),
    "pbs2": ("pbs", PBS, "PBS2", X_UP, Y2, 0, "Transmits to FC4/FC5, reflects to double pass 2"),
    "hwp4": ("hwp", HWP, "HWP4", 215.9, Y2, 0, ""),
    "pbs3": ("pbs", PBS, "PBS3", X_PBS3, Y2, 0, "Splits into FC5 and FC4"),
    "hwp5": ("hwp", HWP, "HWP5", 292.1, Y2, 0, ""),
    "m4": ("mirror", RED, "M4", X_M4, Y2, 0, "Red mount (drawn as M05)"),
    "m19": ("mirror", RED, "M19", X_M4, Y_FC5, 0, "Red mount (drawn as M05)"),
    "fc5": ("fiber", "fiber_cage", "FC5", X_FC, Y_FC5, 180, "A375TM-A f7.5, on the table at the right edge"),
    "hwp10": ("hwp", HWP, "HWP10", X_PBS3, 271.0, 90, ""),
    "hwp9": ("hwp", HWP, "HWP9", X_PBS3, 258.5, 90, ""),
    "m16": ("mirror", RED, "M16", X_PBS3, Y_M16, 0, "Red mount (drawn as M05)"),
    "m20": ("mirror", PM, "M20", X_M20, Y_M16, 0, ""),
    "m18": ("mirror", RED, "M18", X_M20, Y_FC4, 0, "Red mount (drawn as M05)"),
    "fc4": ("fiber", "fiber_cage", "FC4", X_FC, Y_FC4, 180, "A375-A f7.5, on the table at the right edge"),
    # double pass 2 (upper left AOM)
    "hwp11": ("hwp", HWP, "HWP11", X_UP, 254.0, 90, ""),
    "pbs4": ("pbs", PBS, "PBS4", X_UP, Y_SPLIT, 90, "Plate beam splitter (drawn as a cube); "
             "double pass 2 in, its returning light goes to PBS5"),
    "m11": ("mirror", PM, "M11", X_UP, Y_TOP, 0, ""),
    "m6": ("mirror", PM, "M6", X_DP2, Y_TOP, 0, ""),
    "aom2": ("aom", "aom", "AOM2", X_DP2, 50.8, 90, "IntraAction ATM-200, double pass 2"),
    "hwp8": ("hwp", HWP, "HWP8", X_DP2, 107.9, 90, "Double pass 2"),
    "l3": ("lens", "lens_1in", "L3", X_DP2, 139.7, 90, "Cage lens, double pass 2"),
    "dm1": ("mirror", "mirror_d", "DM1", X_DP2, Y_0TH, 0, "D-shaped mirror: picks off AOM2's 0th order"),
    "m9": ("mirror", PM, "M9", X_DP2, 279.4, 90, "Retro mirror of double pass 2"),
    "pbs5": ("pbs", PBS, "PBS5", X_PBS5, Y_SPLIT, 0, "Plate beam splitter (drawn as a cube); splits into FC2 and FC1"),
    "m12": ("mirror", RED, "M12", X_M12, Y_SPLIT, 0, "Red mount (drawn as M05)"),
    "m15": ("mirror", RED, "M15", X_M12, Y_M15, 0, "Red mount (drawn as M05)"),
    "m14": ("mirror", RED, "M14", X_FC2, Y_M15, 0, "Red mount (drawn as M05)"),
    "fc2": ("fiber", "fiber_cage", "FC2", X_FC2, Y_TOP, 270, "On the table at the top edge"),
    "m13": ("mirror", PM, "M13", X_PBS5, Y_FC1, 0, ""),
    "m7": ("mirror", RED, "M7", X_FC1, Y_FC1, 0, "Red mount (drawn as M05)"),
    "fc1": ("fiber", "fiber_cage", "FC1", X_FC1, Y_TOP, 270, "A375TM-A f7.5, on the table at the top edge"),
    # AOM2's 0th order through AOM3 to FC3
    "m8": ("mirror", PM, "M8", X_0TH, Y_0TH, 0, ""),
    "l4": ("lens", "lens_lmr1", "L4", X_0TH, 200.0, 90, "LA1131, f = 50 mm"),
    "m21": ("mirror", PM, "M21", X_0TH, Y_AOM3, 0, ""),
    "aom3": ("aom", "aom", "AOM3", 133.3, Y_AOM3, 0, "IntraAction ATM-400"),
    "m17": ("mirror", RED, "M17", X_M17, Y_AOM3, 0, "Red mount (drawn as M05)"),
    "m5": ("mirror", RED, "M5", X_M17, Y_SH, 0, "Red mount (drawn as M05)"),
    "hwp6": ("hwp", HWP, "HWP6", 304.8, Y_SH, 0, ""),
    "hwp7": ("hwp", HWP, "HWP7", 323.8, Y_SH, 0, ""),
    "sh1": ("shutter", "shutter", "SH1", 368.3, Y_SH, 0, "SR475 #5133"),
    "fc3": ("fiber", "fiber_cage", "FC3", X_FC, Y_SH, 180, "Top fiber coupler on the right edge: AOM2's 0th order"),
}
BEAMS = [
    ("in", "m10", "m1", "hwp1", "pbs1", "aom1", "hwp2", "l1", "l2", "ir1", "m2"),
    ("pbs1", "m3", "ir2", "hwp3", "pbs2", "hwp4", "pbs3", "hwp5", "m4", "m19", "fc5"),
    ("pbs3", "hwp10", "hwp9", "m16", "m20", "m18", "fc4"),
    ("pbs2", "hwp11", "pbs4", "m11", "m6", "aom2", "hwp8", "l3", "m9"),
    ("pbs4", "pbs5", "m12", "m15", "m14", "fc2"),
    ("pbs5", "m13", "m7", "fc1"),
    ("l3", "dm1", "m8", "l4", "m21", "aom3", "m17", "m5", "hwp6", "hwp7", "sh1", "fc3"),
]
LINKED = {e for chain in BEAMS for e in chain}

for eid, (kind, typ, label, x, y, angle, notes) in PARTS.items():
    sch.elements[eid] = SchElement(id=eid, kind=kind, x=round(x * 1.6 / 10) * 10, y=round(y * 1.6 / 10) * 10,
                                   label=label, part=typ, notes=notes)
    lay.components[f"c_{eid}"] = Component(id=f"c_{eid}", type=typ, x=x, y=y, label=label, sch_id=eid, notes=notes,
                                           pinned=True, angle=float(angle), auto_angle=eid in LINKED)

for chain in BEAMS:
    for a, b in zip(chain, chain[1:]):
        sch.links[f"k_{a}_{b}"] = SchLink(id=f"k_{a}_{b}", source=a, target=b, color="#7f3fbf", wavelength_nm=421.0)

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "421nm_system" / "Dy1-lowpower.json"
    lay.save(out)
    print("wrote", out)
