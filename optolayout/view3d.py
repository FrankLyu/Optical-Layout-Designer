"""Light 3D view of the board: real-time, built from the 2D layout.

Vendor mounts use the simplified meshes in component_library/mesh (made by
tools/simplify_cad.py); everything else is drawn from simple shapes that
follow the 2D drawings' colours. Each part stands on a post that puts its
optic at the beam height. Needs pyvista (and pyvistaqt for the tab).

Frames: the layout is mm with y down; 3D has x right, y = -y(layout), z up.
Every part's own frame has the optic at the origin and the beam along +x
(as the STEP files and 2D symbols do).
"""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

import numpy as np
import pyvista as pv

from .model import Layout
from .mounts3d import (LIGHTFLOW_BODY, LIGHTFLOW_ELEMENTS, BLOCK_COLOR, BOARD_BEAM_HEIGHT, DEFAULT_BEAM_HEIGHT, DRILLED_STYLES, MODELS, OLEGO_PILLARS,
                       PLATE_T, PYOPTICL_POCKET_PAD, TABLE_SCREW, footprint, mount_block, mount_boxes, mount_roll, optic_height, pillar_info,
                       pillar_xy, sunk_depth, table_screw_holes)
from .symbols import SYMBOLS

MESH_DIR = Path(__file__).resolve().parents[1] / "component_library" / "mesh"
BOARD_T = 12.7  # board thickness (mm)


def board_thickness(t) -> float:
    return PLATE_T.get(t.style, BOARD_T)


def board_beam_height(t) -> float | None:
    """The beam height a board type sets (its mounts decide it), else None (posts: your choice)."""
    return BOARD_BEAM_HEIGHT.get(t.style)

# colours (matching the 2D drawings)
ANODIZED, ALU, BOARD, HOLE = "#262626", "#c9ccd1", "#d3d6db", "#4a4d52"
RD_RED, RD_YELLOW, MIRROR, GLASS = "#d81e26", "#e8c21a", "#d9e6ee", "#9fd3ea"

_mesh_cache: dict[str, pv.PolyData] = {}
MISSING_MESHES: set[str] = set()  # models asked for but not installed: drawn as simple shapes
PILLAR = "#5b6670"  # printed / anodized Olego pillars
VENDOR_COLORS = {"3DSR475": "#3a3a3a"}  # single-colour vendor parts that aren't black anodized


def _vendor(step_name: str) -> pv.PolyData | None:
    stem = Path(step_name).stem
    if stem not in _mesh_cache:
        f = MESH_DIR / f"{stem}.ply"
        _mesh_cache[stem] = pv.read(f) if f.exists() else None
    m = _mesh_cache[stem]
    if m is None:
        MISSING_MESHES.add(stem)
    return m.copy() if m is not None else None


def _box(x0, x1, y0, y1, z0, z1) -> pv.PolyData:
    return pv.Box(bounds=(min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), min(z0, z1), max(z0, z1)))


def _cyl(r, x0, x1, axis=(1, 0, 0), center=(0, 0, 0), res=32) -> pv.PolyData:
    """Cylinder of radius r along `axis` from x0 to x1 (measured along the axis from `center`)."""
    a = np.array(axis, float)
    c = np.array(center, float) + a * (x0 + x1) / 2
    return pv.Cylinder(center=c, direction=a, radius=r, height=abs(x1 - x0), resolution=res)


# ---- simple models: list of (mesh, colour, options) in the part's own frame ----------

def _rd_mirror(s: float = 1.0):
    out = [(_box(-24 * s, -8.5 * s, -31 * s, 31 * s, -24 * s, 24 * s), RD_RED, {}),
           (_box(-8.5 * s, -1.2 * s, -28 * s, 28 * s, -22 * s, 22 * s), ANODIZED, {})]
    for y, z in ((20, 14), (-20, 14), (20, -14)):
        out.append((_cyl(4.5 * s, -36 * s, -24 * s, center=(0, y * s, z * s)), RD_YELLOW, {}))
    out.append((_cyl(12.7 * s, -1.2 * s, 0, res=48), MIRROR, {"specular": 1.0}))
    return out


def _mirror_mount(r, base):
    """A kinematic mount: a plate down to its base, two knobs behind, the mirror in front."""
    out = [(_box(-12, -1, -base, base, -base, base), ANODIZED, {}), (_cyl(r, -1, 0, res=48), MIRROR, {"specular": 1.0})]
    for y in (-base * 0.6, base * 0.6):
        out.append((_cyl(2.5, -22, -12, center=(0, y, base * 0.6), res=16), ALU, {}))
    return out


def _rotation_mount(r, plate, base):
    return [(_cyl(base, 0, 8), ANODIZED, {}), (_cyl(r, -1, 0, res=48), plate, {"opacity": 0.85})]


def _fiber_port():
    return [(_box(-12, 12, -19, 19, -27, 14), ANODIZED, {}), (_cyl(4, -20, -12, res=24), ALU, {})]


def _newport_m05():
    out = [(_box(-12.5, -1, -11, 11, -11, 11), ANODIZED, {}), (_cyl(6.35, -1, 0), MIRROR, {"specular": 1.0})]
    for y, z in ((6, 6), (-6, 6)):
        out.append((_cyl(2.0, -20, -12.5, center=(0, y, z)), ALU, {}))
    return out


def _lens_cp33():
    return [(_box(-6.35, 6.35, -20.3, 20.3, -20.3, 20.3), ANODIZED, {}),
            (_cyl(12.7, -3, 3), GLASS, {"opacity": 0.6})] + [
        (_cyl(3.0, -6.4, 6.4, center=(0, y, z), res=16), ALU, {}) for y in (-15, 15) for z in (-15, 15)]


def _lens_ring(r):
    return [(_cyl(r + 6.5, -4, 4), ANODIZED, {}), (_cyl(r - 0.5, -4.2, 4.2), GLASS, {"opacity": 0.6})]


def _cage_rotation(plate):
    return [(_box(-6.4, 6.4, -20.3, 20.3, -20.3, 20.3), ANODIZED, {}),
            (_cyl(19, 6.4, 11.5), "#333333", {}), (_cyl(12.7, -1.2, 1.2), plate, {"opacity": 0.85})]


