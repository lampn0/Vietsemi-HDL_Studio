"""SM Object Properties: the state diagram object dialog of the legacy tool (a double-click on a state
away from its name, or on a transition), laid out as the legacy tool shows it.

Left, the object categories (Clock, Resets, Enable, States, Transitions, Junctions, Links,
Text, User Properties); right, the page of the category of the selected objects:
  States       Number of selected states, Name, State Type, Shape..., outgoing transitions
               Style IF / CASE, Implicit loopback, Entry / State / Exit Actions tabs;
  Transitions  Number of selected transitions, IF Condition, Priority, Actions.
Fields HDL Studio does not keep yet (state type, shape, style, loopback, the Visible boxes)
are shown as the legacy tool has them but disabled. OK applies and closes, Apply applies, Cancel closes.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                               QRadioButton, QSpinBox, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from model import Machine, State, Transition

CATEGORIES = ['Clock', 'Resets', 'Enable', 'States', 'Transitions', 'Junctions', 'Links', 'Text',
              'User Properties']
MONO = QFont('Courier New', 9)


def _text_box() -> QPlainTextEdit:
    """A monospaced, non-wrapping text box for conditions and actions."""
    t = QPlainTextEdit()
    t.setFont(MONO)
    t.setLineWrapMode(QPlainTextEdit.NoWrap)
    return t


def _visible() -> QCheckBox:
    """The legacy tool's "Visible" box: shown checked, not editable yet (HDL Studio always shows the text)."""
    c = QCheckBox('Visible')
    c.setChecked(True)
    c.setEnabled(False)
    return c


class SmObjectPropertiesDialog(QDialog):
    """The SM Object Properties dialog (see the module docstring). `applied` is True after OK or
    Apply changed the objects, so the editor knows to redraw and record an undo step.
    """
    def __init__(self, machine: Machine, objs: list, parent=None):
        """Open the dialog on `objs` (the selected states and transitions of `machine`). The page shown
        first is States when a state is selected, else Transitions.
        """
        super().__init__(parent)
        self.machine = machine
        self.objs = objs
        self.applied = False
        self.states = [o for o in objs if isinstance(o, State)]
        self.transitions = [o for o in objs if isinstance(o, Transition)]
        page = 'States' if self.states else 'Transitions'
        self.setWindowTitle(f'SM Object Properties - {page}')
        self.resize(570, 485)

        self.cats = QListWidget()
        self.cats.setFixedWidth(150)
        # categories with objects in the machine are enabled, as the legacy tool greys the others
        present = {'States': bool(machine.states), 'Transitions': bool(machine.transitions),
                   'Junctions': bool(machine.junctions), 'Links': bool(machine.links),
                   'Clock': machine.point('clock') is not None, 'Resets': machine.point('reset') is not None,
                   'Enable': False, 'Text': False, 'User Properties': True}
        for c in CATEGORIES:
            it = QListWidgetItem(c)
            if not present.get(c):
                it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            self.cats.addItem(it)

        self.pages = QStackedWidget()
        self.state_page = self._states_page()
        self.trans_page = self._transitions_page()
        self.pages.addWidget(self.state_page)
        self.pages.addWidget(self.trans_page)
        self.pages.setCurrentWidget(self.state_page if page == 'States' else self.trans_page)
        self.cats.setCurrentRow(CATEGORIES.index(page))
        self.cats.currentRowChanged.connect(self._category)

        body = QHBoxLayout()
        body.addWidget(self.cats)
        body.addWidget(self.pages, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for text, slot in (('OK', self._ok), ('Cancel', self.reject), ('Apply', self.apply), ('Help', None)):
            b = QPushButton(text)
            if slot is None:
                b.setEnabled(False)
            else:
                b.clicked.connect(slot)
            if text == 'OK':
                b.setDefault(True)
            buttons.addWidget(b)
        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addLayout(buttons)

    # -- pages ----------------------------------------------------------------------
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

    def _category(self, row: int):
        """Show the page of the category clicked on the left (only States and Transitions have one)."""
        cat = CATEGORIES[row]
        if cat == 'States':
            self.pages.setCurrentWidget(self.state_page)
        elif cat == 'Transitions':
            self.pages.setCurrentWidget(self.trans_page)
        self.setWindowTitle(f'SM Object Properties - {cat}')

    # -- apply ------------------------------------------------------------------------
    def apply(self) -> bool:
        """Write the fields back to the selected objects. A state name that is empty or used by
        another state is refused (the dialog stays open). Returns False when refused."""
        if len(self.states) == 1:
            s = self.states[0]
            new = self.name.text().strip()
            if not new or any(o.name == new for o in self.machine.states if o is not s):
                self.name.setFocus()
                self.name.selectAll()
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
        self.applied = True
        return True

    def _ok(self):
        """OK: apply and close, unless apply() refused the input."""
        if self.apply():
            self.accept()
