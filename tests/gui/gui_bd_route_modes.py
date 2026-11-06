"""Dragging a PortIO: routing modes cycled with 'z', hint shown (real diagram, nothing written)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from formats.import_bd import import_bd
from gui import bd_editor

app = QApplication(sys.argv)
fails = 0


def ok(name, cond):
    """Count and print one check: PASS / FAIL and its name."""
    global fails
    fails += not cond
    print(('PASS ' if cond else 'FAIL ') + name, flush=True)
bd = import_bd(_env.legacy_bd('libs/protocol_controller/hds/pc_global_controller/struct.bd'))
w = bd_editor.BdEditorWindow(bd); w.resize(1400, 900); w.show(); QTest.qWait(300)
sc, cv, vp = w.scene, w.canvas, w.canvas.viewport()
ortho = lambda pts: all(abs(a[0] - b[0]) < .01 or abs(a[1] - b[1]) < .01 for a, b in zip(pts, pts[1:]))

# a PortIO right of a component, joined to one of its right-side ports
pio = wire = inst = None
for p in bd.port_ios:
    for wr, which in sc._attached(f'pio:{p.id}'):
        other = wr.end if which == 'start' else wr.start
        owner = sc.owner_of(other)
        if isinstance(owner, bd_editor.InstanceItem) and p.x > owner.obj.x + owner.obj.w:
            pio, wire, inst = p, wr, owner.obj
            break
    if pio:
        break
print('  PortIO', pio.name, 'on', inst.name)
item = sc.items_by_id[pio.id]
cv.resetTransform(); cv.scale(0.8, 0.8)
target = QPointF(inst.x + inst.w - 40, inst.y + inst.h + 60)     # below the component, to its left
cv.centerOn((pio.x + target.x()) / 2, (pio.y + target.y()) / 2); QTest.qWait(100)
p0 = cv.mapFromScene(QPointF(pio.x, pio.y)); p1 = cv.mapFromScene(target)
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p0)
for k in range(1, 16):
    QTest.mouseMove(vp, p0 + (p1 - p0) * k / 15); QTest.qWait(5)
hint = sc._hint
ok(f'hint shown: {hint.text()!r}' if hint else 'hint shown', hint is not None and hint.isVisible()
   and hint.text() == "Press 'z' to change routing\nCurrent mode: River")
shots = []
area = QRectF(min(inst.x + inst.w - 200, target.x() - 60), min(pio.y, inst.y + inst.h) - 60, 700, 300)


def snap(label):
    """Keep a labelled picture of the area under test."""
    r = cv.mapFromScene(area).boundingRect()
    shots.append((label, vp.grab(r)))


snap('River')
results = {}
for expect in ('Avoidance', 'Diagonal', 'Dog Leg', 'River'):
    QTest.keyClick(cv, Qt.Key_Z); QTest.qWait(50)
    results[expect] = [list(p) for p in wire.points]
    ok(f'z -> {sc.route_mode}', sc.route_mode == expect and hint.text().endswith(expect))
    if expect != 'River':
        snap(expect)
pts = results['Avoidance']
rect = QRectF(inst.x, inst.y, inst.w, inst.h)
inside = [p for a, b in zip(pts, pts[1:]) for p in (QPointF((a[0] + b[0]) / 2, (a[1] + b[1]) / 2),) if rect.contains(p)]
ok(f'Avoidance: right angles around the component ({len(pts)} points)', ortho(pts) and not inside)
ok('Diagonal: one straight line', len(results['Diagonal']) == 2)
ok(f'Dog Leg: one corner {results["Dog Leg"]}', len(results['Dog Leg']) == 3 and ortho(results['Dog Leg']))
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p1); QTest.qWait(80)
ok('hint hidden after the drag', not hint.isVisible())
ok('undoable', w.act_undo.isEnabled())

# dragging a component shows no hint
c = cv.mapFromScene(QPointF(inst.x + inst.w / 2, inst.y + inst.h / 2))
cv.centerOn(inst.x + inst.w / 2, inst.y + inst.h / 2); QTest.qWait(50)
c = cv.mapFromScene(QPointF(inst.x + inst.w / 2, inst.y + inst.h / 2))
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, c)
for k in range(1, 6):
    QTest.mouseMove(vp, c + (c - c) + QPointF(0, 6 * k).toPoint()); QTest.qWait(5)
ok('no routing hint when dragging a component', not (sc._hint and sc._hint.isVisible()))
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, c + QPointF(0, 30).toPoint())

W = sum(s.width() for _, s in shots) + 10 * len(shots)
pm = QPixmap(W, max(s.height() for _, s in shots) + 20); pm.fill(Qt.white)
pt = QPainter(pm); x = 0
for label, s in shots:
    pt.drawText(x + 4, 14, label); pt.drawPixmap(x, 20, s); x += s.width() + 10
pt.end(); pm.save(os.path.join(OUT, 'bd_route_modes.png'))
w.dirty = False
_env.finish(fails)