def _cube(h, clamp=False):
    out = [(_box(-h, h, -h, h, -h, h), GLASS, {"opacity": 0.55, "specular": 0.8}),
           (_box(-h - 4, h + 4, -h - 4, h + 4, -h - 6, -h), ANODIZED, {})]
    if clamp:
        out.append((_box(-4, 4, -h - 4, h + 4, h, h + 5), ANODIZED, {}))
    return out


def simple_model(typ: str, beam_height: float):
    if typ in ("mirror_rd_1in", "mirror_rd_half_in"):
        return _rd_mirror(1.0 if typ.endswith("1in") else 0.62)
    if typ in ("mirror_1in", "mirror_d"):
        return _mirror_mount(12.7, 25.4)
    if typ in ("mirror_half_in", "mirror_polaris_half"):
        return _mirror_mount(6.35, 14.0)
    if typ in ("hwp", "qwp"):
        return _rotation_mount(12.7, "#f4c430" if typ == "hwp" else "#7cc576", 27.7)
    if typ in ("hwp_half", "qwp_half"):
        return _rotation_mount(6.35, "#f4c430" if typ == "hwp_half" else "#7cc576", 14.0)
    if typ == "fiber":
        return _fiber_port()
    if typ == "mirror_newport_half":
        return _newport_m05()
    if typ == "lens_1in":
        return _lens_cp33()
    if typ == "lens_lmr1":
        return _lens_ring(12.7)
    if typ == "lens_half_in":
        return _lens_ring(6.35)
    if typ in ("hwp_crm", "qwp_crm"):
        return _cage_rotation("#f4c430" if typ.startswith("h") else "#7cc576")
    if typ in ("pbs", "bs", "pbs_mounted"):
        return _cube(12.7, typ == "pbs_mounted")
    if typ == "pbs_half":
        return _cube(6.35)
    if typ == "aom":
        return [(_box(-12.5, 12.5, -33, 33, -12, 12), "#1f3a93", {}), (_cyl(3, 33, 40, axis=(0, 1, 0)), ALU, {})]
    if typ == "laser":
        return [(_box(-160, 0, -60, 60, -beam_height, 40), "#0b55a5", {}), (_cyl(5, 0, 1.5), "#d81e26", {})]
    if typ == "beam_entry":
        return [(pv.Sphere(radius=3, center=(0, 0, 0)), "#ff8c00", {})]
    if typ == "shutter":
        return [(_box(-9.5, 9.5, -19, 19, -19, 19), "#2b2b2b", {}), (_cyl(1.5, 0, 12, axis=(0, 1, 0), center=(0, 19, 0)),
                                                                     "#555555", {})]
    if typ == "dump":
        return [(_cyl(12.7, 0, 26), "#151515", {})]
    if typ == "photodiode":
        return [(_box(0, 20, -25, 25, -20, 20), "#3c4a5c", {}), (_cyl(4, -0.6, 0), MIRROR, {})]
    if typ == "iris":
        return [(_cyl(16, -1.5, 1.5), ANODIZED, {})]
    return [(_box(-10, 10, -10, 10, -10, 10), "#888888", {})]  # unknown: a grey block


def _fiber_cage():
    """Cage fiber coupler: small asphere in a CP33 at the optic, four Ø6 mm
    rods back to a second CP33 holding the FC/APC adapter, connector (green
    APC boot) and the fiber leaving backwards."""
    plate = _vendor("CP33-Step.step")
    out = []
    for x in (0.0, -25.0):
        out.append(((plate.translate((x, 0, 0), inplace=False) if plate is not None
                     else _box(x - 4.4, x + 4.4, -20.3, 20.3, -20.3, 20.3)), ANODIZED, {"smooth_shading": True, "split_sharp_edges": True}))
    for y in (-15, 15):
        for z in (-15, 15):
            out.append((_cyl(3.0, -29.4, 4.4, center=(0, y, z), res=16), ALU, {"specular": 0.8}))
    out += [(_cyl(4.0, -1.5, 1.5, res=32), GLASS, {"opacity": 0.6, "specular": 0.8}),  # asphere
            (_cyl(9.0, -33.5, -29.4, res=32), ANODIZED, {}),  # SM1 FC/APC adapter
            (_cyl(3.6, -46.0, -33.5, res=24), ALU, {"specular": 0.6}),  # connector body
            (_cyl(2.6, -60.0, -46.0, res=24), "#2e9e3e", {}),  # APC boot (green)
            (_cyl(1.5, -110.0, -60.0, res=12), "#1f5fbf", {})]  # fiber jacket
    return out


def part_model(typ: str, beam_height: float):
    """(mesh, colour, options) pieces of one part in its own frame."""
    if typ == "fiber_cage":
        return _fiber_cage()
    m = MODELS.get(typ)
    if m is not None and m.step:
        mesh = _vendor(m.step)
        if mesh is not None:
            if m.rot_x:
                mesh = mesh.rotate_x(m.rot_x, inplace=False)
            opts = {"smooth_shading": True, "split_sharp_edges": True, "specular": 0.4}
            if "RGB" in mesh.point_data:  # multi-coloured part (e.g. Radiant Dyes red body, brass knobs)
                opts.update(scalars="RGB", rgb=True)
            out = [(mesh, VENDOR_COLORS.get(Path(m.step).stem, ANODIZED), opts)]
            if m.mirror_disc:  # the mirror itself: 1" ones are 5 mm thick, 1/2" ones 6 mm
                t = 5.0 if m.mirror_disc > 20 else 6.0
                out.append((_cyl(m.mirror_disc / 2, -t, 0, res=48), MIRROR, {"specular": 1.0}))
            if m.d_mirror:  # half a disc: the circle's centre on the straight edge, 5 mm right of the beam
                disc = _cyl(m.d_mirror / 2, -6.0, 0, center=(0, -5.0, 0), res=64).triangulate()
                out.append((disc.clip(normal=(0, -1, 0), origin=(0, -5.0, 0)), MIRROR, {"specular": 1.0}))
            if m.glass_disc:
                out.append((_cyl(m.glass_disc / 2, -2.0, 2.0, res=48), GLASS, {"opacity": 0.55, "specular": 0.8}))
            return out
    return simple_model(typ, beam_height)


