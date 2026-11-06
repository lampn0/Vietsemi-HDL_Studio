"""Move a component port by dragging it, or by dragging the end of its net (real diagram, nothing written)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
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


def drag(p0, p1, steps=8):
    """Drag with the left button from the first point to the second, in small mouse moves. Prints what grabbed the press."""
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p0)
    print('   grabber', type(sc.mouseGrabberItem()).__name__, 'pin drag', getattr(sc.mouseGrabberItem(), '_pin_drag', None) is not None)
    for k in range(1, steps + 1):
        QTest.mouseMove(vp, p0 + (p1 - p0) * k / steps); QTest.qWait(5)
        if pin is not None: print('   step', k, round(cv.mapToScene(p0 + (p1 - p0) * k / steps).y()), pin.y)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p1); QTest.qWait(80)


# a right-side port with a net to a PortIO (like bist_enable in the screenshot)
inst, pin, wire = None, None, None
for i in bd.instances:
    for q in i.pins:
        if q.side == 'right' and q.net:
            wr = next((x for x in bd.wires if f'pin:{i.id}:{q.name}' in (x.start, x.end)), None)
            free_below = not any(o is not q and o.side == 'right' and abs(o.y - q.y - 40) < 25 for o in i.pins)
            if wr is not None and free_below and q.y + 40 < i.y + i.h:
                inst, pin, wire = i, q, wr
                break
    if pin:
        break
print('  port:', inst.name, pin.name, pin.x, pin.y)
item = sc.items_by_id[inst.id]
x0, y0, ix, iy = pin.x, pin.y, inst.x, inst.y
cv.resetTransform(); cv.centerOn(pin.x, pin.y + 20); QTest.qWait(100)

# 1. click the port: it is selected, the component is not
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, cv.mapFromScene(QPointF(pin.x, pin.y))); QTest.qWait(50)
ok('click on a port selects the port', sc.selected_pin == (inst.id, pin.name) and not item.isSelected())
shot1 = vp.grab(cv.mapFromScene(QRectF(pin.x - 120, pin.y - 30, 360, 70)).boundingRect())

# 2. drag the port down: it slides along the edge, the component stays, the net follows
drag(cv.mapFromScene(QPointF(pin.x, pin.y)), cv.mapFromScene(QPointF(pin.x + 15, pin.y + 40)))
ok(f'port slid along the edge to y={pin.y:.0f} (x unchanged)', pin.x == x0 and abs(pin.y - (y0 + 40)) < 0.01)
ok('component did not move', (inst.x, inst.y) == (ix, iy))
end = wire.points[0] if wire.start == f'pin:{inst.id}:{pin.name}' else wire.points[-1]
ok('net end follows the port', abs(end[1] - pin.y) < 0.01)
ok('net stays orthogonal', ortho(wire.points))
ok('undoable', w.act_undo.isEnabled())
w.act_undo.trigger(); QTest.qWait(100)
inst = next(i for i in w.bd.instances if i.id == inst.id)
pin = next(q for q in inst.pins if q.name == pin.name)
ok('undo puts the port back', (pin.x, pin.y) == (x0, y0))

# 3. select the net, drag its end handle at the port: the port moves
wire = next(x for x in w.bd.wires if x.id == wire.id)
k = 0 if wire.start == f'pin:{inst.id}:{pin.name}' else -1
sc.clearSelection(); sc.wire_items[wire.id].setSelected(True)
ex, ey = wire.points[k]
mid = QPointF((wire.points[0][0] + wire.points[1][0]) / 2, wire.points[0][1])
shot2 = vp.grab(cv.mapFromScene(QRectF(pin.x - 120, pin.y - 30, 360, 70)).boundingRect())
# the handle sits on the port, where the component is on top: drag starts on the wire just beside it
p0 = cv.mapFromScene(QPointF(ex + (3 if k == 0 else -3), ey))
item_at = cv.itemAt(p0)
print('  item under the end handle:', type(item_at).__name__)
drag(p0, cv.mapFromScene(QPointF(ex + 3, ey + 30)))
ok(f'dragging the net end moved the port to y={pin.y:.0f}', abs(pin.y - (y0 + 30)) <= (1000 / 75) / 2 and pin.x == x0)
end = wire.points[0] if k == 0 else wire.points[-1]
ok('net end still on the port', abs(end[1] - pin.y) < 0.01)

pm = QPixmap(shot1.width() + shot2.width() + 10, max(shot1.height(), shot2.height())); pm.fill(Qt.white)
p = QPainter(pm); p.drawPixmap(0, 0, shot1); p.drawPixmap(shot1.width() + 10, 0, shot2); p.end(); pm.save(os.path.join(OUT, 'bd_pin_drag.png'))
w.dirty = False
_env.finish(fails)
