"""The Signals Table / Parameters Table pages of an editor window, as the legacy tool shows them:
while one of these pages is shown the window has the table menus (menus.table_menus: Table menu,
no Diagram / Simulate / Animation), a shorter Standard toolbar, the SM Signals Tools toolbar
and the Appearance toolbar at the bottom (cell colours, font size and style, alignment); the
diagram's own toolbars come back with the diagram page.

    TablePages(win, kind, tables, diagram, diagram_menus, table_menus, keys)

`tables` maps 'signals' / 'parameters' to the pages (tables._ListTable), `diagram` is the widget of
the diagram page, the menu functions give arrange_menus specs. The commands are the window's
toolbar_actions (keys of toolbars.FSM_TABLE_TOOLBARS / APPEARANCE and menus.table_menus).
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QInputDialog, QMainWindow, QMenu, QToolBar, QWidget)

from .menus import arrange_menus
from .toolbars import APPEARANCE, BD_TABLE_TOOLBARS, FSM_TABLE_TOOLBARS, build_toolbars

# the colour grid of the Foreground Color / Font Color drop-downs, row by row (read from the legacy tool)
PALETTE = ['#800080', '#000080', '#008000', '#c00000', '#000000',
           '#c000c0', '#0000c3', '#00c0c0', '#c0c000', '#800000',
           '#ff0000', '#0000ff', '#00ff00', '#ffff00', '#676767',
           '#ea9cff', '#0080c0', '#9cdeff', '#ffff91', '#808080',
           '#ff00ff', '#759cff', '#00ffff', '#ffffb4', '#ffffff']
# Fill Style: the patterns of a cell's fill
FILL_STYLES = [('Solid', 'solid'), ('Dense', 'dense'), ('Horizontal', 'hor'), ('Vertical', 'ver'),
               ('Cross', 'cross'), ('Backward Diagonal', 'bdiag'), ('Forward Diagonal', 'fdiag'),
               ('Diagonal Cross', 'diagcross')]


def _swatch(colour: str) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(QColor(colour))
    return QIcon(pm)


def colour_menu(parent, pick: Callable[[str], None], other: Callable[[], None]) -> QMenu:
    """The legacy colour drop-down: a 5 x 5 grid of colours and Other... below."""
    from PySide6.QtWidgets import QGridLayout, QPushButton, QToolButton, QVBoxLayout, QWidgetAction
    menu = QMenu(parent)
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(4, 4, 4, 4)
    grid = QGridLayout()
    grid.setSpacing(3)
    for k, c in enumerate(PALETTE):
        b = QToolButton()
        b.setFixedSize(18, 18)
        b.setToolTip(c)
        b.setStyleSheet(f'QToolButton {{ background: {c}; border: 1px solid #808080; }} '
                        'QToolButton:hover { border: 2px solid #ffffff; }')
        b.clicked.connect(lambda checked=False, c=c: (menu.close(), pick(c)))
        grid.addWidget(b, k // 5, k % 5)
    lay.addLayout(grid)
    o = QPushButton('Other...')
    o.clicked.connect(lambda: (menu.close(), other()))
    lay.addWidget(o)
    wa = QWidgetAction(menu)
    wa.setDefaultWidget(box)
    menu.addAction(wa)
    return menu


class TablePages:
    """See the module docstring."""

    def __init__(self, win: QMainWindow, kind: str, tables: dict, diagram: QWidget,
                 diagram_menus: Callable[[], list], table_menus: Callable[[], list], keys: dict):
        self.win, self.kind, self.tables, self.diagram = win, kind, tables, diagram
        self.diagram_menus, self.table_menus = diagram_menus, table_menus
        win.current_page = 'diagram'
        self._make_actions()
        acts = win.toolbar_actions
        spec = FSM_TABLE_TOOLBARS if kind == 'fsm' else BD_TABLE_TOOLBARS
        bars = build_toolbars(win, acts, spec, keys, page='table')
        hdl = next((t for t in win.findChildren(QToolBar) if t.windowTitle() == 'HDL Tools'), None)
        if hdl is not None:
            for tb in bars:                                     # before HDL Tools, as in the legacy tool
                win.insertToolBar(hdl, tb)
        bars += build_toolbars(win, acts, [('Appearance', APPEARANCE)], keys, page='table',
                               area=Qt.BottomToolBarArea)
        for tb in win.findChildren(QToolBar):
            if tb.windowTitle() in ('Standard', 'State Diagram Tools', 'Block Diagram Tools', 'Generation') \
                    and tb not in bars:
                tb.setProperty('page', 'diagram')
        self.bars = bars
        for t in tables.values():
            t.table.currentCellChanged.connect(lambda *a: self.update_states())
        win.tabs.currentChanged.connect(lambda _i: self.page_changed())
        self.page_changed()

    # -- pages -------------------------------------------------------------------------------------
    def current(self):
        """The table page shown (the Signals Table when the diagram is shown)."""
        w = self.win.tabs.currentWidget()
        return w if w in self.tables.values() else self.tables['signals']

    def page_changed(self):
        """Another page: the toolbars and menus of that page."""
        page = 'table' if self.win.tabs.currentWidget() in self.tables.values() else 'diagram'
        changed = page != self.win.current_page or not getattr(self, '_shown', False)
        self.win.current_page = page
        self._shown = True
        for tb in self.win.findChildren(QToolBar):
            if tb.property('page') in ('diagram', 'table'):
                tb.setVisible(tb.property('page') == page)
        if changed:
            arrange_menus(self.win, self.table_menus() if page == 'table' else self.diagram_menus())
        self.update_states()

    def show_table(self, which: str):
        self.win.tabs.setCurrentWidget(self.tables[which])

    # -- actions -----------------------------------------------------------------------------------
    def _make_actions(self):
        win = self.win
        acts = win.toolbar_actions
        ro = lambda: self.current().readonly   # noqa: E731

        def act(key, text, slot=None, checkable=False, shortcut=''):
            a = QAction(text, win)
            if checkable:
                a.setCheckable(True)
                if slot is not None:
                    a.toggled.connect(slot)
            elif slot is not None:
                a.triggered.connect(lambda checked=False, f=slot: f())
            if shortcut:
                a.setShortcut(shortcut)
            if slot is None:
                a.setEnabled(False)
                a.setProperty('available', False)
            acts[key] = a
            return a
        t = self.current
        act('table_cut', 'Cut', lambda: t().cut())
        act('table_copy', 'Copy', lambda: t().copy())
        act('table_paste', 'Paste', lambda: t().paste())
        act('table_paste_system', 'Paste from system clipboard', lambda: t().paste())
        act('table_delete', 'Delete', lambda: t().delete())
        act('table_select_all', 'Select All', lambda: t().select_all())
        act('table_appearance', 'Appearance...', self.appearance_dialog)
        act('table_copy_picture', 'Copy Picture', lambda: QApplication.clipboard().setPixmap(t().grab()))
        act('export_tsv', 'TSV (Tab delimited) file...', lambda: t().export(win, '\t'))
        act('export_csv', 'CSV (Comma delimited) file...', lambda: t().export(win, ','))
        act('ports_comments', 'Comments...', self.edit_comment)
        act('table_group', 'Group', self.group)
        act('table_group_add', 'Group', self.group)
        act('table_ungroup', 'UnGroup', lambda: t().group_selected(''))
        act('table_expand', 'Expand All Groups')               # groups are always open in this version
        act('table_collapse', 'Collapse All Groups')
        act('sort_asc', 'Sort Ascending', lambda: t().sort(False))
        act('sort_desc', 'Sort Descending', lambda: t().sort(True))
        act('hide_column', 'Hide Column', lambda: t().hide_column())
        act('show_columns', 'Show Columns...', lambda: t().show_columns(win))
        act('autofit', 'Autofit', lambda: t().autofit())
        # Toggle Filter: the filter row under the column names (both tables)
        act('table_filter', 'Filter', lambda on: [x.set_filter_row(on) for x in self.tables.values()],
            checkable=True)
        act('table_filter_settings', 'Filter Settings...', self.filter_settings)
        if self.kind == 'fsm':                              # View Table for Machine: a drop-down of machines
            vm = act('table_machine', 'View Table for Machine', lambda: None)
            mm = QMenu(win)
            mm.aboutToShow.connect(lambda: fill_machine_tables(win, mm))
            vm.setMenu(mm)
        act('toggle_tables', 'Toggle Signals/Parameters Tables',
            lambda: self.show_table('parameters' if self.current() is self.tables['signals'] else 'signals'))
        act('show_grouped', 'Show Grouped', lambda on: [x.set_grouped(on) for x in self.tables.values()],
            checkable=True)
        act('show_diagram', 'State Machine' if self.kind == 'fsm' else 'Block Diagram',
            lambda: win.tabs.setCurrentWidget(self.diagram))
        for key, text in (('add_input_port', 'Input Port'), ('add_output_port', 'Output Port'),
                          ('add_inout_port', 'InOut Port'), ('add_local_signal', 'Local Signal')):
            if key not in acts:                             # the block diagram: a row of the Signal Table
                mode = key.split('_')[1].replace('local', 'local')
                act(key, text, lambda m=mode: self.add_signal(m))
        # Appearance: the button applies the colour picked last, its arrow opens the colour grid
        self.last_colour = {'bg': '#ffff91', 'fg': '#ff0000'}
        for key, text, attr in (('fill_color', 'Foreground Color', 'bg'), ('font_color', 'Font Color', 'fg')):
            a = act(key, text, lambda attr=attr: t().set_format(**{attr: self.last_colour[attr]}))
            a.setMenu(colour_menu(win, lambda c, attr=attr: self.set_colour(attr, c),
                                  lambda attr=attr: self.pick_colour(attr)))
        fs = act('fill_style', 'Fill Style', lambda: t().set_format(pattern=self.last_pattern))
        self.last_pattern = 'bdiag'
        sm = QMenu(win)
        for label, pattern in FILL_STYLES:
            sm.addAction(label, lambda pt=pattern: (setattr(self, 'last_pattern', pt), t().set_format(pattern=pt)))
        fs.setMenu(sm)
        act('font_grow', 'Increase Font Size', lambda: t().set_format(grow=1))
        act('font_shrink', 'Decrease Font Size', lambda: t().set_format(grow=-1))
        for key in ('bold', 'italic', 'underline'):
            act(key, key.capitalize(), lambda k=key: t().set_format(**{k: None}))
        for key, align in (('cell_align_left', 'left'), ('cell_align_center', 'center'),
                           ('cell_align_right', 'right')):
            act(key, 'Align ' + align.capitalize(), lambda al=align: t().set_format(align=al))
        self._readonly = ro

    def update_states(self):
        """Grey what has nothing to act on (a read-only diagram, no row for the row commands)."""
        acts = self.win.toolbar_actions
        tbl = self.current()
        ro = tbl.readonly
        has_row = 0 <= tbl.table.currentRow() < len(tbl.rows)
        for key in ('table_cut', 'table_paste', 'table_paste_system', 'table_delete', 'add_input_port',
                    'add_output_port', 'add_inout_port', 'add_local_signal', 'table_group', 'table_group_add',
                    'table_ungroup', 'ports_comments', 'fill_color', 'font_color', 'fill_style', 'font_grow',
                    'font_shrink', 'bold', 'italic', 'underline', 'cell_align_left', 'cell_align_center',
                    'cell_align_right', 'table_appearance'):
            a = acts.get(key)
            if a is not None and a.property('available') is not False:
                a.setEnabled(not ro and (has_row or key.startswith(('add_', 'table_paste')) or
                                         key in ('fill_color', 'font_color', 'fill_style', 'font_grow',
                                                 'font_shrink', 'bold', 'italic', 'underline', 'cell_align_left',
                                                 'cell_align_center', 'cell_align_right', 'table_appearance')))
        is_signals = tbl is self.tables['signals']
        for key in ('add_input_port', 'add_output_port', 'add_inout_port', 'add_local_signal'):
            if key in acts and self.win.current_page == 'table':
                acts[key].setEnabled(not ro)
        acts['ports_comments'].setEnabled(not ro and has_row and is_signals)

    # -- commands ----------------------------------------------------------------------------------
    def add_signal(self, mode: str):
        """Add > Input Port / Output Port / InOut Port / Local Signal on a table page of a block
        diagram: a new row of the Signal Table, its name ready to type."""
        tbl = self.tables['signals']
        self.show_table('signals')
        row = tbl.new_row(None)
        row.mode = mode
        tbl.rows.append(row)
        tbl._set_order(tbl.display_rows())
        tbl.table.refresh()
        tbl.changed.emit()
        tbl.edit_cell(row, 'name')

    def group(self):
        """Table > Group > Group: the selected rows into a group (its name asked)."""
        name, ok = QInputDialog.getText(self.win, 'Group', 'Group name:')
        if ok and name.strip():
            self.current().group_selected(name.strip())

    def edit_comment(self):
        """Table > Ports > Comments...: the comment of the current signal."""
        tbl = self.current()
        rows = tbl.display_rows()
        r = tbl.table.currentRow()
        if not 0 <= r < len(rows):
            return
        text, ok = QInputDialog.getMultiLineText(self.win, 'Comments', f'Comment of {rows[r].name}:',
                                                 rows[r].comment)
        if ok and text != rows[r].comment:
            rows[r].comment = text.strip()
            tbl.table.refresh()
            tbl.changed.emit()

    def set_colour(self, attr: str, colour: str):
        """A colour picked in the grid: applied to the selected cells, and kept for the button."""
        self.last_colour[attr] = colour
        self.current().set_format(**{attr: colour})

    def pick_colour(self, attr: str):
        """Other...: any colour."""
        c = QColorDialog.getColor(QColor(self.last_colour[attr]), self.win)
        if c.isValid():
            self.set_colour(attr, c.name())

    def filter_settings(self):
        """Table > Filter Settings...: a value to keep for each column ((All): no filter)."""
        tbl = self.current()
        t = tbl.table
        dlg = QDialog(self.win)
        dlg.setWindowTitle('Filter Settings')
        form = QFormLayout(dlg)
        boxes = []
        from .tables import HEADERS
        for c, attr in enumerate(t.columns):
            cb = QComboBox()
            cb.addItem('(All)')
            values = sorted({tbl.text(r, attr) for r in tbl.rows}, key=str.lower)
            cb.addItems([v or '(Blanks)' for v in values])
            if c in t.filters:
                cb.setCurrentText(t.filters[c] or '(Blanks)')
            form.addRow(HEADERS.get(attr, attr) + ':', cb)
            boxes.append((c, cb))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec():
            t.filters.clear()
            for c, cb in boxes:
                if cb.currentIndex() > 0:
                    t.filters[c] = '' if cb.currentText() == '(Blanks)' else cb.currentText()
            t.apply_filters()

    def appearance_dialog(self):
        """Edit > Appearance...: the colours, font style and alignment of the selected cells."""
        tbl = self.current()
        cells = tbl.selected_cells()
        if not cells:
            return
        fmt = tbl.cell_format(*cells[0])
        dlg = QDialog(self.win)
        dlg.setWindowTitle('Appearance')
        form = QFormLayout(dlg)
        colours = {}
        for attr, label in (('bg', 'Fill color:'), ('fg', 'Font color:')):
            cb = QComboBox()
            for c in PALETTE:
                cb.addItem(_swatch(c), c)
            cb.setEditable(True)
            cb.setCurrentText(fmt.get(attr, '#ffffff'))
            form.addRow(label, cb)
            colours[attr] = cb
        align = QComboBox(); align.addItems(['left', 'center', 'right'])
        align.setCurrentText(fmt.get('align', 'center'))
        form.addRow('Alignment:', align)
        styles = {k: QCheckBox(k.capitalize()) for k in ('bold', 'italic', 'underline')}
        for k, box in styles.items():
            box.setChecked(bool(fmt.get(k)))
            form.addRow('', box)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec():
            tbl.set_format(bg=colours['bg'].currentText(), fg=colours['fg'].currentText(),
                           align=align.currentText(), **{k: b.isChecked() for k, b in styles.items()})


def fill_machine_tables(win, menu: QMenu):
    """View > Table for machine: the machines of the view (the tables belong to the view)."""
    menu.clear()
    for m in win.view.machines:
        a = menu.addAction(m.name)
        a.setCheckable(True)
        a.setChecked(m is win.machine)
        a.triggered.connect(lambda checked=False, x=m: win.show_machine(x))
