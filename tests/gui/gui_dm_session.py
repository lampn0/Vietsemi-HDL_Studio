"""Session restore across separate runs (python gui_dm_session.py runs steps 1, 2, 3)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
if len(sys.argv) < 2:                       # no step given: run them all, one process each
    sys.exit(_env.run_steps(__file__, ['1', '2', '3']))
step = sys.argv[1]
HDP, CFG, OUT = _env.setup()
hdp, cfg = HDP, CFG
from PySide6.QtCore import QRect
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from gui.design_manager import DesignManager
from gui.bd_editor import BdEditorWindow
from gui.main_window import MainWindow as FsmEditorWindow
from gui.text_editor import TextEditorWindow
import homes
from session import Session

app = QApplication(sys.argv)
asked = []
QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(a[2] if len(a) > 2 else ''), QMessageBox.Yes)[1])
fails = 0


def ok(name, cond):
    """Count and print one check: PASS / FAIL and its name."""
    global fails
    fails += not cond
    print(('PASS ' if cond else 'FAIL ') + name, flush=True)
dm = DesignManager(); dm.show()


def editors(cls):
    """The open editor windows of class `cls`."""
    return [w for w in dm.editors.values() if isinstance(w, cls)]


if step == '1':
    dm.restore_session(hdp)                     # no session yet: just opens the project
    for name in ('protocol_controller', 'dti_hbm_lib'):
        lib = dm.project.library(name)
        if lib is not None:
            dm.explore(lib)
    lib = dm.project.library('protocol_controller')
    dm.open_view(lib.units['pc_global_controller'], lib.units['pc_global_controller'].graphic_view())
    dm.open_view(lib.units['gc_control_fsm'], lib.units['gc_control_fsm'].graphic_view())
    hdl = next(f for f in sorted(lib.files) if f.endswith(('.v', '.sv'))) if isinstance(lib.files, (list, dict, set)) else None
    if hdl:
        dm.open_text_file(hdl if os.path.isabs(hdl) else os.path.join(lib.main_hdl_dir, hdl))
    QTest.qWait(300)
    bd = editors(BdEditorWindow)[0]
    bd.setGeometry(QRect(120, 140, 1000, 700)); bd.tabs.setCurrentIndex(1)
    fsm = editors(FsmEditorWindow)[0]
    fsm.setGeometry(QRect(200, 180, 900, 650))
    for t in editors(TextEditorWindow):
        t.editor.goto_line(20)
    dm.tabs.setCurrentWidget(dm.explorers['protocol_controller'])
    # unsaved change in the block diagram
    net = bd.bd.wires[0].net
    bd._rename(net, 'recovered_net'); bd._reload_scene(); bd.changed()
    dm.autosave(); QTest.qWait(100)
    s = Session.load()
    print('  session:', s.project, s.explorers, s.current, [(e.kind, e.unit or os.path.basename(e.path), e.tab) for e in s.editors])
    ok('step1: session saved with 3 editors', s is not None and len(s.editors) == 3)
    ok('step1: autosave written', os.listdir(os.path.join(cfg, 'user', homes.version_dir_name(), 'autosave')))
    sys.stdout.flush()
    _env.finish(fails)                                 # simulate a crash: no close, no cleanup

if step == '2':
    dm.restore_session()
    QTest.qWait(300)
    ok('step2: project reopened', dm.project is not None and os.path.samefile(dm.project.path, hdp))
    ok(f'step2: library tabs {list(dm.explorers)}', 'protocol_controller' in dm.explorers)
    ok('step2: current tab restored', dm.tabs.currentWidget() is dm.explorers.get('protocol_controller'))
    bds, fsms, txt = editors(BdEditorWindow), editors(FsmEditorWindow), editors(TextEditorWindow)
    ok(f'step2: editors reopened bd={len(bds)} fsm={len(fsms)} text={len(txt)}', len(bds) == 1 and len(fsms) == 1 and len(txt) == 1)
    ok(f'step2: bd geometry {bds[0].geometry().topLeft().toTuple()}', abs(bds[0].geometry().x() - 120) <= 10 and abs(bds[0].geometry().width() - 1000) <= 10)
    ok('step2: bd tab restored', bds[0].tabs.currentIndex() == 1)
    ok(f'step2: text cursor line {txt[0].editor.textCursor().blockNumber() + 1}', txt[0].editor.textCursor().blockNumber() + 1 == 20)
    ok(f'step2: asked to recover ({len(asked)} question)', any('Recover' in q or 'not saved' in q for q in asked))
    ok('step2: unsaved change recovered and marked modified',
       any(w.net == 'recovered_net' for w in bds[0].bd.wires) and bds[0].dirty)
    # normal exit, discarding the recovered change
    for w in dm.editors.values():
        if hasattr(w, 'dirty'):
            w.dirty = False
    dm.close(); QTest.qWait(200)
    s = Session.load()
    ok('step2: normal close keeps the window list', s is not None and len(s.editors) == 3)
    ok('step2: autosave removed after a normal close', not os.listdir(os.path.join(cfg, 'user', homes.version_dir_name(), 'autosave')))

if step == '3':
    dm.restore_session()
    QTest.qWait(300)
    ok('step3: windows reopened again', len(dm.editors) == 3)
    ok('step3: no recovery question', not asked)
    bd = editors(BdEditorWindow)[0]
    ok('step3: discarded change is gone', not any(w.net == 'recovered_net' for w in bd.bd.wires) and not bd.dirty)
    for w in dm.editors.values():
        if hasattr(w, 'dirty'):
            w.dirty = False
    dm.close()
_env.finish(fails)
