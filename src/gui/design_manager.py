"""The Design Manager: the main window of HDL Studio (the legacy tool Design Manager).

    DesignManager    the window: menus and toolbars, the left launcher bar, the Project page
                     (libraries of the .hdp), one LibraryExplorer tab per library opened, the
                     Log, and the coordinator of everything else: opening projects, opening
                     views in editors (with locks and the session), generation, preferences.
    LibraryExplorer  the three panes of one library: Design Units (units and their views),
                     Files (HDL files and graphics folders) and Design Hierarchy.
    HierarchyWindow  the stand-alone Design Hierarchy below the project's design root.

Editors are kept in `self.editors` (key = view file path or text file path) so a view is
never opened twice. The session (session.py) is saved whenever windows open or close, and
unsaved editor contents are copied to the autosave folder on a timer.

Two caches make large projects fast: the parse cache of HDL files (Project.cache, saved
between runs) and the cache of each diagram's instances (view_cache, used by the hierarchy).
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from datetime import datetime

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QDockWidget, QFileDialog, QHBoxLayout, QHeaderView,
                               QLabel, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QSizePolicy, QSplitter, QStackedWidget, QStyle, QTabBar, QTabWidget, QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from hdl.parser import HAVE_SLANG
from bd_model import BlockDiagram
from model import FsmView
from formats.names import META_DIR, PROJECT_DIR_VAR
from version import APP_NAME
from prefs import Prefs, expand_header
from session import EditorState, Session, drop_autosave, read_autosave, write_autosave
from project.generate import GenResult, load_view, native_path
from project.project import DesignUnit, Library, Project, View, create_project, open_project
from project.templates import new_fsm, new_module
from .bd_editor import BdEditorWindow
from .branding import install_app_icon, show_about
from .status import StatusProgress
from .dm_toolbar import DmToolbars
from .dm_icons import ROOT_TEXT, dm_icon, library_icon, project_icon, tree_icon, unit_icon, view_icon
from .context import EditorContext, generate_with_prompt
from .menus import DM_MENUS, arrange_menus
from .dialogs import NewLibraryDialog, NewProjectDialog, NewUnitDialog, PreferencesDialog
from .main_window import MainWindow as FsmEditorWindow
from .text_editor import TextEditorWindow
from . import explorer_menus as M
from . import text_selection

RED = QBrush(QColor(200, 0, 0))
GREY = QBrush(QColor(130, 130, 130))


# File > New > Registered View: (menu text, file extension) or (submenu, [(text, extension)])
REGISTERED_VIEWS = [
    ('Quartus', [('Quartus Arguments', 'qarg'), ('Quartus Equation File', 'eqn'),
                 ('Quartus Pin Information File', 'pin'), ('Quartus Settings and Assigments', 'qsf'),
                 ('Quartus Summary File', 'summary'), ('Quartus Text Tabular Format Programming File', 'ttf'),
                 ('Quartus Verilog Mapping File', 'vqm'), ('Quartus Workspace', 'qws')]),
    ('Xilinx', [('Xilinx ASCII Configuration File', 'rbt'), ('Xilinx Bitstream Generation Report', 'bgn'),
                ('Xilinx Design Rule Checking Report', 'drc'), ('Xilinx Floorplanner File', 'fnf'),
                ('Xilinx Jedec Bit Map File', 'jed'), ('Xilinx Mapping Report', 'mrp'),
                ('Xilinx NGDBuild Log', 'bld'), ('Xilinx Netlist Constraint File', 'ncf'),
                ('Xilinx Pad Report', 'pad'), ('Xilinx Place and Route Constraints File', 'pcf'),
                ('Xilinx Place and Route Report', 'par'), ('Xilinx Static Timing Report', 'twr'),
                ('Xilinx Synthesis Constraints File', 'xcf'), ('Xilinx Synthesis Report', 'syr'),
                ('Xilinx User Constraints File', 'ucf')]),
    ('Binary Synthesis File', 'db'), ('C Source File', 'c'), ('C++ Source File', 'cpp'),
    ('Constraint File', 'cst'), ('Cross Reference File', 'xrf'), ('Delay Report', 'dly'),
    ('HEX-Format File', 'hex'), ('Log File', 'log'), ('Memory Initialization File', 'mif'),
    ('Pad Report', 'pad'), ('Property Specification Language File', 'psl'), ('RA control file', 'ra'),
    ('Report File', 'rpt'), ('Standard Delay File', 'sdf'), ('Standard Delay Format File', 'sdo'),
    ('Synopsys Design Constraint File', 'sdc'), ('Text Report File', 'txt')]

# Edit > Change Language To / Set Language: listed as in the legacy tool, greyed
LANGUAGES_CHANGE = ["Verilog '95", 'Verilog 2005', 'SystemVerilog', 'VHDL 2008', 'VHDL 2002', "VHDL '93", "VHDL '87"]
LANGUAGES_SET = ["VHDL '87", "VHDL '93", 'VHDL 2002', 'VHDL 2008', "Verilog '95", 'Verilog 2005', 'SystemVerilog']


def _ts(t: float) -> str:
    """A modification time as the Time Stamp column shows it ('' for 0)."""
    return datetime.fromtimestamp(t).strftime('%a %b %d %Y %H:%M:%S') if t else ''


def _size(path: str) -> str:
    """File size in KB as the Files pane shows it ('' when unreadable)."""
    try:
        return f'{max(1, os.path.getsize(path) // 1024)} KB'
    except OSError:
        return ''


class WrapToolButton(QToolButton):
    """A tool button (icon beside text) whose text breaks onto more lines, at spaces, when the
    button is too narrow for it on one line, and joins again when it is widened. Used on the
    Project page of the left bar, which the user can make wider or narrower.
    """
    PAD = 22                    # margins, icon-to-text spacing and style padding, in pixels

    def __init__(self, text: str):
        """Button showing `text` (wrapped to the width it gets)."""
        super().__init__()
        self._full = text
        self.setText(text)

    def _wrapped(self, width: int) -> str:
        """`_full` broken into lines no wider than the room left beside the icon (a single word
        longer than that stays on its own line).
        """
        room = width - self.iconSize().width() - self.PAD
        fm = self.fontMetrics()
        if room <= 0 or fm.horizontalAdvance(self._full) <= room:
            return self._full
        lines: list[str] = []
        for word in self._full.split():
            if lines and fm.horizontalAdvance(lines[-1] + ' ' + word) <= room:
                lines[-1] += ' ' + word
            else:
                lines.append(word)
        return '\n'.join(lines)

    def resizeEvent(self, event):
        """Re-wrap the text for the new width (the height follows through the layout)."""
        text = self._wrapped(event.size().width())
        if text != self.text():
            self.setText(text)
        super().resizeEvent(event)


class LibraryExplorer(QWidget):
    """Design Units / Files / Design Hierarchy panes for one library."""

    def __init__(self, dm: 'DesignManager', lib: Library):
        """Build the three panes for library `lib` of the Design Manager `dm` and fill them."""
        super().__init__()
        self.dm, self.lib = dm, lib
        self.units = QTreeWidget()
        self.units.setHeaderLabels(['Design Unit', 'Type', 'Language', 'Time Stamp'])
        self.units.setIconSize(QSize(40, 16))         # room for the default-view arrow and root diamond
        self.units.setExpandsOnDoubleClick(False)     # double-click opens the default view; + expands
        self.files = QTreeWidget()
        self.files.setHeaderLabels(['Files', 'Type', 'Size', 'Time Stamp'])
        self.hier = QTreeWidget()
        self.hier.setHeaderLabels(['Design Hierarchy', 'Design Unit Name', 'Extends', 'Name', 'Library'])
        self.extra_roots: list[tuple[str, str]] = []    # (library, unit) added with Show Hierarchy
        for t in (self.units, self.files, self.hier):
            t.setAlternatingRowColors(True)
            t.setUniformRowHeights(True)
            t.header().setSectionResizeMode(QHeaderView.Interactive)
            t.setContextMenuPolicy(Qt.CustomContextMenu)
            t.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.units.itemDoubleClicked.connect(self._open_item)
        self.files.itemDoubleClicked.connect(self._open_item)
        self.hier.itemDoubleClicked.connect(self._open_item)
        self.hier.itemExpanded.connect(self._expand_hier)
        for t in (self.units, self.files, self.hier):
            t.customContextMenuRequested.connect(lambda pos, t=t: self._menu(t, pos))
            M.install_hit_test(t)
            text_selection.apply(t)
        left = QSplitter(Qt.Vertical)
        left.addWidget(self.units)
        left.addWidget(self.files)
        main = QSplitter(Qt.Horizontal)
        main.addWidget(left)
        main.addWidget(self.hier)
        main.setSizes([800, 650])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(main)
        self.refresh()

    # -- filling ---------------------------------------------------------------------
    def refresh(self):
        """Rescan the library (HDL files parsed again only when changed), report problems in the Log
        and fill the three panes again.
        """
        lib = self.lib
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            lib.scan(self.dm.project.cache, self.dm.project.progress)
        finally:
            QApplication.restoreOverrideCursor()
        msgs = list(lib.errors)
        if lib.unparsed_count():
            msgs.append(f'{lib.unparsed_count()} file(s) not parsed (see the Files pane)')
        if not HAVE_SLANG:
            msgs.append('pyslang is not installed: ports/instances are not read from HDL files')
        for m in msgs:                              # scan problems go to the log, the panes stay at the top
            self.dm.log(f'{lib.name}: {m}', 'warning')
        self._fill_units()
        self._fill_files()
        self._fill_hierarchy()

    def _fill_units(self):
        """Design Units pane: one row per unit (icon, type, language, time stamp; red when its file has
        errors, blue for the design root, bold with a graphical view) with its views below it
        (the default view marked).
        """
        self.units.clear()
        lib = self.lib
        root = self.dm.project.design_root_unit() if self.dm.project else None
        for name in sorted(lib.units, key=str.lower):
            du = lib.units[name]
            it = QTreeWidgetItem([du.name, du.type, du.language, _ts(du.mtime)])
            it.setIcon(0, tree_icon(unit_icon(du), root=du is root))
            it.setData(0, Qt.UserRole, ('unit', du))
            default = du.default_view()
            if default is not None:
                it.setToolTip(0, f'{du.name}: double-click opens the default view ({default.name}, {default.label})')
            if du is root:
                it.setForeground(0, QBrush(ROOT_TEXT))
                it.setToolTip(0, f'Design root: {self.dm.project.design_root}')
            if du.file_errors:
                for c in range(4):
                    it.setForeground(c, RED)
                it.setToolTip(0, '\n'.join(du.file_errors[:10]))
            for v in du.views:
                vi = QTreeWidgetItem([v.name, v.label, v.language or du.language, _ts(v.mtime)])
                is_default = du.is_default(v)
                vi.setIcon(0, tree_icon(view_icon(v), is_default))
                vi.setData(0, Qt.UserRole, ('view', du, v))
                note = '\nLegacy file: saved as .json next to it when edited' if v.legacy and v.kind in ('fsm', 'bd') else ''
                vi.setToolTip(0, v.path + ('\nDefault view' if is_default else '') + note)
                if v.kind == 'other':
                    for c in range(4):
                        vi.setForeground(c, GREY)
                it.addChild(vi)
            if du.graphic_view() is not None:
                # the pane's own font in bold (not a QFont made at import, before the application:
                # on Linux that one does not match the font the item views use)
                bold = QFont(self.units.font())
                bold.setBold(True)
                it.setFont(0, bold)
            self.units.addTopLevelItem(it)
        self.units.resizeColumnToContents(0)

    def _fill_files(self):
        """Files pane: the HDL files (red when they do not parse) and the graphics folder per unit."""
        self.files.clear()
        lib = self.lib
        hdl = QTreeWidgetItem(['Design Files', '', '', ''])
        hdl.setIcon(0, dm_icon('design_files'))
        hdl.setData(0, Qt.UserRole, ('libfolder',))
        generated = self._generated_files()
        for path in lib.hdl_files():
            parsed = lib.files.get(path)
            kind = 'generated' if os.path.normcase(os.path.abspath(path)) in generated else 'source'
            it = QTreeWidgetItem([lib.relative_name(path), 'Generated File' if kind == 'generated' else 'Source File',
                                  _size(path), _ts(os.path.getmtime(path))])
            it.setData(0, Qt.UserRole, ('file', path, kind))
            it.setToolTip(0, path)
            it.setIcon(0, dm_icon('file_error' if parsed and parsed.errors else 'file_hdl'))
            if parsed and parsed.errors:
                for c in range(4):
                    it.setForeground(c, RED)
                it.setToolTip(0, path + '\n' + '\n'.join(parsed.errors[:10]))
            hdl.addChild(it)
        self.files.addTopLevelItem(hdl)
        hdl.setExpanded(True)
        if lib.meta_dir and os.path.isdir(lib.meta_dir):
            gfx = QTreeWidgetItem([f'Graphics ({META_DIR})', '', '', ''])
            gfx.setIcon(0, dm_icon('folder'))
            for unit in sorted(os.listdir(lib.meta_dir)):
                d = os.path.join(lib.meta_dir, unit)
                if unit.startswith('.') or not os.path.isdir(d):
                    continue
                ui = QTreeWidgetItem([unit, 'Folder', '', ''])
                ui.setIcon(0, dm_icon('folder'))
                for f in sorted(os.listdir(d)):
                    p = os.path.join(d, f)
                    if os.path.isfile(p) and not f.startswith('.'):
                        fi = QTreeWidgetItem([f, 'Lock' if f.endswith('.lck') else 'View file', _size(p),
                                              _ts(os.path.getmtime(p))])
                        fi.setData(0, Qt.UserRole, ('file', p, 'other'))
                        fi.setIcon(0, dm_icon('file_lock' if f.endswith('.lck') else 'file_view'))
                        ui.addChild(fi)
                gfx.addChild(ui)
            self.files.addTopLevelItem(gfx)
        self.files.resizeColumnToContents(0)

    def _top_units(self) -> list[DesignUnit]:
        """Units not instantiated by any other unit of this library."""
        used = set()
        for du in self.lib.units.values():
            for _, child, _, _ in self.dm.children_of(du):
                used.add(child)
        tops = [du for du in self.lib.units.values() if du.name not in used and du.type != 'Package']
        return sorted(tops, key=lambda d: d.name.lower())

    # -- design hierarchy: the library's top unit always, others added with Show Hierarchy --
    def fixed_root(self) -> DesignUnit | None:
        """Top of the library: the project's design root when it is here, else the unit
        named after the library, else the top unit with the most instances."""
        p = self.dm.project
        root = p.design_root_unit() if p is not None else None
        if root is not None and root.library is self.lib:
            return root
        if self.lib.name in self.lib.units:
            return self.lib.units[self.lib.name]
        tops = self._top_units()
        return max(tops, key=lambda d: (len(self.dm.children_of(d)), d.name)) if tops else None

    def _unit_by_key(self, key: tuple[str, str]) -> DesignUnit | None:
        """The unit for a (library, unit) key, or None when it no longer exists."""
        lib = self.dm.project.library(key[0]) if self.dm.project else None
        return self.dm.project.find_unit(key[1], prefer=lib) if lib is not None else None

    def _fill_hierarchy(self):
        """Design Hierarchy pane: the library's top unit, then the units added with Show Hierarchy."""
        self.hier.clear()
        fixed = self.fixed_root()
        if fixed is not None:
            self.hier.addTopLevelItem(self._root_item(fixed, True))
        for key in list(self.extra_roots):
            du = self._unit_by_key(key)
            if du is None or du is fixed:
                self.extra_roots.remove(key)
                continue
            self.hier.addTopLevelItem(self._root_item(du, False))
        for i in range(self.hier.topLevelItemCount()):
            top = self.hier.topLevelItem(i)
            top.setExpanded(True)
            if top.childCount():
                top.child(0).setExpanded(True)
        for c in range(self.hier.columnCount()):
            self.hier.resizeColumnToContents(c)

    def _root_item(self, du: DesignUnit, fixed: bool) -> QTreeWidgetItem:
        """A hierarchy root: a header row with the unit itself below it."""
        it = QTreeWidgetItem([du.name, du.name, '', du.name, du.library.name])
        it.setIcon(0, dm_icon('hierarchy_root'))
        it.setData(0, Qt.UserRole, ('root', du, fixed))
        if du is self.dm.project.design_root_unit():
            it.setForeground(0, QBrush(ROOT_TEXT))
        it.setToolTip(0, f'Top of library {du.library.name}' if fixed else
                      f'Added with Show Hierarchy; right-click > Hide Hierarchy to remove')
        it.addChild(self._hier_item(du.name, du, du.library.name))
        return it

    def show_hierarchy(self, du: DesignUnit):
        """Add the hierarchy below `du` to the pane (or go to it if it is already shown)."""
        key = (du.library.name, du.name)
        if du is not self.fixed_root() and key not in self.extra_roots:
            self.extra_roots.append(key)
            self.hier.addTopLevelItem(self._root_item(du, False))
            top = self.hier.topLevelItem(self.hier.topLevelItemCount() - 1)
            top.setExpanded(True)
            top.child(0).setExpanded(True)
            self.dm.session_changed()
        for i in range(self.hier.topLevelItemCount()):
            top = self.hier.topLevelItem(i)
            if top.data(0, Qt.UserRole)[1] is du:
                self.hier.setCurrentItem(top)
                self.hier.scrollToItem(top)

    def hide_hierarchy(self, item: QTreeWidgetItem):
        """Hide Hierarchy: remove a root added with Show Hierarchy (the fixed top cannot be removed)."""
        d = item.data(0, Qt.UserRole)
        if not d or d[0] != 'root' or d[2]:
            return
        key = (d[1].library.name, d[1].name)
        if key in self.extra_roots:
            self.extra_roots.remove(key)
        self.hier.takeTopLevelItem(self.hier.indexOfTopLevelItem(item))
        self.dm.session_changed()

    def expand_all(self, item: QTreeWidgetItem, limit: int = 5000):
        """Expand everything below `item` (instances are read as their level opens)."""
        todo, n = [(item, ())], 0
        while todo and n < limit:
            it, path = todo.pop()
            d = it.data(0, Qt.UserRole)
            du = d[1] if d and d[0] in ('unit', 'root') else None
            if du is not None and du.name in path:
                continue                        # recursive instantiation: stop here
            it.setExpanded(True)
            n += 1
            sub = path + ((du.name,) if du is not None and d[0] == 'unit' else ())
            todo.extend((it.child(k), sub) for k in range(it.childCount() - 1, -1, -1))

    def collapse_all(self, item: QTreeWidgetItem):
        """Collapse everything below `item`."""
        todo = [item]
        while todo:
            it = todo.pop()
            it.setExpanded(False)
            todo.extend(it.child(k) for k in range(it.childCount()))

    def _hier_item(self, label: str, du: DesignUnit | None, libname: str, unit_name: str = '') -> QTreeWidgetItem:
        """One hierarchy row: instance `label` of unit `du` (red "(not found)" when du is None). Its
        children are read only when the row is expanded (see _expand_hier).
        """
        view = du.default_view() if du else None
        name = du.name if du else unit_name
        it = QTreeWidgetItem([label, name, '', name, libname if du or libname else '(not found)'])
        it.setData(0, Qt.UserRole, ('unit', du) if du else None)
        it.setIcon(0, view_icon(view) if view is not None else unit_icon(du))
        if view is not None:
            it.setToolTip(0, f'{label}: {name} ({view.label})')
        if du is None:
            it.setToolTip(0, f'{label}: {name} not found' + (f' in library {libname}' if libname else '')
                          + ' (library not mapped or unit missing)')
            for c in range(5):
                it.setForeground(c, RED)
        elif self.dm.may_have_children(du):          # the diagram is read when the row opens
            it.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            it.setData(1, Qt.UserRole, 'unexpanded')
        return it

    def _expand_hier(self, item: QTreeWidgetItem):
        """A hierarchy row opened for the first time: add the instances of its unit, grouped under the
        generate frames (FOR / IF) they are in.
        """
        if item.data(1, Qt.UserRole) != 'unexpanded':
            return
        item.setData(1, Qt.UserRole, 'expanded')
        data = item.data(0, Qt.UserRole)
        du = data[1] if data else None
        if du is None:
            return
        groups: dict[str, QTreeWidgetItem] = {}
        # frames first (by name), then the other instances in diagram order, as the legacy tool lists them
        children = sorted(self.dm.children_of(du), key=lambda c: (0, c[3]) if c[3] else (1, []))
        for inst, child, libname, gen in children:
            parent = item
            for g in gen:
                key = '/'.join(gen[:gen.index(g) + 1])
                if key not in groups:
                    frame_name = g.split(':', 1)[-1].strip()
                    groups[key] = QTreeWidgetItem([g, du.name, '', frame_name, du.library.name])
                    groups[key].setIcon(0, dm_icon('frame'))
                    groups[key].setData(0, Qt.UserRole, ('frame', du))
                    parent.addChild(groups[key])
                parent = groups[key]
            lib = self.dm.project.library(libname) if libname else None
            cdu = self.dm.project.find_unit(child, prefer=lib or du.library)
            parent.addChild(self._hier_item(inst, cdu, cdu.library.name if cdu else (libname or ''), child))
        item.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicatorWhenChildless)

    # -- actions ------------------------------------------------------------------------
    def selected_units(self) -> list[DesignUnit]:
        """The design units selected in the Design Units pane (a view row counts as its unit)."""
        out = []
        for it in self.units.selectedItems():
            d = it.data(0, Qt.UserRole)
            if d and d[1] not in out:
                out.append(d[1])
        return out

    def _open_item(self, item: QTreeWidgetItem, col: int):
        """Double-click: a unit opens its default view, a view opens in its editor, a file opens in
        the text editor.
        """
        d = item.data(0, Qt.UserRole)
        if not d:
            return
        if d[0] in ('root', 'frame'):
            self.dm.open_unit(d[1])
        elif d[0] == 'unit' and d[1] is not None:
            self.dm.open_unit(d[1])             # Design Units or Design Hierarchy row
        elif d[0] == 'view':
            self.dm.open_view(d[1], d[2])
        elif d[0] == 'file':
            self.dm.open_file(d[1], self.lib)

    def _menu(self, tree: QTreeWidget, pos):
        """Right-click in a pane: the menu of the row under the mouse (gui/explorer_menus.py), or
        of the pane's empty space (a row counts only on its icon / text, as in the legacy tool)."""
        item = M.text_item(tree, pos)
        d = item.data(0, Qt.UserRole) if item is not None else None
        if item is None:
            entries = M.hier_blank_menu(self) if tree is self.hier else M.explorer_blank_menu(self)
        elif not d:
            return
        elif d[0] == 'root':
            entries = M.hier_root_menu(self, item, d[2])
        elif d[0] == 'frame':
            entries = M.hier_frame_menu(self, d[1])
        elif d[0] == 'libfolder':
            entries = M.lib_folder_menu(self, item)
        elif d[0] == 'view':
            entries = M.view_menu(self, d[1], d[2])
        elif d[0] == 'unit' and d[1] is not None:
            parent = item.parent()
            pd = parent.data(0, Qt.UserRole) if parent is not None else None
            shown = parent if pd and pd[0] == 'root' else None
            entries = M.unit_menu(self, d[1], in_hierarchy=tree is self.hier, shown_root=shown)
        elif d[0] == 'file':
            entries = M.file_menu(self, d[1], d[2] if len(d) > 2 else 'other')
        else:
            return
        M.popup(entries, self, tree.viewport().mapToGlobal(pos))

    def units_in_file(self, path: str) -> list[DesignUnit]:
        """Design units of the library described in HDL file `path`."""
        key = os.path.normcase(os.path.abspath(path))
        return [du for du in self.lib.units.values()
                if du.hdl is not None and os.path.normcase(os.path.abspath(du.hdl.file)) == key]

    def _generated_files(self) -> set[str]:
        """HDL files generated from a graphical view (normalised paths)."""
        return {os.path.normcase(os.path.abspath(du.hdl.file)) for du in self.lib.units.values()
                if du.hdl is not None and du.graphic_view() is not None}

    def hide_all_hierarchies(self):
        """Hide All: remove every hierarchy added with Show Hierarchy (the library top stays)."""
        for i in range(self.hier.topLevelItemCount() - 1, -1, -1):
            d = self.hier.topLevelItem(i).data(0, Qt.UserRole)
            if d and d[0] == 'root' and not d[2]:
                self.hier.takeTopLevelItem(i)
        self.extra_roots.clear()
        self.dm.session_changed()

    def set_default_view(self, du: DesignUnit, view: View):
        """Set Default View: remember `view` as the one a double-click on the unit opens."""
        try:
            du.library.set_default_view(du.name, view)
        except OSError as e:
            QMessageBox.warning(self, 'Set Default View', str(e))
            return
        self.dm.log(f'{du.library.name}/{du.name}: default view is now {view.name} ({view.label})')
        self._fill_units()
        self._fill_hierarchy()

    def unit_properties(self, du: DesignUnit):
        """Properties...: a summary of the unit and its views."""
        default = du.default_view()
        rows = [('Design unit', du.name), ('Library', du.library.name), ('Type', du.type),
                ('Language', du.language or '-'), ('Default view', f'{default.name} ({default.label})' if default else '-')]
        text = '<table>' + ''.join(f'<tr><td><b>{k}</b>&nbsp;&nbsp;</td><td>{v}</td></tr>' for k, v in rows)
        text += '<tr><td colspan=2><br><b>Views</b></td></tr>' + ''.join(
            f'<tr><td>{v.name}</td><td>{v.label} &nbsp; <small>{v.path}</small></td></tr>' for v in du.views)
        QMessageBox.information(self, f'Properties - {du.name}', text + '</table>')


