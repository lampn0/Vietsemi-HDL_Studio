"""Port drag moves only the port; net drag carries port and PortIO; route points merge when in line."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPointF, Qt
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


def drag(p0, p1, steps=12):
    """Drag with the left button from the first point to the second, in small mouse moves."""
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p0)
    for k in range(1, steps + 1):
        QTest.mouseMove(vp, p0 + (p1 - p0) * k / steps); QTest.qWait(5)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p1); QTest.qWait(80)


def pick():
    """A right-side component port with a net, to drag in the test."""
    for i in w.bd.instances:
        for q in sorted(i.pins, key=lambda q: q.y):
            wr = next((x for x in w.bd.wires if f'pin:{i.id}:{q.name}' in (x.start, x.end)), None)
            if q.side == 'right' and wr is not None and \
                    (wr.end if wr.start == f'pin:{i.id}:{q.name}' else wr.start).startswith('pio:') and \
                    not any(o is not q and o.side == 'right' and 15 < o.y - q.y < 65 for o in i.pins) and \
                    q.y + 40 < i.y + i.h:
                other = wr.end if wr.start == f'pin:{i.id}:{q.name}' else wr.start
                return i, q, wr, sc.owner_of(other).obj
    return None


def reset():
    """Undo the last drag and pick the port again."""
    w.act_undo.trigger(); QTest.qWait(100)
    return pick()


def end_of(wr, ref):
    """The point of wire `wr` at the end attached to `ref`."""
    return wr.points[0] if wr.start == ref else wr.points[-1]


inst, pin, wire, pio = pick()
ref = f'pin:{inst.id}:{pin.name}'

# A. drag the port: only the port moves, the PortIO stays and the net stretches
y0, pp = pin.y, (pio.x, pio.y)
cv.resetTransform(); cv.centerOn(pin.x + 100, pin.y + 20); QTest.qWait(100)
drag(cv.mapFromScene(QPointF(pin.x, pin.y)), cv.mapFromScene(QPointF(pin.x, pin.y + 40)))
ok(f'port moved {pin.y - y0:.0f}', abs(pin.y - y0 - 40) < .01)
ok('PortIO stayed where it was', (pio.x, pio.y) == pp)
ok('net stretched: joins the port, orthogonal', abs(end_of(wire, ref)[1] - pin.y) < .01 and ortho(wire.points))
inst, pin, wire, pio = reset()

# B. drag the port onto the bottom edge: it leaves the edge straight down, PortIO stays
pp = (pio.x, pio.y)
cv.resetTransform(); cv.scale(0.5, 0.5); cv.centerOn(inst.x + inst.w / 2, inst.y + inst.h); QTest.qWait(100)
drag(cv.mapFromScene(QPointF(pin.x, pin.y)), cv.mapFromScene(QPointF(pin.x - 30, inst.y + inst.h + 8)), steps=25)
e = end_of(wire, ref); nxt = wire.points[1] if wire.start == ref else wire.points[-2]
ok(f'port on the {pin.side} edge', pin.side == 'bottom')
ok('net leaves straight down', abs(nxt[0] - pin.x) < .01 and nxt[1] > e[1])
ok('PortIO stayed, net orthogonal to it', (pio.x, pio.y) == pp and ortho(wire.points))
vp.grab().save(os.path.join(OUT, 'bd_pin_net_drag.png'))
inst, pin, wire, pio = reset()

# C. drag the net: the port slides and the PortIO comes along
y0, py0 = pin.y, pio.y
a, b = wire.points[0], wire.points[1]
mid = QPointF((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
cv.resetTransform(); cv.centerOn(mid); QTest.qWait(100); sc.clearSelection()
drag(cv.mapFromScene(mid), cv.mapFromScene(QPointF(mid.x(), mid.y() + 40)))
ok(f'net drag moved the port {pin.y - y0:.0f} and the PortIO {pio.y - py0:.0f}',
   abs(pin.y - y0 - 40) < .01 and abs(pio.y - py0 - 40) < .01)
inst, pin, wire, pio = reset()

# D. route points: drag a black square into line with its neighbours -> it merges
wire.points = [list(wire.points[0]), [wire.points[0][0] + 60, wire.points[0][1]],
               [wire.points[0][0] + 60, wire.points[0][1] - 40], [wire.points[0][0] + 120, wire.points[0][1] - 40],
               [wire.points[0][0] + 120, wire.points[0][1]], list(wire.points[-1])]
sc.wire_items[wire.id].refresh()
n0 = len(wire.points)
sc.clearSelection(); sc.wire_items[wire.id].setSelected(True)
p2 = QPointF(*wire.points[2])
cv.resetTransform(); cv.centerOn(p2); QTest.qWait(100)
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, cv.mapFromScene(p2))
print('  grabber', type(sc.mouseGrabberItem()).__name__, getattr(sc.mouseGrabberItem(), '_drag', None) and sc.mouseGrabberItem()._drag[:2])
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, cv.mapFromScene(p2)); QTest.qWait(50)
print('  pts before', wire.points)
drag(cv.mapFromScene(p2), cv.mapFromScene(QPointF(p2.x(), p2.y() + 40)))
print('  pts after', wire.points)
print('  points after dragging handle 2 into line:', len(wire.points), 'was', n0)
ok('route point dragged into line merges', len(wire.points) < n0)
p3 = QPointF(*wire.points[2]) if len(wire.points) > 3 else None
if p3 is not None:
    drag(cv.mapFromScene(p3), cv.mapFromScene(QPointF(p3.x(), p3.y() + 40)))
print('  points now:', wire.points)
ok('net straight again: just its two ends', len(wire.points) == 2)
w.dirty = False
_env.finish(fails)
