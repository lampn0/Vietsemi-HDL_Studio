"""Block diagram dialogs: choose a component, component properties
(library, names, parameters, text visibility) and signal properties."""
from __future__ import annotations

import os
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QRadioButton, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from bd_model import BdInstance
from model import Parameter, Signal

NET_TYPES = ('wire', 'reg', 'logic', 'tri', 'triand', 'trior', 'tri0', 'tri1', 'trireg', 'wand', 'wor', 'uwire',
             'supply0', 'supply1', 'integer', 'time', 'real', 'realtime')


class ComponentPicker(QDialog):
    """Choose a design unit of the project, or a module from a .v/.sv file."""

    def __init__(self, entries: list[tuple[str, str, str]], start_dir: str = '', parent=None):
        """`entries` are (library, unit, type) of the project's units; `start_dir` is where the
        "From HDL file" chooser opens.
        """
        super().__init__(parent)
        self.setWindowTitle('Add Component')
        self.start_dir = start_dir
        self.file_choice: str | None = None
        self.filter = QLineEdit()
        self.filter.setPlaceholderText('Filter by library or unit name...')
        self.list = QListWidget()
        for lib, unit, typ in entries:
            it = QListWidgetItem(f'{lib}.{unit}    ({typ})')
            it.setData(Qt.UserRole, (lib, unit))
            self.list.addItem(it)
        self.filter.textChanged.connect(self._filter)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        from_file = QPushButton('From HDL file (.v / .sv)...')
        from_file.clicked.connect(self._pick_file)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.filter)
        lay.addWidget(self.list)
        row = QHBoxLayout()
        row.addWidget(from_file)
        row.addStretch(1)
        row.addWidget(bb)
        lay.addLayout(row)
        self.resize(560, 620)

    def _filter(self, text: str):
        """Hide the entries that do not contain the filter text."""
        t = text.lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(t not in it.text().lower())

    def _pick_file(self):
        """"From HDL file": choose a .v / .sv file instead (kept in file_choice) and close."""
        path, _ = QFileDialog.getOpenFileName(self, 'Component from HDL file', self.start_dir,
                                              'Verilog / SystemVerilog (*.v *.sv *.vh *.svh);;All files (*)')
        if path:
            self.file_choice = path
            self.accept()

    def choice(self) -> tuple[str, str] | None:
        """(library, unit) of the selected entry, or None."""
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None


# ---------------------------------------------------------------------------
# BD Object Properties: shared frame (category tree with icons, pages, buttons)
# ---------------------------------------------------------------------------
CATEGORIES = [('Components', 'component'), ('Blocks', 'block'), ('Embedded Blocks', 'embedded'),
              ('ModuleWare', 'moduleware'), ('ExternalIPs', 'external_ip'), ('Signals', 'wire'),
              ('Bundles', 'bundle'), ('PortIOs', 'port_out'),
              ('Frames', 'frame'), ('Comment Text', 'comment'), ('Requirement Reference', 'drc'),
              ('Comment Graphics', 'panel'), ('User Declarations', ''), ('User Properties', '')]

# fill patterns combining foreground and background colours, plus transparent ('none')
FILL_STYLES = ['solid', 'dense', 'medium', 'sparse', 'horizontal', 'vertical', 'cross', 'diagonal', 'diagonal cross',
               'none']

ATTRIBUTE_TEMPLATE = """// Template for Synopsys DC constraints
// synopsys dc_script_begin
//
// synopsys dc_script_end
//
// Template for Exemplar constraints
// exemplar attribute <object> <attribute> <value>"""


