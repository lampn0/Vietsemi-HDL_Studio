"""Frame popup menu, Object Properties dialog, resize handles, copy/paste (real diagram, nothing written)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu
from formats.import_bd import import_bd
from gui import bd_editor, bd_dialogs
from codegen.bd_codegen import generate_bd

app = QApplication(sys.argv)
fails = 0


def ok(name, cond):
    """Count and print one check: PASS / FAIL and its name."""
    global fails
    fails += not cond
    print(('PASS ' if cond else 'FAIL ') + name, flush=True)
bd = import_bd(_env.legacy_bd('libs/protocol_controller/hds/protocol_controller/struct.bd'))
bd.language = 'verilog'
w = bd_editor.BdEditorWindow(bd); w.resize(1500, 950); w.show(); QTest.qWait(300)
sc, cv, vp = w.scene, w.canvas, w.canvas.viewport()
fr_item = next(it for it in sc.items_by_id.values() if isinstance(it, bd_editor.FrameItem) and it.obj.name == 'ps_chan_num')
fr = fr_item.obj
cv.resetTransform(); cv.centerOn(fr.x + fr.w / 2, fr.y + 60); QTest.qWait(100)

# right-click on the dashed border: the frame popup
captured = []
orig_exec = QMenu.exec
def fake_exec(menu, *a, **k):
    """Stand-in for QMenu.exec: record the entries and a picture of the menu, show nothing."""
    captured.append([x.text().replace('&', '') or '-' for x in menu.actions()])
    shots.append(menu.grab())
    return None
shots = []
class CaptureMenu(QMenu):
    """A QMenu whose exec() only records the menu (see fake_exec)."""
    def exec(self, *a, **k):
        """Record the menu instead of showing it."""
        return fake_exec(self)
bd_editor.QMenu = CaptureMenu
border = cv.mapFromScene(QPointF(fr.x + fr.w / 2, fr.y))
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, border); QTest.qWait(50)
ok('click on the dashed border selects the frame', fr_item.isSelected())
sc.context_requested.emit(fr_item, vp.mapToGlobal(border), QPointF(fr.x + fr.w / 2, fr.y))
bd_editor.QMenu = QMenu
print('  menu:', captured[0] if captured else None)
ok('frame popup as in the legacy tool', captured and captured[0] == ['Cut', 'Copy', 'Paste', 'Delete', '-', 'Appearance...',
                                                        'Object Properties...'])

# Object Properties dialog: change range and label, apply
def drive():
    """Check and change the open Frame Properties dialog, then press OK."""
    dlg = next(x for x in app.topLevelWidgets() if isinstance(x, bd_dialogs.FramePropertiesDialog) and x.isVisible())
    shots.append(dlg.grab())
    ok(f'dialog shows style/label/number/range ({dlg.style.currentText()}, {dlg.label.currentText()}, '
       f'{dlg.number.text()}, {dlg.left.text()}:{dlg.right.text()})',
       (dlg.style.currentText(), dlg.label.currentText(), dlg.left.text(), dlg.right.text())
       == ('FOR', 'ps_chan_num', 'PS_CHAN_NUM - 1', '0'))
    dlg.left.setText('PS_CHAN_NUM - 2'); dlg.label.setCurrentText('chan'); dlg.number_vis.setChecked(False)
    dlg.accept()
QTimer.singleShot(300, drive)
w.properties_of_selection(); QTest.qWait(100)
fr = next(f for f in w.bd.frames if f.name == 'chan')
ok(f'properties applied: {fr.title}, number visible={fr.show_number}', fr.spec == '[PS_CHAN_NUM - 2:0]' and not fr.show_number)
text, _ = generate_bd(w.bd)
ok('instance array uses the new range', 'pc_bg_controller_array[PS_CHAN_NUM - 2:0](' in text)

# resize with the bottom-right handle: contents stay, frame grows
fr_item = next(it for it in sc.items_by_id.values() if isinstance(it, bd_editor.FrameItem) and it.obj.name == 'chan')
fr_item.setSelected(True)
inst = next(i for i in w.bd.instances if i.name == 'pc_bg_controller_array'); ix = (inst.x, inst.y)
w0, h0, x0, y0 = fr.w, fr.h, fr.x, fr.y
cv.centerOn(fr.x + fr.w, fr.y + fr.h); QTest.qWait(100)
p0 = cv.mapFromScene(QPointF(fr.x + fr.w, fr.y + fr.h))
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p0)
for k in range(1, 9):
    QTest.mouseMove(vp, p0 + QPoint(6 * k, 5 * k)); QTest.qWait(5)
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p0 + QPoint(48, 40)); QTest.qWait(80)
ok(f'resize: {w0:.0f}x{h0:.0f} -> {fr.w:.0f}x{fr.h:.0f}, corner fixed', fr.w > w0 and fr.h > h0 and (fr.x, fr.y) == (x0, y0))
ok('resize leaves contents where they are', (inst.x, inst.y) == ix)
ok('resize is undoable', w.act_undo.isEnabled())

# copy / paste a frame
sc.clearSelection(); fr_item = next(it for it in sc.items_by_id.values() if isinstance(it, bd_editor.FrameItem) and it.obj.name == 'chan')
fr_item.setSelected(True); w.copy(); w.paste(QPointF(3000, 3000))
names = [f.name for f in w.bd.frames]
ok(f'paste adds a frame with a new label: {names}', 'chan_1' in names)

pm = QPixmap(1200, 420); pm.fill(Qt.white); p = QPainter(pm)
x = 0
for s in shots:
    p.drawPixmap(x, 0, s); x += s.width() + 10
p.end(); pm.save(os.path.join(OUT, 'bd_frame_props.png'))
w.dirty = False
_env.finish(fails)
