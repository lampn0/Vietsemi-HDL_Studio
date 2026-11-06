"""Handles keep their screen size at any zoom; PortIOs sit between two grid dots."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPixmap, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from formats.import_bd import import_bd
from gui import bd_editor
from gui.diagram import GRID

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
pio = next(p for p in bd.port_ios if p.name == 'clk') if any(p.name == 'clk' for p in bd.port_ios) else bd.port_ios[0]
wire = next(x for x, _ in sc._attached(f'pio:{pio.id}'))
sc.clearSelection(); sc.wire_items[wire.id].setSelected(True)
end = wire.points[0] if wire.start == f'pio:{pio.id}' else wire.points[-1]
ok(f'net end on a grid dot at the PortIO stub end ({end[0]:.2f}, {end[1]:.2f})',
   abs(end[0] / GRID - round(end[0] / GRID)) < 1e-6 and abs(abs(end[0] - pio.x) - GRID) < 1e-6)
shots, sizes = [], []
for zoom in (0.7, 1.5, 4.0):
    cv.resetTransform(); cv.scale(zoom, zoom); cv.centerOn(end[0], end[1]); QTest.qWait(120)
    c = cv.mapFromScene(QPointF(*end))
    img = vp.grab(QRectF(c.x() - 20, c.y() - 20, 40, 40).toRect()).toImage()
    black = [(x, y) for x in range(img.width()) for y in range(img.height())
             if QColor(img.pixel(x, y)).value() < 40]
    # the handle is the solid square at the centre: measure its run along the middle row
    row = [y for x, y in black if x == 20]   # the net is horizontal here: measure the handle vertically
    run = 0
    for x in range(20, -1, -1):
        if x in row: run += 1
        else: break
    for x in range(21, 40):
        if x in row: run += 1
        else: break
    sizes.append(run)
    shots.append(vp.grab(cv.mapFromScene(QRectF(pio.x - 120, pio.y - 40, 260, 80)).boundingRect()))
print('  handle width on screen at zoom 0.7 / 1.5 / 4:', sizes)
ok('handles keep the same screen size at every zoom', max(sizes) - min(sizes) <= 1 and 5 <= sizes[0] <= 8)
pm = QPixmap(sum(s.width() + 10 for s in shots), max(s.height() for s in shots)); pm.fill(Qt.white)
p = QPainter(pm); x = 0
for s in shots:
    p.drawPixmap(x, 0, s); x += s.width() + 10
p.end(); pm.save(os.path.join(OUT, 'bd_handles.png')); w.dirty = False
_env.finish(fails)