class ObjectPropertiesDialog(QDialog):
    """Common layout of the legacy "BD Object Properties" dialogs: the object categories
    on the left (the one being edited is active, with its sub-pages), the selected page on
    the right, the window title naming the page, and OK / Cancel / Apply / Help."""

    def __init__(self, category: str, parent=None):
        """Build the frame with `category` as the active category of the tree."""
        super().__init__(parent)
        from .icons import icon
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True); self.tree.setMinimumWidth(200)
        self.tree.setMaximumWidth(230)
        self.stack = QStackedWidget()
        self._pages: dict[int, tuple[QTreeWidgetItem, str]] = {}
        self.category_item = None
        for name, ic in CATEGORIES:
            it = QTreeWidgetItem(self.tree, [name])
            if ic:
                it.setIcon(0, icon(ic))
            if name == category and category:
                self.category_item = it
            elif name in ('User Declarations', 'User Properties'):
                self._extra_items = getattr(self, '_extra_items', []) + [it]
            else:
                it.setDisabled(True)
                if name != 'User Properties':
                    it.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
        self.tree.currentItemChanged.connect(self._page_changed)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
                              | QDialogButtonBox.Help)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        bb.button(QDialogButtonBox.Help).setEnabled(False)
        # User Declarations / User Properties: pages of their own (HDL Studio keeps neither: shown empty)
        for it in getattr(self, '_extra_items', []):
            page = QWidget(); pl = QVBoxLayout(page)
            if it.text(0) == 'User Properties':
                hint = QLabel('Add or modify properties associated with the selected object.\n'
                              'It is not necessary to specify a Class for user-entered properties.')
                hint.setEnabled(False); pl.addWidget(hint)
                t = QTableWidget(1, 3); t.setHorizontalHeaderLabels(['Class', 'Name', 'Value'])
                t.verticalHeader().hide(); t.setEnabled(False); pl.addWidget(t, 1)
            else:
                pl.addStretch(1)
            self.stack.addWidget(page)
            self._pages[id(it)] = (it, it.text(0), self.stack.count() - 1)
        body = QHBoxLayout(); body.addWidget(self.tree); body.addWidget(self.stack, 1)
        lay = QVBoxLayout(self); lay.addLayout(body, 1); lay.addWidget(bb)
        self.applied = False
        self.resize(820, 540)

    def add_page(self, label: str, title: str, widget: QWidget, child: bool = True) -> QTreeWidgetItem:
        """Add a page under the active category (`child`) or as the category's own page; `title` goes
        into the window title when the page is shown. Returns its tree item.
        """
        item = self.category_item if not child else QTreeWidgetItem(self.category_item, [label])
        self.stack.addWidget(widget)
        self._pages[id(item)] = (item, title, self.stack.count() - 1)
        self.category_item.setExpanded(True)
        return item

    def show_page(self, item: QTreeWidgetItem):
        """Select a page's tree item and show the page."""
        self.tree.setCurrentItem(item)
        self._page_changed(item, None)

    def _page_changed(self, cur, _prev):
        """Show the page of the tree item that became current."""
        page = self._pages.get(id(cur)) if cur is not None else None
        if page is not None:
            self.stack.setCurrentIndex(page[2])
            self.setWindowTitle(f'BD Object Properties - {page[1]}')

    def apply(self):
        """Write the pages into the object (subclasses extend it, then call this)."""
        self.applied = True

    def _ok(self):
        """OK: apply and close."""
        self.apply()
        self.accept()


def _desc(text: str) -> QLabel:
    """A word-wrapped description label."""
    lab = QLabel(text); lab.setWordWrap(True)
    return lab


class ColorButton(QPushButton):
    """Colour swatch that opens a colour chooser."""

    def __init__(self, color: str):
        """Start with `color` ('#rrggbb')."""
        super().__init__()
        self.setFixedSize(70, 22)
        self.set_color(color)
        self.clicked.connect(self._choose)

    def set_color(self, color: str):
        """Show and remember a new colour."""
        self.color = color
        self.setStyleSheet(f'background:{color}; border:1px solid #555;')

    def _choose(self):
        """Open the colour chooser and take the colour picked."""
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self.color), self, 'Color')
        if c.isValid():
            self.set_color(c.name())


class AppearancePage(QWidget):
    """Edit Appearance: colours, fill/line style and (for components) the shape."""

    def __init__(self, obj, shapes: list[str] | None = None):
        """Build the page from `obj` (anything with fg / bg / line_color / fill_style / line_style /
        line_width); `shapes` offers a Change Shape list.
        """
        super().__init__()
        self.obj = obj
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        col = QGroupBox('Color'); f = QFormLayout(col)
        self.fg, self.bg = ColorButton(obj.fg), ColorButton(obj.bg)
        self.line = ColorButton(obj.line_color or getattr(obj, 'kind_color', '#606060'))
        f.addRow('Foreground', self.fg); f.addRow('Background', self.bg); f.addRow('Line Color:', self.line)
        sty = QGroupBox('Style'); f = QFormLayout(sty)
        self.fill = QComboBox(); self.fill.addItems(FILL_STYLES)
        self.fill.setCurrentText(obj.fill_style)
        self.lstyle = QComboBox(); self.lstyle.addItems(['solid', 'dash', 'dot'])
        self.lstyle.setCurrentText(obj.line_style)
        self.lwidth = QComboBox(); self.lwidth.addItems(['0 (no line)', '1', '2', '3', '4'])
        self.lwidth.setCurrentIndex(min(max(obj.line_width, 0), 4))
        f.addRow('Fill Style:', self.fill); f.addRow('Line Style:', self.lstyle); f.addRow('Line Width:', self.lwidth)
        top.addWidget(col); top.addWidget(sty)
        lay.addLayout(top)
        self.shape = None
        if shapes:
            box = QGroupBox('Change Shape:'); h = QHBoxLayout(box)
            self.shape = QComboBox(); self.shape.addItems(shapes); self.shape.setCurrentText(obj.shape)
            h.addWidget(self.shape)
            lay.addWidget(box)
        lay.addStretch(1)

    def apply(self):
        """Write the colours and styles back into the object."""
        o = self.obj
        o.fg, o.bg, o.line_color = self.fg.color, self.bg.color, self.line.color
        o.fill_style, o.line_style = self.fill.currentText(), self.lstyle.currentText()
        o.line_width = self.lwidth.currentIndex()
        if self.shape is not None:
            o.shape = self.shape.currentText()


