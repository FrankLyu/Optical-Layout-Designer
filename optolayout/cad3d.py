"""Milestone 2 prototype: build a 3D optomechanical assembly from a 2D layout.

The 2D layout stays the single source of truth. For every component with a 3D
model, the generator places the vendor STEP model (re-posed so the optic sits
at the origin with its normal along +x, z up, see component_library/README.md)
at the beam height on a post, post holder and base, and adds the breadboard
and the beams. Output: a STEP assembly and/or tessellated meshes grouped by
material for rendering.

Needs the OpenCascade bindings: ``pip install cadquery-ocp``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape

from .model import Layout

LIB = Path(__file__).resolve().parents[1] / "component_library" / "step"


@dataclass(frozen=True)
class Model3D:
    step: str
    base_height: float  # optic centre above the mount's bottom face (mm)
    rot_x: float = 0.0  # extra pose fix before placing (deg about x)
    mirror_disc: float = 0.0  # add a Ø mirror (mm) at the optic face


# 2D type -> 3D model. Radiant Dyes has no public CAD yet: KM100 stands in.
MODELS: dict[str, Model3D] = {
    "mirror_1in": Model3D("KM100.step", 25.40, mirror_disc=25.4),
    "mirror_rd_1in": Model3D("KM100.step", 25.40, mirror_disc=25.4),
    "mirror_half_in": Model3D("KM05.step", 14.73, mirror_disc=12.7),
    "mirror_rd_half_in": Model3D("KM05.step", 14.73, mirror_disc=12.7),
    "hwp": Model3D("RSP1.step", 27.73),
    "qwp": Model3D("RSP1.step", 27.73),
    "hwp_half": Model3D("RSP05.step", 13.98),
    "qwp_half": Model3D("RSP05.step", 13.98),
    "fiber": Model3D("PAF2-A4A_on_HCA3.step", 26.99),
    "iris": Model3D("IDA12.step", 12.83, rot_x=90.0),
}


# ---- small OCC helpers ---------------------------------------------------------

def _load_step(path: Path) -> TopoDS_Shape:
    r = STEPControl_Reader()
    if r.ReadFile(str(path)) != IFSelect_RetDone:
        raise IOError(f"cannot read {path}")
    r.TransferRoots()
    return r.OneShape()


def _moved(shape, rot_z_deg=0.0, translate=(0, 0, 0), rot_x_deg=0.0):
    t = gp_Trsf()
    if rot_x_deg:
        rx = gp_Trsf()
        rx.SetRotation(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)).Axis(), math.radians(rot_x_deg))
        t = rx
    rz = gp_Trsf()
    rz.SetRotation(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)).Axis(), math.radians(rot_z_deg))
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(*translate))
    full = tr.Multiplied(rz.Multiplied(t))
    return BRepBuilderAPI_Transform(shape, full, True).Shape()


def _cyl(r, h, base=(0, 0, 0), axis=(0, 0, 1)):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*base), gp_Dir(*axis)), r, h).Shape()


def _rounded_box(x0, y0, z0, dx, dy, dz, r):
    box = BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), dx, dy, dz).Shape()
    if r <= 0:
        return box
    f = BRepFilletAPI_MakeFillet(box)
    e = TopExp_Explorer(box, TopAbs_EDGE)
    while e.More():
        f.Add(r, TopoDS.Edge_s(e.Current()) if hasattr(TopoDS, "Edge_s") else TopoDS.Edge(e.Current()))
        e.Next()
    return f.Shape()


FLANGE_H = 6.35  # pedestal flange thickness (mm)


def _fork():
    """Clamping fork in its own frame: slot around the pedestal along -y, bolt end at +y."""
    body = _rounded_box(-15.9, -22.0, FLANGE_H - 0.01, 31.8, 66.0, 6.35, 1.5)
    slot = _cyl(19.6, 20, (0, 0, 0))
    slot_out = BRepPrimAPI_MakeBox(gp_Pnt(-19.6, -40, 0), 39.2, 40, 20).Shape()
    bolt = _cyl(3.3, 20, (0, 31.75, 0))
    cut = TopoDS_Compound()
    bb = BRep_Builder()
    bb.MakeCompound(cut)
    for sh in (slot, slot_out, bolt):
        bb.Add(cut, sh)
    fork = BRepAlgoAPI_Cut(body, cut).Shape()
    head = _cyl(5.0, 4.0, (0, 31.75, 2 * FLANGE_H))
    comp = TopoDS_Compound()
    bb.MakeCompound(comp)
    bb.Add(comp, fork)
    bb.Add(comp, head)
    return comp


# ---- assembly --------------------------------------------------------------------

@dataclass
class Part:
    name: str
    material: str  # anodized | aluminum | mirror | breadboard | beam
    shape: TopoDS_Shape


def build_assembly(layout: Layout, beam_height: float = 50.8, lib: Path = LIB) -> list[Part]:
    """Return the parts of the 3D assembly in table coordinates (mm).

    2D (x right, y down) maps to 3D (x right, y up, z up); angles keep their
    CCW-from-above meaning, so a 2D rotation is a rotation about +z.
    """
    parts: list[Part] = []
    t = layout.table
    cache: dict[str, TopoDS_Shape] = {}

    # breadboard with tapped holes
    th = 12.7
    board = BRepPrimAPI_MakeBox(gp_Pnt(0, -t.height, -th), t.width, t.height, th).Shape()
    nx = int((t.width - t.hole_offset) // t.hole_pitch) + 1
    ny = int((t.height - t.hole_offset) // t.hole_pitch) + 1
    holes = TopoDS_Compound()
    bb = BRep_Builder()
    bb.MakeCompound(holes)
    for i in range(nx):
        for j in range(ny):
            x = t.hole_offset + i * t.hole_pitch
            y = -(t.hole_offset + j * t.hole_pitch)
            bb.Add(holes, _cyl(3.0, th + 2, (x, y, -th - 1)))
    board = BRepAlgoAPI_Cut(board, holes).Shape()
    parts.append(Part("breadboard", "breadboard", board))

    for c in layout.components.values():
        m = MODELS.get(c.type)
        if m is None:
            continue
        X, Y = c.x, -c.y
        if m.step not in cache:
            if not (lib / m.step).exists():  # the mount is left out; its optic and post are still drawn
                print(f"no CAD for {m.step}: see component_library/README.md")
                cache[m.step] = None
            else:
                cache[m.step] = _load_step(lib / m.step)
        body = cache[m.step]
        if body is not None:
            if m.rot_x:
                body = _moved(body, rot_x_deg=m.rot_x)
            parts.append(Part(f"{c.label or c.type} ({c.id})", "anodized",
                              _moved(body, c.angle, (X, Y, beam_height))))
        if m.mirror_disc:
            disc = _cyl(m.mirror_disc / 2, 6.35, (-6.35, 0, 0), (1, 0, 0))
            parts.append(Part(f"{c.id} optic", "mirror", _moved(disc, c.angle, (X, Y, beam_height))))
        # Thorlabs Ø1" pedestal pillar post (RS-series, cut to length) on a
        # pedestal flange, held by a clamping fork (CF125-style); the post
        # length is whatever puts the optic at beam_height.
        top = beam_height - m.base_height
        if top <= FLANGE_H:
            raise ValueError(f"{c.id}: beam height {beam_height} mm is too low for {m.step}")
        parts.append(Part(f"{c.id} Ø1in post ({top:.1f} mm)", "aluminum",
                          _cyl(12.7, top - FLANGE_H, (X, Y, FLANGE_H))))
        parts.append(Part(f"{c.id} pedestal", "aluminum", _cyl(19.05, FLANGE_H, (X, Y, 0))))
        parts.append(Part(f"{c.id} clamping fork", "anodized",
                          _moved(_fork(), c.angle + 90, (X, Y, 0))))

    for b in layout.beams.values():
        a, z = layout.components[b.source], layout.components[b.target]
        p0 = np.array([a.x, -a.y, beam_height])
        p1 = np.array([z.x, -z.y, beam_height])
        d = p1 - p0
        L = float(np.linalg.norm(d))
        if L > 0:
            parts.append(Part(f"beam {b.id}", "beam",
                              _cyl(0.9, L, tuple(p0), tuple(d / L))))
    return parts


def write_step(parts: list[Part], path: str | Path) -> None:
    comp = TopoDS_Compound()
    bb = BRep_Builder()
    bb.MakeCompound(comp)
    for p in parts:
        if p.material != "beam":
            bb.Add(comp, p.shape)
    w = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    w.Transfer(comp, STEPControl_AsIs)
    w.Write(str(path))


def tessellate(shape: TopoDS_Shape, deflection: float = 0.08, angle: float = 0.25):
    """Triangle mesh (vertices, faces) with vertices shared inside each CAD face,
    so curved faces render smooth and edges between faces stay crisp."""
    BRepMesh_IncrementalMesh(shape, deflection, False, angle, True)
    verts, faces = [], []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    n0 = 0
    while exp.More():
        face = TopoDS.Face_s(exp.Current()) if hasattr(TopoDS, "Face_s") else TopoDS.Face(exp.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            tr = loc.Transformation()
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(tr)
                verts.append((p.X(), p.Y(), p.Z()))
            rev = face.Orientation() == TopAbs_REVERSED
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get()
                faces.append((n0 + a - 1, n0 + c - 1, n0 + b - 1) if rev else (n0 + a - 1, n0 + b - 1, n0 + c - 1))
            n0 += tri.NbNodes()
        exp.Next()
    return np.asarray(verts, dtype=np.float32), np.asarray(faces, dtype=np.int32)


def write_ply(path: str | Path, verts: np.ndarray, faces: np.ndarray) -> None:
    with open(path, "wb") as fh:
        fh.write((f"ply\nformat binary_little_endian 1.0\nelement vertex {len(verts)}\n"
                  "property float x\nproperty float y\nproperty float z\n"
                  f"element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n").encode())
        fh.write(verts.astype("<f4").tobytes())
        rec = np.empty(len(faces), dtype=[("n", "u1"), ("i", "<i4", 3)])
        rec["n"] = 3
        rec["i"] = faces
        fh.write(rec.tobytes())
