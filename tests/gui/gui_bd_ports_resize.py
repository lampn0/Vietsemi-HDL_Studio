"""Block Diagram Tools buttons, Ctrl+click and area selection of component ports, the port popup menu
and its keyboard shortcuts, a click and a double-click on a port name, and resizing a component by a
handle (real diagram, nothing written)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QPainterPath
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu
from formats.import_bd import import_bd
from gui import bd_editor

app = QApplication(sys.argv)
fails = 0


def ok(name, cond):
    """Count and print one check: PASS / FAIL and its name."""
    global fails
    fails += not cond
    print(('PASS ' if cond else 'FAIL ') + name, flush=True)


bd = import_bd(_env.legacy_bd('libs/protocol_controller/hds/gc_auto_refresh/struct.bd'))
w = bd_editor.BdEditorWindow(bd); w.resize(1400, 900); w.show(); QTest.qWait(300)
sc, cv, vp = w.scene, w.canvas, w.canvas.viewport()

# the tool buttons switch the tool (they raised an exception before)
for mode in ('wire', 'bus', 'port_in', 'embedded', 'frame', 'comment', 'panel'):
    w.toolbar_actions[mode].trigger()
    ok(f'tool button {mode}', sc.mode == mode)
w.set_mode('select')

item = next(i for i in sc.items_by_id.values()
            if isinstance(i, bd_editor.InstanceItem) and i.obj.unit == 'gc_t_refi_count')
inst = item.obj
cv.resetTransform(); cv.scale(2, 2); cv.centerOn(item); QTest.qWait(100)
view = lambda pt: cv.mapFromScene(pt)
left = [p for p in inst.pins if p.side == 'left'][:3]

# Ctrl+click adds ports to the selection, Ctrl+click again takes one out
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, view(item.mapToScene(left[0].x - inst.x, left[0].y - inst.y)))
for pin in left[1:]:
    QTest.mouseClick(vp, Qt.LeftButton, Qt.ControlModifier, view(item.mapToScene(pin.x - inst.x, pin.y - inst.y)))
ok('Ctrl+click selects three ports', [p.name for _, p in sc.pins_selected()] == [p.name for p in left])
ok('the component itself stays unselected', not item.isSelected())
QTest.mouseClick(vp, Qt.LeftButton, Qt.ControlModifier, view(item.mapToScene(left[1].x - inst.x, left[1].y - inst.y)))
ok('Ctrl+click again unselects one', [p.name for _, p in sc.pins_selected()] == [left[0].name, left[2].name])

# area selection (the view's rubber band: the selection of the area, then the end of the band)
def area(r: QRectF):
    """Select like a rubber band drawn over scene rectangle r."""
    sc.select_pin(None, None)
    path = QPainterPath(); path.addRect(r)
    sc.setSelectionArea(path)
    w._rubber_band(QRect(0, 0, 5, 5), r.topLeft(), r.bottomRight())
    w._rubber_band(QRect(), QPointF(), QPointF())
    QTest.qWait(30)                         # the selection is corrected just after the band
right_pins = [p for p in inst.pins if p.side == 'right']
ys = [p.y for p in right_pins]
area(QRectF(inst.x + inst.w + 0.5, min(ys) - 2, 30, max(ys) - min(ys) + 4))   # up to the body edge
ok('area over the ports only: the ports, not the component',
   {p.name for _, p in sc.pins_selected()} == {p.name for p in right_pins} and not item.isSelected())
area(QRectF(inst.x + inst.w - 10, min(ys) - 2, 40, max(ys) - min(ys) + 4))
ok('area reaching the body: the component and its ports',
   {p.name for _, p in sc.pins_selected()} == {p.name for p in right_pins} and item.isSelected())
sc.clearSelection()
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, view(item.mapToScene(left[0].x - inst.x, left[0].y - inst.y)))
for pin in left[1:]:
    QTest.mouseClick(vp, Qt.LeftButton, Qt.ControlModifier, view(item.mapToScene(pin.x - inst.x, pin.y - inst.y)))
QTest.mouseClick(vp, Qt.LeftButton, Qt.ControlModifier, view(item.mapToScene(left[1].x - inst.x, left[1].y - inst.y)))

# the port popup menu, as the legacy tool shows it; its commands act on the selected ports only
m = QMenu(); w._pin_menu(m, inst, False)
names = [a.text().replace('&', '') or '-' for a in m.actions()]
ok(f'port popup {names}', names == ['Disconnect', 'Equidistant Ports', 'Add Signal Stubs...', 'Add PortIO...',
                                    'Appearance...', '-', 'Show Text', 'Object Properties...'])
refs = {f'pin:{inst.id}:{p.name}' for p in (left[0], left[2])}
others = lambda: sum(1 for x in bd.wires for r in (x.start, x.end) if r.startswith(f'pin:{inst.id}:') and r not in refs)
n_others = others()
m.actions()[0].trigger()
ok('Disconnect detaches only the selected ports',
   not any(r in refs for x in bd.wires for r in (x.start, x.end)) and others() == n_others)

# the same commands from the keyboard act on the selected ports (Ctrl+F10, Shift+F10, Shift+Alt+C)
item = sc.items_by_id[inst.id]          # the command rebuilt the scene
p_key = left[0]
ref = f'pin:{inst.id}:{p_key.name}'
on_pin = lambda: sum(1 for x in bd.wires if ref in (x.start, x.end))
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, view(item.mapToScene(p_key.x - inst.x, p_key.y - inst.y)))
w.activateWindow(); cv.setFocus(); QTest.qWait(50)
QTest.keyClick(vp, Qt.Key_F10, Qt.ControlModifier); QTest.qWait(50)
ok('Ctrl+F10 adds a signal stub on the selected port', on_pin() == 1)
stub = next(x for x in bd.wires if ref in (x.start, x.end))
r = sc.wire_items[stub.id].label_rect()
xs = sorted(pt[0] for pt in stub.points)
ok(f'the stub is longer than its name ({xs[-1] - xs[0]:.0f} > {r.width():.0f})',
   xs[0] <= r.left() and r.right() <= xs[-1])
QTest.keyClick(vp, Qt.Key_C, Qt.ShiftModifier | Qt.AltModifier); QTest.qWait(50)
ok('Shift+Alt+C disconnects the selected port', on_pin() == 0)
n_pio = len(bd.port_ios)
QTest.keyClick(vp, Qt.Key_F10, Qt.ShiftModifier); QTest.qWait(50)
ok('Shift+F10 adds a PortIO on the selected port', on_pin() == 1 and len(bd.port_ios) == n_pio + 1)

# a click on a port name selects that name on its own; a double-click says it is read only
item = sc.items_by_id[inst.id]          # the command rebuilt the scene
pin = next(p for p in inst.pins if p.side == 'right')
at = view(item.mapToScene(item.pin_label_rect(pin).center()))
QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at)
ok('click on a port name selects the name', sc.selected_text == (inst.id, 'pin:' + pin.name) and not item.isSelected())
QTest.mouseDClick(vp, Qt.LeftButton, Qt.NoModifier, at)
ok('double-click on a port name: read-only text', w.statusBar().currentMessage() == 'Cannot edit read-only text')

# resize: drag the bottom-right handle of the selected component
sc.clearSelection(); item.setSelected(True); QTest.qWait(50)
r0 = QRectF(inst.x, inst.y, inst.w, inst.h)
right = {p.name: (p.x, p.y) for p in inst.pins if p.side == 'right'}
lefts = {p.name: (p.x, p.y) for p in inst.pins if p.side == 'left'}
p0 = view(item.mapToScene(inst.w, inst.h))
p1 = p0 + QPoint(80, 40)
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p0)
for k in range(1, 9):
    QTest.mouseMove(vp, p0 + (p1 - p0) * k / 8); QTest.qWait(10)
ok('an outline follows the mouse', item._outline is not None and item._outline.width() > r0.width())
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p1); QTest.qWait(50)
dw = inst.w - r0.width()
ok(f'component resized ({r0.width():.0f}x{r0.height():.0f} -> {inst.w:.0f}x{inst.h:.0f})',
   dw > 0 and inst.h > r0.height() and (inst.x, inst.y) == (r0.x(), r0.y()))
ok('right ports follow the edge', all(abs(p.x - right[p.name][0] - dw) < .01 and p.y == right[p.name][1]
                                      for p in inst.pins if p.side == 'right'))
ok('left ports stay', all((p.x, p.y) == lefts[p.name] for p in inst.pins if p.side == 'left'))
ends = all(abs(x.points[0 if x.start == ref else -1][0] - bd_editor.pin_end(p)[0]) < .01
           and abs(x.points[0 if x.start == ref else -1][1] - bd_editor.pin_end(p)[1]) < .01
           for p in inst.pins for ref in [f'pin:{inst.id}:{p.name}'] for x in bd.wires if ref in (x.start, x.end))
ok('nets still end on the ports', ends)
ok('diagram marked modified', w.dirty)
cv.viewport().grab().save(os.path.join(OUT, 'bd_ports_resize.png'))
w.dirty = False
_env.finish(fails)