class TextVisibilityPage(QWidget):
    """Fields to display for ports (of a component, or a PortIO) and a format preview."""

    def __init__(self, obj, what: str, sample: str, show_params=None, name_attr: str = 'text_name'):
        """`what` is 'Port' or 'PortIO' (used in the labels), `sample` the name in the preview,
        `show_params` adds the "Show parameter values" box, `name_attr` names the object's
        attribute for the name visibility.
        """
        super().__init__()
        self.obj = obj
        self.name_attr = name_attr
        lay = QVBoxLayout(self)
        self.show_params = None
        if show_params is not None:
            self.show_params = QCheckBox('Show parameter values'); self.show_params.setChecked(show_params)
            lay.addWidget(self.show_params)
        lay.addWidget(_desc(f'Controls the format and visibility of usage and declaration information attached to '
                            f'{"all ports" if what == "Port" else "PortIO" + chr(39) + "s"} e.g. name, type and '
                            f'constraints.'))
        box = QGroupBox('Fields to display'); v = QVBoxLayout(box)
        self.name = QCheckBox(f'{what} Name'); self.name.setChecked(getattr(obj, name_attr))
        self.type = QCheckBox('Type Constraint'); self.type.setChecked(obj.text_type)
        self.type_name = QCheckBox('Type Name'); self.type_name.setChecked(obj.text_type_name)
        self.signed = QCheckBox('Signed'); self.signed.setChecked(obj.text_signed)
        self.value = QCheckBox('Value'); self.value.setChecked(obj.text_value)
        same = QCheckBox(f'Display {what} and Declaration information on the same line')
        same.setChecked(True); same.setEnabled(False)
        v.addWidget(self.name); v.addWidget(self.type)
        for c in (self.type_name, self.signed):
            row = QHBoxLayout(); row.addSpacing(22); row.addWidget(c); row.addStretch(1); v.addLayout(row)
        v.addWidget(self.value); v.addWidget(same)
        lay.addWidget(box)
        misc = QGroupBox('Misc'); g = QVBoxLayout(misc)
        self.selectable = None
        if hasattr(obj, 'selectable_text'):
            self.selectable = QCheckBox('Selectable Text   (allows text boxes on symbol to be individually selected)')
            self.selectable.setChecked(obj.selectable_text)
            g.addWidget(self.selectable)
        row = QHBoxLayout(); row.addWidget(QLabel('Format Preview:'), 0, Qt.AlignTop)
        self.preview = QLabel(); self.preview.setFrameShape(QLabel.Box); self.preview.setMinimumHeight(90)
        self.preview.setStyleSheet('background:white; font-family:"Courier New"; padding:6px;')
        self.preview.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        row.addWidget(self.preview, 1); g.addLayout(row)
        lay.addWidget(misc)
        self.sample = sample
        for c in (self.name, self.type, self.type_name, self.signed, self.value):
            c.toggled.connect(self._update)
        self._update()

    def _update(self, *_):
        """Enable the type sub-options while Type Constraint is on and refresh the preview."""
        for c in (self.type_name, self.signed):
            c.setEnabled(self.type.isChecked())
        self.preview.setText(port_label(self.sample, 'wire', True, '[15:0]', '#3', self._flags()) or ' ')

    def _flags(self) -> dict:
        """The check boxes as text_* flags (the keys port_label reads)."""
        return dict(text_name=self.name.isChecked(), text_type=self.type.isChecked(),
                    text_type_name=self.type_name.isChecked(), text_signed=self.signed.isChecked(),
                    text_value=self.value.isChecked())

    def apply(self):
        """Write the flags into the object."""
        for k, v in self._flags().items():
            setattr(self.obj, self.name_attr if k == 'text_name' else k, v)
        if self.selectable is not None:
            self.obj.selectable_text = self.selectable.isChecked()


def port_label(name: str, type_: str, signed: bool, bounds: str, value: str, f) -> str:
    """Text shown next to a port, as the legacy Port Display Control writes it on one line:
    "name : type signed [bounds] #delay" (Verilog shows the delay as the value)."""
    get = (lambda k: f[k]) if isinstance(f, dict) else (lambda k: getattr(f, k))
    decl = []
    if get('text_type'):
        decl += [x for x in ((type_ if get('text_type_name') else ''),
                             ('signed' if signed and get('text_signed') else ''), bounds) if x]
    if get('text_value') and value:
        decl.append(value if value.startswith('#') else f'#{value}')
    name_part = name if get('text_name') else ''
    if name_part and decl:
        return f'{name_part} : {" ".join(decl)}'
    return name_part or ' '.join(decl)


