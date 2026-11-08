"""The legacy toolbars and menus of both diagram editors, used with the real mouse and keyboard:
the four toolbars, buttons greyed until there is something to act on, Add State from its toolbar
button, Ctrl+C / Ctrl+V, Edit > Align from the menu bar, Ctrl+F (Find), Add Panel and Comment Text
from the toolbar, View > Toolbars hiding a toolbar."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox, QToolBar, QToolButton
from gui.bd_editor import BdEditorWindow
from gui.diagram import StateItem
from gui.main_window import MainWindow
from gui.panels import PanelItem
from bd_model import BlockDiagram

app = QApplication(sys.argv)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ('typed comment', True))
fails = 0


def ok(name, cond):
    """Count and print one check: PASS / FAIL and its name."""
    global fails
    fails += not cond
    print(('PASS ' if cond else 'FAIL ') + name, flush=True)


def button(win, key) -> QToolButton:
    """The toolbar button showing action `key`."""
    a = win.toolbar_actions[key]
    for tb in win.findChildren(QToolBar):
        b = tb.widgetForAction(a)
        if isinstance(b, QToolButton):
            return b
        for tbtn in tb.findChildren(QToolButton):
            if tbtn.defaultAction() is a:
                return tbtn
    raise LookupError(key)


def click(widget, pos=None):
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, pos or widget.rect().center())
    QTest.qWait(80)


# -- state diagram ------------------------------------------------------------------------------
w = MainWindow(); w.resize(1500, 950); w.show(); w.activateWindow(); QTest.qWait(300)
A = w.toolbar_actions
titles = [tb.windowTitle() for tb in w.findChildren(QToolBar)]
ok(f'state diagram toolbars {titles}', titles[:4] == ['Standard', 'State Diagram Tools', 'HDL Tools', 'Tasks'])
w.scene.clearSelection(); w.update_menu_states(); QTest.qWait(50)
ok('Cut / Copy greyed without a selection', not button(w, 'cut').isEnabled() and not button(w, 'copy').isEnabled())

vp = w.canvas.viewport()
n = len(w.machine.states)
click(button(w, 'state'))
ok('Add State button picks the tool', w.scene.mode == 'state')
click(vp, QPoint(vp.width() - 120, vp.height() - 120))
QTest.keyClick(vp, Qt.Key_Escape); QTest.qWait(100)
ok(f'a click adds a state ({n} -> {len(w.machine.states)})', len(w.machine.states) == n + 1)

new = w.scene.item_for(w.machine.states[-1].id)
w.scene.clearSelection(); new.setSelected(True); QTest.qWait(50)
ok('Copy lights up with a selection', button(w, 'copy').isEnabled())
w.canvas.setFocus()
QTest.keyClick(vp, Qt.Key_C, Qt.ControlModifier); QTest.qWait(100)
QTest.keyClick(vp, Qt.Key_V, Qt.ControlModifier); QTest.qWait(200)
ok(f'Ctrl+C / Ctrl+V paste a copy ({len(w.machine.states)} states)', len(w.machine.states) == n + 2)

# Edit > Align > Align Top from the menu bar, on the two new states
a, b = (w.scene.item_for(s.id) for s in w.machine.states[-2:])
b.setPos(b.pos().x(), b.pos().y() + 80)
w.scene.clearSelection(); a.setSelected(True); b.setSelected(True); QTest.qWait(50)
bar = w.menuBar().actions()                 # keep the actions referenced while their menus are used
edit_menu = next(x for x in bar if x.text().replace('&', '') == 'Edit').menu()
edit_menu.aboutToShow.emit()
entries = edit_menu.actions()
align = next(x for x in entries if x.text() == 'Align').menu()
next(x for x in align.actions() if x.text() == 'Align Top').trigger(); QTest.qWait(100)
ok('Edit > Align > Align Top lines them up', abs(a.obj.y - b.obj.y) < 1e-6)

QTest.keyClick(vp, Qt.Key_F, Qt.ControlModifier); QTest.qWait(200)
dlg = getattr(w, '_find_dialog', None)
ok('Ctrl+F opens Find', dlg is not None and dlg.isVisible())
if dlg is not None:
    ok(f'Find and Replace dialog: {dlg.windowTitle()}', dlg.windowTitle().startswith('Find and Replace - '))
    QTest.keyClicks(dlg.find.lineEdit(), w.machine.states[0].name)
    click(dlg.b_more); click(dlg.b_all)
    ok(f'Find All lists the state ({dlg.status.text()})', dlg.results.rowCount() >= 1)
    dlg.close()

click(button(w, 'panel'))
click(vp, QPoint(80, 80))
QTest.keyClick(vp, Qt.Key_Escape); QTest.qWait(100)
ok('Add Panel button places a panel', len(w.machine.panels) == 1 and
   any(isinstance(i, PanelItem) for i in w.scene.items()))

std = next(tb for tb in w.findChildren(QToolBar) if tb.windowTitle() == 'Standard')
std.toggleViewAction().trigger(); QTest.qWait(100)
ok('View > Toolbars hides Standard', not std.isVisible())
std.toggleViewAction().trigger(); QTest.qWait(100)
w.grab().save(os.path.join(OUT, 'editor_toolbars_fsm.png'))
w.dirty = False; w.close()

# -- block diagram ------------------------------------------------------------------------------
b = BdEditorWindow(BlockDiagram(unit='t', language='verilog')); b.resize(1500, 950); b.show(); QTest.qWait(300)
titles = [tb.windowTitle() for tb in b.findChildren(QToolBar)]
ok(f'block diagram toolbars {titles}', titles[:4] == ['Standard', 'Block Diagram Tools', 'HDL Tools', 'Tasks'])
vp = b.canvas.viewport()
click(button(b, 'comment'))
ok('Text button picks Comment Text', b.scene.mode == 'comment')
click(vp, QPoint(300, 300))
QTest.keyClick(vp, Qt.Key_Escape); QTest.qWait(100)
ok('a click adds the typed comment', [c.text for c in b.bd.comments if not c.group] == ['typed comment'])
click(button(b, 'panel'))
click(vp, QPoint(500, 200))
QTest.keyClick(vp, Qt.Key_Escape); QTest.qWait(100)
ok('Add Panel button places a panel', len(b.bd.panels) == 1)
b.update_menu_states()
ok('View Panel enabled once there is a panel', b.toolbar_actions['view_panel'].isEnabled())
b.grab().save(os.path.join(OUT, 'editor_toolbars_bd.png'))
b.dirty = False; b.close()

_env.finish(fails)