class HierarchyWindow(QTreeWidget):
    """View > Sub Windows > Design Hierarchy: the hierarchy below the project's design root."""
    _hier_item = LibraryExplorer._hier_item
    _expand_hier = LibraryExplorer._expand_hier

    def __init__(self, dm: 'DesignManager'):
        """An empty tree; fill() shows the hierarchy."""
        super().__init__()
        self.dm = dm
        self.setHeaderLabels(['Design Hierarchy', 'Design Unit Name', 'Extends', 'Name', 'Library'])
        self.itemExpanded.connect(self._expand_hier)
        self.itemDoubleClicked.connect(self._open)

    def fill(self):
        """Show the hierarchy below the design root (or a hint when there is none)."""
        self.clear()
        root = self.dm.project.design_root_unit() if self.dm.project else None
        if root is None:
            self.addTopLevelItem(QTreeWidgetItem(['No design root: Edit > Set Design Root']))
            return
        it = self._hier_item(root.name, root, root.library.name)
        it.setIcon(0, tree_icon(view_icon(root.default_view()) if root.default_view() else unit_icon(root), root=True))
        it.setForeground(0, QBrush(ROOT_TEXT))
        self.setIconSize(QSize(40, 16))
        self.addTopLevelItem(it)
        it.setExpanded(True)
        self.resizeColumnToContents(0)

    def _open(self, item, col):
        """Double-click on a row opens the unit's default view."""
        d = item.data(0, Qt.UserRole)
        if d and d[1] is not None:
            self.dm.open_unit(d[1])