class ComponentPropertiesDialog(ObjectPropertiesDialog):
    """BD Object Properties for a component instance: Components, Parameters, Text
    Visibility, PortMap Frame, Attributes and Appearance pages."""

    def __init__(self, inst: BdInstance, libraries: list[str], symbol_params: list[tuple[str, str]],
                 page: str = 'component', parent=None, connections: list[tuple[str, str]] | None = None):
        """Build the pages for `inst`. `libraries` are offered for the library field, `symbol_params`
        are the parameters of the component's symbol, `connections` (pin, net) are listed on the
        PortMap Frame page, `page` is the page shown first.
        """
        super().__init__('Components', parent)
        self.inst = inst
        self.symbol_params = symbol_params
        items = {}

        # Components
        w = QWidget(); f = QFormLayout(w)
        row = QHBoxLayout()
        # as in the legacy tool, the library and component name belong to the design unit: change them
        # by moving or renaming the unit in the Design Explorer
        self.lib = QComboBox(); self.lib.addItems(sorted(set(libraries) | {inst.library}))
        self.lib.setCurrentText(inst.library); self.lib.setEnabled(False)
        self.lib.setToolTip('Move the design unit to another library in the Design Explorer to change this')
        self.lib_vis = QCheckBox('Visible'); self.lib_vis.setChecked(inst.show_library)
        row.addWidget(self.lib, 1); row.addWidget(self.lib_vis)
        f.addRow('Library:', row)
        self.unit = QLineEdit(inst.unit); self.unit.setReadOnly(True)
        self.unit.setToolTip('Rename the design unit in the Design Explorer to change this')
        f.addRow('Component Name:', self.unit)
        row = QHBoxLayout()
        self.name = QLineEdit(inst.name)
        self.name_vis = QCheckBox('Visible'); self.name_vis.setChecked(inst.show_instance)
        row.addWidget(self.name, 1); row.addWidget(self.name_vis)
        f.addRow('Instance Name:', row)
        items['component'] = self.add_page('Components', 'Components', w, child=False)

        # Parameters
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel(f'Instance "{inst.name}" of module "{inst.unit}"'))
        body = QHBoxLayout()
        left = QVBoxLayout()
        # "Symbol parameters only": the symbol's Parameters table; "All parameters": also those declared
        # in the module. Each is listed with its default declaration as written.
        sets = symbol_params if isinstance(symbol_params, dict) else {'symbol': symbol_params, 'all': symbol_params}
        self.param_sets = {'symbol': list(sets.get('symbol') or sets.get('all') or []),
                           'all': list(sets.get('all') or sets.get('symbol') or [])}
        self.only_symbol = QRadioButton('Symbol parameters only')
        self.all_params = QRadioButton('All parameters')
        self.only_symbol.setChecked(True)
        grp = QButtonGroup(self); grp.addButton(self.only_symbol); grp.addButton(self.all_params)
        left.addWidget(self.only_symbol); left.addWidget(self.all_params)
        self.avail = QListWidget()
        self.avail.setSelectionMode(QListWidget.ExtendedSelection)
        self.avail.itemDoubleClicked.connect(lambda _: self._add())
        self.avail.itemSelectionChanged.connect(self._update_buttons)
        self.only_symbol.toggled.connect(lambda _: self._fill_avail())
        left.addWidget(self.avail)
        body.addLayout(left, 1)
        mid = QVBoxLayout(); mid.addStretch(1)
        self.buttons = {}
        for text, slot in (('<< Clear', self._clear), ('<< Remove', self._remove), ('Add >>', self._add_clicked),
                           ('Add All >>', self._add_all)):
            b = QPushButton(text); b.clicked.connect(slot); mid.addWidget(b); self.buttons[text] = b
        self.buttons['Add >>'].setToolTip('Shift+Add adds all parameters')
        mid.addStretch(1)
        body.addLayout(mid)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['Name', 'Value'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        for p in inst.params:
            self._row(p.name, p.value)
        body.addWidget(self.table, 1)
        v.addLayout(body)
        self._fill_avail()
        items['parameters'] = self.add_page('Parameters', 'Component Parameters', w)

        # Text Visibility
        self.text_page = TextVisibilityPage(inst, 'Port', 'my_port', inst.show_params)
        self.show_params = self.text_page.show_params
        items['visibility'] = self.add_page('Text Visibility', 'Component Text Visibility', self.text_page)

        # PortMap Frame
        w = QWidget(); v = QVBoxLayout(w)
        box = QGroupBox('Port Map Frame'); g = QVBoxLayout(box)
        row = QHBoxLayout()
        self.pm_enable = QCheckBox('Enable Port Map Frame'); self.pm_enable.setChecked(inst.portmap_frame)
        by_name = QCheckBox('Connection By Name'); by_name.setEnabled(False)
        row.addWidget(self.pm_enable); row.addStretch(1); row.addWidget(by_name); row.addStretch(1)
        g.addLayout(row)
        lists = QHBoxLayout()
        self.pm_auto = QPlainTextEdit(); self.pm_auto.setReadOnly(True)
        self.pm_auto.setToolTip('Mapping made by the nets drawn on the diagram')
        self.pm_auto.setPlainText(',\n'.join(f'.{p}({n})' for p, n in connections or []))
        self.pm_text = QPlainTextEdit()
        self.pm_text.setToolTip('Explicit mapping of unconnected ports, e.g. .port_a(expr), .port_b(1\'b0)')
        free = [p.name for p in sorted(inst.pins, key=lambda p: p.order) if not p.net]
        self.pm_text.setPlainText(inst.portmap_text or ',\n'.join(f'.{n}()' for n in free))
        for e in (self.pm_auto, self.pm_text):
            e.setFont(QFont('Courier New', 9))
            e.setLineWrapMode(QPlainTextEdit.NoWrap)
        lists.addWidget(self.pm_auto); lists.addWidget(self.pm_text)
        g.addLayout(lists)
        self.pm_enable.toggled.connect(self.pm_text.setEnabled)
        self.pm_text.setEnabled(inst.portmap_frame)
        v.addWidget(box)
        items['portmap'] = self.add_page('PortMap Frame', 'Port Map Frame', w)

        # Attributes
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(_desc('Enter embedded synthesis constraints relating to this signal/port/block/component as '
                          'Verilog comments.\nThis text will be inserted into the generated HDL.'))
        self.attrs = QPlainTextEdit(inst.attributes or ATTRIBUTE_TEMPLATE)
        self.attrs.setFont(QFont('Courier New', 9))
        v.addWidget(self.attrs, 1)
        items['attributes'] = self.add_page('Attributes', 'Attributes', w)

        # Appearance
        self.look = AppearancePage(inst, ['rectangle'])
        items['appearance'] = self.add_page('Appearance', 'Edit Appearance', self.look)
        self.show_page(items.get(page, items['component']))

    def _row(self, name: str, value: str):
        """Append an overridden parameter (name read-only, value editable) to the table."""
        r = self.table.rowCount()
        self.table.insertRow(r)
        it = QTableWidgetItem(name)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(r, 0, it)
        self.table.setItem(r, 1, QTableWidgetItem(value))

    def _names(self) -> set[str]:
        """Names of the parameters overridden in the table."""
        return {self.table.item(r, 0).text() for r in range(self.table.rowCount())}

    def _fill_avail(self):
        """Parameters not overridden yet (overridden ones are in the table on the right)."""
        have = self._names()
        rows = self.param_sets['symbol' if self.only_symbol.isChecked() else 'all']
        self.avail.clear()
        for n, d in rows:
            if n in have:
                continue
            it = QListWidgetItem(f'{n}   {d}')          # as the legacy list shows them
            it.setData(Qt.UserRole, (n, d))
            self.avail.addItem(it)
        self._update_buttons()

    def _update_buttons(self):
        """Enable Add / Add All / Remove / Clear according to the lists' contents and selections."""
        self.buttons['Add >>'].setEnabled(bool(self.avail.selectedItems()))
        self.buttons['Add All >>'].setEnabled(self.avail.count() > 0)
        self.buttons['<< Remove'].setEnabled(bool(self.table.selectedItems()))
        self.buttons['<< Clear'].setEnabled(self.table.rowCount() > 0)

    def _add_clicked(self):
        """Add >> (Shift+click adds all, as in the legacy tool)."""
        from PySide6.QtWidgets import QApplication
        if QApplication.keyboardModifiers() & Qt.ShiftModifier:
            return self._add_all()
        self._add()

    def _add(self):
        """Override the selected available parameters (with their default values)."""
        have = self._names()
        for it in self.avail.selectedItems():
            n, d = it.data(Qt.UserRole)
            if n not in have:
                self._row(n, d)
        self._fill_avail()

    def _add_all(self):
        """Override every available parameter."""
        have = self._names()
        for i in range(self.avail.count()):
            n, d = self.avail.item(i).data(Qt.UserRole)
            if n not in have:
                self._row(n, d)
        self._fill_avail()

    def _remove(self):
        """Stop overriding the selected parameters."""
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)
        self._fill_avail()

    def _clear(self):
        """Stop overriding every parameter."""
        self.table.setRowCount(0)
        self._fill_avail()

    def apply(self):
        """Write every page into the instance: name and visibility, parameter overrides, text
        visibility, port map frame, attributes (the untouched template counts as none), appearance.
        """
        i = self.inst
        i.name = self.name.text().strip() or i.name
        i.show_library = self.lib_vis.isChecked()
        i.show_instance = self.name_vis.isChecked()
        i.params = [Parameter(self.table.item(r, 0).text(), (self.table.item(r, 1).text() if self.table.item(r, 1)
                                                               else '').strip())
                    for r in range(self.table.rowCount())]
        i.show_params = self.text_page.show_params.isChecked()
        self.text_page.apply()
        i.portmap_frame = self.pm_enable.isChecked()
        i.portmap_text = self.pm_text.toPlainText().strip()
        text = self.attrs.toPlainText().strip()
        i.attributes = '' if text == ATTRIBUTE_TEMPLATE.strip() else text
        self.look.apply()
        super().apply()


