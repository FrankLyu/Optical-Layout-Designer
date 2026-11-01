"""Render a layout's 3D assembly as a clean studio image (and export STEP).

    python tools/render3d.py examples/demo_3d_simple.json [out.png] [--spp 256] [--size 1600x1000] [--theme light|dark]

Needs: cadquery-ocp (geometry) and mitsuba (rendering), both from pip.
Look: black anodized mounts, satin aluminium posts and breadboard, silver
mirrors, a glowing beam, on a seamless white studio floor with soft light.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from optolayout.cad3d import build_assembly, tessellate, write_ply, write_step  # noqa: E402
from optolayout.model import Layout  # noqa: E402

MATERIALS = {
    "anodized": {"type": "principled", "base_color": {"type": "rgb", "value": [0.018, 0.018, 0.02]},
                 "roughness": 0.32, "specular": 0.55},
    "aluminum": {"type": "principled", "base_color": {"type": "rgb", "value": [0.86, 0.87, 0.89]},
                 "metallic": 1.0, "roughness": 0.22},
    "breadboard": {"type": "principled", "base_color": {"type": "rgb", "value": [0.62, 0.63, 0.65]},
                   "metallic": 0.85, "roughness": 0.42},
    "mirror": {"type": "principled", "base_color": {"type": "rgb", "value": [0.97, 0.97, 0.98]},
               "metallic": 1.0, "roughness": 0.02},
}
BEAM_RGB = [0.55, 0.18, 1.0]  # 399 nm violet; keep radiance low enough not to clip to white


THEMES = {
    # bright product-shot studio
    "light": dict(env=[0.92, 0.93, 0.95], floor=[0.93, 0.93, 0.94], key=6.0, rim=3.0, beam=2.2, board=[0.62, 0.63, 0.65]),
    # dark keynote look: near-black backdrop, cool rim light, glowing beam
    "dark": dict(env=[0.010, 0.010, 0.016], floor=[0.035, 0.035, 0.045], key=5.0, rim=7.0, beam=3.0, board=[0.30, 0.31, 0.34]),
}


def render(layout_path: str, out_png: str, spp: int = 256, size=(1600, 1000), beam_height: float = 50.8,
           step_out: str | None = None, theme: str = "light") -> None:
    th = THEMES[theme]
    import mitsuba as mi
    try:
        mi.set_variant("llvm_ad_rgb")
    except Exception:
        mi.set_variant("scalar_rgb")

    lay = Layout.load(layout_path)
    parts = build_assembly(lay, beam_height)
    if step_out:
        write_step(parts, step_out)

    tmp = Path(tempfile.mkdtemp())
    groups: dict[str, list] = {}
    for p in parts:
        groups.setdefault(p.material, []).append(tessellate(p.shape, 0.05 if p.material != "breadboard" else 0.2))

    scene = {
        "type": "scene",
        "integrator": {"type": "path", "max_depth": 10},
        # seamless studio: white floor under the board + soft white surroundings
        "env": {"type": "constant", "radiance": {"type": "rgb", "value": th["env"]}},
        "floor": {"type": "rectangle", "to_world": mi.ScalarTransform4f().translate([0, 0, -12.71])
                  .scale([4000, 4000, 1]),
                  "bsdf": {"type": "diffuse", "reflectance": {"type": "rgb", "value": th["floor"]}}},
        "key": {"type": "rectangle",
                "to_world": mi.ScalarTransform4f().look_at(origin=[-250, -300, 700], target=[127, -100, 0],
                                                           up=[0, 0, 1]).scale([260, 260, 1]),
                "emitter": {"type": "area", "radiance": {"type": "rgb", "value": [th["key"]] * 3}}},
        "rim": {"type": "rectangle",
                "to_world": mi.ScalarTransform4f().look_at(origin=[600, 300, 400], target=[127, -100, 40],
                                                           up=[0, 0, 1]).scale([180, 180, 1]),
                "emitter": {"type": "area", "radiance": {"type": "rgb", "value": [th["rim"] * 0.9, th["rim"] * 0.95, th["rim"]]}}},
    }
    t = lay.table
    cx, cy = t.width / 2, -t.height / 2
    scene["camera"] = {
        "type": "perspective", "fov": 30, "fov_axis": "x",
        "to_world": mi.ScalarTransform4f().look_at(origin=[cx - 340, cy - 500, 330], target=[cx + 10, cy + 15, 30],
                                                   up=[0, 0, 1]),
        "film": {"type": "hdrfilm", "width": size[0], "height": size[1], "rfilter": {"type": "gaussian"}},
        "sampler": {"type": "independent", "sample_count": spp},
    }
    for mat, meshes in groups.items():
        V, F, n0 = [], [], 0
        for v, f in meshes:
            V.append(v)
            F.append(f + n0)
            n0 += len(v)
        path = tmp / f"{mat}.ply"
        write_ply(path, np.concatenate(V), np.concatenate(F))
        shape = {"type": "ply", "filename": str(path), "face_normals": mat == "beam"}
        if mat == "beam":
            shape["emitter"] = {"type": "area", "radiance": {"type": "rgb", "value": [v * th["beam"] for v in BEAM_RGB]}}
            shape["bsdf"] = {"type": "diffuse", "reflectance": {"type": "rgb", "value": BEAM_RGB}}
        elif mat == "breadboard":
            shape["bsdf"] = dict(MATERIALS[mat], base_color={"type": "rgb", "value": th["board"]})
        else:
            shape["bsdf"] = MATERIALS[mat]
        scene[f"shape_{mat}"] = shape

    img = mi.render(mi.load_dict(scene))
    bmp = mi.Bitmap(img).convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True)
    bmp.write(out_png)
    print("wrote", out_png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("layout")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--spp", type=int, default=256)
    ap.add_argument("--size", default="1600x1000")
    ap.add_argument("--beam-height", type=float, default=50.8)
    ap.add_argument("--theme", choices=sorted(THEMES), default="light")
    a = ap.parse_args()
    out = a.out or str(Path(a.layout).with_suffix(".png")).replace(".png", "_3d.png")
    w, h = (int(s) for s in a.size.split("x"))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    render(a.layout, out, a.spp, (w, h), a.beam_height, step_out=str(Path(out).with_suffix(".step")), theme=a.theme)


if __name__ == "__main__":
    main()
