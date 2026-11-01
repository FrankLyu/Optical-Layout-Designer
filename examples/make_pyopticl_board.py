"""Make examples/pyopticl_board.json: a small PyOpticL-style ion-trap baseplate.

An 8 x 6 in plate in the style of PyOpticL's half-inch modules (UMass ion-trap
group, Designs/modules/singlepass.py): fiber in -> HWP -> PBS -> AOM -> two
mirrors -> iris -> HWP -> fiber out, the PBS's reflection into a dump. All
parts are the half-inch ones PyOpticL uses (Polaris K05S1, RSP05 on a surface
adapter, a 1/2" cube on its adapter, IDA12, PAF2 on HCA3), the beam 1/2" above
the plate.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from optolayout.model import Component, Layout, SchElement, SchLink, Table  # noqa: E402

IN = 25.4
lay = Layout(table=Table(name="PyOpticL single pass (example)", width=8 * IN, height=6 * IN))
lay.table.apply_style("pyopticl")
sch = lay.schematic

R1, R2 = 2 * IN, 4.5 * IN  # the two beam rows
# id: (kind, layout type, label, x, y, notes)
PARTS = {
    "fc1": ("fiber", "fiber", "FC1", 1.0 * IN, R1, "Fiber in"),
    "hwp1": ("hwp", "hwp_half", "HWP1", 2.0 * IN, R1, ""),
    "pbs1": ("pbs", "pbs_half", "PBS1", 3.5 * IN, R1, ""),
    "aom": ("aom", "aom", "AOM1", 5.0 * IN, R1, ""),
    "m1": ("mirror", "mirror_polaris_half", "M1", 7.25 * IN, R1, ""),
    "m2": ("mirror", "mirror_polaris_half", "M2", 7.25 * IN, R2, ""),
    "ir1": ("iris", "iris", "IR1", 6.0 * IN, R2, ""),
    "hwp2": ("hwp", "hwp_half", "HWP2", 3.0 * IN, R2, ""),
    "fc2": ("fiber", "fiber", "FC2", 1.0 * IN, R2, "Fiber out"),
    "bd1": ("dump", "dump", "BD1", 3.5 * IN, 0.5 * IN, "PBS1 reflection"),
}
BEAMS = [("fc1", "hwp1", "pbs1", "aom", "m1", "m2", "ir1", "hwp2", "fc2"), ("pbs1", "bd1")]

for eid, (kind, typ, label, x, y, notes) in PARTS.items():
    sch.elements[eid] = SchElement(id=eid, kind=kind, x=round(x * 1.6 / 10) * 10, y=round(y * 1.6 / 10) * 10,
                                   label=label, part=typ, notes=notes)
    lay.components[f"c_{eid}"] = Component(id=f"c_{eid}", type=typ, x=x, y=y, label=label, sch_id=eid,
                                           pinned=True, auto_angle=True)
for chain in BEAMS:
    for a, b in zip(chain, chain[1:]):
        sch.links[f"k_{a}_{b}"] = SchLink(id=f"k_{a}_{b}", source=a, target=b, color="#7f3fbf", wavelength_nm=422.0)

if __name__ == "__main__":
    out = Path(__file__).with_name("pyopticl_board.json")
    lay.save(out)
    print("wrote", out)
