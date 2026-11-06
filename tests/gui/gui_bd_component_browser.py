"""Add > Component (F3) as in the legacy tool: the floating Component Browser opens, and a unit dragged
from it with the real mouse onto the diagram is instantiated there (body bottom-left at the drop
point, named after the unit, selected). Uses the sample project D:/workspace/hds_reference
(only read). The drag is done by a second thread with pyautogui: QDrag blocks the Qt thread."""
import os, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
import pyautogui  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from bd_model import BlockDiagram  # noqa: E402
from gui import bd_editor  # noqa: E402
from project.project import open_project  # noqa: E402

SAMPLE = os.environ.get('HDLSTUDIO_SAMPLE_HDP', 'D:/workspace/hds_reference/dynamo_dsol.hdp')
app = QApplication(sys.argv)
fails = 0


def ok(name, cond):
    """Count and print one check: PASS / FAIL and its name."""
    global fails
    fails += not cond
    print(('PASS ' if cond else 'FAIL ') + name, flush=True)


proj = open_project(SAMPLE)
win = bd_editor.BdEditorWindow(BlockDiagram(library='dynamo_dsol', unit='t', language='verilog'))
win._project = lambda: proj
win.resize(1200, 800); win.move(400, 150); win.show(); QTest.qWait(400)
win.raise_(); win.activateWindow()

win.mode_actions['component'].trigger(); QTest.qWait(400)
br = getattr(win, '_browser', None)
ok('F3 opens the Component Browser', br is not None and br.isVisible())
br.move(50, 150); QTest.qWait(200)
top = br.tree.topLevelItem(0)
ok('the diagram library comes first, expanded', top is not None and top.text(0) == 'dynamo_dsol' and top.isExpanded())
unit = next(top.child(k) for k in range(top.childCount()) if top.child(k).text(0) == 'dynamo_sram')
br.tree.scrollToItem(unit); QTest.qWait(100)
r = br.tree.visualItemRect(unit)
src = br.tree.viewport().mapToGlobal(r.center())
drop_scene = QPointF(40 * bd_editor.GRID, 40 * bd_editor.GRID)
win.canvas.resetTransform(); win.canvas.centerOn(drop_scene); QTest.qWait(100)
dst = win.canvas.viewport().mapToGlobal(win.canvas.mapFromScene(drop_scene))


def drag():
    """Drag the unit from the Component Browser onto the diagram with the real mouse (pyautogui), in a thread."""
    time.sleep(0.5)
    pyautogui.moveTo(src.x(), src.y()); pyautogui.mouseDown(); time.sleep(0.2)
    for k in range(1, 25):
        pyautogui.moveTo(src.x() + (dst.x() - src.x()) * k / 24, src.y() + (dst.y() - src.y()) * k / 24)
        time.sleep(0.03)
    time.sleep(0.3); pyautogui.mouseUp()


n = len(win.bd.instances)
t = threading.Thread(target=drag); t.start()
for _ in range(60):                      # keep Qt running while the other thread drags
    QTest.qWait(100)
    if not t.is_alive():
        break
QTest.qWait(500)
inst = win.bd.instances[-1] if len(win.bd.instances) > n else None
ok(f'the dropped unit is instantiated ({inst.name if inst else None})', inst is not None and inst.unit == 'dynamo_sram')
if inst is not None:
    print(f'   bottom-left ({inst.x:.1f}, {inst.y + inst.h:.1f}) drop ({drop_scene.x():.1f}, {drop_scene.y():.1f})')
    ok('its bottom-left corner is at the drop point (grid)',
       abs(inst.x - drop_scene.x()) <= bd_editor.GRID and abs(inst.y + inst.h - drop_scene.y()) <= bd_editor.GRID)
    ok('it has the unit ports', len(inst.pins) > 0)
    ok('it is selected', any(getattr(i, 'obj', None) is inst for i in win.scene.selectedItems()))
win.canvas.grab().save(os.path.join(OUT, 'component_browser_drop.png'))
print('FAILS', fails)
win.dirty = False
br.close(); win.close()
sys.exit(1 if fails else 0)
