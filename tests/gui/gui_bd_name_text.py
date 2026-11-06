"""Component name lines on the legacy dynamo_core diagram (read only): select, drag, rename."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication, QLineEdit
from PySide6.QtTest import QTest
app = QApplication(sys.argv)
from formats.import_bd import import_bd
from gui.bd_editor import BdEditorWindow, InstanceItem
bd = import_bd(_env.legacy_bd('hds/dynamo_core/struct.bd'))
inst = next(i for i in bd.instances if i.unit == 'dataflow_controller')
win = BdEditorWindow(bd); win.resize(1200, 800); win.show(); app.processEvents()
vp = win.canvas.viewport()
fails = 0
def check(ok, what):
    """Count and print one check: PASS / FAIL and its name."""
    global fails; fails += not ok; print('PASS' if ok else 'FAIL', what)
def item():
    """The InstanceItem of the component under test."""
    return next(it for it in win.scene.items() if isinstance(it, InstanceItem) and it.obj is inst)
def line_pt(kind):
    """Viewport point at the centre of name line `kind`."""
    it = item(); box = next(r for k, _, r in it.name_lines() if k == kind)
    return win.canvas.mapFromScene(it.mapToScene(box.center()))
win.canvas.centerOn(item().mapToScene(item().name_rect().center())); app.processEvents()
# single click: the line is selected, the body is not
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, line_pt('instance')); app.processEvents()
check(win.scene.selected_text == (inst.id, 'instance') and not item().isSelected(), 'click selects the name line only')
win.canvas.grab().save(os.path.join(OUT, 'name_text.png'))
# drag moves the text, not the component
x0, y0 = inst.x, inst.y; before = list(inst.text_pos); pt = line_pt('instance')
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, pt)
for k in range(1, 6):
    QTest.mouseMove(vp, pt + QPoint(8 * k, 4 * k))
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, pt + QPoint(40, 20)); app.processEvents()
check(inst.text_pos != before and (inst.x, inst.y) == (x0, y0), 'drag moves the name text only')
# click on empty space clears the line selection
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5)); app.processEvents()
check(win.scene.selected_text is None, 'click elsewhere clears it')
def edit(kind, text):
    """Double-click name line `kind`, type `text`, press Enter; returns the edit box used (None when none opened)."""
    QTest.mouseDClick(vp, Qt.LeftButton, Qt.NoModifier, line_pt(kind)); app.processEvents()
    ed = next((w for w in vp.findChildren(QLineEdit) if w.isVisible()), None)
    if ed is None:
        return None
    shown = ed.text(); ed.setText(text); QTest.keyClick(ed, Qt.Key_Return); app.processEvents()
    return shown
check(edit('instance', 'u_dfc') == 'dataflow_controller' and inst.name == 'u_dfc', 'double-click renames the instance')
shown = edit('unit', 'no_such_unit'); print('shown', shown, 'unit', inst.unit, win.statusBar().currentMessage())
check(shown == 'dataflow_controller' and inst.unit == 'dataflow_controller', 'unknown component is refused, unit kept')
print('FAILS', fails)
_env.finish(fails)
