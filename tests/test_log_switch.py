"""Power log: opening never writes, missing log prompt; the layout drop-down."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from optolayout.app import MainWindow  # noqa: E402
from optolayout.logbook import Logbook  # noqa: E402
from optolayout.scene import SetFieldsCmd  # noqa: E402
from optolayout.switcher import BROWSE, layouts_in  # noqa: E402

EX = ROOT / "examples"


def _digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_lazy_logbook():
    p = Path(tempfile.mkdtemp()) / "x.logbook.sqlite"
    lb = Logbook(p)
    lb.register_point("mp_a", "P1")
    assert not p.exists() and lb.in_memory  # nothing on disk yet
    assert lb.latest_two() == {} and lb.power_history("mp_a") == [] and lb.known_points() == [("mp_a", "P1")]
    lb.add_power("mp_a", 2.0)
    assert p.exists() and not lb.in_memory
    lb.close()
    again = Logbook(p)
    assert again.known_points() == [("mp_a", "P1")] and again.power_history("mp_a")[0].power_mw == 2.0
    again.close()


def test_open_does_not_write():
    app = QApplication.instance() or QApplication([])
    tmp = Path(tempfile.mkdtemp())
    for f in ("demo_399nm.json", "demo_399nm.logbook.sqlite"):
        shutil.copy(EX / f, tmp / f)
    log = tmp / "demo_399nm.logbook.sqlite"
    before = _digest(log)
    w = MainWindow(str(tmp / "demo_399nm.json"))
    pid = next(iter(w.scene.layout.points))
    w.open_point_log(pid)  # the log window
    w.refresh_measurements()
    w.save_file()  # saving the layout leaves the log alone too
    app.processEvents()
    assert _digest(log) == before
    w._dialogs[pid].value.setValue(1.5)
    w._dialogs[pid]._add_reading()  # a reading does write (and the point labels with it)
    assert _digest(log) != before
    assert pid in dict(Logbook(log).known_points())
    w.close()


def test_missing_log():
    app = QApplication.instance() or QApplication([])
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(EX / "demo_399nm.json", tmp / "demo.json")
    log = tmp / "demo.logbook.sqlite"

    with mock.patch.object(MainWindow, "ask_missing_log", return_value="none") as ask:
        w = MainWindow(str(tmp / "demo.json"))
    assert ask.called and w.logbook is None and w._no_log and not log.exists()
    with mock.patch.object(QMessageBox, "information") as info:
        w.open_point_log(next(iter(w.scene.layout.points)))
    assert info.called and not w._dialogs and not log.exists()
    w.close()

    with mock.patch.object(MainWindow, "ask_missing_log", return_value="new"):
        w = MainWindow(str(tmp / "demo.json"))
    assert w.logbook is not None and w.logbook.in_memory and not log.exists()  # created at the first reading
    w.logbook.add_power(next(iter(w.scene.layout.points)), 3.0)
    assert log.exists()
    w.close()
    w.logbook.close()
    log.unlink()

    # pick the example's log: copied next to the layout
    pick = mock.patch.object(QFileDialog, "getOpenFileName", return_value=(str(EX / "demo_399nm.logbook.sqlite"), ""))
    with mock.patch.object(MainWindow, "ask_missing_log", return_value="choose"), pick, \
            mock.patch.object(MainWindow, "ask_copy_or_use", return_value="copy"):
        w = MainWindow(str(tmp / "demo.json"))
    assert log.exists() and w.logbook.path == log and "mp_3d" in w.scene.latest
    w.close()
    w.logbook.close()
    log.unlink()
    # ... or used where it is, without touching it
    ex_before = _digest(EX / "demo_399nm.logbook.sqlite")
    with mock.patch.object(MainWindow, "ask_missing_log", return_value="choose"), pick, \
            mock.patch.object(MainWindow, "ask_copy_or_use", return_value="use"):
        w = MainWindow(str(tmp / "demo.json"))
    assert not log.exists() and w.logbook.path == EX / "demo_399nm.logbook.sqlite" and "mp_3d" in w.scene.latest
    w.save_file()  # saving the layout keeps that log, doesn't swap in an empty one
    assert w.logbook.path == EX / "demo_399nm.logbook.sqlite" and _digest(EX / "demo_399nm.logbook.sqlite") == ex_before
    w.close()

    # a layout without points opens without asking
    shutil.copy(EX / "demo_schematic.json", tmp / "plain.json")
    with mock.patch.object(MainWindow, "ask_missing_log") as ask:
        w = MainWindow(str(tmp / "plain.json"))
    assert not ask.called and w.logbook is not None
    w.close()


def test_layout_switcher():
    app = QApplication.instance() or QApplication([])
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(EX / "demo_399nm.json", tmp / "demo.json")
    shutil.copy(EX / "demo_399nm.logbook.sqlite", tmp / "demo.logbook.sqlite")
    shutil.copy(EX / "small_board.json", tmp / "board_b.json")
    (tmp / "notes.json").write_text(json.dumps({"a": 1}), encoding="utf-8")  # not a layout
    (tmp / "broken.json").write_text("{", encoding="utf-8")
    assert [p.name for p in layouts_in(tmp)] == ["board_b.json", "demo.json"]

    w = MainWindow(str(tmp / "demo.json"))
    sw = w.switcher
    names = [sw.itemText(i) for i in range(sw.count())]
    assert names[:2] == ["board_b", "demo"] and names[-1] == BROWSE and sw.currentText() == "demo"

    # unsaved changes + Cancel: stay, and the drop-down shows demo again
    c = next(iter(w.scene.layout.components.values()))
    w.scene.undo.push(SetFieldsCmd(w.scene, {c.id: ({"x": c.x}, {"x": c.x + 1})}, "Move"))
    m = mock.Mock()
    m.exec.return_value = QMessageBox.Cancel
    with mock.patch.object(w, "save_prompt", return_value=m):
        sw._picked(sw.findData(str(tmp / "board_b.json")))
    assert w.path.name == "demo.json" and sw.currentText() == "demo"
    m.exec.return_value = QMessageBox.Discard
    with mock.patch.object(w, "save_prompt", return_value=m):
        sw._picked(sw.findData(str(tmp / "board_b.json")))
    assert w.path.name == "board_b.json" and sw.currentText() == "board_b"

    # new files show up when the list opens; Save As lists the new one
    shutil.copy(EX / "small_board.json", tmp / "c_new.json")
    sw.refresh()
    assert sw.findData(str(tmp / "c_new.json")) >= 0
    with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(tmp / "d_saved.json"), "")):
        w.save_as()
    assert sw.currentText() == "d_saved"
    # Browse… opens the usual Open dialog
    with mock.patch.object(w, "open_file") as op:
        sw._picked(sw.findData(BROWSE))
    assert op.called and sw.currentText() == "d_saved"
    w.close()


if __name__ == "__main__":
    test_lazy_logbook()
    test_open_does_not_write()
    test_missing_log()
    test_layout_switcher()
    print("ok")
