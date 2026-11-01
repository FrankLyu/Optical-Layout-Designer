"""Drive both tabs with simulated mouse and keys: draw a schematic, see the
layout follow, move parts in the layout, auto-aiming, nudge, undo."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, QRectF, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from optolayout.app import MODE_BEAM, MODE_POINT, MODE_SELECT, MainWindow  # noqa: E402
from optolayout.schematic import MODE_PLACE  # noqa: E402


def test_interaction():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    QApplication.processEvents()
    lay = w.scene.layout

    # ---- schematic: place laser, mirror, fiber with the mouse, then connect them
    w.tabs.setCurrentIndex(0)
    v = w.sch_page.view
    v.resetTransform()
    v.centerOn(100, 0)
    QApplication.processEvents()

    def click(view, x, y):
        QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, view.mapFromScene(x, y))

    # placing asks what the part is; here every dialog is accepted as filled in
    asked = []
    w.sch_page.ask_part = lambda el: asked.append(el.kind) or True

    for kind, (x, y) in (("laser", (0, 0)), ("mirror", (150, 0)), ("fiber", (150, -100))):
        w.sch_page.place_kind = kind
        w.sch_page.set_mode(MODE_PLACE)
        click(v, x, y)
    sch = lay.schematic
    assert len(sch.elements) == 3 and asked == ["laser", "mirror", "fiber"]
    assert w.sch_page.mode == "select" and w.a_select.isChecked(), "back to Select after placing"
    assert w.sch_scene.el_items[next(e.id for e in sch.elements.values() if e.kind == "fiber")].isSelected()
    # every element already has a part in the layout, on the table (first fill keeps the arrangement)
    assert len(lay.components) == 3
    t = lay.table
    assert all(0 < c.x < t.width and 0 < c.y < t.height for c in lay.components.values())
    w.set_mode(MODE_BEAM)
    for x, y in ((0, 0), (150, 0), (150, -100)):
        click(v, x, y)
    assert len(sch.links) == 2 and len(lay.beams) == 2, "beams follow the schematic connections"
    m = next(c for c in lay.components.values() if c.type.startswith("mirror"))
    assert abs(m.angle - 135) < 1e-6, m.angle  # aimed between laser (left) and fiber (up)
    em = sch.elements[m.sch_id]
    assert abs(em.angle - 135) < 1e-6, em.angle  # the schematic symbol aims itself too

    # ---- insert a lens into the laser -> mirror beam by clicking on the beam
    w.set_mode(MODE_SELECT)
    w.sch_page.place_kind = "lens"
    w.sch_page.set_mode(MODE_PLACE)
    click(v, 75, 0)
    assert len(sch.elements) == 4 and len(sch.links) == 3 and len(lay.beams) == 3
    lens = next(e for e in sch.elements.values() if e.kind == "lens")
    lens_part = lay.component_for(lens.id)
    laser = next(c for c in lay.components.values() if c.type == "laser")
    assert 0 < lens_part.y < t.height and laser.x < lens_part.x < m.x, "nothing moved by hand yet: copies schematic"

    # ---- part number is set in the schematic and shows in the layout
    w.sch_scene.set_fields(lens.id, {"part_number": "LA1509-A"})
    assert lens_part.part_number == "LA1509-A"

    # ---- layout: drag the mirror with the mouse (snaps to holes, pins the layout)
    w.sch_page.set_mode("select")
    w.tabs.setCurrentIndex(1)
    lv = w.view
    lv.resetTransform()
    lv.centerOn(t.width / 2, t.height / 2 + 80)
    QApplication.processEvents()

    def drag(c, to):
        QTest.mousePress(lv.viewport(), Qt.LeftButton, Qt.NoModifier, lv.mapFromScene(c.x, c.y))
        QTest.mouseMove(lv.viewport(), lv.mapFromScene(c.x + 3, c.y - 3))
        QTest.mouseMove(lv.viewport(), lv.mapFromScene(*to))
        QTest.mouseRelease(lv.viewport(), Qt.LeftButton, Qt.NoModifier, lv.mapFromScene(*to))

    drag(m, (m.x + 25.4, m.y))
    assert m.pinned
    n = (m.x - t.hole_offset) / t.hole_pitch
    assert abs(n - round(n)) < 1e-6, "snapped to a hole"
    fc = next(c for c in lay.components.values() if c.type.startswith("fiber"))

    # ---- once the layout is being arranged by hand, new parts wait below the table
    w.tabs.setCurrentIndex(0)
    w.sch_page.place_kind = "iris"
    w.sch_page.set_mode(MODE_PLACE)
    click(v, 150, -50)
    w.sch_page.set_mode("select")
    iris = lay.component_for(next(e.id for e in sch.elements.values() if e.kind == "iris"))
    assert iris.y > t.height, "new part waits in the strip below the table"
    w.tabs.setCurrentIndex(1)
    lv.resetTransform()
    lv.centerOn(t.width / 2, t.height / 2 + 80)
    QApplication.processEvents()
    drag(iris, (m.x, (m.y + fc.y) / 2))
    assert 0 < iris.y < t.height
    import math
    want = math.degrees(math.atan2(-(fc.y - m.y), fc.x - m.x)) % 360
    assert abs(iris.angle - want) < 1e-6, (iris.angle, want)  # aims along the mirror -> fiber beam
    new_part = lens_part

    # ---- arrow-key nudge by one hole, Shift for 1 mm; undo
    w.scene.clearSelection()
    w.scene.comp_items[m.id].setSelected(True)
    x0 = m.x
    lv.setFocus()
    QTest.keyClick(lv.viewport(), Qt.Key_Right)
    assert abs(m.x - x0 - t.hole_pitch) < 1e-6
    QTest.keyClick(lv.viewport(), Qt.Key_Left, Qt.ShiftModifier)
    assert abs(m.x - x0 - t.hole_pitch + 1) < 1e-6
    w.scene.undo.undo()
    w.scene.undo.undo()
    assert abs(m.x - x0) < 1e-6

    # ---- rotating by hand turns auto-aim off; A turns it back on
    w.rotate_selected(5)
    assert not m.auto_angle and abs(m.angle - 140) < 1e-6
    w.auto_aim_selected()
    assert m.auto_angle and abs(m.angle - 135) < 1e-6

    # ---- layout can't add or delete parts
    w.set_mode(MODE_BEAM)
    assert w.a_select.isChecked() and not w.a_beam.isChecked()
    n_parts = len(lay.components)
    w.delete_selected()
    assert len(lay.components) == n_parts

    # ---- measurement point on a beam; its callout grows with the zoom, within limits
    w.set_mode(MODE_POINT)
    b = next(iter(lay.beams.values()))
    a_, z_ = lay.components[b.source], lay.components[b.target]
    pt = w.add_point_on(b.id)
    it = w.scene.point_items[pt.id]
    w.scene.set_view_zoom(1.0)
    w.scene.layout_annotations()
    r1 = QRectF(it.box)
    w.scene.set_view_zoom(3.0)
    w.scene.layout_annotations()
    r3 = QRectF(it.box)
    assert r3.height() * 3 > r1.height() * 1.2  # bigger on screen when zoomed in
    assert r3.height() <= r1.height()  # but not bigger on the table
    w.scale_text(1.5)
    assert it.box.width() > r3.width()
    w.scale_text(None)
    # the box sits off the marker, clear of the parts
    pos = it.pos()
    box = it.box.translated(pos)
    assert not box.contains(pos)
    for ci in w.scene.comp_items.values():
        assert not ci.body_scene_rect().intersects(box), ci.comp.label

    # ---- cross-probe: double-click jumps to the schematic with the part selected
    w.set_mode(MODE_SELECT)
    w.edit_in_schematic(m)
    assert w.on_schematic() and w.sch_scene.el_items[m.sch_id].isSelected()

    # ---- deleting the mirror in the schematic removes part + its beams; undo puts it back where it was
    w.sch_scene.clearSelection()
    w.sch_scene.el_items[m.sch_id].setSelected(True)
    mx, my = m.x, m.y
    w.delete_selected()
    assert m.id not in lay.components and len(lay.beams) == 2
    w.scene.undo.undo()
    m2 = lay.component_for(m.sch_id)
    assert m2 is not None and (m2.x, m2.y) == (mx, my) and len(lay.beams) == 4
    assert not lay.points[pt.id].archived, "point returns with its beam"

    w.scene.undo.setClean()
    w.close()
    print("ok")


if __name__ == "__main__":
    test_interaction()
