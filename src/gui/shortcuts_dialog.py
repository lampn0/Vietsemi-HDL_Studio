"""Help > Keyboard Shortcuts: the shortcuts of the block diagram and state diagram editors.

A resizable dialog with a filter box and one scrollable list (command, keys) grouped by
editor; it opens at a size that fits the screen, whatever the number of shortcuts.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHeaderView, QLineEdit, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .command_names import COMMANDS
from .toolbars import BD_KEYS, FSM_KEYS

GROUPS = (('Block Diagram', BD_KEYS), ('State Diagram', FSM_KEYS))
SCREEN_PART = 0.7                       # at most this part of the screen when opened


def _command_name(key: str) -> str:
    """Name shown for command `key` (its menu text), or the key itself."""
    return COMMANDS.get(key, ('', key, ''))[1] or key


class ShortcutsDialog(QDialog):
    """Shortcut list with a filter; the window can be resized and the list scrolls."""

    def __init__(self, parent: QWidget | None = None):
        """Fill the list from toolbars.BD_KEYS / FSM_KEYS and size the window to the screen."""
        super().__init__(parent)
        self.setWindowTitle('Keyboard Shortcuts')
        self.setSizeGripEnabled(True)
        lay = QVBoxLayout(self)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText('Filter by command or key')
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        lay.addWidget(self.filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Command', 'Keys'])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        bold = QFont(); bold.setBold(True)
        for title, keys in GROUPS:
            group = QTreeWidgetItem([title])
            group.setFont(0, bold)
            group.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(group)
            group.setFirstColumnSpanned(True)
            for k, v in sorted(keys.items(), key=lambda kv: _command_name(kv[0]).lower()):
                QTreeWidgetItem(group, [_command_name(k), ', '.join(v)])
            group.setExpanded(True)
        lay.addWidget(self.tree)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._fit_screen()

    def _fit_screen(self) -> None:
        """Open at 560 x 640, never more than SCREEN_PART of the available screen."""
        screen = self.screen() or (self.parent().screen() if self.parent() else None)
        w, h = 560, 640
        if screen is not None:
            area = screen.availableGeometry()
            w = min(w, int(area.width() * SCREEN_PART))
            h = min(h, int(area.height() * SCREEN_PART))
        self.resize(w, h)

    def _apply_filter(self, text: str) -> None:
        """Show only rows whose command or keys contain `text` (case-insensitive)."""
        t = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            shown = 0
            for j in range(group.childCount()):
                row = group.child(j)
                hit = not t or t in row.text(0).lower() or t in row.text(1).lower()
                row.setHidden(not hit)
                shown += hit
            group.setHidden(shown == 0)


def show_shortcuts(parent: QWidget | None) -> None:
    """Help > Keyboard Shortcuts."""
    ShortcutsDialog(parent).exec()