class DesignManager(QMainWindow):
    """The Design Manager window (see the module docstring)."""
    def __init__(self):
        """Build the window: preferences, caches, actions and menus, left bar, project page, log,
        timers (autosave, session) and the dock windows.
        """
        super().__init__()
        install_app_icon()                  # Vietsemi mark on every window and dialog
        self.prefs = Prefs.load()
        self.project: Project | None = None
        # status bar progress while a project opens and its libraries are scanned
        self.progress = StatusProgress(self.statusBar())
        self.editors: dict[str, QMainWindow] = {}
        self.explorers: dict[str, LibraryExplorer] = {}
        self.view_cache: dict[tuple[str, float], list] = {}
        self._load_hier_cache()

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        # Project tab: "Design Explorer" title, the project settings, then the libraries by group
        self.project_page = QWidget()
        pl = QVBoxLayout(self.project_page)
        pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)
        title = QLabel('Design Explorer')
        title.setStyleSheet('background:#000080; color:white; padding:2px 4px;')
        pl.addWidget(title)
        self.project_info = QTreeWidget()
        self.project_info.setHeaderHidden(True)
        self.project_info.setRootIsDecorated(True)
        self.project_info.setFixedHeight(84)
        self.project_info.setContextMenuPolicy(Qt.CustomContextMenu)
        self.project_info.customContextMenuRequested.connect(lambda pos: self._page_menu(self.project_info, pos))
        pl.addWidget(self.project_info)
        self.show_protected = QCheckBox('Show protected libraries')   # state of the Protected group check box
        self.show_protected.setChecked(True)
        self.show_protected.toggled.connect(self.fill_project)
        self.libs = QTreeWidget()
        self.libs.setHeaderHidden(True)
        self.libs.setIconSize(QSize(48, 16))          # arrow, book, people, design-root diamond
        self.libs.itemDoubleClicked.connect(lambda it, c: self.explore(it.data(0, Qt.UserRole)))
        self.libs.itemChanged.connect(self._lib_group_checked)
        self.libs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.libs.customContextMenuRequested.connect(lambda pos: self._page_menu(self.libs, pos))
        for t in (self.project_info, self.libs):
            M.install_hit_test(t)
            text_selection.apply(t)
        self.lib_sort_desc = False                     # Sort > Descending on a library group
        pl.addWidget(self.libs, 1)
        self.tabs.addTab(self.project_page, 'Project')
        self.tabs.tabBar().setTabButton(0, QTabBar.RightSide, None)
        self.setCentralWidget(self.tabs)

        self.log_list = QListWidget()
        self.log_list.setFont(QFont('Courier New', 9))
        self.log_list.itemDoubleClicked.connect(self._log_open)
        d = QDockWidget('Log', self)
        d.setObjectName('log')
        d.setWidget(self.log_list)
        self.addDockWidget(Qt.BottomDockWidgetArea, d)
        self.resizeDocks([d], [140], Qt.Vertical)

        self.object_tips = True
        self.toolbar_tips = True
        QApplication.instance().installEventFilter(self)     # View > Object Tips
        self._build_actions()
        self.resize(1500, 900)
        self.fill_project()

        # session: saved shortly after windows open/close, and with the autosave every 30 s
        self._session_quiet = False         # True while restoring or quitting
        self._session_timer = QTimer(self); self._session_timer.setSingleShot(True)
        self._session_timer.setInterval(800)
        self._session_timer.timeout.connect(self.save_session)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self.autosave)
        self._apply_save_settings()
        self._apply_verilog_options()

    # -- menus & toolbars ---------------------------------------------------------------
    def _act(self, menu, text, slot, key=None, tb=None):
        """Create an action `text` -> `slot` (optional shortcut), add it to `menu` and, when `tb` is a
        list, to that toolbar list.
        """
        a = QAction(text, self)
        if key:
            a.setShortcut(key)
        a.triggered.connect(slot)
        if menu is not None:
            menu.addAction(a)
        if isinstance(tb, list):
            tb.append(a)
        elif tb is not None:
            tb.addAction(a)
        return a

    def _build_actions(self):
        """Menu bar of the legacy Design Manager. Entries HDL Studio does not offer are greyed;
        entries that need a selection (`when`) are enabled from the current selection."""
        mb = self.menuBar()
        self._when: list[tuple[QAction, str]] = []

        def item(menu, text, slot=None, key=None, checkable=False, checked=False, to=None, when=None):
            """Add an entry to `menu`: a disabled placeholder when `slot` is None."""
            a = menu.addAction(text)
            if key:
                a.setShortcut(QKeySequence(key))
            if checkable:
                a.setCheckable(True); a.setChecked(checked)
                if slot is not None:
                    a.toggled.connect(slot)
            elif slot is not None:
                a.triggered.connect(slot)
            if slot is None:
                a.setEnabled(False)
            elif when:
                self._when.append((a, when))
            if to is not None:
                to.append(a)
            return a

        def sub(menu, text, entries=()):
            """Submenu; an entry is a text (greyed), '-' or (text, slot, when)."""
            m = menu.addMenu(text)
            for e in entries:
                if e == '-':
                    m.addSeparator()
                elif isinstance(e, tuple):
                    item(m, e[0], e[1], when=e[2] if len(e) > 2 else None)
                else:
                    item(m, e)
            return m

        # File
        fm = mb.addMenu('&File')
        new = self.new_menu = fm.addMenu('&New')
        item(new, '&Design Content...', self.new_unit, QKeySequence.New, when='project')
        reg = new.addMenu('&Registered View')
        for name, entries in REGISTERED_VIEWS:
            if isinstance(entries, list):
                s = reg.addMenu(name)
                for n, ext in entries:
                    item(s, n, lambda checked=False, n=n, e=ext: self.new_registered_view(n, e), when='project')
            else:
                item(reg, name, lambda checked=False, n=name, e=entries: self.new_registered_view(n, e),
                     when='project')
        self.act_new_project = item(new, '&Project...', self.new_project)
        item(new, '&Library...', self.new_library, when='project')
        item(new, '&Test Bench...')
        sub(fm, '&Add', [('&Existing Design...', self.new_library, 'project'),
                         ('Existing &Files...', self.add_existing_files, 'lib'), '&Gate Level...'])
        op = fm.addMenu('&Open')
        item(op, '&Design Content', lambda: self._with_unit(self.open_unit), when='unit')
        item(op, '&Project...', self.open_project_dialog, QKeySequence.Open)
        cl = fm.addMenu('&Close')
        item(cl, '&Current Design Explorer', lambda: self._close_tab(self.tabs.currentIndex()), when='explorer')
        item(cl, '&All Design Explorers', self.close_explorers, when='project')
        item(cl, 'All &Editor Windows', self.close_editors)
        item(cl, 'Close &Project', self.close_project)
        fm.addSeparator()
        item(fm, '&Explore Library', lambda: self.explore(self._selected_lib()), when='lib')
        fm.addSeparator()
        item(fm, 'Page Set&up...', self.page_setup)
        item(fm, '&Print...', None, 'Ctrl+P')
        item(fm, 'Print &Hierarchy...')
        fm.addSeparator()
        sub(fm, '&Document And Visualize', ['Single Level', 'Hierarchy Through Components', 'Through Design Root'])
        fm.addSeparator()
        item(fm, 'E&xit', self.close)

        # Edit
        em = mb.addMenu('&Edit')
        item(em, 'Cu&t', None, 'Ctrl+X')
        item(em, '&Copy', self.copy_selection, 'Ctrl+C')
        item(em, '&Paste', None, 'Ctrl+V')
        item(em, 'Paste &Special...')
        em.addSeparator()
        sub(em, 'Copy Path to Clip&board', [('&Hard Path to Clipboard', lambda: self._copy_path('hard'), 'item'),
                                            ('&Soft Path to Clipboard', lambda: self._copy_path('soft'), 'item')])
        em.addSeparator()
        item(em, 'Remove From Pro&ject')
        item(em, '&Delete From Disk...', None, 'Del')
        item(em, 'Delete Spec&ial...')
        item(em, 'Delete C&ontents...')
        item(em, '&Rename', None, 'F2')
        item(em, 'Edit Re&ference...')
        em.addSeparator()
        item(em, '&Expand All', lambda: self._tree_call(lambda t: t.expandAll()), when='item')
        item(em, 'Co&llapse All', lambda: self._tree_call(lambda t: t.collapseAll()), when='item')
        item(em, 'Select &All', lambda: self._tree_call(lambda t: t.selectAll()), 'Ctrl+A')
        em.addSeparator()
        item(em, '&Hide Hierarchy', self._hide_selected_hierarchy, 'Shift+Space', when='hide')
        item(em, 'Cross-&Highlight')
        em.addSeparator()
        item(em, 'Set Design &Root', lambda: self._with_unit(self.set_design_root), when='unit')
        item(em, '&Toggle Top Marker')
        item(em, 'Set &Gate Level')
        item(em, 'Set Default &View', self._set_selected_default_view, when='view')
        em.addSeparator()
        sub(em, 'Change Language &To', LANGUAGES_CHANGE)
        em.addSeparator()
        sub(em, 'Set La&nguage', LANGUAGES_SET)
        item(em, 'Set as Source File')
        item(em, 'Set as Include File')
        item(em, "Don't Touch Settings...")
        em.addSeparator()
        item(em, '&Check', self.check_selected)
        item(em, 'Edit Black-Box Settings...')
        item(em, 'Pr&operties...', lambda: self._with_unit(lambda du: self._explorer_call(
            lambda ex: ex.unit_properties(du))), when='unit')

        # View
        vm = mb.addMenu('&View')
        item(vm, '&Refresh', self.refresh, 'F5').setIcon(dm_icon('tb_refresh'))
        item(vm, 'Reload &Library', self.reload_all, 'Shift+F5', when='explorer')
        vm.addSeparator()
        item(vm, '&Status Bar', lambda on: self.statusBar().setVisible(on), checkable=True, checked=True)
        self.act_shortcut_bar = item(vm, 'S&hortcut Bar', lambda on: self.shortcut_dock.setVisible(on),
                                     checkable=True, checked=True)
        item(vm, 'Object &Tips', lambda on: setattr(self, 'object_tips', on), checkable=True, checked=True)
        vm.addSeparator()
        cv = vm.addMenu('&Change Explorer View')
        group = QActionGroup(self)
        self.explorer_view_actions = {}
        for text, mode in (('&Design Units', 'units'), ('&Files', 'files')):
            self.explorer_view_actions[mode] = item(cv, text, lambda on, m=mode: on and self._explorer_view(m),
                                                    checkable=True, checked=mode == 'units', when='explorer')
            group.addAction(self.explorer_view_actions[mode])
        group.addAction(item(cv, '&Logical Objects', checkable=True))
        sw = vm.addMenu('Sub &Windows')
        self.act_hier_window = item(sw, '&Design Hierarchy', self._show_hierarchy_window, checkable=True)
        self.act_launch_pad = item(sw, '&Launch Pad', lambda on: self.launch_pad.setVisible(on), checkable=True,
                                   checked=True)
        for text in ('&Side Data/Downstream', '&Tasks and Templates'):
            item(sw, text, lambda checked=False, t=text: self.statusBar().showMessage(
                f'{t.replace("&", "")}: not part of HDL Studio (Verilog/SystemVerilog design management only)', 6000))
        sw.addSeparator()
        item(sw, 'Layout')
        tb = vm.addMenu('T&oolbars')
        item(tb, '&Tooltips', lambda on: setattr(self, 'toolbar_tips', on), checkable=True, checked=True)
        tb.addSeparator()
        for bar in self._build_toolbars():
            a = bar.toggleViewAction(); a.setText(bar.windowTitle()); tb.addAction(a)
        tb.addSeparator()
        item(tb, '&Settings...', self.toolbar_settings)
        vm.addSeparator()
        self.hier_pane_action = item(vm, '&Explore Libraries With Design Hierarchy', self._show_hierarchy_panes,
                                     checkable=True, checked=True)
        vm.addSeparator()
        item(vm, 'Col&umns')
        item(vm, '&Filters')

        # HDL
        hm = mb.addMenu('&HDL')
        sub(hm, '&Convert To Graphics', ['Single Level', 'Hierarchy Through Components'])
        sub(hm, '&Visualize Code As', ['Block Diagram', 'IBD', 'State Diagram', 'Flow Chart'])
        item(hm, '&Update Graphics')
        hm.addSeparator()
        item(hm, 'Generate VHDL Configurations...', lambda: self.statusBar().showMessage(
            'No VHDL configurations: HDL Studio projects are Verilog/SystemVerilog only', 6000))
        hm.addSeparator()
        item(hm, 'View &Generated HDL', self.open_selected_hdl, 'Ctrl+G')

        # Tasks
        tm = mb.addMenu('&Tasks')
        item(tm, 'Tasks and Templates')
        tm.addSeparator()
        item(tm, 'Set &Generate Always')
        item(tm, 'Set &Compile Always')
        item(tm, 'Generate All (One Shot)', self.generate_current_library)
        item(tm, 'Compile All (One Shot)')
        tm.addSeparator()
        for text in ('New Tool...', 'New Flow...', 'Supplied Tasks...'):
            item(tm, text)
        tm.addSeparator()
        gen = sub(tm, 'Generate')
        item(gen, '&Single (selected design units)', self.generate_selected, 'Shift+G')
        item(gen, '&Whole Library', self.generate_current_library)

        # Tools
        tl = mb.addMenu('T&ools')
        item(tl, '&Find')
        item(tl, '&Advanced Find...')
        tl.addSeparator()
        item(tl, '&Viewpoint Manager')
        item(tl, '&Component Browser')
        item(tl, '&DesignPad', self.open_selected_hdl)
        item(tl, 'Registers...')
        tl.addSeparator()
        item(tl, 'Mark Top-Level Design Units...')
        item(tl, 'Update Where Used...')
        sub(tl, 'Reports')
        item(tl, 'Register File Types...')

        # Options
        om = mb.addMenu('O&ptions')
        item(om, '&Main...', self.main_settings)
        item(om, '&VHDL...')
        item(om, 'V&erilog...', self.verilog_options)
        for text in ('Documentation && Visualization...', 'Design Management...', 'Version Management...',
                     'Requirements Referencing...', 'HTML Browser...'):
            item(om, text)
        sub(om, '&Animation')
        om.addSeparator()
        sub(om, 'Master &Preferences')

        # Window
        self.window_menu = mb.addMenu('&Window')
        self.window_menu.aboutToShow.connect(self._fill_window_menu)

        # Help
        hp = mb.addMenu('&Help')
        item(hp, 'Help and &Manuals', None, 'F1')
        item(hp, 'Tcl Command Reference')
        sub(hp, 'Tutorials')
        item(hp, 'Command Line Switches')
        item(hp, '&Keyboard Shortcuts', self._show_shortcuts)
        item(hp, 'Regular Expressions')
        hp.addSeparator()
        item(hp, 'Setup Assistant...')
        hp.addSeparator()
        sub(hp, 'Support')
        for text in ('Release Notes', "What's New"):
            item(hp, text)
        hp.addSeparator()
        item(hp, f'&About {APP_NAME}', lambda: show_about(self))
        self._build_left_bar()
        for m in mb.findChildren(QMenu):
            m.aboutToShow.connect(self._update_menu_states)
        for w in (self.tabs, ):
            w.currentChanged.connect(self._update_menu_states)
        self.libs.itemSelectionChanged.connect(self._update_menu_states)
        self._update_menu_states()

    def _build_toolbars(self) -> list[QToolBar]:
        """Standard, Design Manager, HDL and Tasks toolbars, as in the legacy tool (gui/dm_toolbar.py)."""
        gen = QMenu(self)
        gen.addAction('&Single (selected design units)', self.generate_selected)
        gen.addAction('&Whole Library', self.generate_current_library)
        self.toolbars = DmToolbars(self, {'new': self.new_menu, 'generate': gen})
        return self.toolbars.bars

    # -- toolbar actions: they act on the current selection (selection_kind) ------------------
    def selection_kind(self) -> str:
        """What is selected, for the toolbar (dm_toolbar.py): none / lib on the Project page;
        explorer / unit / file / hier in a library tab (the pane with the focus first)."""
        ex = self._explorer()
        if ex is None:
            it = self.libs.currentItem()
            ok = it is not None and it.isSelected() and isinstance(it.data(0, Qt.UserRole), Library)
            return 'lib' if ok else 'none'
        for t in sorted((ex.units, ex.files, ex.hier), key=lambda t: not t.hasFocus()):
            for it in t.selectedItems():
                d = it.data(0, Qt.UserRole)
                if not d:
                    continue
                if t is ex.hier:
                    return 'hier'
                if d[0] in ('unit', 'view'):
                    return 'unit'
                if d[0] == 'file':
                    return 'file'
        return 'explorer'

    def _selected_row(self):
        """(tree, data) of the first selected row of the library tab shown (pane with focus first)."""
        ex = self._explorer()
        if ex is None:
            return None, None
        for t in sorted((ex.units, ex.files, ex.hier), key=lambda t: not t.hasFocus()):
            for it in t.selectedItems():
                if it.data(0, Qt.UserRole):
                    return t, it.data(0, Qt.UserRole)
        return None, None

    def open_selected(self):
        """Open: the selected unit (default view), view, file or hierarchy row."""
        _, d = self._selected_row()
        if not d:
            return
        if d[0] == 'view':
            self.open_view(d[1], d[2])
        elif d[0] == 'file':
            self.open_file(d[1], self._explorer().lib)
        elif d[0] in ('unit', 'root', 'frame') and d[1] is not None:
            self.open_unit(d[1])

    def selected_properties(self):
        """Object Properties of the selected design unit."""
        ex = self._explorer()
        units = ex.selected_units() if ex else []
        if units:
            ex.unit_properties(units[0])

    def toggle_selected_hierarchy(self):
        """Toggle Hierarchy: show the hierarchy of the selected unit (of the units of the selected
        file), or hide it when it is shown already."""
        ex = self._explorer()
        t, d = self._selected_row()
        if ex is None or not d:
            return
        units = [d[1]] if d[0] in ('unit', 'view') else ex.units_in_file(d[1]) if d[0] == 'file' else []
        if not units or units[0] is None:
            return
        du = units[0]
        for i in range(ex.hier.topLevelItemCount()):
            top = ex.hier.topLevelItem(i)
            r = top.data(0, Qt.UserRole)
            if r and r[1] is du and not r[2]:
                ex.hide_hierarchy(top)
                return
        ex.show_hierarchy(du)

    def explore_selected(self):
        """Explore Library: open the tab of the library selected on the Project page."""
        self.explore(self._selected_lib())

    def toggle_explorer_view(self):
        """Change Explorer View: switch the library tabs between Design Units and Files."""
        self._explorer_view('files' if getattr(self, 'explorer_view', 'units') == 'units' else 'units')

    def toolbar_settings(self):
        """View > Toolbars > Settings...: choose which toolbars are shown."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self); dlg.setWindowTitle('Toolbar Settings')
        lay = QVBoxLayout(dlg)
        boxes = []
        for bar in self.findChildren(QToolBar):
            c = QCheckBox(bar.windowTitle()); c.setChecked(bar.isVisible()); lay.addWidget(c)
            boxes.append((bar, c))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); lay.addWidget(bb)
        if dlg.exec():
            for bar, c in boxes:
                bar.setVisible(c.isChecked())

    # -- menu helpers --------------------------------------------------------------------
    def _menu_state(self) -> dict[str, bool]:
        """What the current selection allows, for the `when` of the menu entries."""
        ex = self._explorer()
        units = ex.selected_units() if ex else []
        cur = ex.units.currentItem() if ex else None
        d = cur.data(0, Qt.UserRole) if cur is not None and cur.isSelected() else None
        top = ex.hier.currentItem() if ex else None
        while top is not None and top.parent() is not None:
            top = top.parent()
        root = top.data(0, Qt.UserRole) if top is not None else None
        lib_item = self.libs.currentItem() if ex is None else None
        lib_selected = lib_item is not None and lib_item.isSelected() and isinstance(lib_item.data(0, Qt.UserRole), Library)
        return {'project': self.project is not None,
                'explorer': ex is not None,
                'lib': ex is not None or lib_selected,
                'unit': bool(units),
                'item': bool(units) or lib_selected or bool(ex and ex.hier.selectedItems()),
                'view': bool(d and d[0] == 'view' and d[2].kind != 'symbol'),
                'hide': bool(root and root[0] == 'root' and not root[2])}

    def _update_menu_states(self, *args):
        """Enable the menu entries that need a selection / a project (when a menu opens)."""
        state = self._menu_state()
        for a, when in self._when:
            a.setEnabled(state.get(when, False))
        if getattr(self, 'toolbars', None) is not None:
            self.toolbars.update(self.selection_kind())

    def _explorer(self) -> 'LibraryExplorer | None':
        """The LibraryExplorer of the tab shown, or None on the Project page."""
        w = self.tabs.currentWidget()
        return w if isinstance(w, LibraryExplorer) else None

    def _explorer_call(self, fn):
        """Call fn(explorer) on the library tab shown (a message when the Project page is shown)."""
        ex = self._explorer()
        if ex is None:
            self.statusBar().showMessage('Open a library first (Explore Library)', 4000)
            return
        fn(ex)

    def _tree_call(self, fn):
        """Run fn on the tree that has the focus: a pane of the library explorer, or the project tree."""
        ex = self._explorer()
        if ex is None:
            fn(self.libs)
            return
        focus = QApplication.focusWidget()
        tree = next((t for t in (ex.units, ex.files, ex.hier) if focus is t or (focus and t.isAncestorOf(focus))),
                    ex.units)
        fn(tree)

    def _with_unit(self, fn):
        """Call fn(unit) with the first selected design unit (a message when none is selected)."""
        ex = self._explorer()
        units = ex.selected_units() if ex else []
        if not units:
            self.statusBar().showMessage('Select a design unit first', 4000)
            return
        fn(units[0])

    def _selected_paths(self) -> list[str]:
        """Files of the selection: views/units of the explorer, or library folders."""
        ex = self._explorer()
        out = []
        if ex is None:
            it = self.libs.currentItem()
            lib = it.data(0, Qt.UserRole) if it is not None and it.isSelected() else None
            if isinstance(lib, Library):
                out.append(lib.main_hdl_dir)
            return out
        for it in ex.units.selectedItems() + ex.files.selectedItems():
            d = it.data(0, Qt.UserRole)
            if not d:
                continue
            if d[0] == 'view':
                out.append(d[2].path)
            elif d[0] == 'unit' and d[1] is not None and d[1].default_view() is not None:
                out.append(d[1].default_view().path)
            elif d[0] == 'file':
                out.append(d[1])
        return out

    def _copy_path(self, what: str):
        """Hard path: the absolute file path. Soft path: relative to the project folder,
        through $HDS_PROJECT_DIR."""
        paths = self._selected_paths()
        if not paths:
            self.statusBar().showMessage('Select a design unit, view or library first', 4000)
            return
        if what == 'soft' and self.project is not None:
            pd = os.path.normcase(os.path.abspath(self.project.dir))
            paths = [f'${PROJECT_DIR_VAR}/' + os.path.relpath(p, self.project.dir).replace(os.sep, '/')
                     if os.path.normcase(os.path.abspath(p)).startswith(pd) else p for p in paths]
        text = '\n'.join(paths)
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(f'Copied {text}', 4000)

    def copy_selection(self):
        """Edit > Copy: names of the selected rows."""
        ex = self._explorer()
        trees = [self.libs] if ex is None else [ex.units, ex.files, ex.hier]
        names = [it.text(0) for t in trees for it in t.selectedItems()]
        if names:
            QApplication.clipboard().setText('\n'.join(names))
            self.statusBar().showMessage(f'Copied {len(names)} name(s)', 4000)

    def _set_selected_default_view(self):
        """Edit > Set Default View for the selected unit."""
        ex = self._explorer()
        it = ex.units.currentItem() if ex else None
        d = it.data(0, Qt.UserRole) if it is not None else None
        if d and d[0] == 'view':
            ex.set_default_view(d[1], d[2])

    def _explorer_view(self, mode: str):
        """View > Change Explorer View: Design Units (units and files panes) or Files only."""
        self.explorer_view = mode
        a = getattr(self, 'explorer_view_actions', {}).get(mode)
        if a is not None and not a.isChecked():
            a.setChecked(True)
        for ex in self.explorers.values():
            ex.units.setVisible(mode == 'units')

    def _hide_selected_hierarchy(self):
        """Hide Hierarchy for the selected hierarchy root."""
        ex = self._explorer()
        it = ex.hier.currentItem() if ex else None
        while it is not None and it.parent() is not None:
            it = it.parent()
        if it is not None:
            ex.hide_hierarchy(it)

    def _show_hierarchy_window(self, on: bool):
        """View > Sub Windows > Design Hierarchy: the hierarchy below the design root."""
        dock = getattr(self, 'hier_dock', None)
        if dock is None:
            dock = self.hier_dock = QDockWidget('Design Hierarchy', self)
            dock.setObjectName('design_hierarchy')
            dock.setWidget(HierarchyWindow(self))
            dock.visibilityChanged.connect(lambda v: self.act_hier_window.setChecked(v))
            self.addDockWidget(Qt.RightDockWidgetArea, dock)
        if on:
            dock.widget().fill()
        dock.setVisible(on)

    def close_explorers(self):
        """Close every library tab."""
        while self.tabs.count() > 1:
            self._close_tab(1)

    def close_editors(self):
        """Close every editor window (each asks about unsaved changes)."""
        for w in list(self.editors.values()):
            w.close()

    def page_setup(self, parent=None):
        """File > Page Setup... (`parent`: the window it is asked from, a diagram editor or this one;
        the dialog opens over it, so that window stays in front)."""
        from .dm_options import PageSetupDialog
        dlg = PageSetupDialog(self.prefs, parent or self)
        if dlg.exec():
            self.log('Page setup saved to ' + self.prefs.path())

    def new_registered_view(self, kind: str, ext: str):
        """File > New > Registered View: an empty file of that type in a library, opened as text."""
        lib = self._selected_lib() or (self.project.library(self.project.default_library) if self.project else None)
        if lib is None:
            self.statusBar().showMessage('Select a library first', 4000)
            return
        path, _ = QFileDialog.getSaveFileName(self, f'New {kind}', os.path.join(lib.main_hdl_dir, f'untitled.{ext}'),
                                              f'{kind} (*.{ext});;All files (*)')
        if not path:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            open(path, 'w', encoding='utf-8').close()
        self.log(f'Created {path}', path=path)
        self.open_text_file(path)

    def add_existing_files(self):
        """File > Add > Existing Files: copy HDL files into the library's HDL folder."""
        import shutil
        lib = self._selected_lib()
        if lib is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, f'Add files to {lib.name}', '',
                                                'HDL (*.v *.sv *.vh *.svh *.vlg *.verilog *.vo);;All files (*)')
        if not paths:
            return
        os.makedirs(lib.main_hdl_dir, exist_ok=True)
        for p in paths:
            dest = os.path.join(lib.main_hdl_dir, os.path.basename(p))
            if os.path.exists(dest):
                self.log(f'{dest} exists: not overwritten', 'warning')
                continue
            shutil.copy2(p, dest)
            self.log(f'Added {dest}', path=dest)
        if lib.name in self.explorers:
            self.explorers[lib.name].refresh()
        else:
            self.explore(lib)

    def set_hierarchy_panes(self, on: bool):
        """Show / hide the Design Hierarchy panes and tick View > Explore Libraries With Design Hierarchy."""
        self.hier_pane_action.setChecked(on)        # its toggled signal calls _show_hierarchy_panes
        self._show_hierarchy_panes(on)

    def _show_hierarchy_panes(self, on: bool):
        """Show / hide the Design Hierarchy pane of every library tab."""
        self.show_hierarchy_pane = on
        for ex in self.explorers.values():
            ex.hier.setVisible(on)

    def _fill_window_menu(self):
        """Window menu: the open editor windows (a click raises one)."""
        m = self.window_menu
        m.clear()
        log = next((d for d in self.findChildren(QDockWidget) if d.objectName() == 'log'), None)
        m.addAction('&Log Window', lambda: (log.show(), log.raise_()) if log else None)
        m.addAction('&Task Log Window').setEnabled(False)
        m.addAction('Layout').setEnabled(False)
        m.addSeparator()
        wins = [self] + [w for w in self.editors.values() if w.isVisible()]
        for k, w in enumerate(wins, 1):
            m.addAction(f'&{k} - {w.windowTitle()}', lambda w=w: (w.show(), w.raise_(), w.activateWindow()))

    def _show_shortcuts(self, parent=None):
        """Help > Keyboard Shortcuts: the shortcuts of both editors (gui/shortcuts_dialog.py)."""
        from .shortcuts_dialog import show_shortcuts
        show_shortcuts(parent or self)

    def main_settings(self, parent=None):
        """Options > Main...; applies the recovery-file settings when something was saved. The dialog
        opens over `parent` (the diagram it is asked from), else over the Design Manager."""
        from .main_settings import MainSettingsDialog
        dlg = MainSettingsDialog(self.prefs, parent or self)
        dlg.exec()
        if dlg.applied:
            self._apply_save_settings()
            self.log('Main settings saved to ' + self.prefs.path())

    def _apply_save_settings(self):
        """Recovery files every N minutes (Main Settings > Save)."""
        self._autosave_timer.setInterval(max(1, self.prefs.autosave_minutes) * 60000)
        if self.prefs.autosave_enabled:
            self._autosave_timer.start()
        else:
            self._autosave_timer.stop()

    def _build_left_bar(self):
        """Left bar as in the legacy Design Manager: the Project page of project commands while the
        Project tab is current, the Main page of large launcher buttons with a library tab."""
        stack = QStackedWidget()

        def page(buttons, stretch: bool = False) -> QWidget:
            """A page of the left bar (a column of launcher buttons): centred, or as wide as the
            bar when `stretch`.
            """
            w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(6)
            for b in buttons:
                if stretch:
                    lay.addWidget(b)
                else:
                    lay.addWidget(b, 0, Qt.AlignHCenter)
            lay.addStretch(1)
            return w

        def launcher(icon_name: str, text: str, slot=None, menu: QMenu | None = None, tip: str = ''):
            """One launcher button (icon and text) on a left bar page."""
            b = QToolButton()
            b.setIcon(dm_icon(icon_name)); b.setIconSize(QSize(40, 40))
            b.setText(text); b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setFixedWidth(84); b.setMinimumHeight(70)
            b.setAutoRaise(False)
            if menu is not None:
                b.setMenu(menu); b.setPopupMode(QToolButton.InstantPopup)
            elif slot is not None:
                b.clicked.connect(slot)
            else:
                # shown as in the legacy tool, but these flows are not part of HDL Studio
                tip = tip or f'{text.replace(chr(10), " ").replace("&&", "&")}: not part of HDL Studio '                     '(design management, generation and maintenance only)'
                b.clicked.connect(lambda checked=False, t=tip: self.statusBar().showMessage(t, 6000))
            b.setToolTip(tip)
            return b

        new_menu = QMenu(self)
        new_menu.addAction(dm_icon('unit_component'), 'New Design Content...', self.new_unit)
        new_menu.addAction(dm_icon('library'), 'New Library...', self.new_library)
        new_menu.addAction('New Project...', self.new_project)
        new_menu.addSeparator()
        new_menu.addAction(dm_icon('file_hdl'), 'Open HDL File...', self.open_any_file)
        main = self.launch_pad_page = page([
            launcher('launch_new', 'New / Add', menu=new_menu, tip='Create a design unit, library or project'),
            launcher('launch_check', 'Check', self.check_selected,
                     tip='Syntax check of the selected design units (generated HDL for graphical views)'),
            launcher('launch_simulate', 'Simulate'),
            launcher('launch_synthesize', 'Synthesize'),
            launcher('launch_document', 'Document &&\nVisualize'),
            launcher('launch_registers', 'Registers'),
        ])

        def project_button(icon_name: str, text: str, slot=None):
            """A button of the project page of the left bar."""
            b = WrapToolButton(text); b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setIcon(project_icon(icon_name)); b.setIconSize(QSize(24, 24))
            b.setAutoRaise(True); b.setMinimumWidth(120)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)     # follows the bar width
            if slot is None:
                b.setEnabled(False); b.setToolTip('Not available in HDL Studio yet')
            else:
                b.clicked.connect(slot)
            return b
        project = page([
            project_button('new_project', 'New Project...', self.new_project),
            project_button('open_project', 'Open Project...', self.open_project_dialog),
            project_button('new_library', 'New Library...', self.new_library),
            project_button('edit_mappings', 'Edit Mappings...'),
            project_button('set_default', 'Set As Default', self._set_default_library),
            project_button('explore_library', 'Explore Library', lambda: self.explore(self._selected_lib())),
            project_button('new_add', 'New / Add...', self.new_unit),
            project_button('version', 'Version Management...'),
            project_button('close_project', 'Close Project', self.close_project),
        ], stretch=True)
        project.setObjectName('project_page_bar')
        project.setStyleSheet('#project_page_bar { background:#707070; } '
                              'QToolButton { color:white; text-align:left; } '
                              'QToolButton:disabled { color:#b8b8b8; } '
                              'QToolButton:hover { background:#858585; }')
        self.launch_pad = main
        for w in (main, project):                   # Main goes with a library tab, Project with the Project tab
            stack.addWidget(w)

        box = QWidget(); bl = QVBoxLayout(box); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(0)
        self.left_title = QLabel('Main'); self.left_title.setAlignment(Qt.AlignCenter)
        self.left_title.setStyleSheet('background:#c8c8c8; padding:3px; border-bottom:1px solid #999;')
        bl.addWidget(self.left_title)
        bl.addWidget(stack, 1)
        self.left_pages = stack
        self.tabs.currentChanged.connect(self._left_page_for_tab)
        dock = QDockWidget('Shortcuts', self)
        self.shortcut_dock = dock
        dock.setObjectName('shortcuts')
        dock.setTitleBarWidget(QWidget())         # no title bar, like the legacy side bar
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setWidget(box)
        box.setMinimumWidth(128)                  # drag the edge of the bar to widen it
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.resizeDocks([dock], [128], Qt.Horizontal)     # opens narrow, as before
        self._left_page_for_tab(self.tabs.currentIndex())

    def _left_page_for_tab(self, index: int):
        """The Project page goes with the Project tab, the Main page with a library tab."""
        on_project = self.tabs.widget(index) is self.project_page
        self.left_pages.setCurrentIndex(1 if on_project else 0)
        self.left_title.setText('Project' if on_project else 'Main')

    def _set_default_library(self):
        """Make the selected library the project's default library (written to the .hdp)."""
        lib = self._selected_lib()
        if self.project is None or lib is None:
            self.statusBar().showMessage('Select a library first', 4000)
            return
        self.project.set_default_library(lib.name)
        self.log(f'Default library set to {lib.name}')
        self.fill_project()

    def set_design_root(self, du: DesignUnit):
        """Set Design Root: write the unit as design_root to the .hdp and redraw the panes."""
        if self.project is None:
            return
        old = self.project.design_root
        self.project.set_design_root(du)
        self.log(f'Design root set to {self.project.design_root}' + (f' (was {old})' if old else '')
                 + f'; saved in {self.project.path}')
        self.fill_project()

    def check_selected(self):
        """Check the units selected in the library tab (see check_units)."""
        w = self.tabs.currentWidget()
        units = w.selected_units() if isinstance(w, LibraryExplorer) else []
        if not units:
            self.log('Select design units to check', 'warning')
            return
        self.check_units(units)

    def check_units(self, units: list[DesignUnit]):
        """Syntax check of design units: their HDL files, or the HDL generated from
        their graphical view."""
        from hdl.parser import check_text
        from project.generate import generate_text
        total = 0
        for du in units:
            try:
                g = du.default_view() if du.default_view() and du.default_view().kind in ('fsm', 'bd') \
                    else du.graphic_view()
                if g is not None:
                    text, warnings = generate_text(load_view(du.library, du, g))
                    name = du.name + ('.sv' if du.language == 'systemverilog' else '.v')
                    diags = [(0, 'warning', w_) for w_ in warnings]
                elif du.text_view() is not None:
                    with open(du.text_view().path, encoding='utf-8', errors='replace') as f:
                        text = f.read()
                    name, diags = du.text_view().path, []
                else:
                    self.log(f'{du.name}: nothing to check', 'warning')
                    continue
                diags += check_text(text, name, du.library.include_dirs)
            except Exception as e:
                self.log(f'{du.name}: check failed: {e}', 'error')
                continue
            errors = [d for d in diags if d[1] == 'error']
            total += len(errors)
            for line, sev, msg in diags[:20]:
                self.log(f'{du.name}: {sev} line {line}: {msg}' if line else f'{du.name}: {sev}: {msg}',
                         'error' if sev == 'error' else 'warning')
            self.log(f'{du.name}: check {"passed" if not errors else "found " + str(len(errors)) + " error(s)"}'
                     f' ({len(diags) - len(errors)} warning(s))')
        self.log(f'Check finished: {len(units)} unit(s), {total} error(s)')

    def _fill_recent(self):
        """File > Recent Projects."""
        self.recent_menu.clear()
        for p in self.prefs.recent_projects:
            a = self.recent_menu.addAction(p)
            a.triggered.connect(lambda checked=False, p=p: self.load_project(p))
        if not self.prefs.recent_projects:
            self.recent_menu.addAction('(none)').setEnabled(False)

    # -- logging --------------------------------------------------------------------------
    def log(self, msg: str, level: str = 'info', path: str = ''):
        """Add a time-stamped line to the Log; `level` 'warning' / 'error' colours it, `path` is a
        file a double-click on the line opens.
        """
        it = QListWidgetItem(f'{datetime.now().strftime("%H:%M:%S")}  {msg}')
        if level == 'error':
            it.setForeground(QColor(200, 0, 0))
        elif level == 'warning':
            it.setForeground(QColor(160, 100, 0))
        if path:
            it.setData(Qt.UserRole, path)
        self.log_list.addItem(it)
        self.log_list.scrollToBottom()

    def _log_open(self, item):
        """Double-click on a Log line: open the file it refers to."""
        p = item.data(Qt.UserRole)
        if p:
            self.open_file(p, None)

    # -- project ---------------------------------------------------------------------------
    def update_title(self):
        """Window title: the project name and file."""
        self.setWindowTitle(f'Design Manager - Project {self.project.name}' if self.project
                            else 'Design Manager - no project')

    def load_project(self, path: str):
        """Open a .hdp project (closing the current one first): read it with the saved HDL parse
        cache, log its problems, fill the Project page and add it to Recent Projects.
        """
        if not self.close_project():
            return
        self.progress.begin(f'Opening project {os.path.basename(path)}...')
        try:
            try:
                self.project = open_project(path)
            except Exception as e:
                QMessageBox.critical(self, 'Open project', f'Cannot open {path}:\n{e}')
                return
            self.project.progress = self.progress.scan_library
            self.project.cache.update(self._load_hdl_cache())
            self.prefs.add_recent(path)
            self.log(f'Opened project {path} ({len(self.project.libraries)} libraries)')
            for err in self.project.errors:
                self.log(err, 'warning')
            self.fill_project()
            if self.project.default_library and self.project.library(self.project.default_library):
                self.explore(self.project.library(self.project.default_library))
        finally:
            self.progress.end()

    def close_project(self) -> bool:
        """File > Close Project: close the editors (asking for unsaved work), the library tabs, and
        save the HDL parse cache. False when an editor refused to close.
        """
        for w in list(self.editors.values()):
            text = getattr(w, 'editor', None)
            if getattr(w, 'dirty', False) or (hasattr(text, 'document') and text.document().isModified()):
                # the editor asks Save / Discard / Cancel: bring it to the front first, so that its
                # question is not hidden behind the Design Manager (as the legacy tool shows each
                # modified diagram with its question)
                if w.isMinimized():
                    w.showNormal()
                w.show(); w.raise_(); w.activateWindow()
                QApplication.processEvents()
            if not w.close():
                return False
        while self.tabs.count() > 1:
            self.tabs.removeTab(1)
        self.explorers.clear()
        if self.project is not None:
            self._save_hdl_cache()
        self.project = None
        self.fill_project()
        return True

    # parsed HDL files of the project, kept between sessions: a file is parsed again when its time changes
    @staticmethod
    def _hdl_cache_path() -> str:
        """File of the HDL parse cache (pickle, in the config folder)."""
        return os.path.join(os.path.dirname(Prefs.path()), 'hdl_cache.pickle')

    def _load_hdl_cache(self) -> dict:
        """The HDL parse cache of an earlier run ({} when missing or written by another version)."""
        import pickle
        try:
            with open(self._hdl_cache_path(), 'rb') as f:
                data = pickle.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:                           # missing, or written by another version
            return {}

    def _save_hdl_cache(self):
        """Write the HDL parse cache of the project (atomically; errors ignored: it is only a cache)."""
        import pickle
        try:
            tmp = self._hdl_cache_path() + '.tmp'
            with open(tmp, 'wb') as f:
                pickle.dump(self.project.cache, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, self._hdl_cache_path())
        except Exception:
            pass                                    # only a cache

    def fill_project(self):
        """Project page: the libraries of the project (regular / protected groups, errors in red)."""
        self.update_title()
        self.libs.blockSignals(True)
        self.libs.clear()
        self.project_info.clear()
        p = self.project
        if p is None:
            self.project_info.addTopLevelItem(QTreeWidgetItem(['No project open: File > Open > Project... '
                                                               'or File > New > Project...']))
            self.libs.blockSignals(False)
            return
        mine = QTreeWidgetItem([f'My Project:   {p.path}'])
        mine.setData(0, Qt.UserRole, 'project')
        mine.setCheckState(0, Qt.Checked)
        for text in ('Verilog Library Search Path:  <None>', 'Verilog Implicit Include Libraries:  <None>'):
            mine.addChild(QTreeWidgetItem([text]))
        self.project_info.addTopLevelItem(mine)
        mine.setExpanded(True)
        shared = QTreeWidgetItem([f'Shared Project: {p.shared_path or "<None>"}'])
        shared.setData(0, Qt.UserRole, 'shared')
        shared.setCheckState(0, Qt.Checked if p.shared_path else Qt.Unchecked)
        self.project_info.addTopLevelItem(shared)
        root = p.design_root_unit()
        root_lib = root.library if root is not None else None
        for title, key in (('Regular Libraries', 'regular'), ('Protected Libraries', 'protected'),
                           ('Downstream Only Libraries', 'downstream')):
            libs = sorted((l for l in p.libraries if l.type == key), key=lambda l: l.name.lower(),
                          reverse=self.lib_sort_desc)
            g = QTreeWidgetItem([f'{title} [ {len(libs)} items ]' if libs else f'{title} [ Empty ]'])
            g.setData(0, Qt.UserRole, key)
            shown = key == 'regular' or (key == 'protected' and self.show_protected.isChecked())
            if libs:
                g.setCheckState(0, Qt.Checked if shown else Qt.Unchecked)
            self.libs.addTopLevelItem(g)
            for lib in libs:
                text = lib.name + ('  <active>' if lib.name == p.default_library else '')
                it = QTreeWidgetItem([text])
                it.setData(0, Qt.UserRole, lib)
                it.setIcon(0, library_icon(key == 'protected', lib.origin == 'shared', lib is root_lib))
                tip = [f'Library {lib.name} ({lib.type})', 'HDL: ' + '; '.join(lib.hdl_dirs),
                       'Graphics: ' + (lib.meta_dir or '-')]
                if lib is root_lib:
                    it.setForeground(0, QBrush(ROOT_TEXT))
                    tip.insert(1, f'Holds the design root {p.design_root}')
                if lib.errors:
                    it.setForeground(0, RED)
                    tip += lib.errors
                it.setToolTip(0, '\n'.join(tip))
                for d in lib.hdl_dirs:
                    it.addChild(QTreeWidgetItem([f'HDL: {d}']))
                if lib.meta_dir:
                    it.addChild(QTreeWidgetItem([f'Graphics: {lib.meta_dir}']))
                g.addChild(it)
            g.setExpanded(shown)
        self.libs.blockSignals(False)

    def _lib_group_checked(self, item: QTreeWidgetItem, col: int):
        """The check box of a library group shows or hides its libraries."""
        on = item.checkState(0) == Qt.Checked
        if item.data(0, Qt.UserRole) == 'protected':
            self.show_protected.blockSignals(True); self.show_protected.setChecked(on)
            self.show_protected.blockSignals(False)
        item.setExpanded(on)

    def _selected_lib(self) -> Library | None:
        """The library selected on the Project page (or of the current tab)."""
        w = self.tabs.currentWidget()
        if isinstance(w, LibraryExplorer):
            return w.lib
        it = self.libs.currentItem()
        return it.data(0, Qt.UserRole) if it else None

    def _page_menu(self, tree: QTreeWidget, pos):
        """Right-click on the Project page: the menu of the row (My Project, Shared Project, a
        library group, a library) or of the empty space (gui/explorer_menus.py). A row counts only
        on its icon / text; the rest of the project rows has no menu."""
        it = M.text_item(tree, pos)
        d = it.data(0, Qt.UserRole) if it is not None else None
        if it is None:
            if tree is not self.libs:
                return
            entries = M.page_blank_menu(self)
        elif isinstance(d, Library):
            entries = M.library_menu(self, d)
        elif d == 'project':
            entries = M.project_menu(self)
        elif d == 'shared':
            entries = M.shared_menu(self)
        elif d in ('regular', 'protected', 'downstream'):
            entries = M.group_menu(self, d)
        else:
            return                                  # search path rows, HDL / graphics folder rows
        M.popup(entries, self, tree.viewport().mapToGlobal(pos))

    def refresh_project(self):
        """Refresh (F5) on the Project page: rescan the open libraries and redraw the page."""
        self.refresh()
        self.fill_project()

    def refresh_library(self, lib: Library):
        """Refresh Library: read the library again (its tab too when it is open)."""
        if self.project is None:
            return
        if lib.name in self.explorers:
            self.explorers[lib.name].refresh()
        else:
            lib.scan(self.project.cache, self.project.progress)
        self.fill_project()
        self.log(f'Library {lib.name} refreshed: {len(lib.units)} design units, {len(lib.files)} HDL files')

    def refresh_libraries(self, kind: str):
        """Refresh Libraries on a group row: refresh every library of that group."""
        for lib in [l for l in self.project.libraries if l.type == kind] if self.project else []:
            self.refresh_library(lib)

    def sort_libraries(self, descending: bool):
        """Sort > Ascending / Descending of the library groups."""
        self.lib_sort_desc = descending
        self.fill_project()

    def set_default_library(self, lib: Library):
        """Set as Default Library (written to the .hdp)."""
        self.project.set_default_library(lib.name)
        self.fill_project()
        self.log(f'Default library is now {lib.name}; saved in {self.project.path}')

    def change_library_type(self, lib: Library, lib_type: str):
        """Change Library Type To > Regular / Protected / Downstream Only (written to the .hdp)."""
        old = lib.type
        self.project.set_library_type(lib, lib_type)
        if lib.name in self.explorers:
            self.explorers[lib.name].refresh()
        self.fill_project()
        self.log(f'Library {lib.name}: type {old} -> {lib_type}; saved in {self.project.path}')

    def unset_design_root(self):
        """Unset Design Root: the project has no design root any more (written to the .hdp)."""
        if self.project is None:
            return
        old = self.project.design_root
        self.project.unset_design_root()
        self.log(f'Design root {old} unset; saved in {self.project.path}')
        self.fill_project()
        for ex in self.explorers.values():
            ex._fill_units()
            ex._fill_hierarchy()

    def close_explorer(self, ex: 'LibraryExplorer'):
        """Close the library tab `ex` (Close Library / Close Current Design Explorer)."""
        i = self.tabs.indexOf(ex)
        if i > 0:
            self._close_tab(i)

    def explore(self, lib: Library | None):
        """Open (or show) the tab of library `lib`."""
        if not isinstance(lib, Library):
            return
        if lib.name in self.explorers:
            self.tabs.setCurrentWidget(self.explorers[lib.name])
            return
        ex = LibraryExplorer(self, lib)
        ex.hier.setVisible(getattr(self, 'show_hierarchy_pane', True))
        ex.units.setVisible(getattr(self, 'explorer_view', 'units') == 'units')
        for t in (ex.units, ex.files, ex.hier):
            t.itemSelectionChanged.connect(self._update_menu_states)
        self.explorers[lib.name] = ex
        self.tabs.addTab(ex, lib.name)
        self.tabs.setCurrentWidget(ex)
        self.session_changed()
        n = len(lib.units)
        self.log(f'Library {lib.name}: {n} design units, {len(lib.files)} HDL files'
                 + (f', {lib.unparsed_count()} not parsed' if lib.unparsed_count() else ''))

    def _close_tab(self, i: int):
        """Close library tab `index` (the Project page cannot be closed)."""
        w = self.tabs.widget(i)
        if isinstance(w, LibraryExplorer):
            self.explorers.pop(w.lib.name, None)
            self.tabs.removeTab(i)
            self.session_changed()

    def reload_all(self):
        """Forget every cached parse result, then refresh."""
        if self.project is not None:
            self.project.cache.clear()
        self.refresh()

    def open_selected_hdl(self):
        """Ctrl+G: open the HDL text of the selected design unit (generated or source)."""
        w = self.tabs.currentWidget()
        units = w.selected_units() if isinstance(w, LibraryExplorer) else []
        if not units:
            self.log('Select a design unit first', 'warning')
            return
        du = units[0]
        if du.text_view() is not None:
            self.open_file(du.text_view().path, du.library)
        else:
            self.log(f'{du.name}: no HDL file yet; generate it first (Shift+G)', 'warning')

    def refresh(self):
        """View > Refresh: rescan the library shown."""
        self.view_cache.clear()
        self._hier_disk.clear()
        if self.project is not None:
            self.project.cache.clear()              # View > Refresh reads everything again from disk
        for ex in self.explorers.values():
            ex.refresh()
        self.log('Refreshed')

    # -- hierarchy ------------------------------------------------------------------------
    @staticmethod
    def _hier_cache_path() -> str:
        """File of the instance cache of the diagrams (used by the hierarchy panes)."""
        # the name changes when what is cached changes (v2: ModuleWare gates left out)
        return os.path.join(os.path.dirname(Prefs.path()), 'hier_cache_v2.json')

    def _load_hier_cache(self):
        """Instances of the block diagrams read before: path -> [mtime, children]."""
        try:
            with open(self._hier_cache_path(), encoding='utf-8') as f:
                self._hier_disk: dict[str, list] = json.load(f)
        except (OSError, ValueError):
            self._hier_disk = {}

    def _save_hier_cache(self):
        """Write the instance cache of the diagrams."""
        try:
            os.makedirs(os.path.dirname(self._hier_cache_path()), exist_ok=True)
            with open(self._hier_cache_path(), 'w', encoding='utf-8') as f:
                json.dump(self._hier_disk, f)
        except OSError:
            pass                                    # only a cache

    def may_have_children(self, du: DesignUnit) -> bool:
        """Whether a hierarchy row gets an expand mark, without reading a block diagram not read yet."""
        g = du.graphic_view()
        if g is not None and g.kind == 'bd':
            key = (g.path, g.mtime)
            if key in self.view_cache:
                return bool(self.view_cache[key])
            saved = self._hier_disk.get(g.path)
            return bool(saved[1]) if saved and saved[0] == g.mtime else True
        return bool(self.children_of(du))

    def children_of(self, du: DesignUnit) -> list[tuple[str, str, str, list[str]]]:
        """(instance, unit, library or '', generate path) below a design unit."""
        g = du.graphic_view()
        if g is not None and g.kind == 'bd':
            key = (g.path, g.mtime)
            if key not in self.view_cache:
                saved = self._hier_disk.get(g.path)
                if saved and saved[0] == g.mtime:       # read in an earlier session, file unchanged
                    self.view_cache[key] = [tuple(c) for c in saved[1]]
                    return self.view_cache[key]
                try:
                    bd = load_view(du.library, du, g)
                    # generate frames around an instance give its place in the hierarchy (FOR : name)
                    self.view_cache[key] = [(i.name, i.unit, i.library,
                                             [f.label for f in bd.frame_path(i.x + i.w / 2, i.y + i.h / 2)])
                                            for i in bd.instances if i.library != 'moduleware']   # gates, not units
                    self._hier_disk[g.path] = [g.mtime, self.view_cache[key]]
                    self._save_hier_cache()
                except Exception as e:
                    self.view_cache[key] = []
                    self.log(f'{du.name}: cannot read {os.path.basename(g.path)}: {e}', 'error')
            return self.view_cache[key]
        if du.hdl is not None:
            return [(i.name, i.module, '', i.generate) for i in du.hdl.instances]
        return []

    # -- opening ----------------------------------------------------------------------------
    def open_unit(self, du: DesignUnit):
        """Open the default view of a design unit."""
        v = du.default_view()
        if v is None:
            self.log(f'{du.name}: no view to open', 'warning')
            return
        self.open_view(du, v)

    def open_unit_by_name(self, unit: str, library: str = ''):
        """Open unit `unit` (searched in `library` first) - used by Open Down in the editors; a Log
        warning when it is not found.
        """
        if self.project is None:
            return
        lib = self.project.library(library) if library else None
        du = self.project.find_unit(unit, prefer=lib)
        if du is None:
            self.log(f'Design unit {library + "." if library else ""}{unit} not found', 'warning')
            return
        self.open_unit(du)

    def open_view(self, du: DesignUnit, view: View):
        """Open `view` of `du` in its editor: state diagram, block diagram or text. An editor already
        open is raised instead. Steps: read the view, lock it (EditorContext.acquire: may end
        read-only or be cancelled), offer the unsaved changes of an autosave, create the editor
        window, log and update the session.
        """
        if view.kind == 'text':
            return self.open_file(view.path, du.library)
        if view.kind not in ('fsm', 'bd'):
            self.log(f'{du.name}/{view.name}: {view.label} views are not supported yet', 'warning')
            return
        key = native_path(du.library, du.name, view.name, view.kind)
        if key in self.editors:
            w = self.editors[key]
            w.show(); w.raise_(); w.activateWindow()
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            model = load_view(du.library, du, view)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.log(f'Cannot open {view.path}: {e}', 'error')
            QMessageBox.critical(self, 'Open view', f'Cannot open {view.path}:\n{e}')
            return
        QApplication.restoreOverrideCursor()
        ctx = EditorContext(self, self.project, du.library, du, view)
        if not ctx.acquire(self):
            return
        ctx.key = key
        recovered = None
        if not ctx.readonly:
            text = self._recover(key, view.kind, key if os.path.exists(key) else view.path)
            if text is not None:
                try:
                    recovered = (FsmView if view.kind == 'fsm' else BlockDiagram).from_json(text)
                except (ValueError, KeyError, TypeError) as e:
                    self.log(f'Cannot read the unsaved changes of {key}: {e}', 'error')
        w = FsmEditorWindow(recovered or model, ctx) if view.kind == 'fsm' else BdEditorWindow(recovered or model, ctx)
        if recovered is not None:
            w.dirty = True
            w.undo_stack.clean = None           # recovered changes are not on disk: no state is "saved"
            w.update_title()
            self.log(f'Recovered unsaved changes of {du.library.name}/{du.name}/{view.name}')
        if view.legacy:
            w.statusBar().showMessage(f'Imported from {os.path.basename(view.path)}; '
                                      f'Save writes {os.path.basename(key)} next to it.', 10000)
        self.editors[key] = w
        w.show()
        self.log(f'Opened {du.library.name}/{du.name}/{view.name} ({view.label})'
                 + (' read-only: ' + ctx.readonly_reason if ctx.readonly else ''))
        self.session_changed()

    def open_file(self, path: str, lib: Library | None):
        """Open a file of a library pane: a view file in its editor, anything else as text."""
        if path.endswith(('.sm', '.bd', '.fsm.json', '.bd.json')) and lib is not None:
            unit = os.path.basename(os.path.dirname(path))
            du = lib.units.get(unit)
            if du:
                v = next((v for v in du.views if v.path == path), None) or du.graphic_view()
                if v:
                    return self.open_view(du, v)
        self.open_text_file(path, lib)

    def open_text_file(self, path: str, lib: Library | None = None):
        """Open an HDL / text file in the text editor (or the external editor of the preferences),
        read-only when its library is protected.
        """
        if lib is None and self.project is not None:
            lib = next((l for l in self.project.libraries if l.owns(path)), None)
        if self.prefs.use_external_editor and self.prefs.external_editor:
            cmd = self.prefs.external_editor.replace('{file}', shlex.quote(path)).replace('{line}', '1')
            try:
                subprocess.Popen(shlex.split(cmd))
                self.log(f'Started: {cmd}')
            except OSError as e:
                self.log(f'Cannot start external editor "{cmd}": {e}', 'error')
            return
        key = os.path.abspath(path)
        if key in self.editors:
            w = self.editors[key]
            w.show(); w.raise_(); w.activateWindow()
            return
        ro = ''
        if lib is not None and not lib.writable:
            ro = f'library {lib.name} is {lib.type}'
        elif os.path.exists(path) and not os.access(path, os.W_OK):
            ro = 'no write permission'
        w = TextEditorWindow(path, lib.include_dirs if lib else [], ro,
                             on_saved=lambda p: self._text_saved(p), on_closed=lambda w, k=key: self._text_closed(k))
        if not ro:
            text = self._recover(key, 'text', path)
            if text is not None:
                w.editor.setPlainText(text)
                w.editor.document().setModified(True)
                self.log(f'Recovered unsaved changes of {path}')
        self.editors[key] = w
        w.show()
        self.session_changed()

    def open_any_file(self):
        """File > Open HDL File...: choose any file and open it as text."""
        path, _ = QFileDialog.getOpenFileName(self, 'Open HDL file', self.project.dir if self.project else '',
                                              'HDL (*.v *.sv *.vh *.svh);;All files (*)')
        if path:
            self.open_text_file(path)

    def _text_saved(self, path: str):
        """A text file was saved: rescan its library (its units and ports may have changed)."""
        self.log(f'Saved {path}')
        for ex in self.explorers.values():
            if ex.lib.owns(path):
                ex.refresh()

    def editor_closed(self, ctx: EditorContext):
        """An editor window closed: forget it, drop its autosave, save the session."""
        key = getattr(ctx, 'key', '')
        self.editors.pop(key, None)
        drop_autosave(key)          # closed normally: saved or discarded on purpose
        self.session_changed()

    def _text_closed(self, key: str):
        """A text editor window closed: forget it, drop its autosave, save the session."""
        self.editors.pop(key, None)
        drop_autosave(key)
        self.session_changed()

    # -- session & autosave --------------------------------------------------------------
    def session_changed(self):
        """Something the session records changed: save it soon (timer)."""
        if not self._session_quiet:
            self._session_timer.start()

    def session_snapshot(self) -> Session:
        """The current session: project, library tabs, editor windows (place, page, cursor line) and
        the extra hierarchy roots.
        """
        s = Session(project=os.path.abspath(self.project.path) if self.project else '',
                    geometry=bytes(self.saveGeometry().toBase64()).decode('ascii'))
        for i in range(1, self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, LibraryExplorer):
                s.explorers.append(w.lib.name)
                if w.extra_roots:
                    s.hierarchies[w.lib.name] = [list(k) for k in w.extra_roots]
                if w is self.tabs.currentWidget():
                    s.current = w.lib.name
        for key, w in self.editors.items():
            geo = bytes(w.saveGeometry().toBase64()).decode('ascii')
            if isinstance(w, TextEditorWindow):
                s.editors.append(EditorState('text', path=w.path, geometry=geo,
                                             line=w.editor.textCursor().blockNumber() + 1))
            elif getattr(w, 'context', None) is not None:
                c = w.context
                s.editors.append(EditorState('view', c.lib.name, c.unit.name, c.view.name, key, geo,
                                             w.tabs.currentIndex()))
        return s

    def save_session(self):
        """Write the session (unless restoring it is switched off)."""
        if self._session_quiet:
            return
        try:
            self.session_snapshot().save()
        except OSError as e:
            self.log(f'Cannot save the session: {e}', 'warning')

    def restore_session(self, project_path: str = '') -> bool:
        """Reopen the last session (or only its windows of `project_path`, when given)."""
        s = Session.load()
        if s is None or not s.project:
            if project_path:
                self.load_project(project_path)
            return False
        same = not project_path or os.path.normcase(os.path.abspath(project_path)) == os.path.normcase(s.project)
        target = project_path or s.project
        if not os.path.exists(target):
            self.log(f'Last project {target} no longer exists', 'warning')
            return False
        if s.geometry:
            self.restoreGeometry(QByteArray.fromBase64(s.geometry.encode('ascii')))
        self._session_quiet = True
        self.progress.begin(f'Restoring the last session ({os.path.basename(target)})...')
        try:
            self.load_project(target)
            if self.project is None or not same:
                return False
            for name in s.explorers:
                lib = self.project.library(name)
                if lib is not None:
                    self.explore(lib)
                    roots = s.hierarchies.get(name) or []
                    if roots:
                        ex = self.explorers[name]
                        ex.extra_roots = [tuple(k) for k in roots if isinstance(k, list) and len(k) == 2]
                        ex._fill_hierarchy()
            for es in s.editors:
                self._reopen(es)
            if s.current in self.explorers:
                self.tabs.setCurrentWidget(self.explorers[s.current])
            elif not s.current:
                self.tabs.setCurrentIndex(0)
        finally:
            self._session_quiet = False
            self.progress.end()
        self.log(f'Restored the last session ({len(s.editors)} window(s))')
        self.save_session()
        return True

    def _reopen(self, es: EditorState):
        """Reopen the editor windows of a saved session, at their saved places."""
        geo = QByteArray.fromBase64(es.geometry.encode('ascii')) if es.geometry else None
        if es.kind == 'text':
            if not os.path.exists(es.path):
                self.log(f'{es.path} no longer exists', 'warning')
                return
            self.open_text_file(es.path)
            w = self.editors.get(os.path.abspath(es.path))
            if w is not None and es.line:
                w.editor.goto_line(es.line)
        else:
            lib = self.project.library(es.library)
            du = self.project.find_unit(es.unit, prefer=lib) if lib is not None else None
            view = next((v for v in du.views if v.name == es.view and v.kind in ('fsm', 'bd')), None) if du else None
            if view is None:
                self.log(f'{es.library}/{es.unit}/{es.view} no longer exists', 'warning')
                return
            self.open_view(du, view)
            w = self.editors.get(native_path(du.library, du.name, view.name, view.kind))
            if w is not None and 0 <= es.tab < w.tabs.count():
                w.tabs.setCurrentIndex(es.tab)
        if w is not None and geo is not None:
            w.restoreGeometry(geo)

    def autosave(self):
        """Keep the unsaved content of every editor, to recover it after a crash."""
        for key, w in list(self.editors.items()):
            try:
                if isinstance(w, TextEditorWindow):
                    if w.editor.document().isModified() and not w.readonly_reason:
                        write_autosave(key, 'text', w.editor.toPlainText())
                    else:
                        drop_autosave(key)
                elif getattr(w, 'context', None) is not None:
                    if w.dirty and not w.context.readonly:
                        model = w.view if isinstance(w, FsmEditorWindow) else w.bd
                        write_autosave(key, w.context.view.kind, model.to_json())
                    else:
                        drop_autosave(key)
            except OSError as e:
                self.log(f'Autosave of {key} failed: {e}', 'warning')
        self.save_session()

    def _recover(self, key: str, kind: str, file_path: str) -> str | None:
        """Unsaved content left by a crash, if the user wants it back."""
        saved = read_autosave(key)
        if saved is None or saved.get('kind') != kind:
            return None
        mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0.0
        if saved.get('saved_at', 0) <= mtime:
            drop_autosave(key)          # the file was saved after this copy
            return None
        when = datetime.fromtimestamp(saved['saved_at']).strftime('%Y-%m-%d %H:%M')
        r = QMessageBox.question(self, 'Recover unsaved changes',
                                 f'{os.path.basename(key)} has changes that were not saved (kept at {when}), '
                                 'probably because the tool was closed abnormally.\n\nRecover them?',
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if r != QMessageBox.Yes:
            drop_autosave(key)
            return None
        return saved['content']

    def view_saved(self, ctx: EditorContext):
        """An editor saved its view: rescan its library tab (new files, time stamps)."""
        ex = self.explorers.get(ctx.lib.name)
        if ex:
            ex.refresh()

    # -- generation -------------------------------------------------------------------------
    def generate_model(self, lib: Library, du: DesignUnit, model, parent):
        """Generate one unit from the model of an editor (asks before overwriting a hand-edited file)."""
        generate_with_prompt(self, lib, du, model, parent)

    def generate_units(self, units: list[DesignUnit]):
        """Generate the given units (each from its graphical view)."""
        targets = [u for u in units if u.graphic_view()]
        if not targets:
            self.log('Nothing to generate: select design units that have a state machine or block diagram view',
                     'warning')
            return
        for du in targets:
            key = native_path(du.library, du.name, du.graphic_view().name, du.graphic_view().kind)
            editor = self.editors.get(key)
            model = (getattr(editor, 'view', None) or getattr(editor, 'bd', None)) if editor else None
            generate_with_prompt(self, du.library, du, model, self, du.graphic_view())
        for ex in self.explorers.values():
            if any(u.library is ex.lib for u in targets):
                ex.refresh()

    def generate_selected(self):
        """Tasks > Generate on the units selected in the current library tab."""
        w = self.tabs.currentWidget()
        if isinstance(w, LibraryExplorer):
            self.generate_units(w.selected_units())
        else:
            self.log('Open a library and select design units to generate', 'warning')

    def generate_current_library(self):
        """Generate every unit of the library of the current tab."""
        lib = self._selected_lib()
        if lib:
            self.generate_library(lib)

    def generate_library(self, lib: Library):
        """Generate every unit of `lib` with a graphical view."""
        if not lib.scanned:
            lib.scan(self.project.cache, self.project.progress)
        units = [u for u in lib.units.values() if u.graphic_view()]
        self.log(f'Generating {len(units)} design unit(s) in {lib.name}')
        self.generate_units(units)

    def report_generation(self, res: GenResult):
        """Log the result of one generation (written / unchanged / conflict / error and warnings)."""
        if res.status == 'written':
            self.log(f'{res.unit}: wrote {res.path}', path=res.path)
        elif res.status == 'unchanged':
            self.log(f'{res.unit}: {os.path.basename(res.path)} is up to date', path=res.path)
        elif res.status == 'conflict':
            self.log(f'{res.unit}: {res.message}', 'warning', res.path)
        else:
            self.log(f'{res.unit}: {res.message}', 'error')
        for w in res.warnings:
            self.log(f'{res.unit}: {w}', 'warning')

    # -- creation ------------------------------------------------------------------------------
    def new_project(self):
        """File > New Project."""
        dlg = NewProjectDialog(self)
        if dlg.exec():
            path = dlg.hdp_path
            try:
                create_project(path, dlg.lib.text().strip())
            except OSError as e:
                QMessageBox.critical(self, 'New project', str(e))
                return
            self.load_project(path)

    def open_project_dialog(self):
        """File > Open Project: choose a .hdp file."""
        path, _ = QFileDialog.getOpenFileName(self, 'Open project', os.path.dirname(self.prefs.recent_projects[0])
                                              if self.prefs.recent_projects else '', 'Project files (*.hdp)')
        if path:
            self.load_project(path)

    def new_library(self):
        """File > New Library: add a library to the project and open its tab."""
        if self.project is None:
            return QMessageBox.information(self, 'New library', 'Open or create a project first.')
        dlg = NewLibraryDialog(self.project.dir, self)
        if dlg.exec():
            name = dlg.name.text().strip()
            if self.prefs.downcase_names:
                name = name.lower()                 # Main Settings > General
            if self.project.library(name):
                return QMessageBox.warning(self, 'New library', f'Library {name} already exists.')
            lib = self.project.add_library(name, dlg.folder.text().strip(), dlg.type.currentText())
            self.log(f'Created library {name} in {dlg.folder.text().strip()}')
            self.fill_project()
            self.explore(lib)

    def new_unit(self):
        """File > New Design Content: create a state machine, block diagram or text module in a
        library (from templates.py) and open it.
        """
        if self.project is None:
            return QMessageBox.information(self, 'New design content', 'Open or create a project first.')
        writable = [l.name for l in self.project.libraries if l.writable]
        cur = self._selected_lib()
        dlg = NewUnitDialog(writable, cur.name if cur else self.project.default_library, self.prefs, self)
        if not dlg.exec():
            return
        lib = self.project.library(dlg.lib.currentText())
        unit = dlg.unit.text().strip()
        if self.prefs.downcase_names:
            unit = unit.lower()                     # Main Settings > General
        if not lib.scanned:
            lib.scan(self.project.cache, self.project.progress)
        if unit in lib.units:
            return QMessageBox.warning(self, 'New design content', f'{unit} already exists in {lib.name}.')
        kind = dlg.kind.currentData()
        ports = dlg.parsed_ports()
        if kind == 'fsm':
            view = dlg.view.text().strip() or 'fsm'
            model = new_fsm(lib.name, unit, view, ports, dlg.language.currentData(),
                            self.prefs.default_state_decl, self.prefs.default_encoding)
            model.pre_module_directives = self._pre_module(model.language)
            model.post_module_directives, model.end_module_directives = self.prefs.post_module, self.prefs.end_module
            path = native_path(lib, unit, view, 'fsm')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            model.save(path)
            self.log(f'Created state machine {lib.name}/{unit}/{view}')
        elif kind == 'bd':
            # an empty block diagram (as the legacy tool creates one); its ports come from the nets and
            # PortIOs drawn on it, so the Ports list of the dialog is not used
            from bd_model import BlockDiagram
            view = dlg.view.text().strip() or 'struct'
            model = BlockDiagram(library=lib.name, unit=unit, view=view, language=dlg.language.currentData())
            model.pre_module_directives = self._pre_module(model.language)
            model.post_module_directives, model.end_module_directives = self.prefs.post_module, self.prefs.end_module
            path = native_path(lib, unit, view, 'bd')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(model.to_json())
            self.log(f'Created block diagram {lib.name}/{unit}/{view}')
        else:
            language = 'systemverilog' if kind == 'sv' else 'verilog'
            pr = self.prefs                         # Options > Verilog > File: source file naming rule
            name = pr.source_rule.replace('%(module_name)', unit).replace('%(unit)', unit).replace(
                '%(ext)', pr.sv_ext if kind == 'sv' else pr.source_ext)
            name = {'Always lower case': name.lower(), 'Always upper case': name.upper()}.get(pr.source_case, name)
            path = os.path.join(lib.main_hdl_dir, name)
            header = expand_header(self.prefs.header_template, lib.name, unit, unit, self.project.name)
            os.makedirs(lib.main_hdl_dir, exist_ok=True)
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(new_module(unit, ports, language, header, self._pre_module(language),
                                            pr.post_module, pr.end_module))
            self.log(f'Created {path}', path=path)
        self.explore(lib)
        self.explorers[lib.name].refresh()
        du = lib.units.get(unit)
        if du:
            self.open_unit(du)

    def _pre_module(self, language: str) -> str:
        """Verilog Options > Default Directives (pre-module), then the Default Packages for SystemVerilog."""
        parts = [self.prefs.pre_module.strip('\n')]
        if language == 'systemverilog':
            parts.append(self.prefs.package_refs.strip('\n'))
        return '\n'.join(t for t in parts if t)

    def verilog_options(self, parent=None):
        """Options > Verilog... (over `parent`, the diagram it is asked from, else the Design Manager)"""
        from .dm_options import VerilogOptionsDialog
        dlg = VerilogOptionsDialog(self.prefs, parent or self, self.project)
        dlg.exec()
        if dlg.applied:
            self._apply_verilog_options()
            self.log('Verilog options saved to ' + self.prefs.path())

    def _apply_verilog_options(self):
        """Make the Verilog options take effect: allowed extensions, generation style (tab width,
        parameter mapping, @*).
        """
        from project import generate, project
        from . import text_editor
        project.set_allowed_extensions(self.prefs.verilog_extensions)
        generate.GENERATED_EXT.update(verilog=self.prefs.generated_ext or 'v', systemverilog=self.prefs.sv_ext or 'sv')
        text_editor.TAB_WIDTH = int(self.prefs.verilog_style.get('tab_width', 2))
        # the generators follow Options > Verilog > Style as the legacy tool does
        from codegen.common import set_style
        st = self.prefs.verilog_style
        set_style(st.get('tab_width', 2), st.get('param_mapping', 'Named'), st.get('implicit_event', False))

    def preferences(self):
        """Options > Preferences..."""
        dlg = PreferencesDialog(self.prefs, self)
        if dlg.exec():
            dlg.apply()
            self.log('Preferences saved to ' + self.prefs.path())

    def eventFilter(self, obj, e):
        """Swallow tool tips while View > Object Tips (or the toolbar Tooltips option) is off."""
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.ToolTip and not self.object_tips and isinstance(obj, QWidget) and obj.window() is self:
            return True                             # View > Object Tips off
        if e.type() == QEvent.ToolTip and not self.toolbar_tips and isinstance(obj, QWidget) and isinstance(obj.parent(), QToolBar):
            return True                             # View > Toolbars > Tooltips off
        return super().eventFilter(obj, e)

    def closeEvent(self, e):
        """Exit: save the session first (so it still lists the open windows), then close the project;
        the window stays open when an editor refuses to close.
        """
        # remember the windows before closing them; closing must not overwrite that
        self.save_session()
        self._session_quiet = True
        if self.close_project():
            e.accept()
        else:
            self._session_quiet = False
            e.ignore()