class PortIoPropertiesDialog(ObjectPropertiesDialog):
    """BD Object Properties for a PortIO: mode, Text Visibility and Appearance pages."""

    def __init__(self, pio, page: str = 'mode', parent=None):
        """Build the Port IO (mode), Text Visibility and Appearance pages for `pio`."""
        super().__init__('PortIOs', parent)
        self.pio = pio
        items = {}
        w = QWidget(); v = QVBoxLayout(w)
        box = QGroupBox('PortIO mode settings'); g = QVBoxLayout(box)
        self.modes = {}
        for text, mode in (('In', 'input'), ('Out', 'output'), ('InOut', 'inout')):
            r = QRadioButton(text); r.setChecked(pio.mode == mode); g.addWidget(r); self.modes[mode] = r
        g.addStretch(1)
        v.addWidget(box); v.addStretch(1)
        items['mode'] = self.add_page('PortIOs', 'Port IO', w, child=False)
        self.text_page = TextVisibilityPage(pio, 'PortIO', 'my_portIo', name_attr='show_text')
        items['visibility'] = self.add_page('Text Visibility', 'Text Visibility', self.text_page)
        self.look = AppearancePage(pio)
        items['appearance'] = self.add_page('Appearance', 'Edit Appearance', self.look)
        self.show_page(items.get(page, items['mode']))

    def mode(self) -> str:
        """The mode chosen ('input', 'output' or 'inout'); the editor applies it (it may redraw the port)."""
        return next(m for m, r in self.modes.items() if r.isChecked())

    def apply(self):
        """Write the text visibility and appearance pages into the port."""
        self.text_page.apply()
        self.look.apply()
        super().apply()