def _pillar(typ: str) -> pv.PolyData | None:
    stem = OLEGO_PILLARS.get(typ)
    if stem is None:
        return None
    key = "Olego/" + stem
    if key not in _mesh_cache:
        f = MESH_DIR / "Olego" / f"{stem}.ply"
        _mesh_cache[key] = pv.read(f) if f.exists() else _simple_pillar(stem)
    return _mesh_cache[key]


def _simple_pillar(stem: str) -> pv.PolyData:
    """Stands in for a pillar with no mesh: its flange and a column up to the seat."""
    MISSING_MESHES.add(stem)
    _height, seat, flange = pillar_info(stem)
    return pv.merge([_box(-flange / 2, flange / 2, -flange / 2, flange / 2, 0, 4).triangulate(),
                     _cyl(flange / 4, 0, seat, axis=(0, 0, 1), res=24).triangulate()], merge_points=False)


def base_height(typ: str) -> float:
    m = MODELS.get(typ)
    if m is not None:
        return m.base_height
    return 12.7


# ---- the board ---------------------------------------------------------------------

def _board_rects(t) -> list[tuple[float, float, float, float]]:
    """The board (minus its cut-outs) as non-overlapping rectangles (x0, y0, x1, y1)."""
    xs = sorted({0.0, t.width} | {v for c in t.cutouts for v in (c[0], c[0] + c[2]) if 0 < v < t.width})
    out = []
    for x0, x1 in zip(xs, xs[1:]):
        xm = (x0 + x1) / 2
        cuts = sorted((c[1], c[1] + c[3]) for c in t.cutouts if c[0] < xm < c[0] + c[2])
        y = 0.0
        for a, b in cuts:
            if a > y:
                out.append((x0, y, x1, min(a, t.height)))
            y = max(y, b)
        if y < t.height:
            out.append((x0, y, x1, t.height))
    return out


def board_solid(t) -> pv.PolyData:
    """The board as one solid: its outline (rectangle minus cut-outs) extruded
    down by the thickness. Built from a single outline, not glued-together
    blocks, so no seam shows where a cut-out starts."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainterPath
    path = QPainterPath()
    path.addRect(QRectF(0, 0, t.width, t.height))
    for cx, cy, cw, ch in t.cutouts:
        hole = QPainterPath()
        hole.addRect(QRectF(cx, cy, cw, ch))
        path = path.subtracted(hole)
    solids = []
    for poly in path.simplified().toFillPolygons():
        pts = [(q.x(), -q.y(), 0.0) for q in poly]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts = pts[:-1]
        top = pv.PolyData(np.array(pts, float), np.array([len(pts), *range(len(pts))])).triangulate()
        solids.append(top.extrude((0, 0, -board_thickness(t)), capping=True))
    if not solids:  # fall back to blocks
        return pv.merge([_box(x0, x1, -y0, -y1, -board_thickness(t), 0) for x0, y0, x1, y1 in _board_rects(t)])
    board = pv.merge(solids).triangulate().clean()
    return board.compute_normals(split_vertices=True, feature_angle=30, auto_orient_normals=True)


def _quad(c, x0, x1, y0, y1, z0, z1) -> pv.PolyData:
    """A box given in a part's library frame (x along the beam, y left), turned and placed with the part."""
    return _box(x0, x1, y0, y1, z0, z1).rotate_z(c.angle, inplace=False).translate((c.x, -c.y, 0), inplace=False)


def _block_mesh(c, style: str) -> list[pv.PolyData]:
    """The printed adapter (PyOpticL) or machined pedestal (LightFlow) under a part."""
    e = LIGHTFLOW_ELEMENTS.get(c.type) if style == "lightflow" else None
    if e is not None and e.mesh and mount_boxes(c.type, style):  # the lab's pedestal, its real shape
        key = "LightFlow/" + e.mesh
        if key not in _mesh_cache:
            f = MESH_DIR / "LightFlow" / f"{e.mesh}.ply"
            _mesh_cache[key] = pv.read(f) if f.exists() else None
        if _mesh_cache[key] is not None:
            return [_place(_mesh_cache[key], c.angle, c.x, c.y, 0.0)]
    return [_quad(c, b.x0, b.x1, b.y0, b.y1, b.z0, b.z1) for b in mount_boxes(c.type, style)]


def _pocket_mesh(c, style: str) -> list[pv.PolyData]:
    """The pocket milled for a part that sits lower than the plate top: its
    opening, a thin dark patch on the plate (the plate itself is not cut)."""
    if sunk_depth(c.type, style) <= 0:
        return []
    b = mount_block(c.type, style)
    if b is not None:
        r, pad = (b.x0, b.x1, b.y0, b.y1), 2.0  # PyOpticL adapters: 2 mm drill tolerance
    else:
        fp = footprint(c.type) or (-12.0, 12.0, -12.0, 12.0)
        r, pad = (fp[0], fp[1], -fp[3], -fp[2]), PYOPTICL_POCKET_PAD
    return [_quad(c, r[0] - pad, r[1] + pad, r[2] - pad, r[3] + pad, 0.0, 0.08)]


def hole_positions(layout: Layout) -> list[tuple[float, float]]:
    t = layout.table
    pts = []
    if t.style in DRILLED_STYLES:  # what shows from above: the table screws
        return table_screw_holes(t, [(c.type, c.x, c.y, c.angle) for c in layout.components.values()
                                        if SYMBOLS[c.type].physical and t.on_board(c.x, c.y)])
    if t.has_grid:
        nx, ny = t.columns(), t.rows()
        for i in range(nx):
            for j in range(ny):
                x, y = t.hole_offset + i * t.hole_pitch, t.hole_offset + j * t.hole_pitch
                pts.append((x, y))
                if t.center_holes and t.center_hole_ok(x + t.hole_pitch / 2, y + t.hole_pitch / 2):
                    pts.append((x + t.hole_pitch / 2, y + t.hole_pitch / 2))
    else:
        pts = [(c.x, c.y) for c in layout.components.values() if SYMBOLS[c.type].physical]
    if t.has_grid:
        return [(x, y) for x, y in pts if t.hole_ok(x, y)]
    return [(x, y) for x, y in pts if t.on_board(x, y)]


