"""3D view: the scene builds from a layout (board with cut-outs, parts, posts, beams)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_view3d():
    try:
        import pyvista as pv
    except ImportError:
        print("skipped: pyvista not installed")
        return
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    assert app is not None
    from optolayout.model import Layout
    from optolayout.view3d import _board_rects, hole_positions, part_model, populate

    lay = Layout.load(ROOT / "examples" / "small_board.json")
    t = lay.table
    rects = _board_rects(t)
    area = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in rects)
    cut = sum(c[2] * c[3] for c in t.cutouts)
    assert abs(area - (t.width * t.height - cut)) < 1e-6
    holes = hole_positions(lay)
    assert holes and all(t.on_board(x, y) for x, y in holes)
    # every part type has a model
    from optolayout.symbols import SYMBOLS
    for typ in SYMBOLS:
        assert part_model(typ, 50.8), typ
    p = pv.Plotter(off_screen=True)
    actors = populate(p, lay, 50.8)
    assert len(actors) == len(lay.components)
    assert all(f"beam_{b}" in p.actors for b in lay.beams)
    p.close()
    print("ok")


def test_without_cad():
    """With no meshes installed (a fresh download) every board still builds, from simple shapes."""
    try:
        import pyvista as pv
    except ImportError:
        print("skipped: pyvista not installed")
        return
    import tempfile

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    assert app is not None
    from optolayout import view3d
    from optolayout.model import Layout
    from optolayout.symbols import SYMBOLS

    saved = view3d.MESH_DIR, dict(view3d._mesh_cache)
    view3d.MESH_DIR = Path(tempfile.mkdtemp())
    view3d._mesh_cache.clear()
    try:
        for typ in SYMBOLS:
            pieces = view3d.part_model(typ, 50.8)
            assert pieces, typ
            if typ in view3d.MODELS and view3d.MODELS[typ].step:  # has a real model, so has its own stand-in too
                assert pieces[0][1] != "#888888", typ
        for name in ("small_board", "lightflow_board", "pyopticl_board", "demo_399nm"):
            lay = Layout.load(ROOT / "examples" / f"{name}.json")
            p = pv.Plotter(off_screen=True)
            assert len(view3d.populate(p, lay, 50.8)) > 0, name
            p.close()
        assert view3d.MISSING_MESHES
    finally:
        view3d.MESH_DIR = saved[0]
        view3d._mesh_cache.clear()
        view3d._mesh_cache.update(saved[1])
        view3d.MISSING_MESHES.clear()
    print("ok")


if __name__ == "__main__":
    test_view3d()
    test_without_cad()
