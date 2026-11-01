"""LightFlow optical circuit board: 1" beam, pedestals, drilled holes, BOM and 3D."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_lightflow():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    assert app is not None
    from optolayout.app import MainWindow
    from optolayout.bom import bill_of_materials
    from optolayout.mounts3d import DOWEL_D, SCREW_D, drilled_holes, mount_block, optic_height

    work = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "examples" / "lightflow_board.json", work / "l.json")
    w = MainWindow(str(work / "l.json"))
    lay, sc = w.scene.layout, w.scene
    t = lay.table
    assert t.style == "lightflow" and not t.grid_holes and not sc.clashes
    assert all(optic_height(c.type, t.style) == 25.4 for c in lay.components.values())
    # a Polaris K05S1 stands on the lab's 10.2 x 25 x 12.7 mm pedestal: one 8-32 under the mount's tapped
    # hole (8 mm behind the mirror) and two M2 dowels across the beam
    m = next(c for c in lay.components.values() if c.type == "mirror_polaris_half")
    b = mount_block(m.type, t.style)
    assert abs(b.z1 - 12.7) < 1e-6 and b.z0 == 0
    assert abs(b.x1 - b.x0 - 10.2) < 1e-6 and abs(b.y1 - b.y0 - 25.0) < 1e-6
    holes = drilled_holes(m.type, t.style, 0.0, 0.0, 0.0)
    assert [h[2] for h in holes] == [SCREW_D, DOWEL_D, DOWEL_D] and abs(holes[0][0] + 8.02) < 1e-6
    # the lab's RSP05 pedestal: 8-32s 26 mm apart across the beam, top under the mount's base
    hwp = next(c for c in lay.components.values() if c.type == "hwp_half")
    (x0, y0, _), (x1, y1, _) = drilled_holes(hwp.type, t.style, hwp.x, hwp.y, hwp.angle)
    assert abs(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 - 26.0) < 1e-6
    assert sc.comp_items[hwp.id].outline().boundingRect().height() > 35

    rows = bill_of_materials(lay)
    by_pn = {r.part_number: r for r in rows}
    assert not any(r.section == "Posts & clamps" for r in rows)
    assert by_pn["1/4\"-20 x 3/4\" cap screw"].qty == len(sc.table_screw_holes()) >= 4
    assert any(r.part_number.startswith("Optical circuit board ") for r in rows)
    # one pedestal per part, except the D mirror (its column is part of its CAD)
    assert sum(r.qty for r in rows if r.part_number.startswith("Pedestal ")) == sum(
        1 for c in lay.components.values() if c.type != "mirror_d")
    dm = next(c for c in lay.components.values() if c.type == "mirror_d")
    assert mount_block(dm.type, t.style) is None and len(drilled_holes(dm.type, t.style, 0, 0, 0)) == 3

    try:
        import pyvista as pv
    except ImportError:
        print("3D skipped: pyvista not installed")
        return
    from optolayout.view3d import board_thickness, populate
    assert board_thickness(t) == 12.7
    from optolayout.mounts3d import mount_boxes
    assert len(mount_boxes("iris", t.style)) == 2  # the lab's iris column and its foot
    p = pv.Plotter(off_screen=True)
    populate(p, lay, 25.4)
    assert "adapters" in p.actors and "posts" not in p.actors
    p.close()
    print("ok")


if __name__ == "__main__":
    test_lightflow()
