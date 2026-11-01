"""Make 626nm_system/AOM5-FC8.json: a planned 16 x 32 in Olego board with five
AOM double passes and eight fiber couplers (plan, 2026-10-28).

This is a plan, not a photo of a real board. Jiahao's choices: Olego board,
626 nm, laser head (20 x 10 cm) in the top-left corner with the beam along the
long edge, fibers wherever they fit, the same AOM model for all five (+1 order
double pass, cat's eye f = 150 mm), some AOMs feed two fibers through a PBS,
HWP + PBS before every AOM, a QWP + HWP pair before every fiber for PM
alignment, no isolator / shutters / pick-offs, Polaris 1/2" mounts.
Fiber rules (Jiahao): every fiber gets two steering mirrors MA -> MB at least
100 mm apart, and 100-300 mm from MB to the coupler.

Beam path:
  Laser -> M1, which turns it down a vertical "bus" (x = X_BUS).
  Each bus tap is HWPB + PBSB reflecting left (the last one is the mirror
  MBUS: it takes what is left) -> HWPD -> PBSD -> AOM -> LD (f = 150 mm) ->
  QWPD -> retro mirror MR. The returning light leaves PBSD downwards -> MOUT
  -> right along its output lane, crossing the bus between two taps.
  Fibers 1-5 (one per AOM): MA turns the lane up, MB turns it right ->
  QWPF + HWPF -> coupler on the right edge.
  Second fibers (FC6-FC8): HWPS + PBSS on an output lane, then one of
    "bottom": MA turns the reflected beam right, MB turns it down to a
              coupler on the bottom edge;
    "top":    fold mirror F turns it left, MA turns it up, MB turns it left
              to a coupler in the free strip right of the laser.
  Where beams cross, no part sits at the crossing.
The fiber positions in SPLITS / COL / SLOT were found by a clearance search
(every mount footprint against every beam and every other mount).
In the schematic a double pass is drawn one way only: the chain ends at the
retro mirror and the returning light starts again at PBSD.

Positions snap to the Olego 1/4" half-grid (Q = 6.35 mm). The laser box in
the app is 16 x 12 cm; the real head is 20 x 10 cm, back to x = 3 mm.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from optolayout.model import Component, Layout, SchElement, SchLink, Table, WAVELENGTH_COLORS  # noqa: E402

IN = 25.4
Q = IN / 4  # Olego half-grid
W, H = 32 * IN, 16 * IN
NM = 626.0

PM, HWP, QWP, PBS, LENS, FC = "mirror_polaris_half", "hwp_half", "qwp_half", "pbs_half", "lens_1in", "fiber_cage"
# everything below is in half-grid steps from the board's top-left corner (x right, y down)
Y_LASER, X_LASER = 8, 32  # laser output
X_BUS = 71  # vertical distribution bus
X_PBSD, X_HWPD = 64, 67  # double-pass PBS and its HWP, left of the bus
Y_DP = [20 + 9 * k for k in range(5)]  # double-pass rows, 57 mm apart
DY_OUT = 4  # a double pass's output lane sits this far below its row
DY_TAP = 3  # bus HWP above its tap
X_AOM = (59, 51)  # staggered AOM columns
F_LENS = 24  # 152.4 mm, the f = 150 mm cat's eye
X_FC = 118  # right-edge couplers
Y_FC_BOTTOM = 54  # bottom-edge couplers (beam coming down)

# fibers 1-5: MA/MB column and coupler row; QWPF/HWPF x on the right-edge rows
COL = [95, 100, 91, 76, 97]
SLOT = [4, 11, 18, 28, 43]
X_WP = (111, 116)
# second fibers: lane (AOM) -> dict; see build()
SPLITS = {
    1: dict(kind="top", hx=79, px=86, yr=20, xm=82, ytop=4, xfc=43),
    2: dict(kind="bottom", hx=78, px=81, yr=37, xb=113, wy=(46, 51)),
    3: dict(kind="bottom", hx=80, px=85, yr=30, xb=105, wy=(40, 51)),
}


def build(col=COL, slot=SLOT, splits=SPLITS, x_wp=X_WP):
    """Parts {id: (kind, type, label, x, y, angle, notes)} in mm, and beam chains."""
    parts, beams = {}, []

    def part(eid, kind, typ, label, x, y, angle=0, notes=""):
        parts[eid] = (kind, typ, label, x * Q, y * Q, angle, notes)
        return eid

    def mirror(eid, label, x, y, notes=""):
        return part(eid, "mirror", PM, label, x, y, 0, notes)

    def waveplates(n, p1, p2):
        return [part(f"qwpf{n}", "qwp", QWP, f"QWPF{n}", *p1, 0, f"PM alignment into FC{n}"),
                part(f"hwpf{n}", "hwp", HWP, f"HWPF{n}", *p2, 0, f"PM alignment into FC{n}")]

    part("laser", "laser", "laser", "626 nm laser", X_LASER, Y_LASER, 0, "Laser head 20 x 10 cm (drawn 16 x 12)")
    bus = ["laser", mirror("m1", "M1", X_BUS, Y_LASER, "Turns the laser down the bus")]
    n_fc = 5
    for k, y in enumerate(Y_DP, start=1):
        xa = X_AOM[(k - 1) % 2]
        if k == len(Y_DP):
            bus.append(mirror("mbus", "MBUS", X_BUS, y, "End of the bus: takes what is left into DP5"))
        else:
            bus += [part(f"hwpb{k}", "hwp", HWP, f"HWPB{k}", X_BUS, y - DY_TAP, 90, f"Sets the DP{k} tap"),
                    part(f"pbsb{k}", "pbs", PBS, f"PBSB{k}", X_BUS, y, 0, f"Tap to double pass {k}")]
        beams.append([bus[-1],
                      part(f"hwpd{k}", "hwp", HWP, f"HWPD{k}", X_HWPD, y, 0, f"Sets the power into AOM{k}"),
                      part(f"pbsd{k}", "pbs", PBS, f"PBSD{k}", X_PBSD, y, 0, f"Double pass {k}: in; return leaves downwards"),
                      part(f"aom{k}", "aom", "aom", f"AOM{k}", xa, y, 0, f"Double pass {k}, +1 order (model TBD)"),
                      part(f"ld{k}", "lens", LENS, f"LD{k}", xa - F_LENS, y, 0, "Cat's eye lens, f = 150 mm"),
                      part(f"qwpd{k}", "qwp", QWP, f"QWPD{k}", xa - 2 * F_LENS + 5, y, 0, f"Double pass {k}"),
                      mirror(f"mr{k}", f"MR{k}", xa - 2 * F_LENS, y, f"Retro mirror of double pass {k}")])
        lane = y + DY_OUT
        out = [f"pbsd{k}", mirror(f"mout{k}", f"MOUT{k}", X_PBSD, lane, "Crosses the bus to the right")]
        sp = splits.get(k)
        if sp:
            n_fc += 1
            n = n_fc
            out += [part(f"hwps{k}", "hwp", HWP, f"HWPS{k}", sp["hx"], lane, 0, f"Sets the AOM{k} fiber split"),
                    part(f"pbss{k}", "pbs", PBS, f"PBSS{k}", sp["px"], lane, 0, f"Splits AOM{k} into FC{k} and FC{n}")]
            px, yr = sp["px"], sp["yr"]
            if sp["kind"] == "bottom":
                xb = sp["xb"]
                beams.append([f"pbss{k}", mirror(f"ma{n}", f"MA{n}", px, yr, f"FC{n} walk, 1st mirror"),
                              mirror(f"mb{n}", f"MB{n}", xb, yr, f"FC{n} walk, 2nd mirror")]
                             + waveplates(n, (xb, sp["wy"][0]), (xb, sp["wy"][1]))
                             + [part(f"fc{n}", "fiber", FC, f"FC{n}", xb, Y_FC_BOTTOM, 90,
                                     f"From AOM{k} (PBSS{k}), bottom edge")])
            else:  # top: fold left, up, left into a coupler right of the laser
                xm, yt, xf = sp["xm"], sp["ytop"], sp["xfc"]
                beams.append([f"pbss{k}", mirror(f"f{n}", f"F{n}", px, yr, f"Fold: sends AOM{k}'s second beam left"),
                              mirror(f"ma{n}", f"MA{n}", xm, yr, f"FC{n} walk, 1st mirror"),
                              mirror(f"mb{n}", f"MB{n}", xm, yt, f"FC{n} walk, 2nd mirror")]
                             + waveplates(n, (xf + 10, yt), (xf + 6, yt))
                             + [part(f"fc{n}", "fiber", FC, f"FC{n}", xf, yt, 0, f"From AOM{k} (PBSS{k}), right of the laser")])
        c, s = col[k - 1], slot[k - 1]
        out += [mirror(f"ma{k}", f"MA{k}", c, lane, f"FC{k} walk, 1st mirror"),
                mirror(f"mb{k}", f"MB{k}", c, s, f"FC{k} walk, 2nd mirror")]
        out += waveplates(k, (x_wp[0], s), (x_wp[1], s))
        beams.append(out + [part(f"fc{k}", "fiber", FC, f"FC{k}", X_FC, s, 180, f"From AOM{k}, right edge")])
    beams.append(bus)
    return parts, beams


def make_layout(parts, beams):
    lay = Layout(table=Table(name="AOM5-FC8", width=W, height=H))
    lay.table.apply_style("olego")
    sch = lay.schematic
    linked = {e for chain in beams for e in chain}
    color = WAVELENGTH_COLORS["626 nm"][1]
    for eid, (kind, typ, label, x, y, angle, notes) in parts.items():
        sch.elements[eid] = SchElement(id=eid, kind=kind, x=round(x * 1.6 / 10) * 10, y=round(y * 1.6 / 10) * 10,
                                       label=label, part=typ, notes=notes)
        lay.components[f"c_{eid}"] = Component(id=f"c_{eid}", type=typ, x=round(x, 2), y=round(y, 2), label=label,
                                               sch_id=eid, notes=notes, pinned=True, angle=float(angle),
                                               auto_angle=eid in linked)
    for chain in beams:
        for a, b in zip(chain, chain[1:]):
            sch.links[f"k_{a}_{b}"] = SchLink(id=f"k_{a}_{b}", source=a, target=b, color=color, wavelength_nm=NM)
    return lay


if __name__ == "__main__":
    parts, beams = build()
    out = Path(__file__).resolve().parents[1] / "626nm_system" / "AOM5-FC8.json"
    make_layout(parts, beams).save(out)
    print("wrote", out, len(parts), "parts")
