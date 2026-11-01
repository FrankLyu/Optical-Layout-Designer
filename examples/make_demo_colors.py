"""Make examples/demo_colors.json: a board that mixes wavelengths, to check
that each beam colour reads clearly over the hole pattern and that the
wavelength legend appears. One straight row per wavelength:

    421 nm  laser -> half-wave plate -> PBS -> fiber
    530 nm  laser -> lens -> fiber
    626 nm  laser -> half-wave plate -> photodiode
    741 nm  laser -> iris -> fiber
    1064 nm laser -> lens -> beam dump
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from optolayout.model import WAVELENGTH_COLORS, Layout, SchElement, SchLink, Table  # noqa: E402

lay = Layout(table=Table(name="Wavelength test, 36 x 24 in", width=914.4, height=609.6))
sch = lay.schematic


def el(eid, kind, x, y, label=None):
    sch.elements[eid] = SchElement(id=eid, kind=kind, x=x, y=y, label=label or sch.next_label(kind))


def chain(name, *ids):
    wl, color = WAVELENGTH_COLORS[name]
    for a, b in zip(ids, ids[1:]):
        lid = f"k_{a}_{b}"
        sch.links[lid] = SchLink(id=lid, source=a, target=b, color=color, wavelength_nm=wl)


rows = [("421 nm", ["hwp", "pbs"], "fiber"), ("530 nm", ["lens"], "fiber"), ("626 nm", ["hwp"], "photodiode"),
        ("741 nm", ["iris"], "fiber"), ("1064 nm", ["lens"], "dump")]
for r, (name, mids, end) in enumerate(rows):
    y = r * 125
    ids = [f"las{r}"]
    el(ids[0], "laser", 200 * (r % 2), y, name)  # staggered: the laser boxes are taller than the row pitch
    for i, kind in enumerate(mids):
        ids.append(f"{kind}{r}")
        el(ids[-1], kind, 360 + 100 * i, y)
    ids.append(f"end{r}")
    el(ids[-1], end, 580, y)
    chain(name, *ids)

out = Path(__file__).with_name("demo_colors.json")
lay.save(out)
print("wrote", out)