def _discs(pts, r, z, n=12) -> pv.PolyData:
    """Many flat discs as one mesh (the holes)."""
    if not pts:
        return pv.PolyData()
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring = np.stack([np.cos(a) * r, np.sin(a) * r, np.zeros(n)], 1)
    P = np.asarray(pts, float)
    verts = (ring[None, :, :] + np.stack([P[:, 0], -P[:, 1], np.full(len(P), z)], 1)[:, None, :]).reshape(-1, 3)
    faces = np.hstack([np.full((len(P), 1), n), (np.arange(len(P))[:, None] * n + np.arange(n)[None, :])]).ravel()
    return pv.PolyData(verts, faces)


# ---- the scene -----------------------------------------------------------------------

def _place(mesh: pv.PolyData, angle_deg: float, x: float, y: float, z: float) -> pv.PolyData:
    return mesh.rotate_z(angle_deg, inplace=False).translate((x, -y, z), inplace=False)


# ---- studio look -------------------------------------------------------------------------
# Physically based materials (metal/roughness) for each drawing colour, lit by a
# soft studio environment, with shadows, ambient occlusion and glowing beams.
PBR = {
    ANODIZED: dict(metallic=0.05, roughness=0.55),  # black anodizing: satin
    PILLAR: dict(metallic=0.35, roughness=0.45),
    ALU: dict(metallic=1.0, roughness=0.32),  # brushed aluminium
    BOARD: dict(metallic=0.9, roughness=0.48),
    HOLE: dict(metallic=0.2, roughness=0.8),
    MIRROR: dict(metallic=1.0, roughness=0.04),
    GLASS: dict(metallic=0.0, roughness=0.05),
    RD_RED: dict(metallic=0.45, roughness=0.35),
    RD_YELLOW: dict(metallic=0.9, roughness=0.3),
}
DEFAULT_PBR = dict(metallic=0.3, roughness=0.45)

THEMES = {  # background (bottom, top) and how bright the studio is
    "light": dict(bg=("#e4e6ea", "#fbfbfc"), env=(0.62, 0.40, 0.16), key=1.0),
    "dark": dict(bg=("#07080b", "#1c2029"), env=(0.26, 0.08, 0.02), key=0.8),
}


def _style(color, opts: dict, studio: bool) -> dict:
    """add_mesh keyword arguments for a part piece: the classic look, or a
    physically based material for the studio look."""
    kw = dict(opts)
    if not studio:
        return kw
    kw.pop("specular", None)
    kw.pop("ambient", None)
    mat = PBR.get(color, DEFAULT_PBR) if isinstance(color, str) else DEFAULT_PBR
    if kw.get("rgb"):  # multi-coloured vendor parts (Radiant Dyes red + brass)
        mat = PBR[RD_RED]
    kw.update(pbr=True, **mat)
    return kw


