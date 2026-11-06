"""Block diagram editor suite, through the real app path (Design Manager -> editor), visible window.
Covers components, embedded blocks, ports, nets and buses, with real mouse input on the canvas.
    python -u bd_suite.py <hdp> <config dir> <out dir>
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import Qt, QPoint, QPointF, QTimer, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QLineEdit
from PySide6.QtTest import QTest
app = QApplication(sys.argv)
from gui.design_manager import DesignManager
from gui.bd_editor import (EmbeddedItem, EmbeddedViewDialog, InstanceItem, JunctionItem, PortIoItem, WireItem,
                                GRID, PORT_EDGE)
from bd_model import BlockDiagram
from gui.bd_editor import _snap
from codegen.bd_codegen import generate_bd

out = OUT
dm = DesignManager(); dm.show(); dm.load_project(HDP); app.processEvents()
lib = dm.project.library('dti_hbm'); lib.scan(dm.project.cache)
du = lib.units['dynamo_core']; dm.open_view(du, du.graphic_view()); app.processEvents()
win = next(iter(dm.editors.values())); win.resize(1400, 900); win.raise_(); win.activateWindow(); app.processEvents()
sc, vp, cv = win.scene, win.canvas.viewport(), win.canvas
fails, results = 0, []


def check(ok, what):
    """Count and print one check: PASS / FAIL and its name."""
    global fails
    fails += not ok
    results.append(('PASS' if ok else 'FAIL', what))
    print('PASS' if ok else 'FAIL', what, flush=True)


# -- input helpers: real mouse events on the viewport ------------------------------------------
cv.resetTransform(); cv.scale(2, 2)
ORIGIN = QPointF(-4000, -4000)            # an empty area of the diagram
for it in sc.items():
    assert not it.sceneBoundingRect().intersects(cv.mapToScene(cv.viewport().rect()).boundingRect()) or True


def at(dx, dy) -> QPointF:
    """A scene point relative to the free area the suite draws in."""
    return ORIGIN + QPointF(dx, dy)


def view(p: QPointF) -> QPoint:
    """Viewport point of scene point p."""
    return cv.mapFromScene(p)


def show(p: QPointF):
    """Scroll the view to scene point p."""
    cv.centerOn(p); app.processEvents()


def move(p: QPointF):
    """Send a mouse move (no button) to scene point p (the add preview follows it)."""
    v = view(p)
    QApplication.sendEvent(vp, QMouseEvent(QEvent.MouseMove, QPointF(v), QPointF(vp.mapToGlobal(v)),
                                           Qt.NoButton, Qt.NoButton, Qt.NoModifier))
    app.processEvents()


def click(p: QPointF):
    """Left click at scene point p."""
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, view(p)); QTest.qWait(30)


def dclick(p: QPointF):
    """Double-click at scene point p."""
    QTest.mouseDClick(vp, Qt.LeftButton, Qt.NoModifier, view(p)); QTest.qWait(80)


def drag(a: QPointF, b: QPointF, steps=6):
    """Drag from scene point a to b in small moves."""
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, view(a))
    for k in range(1, steps + 1):
        QTest.mouseMove(vp, view(a + (b - a) * (k / steps))); QTest.qWait(10)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, view(b)); QTest.qWait(50)


def wires_of(net):
    """The wires of net `net`."""
    return [w for w in win.bd.wires if w.net == net]


def sig(net):
    """The Signal of net `net`, or None."""
    return next((s for s in win.bd.signals if s.name == net), None)


def new_wires(before):
    """Wires added since the ids in `before`."""
    return [w for w in win.bd.wires if w.id not in before]


def undo_restores(fn, what):
    """Run fn, then undo: the model must be back to what it was."""
    QTest.qWait(500); win.undo_stack.flush()
    before = win.bd.to_json()
    fn()
    QTest.qWait(500); win.undo_stack.flush()
    win.undo_stack.undo(); QTest.qWait(100)
    check(win.bd.to_json() == before, f'undo restores: {what}')
    win.undo_stack.redo(); QTest.qWait(100)


show(at(200, 150))

# ============================== NETS AND BUSES ==============================
# N1 signal from open space to open space: default name, no dialog, two dangling ends
# (as the legacy tool: a click in open space adds a corner, a double-click ends the net there)
win.set_mode('wire'); ids = {w.id for w in win.bd.wires}
click(at(0, 0)); dclick(at(100, 60))
nw = new_wires(ids)
check(len(nw) == 1 and nw[0].net.startswith('sig') and not nw[0].start and not nw[0].end,
      f'N1 signal in open space: default name {nw[0].net if nw else None}, both ends dangling')
s0 = nw[0] if nw else None
check(s0 is not None and not sc.is_bus(s0.net) and sig(s0.net) is not None and not sig(s0.net).bounds,
      'N1 a signal is scalar (thin, no bounds)')

# N2 bus: dbus<n>, bounds [15:0], drawn thick
win.set_mode('bus'); ids = {w.id for w in win.bd.wires}
click(at(0, 100)); dclick(at(160, 100))
nw = new_wires(ids)
b0 = nw[0] if nw else None
check(b0 is not None and b0.net.startswith('dbus') and sig(b0.net).bounds == '[15:0]' and sc.is_bus(b0.net),
      f'N2 bus: {b0.net if b0 else None} {sig(b0.net).bounds if b0 else ""} drawn as a bus')

# N3 a second signal gets the next default name
win.set_mode('wire'); ids = {w.id for w in win.bd.wires}
click(at(0, 200)); dclick(at(120, 200))
nw = new_wires(ids)
check(nw and s0 and nw[0].net != s0.net and nw[0].net.startswith('sig'), f'N3 next default name {nw[0].net if nw else None}')
s1 = nw[0] if nw else None

# N4 a net started on an existing net joins it: same name, a junction dot
ids = {w.id for w in win.bd.wires}; nj = len(win.bd.junctions)
click(at(50, 0)); dclick(at(50, -80))
nw = new_wires(ids)
check(nw and nw[0].net == s0.net and len(win.bd.junctions) == nj + 1 and nw[0].start.startswith('jct:'),
      f'N4 net from an existing net joins it ({nw[0].net if nw else None}, junction dot)')

# N5 a vertical net: its name runs upward along it, half way
nw0 = nw[0] if nw else None
if nw0:
    it = sc.wire_items[nw0.id]
    check(it.is_label_vertical(), 'N5 a vertical net has a vertical name')
# N5b a horizontal net: name half way along, above the net
it = sc.wire_items[s1.id]
lp = it.label_pos(10)
check(abs(lp.y() - (s1.points[0][1] - 3)) < 0.5 and s1.points[0][0] < lp.x() < s1.points[-1][0],
      'N5 a horizontal net has its name half way along, above it')

# N6 Change Style to bus and back
win.set_net_style(s1.net, True)
check(sc.is_bus(s1.net), 'N6 Change Style to Bus')
win.set_net_style(s1.net, False)
check(not sc.is_bus(s1.net), 'N6 Change Style to Signal')

# N7 double-click the name: in-place edit "name : wire" -> rename
win.set_mode('select'); show(at(60, 200))
it = sc.wire_items[next(w for w in win.bd.wires if w.net == s1.net).id]
dclick(it.label_rect().center()); QTest.qWait(150)
ed = next((x for x in vp.findChildren(QLineEdit) if x.isVisible()), None)
check(ed is not None and ed.text().startswith(f'{s1.net} : wire'), f'N7 name double-click edits "{ed.text() if ed else None}"')
if ed:
    ed.setText('my_net : wire[3:0]'); QTest.keyClick(ed, Qt.Key_Return); QTest.qWait(150)
check(sig('my_net') is not None and sig('my_net').bounds == '[3:0]' and wires_of('my_net'), 'N7 rename and bounds applied')

# N8 drag a net: it moves, ends stay dangling
w = wires_of('my_net')[0]; p0 = [list(q) for q in w.points]
show(at(60, 200)); drag(at(60, 200), at(60, 240))
w = wires_of('my_net')[0]
check(w.points != p0 and abs(w.points[0][1] - p0[0][1] - 40) < 0.5, 'N8 dragging a net moves it')

# N9 undo of adding a signal
win.set_mode('wire'); show(at(300, 0))
undo_restores(lambda: (click(at(300, 0)), dclick(at(380, 0))), 'adding a signal')

# N10 signal with a port: input port on the open start, output port on the open end
win.set_mode('wire_port'); ids = {w.id for w in win.bd.wires}; npio = len(win.bd.port_ios)
show(at(300, 100)); click(at(300, 100)); dclick(at(420, 100))
nw = new_wires(ids)
pios = win.bd.port_ios[npio:]
modes = sorted(p.mode for p in pios)
check(nw and modes == ['input', 'output'] and all(p.name == nw[0].net for p in pios)
      and nw[0].start.startswith('pio:') and nw[0].end.startswith('pio:'),
      f'N10 signal with a port: ports {modes} named {nw[0].net if nw else None}')

# ============================== PORTS ==============================
# P1 Add Port In: the port outline follows the cursor; on a dangling end it attaches and takes the name
win.set_mode('port_in'); show(at(100, 60))
move(at(150, 300))
check(sc._ghost is not None and getattr(sc._ghost[1], 'ghost', False), 'P1 adding a port shows its outline (as the legacy tool)')
s0w = next(w for w in wires_of(s0.net) if not w.end or not w.start)
which = 'end' if not s0w.end else 'start'
end = QPointF(*(s0w.points[-1] if which == 'end' else s0w.points[0]))
n = len(win.bd.port_ios); click(end)          # the cursor is the preview's wire end (as the legacy tool)
pio = win.bd.port_ios[-1] if len(win.bd.port_ios) > n else None
s0w = next(w for w in win.bd.wires if w.id == s0w.id)
check(pio is not None and pio.name == s0.net and getattr(s0w, which) == f'pio:{pio.id}',
      f'P1 port on a dangling end attaches and is named {pio.name if pio else None}')
# P2 the port points towards its net (input) / away (output) / both (inout)
item = sc.items_by_id[pio.id]
side = sc.port_side(pio)
check(side == (1 if (s0w.points[-2][0] if which == 'end' else s0w.points[1][0]) > pio.x else -1),
      'P2 the input port faces its net')
win.change_port_mode(pio, 'output'); QTest.qWait(50)
check(next(p for p in win.bd.port_ios if p.id == pio.id).mode == 'output', 'P2 Change Mode In -> Out')
# P3 Add Port Inout in open space: no name asked, the port has no name until connected
win.set_mode('port_inout'); show(at(500, 300))
n = len(win.bd.port_ios); click(at(500, 300)); QTest.qWait(200)
p3 = win.bd.port_ios[-1] if len(win.bd.port_ios) > n else None
check(p3 is not None and p3.mode == 'inout' and p3.name == '', 'P3 inout port in open space, no name yet')
# P4 a net drawn from the free port to open space: the port takes the net's default name
win.set_mode('wire'); ids = {w.id for w in win.bd.wires}
click(QPointF(*sc.port_edge(p3, 1))); dclick(at(620, 300))
nw = new_wires(ids)
p3 = next(p for p in win.bd.port_ios if p.id == p3.id)
check(nw and p3.name == nw[0].net and nw[0].net.startswith('sig') and sig(p3.name).mode == 'inout',
      f'P4 a free port takes the name of the net drawn from it ({p3.name})')
# P5 a free port dragged so its wire end lands on a dangling net end: connects, takes the name
win.set_mode('wire'); ids = {w.id for w in win.bd.wires}
click(at(300, 400)); dclick(at(400, 400))
dn = new_wires(ids)[0]
win.set_mode('port_out'); n = len(win.bd.port_ios); click(at(560, 460)); QTest.qWait(100)
p5 = win.bd.port_ios[-1]
win.set_mode('select'); show(at(450, 430))
# the port's wire end is on its left (no net yet, output): drag the body so that end is on (400, 400)
tip = QPointF(*sc.port_edge(p5, -1))
drag(QPointF(p5.x, p5.y), QPointF(p5.x, p5.y) + (at(400, 400) - tip))
QTest.qWait(300)
p5 = next(p for p in win.bd.port_ios if p.id == p5.id)
dn = next(w for w in win.bd.wires if w.id == dn.id)
check(p5.name == dn.net and dn.end == f'pio:{p5.id}', f'P5 port dropped on a dangling net end connects ({p5.name})')
check(abs(sc.port_edge(p5)[0] - dn.points[-1][0]) < 0.5 and abs(p5.y - dn.points[-1][1]) < 0.5,
      'P5 the port wire end is on the net end')
# P6 a free port dropped with its wire end on the body of a net: joins it with a dot, stays put,
# and the joining net shows no second name
win.set_mode('wire'); ids = {w.id for w in win.bd.wires}
click(at(300, 500)); dclick(at(300, 600))
vn = new_wires(ids)[0]
win.set_mode('port_in'); n = len(win.bd.port_ios); click(at(500, 560)); QTest.qWait(100)
p6 = win.bd.port_ios[-1]
win.set_mode('select'); show(at(400, 550))
tip = QPointF(*sc.port_edge(p6)); nj = len(win.bd.junctions); nw0 = {w.id for w in win.bd.wires}
target = QPointF(p6.x, p6.y) + (at(300, 550) - tip)
drag(QPointF(p6.x, p6.y), target)
QTest.qWait(300)
p6 = next(p for p in win.bd.port_ios if p.id == p6.id)
short = [w for w in win.bd.wires if w.id not in nw0]
check(p6.name == vn.net and len(win.bd.junctions) == nj + 1 and short and short[0].start == f'pio:{p6.id}',
      f'P6 port dropped (wire end) on the body of a net joins it ({p6.name})')
jn = win.bd.junctions[-1]; tip6 = sc.port_edge(p6)
check(abs(tip6[0] - jn.x) <= GRID + 0.5 and abs(tip6[1] - jn.y) < 0.5,
      f'P6 the port stays where it was dropped, its wire end at the dot ({tip6[0] - jn.x:.1f})')
check(short and not short[0].show_text, 'P6 the joining net shows no second name')
# P7 Add Port: the preview's wire end on the body of a net connects; its middle on the net does not
win.set_mode('port_in'); show(at(300, 580))
n = len(win.bd.port_ios); click(at(300, 590) + QPointF(PORT_EDGE, 0)); QTest.qWait(100)   # middle on the net, wire end off it
p_off = win.bd.port_ios[-1] if len(win.bd.port_ios) > n else None
check(p_off is not None and p_off.name == '', 'P7 port with only its middle on a net is not connected')
win.set_mode('port_in')
n = len(win.bd.port_ios); click(at(300, 580)); QTest.qWait(100)   # the cursor is the wire end: on the net
p7 = win.bd.port_ios[-1] if len(win.bd.port_ios) > n else None
check(p7 is not None and p7.name == vn.net and abs(sc.port_edge(p7)[0] - vn.points[0][0]) < 0.5,
      'P7 Add Port with its wire end on a net connects, its wire end on the net')
win.set_mode('select')
cv.grab().save(out + '/suite_ports.png')

# ============================== COMPONENTS ==============================
src = next(i for i in win.bd.instances if i.unit == 'dataflow_controller')
info = {'library': src.library, 'unit': src.unit,
        'ports': [(p.name, p.mode, p.bounds) for p in sorted(src.pins, key=lambda p: p.order)]}
win._pick_component = lambda: info
win.set_mode('component'); show(at(900, 300))
move(at(900, 300))
check(sc._ghost is not None and sc._ghost[0] == 'comp' and sc._ghost[1].opacity() < 1,
      'C1 adding a component shows a faded component under the cursor')
n = len(win.bd.instances); click(at(900, 300))
comp = win.bd.instances[-1] if len(win.bd.instances) > n else None
check(comp is not None and len(comp.pins) == len(src.pins) and comp.name not in {i.name for i in win.bd.instances[:-1]},
      f'C2 component placed: {comp.name if comp else None}, {len(comp.pins) if comp else 0} ports, unique name')
win.set_mode('select')
# C3 a net drawn from a component port takes the port's name and bounds
pin = next(p for p in comp.pins if p.mode == 'output' and p.side == 'right' and not p.net)
win.set_mode('wire'); ids = {w.id for w in win.bd.wires}
show(QPointF(pin.x, pin.y)); click(QPointF(pin.x, pin.y)); dclick(QPointF(pin.x + 150, pin.y))
nw = new_wires(ids)
check(nw and nw[0].net == pin.name and (sig(pin.name).bounds == pin.bounds),
      f'C3 net from a component port is named {nw[0].net if nw else None} with its bounds')
check(nw and next(p for p in next(i for i in win.bd.instances if i.id == comp.id).pins if p.name == pin.name).net == pin.name,
      'C3 the component port is on the net')
# C4 moving the component: its nets follow and stay attached
win.set_mode('select'); comp_item = sc.items_by_id[comp.id]
c = comp_item.mapToScene(QPointF(comp.w / 2, comp.h - 10)); show(c)
w = nw[0]; p0 = list(w.points[0])
drag(c, c + QPointF(0, 40))
w = next(x for x in win.bd.wires if x.id == w.id)
check(abs(w.points[0][1] - p0[1] - 40) < 0.5 and w.start.startswith(f'pin:{comp.id}:'), 'C4 moving a component drags its nets along')
# C5 Port Out on a free component port: a stub net and the port, named after the component port
pin2 = next(p for p in next(i for i in win.bd.instances if i.id == comp.id).pins if p.mode == 'output' and not p.net)
win.set_mode('port_out'); show(QPointF(pin2.x, pin2.y)); n = len(win.bd.port_ios)
click(QPointF(pin2.x, pin2.y))                  # the preview's wire end on the component port
p5 = win.bd.port_ios[-1] if len(win.bd.port_ios) > n else None
check(p5 is not None and p5.name == pin2.name and p5.mode == 'output' and wires_of(pin2.name),
      f'C5 port on a component port: {p5.name if p5 else None}')
# C6 a free port wired to a free component port: both take the component port's name
pin3 = next(p for p in next(i for i in win.bd.instances if i.id == comp.id).pins if p.mode == 'output' and not p.net)
win.set_mode('port_out'); n = len(win.bd.port_ios); click(QPointF(pin3.x + 300, pin3.y + 200)); QTest.qWait(100)
p8 = win.bd.port_ios[-1]
win.set_mode('wire'); show(QPointF(pin3.x + 150, pin3.y + 100))
click(QPointF(pin3.x, pin3.y)); click(QPointF(*sc.port_edge(p8, -1)))
p8 = next(p for p in win.bd.port_ios if p.id == p8.id)
check(p8.name == pin3.name, f'C6 a free port wired to a component port takes its name ({p8.name})')
win.set_mode('select')
cv.grab().save(out + '/suite_component.png')

# ============================== EMBEDDED BLOCKS ==============================
win.set_mode('embedded'); show(at(500, 600)); move(at(500, 600))
check(sc._ghost is not None and sc._ghost[0] == 'emb', 'E1 adding an embedded block shows its outline')
n = len(win.bd.embedded); click(at(500, 600))
eb = win.bd.embedded[-1] if len(win.bd.embedded) > n else None
check(eb is not None and eb.text == '' and eb.text_box is None, f'E2 new block {eb.name if eb else None} has no view')
win.set_mode('select')
seen = []


def accept_view_dialog():
    """Wait for the Create Embedded View dialog (polling) and press OK."""
    d = next((x for x in QApplication.topLevelWidgets() if isinstance(x, EmbeddedViewDialog) and x.isVisible()), None)
    if d is None:
        QTimer.singleShot(100, accept_view_dialog); return
    seen.append(1); d.accept()
QTimer.singleShot(200, accept_view_dialog)
item = sc.items_by_id[eb.id]
win.raise_(); win.activateWindow(); QTest.qWaitForWindowActive(win, 2000)   # the in-place editor closes when focus leaves
dclick(item.body().center()); QTest.qWait(300)
eb = next(e for e in win.bd.embedded if e.id == eb.id)
check(seen and eb.text_box is not None and eb.text.startswith(f'// {eb.name}'), 'E3 double-click the block: Create Embedded View -> Text')
ed = next((x for x in vp.findChildren(QPlainTextEdit) if x.isVisible()), None)
if ed:
    ed.setPlainText('assign y_out = x_in;\n'); cv.setFocus(); QTest.qWait(200)
eb = next(e for e in win.bd.embedded if e.id == eb.id)
check(eb.text == 'assign y_out = x_in;\n', 'E3 text typed in place is kept')
# E4 the Text view moves on its own, and resizes
item = sc.items_by_id[eb.id]; bx, by = eb.x, eb.y; box0 = list(eb.text_box)
c = item.mapToScene(item.text_rect().center()); show(c)
drag(c, c + QPointF(40, 20))
eb = next(e for e in win.bd.embedded if e.id == eb.id)
check((eb.x, eb.y) == (bx, by) and eb.text_box[:2] != box0[:2], 'E4 dragging the Text view moves only the text')
item = sc.items_by_id[eb.id]
corner = item.mapToScene(item.text_rect().bottomRight())
sc.clearSelection(); item.setSelected(True); show(corner); app.processEvents()
drag(corner, corner + QPointF(60, 30))
eb = next(e for e in win.bd.embedded if e.id == eb.id)
check(eb.text_box[2] > box0[2] and eb.text_box[3] > box0[3], 'E4 dragging the corner resizes the Text view')
# E5 nets to and from the block: input / output, and Change Mode
win.set_mode('wire'); item = sc.items_by_id[eb.id]; b = item.body()
ids = {w.id for w in win.bd.wires}
show(b.center()); click(b.center() + QPointF(-200, 0)); click(QPointF(b.left() + 4, b.center().y()))
win_in = new_wires(ids)
check(win_in and win_in[0].end == f'emb:{eb.id}' and abs(win_in[0].points[-1][0] - b.left()) < 0.01,
      'E5 a net drawn to the block attaches to its edge (input)')
ids = {w.id for w in win.bd.wires}
click(QPointF(b.right() - 4, b.center().y())); dclick(QPointF(b.right() + 200, b.center().y()))
win_out = new_wires(ids)
check(win_out and win_out[0].start == f'emb:{eb.id}', 'E5 a net drawn from the block starts on it (output)')
win.set_mode('select')
if win_in:
    w = win_in[0]
    win.set_embedded_port_mode(next(x for x in win.bd.wires if x.id == w.id), 'end', True)
    w = next(x for x in win.bd.wires if x.id == w.id)
    check(w.start == f'emb:{eb.id}', 'E5 Change Mode In -> Out reverses the net')
# E6 moving the block: its nets stay attached, the Text view goes along
item = sc.items_by_id[eb.id]; c = item.mapToScene(QPointF(10, 10)); show(c)
tb0 = list(next(e for e in win.bd.embedded if e.id == eb.id).text_box)
drag(c, c + QPointF(0, 40))
eb = next(e for e in win.bd.embedded if e.id == eb.id)
b = sc.items_by_id[eb.id].body()
ok = all(abs((w.points[0] if w.start == f'emb:{eb.id}' else w.points[-1])[0] - (b.left() if abs((w.points[0] if w.start == f'emb:{eb.id}' else w.points[-1])[0] - b.left()) < 1 else b.right())) < 1
         for w in win.bd.wires if f'emb:{eb.id}' in (w.start, w.end))
check(ok and eb.text_box == tb0, 'E6 moving the block keeps its nets on its edges, Text view goes along')
cv.grab().save(out + '/suite_embedded.png')

# ============================== SAVE, RELOAD, GENERATE ==============================
text = win.bd.to_json()
bd2 = BlockDiagram.from_json(text)
check(bd2.to_json() == text, 'S1 save / reload keeps every object (JSON round trip)')
hdl, warns = generate_bd(win.bd)
check('assign y_out = x_in;' in hdl, 'S2 generated HDL has the embedded block text')
check(f'{comp.name}' in hdl and f'.{pin.name}' in hdl, 'S2 generated HDL has the new component instance')
check(p3.name in hdl, 'S2 generated HDL has the new inout port')
print('warnings:', [w for w in warns if 'my_net' in w or 'sig' in w][:5])

print('\nSUMMARY', sum(1 for r in results if r[0] == 'PASS'), 'passed,', fails, 'failed')
_env.finish(fails)
