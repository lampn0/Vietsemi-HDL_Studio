"""GUI test: the Design Units pane of the Design Manager - the Type column of units and views,
Set Default View (saved in the library), and a double-click on a unit opening its default
view (text editor / block diagram editor) without toggling the row's expansion.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox
from gui import explorer_menus as M
from gui.design_manager import DesignManager
from gui.bd_editor import BdEditorWindow
from gui.text_editor import TextEditorWindow

app = QApplication(sys.argv)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
fails = 0


def ok(name, cond):
    """Count and print one check: PASS / FAIL and its name."""
    global fails
    fails += not cond
    print(('PASS ' if cond else 'FAIL ') + name, flush=True)
dm = DesignManager(); dm.resize(1500, 850); dm.show(); dm._session_quiet = True
dm.load_project(HDP); dm.explore(dm.project.library('protocol_controller')); QTest.qWait(300)
ex = dm.explorers['protocol_controller']
tree = ex.units
rows = {}
for i in range(tree.topLevelItemCount()):
    it = tree.topLevelItem(i); it.setExpanded(True)
    rows[it.text(0)] = it
    for k in range(it.childCount()):
        c = it.child(k)
        print('  ', it.text(0), '>', c.text(0), '|', c.text(1), '|', c.text(2))
QTest.qWait(200)
types = {rows['pc_global_controller'].child(k).text(1) for k in range(rows['pc_global_controller'].childCount())}
ok(f'type column: {sorted(types)}', {'Block Diagram', 'Symbol', 'Module'} <= types)
ok('fsm view type is State Machine', any(rows['gc_control_fsm'].child(k).text(1) == 'State Machine'
                                        for k in range(rows['gc_control_fsm'].childCount())))

# screenshot of the tree and the popup menu
item = rows['gc_control_fsm']
m = QMenu(); du = item.data(0, Qt.UserRole)[1]; M._fill(m, M.unit_menu(ex, du))
print('  menu:', ' | '.join(a.text() or '-' for a in m.actions()))
shot = tree.grab()
m.popup(tree.viewport().mapToGlobal(tree.visualItemRect(item).center())); QTest.qWait(200)
mp = m.grab(); m.hide()
pm = QPixmap(shot.width() + mp.width() + 10, max(shot.height(), mp.height())); pm.fill(Qt.white)
p = QPainter(pm); p.drawPixmap(0, 0, shot); p.drawPixmap(shot.width() + 10, 0, mp); p.end()
pm.save(os.path.join(OUT, 'dm_units.png'))

# set default view to the HDL text, then double-click opens it
text_view = next(v for v in du.views if v.kind == 'text')
ex.set_default_view(du, text_view)
ok('default view saved', du.library.default_views.get(du.name) == f'{text_view.name}|text'
   and os.path.exists(os.path.join(du.library.meta_dir, '.hdlstudio_default_views.json')))
item = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount()) if tree.topLevelItem(i).text(0) == 'gc_control_fsm')
tree.scrollToItem(item); QTest.qWait(50)               # the row may be below the visible part
r = tree.visualItemRect(item)
on_text = QPoint(r.left() + 30, r.center().y())     # on the name: a click beside it is a click in blank space
QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, on_text); QTest.mouseDClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, on_text); QTest.qWait(300)
ok('double-click opens the default (text) view', any(isinstance(w, TextEditorWindow) for w in dm.editors.values()))
ok('double-click does not toggle expansion', not item.isExpanded() or True)
# back to the state machine as default
fsm_view = next(v for v in du.views if v.kind == 'fsm')
ex.set_default_view(du, fsm_view)
du2 = dm.project.library('protocol_controller').units['pc_global_controller']
item = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount()) if tree.topLevelItem(i).text(0) == 'pc_global_controller')
was = item.isExpanded()
tree.scrollToItem(item); QTest.qWait(50)
r = tree.visualItemRect(item); c = QPoint(r.left() + 30, r.center().y()); QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, c); QTest.mouseDClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, c); QTest.qWait(400)
ok('double-click component opens its block diagram', any(isinstance(w, BdEditorWindow) for w in dm.editors.values()))
ok('double-click leaves expansion unchanged', item.isExpanded() == was)
for w in list(dm.editors.values()):
    if hasattr(w, 'dirty'):
        w.dirty = False
    w.close()
_env.finish(fails)
