"""Hole coordinates, the ruler, beam lengths and the optical path between parts."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from optolayout.app import MODE_RULER, MainWindow  # noqa: E402
from optolayout.model import Table  # noqa: E402


def test_holes():
    t = Table(width=914.4, height=609.6)
    assert t.columns() == 36 and t.rows() == 24
    assert Table.column_name(0) == "A" and Table.column_name(25) == "Z" and Table.column_name(26) == "AA"
    assert t.hole_at(12.7, 12.7) == ("A1", 0.0, 0.0)
    name, dx, dy = t.hole_at(12.7 + 2 * 25.4 + 3, 12.7 + 6 * 25.4)
    assert name == "C7" and abs(dx - 3) < 1e-9 and abs(dy) < 1e-9
    assert t.hole_at(-5, 10) is None
    # board types
    o = Table(width=228.6, height=457.2)
    o.apply_style("olego")
    assert (o.hole_pitch, o.center_holes, o.hole_diameter) == (12.7, True, 2.8)
    assert o.hole_at(6.35, 6.35)[0] == "A1"
    o.apply_style("predrilled")
    assert o.hole_at(6.35, 6.35) is None and o.on_board(6.35, 6.35)
    # irregular board: no holes in a cut-out
    t.cutouts = [[457.2, 304.8, 457.2, 304.8]]
    assert t.hole_at(600, 400) is None and t.hole_at(100, 400) is not None and not t.on_board(600, 400)


def test_measure():
    app = QApplication.instance() or QApplication([])
    work = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "examples" / "demo_399nm.json", work / "demo.json")
    w = MainWindow(str(work / "demo.json"))
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    lay = w.scene.layout
    by_label = {c.label: c for c in lay.components.values()}

    # optical path along the beams, either way round
    m1, pbs2 = by_label["M1"], by_label["PBS2"]
    L, ids = lay.optical_path(m1.id, pbs2.id)
    assert ids[0] == m1.id and ids[-1] == pbs2.id and len(ids) > 2
    assert abs(L - sum(lay.beam_length(b) for b in lay.beams.values()
                       if (b.source, b.target) in set(zip(ids, ids[1:])) | set(zip(ids[1:], ids)))) < 1e-6
    assert abs(lay.optical_path(pbs2.id, m1.id)[0] - L) < 1e-9

    # selecting two parts shows it in Properties
    w.scene.clearSelection()
    w.scene.comp_items[m1.id].setSelected(True)
    w.scene.comp_items[pbs2.id].setSelected(True)
    assert "Optical path" in w.props.info.text() and f"{L:.1f}" in w.props.info.text()
    # one part: its hole
    w.scene.clearSelection()
    w.scene.comp_items[m1.id].setSelected(True)
    assert "hole" in w.props.info.text()

    # beam lengths drawn on demand, placed off the beam
    w.scene.set_view_zoom(1.2)  # about a 36" board fitted to a laptop screen
    w.toggle_lengths(True)
    shown = [it for it in w.scene.beam_items.values() if it.len_rect is not None]
    assert len(shown) > len(w.scene.beam_items) // 2 and all(it.len_text.endswith("mm") for it in shown)
    for it in shown:  # never on top of a part
        assert not any(ci.body_scene_rect().intersects(it.len_rect) for ci in w.scene.comp_items.values())
    w.toggle_lengths(False)

    # ruler: drag between two holes measures the distance
    w.set_mode(MODE_RULER)
    v = w.view
    a, b = QPointF(12.7 + 25.4 * 3, 12.7 + 25.4 * 20), QPointF(12.7 + 25.4 * 7, 12.7 + 25.4 * 23)
    pa, pb = v.mapFromScene(a), v.mapFromScene(b)
    QTest.mousePress(v.viewport(), Qt.LeftButton, Qt.NoModifier, pa)
    QTest.mouseMove(v.viewport(), pb)
    QTest.mouseRelease(v.viewport(), Qt.LeftButton, Qt.NoModifier, pb)
    r0, r1 = v.ruler
    d = ((r1.x() - r0.x()) ** 2 + (r1.y() - r0.y()) ** 2) ** 0.5
    assert abs(d - 127.0) < 0.01, d  # 3-4-5 holes: 5 x 25.4 mm
    w.grab()  # draws the ruler
    w.set_mode("select")
    assert v.ruler is None
    print("ok")


def test_fiber_point():
    """A point on a fiber coupler sits at its fiber's end, follows the coupler, saves and reloads."""
    from optolayout.app import MODE_POINT
    from optolayout.model import Layout
    from optolayout.scene import SetFieldsCmd
    app = QApplication.instance() or QApplication([])
    work = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "examples" / "demo_399nm.json", work / "demo.json")
    w = MainWindow(str(work / "demo.json"))
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    lay = w.scene.layout
    fc = next(c for c in lay.components.values() if c.type in ("fiber", "fiber_cage"))
    # clicking the coupler in point mode adds the point
    w.set_mode(MODE_POINT)
    v = w.view
    v.centerOn(fc.x, fc.y)
    app.processEvents()
    ci = w.scene.comp_items[fc.id]
    body = ci.body_scene_rect().center()
    hit = next(QPointF(x, y) for x, y in ((body.x(), body.y()), (fc.x, fc.y))
               if w.view._beam_at(v.mapFromScene(QPointF(x, y))) is None)
    QTest.mouseClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, v.mapFromScene(hit))
    pts = lay.points_at_part(fc.id)
    assert len(pts) == 1 and pts[0].beam_id is None, pts
    pt = pts[0]
    end = lay.fiber_end(fc.id)
    assert lay.point_xy(pt) == end and abs((end[0] - fc.x) ** 2 + (end[1] - fc.y) ** 2 - 74 ** 2) < 25 ** 2
    assert w.scene.point_items[pt.id].pos().x() == end[0]
    # clicking again doesn't add a second one
    w.add_fiber_point(fc.id)
    assert len(lay.points_at_part(fc.id)) == 1
    # it follows the coupler
    w.scene.undo.push(SetFieldsCmd(w.scene, {fc.id: ({"x": fc.x}, {"x": fc.x + 25.4})}, "Move"))
    app.processEvents()
    assert abs(w.scene.point_items[pt.id].pos().x() - lay.fiber_end(fc.id)[0]) < 1e-9
    assert abs(lay.fiber_end(fc.id)[0] - end[0] - 25.4) < 1e-9
    # coupling efficiency: against the last point on the beam into the coupler
    from types import SimpleNamespace as NS
    into = next(b for b in lay.beams.values() if b.target == fc.id)
    p_in = w.add_point_on(into.id)
    latest = {p_in.id: (NS(power_mw=30.0), None), pt.id: (NS(power_mw=18.0), None)}
    assert abs(lay.coupling_efficiency(pt, latest) - 0.6) < 1e-9
    assert lay.coupling_efficiency(pt, {pt.id: latest[pt.id]}) is None
    # saved and loaded
    lay2 = Layout.from_dict(lay.to_dict())
    assert lay2.points[pt.id].part_id == fc.id and lay2.point_xy(lay2.points[pt.id]) == lay.point_xy(pt)
    w.set_mode("select")
    w.scene.undo.setClean()
    w.close()
    print("ok")


if __name__ == "__main__":
    test_holes()
    test_measure()
    test_fiber_point()