def _env_cubemap(theme: str):
    """A soft studio as a cube map: bright overhead softbox, light grey walls,
    darker floor. Made once and cached as six small images."""
    import numpy as np
    from PIL import Image

    top, side, floor = THEMES[theme]["env"]
    folder = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "optolayout" / f"env_{theme}"
    names = ["posx", "negx", "posy", "negy", "posz", "negz"]
    paths = [folder / f"{n}.png" for n in names]
    if not all(p.exists() for p in paths):
        folder.mkdir(parents=True, exist_ok=True)
        n = 128
        v = np.linspace(1, 0, n)[:, None] * np.ones((1, n))  # 1 at the top edge of a side face
        u = np.linspace(-1, 1, n)
        soft = np.exp(-(u[:, None] ** 2 + u[None, :] ** 2) * 1.6)  # softbox in the middle of a face
        faces = {
            # cube-map convention: +y is up
            "posy": top * (0.75 + 0.25 * soft),
            "negy": floor * np.ones((n, n)),
        }
        for k in ("posx", "negx", "posz", "negz"):
            faces[k] = floor + (side - floor) * v ** 0.6 + 0.15 * side * soft * v
        for name, p in zip(names, paths):
            img = (np.clip(faces[name], 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
            Image.fromarray(np.stack([img] * 3, -1)).save(p)
    return pv.cubemap_from_filenames([str(p) for p in paths])


def setup_studio(plotter, theme: str = "light") -> None:
    """Lights, environment, shadows, ambient occlusion and smoothing for the studio look."""
    th = THEMES[theme]
    plotter.set_background(th["bg"][0], top=th["bg"][1])
    plotter.remove_all_lights()
    k = th["key"]
    # key (casts the shadows), fill from the other side, rim from behind
    plotter.add_light(pv.Light(position=(-350, -500, 900), focal_point=(120, -240, 0), intensity=0.85 * k,
                               light_type="scene light", positional=False))
    plotter.add_light(pv.Light(position=(700, -300, 400), focal_point=(120, -240, 0), intensity=0.35 * k,
                               light_type="scene light", positional=False))
    plotter.add_light(pv.Light(position=(200, 600, 500), focal_point=(120, -240, 0), intensity=0.45 * k,
                               light_type="scene light", positional=False))
    try:
        plotter.set_environment_texture(_env_cubemap(theme), is_srgb=True)
        ren = plotter.renderer
        if hasattr(ren, "SetEnvironmentUp"):  # our z is up, the cube map's y is
            ren.SetEnvironmentUp(0.0, 0.0, 1.0)
            ren.SetEnvironmentRight(1.0, 0.0, 0.0)
    except Exception:
        pass  # older VTK: plain lights only
    # (VTK's shadow-map pass doesn't work with these materials: contact shadows are drawn instead)
    try:
        plotter.enable_ssao(radius=3.0, bias=0.5, kernel_size=64, blur=False)  # darkens crevices and joints
    except Exception:
        pass
    plotter.enable_depth_peeling(number_of_peels=4)
    plotter.enable_anti_aliasing("fxaa")


def _contact_shadows(plotter, spots, dark: bool) -> None:
    """Soft shadows on the board under each part: a blurred dark ellipse per
    part, nudged away from the key light, faded to nothing at its rim."""
    if not spots:
        return
    n, rings = 32, 5
    pts, cols, faces = [], [], []
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    for cx, cy, rx, ry, h in spots:
        ox, oy = 0.12 * h, 0.17 * h  # key light comes from -x, -y, high up
        base = len(pts)
        pts.append((cx + ox, cy + oy, 0.08))
        cols.append((0, 0, 0, 0.55 if not dark else 0.75))
        for k in range(1, rings + 1):
            f = k / rings
            for t in a:
                pts.append((cx + ox + np.cos(t) * rx * f, cy + oy + np.sin(t) * ry * f, 0.08))
                cols.append((0, 0, 0, (0.55 if not dark else 0.75) * (1 - f) ** 1.6))
        for i in range(n):  # centre fan
            faces += [3, base, base + 1 + i, base + 1 + (i + 1) % n]
        for k in range(rings - 1):
            r0, r1 = base + 1 + k * n, base + 1 + (k + 1) * n
            for i in range(n):
                j = (i + 1) % n
                faces += [4, r0 + i, r1 + i, r1 + j, r0 + j]
    mesh = pv.PolyData(np.array(pts, float), np.array(faces))
    mesh.point_data["rgba"] = (np.array(cols) * 255).astype(np.uint8)
    plotter.add_mesh(mesh, scalars="rgba", rgba=True, lighting=False, name="contact_shadows")


def _glow_beam(plotter, p0, p1, color: str, name: str) -> None:
    """A beam that looks lit: a bright core and two soft translucent halos,
    none of them shaded or casting shadows."""
    import numpy as np
    line = pv.Line(p0, p1)
    c = np.array(pv.Color(color).float_rgb)
    core = tuple(0.45 * c + 0.55)  # whiter at the centre, like a saturated beam
    plotter.add_mesh(line.tube(radius=0.7, n_sides=12), color=core, lighting=False, name=name)
    plotter.add_mesh(line.tube(radius=1.6, n_sides=16), color=color, lighting=False, opacity=0.5,
                     name=name + "_halo")
    plotter.add_mesh(line.tube(radius=3.4, n_sides=16), color=color, lighting=False, opacity=0.16,
                     name=name + "_glow")


# ---- measurement points: a power-sensor head on the beam -------------------------------
CHANGE_ALERT_PCT = 10.0  # same as the 2D callouts


def _s121c():
    """Thorlabs S121C photodiode power sensor facing the beam (aperture towards
    -x, the light), origin = centre of the aperture. The vendor model when its
    mesh exists (tools/simplify_cad.py), else a simple round head."""
    mesh = _vendor("S121C-Step.step")
    if mesh is not None:
        return [(mesh, ANODIZED, {"smooth_shading": True, "split_sharp_edges": True, "pbr": True,
                                  "metallic": 0.12, "roughness": 0.5}),
                (_cyl(4.75, -0.3, -0.1, res=40), "#1a1630", {"specular": 0.9})]  # Ø9.5 mm photodiode
    return [(_cyl(14.0, 0.0, 11.0, res=40), "#2f343b", {"pbr": True, "metallic": 0.2, "roughness": 0.45}),
            (_cyl(7.5, -0.6, 0.0, res=40), "#c9ccd1", {"pbr": True, "metallic": 1.0, "roughness": 0.3}),
            (_cyl(4.75, -0.8, -0.5, res=32), "#101214", {}),  # Ø9.5 mm aperture
            (_cyl(2.0, 11.0, 18.0, res=16), "#1b1b1b", {})]  # cable


def point_text(point, latest, layout=None) -> tuple[str, str]:
    """Pop-up text and colour for a measurement point: name, last power, when
    (and, at a fiber's end, the coupling efficiency)."""
    from .logbook import format_power
    rec = latest.get(point.id) if latest else None
    if not rec:
        return f"{point.label}\nno reading yet", "#444444"
    last, prev = rec[0], rec[1]
    eff = layout.coupling_efficiency(point, latest) if layout is not None else None
    text = (f"{point.label}  {format_power(last.power_mw)}" + (f"  ({eff * 100:.0f} % coupled)" if eff else "")
            + f"\n{last.measured_at[:16].replace('T', ' ')}")
    color = "#222222"
    if prev is not None and prev.power_mw:
        pct = (last.power_mw - prev.power_mw) / prev.power_mw * 100
        text += f"  ({pct:+.0f} %)"
        if abs(pct) >= CHANGE_ALERT_PCT:
            color = "#d62728" if pct < 0 else "#2ca02c"
    return text, color


def _add_meters(plotter, layout: Layout, zs: dict, latest, studio: bool) -> dict:
    """A small glowing bead on the beam at every measurement point, and a
    sensor head that stays hidden until the point is hovered. Returns
    {pid: (position, text, colour)}; keeps actor -> pid (for picking) and
    pid -> head actors (to show on hover) on the plotter."""
    import numpy as np
    meters, actor_pid, heads, beads = {}, {}, {}, {}
    for pt in layout.points.values():
        if pt.archived:
            continue
        b = layout.beams.get(pt.beam_id or "")
        end = layout.fiber_end(pt.part_id, in_3d=True) if pt.part_id else None
        if end is not None:  # the fiber's free end: the sensor faces it
            c = layout.components[pt.part_id]
            z = zs.get(c.id, 50.8)
            pos = np.array([end[0], -end[1], z])
            d = pos - np.array([c.x, -c.y, z])
        else:
            if b is None:
                continue
            a, z_ = layout.components.get(b.source), layout.components.get(b.target)
            if a is None or z_ is None:
                continue
            p0 = np.array([a.x, -a.y, zs.get(a.id, 50.8)])
            p1 = np.array([z_.x, -z_.y, zs.get(z_.id, 50.8)])
            pos = p0 + (p1 - p0) * pt.t
            d = p1 - p0
        ang = math.degrees(math.atan2(d[1], d[0]))  # head faces back along the beam, towards the light
        text, tcolor = point_text(pt, latest, layout)
        bead = plotter.add_mesh(pv.Sphere(radius=4.5, center=pos), name=f"meter_{pt.id}_bead", lighting=False,
                                color=tcolor if tcolor in ("#d62728", "#2ca02c") else "#ffb000")
        actor_pid[bead] = pt.id
        beads[pt.id] = bead
        acts = []
        for i, (mesh, color, opts) in enumerate(_s121c()):
            m = mesh.rotate_z(ang, inplace=False).translate(pos, inplace=False)
            kw = dict(opts) if studio else {k: v for k, v in opts.items() if k not in ("pbr", "metallic", "roughness")}
            acts.append(plotter.add_mesh(m, color=color, name=f"meter_{pt.id}_{i}", **kw))
        head_r = 15.2  # the sensor head's radius: the post reaches its underside
        u = d[:2] / (np.linalg.norm(d[:2]) or 1.0)
        mid = pos[:2] + u * 6.0  # under the middle of the 12.7 mm deep head, behind the aperture
        stem = _cyl(3.0, 0.0, max(pos[2] - head_r, 1.0), axis=(0, 0, 1), center=(mid[0], mid[1], 0), res=16)
        acts.append(plotter.add_mesh(stem, color=ALU, name=f"meter_{pt.id}_post",
                                     **({"pbr": True, "metallic": 1.0, "roughness": 0.35} if studio else {})))
        for act in acts:
            act.SetVisibility(False)  # the sensor only appears while its point is hovered
            actor_pid[act] = pt.id
        heads[pt.id] = acts
        meters[pt.id] = (tuple(pos + np.array([0, 0, 16.0])), text, tcolor)
    plotter._opto_meter_actors = actor_pid
    plotter._opto_meter_heads = heads
    plotter._opto_meter_beads = beads
    plotter._opto_meters = meters
    return meters


def show_point_labels(plotter, meters: dict, ids=None, name: str = "mp_labels", dark: bool = False) -> None:
    """Floating labels (always facing the viewer) for the given points."""
    ids = list(meters) if ids is None else [i for i in ids if i in meters]
    plotter.remove_actor(name, render=False)
    if not ids:
        return
    pts = [meters[i][0] for i in ids]
    plotter.add_point_labels(pts, [meters[i][1] for i in ids], name=name, font_size=13, point_size=0,
                             shape="rounded_rect", shape_color="#1c2029" if dark else "white", shape_opacity=0.88,
                             text_color="white" if dark else meters[ids[0]][2], always_visible=True,
                             margin=5, show_points=False, render=False)


def populate(plotter, layout: Layout, beam_height: float = 50.8, studio: bool = False, latest=None,
             progress=None) -> dict:
    """Add the board, parts, posts and beams to a pyvista plotter. Returns
    {part id: [actors]} so a caller can highlight or hide parts. progress, if
    given, is called as progress(fraction done, what is being built)."""
    tick = progress or (lambda _f, _what: None)
    tick(0.02, "Board and holes")
    t = layout.table
    actors: dict[str, list] = {}
    board = board_solid(t)
    plotter.add_mesh(board, color=BOARD, name="board", **_style(BOARD, {"specular": 0.3, "ambient": 0.35}, studio))
    drilled = t.style in DRILLED_STYLES
    hole_r = max(TABLE_SCREW[t.style]) / 2 if drilled else t.hole_diameter / 2
    holes = _discs(hole_positions(layout), hole_r, 0.05, n=24 if drilled else 12)
    if holes.n_points:
        plotter.add_mesh(holes, color=HOLE, name="holes", **_style(HOLE, {}, studio))
    posts, pillars, adapters, pockets = [], [], [], []
    spots = []  # contact shadows: (x, y, rx, ry, height)
    zs = {}  # part id -> optic height
    parts = list(layout.components.values())
    for k, c in enumerate(parts):
        tick(0.06 + 0.8 * k / max(len(parts), 1), f"Parts {k + 1} of {len(parts)}")
        zs[c.id] = optic_height(c.type, t.style, beam_height)
        if not t.on_board(c.x, c.y) and c.type != "beam_entry":
            continue  # parts waiting below the board
        z = zs[c.id]
        acts = []
        lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
        pieces = part_model(c.type, z)
        if t.style == "lightflow" and c.type in LIGHTFLOW_BODY:  # the lab's own part (e.g. the AOM as long as its plate)
            pieces = [(_box(*LIGHTFLOW_BODY[c.type]), pieces[0][1], pieces[0][2])] + pieces[1:]
        if drilled and c.type in ("pbs", "bs", "pbs_half") and mount_block(c.type, t.style) is not None:
            pieces = pieces[:1]  # the cube sits on its adapter or pedestal, not on a platform
        roll = mount_roll(c.type, t.style)
        for i, (mesh, color, opts) in enumerate(pieces):
            if roll:  # turned about the beam on its pedestal (the lab's iris stands on its side)
                mesh = mesh.rotate_x(roll, inplace=False)
            placed = _place(mesh, c.angle, c.x, c.y, z)
            if placed.n_points:
                b = np.array(placed.bounds).reshape(3, 2)
                lo, hi = np.minimum(lo, b[:, 0]), np.maximum(hi, b[:, 1])
            acts.append(plotter.add_mesh(placed, color=color, name=f"{c.id}_{i}", **_style(color, opts, studio)))
        if studio and SYMBOLS[c.type].physical and np.isfinite(lo).all():
            spots.append(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, max((hi[0] - lo[0]) * 0.62, 8),
                          max((hi[1] - lo[1]) * 0.62, 8), hi[2]))
        actors[c.id] = acts
        if not SYMBOLS[c.type].physical or c.type == "laser":
            continue
        pillar = _pillar(c.type) if t.style == "olego" else None
        if pillar is not None:  # Olego: the pillar made for this mount, under its base, flange square to the board
            px, py = pillar_xy(c.type, c.x, c.y, c.angle)
            square = round(c.angle / 90.0) * 90.0
            pillars.append(pillar.rotate_z(square, inplace=False).translate((px, -py, 0), inplace=False))
            continue
        if drilled:  # no posts: an adapter / pedestal, or a pocket, where the mount needs one
            adapters += _block_mesh(c, t.style)
            pockets += _pocket_mesh(c, t.style)
            continue
        top = z - base_height(c.type)
        if top > 1:
            posts.append(_cyl(6.35, 0, top, axis=(0, 0, 1), center=(c.x, -c.y, 0), res=24))
            posts.append(_cyl(11, 0, 3, axis=(0, 0, 1), center=(c.x, -c.y, 0), res=24))  # base
    tick(0.88, "Posts and pillars")
    if posts:
        plotter.add_mesh(pv.merge(posts, merge_points=False), color=ALU, smooth_shading=True,
                         split_sharp_edges=True, name="posts", **_style(ALU, {"specular": 0.6}, studio))
    if pillars:
        plotter.add_mesh(pv.merge(pillars, merge_points=False), color=PILLAR, smooth_shading=True,
                         split_sharp_edges=True, name="pillars", **_style(PILLAR, {"specular": 0.3}, studio))
    if pockets:  # drawn as dark recesses on the plate top
        plotter.add_mesh(pv.merge(pockets, merge_points=False), color=HOLE, name="pockets", **_style(HOLE, {}, studio))
    if adapters:
        plotter.add_mesh(pv.merge(adapters, merge_points=False), color=BLOCK_COLOR[t.style], smooth_shading=True,
                         split_sharp_edges=True, name="adapters",
                         **_style(BLOCK_COLOR[t.style], {"specular": 0.2}, studio))
    tick(0.92, "Shadows and beams")
    if studio:
        _contact_shadows(plotter, spots, plotter.background_color.float_rgb[0] < 0.3)
    for b in layout.beams.values():
        a, z_ = layout.components.get(b.source), layout.components.get(b.target)
        if a is None or z_ is None:
            continue
        p0, p1 = (a.x, -a.y, zs[a.id]), (z_.x, -z_.y, zs[z_.id])
        if studio:
            _glow_beam(plotter, p0, p1, b.color, f"beam_{b.id}")
            continue
        line = pv.Line(p0, p1)
        plotter.add_mesh(line.tube(radius=0.9, n_sides=12), color=b.color, ambient=0.7, name=f"beam_{b.id}")
    tick(0.97, "Power sensors")
    _add_meters(plotter, layout, zs, latest, studio)
    return actors


def frame_board(plotter, layout: Layout, beam_height: float = 50.8) -> None:
    """Look at the whole board from the front-left, a little above."""
    t = layout.table
    cx, cy = t.width / 2, -t.height / 2
    plotter.camera.focal_point = (cx, cy, beam_height * 0.4)
    plotter.camera.position = (cx - 0.45, cy - 1.0, beam_height * 0.4 + 0.9)  # direction only; the fit sets distance
    plotter.camera.up = (0, 0, 1)
    plotter.reset_camera(bounds=(0, t.width, -t.height, 0, -board_thickness(t), beam_height + 30))
    plotter.camera.zoom(1.15)


# ---- the tab -------------------------------------------------------------------------------

def make_view3d_widget(get_layout, get_latest=None, open_log=None):
    """The 3D tab: a pyvistaqt view plus a small toolbar. Rebuilt from the
    layout when shown and after edits (call .schedule()). Measurement points
    show as power sensors: hover one for its last reading, click it for its log."""
    import time

    from PySide6.QtCore import QEventLoop, Qt, QTimer
    from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                                   QProgressBar, QPushButton, QVBoxLayout, QWidget)
    from pyvistaqt import QtInteractor

    class View3D(QWidget):
        def __init__(self):
            super().__init__()
            self.get_layout = get_layout
            self.get_latest = get_latest or (lambda: {})
            self.open_log = open_log
            self.plotter = QtInteractor(self)
            self.labels = QCheckBox("Power labels")
            self.labels.setToolTip("Show every measurement point's last reading. Without it, hover a sensor.")
            self.labels.toggled.connect(lambda _on: self._refresh_labels())
            self._hover = None
            self._press = None
            iren = self.plotter.iren
            iren.add_observer("MouseMoveEvent", self._on_move)
            iren.add_observer("LeftButtonPressEvent", self._on_press)
            iren.add_observer("LeftButtonReleaseEvent", self._on_release)
            self.studio = QCheckBox("Studio look")
            self.studio.setToolTip("Realistic materials, studio lighting, shadows and glowing beams. "
                                   "Untick if rotating gets slow.")
            self.studio.setChecked(True)
            self.theme = QComboBox()
            self.theme.addItem("Light studio", "light")
            self.theme.addItem("Dark studio", "dark")
            self.studio.toggled.connect(lambda _on: self.rebuild(restyle=True))
            self.theme.currentIndexChanged.connect(lambda _i: self.rebuild(restyle=True))
            self.beam_h = QDoubleSpinBox()
            self.beam_h.setRange(10, 300)
            self.beam_h.setDecimals(1)
            self.beam_h.setSuffix(" mm")
            self.beam_h.setValue(50.8)
            self.beam_h.valueChanged.connect(lambda _v: self.rebuild())
            reset = QPushButton("Fit board")
            reset.clicked.connect(self.fit)
            bar = QHBoxLayout()
            bar.addWidget(QLabel("Beam height"))
            bar.addWidget(self.beam_h)
            bar.addWidget(reset)
            bar.addWidget(self.studio)
            bar.addWidget(self.theme)
            bar.addWidget(self.labels)
            bar.addStretch(1)
            self.busy_lbl = QLabel()
            self.busy_bar = QProgressBar()
            self.busy_bar.setFixedWidth(200)
            self.busy_bar.setRange(0, 100)
            self.busy_bar.setTextVisible(False)
            bar.addWidget(self.busy_lbl)
            bar.addWidget(self.busy_bar)
            self.busy_lbl.hide()
            self.busy_bar.hide()
            self._building = False
            self.hint = QLabel("Drag to rotate, wheel to zoom, Shift+drag to pan. Hover a power sensor "
                               "for its reading, click it for its log.")
            bar.addWidget(self.hint)
            v = QVBoxLayout(self)
            v.setContentsMargins(4, 4, 4, 4)
            v.addLayout(bar)
            v.addWidget(self.plotter.interactor, 1)
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.setInterval(250)
            self._timer.timeout.connect(self.rebuild)
            self._framed = False
            self.dirty = True
            if board_beam_height(get_layout().table):
                self.beam_h.setValue(board_beam_height(get_layout().table))

        def schedule(self):
            self.dirty = True
            if self.isVisible():
                self._timer.start()

        def _set_busy(self, on: bool, text: str = ""):
            self.busy_lbl.setVisible(on)
            self.busy_bar.setVisible(on)
            self.hint.setVisible(not on)
            self.busy_lbl.setText(text)

        def rebuild(self, restyle: bool = False):
            if self._building:  # an edit arrived while building: build again afterwards
                self._timer.start()
                return
            self._building = True
            t0 = last = time.perf_counter()
            show_now = restyle or not self._framed  # first build: always say what is happening

            def progress(f, what):
                # a progress bar for builds that take a while; repaint now and then (each repaint
                # also renders the half-built scene, so not after every part)
                nonlocal last
                now = time.perf_counter()
                if not self.busy_bar.isVisible():
                    if not (show_now or now - t0 > 0.3):
                        return
                    self._set_busy(True)
                self.busy_bar.setValue(int(f * 100))
                self.busy_lbl.setText(f"Building 3D: {what}…")
                if now - last > 0.08:
                    last = now
                    QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

            try:
                progress(0.0, "lighting")
                cam = self.plotter.camera_position if self._framed else None
                if restyle or not getattr(self, "_styled", False):
                    self._apply_style()
                self.plotter.clear_actors()
                if cam is None:
                    self.fit()  # so the parts appear in place while they are added
                populate(self.plotter, self.get_layout(), self.beam_h.value(), studio=self.studio.isChecked(),
                         latest=self.get_latest(), progress=lambda f, what: progress(f, what[0].lower() + what[1:]))
                self._hover = None
                self._refresh_labels(render=False)
                if MISSING_MESHES:
                    self.hint.setToolTip("No CAD installed for: " + ", ".join(sorted(MISSING_MESHES))
                                         + ". See component_library/README.md.")
                    self.hint.setText("Some parts are simple shapes: their CAD isn't installed "
                                      "(hover for which, see component_library/README.md).")
                if cam is None:
                    self.fit()
                else:
                    self.plotter.camera_position = cam
                self.dirty = False
            finally:
                self._building = False
                self._set_busy(False)

        def _apply_style(self):
            p = self.plotter
            for off in ("disable_shadows", "disable_ssao", "disable_depth_peeling", "disable_anti_aliasing"):
                try:
                    getattr(p, off)()
                except Exception:
                    pass
            self.theme.setEnabled(self.studio.isChecked())
            if self.studio.isChecked():
                setup_studio(p, self.theme.currentData())
            else:
                p.remove_all_lights()
                p.enable_lightkit()
                p.set_background("#f4f5f7", top="#ffffff")
                p.add_light(pv.Light(position=(-400, -600, 900), light_type="scene light", intensity=0.6))
                p.enable_anti_aliasing("msaa")
            self._styled = True

        # measurement points: hover pop-up, click for the log -----------------------------
        def _dark(self):
            return self.studio.isChecked() and self.theme.currentData() == "dark"

        def _meters(self):
            return getattr(self.plotter, "_opto_meters", {})

        def _refresh_labels(self, render: bool = True):
            if self.labels.isChecked():
                show_point_labels(self.plotter, self._meters(), dark=self._dark())
            else:
                self.plotter.remove_actor("mp_labels", render=False)
            if render:
                self.plotter.render()

        def _pick(self):
            import vtk
            x, y = self.plotter.iren.get_event_position()
            meters = getattr(self.plotter, "_opto_meter_actors", {})
            if not meters:
                return None
            # a ray-cast picker over the sensors only (the hardware picker fails with the studio render passes)
            picker = vtk.vtkCellPicker()
            picker.SetTolerance(0.002)
            picker.PickFromListOn()
            for act in meters:
                picker.AddPickList(act)
            picker.Pick(x, y, 0, self.plotter.renderer)
            return meters.get(picker.GetActor())

        def _on_move(self, *_):
            if self._press is not None:
                return  # rotating
            pid = self._pick()
            if pid == self._hover:
                return
            heads = getattr(self.plotter, "_opto_meter_heads", {})
            beads = getattr(self.plotter, "_opto_meter_beads", {})
            for act in heads.get(self._hover, []):
                act.SetVisibility(False)
            if self._hover in beads:
                beads[self._hover].SetVisibility(True)
            for act in heads.get(pid, []):
                act.SetVisibility(True)
            if pid in beads:
                beads[pid].SetVisibility(False)  # the sensor takes the bead's place
            self._hover = pid
            self.plotter.interactor.setCursor(Qt.ArrowCursor if pid is None else Qt.PointingHandCursor)
            if pid is None or self.labels.isChecked():
                self.plotter.remove_actor("mp_hover", render=False)
            else:
                show_point_labels(self.plotter, self._meters(), [pid], name="mp_hover", dark=self._dark())
            self.plotter.render()

        def _on_press(self, *_):
            self._press = self.plotter.iren.get_event_position()

        def _on_release(self, *_):
            start, self._press = self._press, None
            if start is None or self.open_log is None:
                return
            x, y = self.plotter.iren.get_event_position()
            if abs(x - start[0]) + abs(y - start[1]) > 4:
                return  # that was a drag
            pid = self._pick()
            if pid is not None:
                self.open_log(pid)

        def fit(self):
            frame_board(self.plotter, self.get_layout(), self.beam_h.value())
            self._framed = True
            self.plotter.render()

        def showEvent(self, e):
            super().showEvent(e)
            if self.dirty:
                self._timer.start()

        def board_changed(self, old_style: str):
            """A new board type: take the beam height it sets, or go back to the default from one that set it."""
            from types import SimpleNamespace
            h = board_beam_height(self.get_layout().table)
            if h is None and board_beam_height(SimpleNamespace(style=old_style)) is not None:
                h = DEFAULT_BEAM_HEIGHT
            if h is not None:
                self.beam_h.blockSignals(True)
                self.beam_h.setValue(h)
                self.beam_h.blockSignals(False)
            self._framed = False
            self.schedule()

        def reset_for_new_file(self):
            self._framed = False
            if board_beam_height(self.get_layout().table):  # the height the Olego pillars / PyOpticL plate give
                self.beam_h.blockSignals(True)
                self.beam_h.setValue(board_beam_height(self.get_layout().table))
                self.beam_h.blockSignals(False)
            self.schedule()

    return View3D()
