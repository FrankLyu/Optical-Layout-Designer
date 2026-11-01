"""Make examples/lightflow_board.json: a small LightFlow-style optical circuit board.

A single pass (fiber in -> HWP -> PBS -> AOM -> mirror -> D-shaped mirror ->
shutter -> iris -> cage telescope -> HWP -> fiber out, the PBS's reflection
into a dump) on a 10 x 7 in, 1/2" thick board in the LightFlow convention used by the
QITI group / Open Quantum Design (github.com/OpenQuantumDesign/oqd-OCB): every
optic 1" above the board, each mount on a machined pedestal held by tapped 8-32
holes and M2 dowel pins.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from optolayout.model import Component, Layout, SchElement, SchLink, Table  # noqa: E402

IN = 25.4
lay = Layout(table=Table(name="LightFlow single pass (example)", width=10 * IN, height=7 * IN))
lay.table.apply_style("lightflow")
sch = lay.schematic

R1, R2 = 2.25 * IN, 5.0 * IN  # the two beam rows
# id: (kind, layout type, label, x, y, notes)
PARTS = {
    # fiber couplers on the 30 mm cage (asphere in a CP33, rods back to the FC/APC plate), as on the Olego board
    "fc1": ("fiber", "fiber_cage", "FC1", 3.0 * IN, R1, "Fiber in"),
    "hwp1": ("hwp", "hwp_half", "HWP1", 4.0 * IN, R1, ""),
    "pbs1": ("pbs", "pbs_half", "PBS1", 5.0 * IN, R1, ""),
    "aom": ("aom", "aom", "AOM1", 6.75 * IN, R1, "Intraaction, on the lab's ATM plate"),
    "m1": ("mirror", "mirror_polaris_half", "M1", 9.25 * IN, R1, ""),
    "dm1": ("mirror", "mirror_d", "DM1", 9.25 * IN, R2, "D-shaped mirror in a DMM1 on the lab's column"),
    "sh1": ("shutter", "shutter", "SH1", 7.9 * IN, R2, "SRS SR475 on the lab's holder"),
    "ir1": ("iris", "iris", "IR1", 7.1 * IN, R2, ""),
    # cage telescope: two CP33 lens plates on the lab's cage mounts
    "l1": ("lens", "lens_1in", "L1", 6.5 * IN, R2, "Telescope, f = 75 mm"),
    "l2": ("lens", "lens_1in", "L2", 4.85 * IN, R2, "Telescope, f = -30 mm (spacing 42 mm)"),
    "hwp2": ("hwp", "hwp_half", "HWP2", 3.9 * IN, R2, ""),
    "fc2": ("fiber", "fiber_cage", "FC2", 3.0 * IN, R2, "Fiber out"),
    "bd1": ("dump", "dump", "BD1", 5.0 * IN, 0.5 * IN, "PBS1 reflection"),
}
BEAMS = [("fc1", "hwp1", "pbs1", "aom", "m1", "dm1", "sh1", "ir1", "l1", "l2", "hwp2", "fc2"), ("pbs1", "bd1")]

for eid, (kind, typ, label, x, y, notes) in PARTS.items():
    sch.elements[eid] = SchElement(id=eid, kind=kind, x=round(x * 1.6 / 10) * 10, y=round(y * 1.6 / 10) * 10,
                                   label=label, part=typ, notes=notes)
    lay.components[f"c_{eid}"] = Component(id=f"c_{eid}", type=typ, x=x, y=y, label=label, sch_id=eid,
                                           pinned=True, auto_angle=True)
for chain in BEAMS:
    for a, b in zip(chain, chain[1:]):
        sch.links[f"k_{a}_{b}"] = SchLink(id=f"k_{a}_{b}", source=a, target=b, color="#7f3fbf", wavelength_nm=422.0)

if __name__ == "__main__":
    out = Path(__file__).with_name("lightflow_board.json")
    lay.save(out)
    print("wrote", out)
