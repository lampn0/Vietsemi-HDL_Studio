"""SM Object Properties: the state diagram object dialog of the legacy tool (a double-click on a state
away from its name, on a transition, a junction, a link, the clock or the reset point), laid out
as the legacy tool shows it.

Left, the object categories (Clock, Resets, Enable, States, Transitions, Junctions, Links, Text,
Requirement Reference, User Properties) with their icons. As in the legacy tool, the categories of
the selected objects are enabled, and so are Clock / Resets / Enable when the machine has that
point (they can be looked at whatever is selected); the others are greyed. Right, the page of the
category:
  Clock Point   Name (the clock signal), Edge (Rising / Falling), Condition (the expression);
  Reset Points  Reset Mode, Reset name, Reset Level (Low / High), Priority, Reset Actions;
  States        Number of selected states, Name, State Type, Shape..., outgoing transitions
                Style IF / CASE, Implicit loopback, Entry / State / Exit Actions tabs;
  Transitions   Number of selected transitions, IF Condition, Priority, Actions;
  Junctions     Number of selected junctions, Name, Style AND / IF / CASE, CASE Selector Expression;
  Links         Number of selected links, Modify, Link target;
  User Properties  the Class / Name / Value table (empty: HDL Studio keeps no user properties).
Fields HDL Studio does not keep (state type, shape, loopback, the Visible
boxes...) are shown as the legacy tool has them but disabled. OK applies and closes, Apply
applies, Cancel closes.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal as QtSignal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QRadioButton, QSpinBox, QStackedWidget, QTableWidget, QTabWidget,
                               QVBoxLayout, QWidget)

from model import Junction, Link, Machine, Point, State, Transition

CATEGORIES = ['Clock', 'Resets', 'Enable', 'States', 'Transitions', 'Junctions', 'Links', 'Text',
              'Requirement Reference', 'User Properties']
# the icon of each category (editor_icons keys)
_ICONS = {'Clock': 'clock', 'Resets': 'reset', 'Enable': 'enable', 'States': 'state', 'Transitions': 'transition',
          'Junctions': 'junction_if', 'Links': 'link', 'Text': 'text'}
# the window title of each page ("SM Object Properties - <title>")
_TITLES = {'Clock': 'Clock Point', 'Resets': 'Reset Points'}
MONO = QFont('Courier New', 9)


def _text_box() -> QPlainTextEdit:
    """A monospaced, non-wrapping text box for conditions and actions."""
    t = QPlainTextEdit()
    t.setFont(MONO)
    t.setLineWrapMode(QPlainTextEdit.NoWrap)
    return t


def _visible(checked: bool = True) -> QCheckBox:
    """The legacy tool's "Visible" box: shown as the legacy tool has it, not editable (HDL Studio always
    shows the text)."""
    c = QCheckBox('Visible')
    c.setChecked(checked)
    c.setEnabled(False)
    return c


class SmObjectPropertiesDialog(QDialog):
    applied_changes = QtSignal()        # OK / Apply wrote the fields back: the editor redraws at once
    """The SM Object Properties dialog (see the module docstring). `applied` is True after OK or
    Apply changed the objects, so the editor knows to redraw and record an undo step.
    """
    def __init__(self, machine: Machine, objs: list, parent=None, view=None, readonly: bool = False):
        """Open the dialog on `objs` (the selected objects of `machine`); `view` (the FsmView) gives
        the signals for the Clock and Resets pages. The page shown first is the one of the objects:
        a clock / reset point shows Clock / Resets, else States, Transitions, Junctions or Links.
        `readonly`: a read-only diagram; the dialog shows the objects, OK only closes, Apply is greyed.
        """
        super().__init__(parent)
        self.machine = machine
        self.view = view
        self.objs = objs
        self.applied = False
        self.readonly = readonly
        self.states = [o for o in objs if isinstance(o, State)]
        self.transitions = [o for o in objs if isinstance(o, Transition)]
        self.junctions = [o for o in objs if isinstance(o, Junction)]
        self.links = [o for o in objs if isinstance(o, Link)]
        points = {o.kind for o in objs if isinstance(o, Point)}
        self.resize(580, 495)

        self.cats = QListWidget()
        self.cats.setFixedWidth(150)
        try:
            from .editor_icons import editor_icon
        except ImportError:                     # pragma: no cover - icons are optional
            editor_icon = None
        clock, reset = self._signal('clock'), self._signal('reset')
        has = {'Clock': machine.point('clock') is not None and view is not None,
               'Resets': machine.point('reset') is not None and view is not None,
               'Enable': False,
               'States': bool(self.states), 'Transitions': bool(self.transitions),
               'Junctions': bool(self.junctions), 'Links': bool(self.links),
               'Text': False, 'Requirement Reference': False,
               'User Properties': bool(self.states or self.transitions or self.links)}
        for c in CATEGORIES:
            it = QListWidgetItem(c)
            if editor_icon is not None and c in _ICONS:
                it.setIcon(editor_icon(_ICONS[c]))
            if not has[c]:
                it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            self.cats.addItem(it)

        self.pages = QStackedWidget()
        self.page_of: dict[str, QWidget] = {}
        builders = {'Clock': self._clock_page, 'Resets': self._reset_page, 'States': self._states_page,
                    'Transitions': self._transitions_page, 'Junctions': self._junctions_page,
                    'Links': self._links_page, 'User Properties': self._user_page}
        for c, build in builders.items():
            if has[c]:
                self.page_of[c] = build()
                self.pages.addWidget(self.page_of[c])
        first = ('Clock' if 'clock' in points else 'Resets' if 'reset' in points else
                 'States' if self.states else 'Transitions' if self.transitions else
                 'Junctions' if self.junctions else 'Links' if self.links else 'User Properties')
        if first not in self.page_of:
            first = next(iter(self.page_of), 'User Properties')
            if first not in self.page_of:
                self.page_of[first] = self._user_page()
                self.pages.addWidget(self.page_of[first])
        self.cats.setCurrentRow(CATEGORIES.index(first))
        self._category(CATEGORIES.index(first))
        self.cats.currentRowChanged.connect(self._category)

        body = QHBoxLayout()
        body.addWidget(self.cats)
        body.addWidget(self.pages, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for text, slot in (('OK', self._ok), ('Cancel', self.reject), ('Apply', self.apply), ('Help', None)):
            b = QPushButton(text)
            if slot is None or (readonly and text == 'Apply'):
                b.setEnabled(False)
            else:
                b.clicked.connect(slot)
            if text == 'OK':
                b.setDefault(True)
            buttons.addWidget(b)
        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addLayout(buttons)

    # -- helpers --------------------------------------------------------------------
    def _signal(self, category: str):
        """The signal of the view with this category (clock / reset), or None."""
        if self.view is None:
            return None
        return next((s for s in self.view.signals if s.category == category), None)

    def _input_names(self) -> list[str]:
        """Names of the view's input signals (the choices of the clock / reset name)."""
        return [s.name for s in self.view.signals if s.mode == 'input'] if self.view is not None else []

    def _name_combo(self, current: str) -> QComboBox:
        """An editable drop-down of the input signals, set to `current`."""
        c = QComboBox()
        c.setEditable(True)
        c.addItems(self._input_names())
        c.setCurrentText(current)
        return c

    # -- pages ----------------------------------------------------------------------
    def _clock_page(self) -> QWidget:
        """Clock Point: the clock signal, its edge and the condition it makes ("posedge clk")."""
        w = QWidget()
        lay = QVBoxLayout(w)
        s = self._signal('clock')
        expr = (s.expression or f'posedge {s.name}') if s else ''
        form = QFormLayout()
        self.clk_name = self._name_combo(s.name if s else '')
        form.addRow('Name:', self.clk_name)
        self.clk_edge = QComboBox()
        self.clk_edge.addItems(['Rising', 'Falling'])
        self.clk_edge.setCurrentIndex(1 if expr.lstrip().startswith('negedge') else 0)
        form.addRow('Edge:', self.clk_edge)
        lay.addLayout(form)
        row = QHBoxLayout()
        lab = QLabel('Condition:'); lab.setEnabled(False)
        row.addWidget(lab); row.addStretch(1); row.addWidget(_visible())
        lay.addLayout(row)
        self.clk_cond = _text_box()
        self.clk_cond.setReadOnly(True)
        self.clk_cond.setEnabled(False)
        lay.addWidget(self.clk_cond, 1)

        def show_cond():
            edge = 'negedge' if self.clk_edge.currentIndex() == 1 else 'posedge'
            self.clk_cond.setPlainText(f'{edge} {self.clk_name.currentText().strip()}')
        self.clk_name.currentTextChanged.connect(show_cond)
        self.clk_edge.currentIndexChanged.connect(show_cond)
        show_cond()
        self.clk_start = (self.clk_name.currentText(), self.clk_edge.currentIndex())
        return w

    def _reset_page(self) -> QWidget:
        """Reset Points: mode (synchronous: tested in the clocked block; asynchronous: also in its
        sensitivity list), the reset signal, its active level, and the reset actions (automatic: the
        reset values of the Signals Table)."""
        w = QWidget()
        lay = QVBoxLayout(w)
        s = self._signal('reset')
        expr = (s.expression or f'!{s.name}') if s else ''
        lay.addWidget(QLabel('Number of selected resets: 1'))
        form = QFormLayout()
        mode = QHBoxLayout()
        self.rst_mode = QButtonGroup(w)
        for k, t in enumerate(('Synchronous', 'Asynchronous')):
            r = QRadioButton(t)
            r.setChecked(k == (0 if s is not None and s.sync else 1))
            self.rst_mode.addButton(r, k); mode.addWidget(r)
        mode.addStretch(1)
        form.addRow('Reset Mode:', mode)
        self.rst_name = self._name_combo(s.name if s else '')
        form.addRow('Reset name:', self.rst_name)
        self.rst_level = QComboBox()
        self.rst_level.addItems(['Low', 'High'])
        self.rst_level.setCurrentIndex(0 if expr.lstrip().startswith(('!', '~')) else 1)
        form.addRow('Reset Level:', self.rst_level)
        self.rst_start = self._rst_state()
        prio = QSpinBox(); prio.setEnabled(False); prio.setSpecialValueText(' ')
        plab = QLabel('Priority:'); plab.setEnabled(False)
        form.addRow(plab, prio)
        lay.addLayout(form)
        acts = QGroupBox('Reset Actions')
        al = QVBoxLayout(acts)
        top = QHBoxLayout()
        auto = QRadioButton('Automatic (use reset assignments from Signals Table)'); auto.setChecked(True)
        top.addWidget(auto); top.addStretch(1); top.addWidget(_visible(False))
        al.addLayout(top)
        spec = QRadioButton('Specified (use instead of values from Signals Table)'); spec.setEnabled(False)
        al.addWidget(spec)
        box = _text_box(); box.setPlainText('< Automatic >'); box.setEnabled(False)
        al.addWidget(box, 1)
        lay.addWidget(acts, 1)
        return w

    def _states_page(self) -> QWidget:
        """The States page: name (one state only), the disabled the legacy tool-only fields and the three action tabs."""
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        form.addRow('Number of selected states:', QLabel(str(len(self.states))))
        self.name = QLineEdit(self.states[0].name if len(self.states) == 1 else '')
        self.name.setEnabled(len(self.states) == 1)     # one name per state: only for one state
        form.addRow('Name:', self.name)
        typ = QComboBox(); typ.addItems(['Simple State']); typ.setEnabled(False)
        shape = QPushButton('Shape...'); shape.setEnabled(False)
        row = QHBoxLayout(); row.addWidget(typ, 1); row.addWidget(shape)
        form.addRow('State Type:', row)
        lay.addLayout(form)
        out = QGroupBox('Outgoing transitions for this state')
        ol = QVBoxLayout(out)
        style = QHBoxLayout()
        style.addWidget(QLabel('Style:'))
        grp = QButtonGroup(out)
        for k, t in enumerate(('IF', 'CASE')):
            r = QRadioButton(t); r.setChecked(k == 0); r.setEnabled(False); grp.addButton(r); style.addWidget(r)
        style.addStretch(1)
        settings = QPushButton('Settings...'); settings.setEnabled(False); style.addWidget(settings)
        ol.addLayout(style)
        loop = QCheckBox('Implicit loopback'); loop.setChecked(True); loop.setEnabled(False)
        ol.addWidget(loop)
        lay.addWidget(out)
        tabs = QTabWidget()
        self.action_boxes = {}
        one = self.states[0] if len(self.states) == 1 else None
        for title, attr in (('Entry Actions', 'entry_actions'), ('State Actions', 'in_actions'),
                            ('Exit Actions', 'exit_actions')):
            page = QWidget(); pl = QVBoxLayout(page)
            if attr == 'entry_actions':
                via = QCheckBox('Perform entry actions via implicit loopback'); via.setEnabled(False)
                pl.addWidget(via)
            box = _text_box()
            box.setPlainText(getattr(one, attr) if one else '')
            box.setEnabled(one is not None)
            pl.addWidget(box)
            self.action_boxes[attr] = box
            tabs.addTab(page, title)
        tabs.setCornerWidget(_visible())
        lay.addWidget(tabs, 1)
        return w

    def _transitions_page(self) -> QWidget:
        """The Transitions page: condition, priority and actions (editable for one transition only)."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(f'Number of selected transitions:  {len(self.transitions)}'))
        one = self.transitions[0] if len(self.transitions) == 1 else None
        cond = QGroupBox('IF Condition')
        cl = QVBoxLayout(cond)
        cl.addWidget(_visible(), 0, Qt.AlignRight)
        self.cond = _text_box()
        self.cond.setPlainText(one.cond if one else '')
        self.cond.setEnabled(one is not None)
        cl.addWidget(self.cond)
        lay.addWidget(cond)
        prow = QHBoxLayout()
        prow.addWidget(QLabel('Priority:'))
        self.prio = QSpinBox(); self.prio.setRange(1, 99)
        self.prio.setValue(one.priority if one else 1); self.prio.setEnabled(one is not None)
        prow.addWidget(self.prio)
        prow.addStretch(1)
        prow.addWidget(_visible())
        lay.addLayout(prow)
        act = QGroupBox('Actions')
        al = QVBoxLayout(act)
        al.addWidget(_visible(), 0, Qt.AlignRight)
        self.actions = _text_box()
        self.actions.setPlainText(one.actions if one else '')
        self.actions.setEnabled(one is not None)
        al.addWidget(self.actions)
        lay.addWidget(act, 1)
        return w

    def _junctions_page(self) -> QWidget:
        """Junctions: style AND / IF / CASE of the outgoing transitions and the CASE selector expression
        (editable for one junction). HDL Studio keeps no junction name: the field is shown empty."""
        w = QWidget()
        lay = QVBoxLayout(w)
        one = self.junctions[0] if len(self.junctions) == 1 else None
        form = QFormLayout()
        form.addRow('Number of selected junctions:', QLabel(str(len(self.junctions))))
        name = QLineEdit(); name.setEnabled(False)
        form.addRow('Name:', name)
        lay.addLayout(form)
        out = QGroupBox('Outgoing transitions for this junction')
        ol = QHBoxLayout(out)
        ol.addWidget(QLabel('Style:'))
        self.j_style = QButtonGroup(out)
        style = 'case' if one and one.kind == 'case' else 'and' if one and one.symbol == '&' else 'if'
        for k, (t, key) in enumerate((('AND', 'and'), ('IF', 'if'), ('CASE', 'case'))):
            r = QRadioButton(t); r.setChecked(key == style); r.setEnabled(one is not None)
            self.j_style.addButton(r, k); ol.addWidget(r)
        ol.addStretch(1)
        settings = QPushButton('Settings...'); settings.setEnabled(False); ol.addWidget(settings)
        lay.addWidget(out)
        sel = QGroupBox('CASE Selector Expression')
        sl = QFormLayout(sel)
        sl.addRow('Context:', QLabel('case (<selector_expression>)'))
        er = QHBoxLayout()
        self.j_expr = QLineEdit(one.expr if one else '')
        er.addWidget(self.j_expr, 1); er.addWidget(_visible())
        sl.addRow('Expression:', er)
        lay.addWidget(sel)
        lay.addStretch(1)
        self.j_case_box = sel
        self.j_style.idToggled.connect(lambda _id, on: self._junction_style_changed())
        self._junction_style_changed()
        return w

    def _junction_style_changed(self):
        """The CASE expression applies only to a CASE junction."""
        self.j_case_box.setEnabled(len(self.junctions) == 1 and self.j_style.checkedId() == 2)

    def _links_page(self) -> QWidget:
        """Links: the target the link leads to (a state or a junction of this machine)."""
        w = QWidget()
        lay = QVBoxLayout(w)
        one = self.links[0] if len(self.links) == 1 else None
        lay.addWidget(QLabel(f'Number of selected links:  {len(self.links)}'))
        self.l_modify = QCheckBox('Modify'); self.l_modify.setChecked(True)
        lay.addWidget(self.l_modify)
        form = QFormLayout()
        self.l_target = QComboBox()
        self.l_target.setEditable(True)
        self.l_target.addItems(sorted(s.name for s in self.machine.states))
        self.l_target.setCurrentText(one.target if one else '')
        form.addRow('Link target:', self.l_target)
        lay.addLayout(form)
        note = QLabel('The link target can refer to a State, Hierarchical State or Junction within this '
                      'concurrent state machine.')
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)
        self.l_modify.toggled.connect(self.l_target.setEnabled)
        return w

    def _user_page(self) -> QWidget:
        """User Properties: the Class / Name / Value table (HDL Studio keeps none: shown empty)."""
        w = QWidget()
        lay = QVBoxLayout(w)
        hint = QLabel('Add or modify properties associated with the selected object.\n'
                      'It is not necessary to specify a Class for user-entered properties.')
        hint.setEnabled(False)
        lay.addWidget(hint)
        t = QTableWidget(1, 3)
        t.setHorizontalHeaderLabels(['Class', 'Name', 'Value'])
        t.verticalHeader().hide()
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEnabled(False)
        lay.addWidget(t, 1)
        return w

    def _category(self, row: int):
        """Show the page of the category clicked on the left (greyed categories cannot be picked)."""
        cat = CATEGORIES[row]
        if cat in self.page_of:
            self.pages.setCurrentWidget(self.page_of[cat])
        self.setWindowTitle(f'SM Object Properties - {_TITLES.get(cat, cat)}')

    # -- apply ------------------------------------------------------------------------
    def apply(self) -> bool:
        """Write the fields back to the selected objects. A state name that is empty or used by
        another state, or an empty clock / reset / link name, is refused (the dialog stays open).
        Returns False when refused."""
        if len(self.states) == 1:
            s = self.states[0]
            new = self.name.text().strip()
            if not new or any(o.name == new for o in self.machine.states if o is not s):
                self._refuse(self.name)
                return False
            if new != s.name:
                for lk in self.machine.links:          # links to the state follow its new name
                    if lk.target == s.name:
                        lk.target = new
                s.name = new
            for attr, box in self.action_boxes.items():
                setattr(s, attr, box.toPlainText())
        if len(self.transitions) == 1:
            t = self.transitions[0]
            t.cond = self.cond.toPlainText().strip()
            t.actions = self.actions.toPlainText()
            t.priority = self.prio.value()
        if len(self.junctions) == 1:
            j = self.junctions[0]
            style = ('and', 'if', 'case')[self.j_style.checkedId()]
            j.kind = 'case' if style == 'case' else 'if'
            j.symbol = {'and': '&', 'if': 'if', 'case': 'case'}[style]
            j.orig.pop('symbol', None)                  # the symbol is drawn centred again
            j.expr = self.j_expr.text().strip() if style == 'case' else j.expr
        if self.links and self.l_modify.isChecked():
            target = self.l_target.currentText().strip()
            if not target:
                self._refuse(self.l_target.lineEdit())
                return False
            for lk in self.links:
                lk.target = target
        if 'Clock' in self.page_of and (self.clk_name.currentText(), self.clk_edge.currentIndex()) != self.clk_start:
            name = self.clk_name.currentText().strip()
            if not name:
                self._refuse(self.clk_name.lineEdit())
                return False
            edge = 'negedge' if self.clk_edge.currentIndex() == 1 else 'posedge'
            self._set_signal('clock', name, f'{edge} {name}')
            self.clk_start = (self.clk_name.currentText(), self.clk_edge.currentIndex())
        if 'Resets' in self.page_of and self._rst_state() != self.rst_start:
            name = self.rst_name.currentText().strip()
            if not name:
                self._refuse(self.rst_name.lineEdit())
                return False
            self._set_signal('reset', name, f'!{name}' if self.rst_level.currentIndex() == 0 else name)
            rst = self._signal('reset')
            rst.sync, rst.detail = self.rst_mode.checkedId() == 0, ''
            self.rst_start = self._rst_state()
        self.applied = True
        self.applied_changes.emit()
        return True

    def _rst_state(self) -> tuple:
        """The Reset page as set: (name, level, mode)."""
        return self.rst_name.currentText(), self.rst_level.currentIndex(), self.rst_mode.checkedId()

    def _set_signal(self, category: str, name: str, expression: str):
        """Make input `name` the clock / reset signal of the view (the one it replaces becomes a
        plain data input) with this expression; a name that is not a signal yet is added as an input."""
        from model import Signal
        sigs = self.view.signals
        old = self._signal(category)
        new = next((s for s in sigs if s.name == name), None)
        if new is None:
            new = Signal(name=name, mode='input', category=category)
            sigs.append(new)
        if old is not None and old is not new:
            old.category, old.expression, old.sync, old.detail = 'data', '', False, ''
        new.category, new.expression, new.detail = category, expression, ''

    def _refuse(self, field):
        """Put the cursor back on a refused field."""
        if field is not None:
            field.setFocus()
            field.selectAll()

    def _ok(self):
        """OK: apply and close, unless apply() refused the input (read-only: just close)."""
        if self.readonly or self.apply():
            self.accept()
