"""Real app path, visible window: port ghost + attach, new embedded block + view + text, wire to block."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import Qt, QPoint, QPointF, QTimer
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QDialog
from PySide6.QtTest import QTest
app = QApplication(sys.argv)
from gui.design_manager import DesignManager
from gui.bd_editor import EmbeddedItem, EmbeddedViewDialog
dm = DesignManager(); dm.show(); dm.load_project(HDP); app.processEvents()
lib = dm.project.library('dti_hbm'); lib.scan(dm.project.cache)
du = lib.units['dynamo_core']; dm.open_view(du, du.graphic_view()); app.processEvents()
win = next(iter(dm.editors.values())); win.resize(1400, 900); win.raise_(); win.activateWindow(); app.processEvents()
sc = win.scene; vp = win.canvas.viewport(); out = OUT
fails = 0
def check(ok, what):
    """Count and print one check: PASS / FAIL and its name."""
    global fails; fails += not ok; print('PASS' if ok else 'FAIL', what)
win.canvas.resetTransform(); win.canvas.scale(1.5, 1.5)
# 1) port in: ghost, then a click on a dangling net end attaches a port named after the net
w = next(w for w in win.bd.wires if w.net == 'dram_cmd_rdy' and (not w.start or not w.end))
which = 'start' if not w.start else 'end'
end = QPointF(*(w.points[0] if which == 'start' else w.points[-1]))
win.canvas.centerOn(end); app.processEvents(); QTest.qWait(200)
win.set_mode('port_in'); app.processEvents()
from PySide6.QtCore import QEvent
from PySide6.QtGui import QMouseEvent
mp = win.canvas.mapFromScene(end + QPointF(60, 40))
QApplication.sendEvent(vp, QMouseEvent(QEvent.MouseMove, QPointF(mp), QPointF(vp.mapToGlobal(mp)), Qt.NoButton, Qt.NoButton, Qt.NoModifier)); QTest.qWait(200)
check(sc._ghost is not None and getattr(sc._ghost[1], 'ghost', False),
      'adding a port shows its outline under the cursor (as the legacy tool)')
win.canvas.grab().save(out + '/ghost.png')
n_pio = len(win.bd.port_ios)
from gui.bd_editor import PORT_EDGE
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, win.canvas.mapFromScene(end)); QTest.qWait(300)   # the cursor is the preview's wire end (as the legacy tool): on the net end
pio = win.bd.port_ios[-1] if len(win.bd.port_ios) > n_pio else None
w = next(x for x in win.bd.wires if x.id == w.id)
check(pio is not None and pio.name == 'dram_cmd_rdy', f'click on the net end adds port "{pio.name if pio else None}"')
check(pio is not None and getattr(w, which) == f'pio:{pio.id}', 'the net is attached to the new port')
check(sc.port_side(pio) == (1 if (w.points[1][0] if which == 'start' else w.points[-2][0]) > pio.x else -1), 'the port faces its net')
win.canvas.grab().save(out + '/port_on_net.png')
# 2) new embedded block in empty space, then double-click: Create Embedded View -> Text
win.set_mode('embedded'); app.processEvents()
spot = QPointF(end.x() + 200, end.y() + 150)
win.canvas.centerOn(spot); app.processEvents(); QTest.qWait(200)
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, win.canvas.mapFromScene(spot)); QTest.qWait(300)
eb = win.bd.embedded[-1]
check(eb.text == '' and eb.text_box is None, f'new embedded block {eb.name} is empty (no view yet)')
win.canvas.grab().save(out + '/emb_new.png')
seen = []
def accept_dialog():
    """Wait for the Create Embedded View dialog (polling), save its picture and press OK."""
    d = next((x for x in QApplication.topLevelWidgets() if isinstance(x, EmbeddedViewDialog) and x.isVisible()), None)
    if d is None:
        QTimer.singleShot(100, accept_dialog); return
    seen.append(d.windowTitle()); d.grab().save(out + '/emb_dialog.png'); d.accept()
QTimer.singleShot(200, accept_dialog)
item = sc.items_by_id[eb.id]
win.set_mode('select')            # Esc: Add Embedded Block stays active after a placement, as in the legacy tool
win.raise_(); win.activateWindow(); QTest.qWaitForWindowActive(win, 2000)   # the in-place editor closes when focus leaves
QTest.mouseDClick(vp, Qt.LeftButton, Qt.NoModifier, win.canvas.mapFromScene(item.body().center())); QTest.qWait(400)
eb = next(e for e in win.bd.embedded if e.id == eb.id)
check(seen == ['Create Embedded View'], 'double-click on the yellow block opens Create Embedded View')
check(eb.text_box is not None and eb.text.startswith(f'// {eb.name}'), f'Text view created: {eb.text!r}')
ed = next((x for x in vp.findChildren(QPlainTextEdit) if x.isVisible()), None)
check(ed is not None, 'the text is edited in place right away')
if ed:
    ed.setPlainText('assign y = a;\n'); win.canvas.setFocus(); QTest.qWait(300)
eb = next(e for e in win.bd.embedded if e.id == eb.id)
check(eb.text == 'assign y = a;\n', 'leaving the text box keeps the text')
win.canvas.grab().save(out + '/emb_text.png')
# 3) wire tool: from a port to the new block -> attached to the block, entering it (input)
win.set_mode('wire'); app.processEvents()
item = sc.items_by_id[eb.id]
pp = QPointF(*sc.port_edge(pio))
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, win.canvas.mapFromScene(pp)); QTest.qWait(100)
target = QPointF(item.body().left() + 5, item.body().center().y())
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, win.canvas.mapFromScene(target)); QTest.qWait(300)
nw = win.bd.wires[-1]
check(nw.end == f'emb:{eb.id}' and nw.net == 'dram_cmd_rdy', f'the wire ends on the block ({nw.start} -> {nw.end})')
b = sc.items_by_id[eb.id].body()
check(abs(nw.points[-1][0] - b.left()) < 0.01, 'its end is on the block edge')
win.set_mode('select'); win.canvas.centerOn(b.center()); app.processEvents(); QTest.qWait(200)
win.canvas.grab().save(out + '/emb_wired.png')
print('FAILS', fails)
_env.finish(fails)