def _split_range(b: str) -> tuple[str, str]:
    """"[msb:lsb]" -> ('msb', 'lsb'); ('', '') when the text is not a range."""
    m = re.fullmatch(r'\s*\[\s*(.*?)\s*:\s*(.*?)\s*\]\s*', b or '')
    return (m.group(1), m.group(2)) if m else ('', '')


class SignalPropertiesDialog(QDialog):
    """"BD Object Properties - Verilog Signals" for one net."""

    def __init__(self, sig: Signal, parent=None):
        """Build the dialog from net `sig` (its Signal: name, type, bounds, array, delay, ...)."""
        super().__init__(parent)
        self.setWindowTitle('BD Object Properties - Signals')
        self.sig = sig
        use = QGroupBox('Use'); f = QFormLayout(use)
        style = QHBoxLayout()
        self.r_sig = QRadioButton('Signal'); self.r_bus = QRadioButton('Bus')
        (self.r_bus if sig.bounds else self.r_sig).setChecked(True)
        style.addWidget(self.r_sig); style.addWidget(self.r_bus); style.addStretch(1)
        f.addRow('Style:', style)
        self.name = QLineEdit(sig.name)
        f.addRow('Name:', self.name)
        decl = QGroupBox('Declaration'); g = QFormLayout(decl)
        row = QHBoxLayout()
        self.type = QComboBox(); self.type.setEditable(True); self.type.addItems(NET_TYPES)
        self.type.setCurrentText(sig.type or 'wire')
        self.signed = QCheckBox('Signed'); self.signed.setChecked(sig.signed)
        row.addWidget(self.type, 1); row.addWidget(self.signed)
        g.addRow('Type:', row)
        self.vmsb, self.vlsb = (QLineEdit(x) for x in _split_range(sig.bounds))
        self.amsb, self.alsb = (QLineEdit(x) for x in _split_range(sig.array))
        for label, a, b in (('Vector Bounds:', self.vmsb, self.vlsb), ('Array Bounds:', self.amsb, self.alsb)):
            r = QHBoxLayout(); r.addWidget(a); r.addWidget(QLabel(':')); r.addWidget(b)
            g.addRow(label, r)
        self.delay = QLineEdit(sig.delay)
        self.value = QLineEdit(sig.value)
        g.addRow('Delay #', self.delay)
        g.addRow('Value:', self.value)
        self.expansion = QComboBox(); self.expansion.addItems(['NOT-SET', 'scalared', 'vectored'])
        self.expansion.setCurrentText(sig.expansion or 'NOT-SET')
        g.addRow('Expansion:', self.expansion)
        self.strength = QComboBox(); self.strength.addItems(['NOT-SET', 'small', 'medium', 'large'])
        self.strength.setCurrentText(sig.strength or 'NOT-SET')
        g.addRow('Charge Strength:', self.strength)
        self.comment = QLineEdit(sig.comment)
        g.addRow('Comment:', self.comment)
        self.type.currentTextChanged.connect(self._type_changed)
        self._type_changed(self.type.currentText())
        self.r_sig.toggled.connect(lambda on: (self.vmsb.setEnabled(not on), self.vlsb.setEnabled(not on)))
        self.vmsb.setEnabled(self.r_bus.isChecked()); self.vlsb.setEnabled(self.r_bus.isChecked())
        scope = QGroupBox('Apply changes to'); sl = QVBoxLayout(scope)
        for text, enabled in (('Joined wires in this diagram', False), ('Entire net in diagram', True),
                              ('Entire net in hierarchy', False)):
            r = QRadioButton(text); r.setEnabled(enabled); r.setChecked(enabled)
            if not enabled:
                r.setToolTip('Not available in this version: a net is edited as a whole in this diagram')
            sl.addWidget(r)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(use); lay.addWidget(decl); lay.addWidget(scope); lay.addWidget(bb)
        self.resize(560, 420)

    def _type_changed(self, t: str):
        """Enable only the fields that apply to the chosen net / variable type."""
        # as in the legacy dialog: no delay/expansion for variables, charge strength only for trireg
        variable = t.strip() in ('reg', 'logic', 'integer', 'time', 'real', 'realtime')
        self.delay.setEnabled(not variable)
        self.expansion.setEnabled(not variable)
        self.strength.setEnabled(t.strip() == 'trireg')

    def values(self) -> dict:
        """The dialog's fields as Signal attribute values (bounds / array built from msb / lsb)."""
        vb = f'[{self.vmsb.text().strip()}:{self.vlsb.text().strip()}]' \
            if self.r_bus.isChecked() and self.vmsb.text().strip() else ''
        ab = f'[{self.amsb.text().strip()}:{self.alsb.text().strip()}]' if self.amsb.text().strip() else ''
        return dict(name=self.name.text().strip(), type=self.type.currentText().strip() or 'wire',
                    signed=self.signed.isChecked(), bounds=vb, array=ab, delay=self.delay.text().strip(),
                    value=self.value.text().strip(), comment=self.comment.text().strip(),
                    expansion='' if not self.expansion.isEnabled() or self.expansion.currentIndex() == 0
                    else self.expansion.currentText(),
                    strength='' if not self.strength.isEnabled() or self.strength.currentIndex() == 0
                    else self.strength.currentText())


