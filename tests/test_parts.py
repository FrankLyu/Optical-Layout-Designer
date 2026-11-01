"""New toolbox parts: SR475 shutter, lens in LMR1 / cage plate CP33, and a
beam entering at the table edge (a marker, not a physical part)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from optolayout.app import MainWindow, export_scene  # noqa: E402
from optolayout.bom import bill_of_materials  # noqa: E402
from optolayout.model import Layout, SchElement, SchLink, Table  # noqa: E402


def make_board(path):
    lay = Layout(table=Table(name="New parts", width=609.6, height=457.2))
    sch = lay.schematic

    def el(eid, kind, x, y, part="", label=None):
        sch.elements[eid] = SchElement(id=eid, kind=kind, x=x, y=y, part=part, label=label or sch.next_label(kind))

    el("in", "laser", 0, 0, "beam_entry", "From 2nd table")
    el("sh", "shutter", 80, 0)
    el("l1", "lens", 160, 0, "lens_lmr1")
    el("l2", "lens", 240, 0, "lens_1in")
    el("m", "mirror", 320, 0, "mirror_newport_half")
    el("fc", "fiber", 320, 120)
    ids = ["in", "sh", "l1", "l2", "m", "fc"]
    for a, b in zip(ids, ids[1:]):
        sch.links[f"k_{a}_{b}"] = SchLink(id=f"k_{a}_{b}", source=a, target=b, color="#b77fd0", wavelength_nm=399.0)
    lay.save(path)


def test_parts(out_dir=None):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    work = Path(tempfile.mkdtemp())
    make_board(work / "parts.json")
    w = MainWindow(str(work / "parts.json"))
    lay = w.scene.layout
    types = {lay.component_for(e).type for e in lay.schematic.elements}
    assert {"beam_entry", "shutter", "lens_lmr1", "lens_1in"} <= types
    pns = {lay.component_for(e).part_number for e in lay.schematic.elements}
    assert {"SR475", "LMR1", "CP33", "M05"} <= pns
    # the shutter is aimed along the beam like other inline optics
    sh = lay.component_for("sh")
    assert abs(sh.angle) < 1e-6 or abs(sh.angle - 360) < 1e-6, sh.angle
    # the beam entry is a marker: no BOM line, never an overlap
    rows = bill_of_materials(lay)
    assert not any("table edge" in r.description for r in rows)
    assert any(r.part_number == "SR475" for r in rows)
    entry = lay.component_for("in")
    entry.x, entry.y = sh.x, sh.y  # even on top of another part
    w.scene.check_clashes()
    assert entry.id not in w.scene.clashes
    # a lens can be switched between the two mounts and keeps working
    w.sch_scene.set_fields("l1", {"part": "lens_1in"})
    assert lay.component_for("l1").type == "lens_1in" and lay.component_for("l1").part_number == "CP33"
    w.sch_scene.set_fields("in", {"part": "laser"})
    assert lay.component_for("in").type == "laser"
    if out_dir:
        w.sch_scene.set_fields("l1", {"part": "lens_lmr1"})
        w.sch_scene.set_fields("in", {"part": "beam_entry"})
        entry.x, entry.y = 0, sh.y
        w.scene.set_fields(entry.id, {"x": 0.0})
        export_scene(w.scene, str(Path(out_dir) / "parts_layout.png"), 6)
        export_scene(w.sch_scene, str(Path(out_dir) / "parts_schematic.png"), 4)
    print("ok")


if __name__ == "__main__":
    test_parts(sys.argv[1] if len(sys.argv) > 1 else None)
