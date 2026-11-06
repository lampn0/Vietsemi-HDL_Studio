"""DM menu enable states vs. The legacy tool screenshots: python menu_state_test.py <hdp> <cfg>"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
HDP, CFG, OUT = _env.setup()
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from gui.design_manager import DesignManager

dm = DesignManager(); dm.load_project(HDP)
dm.tabs.setCurrentIndex(0)
dm.libs.clearSelection(); dm.libs.setCurrentItem(None)
fails = 0


from PySide6.QtWidgets import QMenu


def menu(path):
    """The menu action at menu path `path` (titles without the & mnemonics)."""
    # QAction.menu() hands the menu to Python in PySide6: walk the QMenu children instead
    parent = dm.menuBar()
    for name in path[:-1]:
        parent = next(m for m in parent.findChildren(QMenu, options=Qt.FindDirectChildrenOnly)
                      if m.title().replace('&', '') == name)
    return next(a for a in parent.actions() if a.text().replace('&', '') == path[-1])


def check(path, enabled):
    """Update the menu states and check that the entry at `path` is enabled / disabled as the legacy tool has it."""
    global fails
    dm._update_menu_states()
    a = menu(path)
    ok = a.isEnabled() == enabled
    fails += not ok
    print(('PASS' if ok else 'FAIL'), ' > '.join(path), 'enabled' if a.isEnabled() else 'grey')


# Project tab, nothing selected: as in the screenshots
for path, on in [
        (('File', 'New', 'Design Content...'), True), (('File', 'New', 'Project...'), True),
        (('File', 'New', 'Library...'), True), (('File', 'New', 'Test Bench...'), False),
        (('File', 'New', 'Registered View', 'Quartus', 'Quartus Workspace'), True),
        (('File', 'New', 'Registered View', 'Xilinx', 'Xilinx User Constraints File'), True),
        (('File', 'New', 'Registered View', 'Text Report File'), True),
        (('File', 'Add', 'Existing Design...'), True), (('File', 'Add', 'Existing Files...'), False),
        (('File', 'Add', 'Gate Level...'), False),
        (('File', 'Open', 'Design Content'), False), (('File', 'Open', 'Project...'), True),
        (('File', 'Close', 'Current Design Explorer'), False), (('File', 'Close', 'All Design Explorers'), True),
        (('File', 'Close', 'All Editor Windows'), True), (('File', 'Close', 'Close Project'), True),
        (('File', 'Explore Library'), False), (('File', 'Page Setup...'), True), (('File', 'Print...'), False),
        (('File', 'Print Hierarchy...'), False), (('File', 'Document And Visualize', 'Single Level'), False),
        (('File', 'Exit'), True),
        (('Edit', 'Cut'), False), (('Edit', 'Copy'), True), (('Edit', 'Paste'), False),
        (('Edit', 'Copy Path to Clipboard', 'Hard Path to Clipboard'), False),
        (('Edit', 'Remove From Project'), False), (('Edit', 'Delete From Disk...'), False),
        (('Edit', 'Rename'), False), (('Edit', 'Expand All'), False), (('Edit', 'Collapse All'), False),
        (('Edit', 'Select All'), True), (('Edit', 'Hide Hierarchy'), False), (('Edit', 'Cross-Highlight'), False),
        (('Edit', 'Set Design Root'), False), (('Edit', 'Toggle Top Marker'), False),
        (('Edit', 'Set Default View'), False), (('Edit', 'Change Language To', 'SystemVerilog'), False),
        (('Edit', 'Set Language', "VHDL '87"), False), (('Edit', 'Check'), True),
        (('Edit', 'Properties...'), False),
        (('View', 'Refresh'), True), (('View', 'Reload Library'), False),
        (('View', 'Change Explorer View', 'Design Units'), False),
        (('View', 'Sub Windows', 'Design Hierarchy'), True), (('View', 'Sub Windows', 'Layout'), False),
        (('View', 'Toolbars', 'Settings...'), True), (('View', 'Columns'), False), (('View', 'Filters'), False),
        (('HDL', 'Convert To Graphics', 'Single Level'), False), (('HDL', 'Visualize Code As', 'IBD'), False),
        (('HDL', 'Update Graphics'), False), (('HDL', 'Generate VHDL Configurations...'), True),
        (('HDL', 'View Generated HDL'), True)]:
    check(path, on)

# select a library in the project tree
lib_item = next(dm.libs.topLevelItem(0).child(k) for k in range(dm.libs.topLevelItem(0).childCount()))
dm.libs.setCurrentItem(lib_item); lib_item.setSelected(True)
check(('File', 'Explore Library'), True)
check(('Edit', 'Expand All'), True)
check(('Edit', 'Copy Path to Clipboard', 'Hard Path to Clipboard'), True)

# library explorer with a unit and a view selected
lib = dm.project.library('protocol_controller')
dm.explore(lib)
ex = dm._explorer()
it = ex.units.topLevelItem(0)
ex.units.setCurrentItem(it); it.setSelected(True)
check(('File', 'Open', 'Design Content'), True)
check(('File', 'Close', 'Current Design Explorer'), True)
check(('Edit', 'Set Design Root'), True)
check(('Edit', 'Properties...'), True)
check(('Edit', 'Set Default View'), False)
check(('View', 'Reload Library'), True)
check(('File', 'Add', 'Existing Files...'), True)
vi = next((ex.units.topLevelItem(k).child(c) for k in range(ex.units.topLevelItemCount())
           for c in range(ex.units.topLevelItem(k).childCount())
           if ex.units.topLevelItem(k).child(c).data(0, Qt.UserRole)[2].kind != 'symbol'), None)
ex.units.clearSelection(); ex.units.setCurrentItem(vi); vi.setSelected(True)
check(('Edit', 'Set Default View'), True)

# design root: arrow + diamond, blue text in the project tree and the unit list
du = lib.units['pc_global_controller'] if 'pc_global_controller' in lib.units else next(iter(lib.units.values()))
dm.set_design_root(du)
ex.refresh()
roots = [dm.libs.topLevelItem(0).child(k) for k in range(dm.libs.topLevelItem(0).childCount())]
root_lib = [r for r in roots if r.data(0, Qt.UserRole) is lib][0]
ok = root_lib.foreground(0).color().blue() == 220 and root_lib.icon(0).availableSizes()[0].width() == 48
print('PASS' if ok else 'FAIL', 'root library marked', root_lib.text(0)); fails += not ok
uit = [ex.units.topLevelItem(k) for k in range(ex.units.topLevelItemCount())
       if ex.units.topLevelItem(k).text(0) == du.name][0]
ok = uit.foreground(0).color().blue() == 220
print('PASS' if ok else 'FAIL', 'root unit marked', du.name); fails += not ok
others = [r for r in roots if r is not root_lib and r.foreground(0).color().blue() == 220]
print('PASS' if not others else 'FAIL', 'only one root library'); fails += bool(others)
print('active marker:', [r.text(0) for r in roots if '<active>' in r.text(0)])

# dialogs build
from gui.dm_options import PageSetupDialog, VerilogOptionsDialog
ps = PageSetupDialog(dm.prefs, dm); vo = VerilogOptionsDialog(dm.prefs, dm)
tabs = [ps.tabs.tabText(k) for k in range(ps.tabs.count())], [vo.tabs.tabText(k) for k in range(vo.tabs.count())]
ok = tabs == (['Layout', 'Boundaries', 'Misc'], ['File', 'Style', 'Headers', 'Default Directives', 'Default Packages'])
print('PASS' if ok else 'FAIL', 'dialog tabs', tabs); fails += not ok
vo.generated_ext.setCurrentText('vlg'); vo.apply(); dm._apply_verilog_options()
from project import generate
ok = generate.target_path(lib, 'abc', 'verilog').endswith('abc.vlg')
print('PASS' if ok else 'FAIL', 'generated extension live'); fails += not ok
vo.generated_ext.setCurrentText('v'); vo.apply(); dm._apply_verilog_options()
dm._show_hierarchy_window(True)
top = dm.hier_dock.widget().topLevelItem(0)
print('PASS' if top.text(0) == du.name else 'FAIL', 'Design Hierarchy window shows root', top.text(0))
fails += top.text(0) != du.name
print('FAILS', fails)
_env.finish(fails)
