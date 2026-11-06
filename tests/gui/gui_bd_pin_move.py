"""Ports move to any edge; connected PortIOs follow; dragging a net moves its ports (real diagram, read only)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPointF, QRectF, Qt
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


def drag(p0, p1, steps=10):
    """Drag with the left button from the first point to the second, in small mouse moves."""
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p0)
    for k in range(1, steps + 1):
        QTest.mouseMove(vp, p0 + (p1 - p0) * k / steps); QTest.qWait(5)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p1); QTest.qWait(80)


def find(kind):
    """(instance, pin, wire, portio) for a right-side port whose net goes to a PortIO."""
    for i in bd.instances:
        for q in sorted(i.pins, key=lambda q: q.y):
            if q.side != 'right' or not q.net:
                continue
            wr = next((x for x in bd.wires if f'pin:{i.id}:{q.name}' in (x.start, x.end)), None)
            if wr is None:
                continue
            other = wr.end if wr.start == f'pin:{i.id}:{q.name}' else wr.start
            if kind == 'pio' and other.startswith('pio:') and not any(
                    o is not q and o.side == 'right' and 15 < o.y - q.y < 65 for o in i.pins) and q.y + 40 < i.y + i.h:
                return i, q, wr, sc.owner_of(other).obj
            if kind == 'pin' and other.startswith('pin:'):
                return i, q, wr, None
    return None


def end_of(wr, ref):
    """The point of wire `wr` at the end attached to `ref`."""
    return wr.points[0] if wr.start == ref else wr.points[-1]


# 1. move a port down: only the port moves, its net stretches; the PortIO at the other end stays
#    (dragging the net instead carries the PortIO, see gui_bd_pin_net_drag)
inst, pin, wire, pio = find('pio')
ref = f'pin:{inst.id}:{pin.name}'
y0, px0, py0 = pin.y, pio.x, pio.y
cv.resetTransform(); cv.centerOn(pin.x + 100, pin.y + 20); QTest.qWait(100)
drag(cv.mapFromScene(QPointF(pin.x, pin.y)), cv.mapFromScene(QPointF(pin.x, pin.y + 40)))
dy = pin.y - y0
ok(f'port moved down {dy:.0f}', abs(dy - 40) < .01)
ok(f'connected PortIO {pio.name} stays where it is', abs(pio.y - py0) < .01 and abs(pio.x - px0) < .01)
ok('net still joins port and PortIO, orthogonal', abs(end_of(wire, ref)[1] - pin.y) < .01 and ortho(wire.points))
w.act_undo.trigger(); QTest.qWait(100)
bd = w.bd
inst = next(i for i in bd.instances if i.id == inst.id); pin = next(q for q in inst.pins if q.name == pin.name)
wire = next(x for x in bd.wires if x.id == wire.id); pio = next(p for p in bd.port_ios if p.id == pio.id)

# 2. move the port onto the top edge of the component
cv.centerOn(inst.x + inst.w / 2, inst.y); QTest.qWait(100)
target = QPointF(inst.x + inst.w / 2, inst.y - 10)
cv.resetTransform(); cv.scale(0.5, 0.5); cv.centerOn(inst.x + inst.w / 2, (inst.y + pin.y) / 2); QTest.qWait(100)
drag(cv.mapFromScene(QPointF(pin.x, pin.y)), cv.mapFromScene(target), steps=20)
ok(f'port went to the {pin.side} edge at ({pin.x:.0f}, {pin.y:.0f})', pin.side == 'top' and abs(pin.y - (inst.y - 5)) < .01
   and inst.x < pin.x < inst.x + inst.w)
e = end_of(wire, ref)
nxt = wire.points[1] if wire.start == ref else wire.points[-2]
ok('net leaves the top edge straight up, orthogonal', abs(e[0] - pin.x) < .01 and abs(nxt[0] - pin.x) < .01
   and nxt[1] < e[1] and ortho(wire.points))
cv.resetTransform(); cv.scale(0.6, 0.6); cv.centerOn(inst.x + inst.w / 2, inst.y); QTest.qWait(100)
vp.grab().save(os.path.join(OUT, 'bd_pin_move.png'))
w.act_undo.trigger(); QTest.qWait(100)
bd = w.bd
inst = next(i for i in bd.instances if i.id == inst.id); pin = next(q for q in inst.pins if q.name == pin.name)
wire = next(x for x in bd.wires if x.id == wire.id); pio = next(p for p in bd.port_ios if p.id == pio.id)
ok('undo puts it back on the right edge', pin.side == 'right')

# 3. drag the net itself: its component port slides and the PortIO comes along
y0, py0 = pin.y, pio.y
a, b = wire.points[0], wire.points[1]
mid = QPointF((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
cv.resetTransform(); cv.centerOn(mid); QTest.qWait(100)
sc.clearSelection()
drag(cv.mapFromScene(mid), cv.mapFromScene(QPointF(mid.x(), mid.y() + 40)))
ok(f'dragging the net moved the port by {pin.y - y0:.0f}', abs(pin.y - y0 - 40) < .01 and pin.side == 'right')
ok('and the PortIO by the same amount', abs(pio.y - py0 - 40) < .01)
ok('net orthogonal', ortho(wire.points))
w.act_undo.trigger(); QTest.qWait(100)

# 4. a net between two components: both ports slide
found = find('pin')
if found:
    inst, pin, wire, _ = found
    bd = w.bd
    ends = [(r, sc.owner_of(r).obj) for r in (wire.start, wire.end)]
    pins = [next(q for q in o.pins if f'pin:{o.id}:{q.name}' == r) for r, o in ends]
    ys = [q.y for q in pins]
    pts = wire.points
    seg = next(k for k in range(len(pts) - 1) if abs(pts[k][1] - pts[k + 1][1]) < .01)
    mid = QPointF((pts[seg][0] + pts[seg + 1][0]) / 2, pts[seg][1])
    cv.resetTransform(); cv.centerOn(mid); QTest.qWait(100)
    drag(cv.mapFromScene(mid), cv.mapFromScene(QPointF(mid.x(), mid.y() + 20)))
    moved = [q.y - y for q, y in zip(pins, ys)]
    ok(f'component-to-component net: both ports moved {moved}', all(abs(m - 20) < .01 for m in moved))
    ok('net orthogonal', ortho(wire.points))
w.dirty = False
_env.finish(fails)
