"""Component Parameters page on the real project (read only: no lock, nothing saved)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from types import SimpleNamespace
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from project.project import open_project
from formats.import_bd import import_bd
from gui import bd_editor, bd_dialogs

app = QApplication(sys.argv)
fails = 0


def ok(name, cond):
    """Count and print one check: PASS / FAIL and its name."""
    global fails
    fails += not cond
    print(('PASS ' if cond else 'FAIL ') + name, flush=True)
proj = open_project(_env.legacy_bd('dti_hbm.hdp'))
bd = import_bd(_env.legacy_bd('libs/protocol_controller/hds/protocol_controller/struct.bd'))
ctx = SimpleNamespace(project=proj, readonly=True, readonly_reason='test', project_name=proj.name,
                      view=SimpleNamespace(path=''), manager=None, release=lambda: None, key='')
w = bd_editor.BdEditorWindow(bd, ctx); w.resize(1400, 900); w.show(); QTest.qWait(300)
inst = next(i for i in bd.instances if i.name == 'pc_global_controller')
shots = []


def drive():
    """Check the parameter lists of the open Component Properties dialog and override one parameter."""
    d = next(x for x in app.topLevelWidgets() if isinstance(x, bd_dialogs.ComponentPropertiesDialog) and x.isVisible())
    rows = [d.avail.item(i).text().split() for i in range(d.avail.count())]
    print('  symbol list:', rows[:4], '...', len(rows))
    ok('declarations shown as written (`CFG_...)', rows and all(r[1].startswith('`') for r in rows[:5]))
    ok('symbol table order', [r[0] for r in rows[:3]] == ['DRAM_ADDR_WIDTH', 'DRAM_BANK_NUM', 'DRAM_BA_WIDTH'])
    ok('Add disabled until a parameter is selected', not d.buttons['Add >>'].isEnabled())
    ok('library and component name not editable', not d.lib.isEnabled() and d.unit.isReadOnly())
    shots.append(d.grab())
    d.avail.item(1).setSelected(True)
    ok('Add enabled with a selection', d.buttons['Add >>'].isEnabled())
    d._add()
    ok('Add moves the parameter to the table', d.table.rowCount() == 1 and d.table.item(0, 0).text() == 'DRAM_BANK_NUM'
       and d.table.item(0, 1).text() == '`CFG_DRAM_BANK_NUM' and d.avail.count() == len(rows) - 1)
    d.all_params.setChecked(True); QTest.qWait(50)
    ok(f'All parameters list ({d.avail.count() + 1} total)', d.avail.count() + 1 >= len(rows))
    d.only_symbol.setChecked(True)
    d.table.selectRow(0); d._remove()
    ok('Remove puts it back in the list', d.table.rowCount() == 0 and d.avail.count() == len(rows))
    shots.append(d.grab())
    d.reject()
QTimer.singleShot(400, drive)
w.component_properties(inst, 'parameters')
pm = QPixmap(sum(s.width() for s in shots) + 10, max(s.height() for s in shots)); pm.fill(Qt.white)
p = QPainter(pm); x = 0
for s in shots:
    p.drawPixmap(x, 0, s); x += s.width() + 10
p.end(); pm.save(os.path.join(OUT, 'bd_params.png'))
w.dirty = False
_env.finish(fails)
