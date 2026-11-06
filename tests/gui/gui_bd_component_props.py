"""Component / PortIO popup menus and BD Object Properties pages (real diagram, nothing written)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu
from formats.import_bd import import_bd
from gui import bd_editor, bd_dialogs
from codegen.bd_codegen import generate_bd

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
shots = []
inst = next(i for i in bd.instances if i.name == 'pc_bg_controller_array')

# component popup
m = QMenu(); w._component_menu(m, inst, QPointF(inst.x, inst.y), False)
names = [a.text().replace('&', '') or '-' for a in m.actions()]
print('  component menu:', names)
ok('component popup in the legacy order', names == [
    'Open As', 'Change Default View', 'Rotate', 'Flip', '-', 'Cut', 'Copy', 'Paste', 'Delete', '-', 'Connect',
    'Disconnect', 'Autoroute', 'Add Signal Stubs...', 'Add PortIO...', 'Equidistant Ports', 'Port Map Frame', '-',
    'Shape', 'Appearance...', 'Show Text', 'Port Visibility...', '-', 'Generics/Parameters', 'Re-level', 'Update',
    'Object Properties...'])
m.popup(w.mapToGlobal(w.rect().center())); QTest.qWait(150); shots.append(m.grab()); m.hide()

# component dialog: visit every page, set options
pages = ['Components', 'Parameters', 'Text Visibility', 'PortMap Frame', 'Attributes', 'Appearance']
free = next(p for p in sorted(inst.pins, key=lambda p: p.order) if not p.net) if any(not p.net for p in inst.pins) else None
def drive():
    """Walk every page of the open Component Properties dialog (titles, pictures), then close it."""
    d = next(x for x in app.topLevelWidgets() if isinstance(x, bd_dialogs.ComponentPropertiesDialog) and x.isVisible())
    titles = []
    root = d.category_item
    for item in [root] + [root.child(k) for k in range(root.childCount())]:
        d.show_page(item); QTest.qWait(60); titles.append(d.windowTitle()); shots.append(d.grab())
    print('  titles:', titles)
    ok('six pages with legacy titles', titles == ['BD Object Properties - ' + t for t in (
        'Components', 'Component Parameters', 'Component Text Visibility', 'Port Map Frame', 'Attributes',
        'Edit Appearance')])
    icons = sum(1 for i in range(d.tree.topLevelItemCount()) if not d.tree.topLevelItem(i).icon(0).isNull())
    ok(f'category tree has icons ({icons})', icons >= 13)
    d.text_page.type.setChecked(True)
    d.attrs.setPlainText('// synopsys dont_touch pc_bg_controller_array')
    d.pm_enable.setChecked(True)
    if free is not None:
        d.pm_text.setPlainText(f".{free.name}(1'b0)")
    d.look.fg.set_color('#ffcc00')
    d.name_vis.setChecked(False)
    d._ok()
QTimer.singleShot(300, drive)
w.component_properties(inst, 'component'); QTest.qWait(100)
text, _ = generate_bd(w.bd)
ok('attributes written before the instance', '// synopsys dont_touch pc_bg_controller_array\npc_bg_controller_array' in text)
if free is not None:
    ok(f'port map frame maps unconnected {free.name}', f"({free.name}" not in text and f"(1'b0)" in text)
ok('appearance and visibility stored', inst.fg == '#ffcc00' and inst.text_type and not inst.show_instance)
ok('diagram marked modified', w.dirty)

# PortIO popup and dialog
pio = next(p for p in w.bd.port_ios if p.mode == 'input')
m = QMenu(); w._port_menu(m, w.scene.items_by_id[pio.id], QPointF(pio.x, pio.y), False)
names = [a.text().replace('&', '') or '-' for a in m.actions()]
ok(f'PortIO popup: {names}', names == ['Change Mode', 'Rotate Port', 'PortIO Text Visibility...', 'Hide Text', '-', 'Cut',
                                      'Copy', 'Paste', 'Delete', '-', 'Connect', 'Disconnect', '-', 'Appearance...', '-',
                                      'Object Properties...'])
def drive2():
    """Walk every page of the open PortIO Properties dialog, then close it."""
    d = next(x for x in app.topLevelWidgets() if isinstance(x, bd_dialogs.PortIoPropertiesDialog) and x.isVisible())
    root = d.category_item; titles = []
    for item in [root] + [root.child(k) for k in range(root.childCount())]:
        d.show_page(item); QTest.qWait(60); titles.append(d.windowTitle()); shots.append(d.grab())
    ok(f'PortIO pages {titles}', titles == ['BD Object Properties - Port IO', 'BD Object Properties - Text Visibility',
                                            'BD Object Properties - Edit Appearance'])
    d.modes['inout'].setChecked(True); d.text_page.type.setChecked(True)
    d._ok()
QTimer.singleShot(300, drive2)
name = pio.name
w.port_properties(pio); QTest.qWait(100)
pio = next(p for p in w.bd.port_ios if p.name == name)
sig = next(s for s in w.bd.signals if s.name == name)
ok(f'port mode changed to inout ({pio.mode}/{sig.mode})', pio.mode == 'inout' and sig.mode == 'inout')
w.dirty = False

pm = QPixmap(2200, 1150); pm.fill(Qt.white); p = QPainter(pm)
x = y = 0; rowh = 0
for s in shots:
    if x + s.width() > 2200:
        x, y = 0, y + rowh + 10; rowh = 0
    p.drawPixmap(x, y, s); x += s.width() + 10; rowh = max(rowh, s.height())
p.end(); pm.save(os.path.join(OUT, 'bd_component_props.png'))
_env.finish(fails)
