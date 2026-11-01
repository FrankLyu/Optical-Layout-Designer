"""Power logger: append-only logbook, archiving on beam delete, log window."""
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402

from optolayout.app import MainWindow, export_scene  # noqa: E402
from optolayout.scene import DeleteCmd, SetFieldsCmd  # noqa: E402


def test_logger(out_dir=None):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    tmp = Path(tempfile.mkdtemp())
    for f in ("demo_399nm.json", "demo_399nm.logbook.sqlite"):
        shutil.copy(ROOT / "examples" / f, tmp / f)
    w = MainWindow(str(tmp / "demo_399nm.json"))
    sc, lb = w.scene, w.logbook
    assert lb is not None and lb.path.name == "demo_399nm.logbook.sqlite"

    # latest readings reach the markers and the overview
    assert "mp_3d" in sc.latest and sc.point_items["mp_3d"]._texts()[1].endswith("mW")
    assert w.points_panel.table.rowCount() == 5

    # append-only at the database level
    try:
        lb.db.execute("DELETE FROM power")
        raise AssertionError("delete should be refused")
    except sqlite3.DatabaseError:
        pass
    lb.db.rollback()

    # unit conversion
    rid = lb.add_power("mp_probe", 850, "µW", notes="unit test")
    assert abs(lb.power_history("mp_probe")[-1].power_mw - 0.85) < 1e-12 and rid > 0

    # moving a part moves the marker but keeps the same point id
    pt = sc.layout.points["mp_dp"]
    x0 = sc.layout.point_xy(pt)
    c = sc.layout.components["l1"]
    sc.undo.push(SetFieldsCmd(sc, {"l1": ({"y": c.y}, {"y": c.y + 25.4})}, "move"))
    assert sc.layout.point_xy(pt) != x0 and pt.id == "mp_dp"

    # deleting the AOM removes its beams; the point on them is archived, not lost
    n_before = len(lb.power_history("mp_dp"))
    sc.undo.push(DeleteCmd(sc, ["aom1"], []))
    assert sc.layout.points["mp_dp"].archived and sc.layout.points["mp_dp"].beam_id is None
    assert "mp_dp" not in sc.point_items  # hidden on the table by default
    sc.set_show_archived(True)
    assert "mp_dp" in sc.point_items
    sc.set_show_archived(False)
    assert len(lb.power_history("mp_dp")) == n_before
    sc.undo.undo()
    assert not sc.layout.points["mp_dp"].archived and sc.layout.points["mp_dp"].beam_id == "b_aom1_l1"

    # deleting a point directly also archives it
    sc.point_items["mp_2d"].setSelected(True)
    w.delete_selected()
    assert sc.layout.points["mp_2d"].archived
    sc.undo.undo()

    # add a point on a beam (midpoint), then a second one lands where clicked
    p_new = w.add_point_on("b_pbs2_m5")
    assert p_new.t == 0.5 and p_new.label == "P6"
    line = sc.beam_items["b_pbs2_m5"].line()
    p2 = w.add_point_on("b_pbs2_m5", line.pointAt(0.25))
    assert abs(p2.t - 0.25) < 1e-6

    # log window: add a reading and a picture
    w.open_point_log("mp_3d")
    dlg = w._dialogs["mp_3d"]
    n = dlg.table.rowCount()
    dlg.value.setValue(13.2)
    dlg.notes.setText("from test")
    dlg._add_reading()
    assert dlg.table.rowCount() == n + 1
    img = QImage(64, 48, QImage.Format_RGB32)
    img.fill(QColor("#336699"))
    k = dlg.pics.count()
    dlg.add_image(img)
    assert dlg.pics.count() == k + 1
    assert abs(sc.latest["mp_3d"][0].power_mw - 13.2) < 1e-9

    # deleting a reading hides it everywhere; Show deleted brings it back
    from unittest import mock
    from PySide6.QtWidgets import QMessageBox
    dlg.table.selectRow(dlg.table.rowCount() - 1)
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        dlg._delete_selected("power")
    assert dlg.table.rowCount() == n and len(lb.power_history("mp_3d")) == n
    assert abs(sc.latest["mp_3d"][0].power_mw - 13.2) > 1e-9  # the label went back to the previous reading
    dlg.show_deleted.setChecked(True)
    assert dlg.table.rowCount() == n + 1 and "(deleted)" in dlg.table.item(n, 3).text()
    dlg.table.selectRow(n)
    dlg._restore_selected("power")
    assert len(lb.power_history("mp_3d")) == n + 1 and abs(sc.latest["mp_3d"][0].power_mw - 13.2) < 1e-9
    dlg.show_deleted.setChecked(False)
    dlg.pics.setCurrentRow(0)  # newest picture first
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        dlg._delete_selected("picture")
    assert dlg.pics.count() == k
    dlg.pic_show_deleted.setChecked(True)
    dlg.pics.item(0).setSelected(True)
    dlg._restore_selected("picture")
    dlg.pic_show_deleted.setChecked(False)
    assert dlg.pics.count() == k + 1

    # save and reload: points and history survive
    w.save_file()
    w2 = MainWindow(str(tmp / "demo_399nm.json"))
    assert set(w2.scene.layout.points) == set(sc.layout.points)
    assert len(w2.logbook.power_history("mp_3d")) == n + 1

    out = Path(out_dir or tmp)
    export_scene(sc, str(out / "demo_399nm_logger.png"))
    dlg.grab().save(str(out / "log_window_power.png"))
    tabs = dlg.findChildren(QTabWidget)[0]
    tabs.setCurrentIndex(1)
    dlg.grab().save(str(out / "log_window_pictures.png"))
    w.grab().save(str(out / "main_window.png"))
    for win in (w, w2):
        win.scene.undo.setClean()
        win.close()
    print("ok", out)


if __name__ == "__main__":
    test_logger(sys.argv[1] if len(sys.argv) > 1 else None)
