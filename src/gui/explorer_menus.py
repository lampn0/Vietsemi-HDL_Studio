"""Right-click menus of the Design Explorer, in the order and grouping of the legacy tool.

Project page (DesignManager.libs / project_info):
    project_menu        My Project row          shared_menu      Shared Project row
    group_menu          Regular / Protected / Downstream Only Libraries
    library_menu        a library               page_blank_menu  empty space
Library tab (LibraryExplorer):
    unit_menu           a design unit (Design Units pane, or a unit of the Design Hierarchy pane)
    view_menu           a view below a unit
    file_menu           a file of the Files pane (source, generated or other)
    lib_folder_menu     the Design Files row of the Files pane
    explorer_blank_menu empty space of the Design Units / Files panes
    hier_root_menu      a hierarchy header row  hier_frame_menu  a FOR / IF generate frame
    hier_blank_menu     empty space of the Design Hierarchy pane

A menu is a list of entries: '-' (separator), (text, slot) / (text, slot, key) - greyed when slot
is None, the key only shown - or (text, [entries]) for a sub-menu (greyed when empty). Entries for
flows HDL Studio does not have are kept, greyed, so the menus read as in the legacy tool.
popup() shows such a list. A row counts as clicked only on its icon or text (text_item(),
install_hit_test()); anywhere else in the row is the pane's empty space.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QFontMetrics, QKeySequence
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QStyleOptionViewItem, QTreeWidget, QWidget

from project.project import DesignUnit, Library, View

if TYPE_CHECKING:
    from .design_manager import DesignManager, LibraryExplorer

Entry = 'str | tuple'
GREY = None                                     # slot of an entry HDL Studio does not offer


def text_item(tree: QTreeWidget, pos):
    """The item whose icon or text (first column) is under `pos` (viewport coordinates), else None.
    As in the legacy tool only these count: the rest of a row (right of the text, the other
    columns) is the pane's empty space.
    """
    item = tree.itemAt(pos)
    if item is None:
        return None
    rect = tree.visualItemRect(item)              # first column, after the indentation
    right = _text_right(tree, item)
    if right is None or right <= rect.left():     # geometry unknown: never make a row unclickable
        return item
    return item if rect.left() <= pos.x() <= right else None


def _text_right(tree: QTreeWidget, item) -> int | None:
    """Right end of the text of `item`'s first cell, as the style and the item delegate draw it.

    The geometry comes from the style itself (SE_ItemViewItemText, with the view's own item font,
    icon size and check box), the same as the selection highlight of gui/text_selection.py, so it is
    right whatever the platform style, font and scaling: on Linux the item views often use another
    font than the application, and an estimate from fixed metrics there left the text unclickable.
    None when the geometry cannot be worked out.
    """
    try:
        index = tree.indexFromItem(item, 0)
        opt = QStyleOptionViewItem()
        tree.initViewItemOption(opt)              # the view's font, icon size, ...
        opt.rect = tree.visualRect(index)
        tree.itemDelegate(index).initStyleOption(opt, index)
        style = tree.style()
        text = style.subElementRect(QStyle.SE_ItemViewItemText, opt, tree)
        margin = style.pixelMetric(QStyle.PM_FocusFrameHMargin, None, tree) + 1
        right = text.left() + QFontMetrics(opt.font).horizontalAdvance(opt.text) + 2 * margin + 2 * _PAD
        return min(right, opt.rect.right())
    except Exception:                             # noqa: BLE001 - a hit test must not break a click
        return None


_PAD = 4                                         # pixels around the icon and the text of a cell


class _BlankPressFilter(QObject):
    """Mouse presses on the empty part of a row (right of the text, other columns) act as on the
    pane's empty space, as in the legacy tool: a left press clears the selection, a right press
    leaves it alone (the context menu still comes, as the menu of the empty space), a double
    click does nothing. The branch area left of a row (+ / -) works as usual.
    """

    def eventFilter(self, obj, e):
        t = e.type()
        if t not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
            return False
        tree = obj.parent()
        pos = e.position().toPoint()
        item = tree.itemAt(pos)
        if item is None or pos.x() < tree.visualItemRect(item).left() or text_item(tree, pos) is not None:
            return False                         # empty space below the rows, branch area, text
        if t == QEvent.MouseButtonPress and e.button() == Qt.LeftButton:
            tree.clearSelection()
            tree.setCurrentItem(None)
        return True


def install_hit_test(tree: QTreeWidget) -> None:
    """Make clicks on `tree` follow text_item(): only the icon / text select or open a row."""
    f = _BlankPressFilter(tree)
    tree.viewport().installEventFilter(f)


def popup(entries: list, parent: QWidget, global_pos) -> None:
    """Show `entries` as a popup menu at `global_pos` (screen coordinates)."""
    m = QMenu(parent)
    _fill(m, entries)
    m.exec(global_pos)


def _fill(menu: QMenu, entries: list) -> None:
    """Add `entries` to `menu` (see the module docstring for their form)."""
    for e in entries:
        if e == '-':
            menu.addSeparator()
            continue
        text, what = e[0], e[1]
        if isinstance(what, list):
            sub = menu.addMenu(text)
            _fill(sub, what)
            sub.setEnabled(bool(what))
            continue
        a = menu.addAction(text)
        if len(e) > 2 and e[2]:
            a.setShortcut(QKeySequence(e[2]))  # shown only: the menu is gone before a key is pressed
            a.setShortcutVisibleInContextMenu(True)
        if len(e) > 3 and e[3] is not None:     # (text, slot, key, checked)
            a.setCheckable(True)
            a.setChecked(e[3])
        if what is None:
            a.setEnabled(False)
        else:
            a.triggered.connect(lambda checked=False, f=what: f())


def _copy(text: str) -> Callable:
    """Slot that puts `text` on the clipboard."""
    return lambda: QApplication.clipboard().setText(text)


def _copy_path(dm: 'DesignManager', path: str) -> tuple:
    """Copy Path to Clipboard > Hard Path (absolute) / Soft Path (with the project folder variable)."""
    if not path:
        return ('Copy Path to Clipboard', [])
    soft = dm.project.soft_path(path) if dm.project is not None else path
    return ('Copy Path to Clipboard', [('Hard Path to Clipboard', _copy(os.path.abspath(path))),
                                       ('Soft Path to Clipboard', _copy(soft))])


def _new_add(dm: 'DesignManager') -> list:
    """The New > / Add > sub-menus of the library panes."""
    return [('New', [('Design Content...', dm.new_unit)]),
            ('Add', [('Existing Files...', dm.add_existing_files)])]


# -- project page --------------------------------------------------------------------------
def project_menu(dm: 'DesignManager') -> list:
    """My Project row."""
    return [('Open Project...', dm.open_project_dialog),
            ('Close Project', dm.close_project),
            '-',
            ('Edit Path', GREY),
            ('Edit Project Description...', GREY),
            ('Edit Verilog Library Search Path ...', GREY),
            ('Advanced', [('Edit Verilog Implicit Includes...', GREY)]),
            '-',
            ('New Project...', dm.new_project),
            ('Save As...', GREY),
            '-',
            ('Refresh', dm.refresh_project, 'F5')]


def shared_menu(dm: 'DesignManager') -> list:
    """Shared Project row."""
    return [('Open Shared Project...', GREY),
            '-',
            ('Edit Path', GREY),
            ('Edit Project Description...', GREY),
            ('Edit Shared Project', GREY),
            '-',
            ('Reset to Default Shared Project', GREY),
            ('Save As...', GREY),
            '-',
            ('Refresh', dm.refresh_project, 'F5')]


def group_menu(dm: 'DesignManager', kind: str) -> list:
    """Regular / Protected / Downstream Only Libraries row."""
    return [('New Library...', dm.new_library),
            ('Refresh Libraries', lambda: dm.refresh_libraries(kind)),
            '-',
            ('Sort', [('Ascending', lambda: dm.sort_libraries(False), '', not dm.lib_sort_desc),
                      ('Descending', lambda: dm.sort_libraries(True), '', dm.lib_sort_desc)]),
            '-',
            ('Paste Mapping', GREY)]


def library_menu(dm: 'DesignManager', lib: Library) -> list:
    """A library on the Project page."""
    p = dm.project
    mode = [('Include All Library Files in the Project', GREY, '', lib.inclusion == 'all'),
            ('Include Specified Library Files in the Project', GREY, '', lib.inclusion != 'all')]
    kinds = [('Regular Library', 'regular'), ('Protected Library', 'protected'),
             ('Downstream Only Library', 'downstream')]
    types = [(t, None if k == lib.type else (lambda k=k: dm.change_library_type(lib, k))) for t, k in kinds]
    return [('Explore Library', lambda: dm.explore(lib)),
            ('Refresh Library', lambda: dm.refresh_library(lib)),
            ('Edit Library Mappings...', GREY),
            '-',
            ('Copy Mapping', GREY),
            ('Paste Mapping', GREY),
            ('Delete Library...', GREY),
            ('Rename', GREY, 'F2'),
            '-',
            ('Change Library Mode to', mode),
            ('Exclusions...', GREY),
            ('Allow Analysis for Sim/Synth', GREY),
            '-',
            ('Change Library Type To', types),
            '-',
            ('Edit Library Configuration Settings...', GREY),
            ('Set as Default Library', None if p is None or p.default_library == lib.name
             else lambda: dm.set_default_library(lib))]


def page_blank_menu(dm: 'DesignManager') -> list:
    """Empty space of the Project page."""
    has = dm.project is not None
    return [('New Library...', dm.new_library if has else GREY),
            '-',
            ('New Project...', dm.new_project),
            ('Open Project...', dm.open_project_dialog),
            ('Close Project', dm.close_project if has else GREY),
            '-',
            ('Paste Mapping', GREY),
            '-',
            ('Refresh', dm.refresh_project if has else GREY, 'F5')]


# -- library tab -----------------------------------------------------------------------------
def _root_entry(dm: 'DesignManager', du: DesignUnit) -> tuple:
    """Set Design Root, or Unset Design Root when `du` is the root already."""
    if dm.project is not None and dm.project.design_root_unit() is du:
        return ('Unset Design Root', dm.unset_design_root)
    return ('Set Design Root', lambda: dm.set_design_root(du))


def _generated_hdl(dm: 'DesignManager', du: DesignUnit) -> tuple:
    """View Generated HDL: the HDL file that describes the unit."""
    path = du.hdl.file if du.hdl is not None else ''
    return ('View Generated HDL', (lambda: dm.open_text_file(path, du.library)) if path else GREY, 'Ctrl+G')


def unit_menu(ex: 'LibraryExplorer', du: DesignUnit, in_hierarchy: bool = False,
              shown_root=None) -> list:
    """A design unit. In the Design Hierarchy pane (`in_hierarchy`) the cut / copy / delete entries
    follow that pane; `shown_root` is the header row when the unit is the top of a hierarchy
    shown there (Show Hierarchy then reads Hide Hierarchy).
    """
    dm = ex.dm
    if shown_root is not None:
        hier = ('Hide Hierarchy', lambda: ex.hide_hierarchy(shown_root), 'Shift+Space')
    else:
        hier = ('Show Hierarchy', lambda: ex.show_hierarchy(du), 'Shift+Space')
    out = [('Open', lambda: dm.open_unit(du), 'Ctrl+O')]
    if not in_hierarchy:
        out += _new_add(dm)
    out += [_generated_hdl(dm, du),
            '-',
            hier,
            ('Cross-Highlight', GREY)]
    if not in_hierarchy:
        out.append(('Update Where Used...', GREY))
    out += [('Reports', []),
            '-',
            ('Design Unit Cut', GREY),
            ('Design Unit Copy', GREY)]
    if not in_hierarchy:
        out += [('Paste', GREY, 'Ctrl+V'), ('Paste Special...', GREY)]
    else:
        out += ['-', _copy_path(dm, (du.default_view() or du.graphic_view()).path
                                if du.default_view() or du.graphic_view() else '')]
    out += ['-',
            ('Remove From Project', GREY),
            ('Delete Design Unit From Disk...', GREY),
            ('Delete Special...', GREY),
            ('Rename', GREY, 'F2'),
            '-',
            ('Check', lambda: dm.check_units([du])),
            '-',
            ('Convert To Graphics', []),
            ('Visualize Code As', []),
            '-',
            _root_entry(dm, du)]
    if in_hierarchy:
        out += [('Set Gate Level', GREY), ('Set Default View', GREY)]
    else:
        out += [('Toggle Top Marker', GREY), '-', ('Change Language To', [])]
    out += ['-',
            ("Don't Touch Settings...", GREY),
            ('Properties...', lambda: ex.unit_properties(du))]
    return out


def view_menu(ex: 'LibraryExplorer', du: DesignUnit, view: View) -> list:
    """A view below a unit in the Design Units pane (a symbol has a shorter menu)."""
    dm = ex.dm
    lib = du.library
    can_default = (view.kind != 'symbol' and not du.is_default(view) and lib.writable
                   and bool(lib.meta_dir))
    common = [('Open', lambda: dm.open_view(du, view), 'Ctrl+O'),
              _generated_hdl(dm, du),
              '-',
              ('Show Hierarchy', lambda: ex.show_hierarchy(du), 'Shift+Space'),
              ('Cross-Highlight', GREY),
              ('Reports', [])]
    if view.kind == 'symbol':
        return common + [('Update Where Used...', GREY),
                         '-',
                         ('Copy', GREY, 'Ctrl+C'),
                         _copy_path(dm, view.path),
                         '-',
                         ('Check', lambda: dm.check_units([du])),
                         '-',
                         _root_entry(dm, du),
                         '-',
                         ("Don't Touch Settings...", GREY),
                         ('Properties...', lambda: ex.unit_properties(du))]
    return common + ['-',
                     ('Cut', GREY, 'Ctrl+X'),
                     ('Copy', GREY, 'Ctrl+C'),
                     '-',
                     _copy_path(dm, view.path),
                     '-',
                     ('Delete From Disk...', GREY, 'Del'),
                     ('Delete Special...', GREY),
                     ('Rename', GREY, 'F2'),
                     '-',
                     ('Check', lambda: dm.check_units([du])),
                     '-',
                     _root_entry(dm, du),
                     ('Set Default View', (lambda: ex.set_default_view(du, view)) if can_default else GREY),
                     '-',
                     ("Don't Touch Settings...", GREY),
                     ('Properties...', lambda: ex.unit_properties(du))]


def file_menu(ex: 'LibraryExplorer', path: str, kind: str) -> list:
    """A file of the Files pane; `kind` is 'source', 'generated' or 'other' (view files, locks)."""
    dm, lib = ex.dm, ex.lib
    open_ = ('Open', lambda: dm.open_file(path, lib), 'Ctrl+O')
    if kind == 'generated':
        return [open_,
                '-',
                ('Cut', GREY, 'Ctrl+X'),
                ('Copy', GREY, 'Ctrl+C'),
                '-',
                _copy_path(dm, path),
                '-',
                ('Remove From Project', GREY),
                ('Delete From Disk...', GREY, 'Del'),
                ('Rename', GREY, 'F2'),
                ('Edit Reference...', GREY),
                '-',
                ('Update Graphics', GREY),
                ('Convert To Source File', GREY)]
    if kind == 'other':
        return [open_, '-', _copy_path(dm, path)]
    units = ex.units_in_file(path)
    return [open_,
            '-',
            ('Show Hierarchy', (lambda: ex.show_hierarchy(units[0])) if units else GREY, 'Shift+Space'),
            ('Cross-Highlight', GREY),
            ('Where Used...', GREY),
            ('Unbound Components', []),
            ('Where Bound (SV)', GREY),
            '-',
            ('Cut', GREY, 'Ctrl+X'),
            ('Copy', GREY, 'Ctrl+C'),
            ('Paste', GREY, 'Ctrl+V'),
            '-',
            _copy_path(dm, path),
            '-',
            ('Remove From Project', GREY),
            ('Delete From Disk...', GREY, 'Del'),
            ('Delete Special...', GREY),
            ('Rename', GREY, 'F2'),
            ('Edit Reference...', GREY),
            '-',
            ('Check', (lambda: dm.check_units(units)) if units else GREY),
            '-',
            ('Convert To Graphics', []),
            ('Visualize Code As', []),
            '-',
            ('Set Gate Level', GREY),
            ('Ignore Parser Gate Level Limits', GREY),
            '-',
            ('Set Language', []),
            ('Set as Include File', GREY),
            ("Don't Touch Settings...", GREY),
            ('Properties...', GREY)]


def lib_folder_menu(ex: 'LibraryExplorer', item) -> list:
    """The Design Files row of the Files pane (the library's HDL folder)."""
    dm = ex.dm
    return [('Expand All', lambda: ex.expand_all(item)),
            ('Collapse All', lambda: ex.collapse_all(item)),
            '-'] + _new_add(dm) + [
            '-',
            ('Cut Contents', GREY),
            ('Copy Contents', GREY),
            ('Paste', GREY, 'Ctrl+V'),
            ('Paste Special...', GREY),
            '-',
            _copy_path(dm, ex.lib.main_hdl_dir),
            '-',
            ('Remove Contents From Project', GREY),
            ('Delete Contents...', GREY),
            '-',
            ('Delete Generated HDL From Disk...', GREY),
            '-',
            ('Files With Critical Syntax Errors', GREY),
            '-',
            ('Edit Library Configuration Settings...', GREY),
            '-',
            ('Close Library', lambda: dm.close_explorer(ex))]


def explorer_blank_menu(ex: 'LibraryExplorer') -> list:
    """Empty space of the Design Units / Files panes."""
    dm = ex.dm
    return _new_add(dm) + [
        '-',
        ('Explore Library...', GREY, 'Alt+L'),
        '-',
        ('Refresh', ex.refresh, 'F5'),
        '-',
        ('Advanced Find...', GREY),
        '-',
        ('Sub Windows', []),
        '-',
        ('Close Current Design Explorer', lambda: dm.close_explorer(ex))]


def hier_root_menu(ex: 'LibraryExplorer', item, fixed: bool) -> list:
    """A header row of the Design Hierarchy pane (the top of the library cannot be hidden)."""
    return [('Expand All', lambda: ex.expand_all(item)),
            ('Collapse All', lambda: ex.collapse_all(item)),
            '-',
            ('Hide Hierarchy', GREY if fixed else (lambda: ex.hide_hierarchy(item)))]


def hier_frame_menu(ex: 'LibraryExplorer', du: DesignUnit) -> list:
    """A FOR / IF generate frame of the Design Hierarchy pane (`du`: the diagram holding it)."""
    return [('Open', lambda: ex.dm.open_unit(du), 'Ctrl+O'),
            _generated_hdl(ex.dm, du),
            '-',
            ('Cross-Highlight', GREY)]


def hier_blank_menu(ex: 'LibraryExplorer') -> list:
    """Empty space of the Design Hierarchy pane."""
    return [('Refresh', ex.refresh, 'F5'),
            '-',
            ('Sub Windows', []),
            '-',
            ('Hide All', ex.hide_all_hierarchies if ex.extra_roots else GREY),
            ('Hide Design Hierarchy Window', lambda: ex.dm.set_hierarchy_panes(False))]
