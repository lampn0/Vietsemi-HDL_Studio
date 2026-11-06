"""Component name text: click selects one name line, drag moves the text, double-click edits
it; undo back to the saved state clears the title "*" (which the legacy tool puts right after the view
name: "lib/unit/view * (Block Diagram)"). Real app path, visible window."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication, QLineEdit
from PySide6.QtTest import QTest
app = QApplication(sys.argv)
from gui.design_manager import DesignManager
from gui.bd_editor import InstanceItem
dm = DesignManager(); dm.show(); dm.load_project(HDP); app.processEvents()
lib = dm.project.library('dti_hbm'); lib.scan(dm.project.cache)
du = lib.units['dynamo_core']; dm.open_view(du, du.graphic_view()); app.processEvents()
win = next(iter(dm.editors.values())); win.resize(1400, 900); win.raise_(); win.activateWindow(); app.processEvents()
inst = next(i for i in win.bd.instances if i.unit == 'dataflow_controller')
fails = 0
def check(ok, what):
    """Count and print one check: PASS / FAIL and its name."""
    global fails; fails += not ok; print('PASS' if ok else 'FAIL', what)
def item():
    """The InstanceItem of the component under test (the scene is rebuilt after edits)."""
    return next(i for i in win.scene.items() if isinstance(i, InstanceItem) and i.obj is inst)
def line_pt(kind):
    """Viewport point at the centre of name line `kind` of the component."""
    it = item(); box = next(r for k, _, r in it.name_lines() if k == kind)
    return win.canvas.mapFromScene(it.mapToScene(box.center()))
win.canvas.resetTransform(); win.canvas.scale(1.5, 1.5)
win.canvas.centerOn(item().mapToScene(item().name_rect().center())); app.processEvents(); QTest.qWait(300)
vp = win.canvas.viewport()
check(not win.dirty and ' * ' not in win.windowTitle(), 'opened without *')
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, line_pt('instance')); QTest.qWait(200)
check(win.scene.selected_text == (inst.id, 'instance') and not item().isSelected(), 'click selects the instance name line')
win.canvas.grab().save(os.path.join(OUT, 'component_name.png'))
before = list(inst.text_pos); x0 = inst.x; pt = line_pt('instance')
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, pt)
for k in range(1, 6):
    QTest.mouseMove(vp, pt + QPoint(10 * k, 6 * k)); QTest.qWait(20)
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, pt + QPoint(50, 30)); QTest.qWait(200)
check(inst.text_pos != before and inst.x == x0, 'drag moves the name text only')
check(win.dirty and ' * ' in win.windowTitle(), 'edited: title has *')
QTest.qWait(600)                                   # let the undo step be taken
win.undo_stack.undo(); QTest.qWait(200)
inst = next(i for i in win.bd.instances if i.unit == 'dataflow_controller')   # the model was reloaded
check(inst.text_pos == before, 'undo puts the text back')
check(not win.dirty and ' * ' not in win.windowTitle(), 'undo to the saved state: no *')
win.undo_stack.redo(); QTest.qWait(200)
check(win.dirty and ' * ' in win.windowTitle(), 'redo: * again')
inst = next(i for i in win.bd.instances if i.unit == 'dataflow_controller')
QTest.mouseDClick(vp, Qt.LeftButton, Qt.NoModifier, line_pt('instance')); QTest.qWait(200)
ed = next((w for w in vp.findChildren(QLineEdit) if w.isVisible()), None)
check(ed is not None and ed.text() == 'dataflow_controller', 'double-click opens the inline editor')
if ed:
    ed.setText('u_dfc'); QTest.keyClick(ed, Qt.Key_Return); QTest.qWait(200)
inst = next(i for i in win.bd.instances if i.unit == 'dataflow_controller')
check(inst.name == 'u_dfc', 'instance renamed')
print('FAILS', fails)
_env.finish(fails)
