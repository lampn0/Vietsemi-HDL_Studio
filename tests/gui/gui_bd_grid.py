"""Port drags keep nets straight out of the port; everything moved lands on the legacy grid."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from formats.import_bd import import_bd
from formats.import_sm import import_sm
from gui import bd_editor
from gui.diagram import GRID, StateItem
from gui.main_window import MainWindow

app = QApplication(sys.argv)
fails = 0


def ok(name, cond):
    """Count and print one check: PASS / FAIL and its name."""
    global fails
    fails += not cond
    print(('PASS ' if cond else 'FAIL ') + name, flush=True)
on = lambda v: abs(v / GRID - round(v / GRID)) < 1e-6
SIDE_OUT = {'left': (-1, 0), 'right': (1, 0), 'top': (0, -1), 'bottom': (0, 1)}


def drag(vp, cv, a, b, steps=16, check=None):
    """Drag between two scene points in `steps` moves; `check()` is called after each move and its complaints are collected."""
    bad = []
    p0, p1 = cv.mapFromScene(a), cv.mapFromScene(b)
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p0)
    for k in range(1, steps + 1):
        QTest.mouseMove(vp, p0 + (p1 - p0) * k / steps); QTest.qWait(5)
        if check:
            r = check()
            if r:
                bad.append((k, r))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p1); QTest.qWait(80)
    return bad


# ---- block diagram
bd = import_bd(_env.legacy_bd('libs/protocol_controller/hds/pc_global_controller/struct.bd'))
w = bd_editor.BdEditorWindow(bd); w.resize(1400, 900); w.show(); QTest.qWait(300)
sc, cv, vp = w.scene, w.canvas, w.canvas.viewport()
inst = next(i for i in bd.instances if i.name == 'gc_control_fsm')
pin = next(q for q in inst.pins if q.name == 'clk')
net = next(x for x in bd.wires if f'pin:{inst.id}:clk' in (x.start, x.end))
ref = f'pin:{inst.id}:clk'


def net_problem():
    """What is wrong with the net of the dragged port ('' when it leaves the port straight and stays orthogonal)."""
    pts = net.points if net.start == ref else list(reversed(net.points))
    if pts[0] != bd_editor.pin_end(pin):
        return 'not on the port'
    o = SIDE_OUT[pin.side]
    d = (pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
    if d[0] * o[1] != d[1] * o[0] or d[0] * o[0] + d[1] * o[1] <= 0:
        return f'enters the side of the arrow {pts[:3]}'
    if not all(abs(a[0] - b[0]) < .01 or abs(a[1] - b[1]) < .01 for a, b in zip(pts, pts[1:])):
        return 'slanted'
    body = QRectF(inst.x + 1, inst.y + 1, inst.w - 2, inst.h - 2)
    for a, b in zip(pts, pts[1:]):
        if body.contains(QPointF((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)) or body.contains(QPointF(*b)):
            return 'through the component'
    return None


cv.resetTransform(); cv.scale(0.7, 0.7); cv.centerOn(inst.x + 100, inst.y); QTest.qWait(100)
bad = drag(vp, cv, QPointF(pin.x, pin.y), QPointF(inst.x + 100, inst.y - 10), check=net_problem)
ok(f'port to the top edge: net straight out of the port at every step {bad[:2]}', not bad and pin.side == 'top')
ok(f'port on the grid along the edge ({pin.x:.2f})', on(pin.x))
shot1 = vp.grab(cv.mapFromScene(QRectF(inst.x - 300, inst.y - 120, 600, 260)).boundingRect())
bad = drag(vp, cv, QPointF(pin.x, pin.y), QPointF(inst.x + inst.w - 40, inst.y - 10), check=net_problem)
ok(f'along the top edge {bad[:2]}', not bad)
bad = drag(vp, cv, QPointF(pin.x, pin.y), QPointF(inst.x + inst.w + 10, inst.y + 60), check=net_problem)
ok(f'round to the right edge (PortIO now behind the port) {bad[:2]}', not bad and pin.side == 'right')
shot2 = vp.grab(cv.mapFromScene(QRectF(inst.x - 300, inst.y - 120, inst.w + 500, 300)).boundingRect())

t = time.perf_counter()
for k in range(100):
    sc.move_pin(sc.items_by_id[inst.id], pin, *sc.items_by_id[inst.id].pin_target(pin, pin.x, pin.y, pin.side, 0,
                                                                                    GRID * (1 if k % 2 else -1)))
ms = (time.perf_counter() - t) * 10
ok(f'a port drag step costs {ms:.2f} ms', ms < 2)

# component and PortIO moves land on the grid
other = next(i for i in w.bd.instances if i.name == 'gc_final_mux')
c = QPointF(other.x + other.w / 2, other.y + other.h / 2)
cv.centerOn(c); QTest.qWait(50)
drag(vp, cv, c, c + QPointF(17, 23))
ok(f'component moved onto the grid ({other.x:.2f}, {other.y:.2f})', on(other.x) and on(other.y))
pio = w.bd.port_ios[0]
cv.centerOn(pio.x, pio.y); QTest.qWait(50)
drag(vp, cv, QPointF(pio.x, pio.y), QPointF(pio.x + 9, pio.y + 31))
ok(f'PortIO moved onto the grid ({pio.x:.2f}, {pio.y:.2f})', on(pio.x) and on(pio.y))
w.dirty = False

# ---- state diagram
view = import_sm(_env.legacy_bd('libs/protocol_controller/hds/gc_control_fsm/fsm.sm'))
f = MainWindow(view); f.resize(1300, 900); f.show(); QTest.qWait(300)
st = f.machine.states[0]
fcv, fvp = f.canvas, f.canvas.viewport()
fcv.resetTransform(); fcv.centerOn(st.x, st.y); QTest.qWait(50)
drag(fvp, fcv, QPointF(st.x, st.y), QPointF(st.x + 21, st.y + 8))
ok(f'state moved onto the grid ({st.x:.2f}, {st.y:.2f})', on(st.x) and on(st.y) and (st.x, st.y) != (0, 0))
ok(f'grid dots spaced like the legacy grid ({fcv.grid:.3f})', abs(fcv.grid - 1000 / 75) < 1e-9)
f.dirty = False

pm = QPixmap(shot1.width() + shot2.width() + 10, max(shot1.height(), shot2.height())); pm.fill(Qt.white)
pt = QPainter(pm); pt.drawPixmap(0, 0, shot1); pt.drawPixmap(shot1.width() + 10, 0, shot2); pt.end()
pm.save(os.path.join(OUT, 'bd_grid.png'))
_env.finish(fails)
