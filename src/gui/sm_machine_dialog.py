"""State Machine Properties and Verilog Compiler Directives: the machine-level dialogs of the
legacy state diagram editor (Diagram > State Machine Properties..., Diagram > Compiler
Directives..., the diagram's popup menu, a double-click on a declaration block), laid out as
The legacy tool shows them on gc_control_fsm.

State Machine Properties: a page tree on the left, the page on the right, OK / Cancel / Apply /
Help under them. The title names the page and, for the pages of one machine, the machine:
"State Machine Properties - Encoding (dram_control_fsm)".

    State Machine             Concurrent Machine Name
      Generation              Machine (Synchronous / Asynchronous, Prop Delay), Generation Style
                              (1 / 2 / 3 Always Blocks, If / One-Hot / Case, Output Encoded, ...),
                              Register state actions on next state, Default State Assignment,
                              Full/Parallel Case Pragmas, Assignment type
        Advanced              State Signal Names (Current / Next State Name), State Variable,
                              animation / interrupt / reset pragma / delay options, Wait State Settings...
      Encoding                Scheme, Pragma, Style (Sequential, 1-Hot, 2-Hot, Gray, Johnson,
                              Manual), the encoding table (State Name | <style>, "n states" / "k bits")
      Statement Blocks        Concurrent Statements, State Register Statements, Global Actions
                              (Pre / Post Actions), each with Visible
      Declaration Blocks      Module Declarations (Visible)
        Pre/Post User Declarations
      Internal Signals        Prefix / Suffix, Registered / Clocked / Gated clock Affix

What HDL Studio keeps (and writes back to the .sm) is editable: the state signal names, the
encoding style and manual codes, the statement block texts, which blocks are shown, the
registered / clocked affixes. Everything else is shown as the legacy tool shows it for this machine but
disabled: HDL Studio generates one style (synchronous, 3 always blocks, case) and has no place
for those options yet.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QGridLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QRadioButton, QStackedWidget, QStyle, QTableWidget, QTableWidgetItem,
                               QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from codegen.encoding import encode
from model import FsmView, Machine

MONO = QFont('Courier New', 9)

# page key, label, parent key (None: top level), title shows the machine name
PAGES = [
    ('machine', 'State Machine', None, False),
    ('generation', 'Generation', 'machine', True),
    ('advanced', 'Advanced', 'generation', True),
    ('encoding', 'Encoding', 'machine', True),
    ('statements', 'Statement Blocks', 'machine', True),
    ('declarations', 'Declaration Blocks', 'machine', False),
    ('user_decls', 'Pre/Post User Declarations', 'declarations', False),
    ('internal', 'Internal Signals', 'machine', True),
]
# Encoding > Style radio buttons as the legacy tool places them (row, column) -> HDL Studio encoding style;
# None: a style HDL Studio does not generate (shown disabled)
ENC_STYLES = [('Sequential', 'sequential', 0, 0), ('1-Hot', 'onehot', 0, 1), ('2-Hot', None, 1, 0),
              ('Gray', 'gray', 1, 1), ('Johnson', 'johnson', 2, 0), ('Manual', 'manual', 2, 1)]
ENC_HEADER = QColor(140, 196, 222)        # the "n states / k bits" row of the encoding table
ENC_NAME = QColor(212, 208, 200)          # the State Name column


def _text_box() -> QPlainTextEdit:
    """A monospaced, non-wrapping text box."""
    t = QPlainTextEdit()
    t.setFont(MONO)
    t.setLineWrapMode(QPlainTextEdit.NoWrap)
    return t


def _off(w):
    """A control the legacy tool has and HDL Studio does not keep yet: shown, not editable."""
    w.setEnabled(False)
    return w


def _editor_button() -> QToolButton:
    """The legacy tool's small "edit in the text editor" button next to each text; not in HDL Studio yet."""
    b = QToolButton()
    b.setIcon(b.style().standardIcon(QStyle.SP_FileDialogDetailedView))
    b.setToolTip('Edit in a text editor (not in HDL Studio yet)')
    return _off(b)


def _caption_row(caption: str, visible: QCheckBox | None) -> QHBoxLayout:
    """A text's caption, then (right) its Visible box and the editor button, as the legacy tool lays them."""
    row = QHBoxLayout()
    row.addWidget(QLabel(caption))
    row.addStretch(1)
    if visible is not None:
        row.addWidget(visible)
    row.addWidget(_editor_button())
    return row


