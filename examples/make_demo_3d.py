"""Simplest 3D test board: a beam enters through an iris, two steering mirrors
walk it into a fiber coupler. Writes examples/demo_3d_simple.json."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from optolayout.model import Beam, Component, Layout, Table  # noqa: E402

H = lambda n: 12.7 + 25.4 * n  # hole index -> mm


def mirror_angle(prev, here, nxt):
    def unit(a, b):
        dx, dy = b[0] - a[0], -(b[1] - a[1])
        n = math.hypot(dx, dy)
        return dx / n, dy / n
    i, o = unit(prev, here), unit(here, nxt)
    return math.degrees(math.atan2(o[1] - i[1], o[0] - i[0])) % 360


lay = Layout(table=Table(name='10" x 8" breadboard', width=254.0, height=203.2))
for cid, t, hx, hy, label, ang in [("iris", "iris", 1, 5, "Iris", 0), ("m1", "mirror_1in", 5, 5, "M1", 0),
                                   ("m2", "mirror_1in", 5, 2, "M2", 0), ("fc", "fiber", 8, 2, "Fiber", 180)]:
    lay.components[cid] = Component(id=cid, type=t, x=H(hx), y=H(hy), angle=ang, label=label)
c = lay.components
pos = {k: (v.x, v.y) for k, v in c.items()}
c["m1"].angle = mirror_angle(pos["iris"], pos["m1"], pos["m2"])
c["m2"].angle = mirror_angle(pos["m1"], pos["m2"], pos["fc"])
for a, b in [("iris", "m1"), ("m1", "m2"), ("m2", "fc")]:
    lay.beams[f"b_{a}_{b}"] = Beam(id=f"b_{a}_{b}", source=a, target=b, wavelength_nm=399.0)
out = Path(__file__).with_name("demo_3d_simple.json")
lay.save(out)
print("wrote", out)
