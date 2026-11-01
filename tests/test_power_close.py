"""Power tool (one point at a time) and the Word-style save prompt."""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from optolayout.app import MODE_POINT, MODE_SELECT, MainWindow  # noqa: E402
from optolayout.scene import SetFieldsCmd  # noqa: E402


def _window():
    app = QApplication.instance() or QApplication([])
    work = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "examples" / "demo_399nm.json", work / "demo.json")
    w = MainWindow(str(work / "demo.json"))
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    return app, w


def test_power_tool_one_shot():
    app, w = _window()
    assert w.a_point.iconText() == "Power" and "Power point" in w.a_point.toolTip()
    assert w.a_point.shortcut().toString() == "M"
    lay = w.scene.layout
    v = w.view
    b = max(lay.beams.values(), key=lay.beam_length)
    line = w.scene.beam_items[b.id].line()
    v.centerOn(line.pointAt(0.4))
    app.processEvents()

    def click(t, mods=Qt.NoModifier):
        QTest.mouseClick(v.viewport(), Qt.LeftButton, mods, v.mapFromScene(line.pointAt(t)))
        app.processEvents()

    n = len(lay.points)
    w.set_mode(MODE_POINT)
    click(0.4, Qt.ShiftModifier)  # Shift: keep the tool for another point
    assert len(lay.points) == n + 1 and w.mode == MODE_POINT and w.a_point.isChecked()
    click(0.3)  # a plain click places one and goes back to Select
    assert len(lay.points) == n + 2 and w.mode == MODE_SELECT and w.a_select.isChecked()
    w.set_mode(MODE_POINT)
    esc = next(a for a in w.actions() if a.shortcut().toString() == "Esc")
    esc.trigger()  # Esc still cancels
    assert w.mode == MODE_SELECT and len(lay.points) == n + 2
    w.scene.undo.setClean()
    w.close()


def test_save_prompt():
    app, w = _window()
    box = w.save_prompt()
    assert box.text() == "Do you want to save changes to demo.json?"
    assert box.button(QMessageBox.Discard).text() == "Don't Save"
    assert box.defaultButton() is box.button(QMessageBox.Save)
    assert box.escapeButton() is box.button(QMessageBox.Cancel)

    def edit():
        c = next(iter(w.scene.layout.components.values()))
        w.scene.undo.push(SetFieldsCmd(w.scene, {c.id: ({"x": c.x}, {"x": c.x + 1})}, "Move"))
        assert not w.scene.undo.isClean()

    def answer(r):
        m = mock.Mock()
        m.exec.return_value = r
        return mock.patch.object(w, "save_prompt", return_value=m)

    assert w._confirm_discard()  # nothing changed: no question
    edit()
    with answer(QMessageBox.Cancel):
        assert not w.close() and w.isVisible()  # Cancel keeps the window
    with answer(QMessageBox.Save):
        assert w._confirm_discard() and w.scene.undo.isClean()  # Save saves
    saved = w.path.read_text(encoding="utf-8")
    edit()
    with answer(QMessageBox.Discard):
        assert w._confirm_discard()  # Don't Save: go on, file untouched
    assert w.path.read_text(encoding="utf-8") == saved
    # untitled: Save opens Save As; cancelling it keeps the window open
    w.path = None
    with answer(QMessageBox.Save), mock.patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
        assert not w._confirm_discard() and not w.scene.undo.isClean()
    # New uses the same prompt
    with answer(QMessageBox.Cancel):
        w.new_file()
    assert w.scene.layout.components
    with answer(QMessageBox.Discard):
        assert w.close()
    app.processEvents()


if __name__ == "__main__":
    test_power_tool_one_shot()
    test_save_prompt()
    print("ok")
