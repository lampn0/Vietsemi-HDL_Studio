"""Frames in the block diagram editor (imported from the real project, nothing written)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog
from formats.import_bd import import_bd
from gui import bd_editor
from codegen.bd_codegen import generate_bd
from hdl.parser import check_text

app = QApplication(sys.argv)
fails = 0


def ok(name, cond):
    """Count and print one check: PASS / FAIL and its name."""
    global fails
    fails += not cond
    print(('PASS ' if cond else 'FAIL ') + name, flush=True)
bd = import_bd(_env.legacy_bd('libs/protocol_controller/hds/protocol_controller/struct.bd'))
bd.language = 'verilog'
w = bd_editor.BdEditorWindow(bd); w.resize(1500, 950); w.show(); QTest.qWait(300)
sc, cv, vp = w.scene, w.canvas, w.canvas.viewport()
frames = [it for it in sc.items_by_id.values() if isinstance(it, bd_editor.FrameItem)]
ok(f'{len(frames)} frames drawn', len(frames) == 3)

# generated HDL: instances in FOR frames become instance arrays
text, _ = generate_bd(bd)
arrays = [l for l in text.splitlines() if '[PS_CHAN_NUM - 1:0](' in l]
print('  ', arrays)
ok('FOR frame instances are instance arrays', len(arrays) == 3)

# drag a frame by its title: the instance inside moves the same amount
fr = next(f for f in frames if f.obj.name == 'ps_chan_num1')
inst = next(i for i in bd.instances if bd.frame_of(i) is fr.obj)
x0, y0, fx0, fy0 = inst.x, inst.y, fr.obj.x, fr.obj.y
cv.resetTransform(); cv.centerOn(fr.obj.x + 60, fr.obj.y); QTest.qWait(100)
p0 = cv.mapFromScene(QPointF(fr.obj.x + 20, fr.obj.y - 8))
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p0)
for k in range(1, 9):
    QTest.mouseMove(vp, p0 + QPoint(0, 5 * k)); QTest.qWait(5)
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p0 + QPoint(0, 40)); QTest.qWait(100)
dy = fr.obj.y - fy0
ok(f'frame moved by {dy:.0f}', abs(dy) > 1)
print('   inst dy', inst.y - y0, 'dx', inst.x - x0, 'item', sc.items_by_id[inst.id].pos().y() - y0)
ok('instance inside moved exactly like the frame (grid snap included)', abs((inst.y - y0) - dy) < 1e-6 and abs((inst.x - x0) - (fr.obj.x - fx0)) < 1e-6)
ok('instance still inside its frame', bd.frame_of(inst) is fr.obj)
ortho = all(abs(a[0] - b[0]) < .01 or abs(a[1] - b[1]) < .01 for wr in bd.wires for a, b in zip(wr.points, wr.points[1:]))
ok('all nets still orthogonal', ortho)
w.act_undo.trigger(); QTest.qWait(100)
inst = next(i for i in w.bd.instances if i.name == inst.name)
ok('undo puts frame and contents back', abs(inst.y - y0) < 1e-6)

# add a FOR frame around nothing, then edit its title
QInputDialog.getText = staticmethod(lambda *a, **k: ('lanes: [N-1:0]', True))
w.set_mode('frame'); w.place_at(QPointF(2000, 2000))
nf = w.bd.frames[-1]
ok(f'new FOR frame {nf.kind} {nf.name} {nf.spec}', (nf.kind, nf.name, nf.spec) == ('for', 'lanes', '[N-1:0]'))
QInputDialog.getText = staticmethod(lambda *a, **k: ('lanes2: [M-1:0]', True))
w.edit_frame(w.bd.frames[-1])
ok('frame title edited', (w.bd.frames[-1].name, w.bd.frames[-1].spec) == ('lanes2', '[M-1:0]'))

# IF/ELSE frames around an embedded block -> `ifdef / `else / `endif, syntax checked
from bd_model import BdEmbedded, BdFrame, BlockDiagram
t = BlockDiagram(unit='t', language='verilog')
t.frames = [BdFrame('f1', 'if', 'g0', '`ifdef USE_X', 1, 0, 0, 300, 200),
            BdFrame('f2', 'else', 'g0', '`else', 2, 0, 300, 300, 200),
            BdFrame('f3', 'if', 'g1', '(W > 4)', 3, 400, 0, 300, 200)]
t.embedded = [BdEmbedded('e1', 'eb1', 1, "wire a = 1'b1;", 50, 50, 100, 60),
              BdEmbedded('e2', 'eb2', 2, "wire a = 1'b0;", 50, 350, 100, 60),
              BdEmbedded('e3', 'eb3', 3, "wire b = 1'b0;", 450, 50, 100, 60)]
txt, _ = generate_bd(t)
body = txt[txt.index('// Instances'):]
print('\n'.join('   ' + l for l in body.splitlines()[:16]))
errs = [d for d in check_text(txt, 't.v') if d[1] == 'error']
ok(f'IF/ELSE frames generate valid Verilog ({errs[:2]})', not errs and '`else' in body and 'if (W > 4) begin : g1' in body)
cv.fit(); QTest.qWait(100)
cv.fitInView(QRectF(fr.obj.x - 300, fr.obj.y - 150, 900, 500), Qt.KeepAspectRatio); QTest.qWait(100)
vp.grab().save(os.path.join(OUT, 'bd_frames.png'))
w.dirty = False
_env.finish(fails)
