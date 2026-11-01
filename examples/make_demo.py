"""Build examples/demo_399nm.json: a small 399 nm distribution board drawn
in the style of Xingjian Lyu's reference (Radiant Dyes mirrors, AOM double passes,
fiber launchers along the top)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from optolayout.model import Beam, Component, Layout, Table  # noqa: E402

H = lambda n: 12.7 + 25.4 * n  # hole index -> mm
BEAM = "#b77fd0"


def mirror_angle(prev, here, nxt):
    """Mirror normal (deg, CCW on screen) that bisects the in/out beams."""
    def unit(a, b):
        dx, dy = b[0] - a[0], -(b[1] - a[1])  # flip y: screen is y-down
        n = math.hypot(dx, dy)
        return dx / n, dy / n
    i, o = unit(prev, here), unit(here, nxt)
    return math.degrees(math.atan2(o[1] - i[1], o[0] - i[0])) % 360


lay = Layout(table=Table(name='36" x 24" breadboard', width=914.4, height=609.6))
# id: (type, hole x, hole y, label, angle or None for mirrors)
P = {
    "laser": ("laser", 7, 3, "399 nm, -260 MHz", 0),
    "m1": ("mirror_rd_1in", 10, 3, "", None),
    "m2": ("mirror_rd_1in", 10, 9, "", None),
    "hwp1": ("hwp", 13.75, 9, "", 0),
    "pbs1": ("pbs_mounted", 15, 9, "", 0),
    "hwp0": ("hwp", 16.25, 9, "", 180),
    # 3D MOT branch (up)
    "m3": ("mirror_rd_half_in", 15, 6, "", None),
    "m4": ("mirror_rd_half_in", 17, 6, "", None),
    "fib_3d": ("fiber", 17, 3, "3D MOT, -40 MHz", 270),
    # double-pass AOM (down)
    "aom1": ("aom", 15, 13, "+80 MHz", 90),
    "l1": ("lens_1in", 15, 16, "", 90),
    "qwp1": ("qwp", 15, 18, "", 90),
    "retro1": ("mirror_rd_1in", 15, 21, "", 90),
    # probe branch
    "pbs2": ("pbs", 21, 9, "", 0),
    "hwp2": ("hwp_half", 21, 6, "", 90),
    "fib_2d": ("fiber", 21, 3, "2D MOT, -40 MHz", 270),
    "m5": ("mirror_1in", 27, 9, "", None),
    "aom2": ("aom", 27, 13, "+20 MHz", 90),
    "ir1": ("iris", 27, 15.5, "", 90),
    "l2": ("lens_half_in", 27, 17.5, "", 90),
    "fib_probe": ("fiber", 27, 20, "Probe, 0 MHz", 90),
    "dump1": ("dump", 30, 13, "", 0),
}
for cid, (t, hx, hy, label, ang) in P.items():
    lay.components[cid] = Component(id=cid, type=t, x=H(hx), y=H(hy), angle=ang or 0.0, label=label)
pos = {k: (c.x, c.y) for k, c in lay.components.items()}


def path(*ids, color=BEAM):
    for a, b in zip(ids, ids[1:]):
        bid = f"b_{a}_{b}"
        lay.beams[bid] = Beam(id=bid, source=a, target=b, color=color, wavelength_nm=399.0)


path("laser", "m1", "m2", "hwp1", "pbs1", "hwp0", "pbs2", "m5", "aom2", "ir1", "l2", "fib_probe")
path("pbs1", "m3", "m4", "fib_3d")
path("pbs1", "aom1", "l1", "qwp1", "retro1")
path("pbs2", "hwp2", "fib_2d")
lay.beams["b_aom2_dump1"] = Beam(id="b_aom2_dump1", source="aom2", target="dump1", color="#dcc3e8",
                                 wavelength_nm=399.0, label="0th order")

c = lay.components
for m, (a, b) in {"m1": ("laser", "m2"), "m2": ("m1", "hwp1"), "m3": ("pbs1", "m4"),
                  "m4": ("m3", "fib_3d"), "m5": ("pbs2", "aom2")}.items():
    c[m].angle = mirror_angle(pos[a], pos[m], pos[b])

# power measurement points (stable ids; the logbook refers to these)
from optolayout.model import MeasurementPoint  # noqa: E402
for pid, label, beam in [("mp_laser", "P1", "b_m2_hwp1"), ("mp_3d", "P2", "b_m4_fib_3d"),
                         ("mp_dp", "P3", "b_aom1_l1"), ("mp_2d", "P4", "b_hwp2_fib_2d"),
                         ("mp_probe", "P5", "b_l2_fib_probe")]:
    lay.points[pid] = MeasurementPoint(id=pid, label=label, beam_id=beam)

out = Path(__file__).with_name("demo_399nm.json")
lay.save(out)
print("wrote", out)

# sample logbook: a few readings and a synthetic beam-profile picture
if "--with-log" in sys.argv:
    import random

    from optolayout.logbook import Logbook, logbook_path_for
    lb_path = logbook_path_for(out)
    lb_path.unlink(missing_ok=True)
    lb = Logbook(lb_path)
    random.seed(1)
    base = {"mp_laser": 42.0, "mp_3d": 12.5, "mp_dp": 25.4, "mp_2d": 8.1, "mp_probe": 0.85}
    days = ["2026-10-01T10:00:00", "2026-10-03T09:30:00", "2026-10-03T11:15:00", "2026-10-09T17:40:00"]
    notes = ["Initial alignment", "Before cleaning", "After cleaning", "Routine check"]
    factor = [1.0, 0.91, 1.05, 1.02]
    for pid, p0 in base.items():
        lb.register_point(pid, lay.points[pid].label)
        for d, n, f in zip(days, notes, factor):
            lb.add_power(pid, round(p0 * f * random.uniform(0.98, 1.02), 3), measured_at=d,
                         wavelength_nm=399.0, instrument="Thorlabs S120C", notes=n)
    try:
        import math as _m

        from PySide6.QtGui import QGuiApplication, QImage, qRgb
        from PySide6.QtCore import QBuffer, QIODevice
        _app = QGuiApplication.instance() or QGuiApplication([])
        img = QImage(320, 240, QImage.Format_RGB32)
        for yy in range(240):
            for xx in range(320):
                v = int(255 * _m.exp(-(((xx - 165) / 38) ** 2 + ((yy - 118) / 30) ** 2)))
                img.setPixel(xx, yy, qRgb(v, v, v))
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        lb.add_picture("mp_3d", bytes(buf.data()), "fiber_input_profile.png", taken_at="2026-10-03T11:20:00",
                       notes="Beam profile before 3D MOT fiber, after cleaning")
    except ImportError:
        pass
    lb.close()
    print("wrote", lb_path)
