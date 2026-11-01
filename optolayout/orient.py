"""Automatic orientation of optics from the beams that touch them.

Used for both layers. Angles follow the model's convention: degrees, CCW as
seen on screen (y down), 0 = optic normal along +x.

- Mirrors: the normal bisects the directions to the incoming and outgoing
  neighbours, so the beam really reflects from one to the other.
- Inline optics (lens, waveplate, AOM, iris): the normal points along the
  beam, in the direction the light travels.
- End points (fiber coupler, photodiode, beam dump, laser): face their
  only neighbour.
- Cubes (PBS, BS): faces square to the incoming beam, with the diagonal
  turned so it sends light toward the reflected neighbour.
"""

from __future__ import annotations

import math

MIRRORS = {"mirror"}
INLINE = {"lens", "hwp", "qwp", "aom", "iris", "shutter"}
ENDS = {"fiber", "photodiode", "dump", "laser"}
CUBES = {"pbs", "bs"}

# layout types whose drawn diagonal is "\" in the local frame (reflects +x travel to +y on screen)
BACKSLASH_CUBES = {"pbs_mounted"}


def _ang(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(-dy, dx)) % 360


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-9 else None


def auto_angle(kind: str, xy: tuple[float, float], ins: list[tuple[float, float]],
               outs: list[tuple[float, float]], layout_type: str = "") -> float | None:
    """Angle for an element at xy with light arriving from `ins` and leaving
    toward `outs` (neighbour positions). None = no opinion (leave as is)."""
    x, y = xy
    nbrs = ins + outs
    if not nbrs:
        return None
    if kind in MIRRORS:
        us = [u for u in (_unit(px - x, py - y) for px, py in nbrs[:2]) if u]
        if len(us) == 1:
            return _ang(*us[0])
        if len(us) == 2:
            n = _unit(us[0][0] + us[1][0], us[0][1] + us[1][1])
            if n is None:  # straight back: face the first neighbour
                return _ang(*us[0])
            return _ang(*n)
        return None
    if kind in ENDS:
        u = _unit(nbrs[0][0] - x, nbrs[0][1] - y)
        return _ang(*u) if u else None
    if kind in INLINE:
        if ins and outs:
            u = _unit(outs[0][0] - ins[0][0], outs[0][1] - ins[0][1])
        elif outs:
            u = _unit(outs[0][0] - x, outs[0][1] - y)
        else:
            u = _unit(x - ins[0][0], y - ins[0][1])
        return _ang(*u) if u else None
    if kind in CUBES:
        if not ins:
            u = _unit(outs[0][0] - x, outs[0][1] - y)
            return _ang(*u) if u else None
        u = _unit(x - ins[0][0], y - ins[0][1])  # travel direction of the incoming beam
        if u is None:
            return None
        theta = _ang(*u)
        # the output that is not straight through is the reflected one
        refl = None
        for px, py in outs:
            v = _unit(px - x, py - y)
            if v and abs(u[0] * v[0] + u[1] * v[1]) < 0.7:
                refl = v
        if refl is None:
            return theta
        # cross > 0 (screen coords) means the reflection turns clockwise on screen, i.e. +90° CCW? compute explicitly
        phi = _ang(*refl)
        turn = (phi - theta) % 360  # 90 = reflected CCW on screen, 270 = CW
        slash_ccw = layout_type not in BACKSLASH_CUBES  # "/" sends +x travel to +90°
        if (turn < 180) == slash_ccw:
            return theta
        return (theta + 90) % 360
    return None
