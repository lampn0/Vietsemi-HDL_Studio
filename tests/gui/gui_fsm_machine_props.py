"""State diagram popup menus and the State Machine Properties / Compiler Directives dialogs, in
the real window with real right clicks (pyautogui), as the legacy tool has them.

    python tests/gui/gui_fsm_machine_props.py [path/to/fsm.sm]

Default diagram: protocol_controller/gc_control_fsm of the real project (copied to
tests/gui/out/machine_props/lib/hds/unit/fsm.sm, never edited in place). Leave the mouse alone
while it runs.

1. Right clicks on open space, a state, a junction, a link, the interrupt and recovery points
   and a transition text: each menu's entries are compared with the menu the legacy tool shows there;
   screenshots in tests/gui/out/machine_props/.
2. Diagram > State Machine Properties...: every page is shown (screenshots), then current
   state name, encoding style, concurrent statements, State Register Statements Visible and the
   registered affix are changed, OK. Diagram > Compiler Directives...: End-Module Directives, OK.
3. File > Save; the .sm read again has the changes.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'src'))
import pyautogui  # noqa: E402
from PySide6.QtCore import QPoint, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

app = QApplication(sys.argv[:1])
from gui.diagram import JunctionItem, LinkItem, PointItem, StateItem, TransitionLabel  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from formats.import_sm import import_sm  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else r'D:\workspace\src\libs\protocol_controller\hds\gc_control_fsm\fsm.sm'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'machine_props')
d = os.path.join(OUT, 'lib', 'hds', 'unit')
os.makedirs(d, exist_ok=True)
path = os.path.join(d, 'fsm.sm')
shutil.copy(SRC, path)

# the menus the legacy tool shows (read from its screenshots); '-' separators are not compared
EDIT = ['Cut', 'Copy', 'Paste', 'Paste Special', 'Delete', 'Appearance...']
EXPECTED = {
    'diagram': ['Signals Table', 'Open Up', 'Undo', 'Redo', 'Paste', 'View Area', 'Zoom In', 'Zoom Out',
                'Zoom Last', 'View Page', 'Print Page...', 'Object Visibility...', 'Update Where Used...',
                'State Machine Properties...'],
    'state': EDIT + ['Change Shape...', 'Show Text', 'Re-level', 'Object Properties...'],
    'junction': EDIT + ['Object Properties...'],
    'link': ['Rotate'] + EDIT + ['Object Properties...'],
    'interrupt': ['Rotate'] + EDIT,
    'recovery': EDIT + ['Hide'],
    'text': ['Copy', 'Paste', 'Paste Special', 'Appearance...', 'Hide Text', 'Send to Editor', 'Finish Edit',
             'Finish All Edits', 'Object Properties...'],
}
results = []


def check(name, ok, detail=''):
    """Record and print one check (PASS / FAIL, its name and a detail)."""
    results.append(ok)
    print(('PASS' if ok else 'FAIL'), name, detail, flush=True)


def wait_for(cond, ms=4000):
    """Process events until cond() is true or `ms` milliseconds have passed; returns whether it did."""
    for _ in range(ms // 50):
        QTest.qWait(50)
        if cond():
            return True
    return False


win = MainWindow()
win.open_path(path)
win.show()
win.showMaximized()
win.raise_()
win.activateWindow()
QTest.qWait(800)
sc, m = win.scene, win.machine
gv = win.canvas
vp = gv.viewport()


def right_click_popup(kind: str, scene_pt):
    """Right click (real mouse) at a scene point; returns the entries of the menu that opens
    (enabled ones marked) after a screenshot of it, and closes it."""
    gv.centerOn(scene_pt)
    QTest.qWait(200)
    g = vp.mapToGlobal(gv.mapFromScene(scene_pt))
    seen, done = [], []

    # the menu runs its own event loop (QMenu.exec): a timer looks at it from inside that loop
    def grab():
        """Timer callback: once the popup menu is shown, record its entries and close it."""
        pop = QApplication.activePopupWidget()
        if pop is None or not pop.isVisible():
            return
        timer.stop()
        win.screen().grabWindow(0).copy(pop.geometry().adjusted(-200, -60, 40, 40)).save(
            os.path.join(OUT, f'pop_{kind}.png'))
        seen.extend((a.text(), a.isEnabled()) for a in pop.actions() if not a.isSeparator())
        pop.close()
        done.append(1)
    timer = QTimer()
    timer.timeout.connect(grab)
    timer.start(200)
    pyautogui.rightClick(g.x(), g.y())
    wait_for(lambda: bool(done))
    timer.stop()
    return seen


def first(cls, pred=lambda it: True):
    """The first scene item of class `cls` that satisfies `pred`, or None."""
    return next((it for it in sc.items() if isinstance(it, cls) and pred(it)), None)


# 1. popup menus --------------------------------------------------------------------------
def empty_point():
    """A viewport point over empty diagram space (for the diagram popup menu)."""
    r = sc.itemsBoundingRect()
    for k in range(40):
        p = r.center() + QPoint(0, 0).toPointF()
        p.setX(r.left() + (k * 97) % int(r.width()))
        p.setY(r.top() + (k * 61) % int(r.height()))
        if not sc.items(p) and all(not sc.items(p + QPoint(dx, dy).toPointF())
                                   for dx in (-15, 15) for dy in (-15, 15)):
            return p
    return r.bottomRight() + QPoint(30, 30).toPointF()


targets = [('diagram', empty_point())]
for kind, it in (('state', first(StateItem)), ('junction', first(JunctionItem)), ('link', first(LinkItem)),
                 ('interrupt', first(PointItem, lambda i: i.obj.kind == 'interrupt')),
                 ('recovery', first(PointItem, lambda i: i.obj.kind == 'recovery')),
                 ('text', first(TransitionLabel, lambda i: bool(i.obj.cond)))):
    if it is None:
        print('skip', kind, '(none in this diagram)')
        continue
    targets.append((kind, it.mapToScene(it.boundingRect().center()) if kind == 'text' else it.scenePos()))
for kind, pt in targets:
    entries = right_click_popup(kind, pt)
    names = [t for t, _ in entries]
    check(f'popup {kind}: legacy entries', names == EXPECTED[kind], '' if names == EXPECTED[kind] else str(names))
    on = {t for t, e in entries if e}
    want_on = {'diagram': {'Signals Table', 'View Area', 'Zoom In', 'Zoom Out', 'State Machine Properties...'},
               'state': {'Delete', 'Object Properties...'}, 'junction': {'Delete', 'Object Properties...'},
               'link': {'Delete', 'Object Properties...'}, 'interrupt': {'Delete'}, 'recovery': {'Delete'},
               'text': {'Copy', 'Object Properties...'}}[kind]
    check(f'popup {kind}: working entries enabled', want_on <= on, str(sorted(want_on - on)))


# 2. the dialogs ----------------------------------------------------------------------------
def drive(script):
    """Run script(dialog) on the modal dialog once it is open (exec() blocks the test)."""
    def go():
        """Wait for the modal dialog to open (polling), then run the script on it."""
        dlg = QApplication.activeModalWidget()
        if dlg is None:
            QTimer.singleShot(100, go)
            return
        script(dlg)
    QTimer.singleShot(300, go)


def click_button(dlg, text):
    """Click the push button labelled `text` in dialog `dlg`."""
    b = next(b for b in dlg.findChildren(QPushButton) if b.text() == text)
    QTest.mouseClick(b, Qt.LeftButton)


def sm_script(dlg):
    """State Machine Properties: show and photograph every page, change the editable fields, OK."""
    from gui.sm_machine_dialog import PAGES
    titles = []
    for key, *_ in PAGES:
        dlg.show_page(key)
        QTest.qWait(150)
        titles.append(dlg.windowTitle())
        dlg.grab().save(os.path.join(OUT, f'smp_{key}.png'))
    check('SM props: page titles as the legacy tool',
          titles[0] == 'State Machine Properties'
          and titles[3] == f'State Machine Properties - Encoding ({m.name})'
          and titles[5] == 'State Machine Properties - Declaration Blocks', str(titles))
    check('SM props: encoding table head', dlg.enc_table.item(0, 0).text() == f'{len(m.states)} states',
          dlg.enc_table.item(0, 0).text())
    dlg.show_page('advanced')
    dlg.cur_name.setText('cs_q')
    dlg.show_page('encoding')
    QTest.mouseClick(dlg.enc_buttons['gray'], Qt.LeftButton)
    QTest.qWait(100)
    check('SM props: table follows the style', dlg.enc_table.horizontalHeaderItem(1).text() == 'Gray')
    dlg.show_page('statements')
    dlg.conc.setPlainText('assign probe = 1\'b0;')
    dlg.sreg_vis.setChecked(True)
    dlg.show_page('internal')
    dlg.reg_affix.setText('_reg')
    click_button(dlg, 'OK')


def cd_script(dlg):
    """Compiler Directives: set an end-module directive, photograph the dialog, OK."""
    dlg.boxes['end_module_directives'].setPlainText('`undef HDLSTUDIO_TEST')
    dlg.grab().save(os.path.join(OUT, 'compdir.png'))
    click_button(dlg, 'OK')


before_undo = win.act_undo.isEnabled()
drive(sm_script)
win.toolbar_actions['sm_props'].trigger()
QTest.qWait(300)
drive(cd_script)
win.toolbar_actions['compiler_directives'].trigger()
QTest.qWait(300)
v = win.view
check('dialogs applied to the diagram', m.current_state_name == 'cs_q' and m.encoding == 'gray'
      and v.concurrent_statements == "assign probe = 1'b0;" and 'statereg' not in v.decl_hidden
      and v.registered_affix == '_reg' and v.end_module_directives == '`undef HDLSTUDIO_TEST')
check('one undo step', win.act_undo.isEnabled() and not before_undo)
check('title marks the change', win.windowTitle().find('*') >= 0, win.windowTitle())

# 3. save and read again ---------------------------------------------------------------------
warn = win.save_file()
QTest.qWait(300)
again = import_sm(path)
a = again.machines[0]
check('saved: current state name', a.current_state_name == 'cs_q', a.current_state_name)
check('saved: concurrent statements', again.concurrent_statements == "assign probe = 1'b0;")
check('saved: end-module directives', again.end_module_directives == '`undef HDLSTUDIO_TEST')
check('saved: block shown', 'statereg' not in again.decl_hidden, str(again.decl_hidden))
check('saved: registered affix', again.registered_affix == '_reg', again.registered_affix)
win.dirty = False
win.close()
print(f'{sum(results)}/{len(results)} passed; file {path}')
sys.exit(0 if all(results) else 1)
