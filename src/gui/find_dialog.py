"""Edit > Find... / Replace... of the diagram editors: the legacy "Find and Replace" dialog.

Layout (read from the legacy tool, state and block diagram):

    [Find] [Replace]                                           Find Next
    Find What:    [combo, history shared by all windows]       Close / Replace
    Replace With: [combo]                  (Replace tab)       More >> / << Less
    -- More -----------------------------------------------    Find All
    Search Depth/Direction  [Current|Hierarchically|...]       Select All / Replace All
                            [ ] Embedded Views                 Help
    Search selected objects [list of the object kinds]
    General  [ ] Match case  [ ] Match whole word only  [ ] Wrap search
             [ ] Regular expression  [ ] Select related object   (Find tab)
             [Clear Constraints]                    [Reg. Exp. Syntax]
    -- after Find All: a table  # | Diagram | Object Name | Status | Text

Find Next goes to the next match after the current one (from the first again with Wrap search)
and shows it: the text opened for editing with the match selected, or, with Select related
object or for a text that has no in-place editor, its object selected. Selecting kinds in Search
selected objects limits the search to them (Clear Constraints selects none again: all kinds).
Replace changes the match Find Next found, then finds the next one; Replace All changes every
match, as one undoable edit.

The editor gives the texts to search as TextField records (`fields()`), each with its kind (an
entry of the list), the name of its object, how to read and write it (no writer: read only) and
how to show it (`show(span)`, span = (start, end) of the match or None).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QGridLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QListWidget, QMessageBox,
                               QPushButton, QTabBar, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

# the legacy tool's messages at the end of a search
END_OF_SEARCH = "End of search. Hit 'Find Next' to start again."
NOTHING_FOUND = 'Search completed. Nothing was found.'
HISTORY: list[str] = []               # Find What entries, shared by every window (as the legacy tool)
REPLACE_HISTORY: list[str] = []
HISTORY_SIZE = 20
DEPTHS = ['Current', 'Hierarchically', 'Through Components']

# object kinds of the Search selected objects list, as the legacy tool lists them
FSM_KINDS = ['Comment text', 'Compiler Directives', 'Group Column/Row', 'Process Declaration Block',
             'Requirement Reference', 'Signals Assign Column', 'Signals Bounds Column', 'Signals Category Column',
             'Signals Comment Column', 'Signals Default Column', 'Signals Delay Column', 'Signals Expression Column',
             'Signals Initial Column', 'Signals Mode Column', 'Signals Name Column', 'Signals Reset Column',
             'Signals Scheme Column', 'Signals Type Column', 'State actions', 'State machine properties',
             'State name', 'Transition actions', 'Transition conditions']
BD_KINDS = ['Block Diagram Properties', 'Block Instance', 'Block Library', 'Block Name', 'Comment text',
            'Compiler Directives', 'Component Generic Interface', 'Component Instance', 'Component Library',
            'Component Name', 'Component Port Map Frame', 'Component Port Name', 'Component Port Type/Range',
            'Component Port initial value', 'Embedded Block Name', 'Embedded Block Number', 'Embedded Block Text',
            'Frame', 'Generics Comment Column', 'Generics Name Column', 'Generics Pragma Column',
            'Generics Type Column', 'Generics Value Column', 'Group Column/Row', 'Requirement Reference',
            'Signal Name', 'Signal Type/Range', 'Signal initial value', 'Signals Bounds Column',
            'Signals Comment Column', 'Signals Delay Column', 'Signals Initial Column', 'Signals Mode Column',
            'Signals Name Column', 'Signals Type Column']

HELP = """<b>Find and Replace</b><br><br>
<b>Find Next</b> shows the next text that matches: it is opened for editing with the match selected
(or its object is selected with <i>Select related object</i>). <b>Find All</b> lists every match below;
double-click a row to show it. <b>Select All</b> selects the objects of every match.<br>
<b>Replace</b> changes the match found and goes to the next one; <b>Replace All</b> changes every match
(one Undo step).<br><br>
<b>Search selected objects</b>: select kinds of text to search only those; <b>Clear Constraints</b>
searches all kinds again.<br>
<b>Wrap search</b>: Find Next starts again from the first match after the last one.<br>
<b>Search Depth</b>: only the current diagram in this version."""


@dataclass
class TextField:
    """One text of a diagram that Find / Replace looks in."""
    kind: str                                       # entry of the Search selected objects list
    name: str                                       # Object Name column, e.g. "State name of IDLE"
    get: Callable[[], str]
    set: Callable[[str], None] | None               # None: read only
    show: Callable[[tuple[int, int] | None], None]  # show the text, the match (start, end) selected
    select: Callable[[bool], None] | None = None    # select its object, added to the selection or alone


def _remember(history: list[str], text: str):
    if text:
        if text in history:
            history.remove(text)
        history.insert(0, text)
        del history[HISTORY_SIZE:]


class FindReplaceDialog(QDialog):
    """The dialog of one editor window. `fields()` gives the texts to search, `kinds` the entries of
    the Search selected objects list, `diagram` the name in the Diagram column and the title,
    `done()` is called after a replacement (redraw, one undo step), `readonly` greys Replace."""

    def __init__(self, parent, fields: Callable[[], list[TextField]], done: Callable[[], None],
                 kinds: list[str], diagram: str, replace: bool = False, readonly: bool = False):
        super().__init__(parent)
        self.setWindowTitle(f'Find and Replace - {diagram}')
        self._fields, self._done, self.diagram, self.readonly = fields, done, diagram, readonly
        self._current: tuple[int, int, int] | None = None     # (field index, start, end) of the match shown
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.tabs = QTabBar()
        self.tabs.addTab('Find')
        self.tabs.addTab('Replace')
        self.tabs.setExpanding(False)
        lay.addWidget(self.tabs)

        top = QHBoxLayout()
        left = QVBoxLayout()
        form = QGridLayout()
        self.find = QComboBox(); self.find.setEditable(True); self.find.addItems(HISTORY)
        self.find.setCurrentText('')
        self.find.setMinimumWidth(240)
        self.repl = QComboBox(); self.repl.setEditable(True); self.repl.addItems(REPLACE_HISTORY)
        self.repl.setCurrentText('')
        self.repl_label = QLabel('Replace With:')
        form.addWidget(QLabel('Find What:'), 0, 0); form.addWidget(self.find, 0, 1)
        form.addWidget(self.repl_label, 1, 0); form.addWidget(self.repl, 1, 1)
        form.setColumnStretch(1, 1)
        left.addLayout(form)

        # More: Search Depth/Direction, Search selected objects, General
        self.more_box = QWidget()
        mg = QGridLayout(self.more_box)
        mg.setContentsMargins(0, 4, 0, 0)
        depth = QGroupBox('Search Depth/Direction')
        dl = QVBoxLayout(depth)
        self.depth = QComboBox(); self.depth.addItems(DEPTHS)
        for k in (1, 2):                            # only the current diagram in this version
            self.depth.model().item(k).setEnabled(False)
        self.embedded = QCheckBox('Embedded Views'); self.embedded.setEnabled(False)
        dl.addWidget(self.depth); dl.addWidget(self.embedded)
        objs = QGroupBox('Search selected objects')
        ol = QVBoxLayout(objs)
        self.kinds = QListWidget()
        self.kinds.addItems(kinds)
        self.kinds.setSelectionMode(QAbstractItemView.MultiSelection)
        self.kinds.setFixedHeight(80)
        ol.addWidget(self.kinds)
        general = QGroupBox('General')
        gl = QVBoxLayout(general)
        self.case = QCheckBox('Match case')
        self.word = QCheckBox('Match whole word only')
        self.wrap = QCheckBox('Wrap search')
        self.regex = QCheckBox('Regular expression')
        self.related = QCheckBox('Select related object')
        for c in (self.case, self.word, self.wrap, self.regex, self.related):
            gl.addWidget(c)
        gl.addStretch(1)
        self.clear_btn = QPushButton('Clear Constraints')
        self.syntax_btn = QPushButton('Reg. Exp. Syntax')
        mg.addWidget(depth, 0, 0)
        mg.addWidget(objs, 1, 0)
        mg.addWidget(general, 0, 1, 2, 2)
        mg.addWidget(self.clear_btn, 2, 1)
        mg.addWidget(self.syntax_btn, 2, 2, Qt.AlignRight)
        mg.setColumnStretch(2, 1)
        left.addWidget(self.more_box)
        left.addStretch(1)                          # Find What stays at the top when the options are hidden
        top.addLayout(left, 1)

        buttons = QVBoxLayout()
        self.b_next = QPushButton('Find Next')
        self.b_replace = QPushButton('Replace')
        self.b_close = QPushButton('Close')
        self.b_more = QPushButton('More >>')
        self.b_all = QPushButton('Find All')
        self.b_select = QPushButton('Select All')
        self.b_repl_all = QPushButton('Replace All')
        self.b_help = QPushButton('Help')
        for b in (self.b_next, self.b_replace, self.b_close, self.b_more, self.b_all, self.b_select,
                  self.b_repl_all, self.b_help):
            b.setFixedWidth(96)
            buttons.addWidget(b)
        buttons.addStretch(1)
        top.addLayout(buttons)
        lay.addLayout(top)

        self.status = QLabel('')
        lay.addWidget(self.status)
        self.results = QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels(['Diagram', 'Object Name', 'Status', 'Text'])
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.results.horizontalHeader().setStretchLastSection(True)
        self.results.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results.setWordWrap(False)
        self.results.cellDoubleClicked.connect(lambda r, _c: self._show_row(r))
        self.results.hide()
        lay.addWidget(self.results, 1)
        self._rows: list[tuple[int, int, int]] = []

        self.tabs.currentChanged.connect(self._tab_changed)
        self.b_next.clicked.connect(self.find_next)
        self.b_replace.clicked.connect(self.replace_one)
        self.b_close.clicked.connect(self.close)
        self.b_more.clicked.connect(lambda: self.set_more(not self.more_box.isVisible()))
        self.b_all.clicked.connect(self.find_all)
        self.b_select.clicked.connect(self.select_all)
        self.b_repl_all.clicked.connect(self.replace_all)
        self.b_help.clicked.connect(lambda: QMessageBox.information(self, 'Find and Replace', HELP))
        self.clear_btn.clicked.connect(self.kinds.clearSelection)
        self.kinds.itemSelectionChanged.connect(self._update_buttons)
        self.regex.toggled.connect(self._update_buttons)
        self.syntax_btn.clicked.connect(self._regex_help)
        self.find.lineEdit().returnPressed.connect(self.find_next)
        self.find.editTextChanged.connect(lambda _t: setattr(self, '_current', None))
        self.b_next.setDefault(True)
        self.set_more(False)
        self.tabs.setCurrentIndex(1 if replace else 0)
        self._tab_changed(self.tabs.currentIndex())

    # -- layout -------------------------------------------------------------------------------
    def set_more(self, on: bool):
        """More >> / << Less: show or hide the search options."""
        self.more_box.setVisible(on)
        self.b_more.setText('<< Less' if on else 'More >>')
        self._tab_changed(self.tabs.currentIndex())
        self.adjustSize()

    def _tab_changed(self, index: int):
        """The Find tab: Find Next, Close, More, Find All, Select All, Help; the Replace tab: Find Next,
        Replace, Close, More, Find All, Replace All, Help (Find All and the last ones with More only)."""
        rep = index == 1
        more = self.more_box.isVisible()
        self.repl.setVisible(rep)
        self.repl_label.setVisible(rep)
        self.related.setVisible(not rep)
        self.b_replace.setVisible(rep)
        self.b_select.setVisible(not rep and more)
        self.b_repl_all.setVisible(rep and more)
        self.b_all.setVisible(more)
        self.b_help.setVisible(more)
        self.b_replace.setEnabled(not self.readonly)
        self.b_repl_all.setEnabled(not self.readonly)
        self.setWindowTitle(f'Find and Replace - {self.diagram}')
        self._update_buttons()

    def _update_buttons(self):
        self.clear_btn.setEnabled(bool(self.kinds.selectedItems()))
        self.syntax_btn.setEnabled(self.regex.isChecked())

    def _regex_help(self):
        from .editor_common import show_regex_help
        show_regex_help(self)

    # -- searching ----------------------------------------------------------------------------
    def pattern(self) -> re.Pattern | None:
        """The search as a regular expression (None when the box is empty or the expression is wrong)."""
        text = self.find.currentText()
        if not text:
            return None
        expr = text if self.regex.isChecked() else re.escape(text)
        if self.word.isChecked():
            expr = rf'\b(?:{expr})\b'
        try:
            return re.compile(expr, 0 if self.case.isChecked() else re.IGNORECASE)
        except re.error as e:
            self.status.setText(f'Invalid regular expression: {e}')
            return None

    def _search_fields(self) -> list[TextField]:
        """The texts of the kinds selected in Search selected objects (all kinds when none is)."""
        wanted = {it.text() for it in self.kinds.selectedItems()}
        return [f for f in self._fields() if not wanted or f.kind in wanted]

    def matches(self) -> tuple[list[TextField], list[tuple[int, int, int]]]:
        """The texts searched and every match in them: (field index, start, end), in order."""
        pat = self.pattern()
        fields = self._search_fields()
        if pat is None:
            return fields, []
        out = []
        for i, f in enumerate(fields):
            for m in pat.finditer(f.get() or ''):
                if m.end() > m.start():
                    out.append((i, m.start(), m.end()))
        return fields, out

    def _remember(self):
        text = self.find.currentText()
        _remember(HISTORY, text)
        self.find.blockSignals(True)
        self.find.clear(); self.find.addItems(HISTORY); self.find.setCurrentText(text)
        self.find.blockSignals(False)

    def _show(self, f: TextField, span):
        if self.related.isChecked() and not self.tabs.currentIndex() and f.select is not None:
            f.select(False)
        else:
            f.show(span)

    def find_next(self) -> bool:
        """Find Next: show the match after the one shown last (from the first with Wrap search).
        Returns True when a match was shown."""
        self._remember()
        fields, found = self.matches()
        if not found:
            self._current = None
            self._message(NOTHING_FOUND)
            return False
        nxt = found[0]
        if self._current is not None:
            later = [m for m in found if m > self._current]
            if later:
                nxt = later[0]
            elif not self.wrap.isChecked():
                # as the legacy tool: a message, and the next Find Next starts from the first match again
                self._current = None
                self._message(END_OF_SEARCH)
                return False
        self._current = nxt
        f = fields[nxt[0]]
        self.status.setText(f'{f.name}')
        # as the legacy tool: the diagram comes to the front with the match selected in its text
        self._show(f, (nxt[1], nxt[2]))
        return True

    def _message(self, text: str):
        """The end of the search (or nothing found): a message box, as the legacy tool shows."""
        from version import APP_NAME
        from .editor_common import mark_text
        mark_text(None, None)
        self.status.setText(text)
        QMessageBox.information(self, APP_NAME, text)

    def find_all(self):
        """Find All: one row per text that matches, below the options."""
        self._remember()
        fields, found = self.matches()
        rows = []
        for m in found:
            if not rows or rows[-1][0] != m[0]:
                rows.append(m)
        self._rows = rows
        self._row_fields = fields
        self.results.setRowCount(len(rows))
        for r, (i, _s, _e) in enumerate(rows):
            f = fields[i]
            status = 'Read Only' if self.readonly or f.set is None else 'Available for Edit'
            for c, v in enumerate((self.diagram, f.name, status, (f.get() or '').replace('\n', ' '))):
                self.results.setItem(r, c, QTableWidgetItem(v))
        self.results.resizeColumnsToContents()
        for c in range(3):
            self.results.setColumnWidth(c, min(self.results.columnWidth(c), 260))
        self.results.setVisible(True)
        self.status.setText(f'{len(found)} match(es) in {len(rows)} object(s)')
        if not self.more_box.isVisible():
            self.set_more(True)
        self.resize(max(self.width(), 760), max(self.height(), 520))

    def _show_row(self, r: int):
        if 0 <= r < len(self._rows):
            i, s, e = self._rows[r]
            self._current = self._rows[r]
            self._show(self._row_fields[i], (s, e))

    def select_all(self):
        """Select All: select the objects of every match."""
        fields, found = self.matches()
        hit = [fields[i] for i in dict.fromkeys(i for i, _s, _e in found)]
        add = False
        for f in hit:
            if f.select is not None:
                f.select(add)
                add = True
        self.status.setText(f'{len(hit)} object(s) selected')

    # -- replacing ----------------------------------------------------------------------------
    def _replacement(self, m: re.Match) -> str:
        text = self.repl.currentText()
        return m.expand(text) if self.regex.isChecked() else text

    def replace_one(self):
        """Replace: change the match Find Next found (or find one first), then find the next one."""
        _remember(REPLACE_HISTORY, self.repl.currentText())
        pat = self.pattern()
        if pat is None or self.readonly:
            return
        fields, found = self.matches()
        cur = self._current
        if cur is None or cur not in found:
            self.find_next()
            return
        f = fields[cur[0]]
        if f.set is None:
            self.status.setText(f'{f.name} is read only')
            self.find_next()
            return
        old = f.get() or ''
        m = pat.match(old, cur[1])
        if m is None or m.end() != cur[2]:
            self.find_next()
            return
        new_text = self._replacement(m)
        f.set(old[:cur[1]] + new_text + old[cur[2]:])
        self._current = (cur[0], cur[1], cur[1] + len(new_text))
        self._done()
        self.find_next()

    def replace_all(self) -> int:
        """Replace All: change every match (one undoable edit). Returns the number of replacements."""
        _remember(REPLACE_HISTORY, self.repl.currentText())
        pat = self.pattern()
        if pat is None or self.readonly:
            return 0
        n = 0
        for f in self._search_fields():
            if f.set is None:
                continue
            old = f.get() or ''
            new, k = pat.subn(self._replacement, old)
            if k and new != old:
                f.set(new)
                n += k
        if n:
            self._done()
        self._current = None
        self.status.setText(f'{n} replacement(s)')
        if self.results.isVisible():
            self.find_all()
        return n

    def open_tab(self, replace: bool):
        """Show the dialog on its Find or Replace tab, the selected text of the window as the search."""
        self.tabs.setCurrentIndex(1 if replace else 0)
        self.show()
        self.raise_()
        self.activateWindow()
        self.find.setFocus()
        self.find.lineEdit().selectAll()