def _code_digits(code: str) -> str:
    """5'b00010 -> 00010, 5'd3 -> 00011: the legacy tool shows a state's code as its bits only."""
    if "'d" in code:
        width, value = code.split("'d", 1)
        try:
            return f'{int(value):0{int(width)}b}'
        except ValueError:
            return code
    return code.split("'b", 1)[1] if "'b" in code else code


class StateMachinePropertiesDialog(QDialog):
    """`view` / `machine` are changed only by Apply / OK (`applied` is then True); Cancel leaves
    them as they were. `readonly`: the fields are shown, OK / Apply only close."""

    def __init__(self, view: FsmView, machine: Machine, parent=None, page: str = 'generation',
                 readonly: bool = False):
        """Build the page tree and every page (PAGES order), the buttons, and open on `page`."""
        super().__init__(parent)
        self.view, self.machine = view, machine
        self.readonly = readonly
        self.applied = False
        self.resize(710, 483)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFixedWidth(204)
        self.pages = QStackedWidget()
        items: dict[str, QTreeWidgetItem] = {}
        self._page_of: dict[str, QWidget] = {}
        builders = {'machine': self._machine_page, 'generation': self._generation_page,
                    'advanced': self._advanced_page, 'encoding': self._encoding_page,
                    'statements': self._statements_page, 'declarations': self._declarations_page,
                    'user_decls': self._user_decls_page, 'internal': self._internal_page}
        for key, label, parent_key, _ in PAGES:
            it = QTreeWidgetItem(items[parent_key] if parent_key else self.tree, [label])
            it.setData(0, Qt.UserRole, key)
            items[key] = it
            w = builders[key]()
            self.pages.addWidget(w)
            self._page_of[key] = w
        self.tree.expandAll()
        self.tree.currentItemChanged.connect(lambda cur, _old: cur and self.show_page(cur.data(0, Qt.UserRole)))
        self._items = items

        body = QHBoxLayout()
        body.addWidget(self.tree)
        body.addWidget(self.pages, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for text, slot in (('OK', self._ok), ('Cancel', self.reject), ('Apply', self.apply), ('Help', None)):
            b = QPushButton(text)
            b.setMinimumWidth(75)
            if slot is None:
                b.setEnabled(False)
            else:
                b.clicked.connect(slot)
            if text == 'OK':
                b.setDefault(True)
            if text == 'Apply' and readonly:
                b.setEnabled(False)
            buttons.addWidget(b)
        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addLayout(buttons)
        if readonly:
            for w in self._editable:
                w.setEnabled(False)
        self.tree.setCurrentItem(items.get(page, items['generation']))
        self.show_page(page if page in items else 'generation')

    def show_page(self, key: str):
        """Show page `key` and put its name (and the machine's, for machine pages) in the title."""
        self.pages.setCurrentWidget(self._page_of[key])
        label, named = next((l, n) for k, l, _p, n in PAGES if k == key)
        title = 'State Machine Properties' if key == 'machine' else f'State Machine Properties - {label}'
        self.setWindowTitle(f'{title} ({self.machine.name})' if named else title)
        if self.tree.currentItem() is not self._items[key]:
            self.tree.setCurrentItem(self._items[key])

    # the controls HDL Studio keeps (disabled in a read-only diagram)
    @property
    def _editable(self) -> list:
        """The controls HDL Studio keeps (disabled in a read-only diagram)."""
        return [self.cur_name, self.next_name, *self.enc_buttons.values(), self.enc_table, self.conc,
                self.conc_vis, self.sreg, self.sreg_vis, self.glob_vis, self.pre_act, self.post_act,
                self.module_vis, self.reg_affix, self.clk_affix]

    # -- pages --------------------------------------------------------------------------
    def _machine_page(self) -> QWidget:
        """State Machine page: the concurrent machine name (shown, not editable)."""
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel('Concurrent Machine Name:'))
        # renamed with Diagram > Rename Concurrent Machine... in the legacy tool; not in HDL Studio yet
        row.addWidget(_off(QLineEdit(self.machine.name)), 1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    def _generation_page(self) -> QWidget:
        """Generation page: the legacy tool's machine / style / pragma options, shown disabled (HDL Studio generates
        one style: synchronous, 3 always blocks, case).
        """
        w = QWidget()
        lay = QVBoxLayout(w)
        mach = QGroupBox('Machine')
        g = QGridLayout(mach)
        sync = _off(QRadioButton('Synchronous')); sync.setChecked(True)
        g.addWidget(sync, 0, 0)
        g.addWidget(_off(QRadioButton('Asynchronous')), 1, 0)
        g.addWidget(_off(QLabel('Prop Delay:')), 1, 1)
        g.addWidget(_off(QLineEdit()), 1, 2)
        g.setColumnStretch(2, 1)
        lay.addWidget(mach)
        style = QGroupBox('Generation Style')
        g = QGridLayout(style)
        blocks, kinds = QButtonGroup(style), QButtonGroup(style)
        for r, text in enumerate(('1 Always Block', '2 Always Blocks', '3 Always Blocks')):
            b = _off(QRadioButton(text)); b.setChecked(r == 2); blocks.addButton(b); g.addWidget(b, r, 0)
        for r, text in enumerate(('If', 'One-Hot', 'Case')):
            b = _off(QRadioButton(text)); b.setChecked(r == 2); kinds.addButton(b); g.addWidget(b, r, 1)
        case = _off(QComboBox()); case.addItem('case')
        g.addWidget(case, 2, 2)
        g.addWidget(_off(QCheckBox('Output Encoded')), 3, 0, 1, 2)
        local = _off(QCheckBox('Use Local signals in encoding'))
        local.setContentsMargins(18, 0, 0, 0)
        g.addWidget(local, 4, 0, 1, 2)
        g.setColumnStretch(2, 1)
        lay.addWidget(style)
        reg = _off(QCheckBox('Register state actions on next state'))
        reg.setChecked(self.machine.next_state_clocking)
        lay.addWidget(reg)
        lay.addWidget(_off(QCheckBox('Default State Assignment')))
        row = QHBoxLayout()
        row.addWidget(_off(QCheckBox('Full/Parallel Case Pragmas')))
        prag = _off(QComboBox()); prag.addItem('// pragma parallel_case full_case')
        row.addWidget(prag, 1)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel('Assignment type:'))
        assign = _off(QComboBox()); assign.addItem('Mixed')
        row.addWidget(assign, 1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    def _advanced_page(self) -> QWidget:
        """Advanced page: the editable current / next state signal names, the other options disabled."""
        w = QWidget()
        lay = QVBoxLayout(w)
        names = QGroupBox('State Signal Names')
        g = QGridLayout(names)
        # The legacy tool leaves the boxes empty for the default names; HDL Studio shows them as hints
        self.cur_name = QLineEdit('' if self.machine.current_state_name == 'current_state'
                                  else self.machine.current_state_name)
        self.cur_name.setPlaceholderText('current_state')
        self.next_name = QLineEdit('' if self.machine.next_state_name == 'next_state'
                                   else self.machine.next_state_name)
        self.next_name.setPlaceholderText('next_state')
        g.addWidget(QLabel('Current State Name:'), 0, 0); g.addWidget(self.cur_name, 0, 1)
        g.addWidget(QLabel('Next State Name:'), 1, 0); g.addWidget(self.next_name, 1, 1)
        lay.addWidget(names)
        var = QGroupBox('State Variable')
        h = QHBoxLayout(var)
        h.addWidget(_off(QRadioButton('Assign value to output port:')))
        h.addWidget(_off(QComboBox()), 1)
        lay.addWidget(var)
        for text in ('Instrument HDL for animation', 'Generate interrupts as overrides', 'Add Reset Pragma'):
            lay.addWidget(_off(QCheckBox(text)))
        row = QHBoxLayout()
        row.addWidget(_off(QCheckBox('Use delay for current state assign:')))
        row.addWidget(_off(QLineEdit('0')), 1)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(_off(QPushButton('Wait State Settings...')))
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    def _encoding_page(self) -> QWidget:
        """Encoding page: style radio buttons and the encoding table (filled by _fill_encoding)."""
        w = QWidget()
        lay = QHBoxLayout(w)
        left = QVBoxLayout()
        scheme = QGroupBox('Scheme')
        sl = QVBoxLayout(scheme)
        spec = _off(QRadioButton('Specified')); spec.setChecked(True)
        sl.addWidget(spec)
        sl.addWidget(_off(QRadioButton('Auto')))
        sl.addWidget(_off(QCheckBox('Pragma')))
        prag = _off(QComboBox()); prag.addItem('syn_encoding')
        sl.addWidget(prag)
        left.addWidget(scheme)
        style = QGroupBox('Style')
        g = QGridLayout(style)
        self.enc_group = QButtonGroup(style)
        self.enc_buttons: dict[str, QRadioButton] = {}
        for text, key, r, c in ENC_STYLES:
            b = QRadioButton(text)
            if key is None:
                _off(b)
            else:
                self.enc_buttons[key] = b
                b.toggled.connect(lambda on, k=key: on and self._fill_encoding(k))
            self.enc_group.addButton(b)
            g.addWidget(b, r, c)
        left.addWidget(style)
        for text in ('Parameter Declaration Range', 'Add state vector pragma', 'Add syn_preserve pragma'):
            left.addWidget(_off(QCheckBox(text)))
        left.addStretch(1)
        lay.addLayout(left)
        box = QGroupBox('Encoding')
        bl = QVBoxLayout(box)
        self.enc_table = QTableWidget(0, 2)
        self.enc_table.verticalHeader().hide()
        self.enc_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.enc_table.setSelectionMode(QAbstractItemView.SingleSelection)
        bl.addWidget(self.enc_table)
        lay.addWidget(box, 1)
        # per-state codes typed in Manual style (kept while the dialog is open)
        self._manual = {s.name: _code_digits(s.encoding) for s in self.machine.states}
        style_now = self.machine.encoding if self.machine.encoding in self.enc_buttons else 'sequential'
        self.enc_buttons[style_now].setChecked(True)
        self._fill_encoding(style_now)
        return w

    def _enc_style(self) -> str:
        """The encoding style whose radio button is checked."""
        return next((k for k, b in self.enc_buttons.items() if b.isChecked()), 'sequential')

    def _fill_encoding(self, style: str):
        """The encoding table for a style: the first row "n states | k bits", then one row per
        state with its code; the codes can be typed in Manual style only."""
        t = self.enc_table
        if t.rowCount() and self._shown_style == 'manual':
            self._keep_manual()
        self._shown_style = style
        names = [s.name for s in self.machine.states]
        manual = {n: c for n, c in self._manual.items() if c} if style == 'manual' else None
        width, codes = encode(names, style, manual) if names else (0, {})
        label = next(text for text, k, _r, _c in ENC_STYLES if k == style)
        t.blockSignals(True)
        t.setHorizontalHeaderLabels(['State Name', label])
        t.setRowCount(len(names) + 1)
        for col, text in enumerate((f'{len(names)} states', f'{width} bits')):
            it = QTableWidgetItem(text)
            it.setFlags(Qt.ItemIsEnabled)
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(QBrush(ENC_HEADER))
            t.setItem(0, col, it)
        for r, n in enumerate(names, start=1):
            it = QTableWidgetItem(n)
            it.setFlags(Qt.ItemIsEnabled)
            it.setBackground(QBrush(ENC_NAME))
            t.setItem(r, 0, it)
            code = self._manual.get(n, '') if style == 'manual' else _code_digits(codes.get(n, ''))
            it = QTableWidgetItem(code)
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            it.setFlags(flags | Qt.ItemIsEditable if style == 'manual' else flags)
            t.setItem(r, 1, it)
        t.blockSignals(False)

    _shown_style = ''

    def _keep_manual(self):
        """Remember the codes typed in the table (Manual style) before the table is refilled."""
        for r in range(1, self.enc_table.rowCount()):
            n, c = self.enc_table.item(r, 0), self.enc_table.item(r, 1)
            if n is not None and c is not None:
                self._manual[n.text()] = c.text().strip()

    def _statements_page(self) -> QWidget:
        """Statement Blocks page: concurrent statements, state register statements, global pre / post
        actions, each with its Visible box.
        """
        w = QWidget()
        lay = QVBoxLayout(w)
        hidden = set(self.view.decl_hidden)
        self.conc_vis = QCheckBox('Visible'); self.conc_vis.setChecked('concurrent' not in hidden)
        lay.addLayout(_caption_row('Concurrent Statements:', self.conc_vis))
        self.conc = _text_box(); self.conc.setPlainText(self.view.concurrent_statements)
        lay.addWidget(self.conc, 1)
        self.sreg_vis = QCheckBox('Visible'); self.sreg_vis.setChecked('statereg' not in hidden)
        lay.addLayout(_caption_row('State Register Statements:', self.sreg_vis))
        self.sreg = _text_box(); self.sreg.setPlainText(self.view.state_register_statements)
        lay.addWidget(self.sreg, 1)
        glob = QGroupBox('Global Actions')
        gl = QVBoxLayout(glob)
        row = QHBoxLayout()
        row.addWidget(QLabel('Location of non-driving actions:'))
        loc = _off(QComboBox()); loc.addItem('Output Process')
        row.addWidget(loc)
        row.addStretch(1)
        self.glob_vis = QCheckBox('Visible'); self.glob_vis.setChecked('global' not in hidden)
        row.addWidget(self.glob_vis)
        gl.addLayout(row)
        gl.addLayout(_caption_row('Pre Actions:', None))
        self.pre_act = _text_box(); self.pre_act.setPlainText(self.view.global_pre_actions)
        gl.addWidget(self.pre_act, 1)
        gl.addLayout(_caption_row('Post Actions:', None))
        self.post_act = _text_box(); self.post_act.setPlainText(self.view.global_post_actions)
        gl.addWidget(self.post_act, 1)
        lay.addWidget(glob, 2)
        return w

    def _declarations_page(self) -> QWidget:
        """Declaration Blocks page: the Visible box of the Module Declarations block."""
        w = QWidget()
        lay = QVBoxLayout(w)
        self.module_vis = QCheckBox('Visible'); self.module_vis.setChecked('module' not in self.view.decl_hidden)
        lay.addLayout(_caption_row('Module Declarations:', self.module_vis))
        # the generated declarations of the module: the legacy tool shows them here, HDL Studio does not yet
        lay.addWidget(_off(_text_box()), 1)
        return w

    def _user_decls_page(self) -> QWidget:
        """Pre/Post User Declarations page (shown as the legacy tool has it, not kept by HDL Studio yet)."""
        w = QWidget()
        lay = QVBoxLayout(w)
        box = QGroupBox('User Declaration')
        bl = QVBoxLayout(box)
        bl.addWidget(QLabel('Pre User Entered Declarations:\nThese declarations will be inserted in the '
                            'generated HDL before\nthe automatically generated declarations for '
                            'signals on the diagram.'))
        bl.addWidget(_off(_text_box()), 1)
        bl.addWidget(QLabel('Post User Entered Declarations:\nThese declarations will be inserted in the '
                            'generated HDL after\nthe automatically generated declarations for '
                            'signals on the diagram.'))
        bl.addWidget(_off(_text_box()), 1)
        lay.addWidget(box)
        return w

    def _internal_page(self) -> QWidget:
        """Internal Signals page: registered / clocked affixes (editable), the rest disabled."""
        w = QWidget()
        lay = QVBoxLayout(w)
        box = QGroupBox('Internal Signal Prefix / Suffix')
        g = QGridLayout(box)
        g.addWidget(QLabel('Affix to be used as :'), 0, 0, 1, 3)
        row = QHBoxLayout()
        row.addWidget(_off(QRadioButton('Prefix')))
        suffix = _off(QRadioButton('Suffix')); suffix.setChecked(True)
        row.addWidget(suffix)
        row.addStretch(1)
        g.addLayout(row, 1, 0, 1, 3)
        self.reg_affix = QLineEdit(self.view.registered_affix)
        self.clk_affix = QLineEdit(self.view.clocked_affix)
        gated = _off(QLineEdit('_gated'))
        for r, (text, edit) in enumerate((('Registered Affix:', self.reg_affix), ('Clocked Affix:', self.clk_affix),
                                          ('Gated clock Affix:', gated)), start=2):
            edit.setFixedWidth(64)
            example = QLabel()
            # "E.g. X_r", following the affix as it is typed
            edit.textChanged.connect(lambda s, lab=example: lab.setText(f'E.g. X{s}'))
            example.setText(f'E.g. X{edit.text()}')
            g.addWidget(QLabel(text), r, 0)
            g.addWidget(edit, r, 1)
            g.addWidget(example, r, 2)
        g.setColumnStretch(2, 1)
        g.addWidget(_off(QCheckBox('Use initial value of original signals')), 5, 0, 1, 3)
        note = QLabel('The affix strings are added to the internal signals representing\nregistered, '
                      'clocked and gated clock signals as a Prefix or Suffix.')
        g.addWidget(note, 6, 0, 1, 3)
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    # -- apply ----------------------------------------------------------------------------
    def apply(self) -> bool:
        """Write the editable fields to the view / machine. Empty names and affixes fall back to
        The legacy tool's defaults (current_state, next_state, _r, _cld)."""
        if self.readonly:
            return True
        v, m = self.view, self.machine
        m.current_state_name = self.cur_name.text().strip() or 'current_state'
        m.next_state_name = self.next_name.text().strip() or 'next_state'
        style = self._enc_style()
        if style == 'manual':
            self._keep_manual()
            for s in m.states:
                s.encoding = self._manual.get(s.name, '')      # the bits; codegen adds the width
        m.encoding = style
        v.concurrent_statements = self.conc.toPlainText()
        v.state_register_statements = self.sreg.toPlainText()
        v.global_pre_actions = self.pre_act.toPlainText()
        v.global_post_actions = self.post_act.toPlainText()
        hidden = [k for k in v.decl_hidden if k not in ('concurrent', 'statereg', 'global', 'module')]
        for key, box in (('concurrent', self.conc_vis), ('statereg', self.sreg_vis), ('global', self.glob_vis),
                         ('module', self.module_vis)):
            if not box.isChecked():
                hidden.append(key)
        v.decl_hidden = hidden
        v.registered_affix = self.reg_affix.text().strip() or '_r'
        v.clocked_affix = self.clk_affix.text().strip() or '_cld'
        self.applied = True
        return True

    def _ok(self):
        """OK: apply, then close."""
        if self.apply():
            self.accept()


class CompilerDirectivesDialog(QDialog):
    """Verilog Compiler Directives (Diagram > Compiler Directives...): Visible, then the Pre- /
    Post- / End-Module Directives texts; OK / Cancel / Help."""

    def __init__(self, view: FsmView, parent=None, readonly: bool = False):
        """Build the dialog from `view`; `readonly` shows the texts without letting them change."""
        super().__init__(parent)
        self.view = view
        self.readonly = readonly
        self.applied = False
        self.setWindowTitle('Verilog Compiler Directives')
        self.resize(421, 557)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel('Compiler Directives:'))
        row.addStretch(1)
        self.visible = QCheckBox('Visible'); self.visible.setChecked('compdir' not in view.decl_hidden)
        row.addWidget(self.visible)
        lay.addLayout(row)
        self.boxes = {}
        for title, attr in (('Pre-Module Directives', 'pre_module_directives'),
                            ('Post-Module Directives', 'post_module_directives'),
                            ('End-Module Directives', 'end_module_directives')):
            g = QGroupBox(title)
            gl = QVBoxLayout(g)
            t = _text_box(); t.setPlainText(getattr(view, attr))
            gl.addWidget(t)
            lay.addWidget(g, 1)
            self.boxes[attr] = t
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for text, slot in (('OK', self._ok), ('Cancel', self.reject), ('Help', None)):
            b = QPushButton(text)
            b.setMinimumWidth(75)
            if slot is None:
                b.setEnabled(False)
            else:
                b.clicked.connect(slot)
            if text == 'OK':
                b.setDefault(True)
            buttons.addWidget(b)
        lay.addLayout(buttons)
        if readonly:
            for w in (self.visible, *self.boxes.values()):
                w.setEnabled(False)

    def _ok(self):
        """Write the three directive texts and the Visible choice into the view, then close."""
        if not self.readonly:
            for attr, t in self.boxes.items():
                setattr(self.view, attr, t.toPlainText())
            hidden = [k for k in self.view.decl_hidden if k != 'compdir']
            if not self.visible.isChecked():
                hidden.append('compdir')
            self.view.decl_hidden = hidden
            self.applied = True
        self.accept()
