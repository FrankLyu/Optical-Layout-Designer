"""PyOpticL ion-trap baseplate: board type, 2D holes, overlap check, BOM and 3D."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_pyopticl():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    assert app is not None
    from optolayout.app import MainWindow, hole_text
    from optolayout.bom import bill_of_materials
    from optolayout.model import Table
    from optolayout.mounts3d import PYOPTICL_BEAM_HEIGHT, drilled_holes, optic_height

    # switching board types puts back what the old one set
    t = Table()
    t.apply_style("olego")
    t.apply_style("pyopticl")
    assert not t.grid_holes and t.edge_margin == 0 and not t.center_holes
    t.apply_style("grid")
    assert t.grid_holes

    work = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "examples" / "pyopticl_board.json", work / "p.json")
    w = MainWindow(str(work / "p.json"))
    lay, sc = w.scene.layout, w.scene
    t = lay.table
    assert t.style == "pyopticl" and not sc.clashes
    assert hole_text(t, 12.7, 12.7) == "grid point A1"
    assert all(optic_height(c.type, t.style) == PYOPTICL_BEAM_HEIGHT for c in lay.components.values())
    # an RSP05 sits on a surface adapter: two 8-32s across the beam, 25 mm apart; the adapter counts for overlaps
    hwp = next(c for c in lay.components.values() if c.type == "hwp_half")
    (x0, y0, _d0), (x1, y1, _d1) = drilled_holes(hwp.type, t.style, hwp.x, hwp.y, hwp.angle)
    assert abs(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 - 25.0) < 1e-6
    assert sc.comp_items[hwp.id].outline().boundingRect().height() > 36
    # table screws on the 1" grid, clear of the parts
    holes = sc.table_screw_holes()
    assert len(holes) >= 4
    assert all(abs((v - 12.7) / 25.4 - round((v - 12.7) / 25.4)) < 1e-6 for h in holes for v in h)

    rows = bill_of_materials(lay)
    by_pn = {r.part_number: r for r in rows}
    assert not any(r.section == "Posts & clamps" for r in rows)  # no posts on a baseplate
    assert by_pn["1/4\"-20 x 1-1/4\" cap screw"].qty == len(holes)
    assert sum(r.qty for r in rows if r.part_number.startswith("Surface adapter")) == 3  # 2 RSP05 + the cube
    assert any(r.part_number.startswith("Baseplate ") for r in rows)

    try:
        import pyvista as pv
    except ImportError:
        print("3D skipped: pyvista not installed")
        return
    from optolayout.view3d import populate
    p = pv.Plotter(off_screen=True)
    populate(p, lay, PYOPTICL_BEAM_HEIGHT)
    assert "adapters" in p.actors and "pockets" in p.actors and "posts" not in p.actors
    p.close()
    print("ok")


if __name__ == "__main__":
    test_pyopticl()
