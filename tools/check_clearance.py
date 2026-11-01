"""Clearance check for a planned layout, without Qt.

Usage: py -3.13 tools/check_clearance.py examples/make_<name>.py

The make script must define build() -> (parts, beams), with
parts = {id: (kind, type, label, x_mm, y_mm, angle, notes)} and beams = a list
of id chains, plus W and H (board size in mm). Every mount footprint is checked
against every other mount, every beam it is not on, and the board edge. Mirror
normals come from their two beam neighbours.

Footprints are the bare mounts (no Olego pillar flanges), so the app's own
overlap check (the red boxes) is stricter: a plan must pass both.
"""

import importlib.util
import math
import sys

FP = {"mirror_polaris_half": (-14.3, 5.2, -12.7, 12.7), "hwp_half": (-5.7, 5.7, -11, 11),
      "qwp_half": (-5.7, 5.7, -11, 11), "pbs_half": (-9, 9, -9, 9), "lens_1in": (-4.4, 4.4, -20.3, 20.3),
      "fiber_cage": (-62, 4.4, -20.3, 20.3), "aom": (-12.5, 12.5, -33, 33), "laser": (-200, 0, -50, 50)}


def unit(dx, dy):
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def rects_of(parts, beams):
    nb = {}
    for ch in beams:
        for i, e in enumerate(ch):
            d = nb.setdefault(e, [])
            if i > 0:
                d.append(ch[i - 1])
            if i < len(ch) - 1:
                d.append(ch[i + 1])
    rects = {}
    for e, (_kind, typ, _label, x, y, _ang, _notes) in parts.items():
        dirs = [unit(parts[n][3] - x, parts[n][4] - y) for n in nb.get(e, [])]
        if typ == "laser":
            ux = (1.0, 0.0)
        elif typ.startswith("mirror") and len(dirs) >= 2:
            a, b = dirs[0], dirs[1]  # normal = bisector of the directions to its two neighbours
            s = (a[0] + b[0], a[1] + b[1])
            ux = unit(*s) if abs(s[0]) + abs(s[1]) > 1e-6 else a
        else:
            ux = dirs[0] if dirs else (1.0, 0.0)
        rects[e] = (x, y, ux, (-ux[1], ux[0]), FP.get(typ, (-10, 10, -10, 10)))
    return rects


def corners(r):
    x, y, ux, uy, (x0, x1, y0, y1) = r
    return [(x + a * ux[0] + b * uy[0], y + a * ux[1] + b * uy[1]) for a, b in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]


def overlap(r1, r2, m=0.5):
    c1, c2 = corners(r1), corners(r2)
    for ax in (r1[2], r1[3], r2[2], r2[3]):
        p1 = [p[0] * ax[0] + p[1] * ax[1] for p in c1]
        p2 = [p[0] * ax[0] + p[1] * ax[1] for p in c2]
        if max(p1) + m <= min(p2) or max(p2) + m <= min(p1):
            return False
    return True


def seg_hits(r, p, q, m=1.0):
    x, y, ux, uy, (x0, x1, y0, y1) = r

    def loc(pt):
        dx, dy = pt[0] - x, pt[1] - y
        return dx * ux[0] + dy * ux[1], dx * uy[0] + dy * uy[1]
    (ax, ay), (bx, by) = loc(p), loc(q)
    t0, t1, dx, dy = 0.0, 1.0, bx - ax, by - ay  # Liang-Barsky clip against the grown rectangle
    for pp, qq in ((-dx, ax - (x0 - m)), (dx, (x1 + m) - ax), (-dy, ay - (y0 - m)), (dy, (y1 + m) - ay)):
        if abs(pp) < 1e-12:
            if qq < 0:
                return False
        else:
            t = qq / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def check(parts, beams, w, h):
    rects = rects_of(parts, beams)
    issues = []
    ids = list(rects)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if overlap(rects[a], rects[b]):
                issues.append(("mounts touch", a, b))
    for ch in beams:
        for a, b in zip(ch, ch[1:]):
            for e, r in rects.items():
                if e not in (a, b) and seg_hits(r, parts[a][3:5], parts[b][3:5]):
                    issues.append(("beam through", f"{a}->{b}", e))
    for e, r in rects.items():
        if e != "laser" and any(px < -0.5 or py < -0.5 or px > w + 0.5 or py > h + 0.5 for px, py in corners(r)):
            issues.append(("off the board", e))
    return issues


if __name__ == "__main__":
    spec = importlib.util.spec_from_file_location("mk", sys.argv[1])
    mk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mk)
    found = check(*mk.build(), mk.W, mk.H)
    for it in found:
        print(*it)
    print(len(found), "issues")
