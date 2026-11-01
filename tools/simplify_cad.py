"""Make light meshes of the vendor STEP models for the 3D viewer.

    python tools/simplify_cad.py [--triangles 8000] [names...]

Reads each component_library/step/*.step or *.stp, puts it in the library
frame (optic centre at the origin, optic normal / beam along +x, z up, the
mount's base face below), meshes it coarsely, decimates it to about
--triangles triangles and writes component_library/mesh/<name>.ply. The
viewer only reads these small files, so it opens instantly and doesn't need
the CAD libraries. Run it again after adding a STEP file; give a new file's
pose in POSES if it isn't already in the library frame (vendor downloads
usually aren't). Needs cadquery-ocp and pyvista (pip).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pyvista as pv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from optolayout.cad3d import _load_step, tessellate  # noqa: E402

STEP_DIR = ROOT / "component_library" / "step"
OLEGO_DIR = ROOT / "component_library" / "Olego_step"  # Olego pillars (STEP, or STL when that's all there is)
MESH_DIR = ROOT / "component_library" / "mesh"

# Olego pillars: which file axis points up (from the square 4-hole flange that
# screws to the board towards the end the mount sits on). Each is put with the
# flange's bottom face at z = 0, centred on the flange, sides along x and y.
PILLAR_UP = {
    "Olego_CP33": "+y", "Olego_LMR1": "+y", "Olego_MDI_HS": "+y", "Olego_PBS_0.5in": "+y",
    "Olego_RSP05": "+y", "Olego_SR475": "+y", "Olego_polaris_0.5inch_mirror": "+y",
    "Olego_M05": "+z", "Olego_M05_0deg": "+z", "PD36A2_mount": "-z",
}

# Vendor files as downloaded -> library frame. For each: the optic centre in
# the file's coordinates, the file direction that becomes +x (where the optic
# faces / the beam goes) and the one that becomes +z (up, away from the face
# the mount stands on). Centres were measured from the bores (2026-10-11);
# files not listed are already in the library frame.
POSES = {
    # Radiant Dyes MDI-HS (1"): bore centre of the front plate, mirror flush with its face;
    # the adjuster knobs are at the back (+z in the file); it stands on its y- face
    "MDI-HS-2-3030": dict(origin=(25.44, 25.0, -15.8), x=(0, 0, -1), z=(0, 1, 0)),
    # Newport M05 (1/2"): same layout
    "Newport-M05": dict(origin=(-65.03, 16.22, -16.5), x=(0, 0, -1), z=(0, 1, 0)),
    # Thorlabs CP33 cage plate: bore along z, stands on its y- edge (tapped there)
    "CP33-Step": dict(origin=(0, 0, 0), x=(0, 0, 1), z=(0, 1, 0)),
    # Thorlabs CRM1T cage rotation mount: same as CP33; its tapped boss on the y- edge is the base
    "CRM1T-Step": dict(origin=(0, 0, 0), x=(0, 0, 1), z=(0, 1, 0)),
    # Thorlabs LMR1: bore along z, the post tab points to y-
    "LMR1-Step": dict(origin=(0, 0, -5.1), x=(0, 0, 1), z=(0, 1, 0)),
    # SRS SR475 shutter head: the 3 mm aperture runs along y, 4.8 mm from the x- end. Our lab
    # stands it vertical (long side up), aperture end down, so it can sit at 2" beam height
    "3DSR475": dict(origin=(-23.83, 2.5, -6.33), x=(0, 1, 0), z=(1, 0, 0)),
    # Thorlabs S121C power sensor head: round Ø30.5 head, SM1-threaded aperture side at y+ (y = 30.87),
    # cable leaving at x+. Library frame: aperture centre at the origin facing -x (towards the light)
    "S121C-Step": dict(origin=(0.38, 30.87, -16.08), x=(0, -1, 0), z=(0, 0, 1)),
    # Our lab's LightFlow pedestals (step/LightFlow, exported from component_library/lightflow small
    # mount - new): origin = the point under the optic on the board, x along the beam, z up.
    # Measured 2026-10-19 from the holes: see docs/LIGHTFLOW_BOARD.md.
    "LF_polarismount": dict(origin=(-27.33, -2.46, 0), x=(1, 0, 0), z=(0, 0, 1)),  # screw 8.02 behind the mirror
    "LF_RSP05": dict(origin=(-0.28, 5.62, 0), x=(1, 0, 0), z=(0, 0, 1)),  # centre screw 0.64 behind the optic
    "LF_halfinchpbsmount": dict(origin=(14.52, 8.17, 0), x=(1, 0, 0), z=(0, 0, 1)),
    "LF_cagemount": dict(origin=(9.26, 7.94, 0), x=(1, 0, 0), z=(0, 0, 1)),
    "LF_irismount": dict(origin=(-15.22, -56.6, 0), x=(1, 0, 0), z=(0, 0, 1)),  # IDA12 edge on the column face
    "LF_newport_M05": dict(origin=(0.18, 0, 8.69), x=(0, 0, 1), z=(0, 1, 0)),  # stands on its y- face
    # long side across the beam; in the lab it is used upside down (the file's top face on the board)
    "LF_SRSshutter-new": dict(origin=(7.67, 13.0, 34.92), x=(0, -1, 0), z=(0, 0, -1)),
    "LF_IntraactionAOM-ATM": dict(origin=(0, 0, 0), x=(1, 0, 0), z=(0, 0, 1)),
    # The lab's D-shaped mirror: a DMM1 holding a 1" D mirror, on its own column with a slotted foot
    # ("Left D-Shaped Mirror Mount.STEP"); the D's straight edge on the outside, the beam 5 mm in from it
    "DMM1_lab": dict(origin=(0.83, 5.0, 25.4), x=(1, 0, 0), z=(0, 0, 1)),
}

# parts drawn in several colours: [(colour, test on a triangle's centre x in the library frame)],
# first match wins (REGION_AXIS: test y or z instead)
REGION_AXIS = {"DMM1_lab": 1}
REGION_COLORS = {
    # the lab's D mirror: black DMM1 holder, its machined column and foot in aluminium
    "DMM1_lab": [((0.07, 0.07, 0.08), lambda y: y < 7.9), ((0.66, 0.68, 0.71), lambda y: True)],
    # Radiant Dyes MDI-HS, from the front: black front plate holding the mirror, steel balls,
    # red back plate carrying the knobs, brass knobs
    "MDI-HS-2-3030": [((0.07, 0.07, 0.08), lambda x: x > -8.2),
                      ((0.62, 0.64, 0.67), lambda x: x > -13.0),
                      ((0.82, 0.08, 0.10), lambda x: x >= -28.2),
                      ((0.80, 0.62, 0.20), lambda x: True)],
}


def pillar(path: Path, triangles: int) -> pv.PolyData:
    """An Olego pillar standing on the board: flange bottom at z = 0, centred."""
    if path.suffix.lower() == ".stl":
        mesh = pv.read(path).triangulate().clean()
    else:
        v, f = tessellate(_load_step(path), deflection=0.05, angle=0.12)
        mesh = pv.PolyData(v.astype(float), np.hstack([np.full((len(f), 1), 3), f]).ravel()).clean(tolerance=1e-4)
        mesh = pv.PolyData(mesh.points, mesh.faces).triangulate()
    sign, ax = PILLAR_UP[path.stem][0], "xyz".index(PILLAR_UP[path.stem][1])
    z = np.zeros(3)
    z[ax] = 1.0 if sign == "+" else -1.0
    x = np.zeros(3)
    x[(ax + 1) % 3] = 1.0
    P = np.asarray(mesh.points)
    h = P @ z
    base = P[np.abs(h - h.min()) < 0.6]  # the flange's bottom face
    centre = (base.min(axis=0) + base.max(axis=0)) / 2
    mesh = pose(mesh, dict(origin=tuple(centre), x=tuple(x), z=tuple(z)))
    mesh.points[:, 2] -= mesh.points[:, 2].min()  # flange bottom exactly on the board
    return _decimate(mesh, triangles).compute_normals(split_vertices=True, feature_angle=35)


def pillar_seat(mesh: pv.PolyData, min_area: float = 3.0) -> tuple[float, list[float]]:
    """The face a mount lands on: of the upward-facing flat faces in the top
    15 mm (the flange is lower), the one with the largest area. Small raised
    steps next to it are locating ledges, not the seat. Returns (seat z, all
    step heights)."""
    m = mesh.compute_normals(cell_normals=True, point_normals=False)
    up = m.cell_data["Normals"][:, 2] > 0.95
    z = m.cell_centers().points[:, 2]
    area = m.compute_cell_sizes()["Area"]
    top = up & (z > z.max() - 15)
    levels: dict[float, float] = {}
    for zz, aa in zip(np.round(z[top], 1), area[top]):
        levels[zz] = levels.get(zz, 0.0) + aa
    steps = sorted(k for k, v in levels.items() if v >= min_area)
    return max(levels, key=levels.get), steps


def pose(mesh: pv.PolyData, p: dict) -> pv.PolyData:
    x, z = np.array(p["x"], float), np.array(p["z"], float)
    R = np.stack([x, np.cross(z, x), z])  # rows: the new axes in file coordinates
    out = mesh.copy()
    out.points = (np.asarray(mesh.points) - np.array(p["origin"], float)) @ R.T
    return out


def _decimate(piece: pv.PolyData, target: int) -> pv.PolyData:
    if piece.n_cells > target:
        piece = piece.decimate(1 - target / piece.n_cells)  # quadric decimation keeps the outline
    return piece


def simplify(step: Path, triangles: int) -> pv.PolyData:
    shape = _load_step(step)
    v, f = tessellate(shape, deflection=0.1, angle=0.15)
    faces = np.hstack([np.full((len(f), 1), 3), f]).ravel()
    mesh = pv.PolyData(v.astype(float), faces).clean(tolerance=1e-4)
    mesh = pv.PolyData(mesh.points, mesh.faces).triangulate()  # clean turns slivers into lines: drop them
    if step.stem in POSES:
        mesh = pose(mesh, POSES[step.stem])
    colors = REGION_COLORS.get(step.stem)
    if colors is None:
        return _decimate(mesh, triangles).compute_normals(split_vertices=True, feature_angle=35)
    cx = np.asarray(mesh.cell_centers().points)[:, REGION_AXIS.get(step.stem, 0)]
    group = np.full(mesh.n_cells, -1)
    for k, (_rgb, test) in enumerate(colors):
        hit = np.array([test(x) for x in cx]) & (group < 0)
        group[hit] = k
    pieces = []
    for k, (rgb, _test) in enumerate(colors):
        ids = np.flatnonzero(group == k)
        if not len(ids):
            continue
        part = mesh.extract_cells(ids).extract_surface(algorithm="dataset_surface").triangulate()
        part = _decimate(part, max(int(triangles * len(ids) / mesh.n_cells), 60))
        part.point_data["RGB"] = np.tile((np.array(rgb) * 255).astype(np.uint8), (part.n_points, 1))
        pieces.append(part)
    return pv.merge(pieces).compute_normals(split_vertices=True, feature_angle=35)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--triangles", type=int, default=8000)
    ap.add_argument("names", nargs="*", help="only these files (names without extension)")
    a = ap.parse_args()
    MESH_DIR.mkdir(exist_ok=True)
    for step in sorted(p for p in STEP_DIR.rglob("*") if p.suffix.lower() in (".step", ".stp")):  # subfolders too (Olego/)
        if a.names and step.stem not in a.names:
            continue
        t = time.time()
        m = simplify(step, a.triangles)
        out = MESH_DIR / step.relative_to(STEP_DIR).with_suffix(".ply")  # keeps subfolders, e.g. mesh/Olego/
        out.parent.mkdir(parents=True, exist_ok=True)
        m.save(out, binary=True, texture="RGB" if "RGB" in m.point_data else None)
        lo = np.array(m.bounds).reshape(3, 2)[:, 0]
        print(f"{step.name:28s} -> {m.n_cells:5d} triangles, {out.stat().st_size / 1024:5.0f} kB, "
              f"base {-lo[2]:5.2f} mm below the optic, back at x={lo[0]:6.1f}, {time.time() - t:4.1f} s", flush=True)
    info_file = MESH_DIR / "Olego" / "pillars.json"
    info = json.loads(info_file.read_text()) if info_file.exists() else {}
    for src in sorted(OLEGO_DIR.glob("*")) if OLEGO_DIR.exists() else []:
        if src.stem not in PILLAR_UP or src.suffix.lower() not in (".step", ".stp", ".stl"):
            continue
        if a.names and src.stem not in a.names:
            continue
        m = pillar(src, 1_000_000)  # simple shapes: keep the full mesh
        out = MESH_DIR / "Olego" / (src.stem + ".ply")
        out.parent.mkdir(parents=True, exist_ok=True)
        m.save(out, binary=True)
        b = np.array(m.bounds)
        seat, steps = pillar_seat(m)
        info[src.stem] = {"height": round(b[5], 2), "seat": round(seat, 2), "flange": round(b[1] - b[0], 1),
                          "steps": [round(z, 2) for z in steps]}
        print(f"{src.name:28s} -> pillar {b[5]:5.2f} mm tall, seat at {seat:5.2f} mm (top steps "
              f"{', '.join(f'{z:.2f}' for z in steps)}), flange {b[1] - b[0]:4.1f} mm, {m.n_cells} triangles", flush=True)
    if info:
        info_file.parent.mkdir(parents=True, exist_ok=True)
        info_file.write_text(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
