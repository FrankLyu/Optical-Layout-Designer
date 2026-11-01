"""Lab sheet: settings kept in the layout file, table / HTML / TSV / PDF output."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from optolayout.labsheet import (BLANK_HEADERS, LOG_HEADERS, LabSheetDialog, clipboard_mime, sheet_document,  # noqa: E402
                                 sheet_html, sheet_table, sheet_tsv, write_csv, write_pdf)
from optolayout.logbook import Logbook  # noqa: E402
from optolayout.model import LabSheet, Layout, MeasurementPoint  # noqa: E402


def test_settings_round_trip():
    lay = Layout()
    lay.points["mp_a"] = MeasurementPoint(id="mp_a", label="P1", beam_id=None)
    lay.lab_sheet = LabSheet(points=["mp_a"], names={"mp_a": "after AOM"}, include_log=False, history=3,
                             include_picture=False)
    d = lay.to_dict()
    assert d["lab_sheet"] == {"points": ["mp_a"], "names": {"mp_a": "after AOM"}, "include_log": False,
                              "history": 3, "include_picture": False}
    tmp = Path(tempfile.mkdtemp()) / "x.json"
    lay.save(tmp)
    back = Layout.load(tmp)
    assert back.lab_sheet == lay.lab_sheet and back.point_name("mp_a") == "after AOM"
    # older files have no lab_sheet key: defaults
    d.pop("lab_sheet")
    old = Layout.from_dict(json.loads(json.dumps(d)))
    assert old.lab_sheet == LabSheet() and old.lab_sheet.include_log and old.lab_sheet.include_picture
    assert old.lab_sheet.history == 1 and old.point_name("mp_a") == ""
    # odd values are tidied
    odd = Layout.from_dict({**d, "lab_sheet": {"names": {"mp_a": "  "}, "history": 0}})
    assert odd.lab_sheet.names == {} and odd.lab_sheet.history == 1


def _layout_with_log():
    lay = Layout()
    for i, pid in enumerate(("mp_a", "mp_b", "mp_c"), 1):
        lay.points[pid] = MeasurementPoint(id=pid, label=f"P{i}", beam_id=None)
    lay.points["mp_c"].archived = True
    lb = Logbook(Path(tempfile.mkdtemp()) / "t.logbook.sqlite")
    lb.add_power("mp_a", 1.0, measured_at="2026-10-01T10:00:00", instrument="S120C")
    wrong = lb.add_power("mp_a", 99.0, measured_at="2026-10-02T10:00:00")
    lb.add_power("mp_a", 2.5, measured_at="2026-10-02T10:05:00", supersedes=wrong, notes="fixed <typo>")
    lb.add_power("mp_a", 500, "µW", measured_at="2026-10-03T09:00:00", instrument="S120C", notes="after\tclean")
    return lay, lb


def test_table_html_tsv():
    lay, lb = _layout_with_log()
    lay.lab_sheet.names = {"mp_a": "after AOM", "mp_b": "fiber <in>"}
    s = LabSheet(points=["mp_b", "mp_a", "mp_c"], names=lay.lab_sheet.names, history=1)
    headers, rows = sheet_table(lay, lb, s)
    assert headers == LOG_HEADERS
    # P1 first, archived P3 left out, one reading per point, P2 has none
    assert [r[:3] for r in rows] == [["after AOM", "P1", "0.5"], ["fiber <in>", "P2", ""]]
    assert rows[0][3:] == ["S120C", "2026-10-03 09:00", "after\tclean"] and rows[1][5] == "no readings"
    s.history = 3  # newest first, the superseded reading left out
    _h, rows = sheet_table(lay, lb, s)
    assert [r[2] for r in rows if r[1] == "P1"] == ["0.5", "2.5", "1"]
    s.include_log = False
    headers, rows = sheet_table(lay, lb, s)
    assert headers == BLANK_HEADERS and rows == [["after AOM", "P1", "", ""], ["fiber <in>", "P2", "", ""]]
    assert sheet_table(lay, None, LabSheet(points=["mp_a"]))[1][0][5] == "no readings"  # no logbook yet

    s.include_log, s.history = True, 1
    headers, rows = sheet_table(lay, lb, s)
    img = QImage(300, 150, QImage.Format_ARGB32)
    img.fill(Qt.white)
    md = clipboard_mime("Lab sheet: x.json", "today", headers, rows, img)
    h = md.html()
    assert "<table border='1'" in h and h.count("<tr>") == 3 and "<th" in h
    assert "fiber &lt;in&gt;" in h and "data:image/png;base64,iVBOR" in h and "width='640'" in h
    assert md.hasImage() and md.hasText()
    tsv = md.text()
    lines = tsv.rstrip("\r\n").split("\r\n")
    assert lines[0] == "\t".join(LOG_HEADERS) and len(lines) == 3
    assert all(len(ln.split("\t")) == len(LOG_HEADERS) for ln in lines)  # the tab in a note does not split a cell
    assert "after clean" in lines[1]
    assert "<img" not in sheet_html("t", "s", headers, rows) and sheet_tsv(headers, []) == "\t".join(headers) + "\r\n"

    # PDF and CSV
    app = QApplication.instance() or QApplication([])
    assert app is not None
    out = Path(tempfile.mkdtemp())
    write_pdf(sheet_document("Lab sheet", "today", headers, rows, img), str(out / "s.pdf"))
    assert (out / "s.pdf").read_bytes()[:5] == b"%PDF-" and (out / "s.pdf").stat().st_size > 1000
    write_csv(headers, rows, str(out / "s.csv"))
    assert (out / "s.csv").read_text(encoding="utf-8-sig").splitlines()[0] == ",".join(LOG_HEADERS)
    lb.close()


def test_dialog_in_app():
    app = QApplication.instance() or QApplication([])
    from optolayout.app import MainWindow
    tmp = Path(tempfile.mkdtemp())
    for f in ("demo_399nm.json", "demo_399nm.logbook.sqlite"):
        shutil.copy(ROOT / "examples" / f, tmp / f)
    w = MainWindow(str(tmp / "demo_399nm.json"))
    lay = w.scene.layout
    assert w.scene.undo.isClean() and lay.lab_sheet == LabSheet()
    assert w.a_sheet.shortcut().toString() == "Ctrl+P" and w.a_sheet.iconText() == "Sheet"
    assert w.a_select.iconText() == "Select" and "Select / move" in w.a_select.toolTip()

    pics = []
    dlg = LabSheetDialog(lay, w.logbook, "demo_399nm.json", lambda: pics.append(1) or QImage(), w.store_lab_sheet, w)
    n = dlg.table.rowCount()
    assert n == len([p for p in lay.points.values() if not p.archived])
    for i in range(n):
        assert dlg.table.item(i, 0).checkState() == Qt.Unchecked
    dlg.table.item(0, 0).setCheckState(Qt.Checked)
    dlg.table.item(0, 1).setText("after AOM")
    pid = dlg.table.item(0, 0).data(Qt.UserRole)
    dlg.history.setValue(2)
    dlg.include_picture.setChecked(False)
    dlg.copy_sheet()
    assert not pics  # no picture asked for, none rendered
    assert "after AOM" in QApplication.clipboard().mimeData().html()
    dlg.close()
    assert not w.scene.undo.isClean()  # settings are a change to the layout
    assert lay.lab_sheet.points == [pid] and lay.lab_sheet.history == 2 and not lay.lab_sheet.include_picture
    assert w.scene.point_items[pid]._texts()[0].endswith("· after AOM")
    w.scene.undo.undo()
    assert w.scene.layout.lab_sheet == LabSheet() and "·" not in w.scene.point_items[pid]._texts()[0]
    w.scene.undo.redo()

    w.save_file()
    w2 = MainWindow(str(tmp / "demo_399nm.json"))
    s2 = w2.scene.layout.lab_sheet
    assert s2.points == [pid] and s2.names == {pid: "after AOM"} and s2.history == 2
    dlg2 = LabSheetDialog(w2.scene.layout, w2.logbook, "x", QImage, w2.store_lab_sheet, w2)
    checked = [dlg2.table.item(i, 0).data(Qt.UserRole) for i in range(dlg2.table.rowCount())
               if dlg2.table.item(i, 0).checkState() == Qt.Checked]
    assert checked == [pid] and dlg2.table.item(0, 1).text() == "after AOM"
    dlg2.close()
    assert w2.scene.undo.isClean()  # nothing changed: the file is not marked modified

    # the real layout picture renders
    from optolayout.app import render_scene_image
    img = render_scene_image(w2.scene, 800)
    assert not img.isNull() and img.width() == 800
    for win in (w, w2):
        win.scene.undo.setClean()
        win.close()
    QApplication.clipboard().clear()  # offscreen Qt crashes at exit if the sheet is still on its clipboard


if __name__ == "__main__":
    test_settings_round_trip()
    test_table_html_tsv()
    test_dialog_in_app()
    print("ok")
