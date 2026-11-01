"""Make examples/demo_schematic.json: a schematic-only starting point.

    laser -> λ/2 -> PBS -> AOM -> lens -> mirror -> fiber coupler
                     └-> beam dump (rejected port)

Open it: the Schematic tab defines the parts and beams; the Layout tab has
them placed on the table, where you only move them. Mirrors and other optics
aim themselves from the beams.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from optolayout.model import Layout, SchElement, SchLink, Table  # noqa: E402

lay = Layout(table=Table(name="Schematic demo, 24 x 18 in", width=609.6, height=457.2))
sch = lay.schematic


def el(eid, kind, x, y, label=None, part_number=""):
    sch.elements[eid] = SchElement(id=eid, kind=kind, x=x, y=y, label=label or sch.next_label(kind),
                                   part_number=part_number)


def link(a, b):
    lid = f"k_{a}_{b}"
    sch.links[lid] = SchLink(id=lid, source=a, target=b, color="#b77fd0", wavelength_nm=399.0)


el("las", "laser", 0, 0)
el("hwp", "hwp", 70, 0)
el("pbs", "pbs", 130, 0)
el("aom", "aom", 210, 0)
el("l1", "lens", 280, 0, part_number="LA1509-A")
el("m1", "mirror", 340, 0)
el("fc", "fiber", 340, -90)
el("bd", "dump", 130, 80)
for a, b in [("las", "hwp"), ("hwp", "pbs"), ("pbs", "aom"), ("aom", "l1"), ("l1", "m1"), ("m1", "fc"), ("pbs", "bd")]:
    link(a, b)

out = Path(__file__).with_name("demo_schematic.json")
lay.save(out)
print("wrote", out)
