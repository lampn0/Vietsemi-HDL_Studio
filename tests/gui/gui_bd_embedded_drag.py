"""Dragging the end of a net on an embedded block slides it along the block edge; dragging the
yellow frame moves the block. Imports the legacy dynamo_core diagram (read only)."""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
app = QApplication(sys.argv)
from formats.import_bd import import_bd
from gui.bd_editor import BdEditorWindow, EmbeddedItem
found = None
for f in [_env.legacy_bd('hds/dynamo_core/struct.bd')]:
    bd = import_bd(f)
    for w in bd.wires:
        if w.end.startswith('emb:') or w.start.startswith('emb:'):
            found = (f, bd, w); break
    if found: break
f, bd, w = found
which = 'end' if w.end.startswith('emb:') else 'start'
print(os.path.basename(os.path.dirname(f)), w.net, which)
win = BdEditorWindow(bd); win.resize(1200, 800); win.show(); app.processEvents()
win.canvas.resetTransform(); win.canvas.scale(2, 2)
emb_id = (w.end if which == 'end' else w.start).split(':')[1]
item = win.scene.items_by_id[emb_id]; eb = item.obj
end = w.points[-1] if which == 'end' else w.points[0]
win.canvas.centerOn(QPointF(*end)); app.processEvents()
vp = win.canvas.viewport(); fails = 0
def check(ok, what):
    """Count and print one check: PASS / FAIL and its name."""
    global fails; fails += not ok; print('PASS' if ok else 'FAIL', what)
side = item.edge_side(*end)
bx, by = eb.x, eb.y
pt = win.canvas.mapFromScene(QPointF(*end))
step = QPoint(0, 20) if side in ('left', 'right') else QPoint(20, 0)
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, pt)
for k in range(1, 5):
    QTest.mouseMove(vp, pt + step * k / 4)
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, pt + step); app.processEvents()
new_end = w.points[-1] if which == 'end' else w.points[0]
check((eb.x, eb.y) == (bx, by), 'embedded block stayed')
check(new_end != list(end), f'net end moved {end} -> {new_end}')
check(item.edge_side(*new_end) == side and (w.end if which == 'end' else w.start) == f'emb:{emb_id}', 'still on the same edge, still attached')
ok_ortho = all(abs(a[0] - b[0]) < .01 or abs(a[1] - b[1]) < .01 for a, b in zip(w.points, w.points[1:]))
check(ok_ortho, 'net keeps right angles')
# a press inside the block, away from net ends, still moves the block
c = item.body().topLeft() + QPointF(6, 6); win.canvas.centerOn(c); app.processEvents(); pc = win.canvas.mapFromScene(c)   # the yellow frame, not the Text view
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, pc)
for k in range(1, 5):
    QTest.mouseMove(vp, pc + QPoint(10 * k, 0))
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, pc + QPoint(40, 0)); app.processEvents()
check(eb.x != bx, 'a drag on the yellow frame moves the block')
print('FAILS', fails)
_env.finish(fails)