class FramePropertiesDialog(QDialog):
    """"BD Object Properties - Frames", laid out as in the legacy editor: the object
    categories on the left (only Frames applies here), the frame page on the right."""

    CATEGORIES = ['Components', 'Blocks', 'Embedded Blocks', 'ModuleWare', 'ExternalIPs', 'Signals', 'Bundles',
                  'PortIOs', 'Frames', 'Comment Text', 'Requirement Reference', 'Comment Graphics',
                  'User Declarations', 'User Properties']

    def __init__(self, frame, if_names: list[str], parent=None, apply=None):
        """Build the dialog for `frame`; `if_names` are the IF frame labels offered for an ELSE frame,
        `apply(values)` is called by the Apply button.
        """
        super().__init__(parent)
        self.setWindowTitle('BD Object Properties - Frames')
        self._apply_cb = apply
        tree = QTreeWidget(); tree.setHeaderHidden(True); tree.setMaximumWidth(190)
        for name in self.CATEGORIES:
            it = QTreeWidgetItem(tree, [name])
            if name == 'Frames':
                QTreeWidgetItem(it, ['Appearance']).setDisabled(True)
                it.setExpanded(True)
                tree.setCurrentItem(it)
            else:
                it.setDisabled(True)

        page = QWidget(); f = QFormLayout(page)
        self.style = QComboBox(); self.style.addItems(['FOR', 'IF', 'ELSE'])
        self.style.setCurrentText(frame.kind.upper())
        f.addRow('Frame Style:', self.style)
        row = QHBoxLayout()
        self.label = QComboBox(); self.label.setEditable(True)
        self.label.addItems(sorted(set(if_names) | {frame.name}))
        self.label.setCurrentText(frame.name)
        self.label_vis = QCheckBox('Visible'); self.label_vis.setChecked(frame.show_label)
        row.addWidget(self.label, 1); row.addWidget(self.label_vis)
        f.addRow('Label:', row)
        row = QHBoxLayout()
        self.number = QLineEdit(str(frame.number))
        self.number_vis = QCheckBox('Visible'); self.number_vis.setChecked(frame.show_number)
        row.addWidget(self.number, 1); row.addWidget(self.number_vis)
        f.addRow('Number:', row)

        self.for_box = QGroupBox('Repeating Instance (FOR) Expression'); g = QHBoxLayout(self.for_box)
        left, right = frame.range() if frame.kind == 'for' else ('', '0')
        self.left, self.right = QLineEdit(left), QLineEdit(right)
        g.addWidget(QLabel('Range:')); g.addWidget(self.left, 2); g.addWidget(QLabel(':')); g.addWidget(self.right, 1)
        self.if_box = QGroupBox('Conditional Instance (IF) Expression'); g = QHBoxLayout(self.if_box)
        self.cond = QLineEdit(frame.spec if frame.kind == 'if' else '')
        self.cond.setPlaceholderText('`ifdef MACRO  or  (expression)')
        g.addWidget(QLabel('Condition:')); g.addWidget(self.cond, 1)
        self.else_box = QGroupBox('Alternative (ELSE)'); g = QHBoxLayout(self.else_box)
        g.addWidget(QLabel('Used when the IF frame with the same label is not selected.'))
        f.addRow(self.for_box); f.addRow(self.if_box); f.addRow(self.else_box)
        self.style.currentTextChanged.connect(self._style_changed)
        self._style_changed(self.style.currentText())

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
                              | QDialogButtonBox.Help)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Apply).clicked.connect(lambda: self._apply_cb and self._apply_cb(self.values()))
        bb.button(QDialogButtonBox.Help).setEnabled(False)
        body = QHBoxLayout(); body.addWidget(tree); body.addWidget(page, 1)
        lay = QVBoxLayout(self); lay.addLayout(body, 1); lay.addWidget(bb)
        self.resize(680, 380)

    def _style_changed(self, style: str):
        """Show the expression box of the chosen frame style."""
        self.for_box.setVisible(style == 'FOR')
        self.if_box.setVisible(style == 'IF')
        self.else_box.setVisible(style == 'ELSE')

    def values(self) -> dict:
        """The frame attributes chosen (kind, name, spec, number, label / number visibility)."""
        kind = self.style.currentText().lower()
        if kind == 'for':
            spec = f'[{self.left.text().strip() or "0"}:{self.right.text().strip() or "0"}]'
        elif kind == 'if':
            spec = self.cond.text().strip()
        else:
            spec = '`else'
        num = self.number.text().strip()
        return dict(kind=kind, name=self.label.currentText().strip(), spec=spec,
                    number=int(num) if num.isdigit() else 1, show_label=self.label_vis.isChecked(),
                    show_number=self.number_vis.isChecked())


