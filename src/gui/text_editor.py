"""HDL text editor window (the legacy tool DesignPad equivalent).

    CodeEditor        QPlainTextEdit with a line-number gutter (error lines in red), current
                      line highlight, Verilog highlighting and soft tabs
    TextEditorWindow  the window around it: File / Edit / Tools menus, Find / Replace bar,
                      Problems list filled by the slang syntax check (F7, also run on load and
                      save), reload when the file changed on disk, Save / Discard / Cancel on close

The Design Manager opens one window per file and passes callbacks (on_saved, on_closed) so
it can rescan the library and keep the session up to date.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPainter, QTextCursor, QTextDocument, QTextFormat
from PySide6.QtWidgets import (QDockWidget, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                               QTextEdit, QWidget)

from hdl.parser import check_text
from .branding import install_app_icon
from .code_view import VerilogHighlighter


def _add(menu, text, slot, key=None):
    """Add an action `text` -> `slot` (with an optional shortcut) to `menu` and return it."""
    a = QAction(text, menu)
    if key is not None:
        a.setShortcut(key)
    a.triggered.connect(slot)
    menu.addAction(a)
    return a


class _LineArea(QWidget):
    """The gutter widget left of the editor; CodeEditor paints it."""
    def __init__(self, editor: 'CodeEditor'):
        """A child of `editor`."""
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        """As wide as the editor needs for its line numbers."""
        return QSize(self.editor.line_area_width(), 0)

    def paintEvent(self, e):
        """Let the editor paint the line numbers."""
        self.editor.paint_line_area(e)


TAB_WIDTH = 2      # Options > Verilog > Style: Tab Width (spaces), for Verilog text views


class CodeEditor(QPlainTextEdit):
    """The editing widget (see the module docstring)."""
    def __init__(self, parent=None):
        """Set up font, tab stops, the gutter and the signals that keep it in sync with the scrolling."""
        super().__init__(parent)
        self.setFont(QFont('Courier New', 10))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.tab_width = TAB_WIDTH
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * self.tab_width)
        self.area = _LineArea(self)
        self.highlighter = VerilogHighlighter(self.document())
        self.blockCountChanged.connect(lambda _: self.setViewportMargins(self.line_area_width(), 0, 0, 0))
        self.updateRequest.connect(self._update_area)
        self.cursorPositionChanged.connect(self._highlight_line)
        self.setViewportMargins(self.line_area_width(), 0, 0, 0)
        self.error_lines: set[int] = set()

    def line_area_width(self) -> int:
        """Width of the gutter: room for the digits of the last line number (at least 4)."""
        return 12 + self.fontMetrics().horizontalAdvance('9') * max(4, len(str(self.blockCount())))

    def _update_area(self, rect, dy):
        """Scroll or repaint the gutter together with the text (Qt's updateRequest signal)."""
        if dy:
            self.area.scroll(0, dy)
        else:
            self.area.update(0, rect.y(), self.area.width(), rect.height())

    def resizeEvent(self, e):
        """Keep the gutter along the left edge of the editor."""
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.area.setGeometry(QRect(cr.left(), cr.top(), self.line_area_width(), cr.height()))

    def paint_line_area(self, e):
        """Paint the line numbers of the visible blocks, with a red band on lines that have errors."""
        p = QPainter(self.area)
        p.fillRect(e.rect(), QColor(240, 240, 240))
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= e.rect().bottom():
            n = block.blockNumber() + 1
            h = round(self.blockBoundingRect(block).height())
            if n in self.error_lines:
                p.fillRect(0, top, self.area.width(), h, QColor(255, 190, 190))
            p.setPen(QColor(120, 120, 120))
            p.drawText(0, top, self.area.width() - 6, h, Qt.AlignRight, str(n))
            block = block.next()
            top += h

    def keyPressEvent(self, e):
        """Tab without selection inserts spaces up to the next tab stop (no tab characters)."""
        if e.key() == Qt.Key_Tab and not e.modifiers() and not self.textCursor().hasSelection():
            col = self.textCursor().positionInBlock()          # spaces to the next tab stop
            self.insertPlainText(' ' * (self.tab_width - col % self.tab_width))
            return
        super().keyPressEvent(e)

    def _highlight_line(self):
        """Give the line of the cursor a light yellow background."""
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor(255, 255, 220))
        sel.format.setProperty(QTextFormat.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([sel])

    def goto_line(self, line: int):
        """Put the cursor on line `line` (1-based), centred in the view."""
        block = self.document().findBlockByLineNumber(max(0, line - 1))
        cur = QTextCursor(block)
        self.setTextCursor(cur)
        self.centerCursor()
        self.setFocus()


class TextEditorWindow(QMainWindow):
    """One HDL file in a window (see the module docstring)."""
    def __init__(self, path: str, include_dirs: list[str] | None = None, readonly_reason: str = '',
                 on_saved=None, on_closed=None):
        """Open `path`. `include_dirs` are used by the syntax check; a non-empty `readonly_reason`
        makes the text read-only (protected library, lock held by someone else ...).
        """
        super().__init__()
        install_app_icon()                  # Vietsemi mark (also when run on its own)
        self.path = path
        self.include_dirs = include_dirs or []
        self.readonly_reason = readonly_reason
        self.on_saved, self.on_closed = on_saved, on_closed
        self.editor = CodeEditor()
        self.setCentralWidget(self.editor)
        self.problems = QListWidget()
        self.problems.setFont(QFont('Courier New', 9))
        self.problems.itemActivated.connect(lambda it: self.editor.goto_line(it.data(Qt.UserRole)))
        self.problems.itemClicked.connect(lambda it: self.editor.goto_line(it.data(Qt.UserRole)))
        dock = QDockWidget('Problems', self)
        dock.setWidget(self.problems)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [110], Qt.Vertical)
        self._build_find_bar()
        self._build_menu()
        self.mtime = 0.0
        self.load()
        self.editor.document().modificationChanged.connect(lambda _: self.update_title())
        if readonly_reason:
            self.editor.setReadOnly(True)
        self.resize(1100, 850)

    def _build_find_bar(self):
        """The Find / Replace bar (a dock at the top, hidden until Ctrl+F)."""
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.addWidget(QLabel('Find:'))
        self.find_edit = QLineEdit()
        self.find_edit.returnPressed.connect(self.find_next)
        lay.addWidget(self.find_edit)
        b = QPushButton('Next'); b.clicked.connect(self.find_next); lay.addWidget(b)
        b = QPushButton('Previous'); b.clicked.connect(lambda: self.find_next(back=True)); lay.addWidget(b)
        lay.addWidget(QLabel('Replace:'))
        self.repl_edit = QLineEdit(); lay.addWidget(self.repl_edit)
        b = QPushButton('Replace all'); b.clicked.connect(self.replace_all); lay.addWidget(b)
        self.find_dock = QDockWidget('Find / Replace', self)
        self.find_dock.setWidget(bar)
        self.addDockWidget(Qt.TopDockWidgetArea, self.find_dock)
        self.find_dock.hide()

    def _build_menu(self):
        """File, Edit and Tools menus with their shortcuts."""
        fm = self.menuBar().addMenu('&File')
        _add(fm, '&Save', self.save, QKeySequence.Save)
        _add(fm, '&Reload from disk', self.reload)
        fm.addSeparator()
        _add(fm, '&Close', self.close, QKeySequence.Close)
        em = self.menuBar().addMenu('&Edit')
        _add(em, '&Undo', self.editor.undo, QKeySequence.Undo)
        _add(em, '&Redo', self.editor.redo, QKeySequence.Redo)
        em.addSeparator()
        _add(em, '&Find / Replace...', self.show_find, QKeySequence.Find)
        _add(em, 'Find &next', self.find_next, QKeySequence.FindNext)
        _add(em, '&Go to line...', self.ask_line, 'Ctrl+L')
        tm = self.menuBar().addMenu('&Tools')
        _add(tm, 'Check &syntax', self.check, 'F7')

    # -- file ------------------------------------------------------------------------
    def load(self):
        """Read the file into the editor (empty if it does not exist yet) and check it."""
        try:
            with open(self.path, encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError:
            text = ''
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self.mtime = os.path.getmtime(self.path) if os.path.exists(self.path) else 0.0
        self.update_title()
        self.check()

    def reload(self):
        """File > Reload from disk (asks first when there are unsaved changes)."""
        if self.editor.document().isModified():
            if QMessageBox.question(self, 'Reload', 'Discard your changes and reload from disk?') != QMessageBox.Yes:
                return
        self.load()

    def save(self) -> bool:
        """Write the file (LF line endings). Asks before overwriting a file another program changed
        since it was loaded. Returns False when nothing was written.
        """
        if self.readonly_reason:
            QMessageBox.information(self, 'Read-only', f'Cannot save: {self.readonly_reason}.')
            return False
        if os.path.exists(self.path) and os.path.getmtime(self.path) != self.mtime:
            if QMessageBox.question(self, 'File changed on disk',
                                    f'{os.path.basename(self.path)} was changed by another program. Overwrite it?') \
                    != QMessageBox.Yes:
                return False
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        with open(self.path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(self.editor.toPlainText())
        self.mtime = os.path.getmtime(self.path)
        self.editor.document().setModified(False)
        self.update_title()
        self.check()
        if self.on_saved:
            self.on_saved(self.path)
        return True

    def update_title(self):
        """Window title: file name, [read-only], '*' when modified, and the folder."""
        star = ' *' if self.editor.document().isModified() else ''
        ro = ' [read-only]' if self.readonly_reason else ''
        self.setWindowTitle(f'{os.path.basename(self.path)}{ro}{star} — {os.path.dirname(self.path)}')

    def changeEvent(self, e):
        """When the window becomes active, reload a file changed on disk (if not modified here)."""
        super().changeEvent(e)
        if self.isActiveWindow() and os.path.exists(self.path) and self.mtime and \
                os.path.getmtime(self.path) != self.mtime and not self.editor.document().isModified():
            self.load()

    def closeEvent(self, e):
        """Ask Save / Discard / Cancel for unsaved changes, then tell the owner the window closed."""
        if self.editor.document().isModified():
            r = QMessageBox.question(self, 'Unsaved changes', f'Save {os.path.basename(self.path)}?',
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel or (r == QMessageBox.Save and not self.save()):
                e.ignore()
                return
        if self.on_closed:
            self.on_closed(self)
        e.accept()

    # -- tools -------------------------------------------------------------------------
    def check(self):
        """Syntax-check the text with slang and list the diagnostics in the Problems dock."""
        self.problems.clear()
        diags = check_text(self.editor.toPlainText(), self.path, self.include_dirs)
        self.editor.error_lines = {l for l, sev, _ in diags if sev == 'error'}
        self.editor.area.update()
        for line, sev, msg in diags:
            it = QListWidgetItem(f'{os.path.basename(self.path)}:{line}: {sev}: {msg}')
            it.setData(Qt.UserRole, line)
            it.setForeground(QColor(200, 0, 0) if sev == 'error' else QColor(150, 110, 0))
            self.problems.addItem(it)
        if not diags:
            self.problems.addItem('No syntax errors')
        errors = sum(1 for d in diags if d[1] == 'error')
        self.statusBar().showMessage(f'{errors} error(s), {len(diags) - errors} warning(s)', 5000)

    def show_find(self):
        """Show the Find / Replace bar with the search text selected."""
        self.find_dock.show()
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def find_next(self, back: bool = False):
        """Find the next (or previous) match, wrapping around at the end of the text."""
        text = self.find_edit.text()
        if not text:
            return self.show_find()
        flags = QTextDocument.FindBackward if back else QTextDocument.FindFlag(0)
        if not self.editor.find(text, flags):
            cur = self.editor.textCursor()
            cur.movePosition(QTextCursor.End if back else QTextCursor.Start)
            self.editor.setTextCursor(cur)
            self.editor.find(text, flags)

    def replace_all(self):
        """Replace every match in one undo step."""
        text, repl = self.find_edit.text(), self.repl_edit.text()
        if not text or self.editor.isReadOnly():
            return
        cur = self.editor.textCursor()
        cur.beginEditBlock()
        body = self.editor.toPlainText()
        count = body.count(text)
        cur.select(QTextCursor.Document)
        cur.insertText(body.replace(text, repl))
        cur.endEditBlock()
        self.statusBar().showMessage(f'Replaced {count} occurrence(s)', 4000)

    def ask_line(self):
        """Edit > Go to line."""
        n, ok = QInputDialog.getInt(self, 'Go to line', 'Line:', 1, 1, self.editor.blockCount())
        if ok:
            self.editor.goto_line(n)
