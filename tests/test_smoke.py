"""Headless smoke test: load, edit, undo/redo, save round-trip, export."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from optolayout.app import MainWindow, export_scene  # noqa: E402
from optolayout.model import Component, Layout  # noqa: E402
from optolayout.scene import AddComponentCmd, DeleteCmd, SetFieldsCmd  # noqa: E402


def test_all(out_dir=None):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    import shutil
    work = Path(tempfile.mkdtemp())
    demo = work / "demo_399nm.json"
    shutil.copy(ROOT / "examples" / "demo_399nm.json", demo)  # don't touch the example's logbook
    w = MainWindow(str(demo))
    sc = w.scene
    n_c, n_b = len(sc.layout.components), len(sc.layout.beams)

    sc.undo.push(AddComponentCmd(sc, Component(id="cx", type="lens_1in", x=100, y=100)))
    assert "cx" in sc.layout.components and "cx" in sc.comp_items
    sc.undo.push(SetFieldsCmd(sc, {"m1": ({"angle": sc.layout.components["m1"].angle}, {"angle": 10.0})}, "rot"))
    assert sc.layout.components["m1"].angle == 10.0
    n_pbs = len(sc.layout.beams_touching("pbs1"))
    sc.undo.push(DeleteCmd(sc, ["pbs1"], []))
    assert "pbs1" not in sc.layout.components
    assert len(sc.layout.beams) == n_b - n_pbs
    for _ in range(3):
        sc.undo.undo()
    assert len(sc.layout.components) == n_c and len(sc.layout.beams) == n_b
    assert sc.layout.components["m1"].angle != 10.0
    sc.undo.redo()
    assert "cx" in sc.layout.components
    sc.undo.undo()

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "rt.json"
        sc.layout.save(p)
        again = Layout.load(p)
        assert again.to_dict() == sc.layout.to_dict()

    out = Path(out_dir or tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    export_scene(sc, str(out / "demo_399nm.png"))
    export_scene(sc, str(out / "demo_399nm.svg"))
    assert (out / "demo_399nm.png").stat().st_size > 1000
    assert (out / "demo_399nm.svg").stat().st_size > 1000
    print("ok", out)


if __name__ == "__main__":
    test_all(sys.argv[1] if len(sys.argv) > 1 else None)