def library_of_file(project, path: str, fallback: str) -> str:
    """Library whose HDL folder holds `path` (directly or in a sub-folder)."""
    if project is not None:
        for lib in project.libraries:
            if lib.owns(path):
                return lib.name
    return fallback


class _SmallDialog(QDialog):
    """A legacy one-page dialog: `page` above OK / Cancel (/ Apply / Help). `applied` is True once OK or
    Apply wrote the page into its object; `on_apply` is called then (the editor redraws)."""

    def __init__(self, title: str, page: QWidget, parent=None, apply_button: bool = True, on_apply=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.page, self.applied, self.on_apply = page, False, on_apply
        buttons = QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        if apply_button:
            buttons |= QDialogButtonBox.Apply | QDialogButtonBox.Help
        bb = QDialogButtonBox(buttons)
        bb.accepted.connect(lambda: (self._apply(), self.accept()))
        bb.rejected.connect(self.reject)
        if apply_button:
            bb.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
            bb.button(QDialogButtonBox.Help).setEnabled(False)
        lay = QVBoxLayout(self)
        lay.addWidget(page, 1)
        lay.addWidget(bb)

    def _apply(self):
        self.page.apply()
        self.applied = True
        if self.on_apply is not None:
            self.on_apply()


def edit_appearance_dialog(obj, parent=None, on_apply=None) -> QDialog:
    """Appearance... of a component or PortIO popup menu: the legacy "Edit Appearance" dialog (colours,
    fill / line style and width, and the Font box, greyed: the diagram font is fixed)."""
    page = AppearancePage(obj)
    font = QGroupBox('Font'); h = QHBoxLayout(font)
    name = QLineEdit(); name.setEnabled(False); h.addWidget(name, 1)
    b = QPushButton('Set...'); b.setEnabled(False); h.addWidget(b)
    page.layout().insertWidget(1, font)
    dlg = _SmallDialog('Edit Appearance', page, parent, on_apply=on_apply)
    dlg.resize(490, 257)
    return dlg


def port_display_dialog(inst, parent=None, on_apply=None) -> QDialog:
    """Port Visibility... of the component popup menu: the legacy "Port Display Control" dialog (the
    fields shown next to every port of the component)."""
    page = TextVisibilityPage(inst, 'Port', 'my_port')
    dlg = _SmallDialog('Port Display Control', page, parent, apply_button=False, on_apply=on_apply)
    dlg.resize(437, 423)
    return dlg


class EmbeddedPropertiesDialog(ObjectPropertiesDialog):
    """BD Object Properties for an embedded block, as the legacy tool: the Embedded Block page (name and number,
    each with Visible, Show Ports when connected) and the Text page (its HDL). Text Appearance, Text Box
    Appearance and Block Appearance are listed greyed: HDL Studio draws embedded blocks in fixed colours."""

    def __init__(self, eb, parent=None):
        super().__init__('Embedded Blocks', parent)
        self.eb = eb
        w = QWidget()
        v = QVBoxLayout(w)
        box = QGroupBox('Embedded Block')
        f = QFormLayout(box)
        self.name = QLineEdit(eb.name)
        self.name_visible = QCheckBox('Visible')
        self.name_visible.setChecked(eb.show_name)
        row = QHBoxLayout(); row.addWidget(self.name, 1); row.addWidget(self.name_visible)
        f.addRow('Name:', row)
        self.number = QLineEdit(str(eb.number))
        num_visible = QCheckBox('Visible')
        num_visible.setChecked(eb.show_name)
        num_visible.setEnabled(False)           # shown together with the name in HDL Studio
        self.name_visible.toggled.connect(num_visible.setChecked)
        row = QHBoxLayout(); row.addWidget(self.number, 1); row.addWidget(num_visible)
        f.addRow('Number:', row)
        ports = QCheckBox('Show Ports when connected')
        ports.setChecked(True)
        ports.setEnabled(False)
        f.addRow(ports)
        v.addWidget(box)
        v.addStretch(1)
        first = self.add_page('', 'Embedded Blocks', w, child=False)
        t = QWidget()
        tv = QVBoxLayout(t)
        self.text = QPlainTextEdit(eb.text.strip('\n'))
        self.text.setFont(QFont('Courier New', 9))
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        tv.addWidget(self.text)
        self.add_page('Text', 'Embedded Text', t)
        for label in ('Text Appearance', 'Text Box Appearance', 'Block Appearance'):
            QTreeWidgetItem(self.category_item, [label]).setDisabled(True)
        self.show_page(first)
        self.resize(671, 543)

    def apply(self):
        """Name (kept when empty), number, name visibility and the text."""
        eb = self.eb
        if self.name.text().strip():
            eb.name = self.name.text().strip()
        if self.number.text().strip().isdigit():
            eb.number = int(self.number.text().strip())
        eb.show_name = self.name_visible.isChecked()
        if self.text.toPlainText() != eb.text.strip('\n'):
            eb.text = self.text.toPlainText()
        super().apply()
