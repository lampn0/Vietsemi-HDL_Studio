"""Drawing a net as the legacy tool does it (watched on the legacy tool):
a click in open space adds a right-angle corner and the net goes on, a double-click ends it in
open space, a click on an object (here the end of another net) ends it there at once."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from bd_model import BlockDiagram  # noqa: E402
from gui import bd_editor  # noqa: E402

app = QApplication(sys.argv)
fails = 0


def ok(name, cond):
    """Count and print one check: PASS / FAIL and its name."""
    global fails
    fails += not cond
    print(('PASS ' if cond else 'FAIL ') + name, flush=True)


win = bd_editor.BdEditorWindow(BlockDiagram(language='verilog'))
win.resize(1200, 800); win.show(); QTest.qWait(300)
sc, cv, vp = win.scene, win.canvas, win.canvas.viewport()
cv.resetTransform(); cv.centerOn(300, 200); QTest.qWait(50)


G = bd_editor.GRID                     # the editor's grid step; all points below are on it


def pt(x, y):
    """Viewport point of grid position (x, y)."""
    return cv.mapFromScene(QPointF(x * G, y * G))


def click(x, y):
    """Left click at grid position (x, y)."""
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, pt(x, y)); QTest.qWait(40)


def dclick(x, y):
    """Double-click at grid position (x, y)."""
    QTest.mouseDClick(vp, Qt.LeftButton, Qt.NoModifier, pt(x, y)); QTest.qWait(80)


# 1. start, a click in open space, then a double-click: one net with a right-angle corner
win.set_mode('wire')
click(8, 8); click(15, 8)
ok('a click in open space does not end the net', not win.bd.wires and sc._wire_start is not None)
QTest.mouseMove(vp, pt(20, 12)); QTest.qWait(30)
dclick(20, 12)
w = win.bd.wires[0] if win.bd.wires else None
ok('a double-click ends it', w is not None and sc._wire_start is None)
pts = [(round(p[0] / G), round(p[1] / G)) for p in w.points] if w else []
print('   points', pts)
ok('ends where clicked', pts and pts[0] == (8, 8) and pts[-1] == (20, 12))
ortho = all(abs(a[0] - b[0]) < .01 or abs(a[1] - b[1]) < .01 for a, b in zip(pts, pts[1:]))
ok('all segments are horizontal or vertical', ortho)
ok('after the horizontal segment the net turns vertical first (as the legacy tool)', (15, 12) in pts)
ok('default name sig0', w is not None and w.net == 'sig0')

# 2. a click on the dangling end of sig0 ends a new net there at once, joined to sig0
win.set_mode('wire'); n = len(win.bd.wires)
click(8, 16); click(20, 12)
ok('a click on an object ends the net at once', len(win.bd.wires) == n + 1 and sc._wire_start is None)
ok('the new net is joined to sig0', win.bd.wires[-1].net == 'sig0')

print('FAILS', fails)
win.dirty = False
win.close()
sys.exit(1 if fails else 0)
