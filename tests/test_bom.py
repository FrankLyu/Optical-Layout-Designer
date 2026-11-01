"""Default part numbers and the bill of materials."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from optolayout.app import MainWindow  # noqa: E402
from optolayout.bom import bill_of_materials, write_bom_csv  # noqa: E402
from optolayout.mounts3d import MODELS  # noqa: E402
from optolayout.schematic import SchSetFieldsCmd  # noqa: E402


def test_bom():
    app = QApplication.instance() or QApplication([])
    assert app is not None
    work = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "examples" / "demo_399nm.json", work / "demo.json")
    w = MainWindow(str(work / "demo.json"))
    lay = w.scene.layout
    rows = bill_of_materials(lay)
    by_pn = {r.part_number: r for r in rows}
    # every part is counted once in the optics section
    assert sum(r.qty for r in rows if r.section == "Optics & mounts") == len(lay.schematic.elements)
    # one post and fork per part the 3D model stands on a post
    n_posts = sum(1 for c in lay.components.values() if c.type in MODELS and MODELS[c.type].post)
    assert by_pn["CF125"].qty == n_posts
    assert sum(r.qty for r in rows if r.part_number.startswith("Ø1\" pedestal post")) == n_posts
    assert by_pn["HCA3"].qty == sum(1 for c in lay.components.values() if c.type == "fiber")

    # picking a Thorlabs 1" mirror fills in KM100; a typed number overrides it and survives a part change
    sp = w.sch_page.props
    el = next(e for e in lay.schematic.elements.values() if e.kind == "mirror")
    w.sch_scene.clearSelection()
    w.sch_scene.el_items[el.id].setSelected(True)
    i = sp.part.findData("mirror_1in")
    sp.part.setCurrentIndex(i)
    sp._part_changed(i)
    assert el.part == "mirror_1in" and el.part_number == "" and sp.part_number.text() == "KM100"
    assert lay.component_for(el.id).part_number == "KM100"
    sp.part_number.setText("POLARIS-K1")
    sp._pn_changed()
    assert el.part_number == "POLARIS-K1"
    sp.part_number.setText("KM100")  # typing the default back stores "use the default"
    sp._pn_changed()
    assert el.part_number == ""
    i = sp.part.findData("mirror_half_in")
    sp.part.setCurrentIndex(i)
    sp._part_changed(i)
    assert sp.part_number.text() == "KM05"
    w.scene.undo.push(SchSetFieldsCmd(w.sch_scene, {el.id: ({"part_number": ""}, {"part_number": "X1"})}, "pn"))
    assert any(r.part_number == "X1" for r in bill_of_materials(lay))

    # the dialog asked when a part is placed: size/mount brings its default part number
    from optolayout.model import SchElement
    from optolayout.schematic import NewPartDialog
    new = SchElement(id="s_new", kind="hwp", label=lay.schematic.next_label("hwp"))
    dlg = NewPartDialog(new, lay.schematic)
    assert dlg.part_number.text() == "RSP1" and dlg.ok.isEnabled()
    dlg.part.setCurrentIndex(dlg.part.findData("hwp_half"))
    assert dlg.part_number.text() == "RSP05"
    dlg.notes.setPlainText("for the 2D MOT")
    dlg.accept()
    assert (new.part, new.part_number, new.notes) == ("hwp_half", "", "for the 2D MOT")
    taken = next(iter(lay.schematic.elements.values())).label
    dlg = NewPartDialog(SchElement(id="s_x", kind="hwp", label=taken), lay.schematic)
    assert not dlg.ok.isEnabled(), "labels must be unique"

    w.show_bom()
    assert w._bom.table.rowCount() > len(rows) - 2
    write_bom_csv(rows, str(work / "bom.csv"))
    assert "CF125" in (work / "bom.csv").read_text(encoding="utf-8")
    print("ok")


if __name__ == "__main__":
    test_bom()
