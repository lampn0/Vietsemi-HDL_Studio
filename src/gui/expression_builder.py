"""Edit > Expression Builder of the state diagram editor: build a Verilog expression (a transition
condition, typically) from the signals of the diagram and the operators, by clicking, as the
legacy tool's dialog does. The text stays editable; OK puts it on the selected transition, and
Copy puts it on the clipboard.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel,
                               QListWidget, QPlainTextEdit, QPushButton, QVBoxLayout)

# operator buttons, in rows: (label on the button, text inserted)
OPERATORS = [
    [('&&', ' && '), ('||', ' || '), ('!', '!'), ('( )', '()')],
    [('==', ' == '), ('!=', ' != '), ('<', ' < '), ('>', ' > ')],
    [('<=', ' <= '), ('>=', ' >= '), ('&', ' & '), ('|', ' | ')],
    [('^', ' ^ '), ('~', '~'), ("1'b0", "1'b0"), ("1'b1", "1'b1")],
]


class ExpressionBuilder(QDialog):
    """The dialog. `signals` are the names offered; `text` the expression to start from; `target`
    names what OK changes (empty: OK only closes)."""

    def __init__(self, parent, signals: list[str], text: str = '', target: str = ''):
        super().__init__(parent)
        self.setWindowTitle('Expression Builder')
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f'Expression for the selected {target}:' if target else
                             'Expression (select one transition to apply it to its condition):'))
        self.edit = QPlainTextEdit(text)
        self.edit.setFixedHeight(70)
        lay.addWidget(self.edit)
        row = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel('Signals (double-click to insert):'))
        self.signals = QListWidget()
        self.signals.addItems(sorted(signals, key=str.lower))
        self.signals.itemDoubleClicked.connect(lambda it: self.insert(it.text()))
        left.addWidget(self.signals)
        row.addLayout(left, 2)
        grid = QGridLayout()
        for r, ops in enumerate(OPERATORS):
            for c, (label, ins) in enumerate(ops):
                b = QPushButton(label.replace('&', '&&'))
                b.setFixedWidth(52)
                b.clicked.connect(lambda checked=False, t=ins: self.insert(t))
                grid.addWidget(b, r, c)
        ops_box = QVBoxLayout()
        ops_box.addWidget(QLabel('Operators:'))
        ops_box.addLayout(grid)
        ops_box.addStretch(1)
        row.addLayout(ops_box, 1)
        lay.addLayout(row)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        copy = box.addButton('Copy', QDialogButtonBox.ActionRole)
        clear = box.addButton('Clear', QDialogButtonBox.ResetRole)
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.text()))
        clear.clicked.connect(self.edit.clear)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.resize(560, 380)

    def insert(self, text: str):
        """Insert `text` at the cursor; "()" puts the cursor between the brackets (around a selection)."""
        cur = self.edit.textCursor()
        if text == '()':
            sel = cur.selectedText()
            cur.insertText(f'({sel})')
            if not sel:
                cur.movePosition(cur.Left)
                self.edit.setTextCursor(cur)
        else:
            cur.insertText(text)
        self.edit.setFocus()

    def text(self) -> str:
        """The expression, on one line."""
        return ' '.join(self.edit.toPlainText().split())
