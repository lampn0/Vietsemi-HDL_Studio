"""Save a state diagram from the editor back to its legacy .sm (real window, real save path).

    python tests/gui/gui_fsm_save_sm.py [path/to/fsm.sm] [--keep]

Without a path it uses gc_control_fsm of the real project (HDLSTUDIO_TEST_SRC, as the other GUI
tests) and is skipped when that file is not there, so run_all.py can run it. The .sm is copied to tests/gui/out/save_sm/fsm.sm (unless --keep: then the file itself is
edited, for opening it in the legacy tool afterwards). In the editor: the state ST_REF_DES (else the
second state) is dragged by the mouse 3 grid steps up, a transition's condition is changed,
File > Save. The file is read again and checked: the state moved, its transitions' ends
moved with it, the condition is there, all else unchanged.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'src'))
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])
from gui.main_window import MainWindow  # noqa: E402
from formats.import_sm import import_sm  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith('--')]
src = args[0] if args else os.path.join(os.environ.get('HDLSTUDIO_TEST_SRC', r'D:\workspace\src'),
                                        'libs', 'protocol_controller', 'hds', 'gc_control_fsm', 'fsm.sm')
if not os.path.isfile(src):
    print(f'SKIP gui_fsm_save_sm: {src} not found (give a .sm or set HDLSTUDIO_TEST_SRC)', flush=True)
    sys.exit(0)
if '--keep' in sys.argv:
    path = src
else:
    # in <library>/hds/<unit>/ as in a project, so the editor knows the names without asking
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'save_sm', 'lib', 'hds', 'unit')
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, 'fsm.sm')
    shutil.copy(src, path)

def _close_dialogs():
    """Timer callback: print and close any modal dialog, so the test never hangs on one."""
    # a modal dialog (a message box) must not hang the test: print it and close it
    w = QApplication.activeModalWidget()
    if w is not None:
        print('dialog:', w.windowTitle(), '|', getattr(w, 'text', lambda: '')())
        w.close()


from PySide6.QtCore import QTimer  # noqa: E402
_t = QTimer()
_t.timeout.connect(_close_dialogs)
_t.start(500)
print('open', path, flush=True)
win = MainWindow()
win.open_path(path)
win.show()
QTest.qWait(500)
sc, m = win.scene, win.machine
st = next((s for s in m.states if s.name == 'ST_REF_DES'), m.states[1])
item = sc.items_by_id[st.id]
gv = sc.views()[0]
gv.centerOn(item)
QTest.qWait(200)
x0, y0 = st.x, st.y
p0 = gv.mapFromScene(item.scenePos())
step = gv.mapFromScene(item.scenePos().x(), item.scenePos().y() - 30) - p0
vp = gv.viewport()
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p0)
for k in range(1, 6):
    QTest.mouseMove(vp, p0 + QPoint(step.x() * k // 5, step.y() * k // 5))
    QTest.qWait(30)
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p0 + step)
QTest.qWait(200)
moved = (st.x - x0, st.y - y0)
state_ids = {s.id for s in m.states}
t = next(t for t in m.transitions if t.cond and t.src in state_ids and t.src != st.id and t.dst != st.id)
t.cond = t.cond + ' & saved_by_studio'
print('save', flush=True)
win.save_file()
print('saved', flush=True)
QTest.qWait(200)
win.dirty = False
win.close()

again = import_sm(path).machines[0]
s2 = next(s for s in again.states if s.id == st.id)
t2 = next(x for x in again.transitions if x.id == t.id)
ends_ok = True
for x in again.transitions:
    if st.id in (x.src, x.dst) and x.src != x.dst:
        # the end on the moved state lies on its circle (radius as saved)
        import math
        ang = x.start_angle if x.src == st.id else x.end_angle
        ends_ok &= ang is not None
checks = [
    ('state dragged', moved[1] < -1),
    ('state saved where it was dragged', abs(s2.x - st.x) < 0.02 and abs(s2.y - st.y) < 0.02),
    ('condition saved', t2.cond == t.cond),
    ('transition ends on the moved state', ends_ok),
    ('same objects', len(again.transitions) == len(m.transitions) and len(again.states) == len(m.states)),
]
bad = 0
for name, ok in checks:
    print(('PASS ' if ok else 'FAIL ') + name, flush=True)
    bad += not ok
print('file:', path)
sys.exit(1 if bad else 0)
