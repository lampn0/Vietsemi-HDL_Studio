"""Signals Table and Parameters Table pages of the diagram editors, drawn and used exactly as the
legacy tool's spreadsheet pages.

The layout comes from the view (FsmView / BlockDiagram .signals_sheet / .params_sheet, read
from the legacy file by formats.sheet, or a new diagram's default below): the columns in their
order with their widths in pixels, the frozen columns (`fixed_col`, the row number column
counts), the heights of the column letter row, the column name row and the rows, the display
order of the rows, the colours of the header / cells / group rows and the format of single cells
(alignment, cell and text colour, size, bold).

Look (colours measured on the legacy tool's screen):
    - two header rows: the column letters (A, B, ...) and the column names, silver; the current
      column's letter cell orange with a filter arrow, its name cell khaki; a round "A" badge in
      the corner; row numbers on the left;
    - the frozen columns stay at the left when the table scrolls sideways, set off by a grey
      double line; the header is set off from the rows the same way;
    - black text (the blue / orange edges the legacy tool's letters show on screen are Windows
      ClearType, not colours); cells that do not apply to their row (Scheme of an input, Expression of a data signal,
      Category of an output, ...) are grey and cannot be edited;
    - the current row and column are tinted light yellow, the current cell has a black frame
      with a small square at its bottom-right corner; an empty row at the end adds a signal.

Use: a click selects a cell; typing, F2 or a double-click edits it (choices in a drop-down list);
Enter goes down. Del clears cells, or deletes the rows selected by their numbers. The arrow of the
current column filters the rows by a value. The editor windows add the legacy Table menu, the
SM Signals Tools toolbar and the Appearance toolbar (cell colours, font, alignment) for these
pages; their commands are the methods of _ListTable below.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import QEvent, QItemSelection, QItemSelectionModel, QModelIndex, QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QImage, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtWidgets import (QAbstractItemDelegate, QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QHeaderView, QLineEdit, QMenu, QStyledItemDelegate,
                               QTableView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from model import CATEGORY_LABELS, Parameter, Signal as Sig, category_label, set_category_label

# colours of the legacy spreadsheet
SILVER = QColor(192, 192, 192)
GRID = QColor(128, 128, 128)
SPLIT = QColor(160, 160, 160)                   # the double line of the frozen columns / header
CURRENT_LETTER = QColor(236, 194, 126)
CURRENT_NAME = QColor(192, 192, 173)
NA = QColor(217, 217, 217)                      # a cell that does not apply
TINT = QColor(255, 255, 230)                    # the current row and column
COMBO_ARROW = 17                                # width of a drop-down arrow, drawn outside the cell
NA_TINT = QColor(217, 217, 196)
BADGE = QColor(255, 255, 150)
FONT_FAMILY = 'Tahoma'
FONT_PT = 8

HEADERS = {'group': 'Group', 'name': 'Name', 'mode': 'Mode', 'type': 'Type', 'signed': 'Signed',
           'bounds': 'Bounds', 'delay': 'Delay', 'value': 'Value', 'category': 'Category', 'assign': 'Assign In',
           'expression': 'Expression', 'scheme': 'Scheme', 'default': 'Default', 'reset': 'Reset',
           'comment': 'Comment', 'pragma': 'Pragma'}

_VA = {'header': {'bg': '#c0c0c0', 'fg': '#000000'}, 'cell': {'bg': '#ffffff', 'fg': '#000000'},
       'group': {'bg': '#9cdeff', 'fg': '#000000'}}
_HEIGHTS = {'#letters': 20, '#title': 23, '#filter': 0, '#row': 20}


def _default(columns: list, fixed: int) -> dict:
    return {'columns': columns, 'fixed_col': fixed, 'fixed_row': 2, 'heights': dict(_HEIGHTS), 'order': [],
            'va': copy.deepcopy(_VA), 'cells': {}}


# the layout of a new diagram's tables, measured on the legacy tool
FSM_SIGNALS_SHEET = _default([['#ref', 20], ['group', 50], ['name', 70], ['mode', 50], ['type', 80],
                              ['signed', 60], ['bounds', 80], ['delay', 40], ['value', 40], ['category', 100],
                              ['assign', 60], ['expression', 130], ['scheme', 56], ['default', 50], ['reset', 50],
                              ['comment', 80]], 4)
BD_SIGNALS_SHEET = _default([['#ref', 20], ['group', 50], ['name', 70], ['mode', 50], ['type', 80], ['signed', 60],
                             ['bounds', 80], ['delay', 40], ['value', 40], ['comment', 80]], 4)
PARAMS_SHEET = _default([['#ref', 20], ['group', 50], ['name', 70], ['value', 100], ['comment', 80]], 3)

# Category: the legacy names; each sets the category and the expression of the signal
CATEGORY_CHOICES = list(CATEGORY_LABELS)        # as the legacy tool lists them (alphabetical)
SCHEME_CHOICES = {'comb': 'Comb', 'clocked': 'Clocked', 'registered': 'Registered', 'none': ''}
CHOICES = {'mode': ['input', 'output', 'inout', 'local'], 'type': ['wire', 'reg', 'logic'],
           'assign': ['<auto>', '<none>'],
           'signed': ['', 'signed'], 'category': CATEGORY_CHOICES, 'scheme': ['Comb', 'Clocked', 'Registered']}
EDITABLE_CHOICES = {'type', 'bounds'}
# columns showing the arrow (not the I-beam) under the mouse, as in the legacy tool
ARROW_COLUMNS = set(CHOICES) | {'expression'}
CURSOR_MARGIN = 3       # the I-beam only this far inside a cell's edges, the arrow on the edges


# the legacy tool's mouse cursor over the cells: an I-beam with a black core and a white outline,
# seen on any cell colour (hot spot at its middle)
_IBEAM = ['oooo...oooo',
          'oo###o###oo',
          'ooooo#ooooo',
          '....o#o....', '....o#o....', '....o#o....', '....o#o....', '....o#o....',
          '....o#o....', '....o#o....', '....o#o....', '....o#o....',
          'ooooo#ooooo',
          'oo###o###oo',
          'oooo...oooo']
_CURSOR: list = []


def cell_cursor() -> QCursor:
    """The I-beam shown over the cells and in a cell being edited."""
    if not _CURSOR:
        img = QImage(32, 32, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        for y, line in enumerate(_IBEAM):
            for x, ch in enumerate(line):
                if ch != '.':
                    img.setPixelColor(x + 2, y, QColor(Qt.black) if ch == '#' else QColor(Qt.white))
        _CURSOR.append(QCursor(QPixmap.fromImage(img), 7, 7))
    return _CURSOR[0]


class _ComboCursor(QObject):
    """In a drop-down editor: the I-beam over its text, the arrow over its button."""

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.MouseMove, QEvent.Enter, QEvent.HoverMove):
            pos = obj.mapFromGlobal(QCursor.pos())
            over_button = isinstance(obj, QComboBox) and pos.x() >= obj.width() - COMBO_ARROW
            obj.setCursor(Qt.ArrowCursor if over_button else cell_cursor())
        return False


def column_letter(k: int) -> str:
    """A, B, ... Z, AA, AB ... as spreadsheet columns are named."""
    s = ''
    k += 1
    while k:
        k, r = divmod(k - 1, 26)
        s = chr(65 + r) + s
    return s


def category_text(s: Sig) -> str:
    """The legacy Category text of a signal: Data, Clock (Rising), Reset (Sync Low), ..."""
    return category_label(s)


def set_category(s: Sig, text: str) -> None:
    """Category picked in the table: the category and the matching expression of the signal."""
    set_category_label(s, text)


def _font(fmt: dict) -> QFont:
    f = QFont(FONT_FAMILY, FONT_PT + (fmt.get('grow', 0)))
    f.setBold(bool(fmt.get('bold')))
    f.setItalic(bool(fmt.get('italic')))
    f.setUnderline(bool(fmt.get('underline')))
    return f


_ALIGN = {'left': Qt.AlignLeft, 'center': Qt.AlignHCenter, 'right': Qt.AlignRight}
_PATTERNS = {'dense': Qt.Dense5Pattern, 'hor': Qt.HorPattern, 'ver': Qt.VerPattern, 'cross': Qt.CrossPattern,
             'bdiag': Qt.BDiagPattern, 'fdiag': Qt.FDiagPattern, 'diagcross': Qt.DiagCrossPattern}


# -- header ---------------------------------------------------------------------------------------------
class _Header(QHeaderView):
    """The two header rows: the letter above the name; the current column's letter cell orange with
    the filter arrow; the grey double line below."""

    def __init__(self, table: '_SheetTable'):
        super().__init__(Qt.Horizontal)
        self.sheet = table
        self.setSectionsClickable(True)
        self.setHighlightSections(False)
        self.setSectionResizeMode(QHeaderView.Interactive)
        self.setMinimumSectionSize(8)

    def sizeHint(self):
        s = super().sizeHint()
        s.setHeight(self.sheet.header_height())
        return s

    def paintSection(self, p: QPainter, rect: QRect, index: int):
        if not rect.isValid():
            return
        t = self.sheet
        p.save()
        cur = t.currentColumn() == index
        marked = index in t.marked_columns()
        lh = t.height_of('#letters')
        fh = t.filter_height()
        top = QRect(rect.left(), rect.top(), rect.width(), lh)
        bottom = QRect(rect.left(), rect.top() + lh, rect.width(), rect.height() - lh - fh - 4)
        attr = t.columns[index]
        fmt = t.owner.title_format(attr)
        p.fillRect(rect, QColor(fmt.get('bg', '#c0c0c0')))
        if cur or marked:
            p.fillRect(top, CURRENT_LETTER)
        if index in t.full_columns():
            p.fillRect(bottom, Qt.black)        # a column selected by its letter: its name cell too
        elif cur:
            p.fillRect(bottom, CURRENT_NAME)
        p.setPen(QPen(GRID, 1))
        p.drawLine(rect.right(), rect.top(), rect.right(), rect.bottom())
        p.drawLine(rect.left(), top.bottom(), rect.right(), top.bottom())
        p.setFont(_font({}))
        p.setPen(Qt.black)
        p.drawText(top, Qt.AlignCenter, column_letter(index))
        f = _font(fmt)
        f.setItalic(f.italic() or index in t.filters)          # a filtered column
        p.setFont(f)
        p.setPen(Qt.white if index in t.full_columns() else QColor(fmt.get('fg', '#000000')))
        p.drawText(bottom.adjusted(3, 0, -3, 0), _ALIGN.get(fmt.get('align', 'center')) | Qt.AlignVCenter,
                   HEADERS.get(attr, attr))
        if cur:
            a = self.arrow_rect(rect)
            p.setBrush(QColor(110, 110, 110)); p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygon([QPoint(a.left() + 1, a.top() + 3), QPoint(a.right() - 1, a.top() + 3),
                                    QPoint(a.center().x(), a.bottom() - 2)]))
        if fh:                                      # the filter row: the value kept and a drop-down arrow
            fr = QRect(rect.left(), bottom.bottom() + 1, rect.width() - 1, fh)
            p.fillRect(fr, Qt.white)
            p.setPen(QPen(GRID, 1))
            p.drawLine(fr.left(), fr.top(), fr.right() + 1, fr.top())
            p.setFont(_font({}))
            p.setPen(Qt.black)
            p.drawText(fr.adjusted(3, 0, -16, 0), Qt.AlignLeft | Qt.AlignVCenter, t.filters.get(index, ''))
            b = self.filter_button(fr)
            p.fillRect(b, QColor(240, 240, 240))
            p.setPen(QPen(GRID, 1)); p.setBrush(Qt.NoBrush); p.drawRect(b)
            p.setBrush(Qt.black); p.setPen(Qt.NoPen)
            c = b.center()
            p.drawPolygon(QPolygon([QPoint(c.x() - 2, c.y() - 1), QPoint(c.x() + 3, c.y() - 1), QPoint(c.x(), c.y() + 2)]))
        _draw_header_split(p, rect.left(), rect.right(), rect.bottom())
        p.restore()

    def arrow_rect(self, rect: QRect) -> QRect:
        return QRect(rect.right() - 14, rect.top() + 2, 11, self.sheet.height_of('#letters') - 4)

    @staticmethod
    def filter_button(fr: QRect) -> QRect:
        return QRect(fr.right() - 13, fr.top() + 4, 11, fr.height() - 7)

    def mousePressEvent(self, e):
        """A click on the filter arrow of the current column, or in the filter row, opens the filter
        menu of that column."""
        index = self.logicalIndexAt(e.position().toPoint())
        t = self.sheet
        fh = t.filter_height()
        if fh and index >= 0 and e.button() == Qt.LeftButton and \
                e.position().y() >= self.height() - fh - 4 and e.position().y() < self.height() - 4:
            x = self.sectionViewportPosition(index)
            t.filter_menu(index, self.mapToGlobal(QPoint(x, self.height())))
            return
        if index == self.sheet.currentColumn() and e.button() == Qt.LeftButton:
            rect = QRect(self.sectionViewportPosition(index), 0, self.sectionSize(index), self.height())
            if self.arrow_rect(rect).adjusted(-3, -3, 3, 3).contains(e.position().toPoint()):
                self.sheet.filter_menu(index, self.mapToGlobal(QPoint(rect.right() - 14, rect.height() // 2)))
                return
        super().mousePressEvent(e)


def _draw_header_split(p: QPainter, left: int, right: int, bottom: int):
    """The double line under the header: white, grey, then the grid line."""
    p.fillRect(QRect(left, bottom - 3, right - left + 1, 2), Qt.white)
    p.fillRect(QRect(left, bottom - 1, right - left + 1, 2), SPLIT)


class _RowHeader(QHeaderView):
    """Row numbers, silver, the current row's tinted."""

    def __init__(self, table: '_SheetTable'):
        super().__init__(Qt.Vertical)
        self.sheet = table
        self.setSectionsClickable(True)
        self.setHighlightSections(False)
        self.setSectionResizeMode(QHeaderView.Fixed)
        self.setMinimumSectionSize(4)                # rows as low as the layout says (20 pixels)

    def sizeHint(self):
        s = super().sizeHint()
        s.setWidth(self.sheet.ref_width())
        return s

    def paintSection(self, p: QPainter, rect: QRect, index: int):
        p.save()
        t = self.sheet
        p.fillRect(rect, CURRENT_LETTER if index in t.marked_rows() else
                   TINT if t.currentRow() == index else QColor(t.owner.va('header').get('bg', '#c0c0c0')))
        p.setPen(QPen(GRID, 1))
        p.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        p.drawLine(rect.right(), rect.top(), rect.right(), rect.bottom())
        p.setPen(Qt.black)
        p.setFont(_font({}))
        p.drawText(rect, Qt.AlignCenter, str(index + 1 + (1 if t.owner.filter_row else 0)))
        p.restore()


# -- cells -----------------------------------------------------------------------------------------------
class _Delegate(QStyledItemDelegate):
    """Draws a cell with its format (see the module docstring) and edits it: a drop-down list for
    the columns with choices, a text box for the others."""

    def __init__(self, table: '_SheetTable'):
        super().__init__(table)
        self.sheet = table

    def paint(self, p: QPainter, option, index: QModelIndex):
        t = self.sheet
        r, c = index.row(), index.column()
        rect = option.rect
        fmt = t.cell_format(r, c)
        na = not t.applies(r, c)
        tinted = r == t.currentRow() or c == t.currentColumn()
        marked = t.is_marked(index)
        p.save()
        if marked:
            bg = QColor(Qt.black)               # selected rows / columns / cells: black, as the legacy tool
        elif na:
            bg = NA_TINT if tinted else NA
        else:
            bg = TINT if tinted and QColor(fmt.get('bg', '#ffffff')) == QColor('#ffffff') else QColor(fmt.get('bg'))
        p.fillRect(rect, bg)
        if fmt.get('pattern') and fmt['pattern'] != 'solid' and not na and not marked:
            p.fillRect(rect, QBrush(QColor(90, 90, 90), _PATTERNS.get(fmt['pattern'], Qt.SolidPattern)))
        p.setFont(_font(fmt))
        fg = QColor(fmt.get('fg', '#000000'))
        if marked:                              # the text in the inverse colour
            fg = QColor(255 - fg.red(), 255 - fg.green(), 255 - fg.blue())
        p.setPen(fg)
        p.drawText(rect.adjusted(3, 0, -3, 0), _ALIGN.get(fmt.get('align', 'center')) | Qt.AlignVCenter,
                   index.data(Qt.DisplayRole) or '')
        if r == t.currentRow() and c == t.currentColumn() and (t.hasFocus() or t.frozen.hasFocus()):
            p.setPen(QPen(Qt.black, 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(rect.adjusted(1, 1, -1, -1))
            p.fillRect(QRect(rect.right() - 4, rect.bottom() - 4, 5, 5), Qt.black)
        p.restore()

    def createEditor(self, parent, option, index):
        choices = self.sheet.choices(index.row(), index.column())
        fmt = self.sheet.cell_format(index.row(), index.column())
        if choices is not None:
            cb = QComboBox(parent)
            cb.setFont(_font(fmt))
            cb.setEditable(self.sheet.columns[index.column()] in EDITABLE_CHOICES)
            cb.addItems(choices)
            cb.setStyleSheet('QComboBox { background: white; border: 1px solid #646464; padding-left: 2px; }'
                             ' QComboBox::drop-down { width: %dpx; }' % COMBO_ARROW)
            # a choice picked in the list is written at once
            cb.setMouseTracking(True)
            cb.setCursor(cell_cursor())
            filt = _ComboCursor(cb)
            cb.installEventFilter(filt)
            cb.installEventFilter(self.sheet)            # Esc ends the edit, see _SheetTable.eventFilter
            if cb.lineEdit() is not None:
                cb.lineEdit().setCursor(cell_cursor())
                cb.lineEdit().installEventFilter(self.sheet)
            cb.activated.connect(lambda _k, cb=cb: (self.commitData.emit(cb),
                                                    self.closeEditor.emit(cb, QAbstractItemDelegate.NoHint)))
            return cb
        ed = QLineEdit(parent)
        ed.setFont(_font(fmt))
        ed.setAlignment(_ALIGN.get(fmt.get('align', 'center')))
        ed.setFrame(False)
        ed.setCursor(cell_cursor())
        ed.installEventFilter(self.sheet)
        return ed

    def setEditorData(self, editor, index):
        text = index.data(Qt.EditRole) or ''
        typed = self.sheet._typed
        if isinstance(editor, QComboBox):
            k = editor.findText(text)
            if k >= 0:
                editor.setCurrentIndex(k)
            elif editor.isEditable():
                editor.setEditText(text)
        else:
            editor.setText(text if typed is None else typed)
            if typed is None:
                editor.selectAll()
        self.sheet._typed = None

    def setModelData(self, editor, model, index):
        text = editor.currentText() if isinstance(editor, QComboBox) else editor.text()
        self.sheet.write(index.row(), index.column(), text.strip())

    def updateEditorGeometry(self, editor, option, index):
        if isinstance(editor, QComboBox):           # the drop-down arrow sits outside the cell, on its right
            editor.setGeometry(option.rect.adjusted(0, 0, COMBO_ARROW, 0))
        else:
            editor.setGeometry(option.rect.adjusted(1, 1, -1, -1))


# -- the sheet ------------------------------------------------------------------------------------------
class _SheetTable(QTableWidget):
    """The spreadsheet of a _ListTable. The frozen columns are a second view (`frozen`) over the
    same model and selection, laid over the left of this one."""
    changed = Signal()

    def __init__(self, owner: '_ListTable'):
        super().__init__(0, 0)
        self.owner = owner
        self.columns: list[str] = []
        self.filters: dict[int, str] = {}
        self._typed: str | None = None
        self.setHorizontalHeader(_Header(self))
        self.setVerticalHeader(_RowHeader(self))
        self.setItemDelegate(_Delegate(self))
        self.setShowGrid(True)
        self.setStyleSheet('QTableView { gridline-color: #808080; background: white; } '
                           'QHeaderView { background: white; }')          # white below the rows
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # as the legacy tool: the mouse is an I-beam over the cells, a click starts editing the cell
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)
        self.setMouseTracking(True)
        self._pressed = None
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setWordWrap(False)
        self.setCornerButtonEnabled(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: self._popup(self.viewport().mapToGlobal(pos),
                                                                        self.indexAt(pos)))
        self.frozen = _FrozenView(self)
        self.horizontalHeader().sectionResized.connect(self._column_resized)
        self.currentCellChanged.connect(lambda *a: self.repaint_all())
        self.selectionModel().selectionChanged.connect(lambda *a: self.repaint_all())

    # -- selection ----------------------------------------------------------------------------
    def is_marked(self, index: QModelIndex) -> bool:
        """Whether a cell is drawn selected (black): it is selected and the selection is more than
        the one cell a click puts the cursor in."""
        sm = self.selectionModel()
        return sm.isSelected(index) and len(sm.selectedIndexes()) > 1

    def marked_rows(self) -> set[int]:
        """Rows with a cell drawn selected (their numbers are tinted, as in the legacy tool)."""
        idx = self.selectionModel().selectedIndexes()
        return {i.row() for i in idx} if len(idx) > 1 else set()

    def marked_columns(self) -> set[int]:
        """Columns with a cell drawn selected (their letters are tinted)."""
        idx = self.selectionModel().selectedIndexes()
        return {i.column() for i in idx} if len(idx) > 1 else set()

    def full_columns(self) -> set[int]:
        """Columns selected whole (by their letter)."""
        sm = self.selectionModel()
        if self.rowCount() < 2:
            return set()
        return {c for c in range(self.columnCount()) if sm.isColumnSelected(c, QModelIndex())}

    def full_rows(self) -> list[int]:
        """Rows selected whole (by their number), in display order."""
        sm = self.selectionModel()
        return [r for r in range(self.rowCount()) if sm.isRowSelected(r, QModelIndex())]

    # -- layout -------------------------------------------------------------------------------
    @property
    def rows(self) -> list:
        return self.owner.display_rows()

    def height_of(self, key: str) -> int:
        return int(self.owner.layout()['heights'].get(key, _HEIGHTS[key]))

    def filter_height(self) -> int:
        """Height of the filter row (Toggle Filter), 0 while it is hidden."""
        return (self.height_of('#filter') or 20) if self.owner.filter_row else 0

    def header_height(self) -> int:
        return self.height_of('#letters') + self.height_of('#title') + self.filter_height() + 4

    def ref_width(self) -> int:
        return int(next((w for a, w in self.owner.layout()['columns'] if a == '#ref'), 20))

    def fixed(self) -> int:
        """The frozen data columns (the file's fixedCol counts the row number column)."""
        return max(0, min(int(self.owner.layout().get('fixed_col', 1)) - 1, len(self.columns)))

    def apply_layout(self):
        """Columns, widths and heights from the layout."""
        lay = self.owner.layout()
        self.columns = [a for a, _ in lay['columns'] if not a.startswith('#') and a in self.owner.known]
        self.blockSignals(True)
        self.setColumnCount(len(self.columns))
        widths = dict((a, w) for a, w in lay['columns'])
        for k, a in enumerate(self.columns):
            self.horizontalHeader().resizeSection(k, int(widths.get(a, 60)))
        self.blockSignals(False)
        self.horizontalHeader().setFixedHeight(self.header_height())
        self.verticalHeader().setFixedWidth(self.ref_width())
        self.verticalHeader().setDefaultSectionSize(self.height_of('#row'))
        self.frozen.apply_layout()

    def refresh(self):
        """Show the rows again (texts, the empty last row, the filters)."""
        cur = (self.currentRow(), self.currentColumn())
        rows = self.rows
        self.blockSignals(True)
        self.setRowCount(len(rows) + 1)
        for r in range(len(rows) + 1):
            for c, attr in enumerate(self.columns):
                text = self.owner.text(rows[r], attr) if r < len(rows) else ''
                it = self.item(r, c)
                if it is None:
                    it = QTableWidgetItem()
                    self.setItem(r, c, it)
                it.setText(text)
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
                if self.applies(r, c) and not self.owner.readonly:
                    flags |= Qt.ItemIsEditable
                it.setFlags(flags)
            self.setRowHeight(r, self.height_of('#row'))
        self.blockSignals(False)
        self.apply_filters()
        if cur[0] >= 0:
            self.setCurrentCell(min(cur[0], self.rowCount() - 1), max(cur[1], 0))
        self.repaint_all()

    def repaint_all(self):
        for v in (self, self.frozen):
            v.viewport().update()
            v.horizontalHeader().viewport().update()
            v.verticalHeader().viewport().update()

    def _column_resized(self, index: int, _old: int, new: int):
        if 0 <= index < len(self.columns):
            self.owner.set_width(self.columns[index], new)
        self.frozen.apply_layout()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.frozen.place()

    def scrollTo(self, index, hint=QAbstractItemView.EnsureVisible):
        """Keep a cell of the scrolling columns clear of the frozen ones."""
        if index.column() >= self.fixed():
            super().scrollTo(index, hint)

    def cell_format(self, r: int, c: int) -> dict:
        rows = self.rows
        return self.owner.cell_format(rows[r] if r < len(rows) else None, self.columns[c])

    def applies(self, r: int, c: int) -> bool:
        rows = self.rows
        if r >= len(rows):
            return True
        return self.owner.applies(rows[r], self.columns[c])

    def choices(self, r: int, c: int) -> list[str] | None:
        rows = self.rows
        return self.owner.choices(rows[r] if r < len(rows) else None, self.columns[c])

    def write(self, r: int, c: int, text: str):
        """A cell was edited: into its row object (a new row for the empty last row)."""
        self.owner.write(r, self.columns[c], text)

    # -- filters --------------------------------------------------------------------------------
    def apply_filters(self):
        rows = self.rows
        for r in range(self.rowCount()):
            hide = r < len(rows) and any(self.owner.text(rows[r], self.columns[c]) != v
                                         for c, v in self.filters.items() if c < len(self.columns))
            self.setRowHidden(r, hide)
            self.frozen.setRowHidden(r, hide)
        self.horizontalHeader().viewport().update()

    def filter_menu(self, c: int, pos: QPoint):
        """The filter arrow: (All) or one of the values of the column."""
        m = QMenu(self)
        a = m.addAction('(All)')
        a.setCheckable(True); a.setChecked(c not in self.filters)
        a.triggered.connect(lambda: self.set_filter(c, None))
        for v in sorted({self.owner.text(row, self.columns[c]) for row in self.rows}, key=str.lower):
            b = m.addAction(v or '(Blanks)')
            b.setCheckable(True); b.setChecked(self.filters.get(c) == v)
            b.triggered.connect(lambda checked=False, v=v: self.set_filter(c, v))
        m.exec(pos)

    def set_filter(self, c: int, value: str | None):
        if value is None:
            self.filters.pop(c, None)
        else:
            self.filters[c] = value
        self.apply_filters()

    # -- interaction -------------------------------------------------------------------------------
    def _popup(self, global_pos: QPoint, idx: QModelIndex):
        if idx.isValid():
            self.setCurrentCell(idx.row(), idx.column())
        o = self.owner
        m = QMenu(self)
        m.addAction('Cut', o.cut).setEnabled(not o.readonly)
        m.addAction('Copy', o.copy)
        m.addAction('Paste', o.paste).setEnabled(not o.readonly)
        m.addAction('Delete', o.delete).setEnabled(not o.readonly)
        m.addSeparator()
        m.addAction('Insert Row', o.insert_row).setEnabled(not o.readonly)
        m.addSeparator()
        m.addAction('Sort Ascending', lambda: o.sort(False))
        m.addAction('Sort Descending', lambda: o.sort(True))
        m.addAction('Hide Column', o.hide_column)
        m.addSeparator()
        m.addAction('Clear Filters', o.clear_filters).setEnabled(bool(self.filters))
        m.exec(global_pos)

    def edit_current(self, typed: str | None = None, popup: bool = False):
        """Edit the current cell (in the frozen view when it is a frozen column); `popup`: open
        the drop-down list of a cell with choices."""
        it = self.currentItem()
        if it is None or not it.flags() & Qt.ItemIsEditable:
            return
        if typed is not None and self.choices(it.row(), it.column()) is None:
            self._typed = typed
        view = self.frozen if it.column() < self.fixed() else self
        idx = self.model().index(it.row(), it.column())
        view.edit(idx)
        ed = view.indexWidget(idx)
        if popup and isinstance(ed, QComboBox):
            QTimer.singleShot(0, ed.showPopup)

    def click_edit(self, view: QAbstractItemView, e, release: bool):
        """A plain left click (press and release in the same cell, no drag, no Shift / Ctrl) starts
        editing that cell; a drop-down list opens at once."""
        idx = view.indexAt(e.position().toPoint())
        if not release:
            plain = e.button() == Qt.LeftButton and not e.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier)
            self._pressed = idx if plain and idx.isValid() else None
            return
        start, self._pressed = self._pressed, None
        if start is None or start != idx or e.button() != Qt.LeftButton or self.owner.readonly:
            return
        if len(self.selectionModel().selectedIndexes()) > 1:
            return
        self.edit_current(popup=True)

    def update_cursor(self, view: QAbstractItemView, pos: QPoint):
        """The legacy tool's cursor: the I-beam inside a text cell (not on its edges), the arrow on
        the edges, over drop-down / check columns and over grey cells that do not apply."""
        idx = view.indexAt(pos)
        ibeam = False
        if idx.isValid() and not self.owner.readonly:
            m = CURSOR_MARGIN
            inner = view.visualRect(idx).adjusted(m, m, -m - 1, -m - 1)
            ibeam = (inner.contains(pos) and self.columns[idx.column()] not in ARROW_COLUMNS
                     and self.applies(idx.row(), idx.column()))
        view.viewport().setCursor(cell_cursor() if ibeam else Qt.ArrowCursor)

    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)
        self.update_cursor(self, e.position().toPoint())

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        self.click_edit(self, e, False)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        self.click_edit(self, e, True)

    def event(self, e):
        """Esc belongs to the table (not to the window's Select shortcut, which shows the diagram)."""
        if e.type() == QEvent.ShortcutOverride and e.key() == Qt.Key_Escape:
            e.accept()
            return True
        return super().event(e)

    def eventFilter(self, obj, e):
        """An editor of a cell keeps Esc too (it ends the edit)."""
        if e.type() == QEvent.ShortcutOverride and e.key() == Qt.Key_Escape:
            e.accept()
        return super().eventFilter(obj, e)

    def unselect(self):
        """Esc out of editing: no cell selected (as the legacy tool, the second Esc)."""
        self.selectionModel().clearSelection()
        self.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.NoUpdate)
        self.repaint_all()

    def keyPressEvent(self, e):
        """Typing starts editing the current cell; Del clears cells or deletes the rows selected by
        their numbers; Enter goes down."""
        if e.key() == Qt.Key_Escape and self.state() != QAbstractItemView.EditingState:
            self.unselect()
            return
        if self.state() != QAbstractItemView.EditingState and not self.owner.readonly:
            if e.key() == Qt.Key_Delete:
                self.owner.delete()
                return
            if e.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.setCurrentCell(min(self.currentRow() + 1, self.rowCount() - 1), self.currentColumn())
                return
            if e.key() == Qt.Key_F2:
                self.edit_current()
                return
            text = e.text()
            if text and text.isprintable() and not e.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
                self.edit_current(text)
                return
        super().keyPressEvent(e)

    def closeEditor(self, editor, hint):
        """Enter in an editor commits it and goes to the cell below."""
        super().closeEditor(editor, hint)
        self.setFocus()                     # the keys (Esc, typing) go to the table again
        if hint == QAbstractItemDelegate.SubmitModelCache:
            self.setCurrentCell(min(self.currentRow() + 1, self.rowCount() - 1), self.currentColumn())

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.repaint_all()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.repaint_all()


class _FrozenView(QTableView):
    """The frozen columns (and the row numbers): a view over the sheet's model and selection laid
    over its left part, which does not scroll sideways; a grey double line on its right."""

    def __init__(self, sheet: _SheetTable):
        super().__init__(sheet)
        self.sheet = sheet
        self.setModel(sheet.model())
        self.setSelectionModel(sheet.selectionModel())
        self.setItemDelegate(_Delegate(sheet))
        self.setHorizontalHeader(_Header(sheet))
        self.setVerticalHeader(_RowHeader(sheet))
        self.setStyleSheet('QTableView { gridline-color: #808080; background: white; border: none; } '
                           'QHeaderView { background: white; }')
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(sheet.editTriggers())
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: sheet._popup(self.viewport().mapToGlobal(pos),
                                                                         self.indexAt(pos)))
        self.horizontalHeader().sectionResized.connect(self._resized)
        sheet.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)
        self.verticalScrollBar().valueChanged.connect(sheet.verticalScrollBar().setValue)
        self._badge = _Badge(self)
        self.show()

    def apply_layout(self):
        s = self.sheet
        n = s.fixed()
        self.horizontalHeader().blockSignals(True)
        for k in range(s.columnCount()):
            self.setColumnHidden(k, k >= n)
            if k < n:
                self.setColumnWidth(k, s.columnWidth(k))
        self.horizontalHeader().blockSignals(False)
        self.horizontalHeader().setFixedHeight(s.header_height())
        self.verticalHeader().setFixedWidth(s.ref_width())
        self.verticalHeader().setDefaultSectionSize(s.height_of('#row'))
        for r in range(s.rowCount()):
            self.setRowHeight(r, s.rowHeight(r))
        self.place()

    def _resized(self, index: int, _old: int, new: int):
        if index < self.sheet.fixed() and self.sheet.columnWidth(index) != new:
            self.sheet.setColumnWidth(index, new)

    def place(self):
        """Over the left of the sheet: row numbers and frozen columns, the sheet's height."""
        s = self.sheet
        w = s.verticalHeader().width() + sum(s.columnWidth(k) for k in range(s.fixed())) + 2
        fw = s.frameWidth()
        self.setGeometry(fw, fw, w, s.viewport().height() + s.horizontalHeader().height())
        self._badge.place()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.sheet.fixed():                      # the double line after the frozen columns
            p = QPainter(self.viewport())
            x = self.viewport().width()
            p.fillRect(QRect(x - 3, 0, 2, self.viewport().height()), SPLIT)
            p.setPen(QPen(GRID, 1))
            p.drawLine(x - 1, 0, x - 1, self.viewport().height())

    def keyPressEvent(self, e):
        self.sheet.keyPressEvent(e)

    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)
        self.sheet.update_cursor(self, e.position().toPoint())

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        self.sheet.click_edit(self, e, False)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        self.sheet.click_edit(self, e, True)


class _Badge(QWidget):
    """The round "A" badge in the corner of the table."""

    def __init__(self, view: QTableView):
        super().__init__(view)
        self.view = view
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def place(self):
        self.setGeometry(0, 0, self.view.verticalHeader().width(), self.view.horizontalHeader().height())
        self.raise_()

    def paintEvent(self, e):
        t = self.view.sheet
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(t.owner.va('header').get('bg', '#c0c0c0')))
        p.setPen(QPen(GRID, 1))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        lh = t.height_of('#letters')
        p.drawLine(0, lh - 1, self.width(), lh - 1)
        side = min(self.width() - 4, 14)
        th = t.height_of('#title')
        r = QRect((self.width() - side) // 2, lh + (th - side) // 2, side, side)
        p.setBrush(BADGE); p.setPen(QPen(Qt.black, 1))
        p.drawEllipse(r)
        f = _font({'bold': True})
        p.setFont(f)
        p.drawText(r, Qt.AlignCenter, 'A')
        fh = t.filter_height()
        if fh:                                      # the filter row: a funnel
            top = self.height() - 4 - fh
            p.setPen(QPen(GRID, 1)); p.drawLine(0, top, self.width(), top)
            cx = self.width() // 2
            p.setBrush(QColor(255, 220, 60)); p.setPen(QPen(QColor(90, 70, 0), 1))
            p.drawPolygon(QPolygon([QPoint(cx - 6, top + 4), QPoint(cx + 6, top + 4), QPoint(cx + 1, top + 10),
                                    QPoint(cx + 1, top + fh - 3), QPoint(cx - 1, top + fh - 4),
                                    QPoint(cx - 1, top + 10)]))
        _draw_header_split(p, 0, self.width(), self.height() - 1)


# -- the pages ---------------------------------------------------------------------------------------------
class _ListTable(QWidget):
    """A page of the editor: the spreadsheet of a list of rows and its layout (see the module
    docstring). Subclasses give the text of a cell, how a typed value is stored, which cells
    apply and the choices."""
    changed = Signal()
    DEFAULT: dict = {}
    ENTRY = 'Row'

    def __init__(self, parent=None, default: dict | None = None, known: set[str] | None = None):
        super().__init__(parent)
        self.rows: list = []
        self.sheet: dict = {}
        self.readonly = False
        self.default = default or self.DEFAULT
        self.known = known or {a for a, _ in self.default['columns']}
        self.grouped = False
        self.filter_row = False                 # Toggle Filter: the filter row is shown
        self.table = _SheetTable(self)
        self.table.changed.connect(self.changed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.table)

    @property
    def columns(self) -> list[str]:
        return self.table.columns

    # -- model ------------------------------------------------------------------------------------
    def set_rows(self, rows: list, sheet: dict | None = None):
        """Show `rows` with the layout `sheet` (both kept by reference: edits change them)."""
        self.rows = rows
        if sheet is not None:
            self.sheet = sheet
        self.table.apply_layout()
        self.table.refresh()

    def set_readonly(self, on: bool):
        self.readonly = on
        self.table.refresh()

    def layout(self) -> dict:
        """The layout in use: the view's, or a new diagram's."""
        return self.sheet if self.sheet.get('columns') else self.default

    def _own(self) -> dict:
        """The view's layout, made from the default the first time it is changed."""
        if not self.sheet.get('columns'):
            self.sheet.update(copy.deepcopy(self.default))
        return self.sheet

    def va(self, which: str) -> dict:
        return self.layout().get('va', {}).get(which, _VA[which])

    def display_rows(self) -> list:
        """The rows in display order (the layout's order, rows it does not list at the end)."""
        order = {n: k for k, n in enumerate(self.layout().get('order', []))}
        rows = sorted(self.rows, key=lambda r: order.get(r.name, len(order)))
        if self.grouped:
            rows.sort(key=lambda r: (not r.group, r.group.lower()))
        return rows

    def _set_order(self, rows: list):
        self._own()['order'] = [r.name for r in rows]

    def column_of(self, attr: str) -> int:
        return self.table.columns.index(attr) if attr in self.table.columns else -1

    def row_of(self, obj) -> int:
        rows = self.display_rows()
        return rows.index(obj) if obj in rows else -1

    def edit_cell(self, row_obj, attr: str):
        """Make the cell of `row_obj` / `attr` current and start editing it."""
        r = self.row_of(row_obj) if not isinstance(row_obj, int) else row_obj
        c = self.column_of(attr)
        if r < 0 or c < 0:
            return
        self.table.setCurrentCell(r, c)
        self.table.setFocus()
        self.table.edit_current()

    def set_width(self, attr: str, width: int):
        cols = self._own()['columns']
        for item in cols:
            if item[0] == attr and item[1] != width:
                item[1] = width
                self.changed.emit()

    # -- formats ------------------------------------------------------------------------------------
    def cell_format(self, row, attr: str) -> dict:
        fmt = dict(self.va('cell'))
        if row is not None:
            fmt.update(self.layout().get('cells', {}).get(f'{row.name}|{attr}', {}))
        return fmt

    def title_format(self, attr: str) -> dict:
        fmt = dict(self.va('header'))
        fmt.update(self.layout().get('cells', {}).get(f'#title|{attr}', {}))
        return fmt

    def selected_cells(self) -> list[tuple[object, str]]:
        rows = self.display_rows()
        out = [(rows[i.row()], self.table.columns[i.column()]) for i in self.table.selectedIndexes()
               if i.row() < len(rows)]
        if not out and 0 <= self.table.currentRow() < len(rows) and self.table.currentColumn() >= 0:
            out = [(rows[self.table.currentRow()], self.table.columns[self.table.currentColumn()])]
        return out

    def set_format(self, **changes):
        """Appearance toolbar: change the format of the selected cells (bg, fg, align, bold, italic,
        underline; grow = +1 / -1 for the font size)."""
        cells = self._own().setdefault('cells', {})
        done = False
        for row, attr in self.selected_cells():
            key = f'{row.name}|{attr}'
            fmt = cells.setdefault(key, {})
            for k, v in changes.items():
                if k == 'grow':
                    fmt['grow'] = max(-3, min(8, fmt.get('grow', 0) + v))
                elif k in ('bold', 'italic', 'underline') and v is None:
                    fmt[k] = not fmt.get(k, False)
                else:
                    fmt[k] = v
            done = True
        if done:
            self.table.repaint_all()
            self.changed.emit()

    # -- editing ------------------------------------------------------------------------------------
    def write(self, r: int, attr: str, text: str):
        """Cell (display row r, attr) was edited (a new row for the empty last row)."""
        rows = self.display_rows()
        if r >= len(rows):
            if not text:
                return
            row = self.new_row(text if attr == 'name' else None)
            if attr == 'name' and row.name != text:
                return
            self.rows.append(row)
            self._set_order(rows + [row])
            if attr != 'name':
                self.set_value(row, attr, text)
        else:
            row = rows[r]
            if self.text(row, attr) == text:
                return
            old = row.name
            if not self.set_value(row, attr, text):
                return
            if attr == 'name':
                self._renamed(old, row.name)
        self.table.refresh()
        self.changed.emit()

    def _renamed(self, old: str, new: str):
        """A row renamed: its place and its cell formats follow."""
        lay = self.sheet
        if not lay.get('columns'):
            return
        lay['order'] = [new if n == old else n for n in lay.get('order', [])]
        cells = lay.get('cells', {})
        for key in [k for k in cells if k.startswith(old + '|')]:
            cells[new + key[len(old):]] = cells.pop(key)

    def insert_row(self):
        """Insert a new row above the current one."""
        rows = self.display_rows()
        r = self.table.currentRow()
        r = len(rows) if r < 0 or r > len(rows) else r
        row = self.new_row(None)
        self.rows.append(row)
        self._set_order(rows[:r] + [row] + rows[r:])
        self.table.refresh()
        self.table.setCurrentCell(r, max(self.column_of('name'), 0))
        self.changed.emit()

    def delete_rows(self, display_rows: list[int]):
        rows = self.display_rows()
        dead = [rows[r] for r in display_rows if r < len(rows)]
        for row in dead:
            self.rows.remove(row)
        if dead:
            if self.sheet.get('columns'):
                self.sheet['order'] = [n for n in self.sheet.get('order', []) if n not in {d.name for d in dead}]
            self.table.refresh()
            self.changed.emit()

    def delete(self):
        """Edit > Delete / Del: the rows selected by their numbers, else empty the selected cells."""
        if self.readonly:
            return
        t = self.table
        full = [r for r in range(t.rowCount()) if t.selectionModel().isRowSelected(r, QModelIndex())]
        if full:
            self.delete_rows(full)
            return
        done = False
        for row, attr in self.selected_cells():
            r, c = self.row_of(row), self.column_of(attr)
            if attr != 'name' and t.applies(r, c) and self.choices(row, attr) is None:
                done = self.set_value(row, attr, '') or done
        if done:
            t.refresh()
            self.changed.emit()

    def copy(self) -> str:
        """Edit > Copy: the selected cells as tab-separated text (rows by lines)."""
        idx = sorted(self.table.selectedIndexes(), key=lambda i: (i.row(), i.column()))
        if not idx and self.table.currentItem() is not None:
            idx = [self.table.currentIndex()]
        lines: dict[int, list[str]] = {}
        for i in idx:
            lines.setdefault(i.row(), []).append(i.data() or '')
        text = '\n'.join('\t'.join(v) for _, v in sorted(lines.items()))
        QApplication.clipboard().setText(text)
        return text

    def cut(self):
        self.copy()
        self.delete()

    def paste(self):
        """Edit > Paste: tab-separated text from the clipboard. Whole rows (copied by their numbers: one
        value per column) become new rows, as in the legacy tool: below the current row, or at the end
        from the empty last row, each name made unique (clk -> clk1). Other text goes into the cells
        from the current cell on."""
        text = QApplication.clipboard().text()
        if self.readonly or not text:
            return
        lines = text.rstrip('\n').split('\n')
        cols = self.table.columns
        if 'name' in cols and all(len(line.split('\t')) == len(cols) for line in lines):
            self.paste_rows([dict(zip(cols, line.split('\t'))) for line in lines])
            return
        r0, c0 = max(self.table.currentRow(), 0), max(self.table.currentColumn(), 0)
        for dr, line in enumerate(text.rstrip('\n').split('\n')):
            for dc, value in enumerate(line.split('\t')):
                c = c0 + dc
                if c < len(self.table.columns):
                    self.write(r0 + dr, self.table.columns[c], value.strip())

    def paste_rows(self, values: list[dict]):
        """New rows from `values` (attr -> text each) below the current row (at the end from the empty
        last row or with no current row); the new rows are selected."""
        rows = self.display_rows()
        r = self.table.currentRow()
        at = len(rows) if r < 0 or r >= len(rows) else r + 1
        new = []
        for v in values:
            base = v.get('name', '').strip()
            row = self.new_row(self._copy_name(base) if base else None)
            for attr, value in v.items():
                if attr != 'name' and value.strip() and self.applies(row, attr):
                    self.set_value(row, attr, value.strip())
            self.rows.append(row)
            new.append(row)
        self._set_order(rows[:at] + new + rows[at:])
        self.table.refresh()
        m = self.table.model()
        self.table.setCurrentCell(at, max(self.column_of('name'), 0))
        self.table.selectionModel().select(
            QItemSelection(m.index(at, 0), m.index(at + len(new) - 1, m.columnCount() - 1)),
            QItemSelectionModel.ClearAndSelect)
        self.changed.emit()

    def _copy_name(self, base: str) -> str:
        """The name of a pasted row: `base` when it is free, else base1, base2, ... (legacy tool)."""
        names = {r.name for r in self.rows}
        if base not in names:
            return base
        k = 1
        while f'{base}{k}' in names:
            k += 1
        return f'{base}{k}'

    def select_all(self):
        self.table.selectAll()

    # -- Table menu ----------------------------------------------------------------------------------
    def sort(self, descending: bool = False):
        """Table > Columns > Sort Ascending / Descending by the current column (the display order)."""
        c = max(self.table.currentColumn(), 0)
        attr = self.table.columns[c]
        rows = sorted(self.display_rows(), key=lambda r: self.text(r, attr).lower(), reverse=descending)
        self._set_order(rows)
        self.table.refresh()
        self.changed.emit()

    def hide_column(self):
        """Table > Columns > Hide Column: the current column."""
        c = self.table.currentColumn()
        if c < 0 or self.table.columns[c] == 'name':
            return
        attr = self.table.columns[c]
        lay = self._own()
        lay.setdefault('hidden', []).append([a for a in lay['columns'] if a[0] == attr][0])
        lay['columns'] = [a for a in lay['columns'] if a[0] != attr]
        if c < self.table.fixed():
            lay['fixed_col'] = max(1, lay.get('fixed_col', 1) - 1)
        self.table.apply_layout(); self.table.refresh()
        self.changed.emit()

    def show_columns(self, parent=None):
        """Table > Columns > Show Columns...: tick the columns to show."""
        lay = self._own()
        shown = [a for a, _ in lay['columns'] if not a.startswith('#')]
        every = [a for a, _ in self.default['columns'] if not a.startswith('#')]
        every += [a for a in shown if a not in every]
        dlg = QDialog(parent or self)
        dlg.setWindowTitle('Show Columns')
        v = QVBoxLayout(dlg)
        boxes = {}
        for a in every:
            boxes[a] = QCheckBox(HEADERS.get(a, a))
            boxes[a].setChecked(a in shown)
            boxes[a].setEnabled(a != 'name')
            v.addWidget(boxes[a])
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if not dlg.exec():
            return
        widths = {a: w for a, w in lay['columns'] + lay.get('hidden', []) + self.default['columns']}
        keep = [[a, w] for a, w in lay['columns'] if a.startswith('#') or boxes.get(a, None) is None
                or boxes[a].isChecked()]
        for a in every:
            if boxes[a].isChecked() and a not in [x for x, _ in keep]:
                keep.append([a, widths.get(a, 60)])
        lay['columns'] = keep
        self.table.apply_layout(); self.table.refresh()
        self.changed.emit()

    def autofit(self):
        """Table > Autofit: every column as wide as its widest text."""
        t = self.table
        for c in range(len(t.columns)):
            t.resizeColumnToContents(c)
            t.setColumnWidth(c, max(t.columnWidth(c), 30))
        t.frozen.apply_layout()

    def filter_current(self):
        """Table > Filter: the filter menu of the current column."""
        c = max(self.table.currentColumn(), 0)
        h = self.table.horizontalHeader()
        self.table.filter_menu(c, h.mapToGlobal(QPoint(h.sectionViewportPosition(c), h.height())))

    def set_filter_row(self, on: bool):
        """Table > Filter / Toggle Filter: show the filter row (hiding it drops the filters)."""
        self.filter_row = on
        if not on:
            self.table.filters.clear()
        self.table.apply_layout()
        self.table.refresh()

    def clear_filters(self):
        self.table.filters.clear()
        self.table.apply_filters()

    def export(self, parent, sep: str):
        """Table > Export > TSV / CSV file...: the table as shown."""
        kind = 'TSV (Tab delimited)' if sep == '\t' else 'CSV (Comma delimited)'
        path, _ = QFileDialog.getSaveFileName(parent, 'Export', '', f'{kind} (*.{"tsv" if sep == chr(9) else "csv"})')
        if not path:
            return None
        import csv
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f, delimiter=sep)
            w.writerow([HEADERS.get(a, a) for a in self.table.columns])
            for row in self.display_rows():
                w.writerow([self.text(row, a) for a in self.table.columns])
        return path

    def group_selected(self, name: str):
        """Table > Group > Group / UnGroup: the group of the selected rows."""
        rows = {row for row, _ in self.selected_cells()}
        for row in rows:
            row.group = name
        if rows:
            self.table.refresh()
            self.changed.emit()

    def set_grouped(self, on: bool):
        """Table > Show Grouped: the rows of a group together."""
        self.grouped = on
        self.table.refresh()

    # -- for subclasses -----------------------------------------------------------------------------
    def text(self, row, attr: str) -> str:
        val = getattr(row, attr, '')
        return 'signed' if val is True else '' if val is False or val is None else str(val)

    def set_value(self, row, attr: str, text: str) -> bool:
        """Store a typed value; False when it is refused (an empty or duplicate name)."""
        if attr == 'name':
            if not text or any(r is not row and r.name == text for r in self.rows):
                return False
        cur = getattr(row, attr, '')
        setattr(row, attr, text.lower() in ('signed', 'yes', 'true', '1') if isinstance(cur, bool) else text)
        return True

    def applies(self, row, attr: str) -> bool:
        return True

    def choices(self, row, attr: str) -> list[str] | None:
        return list(CHOICES[attr]) if attr in CHOICES else None

    def new_row(self, name: str | None):
        raise NotImplementedError

    def _free(self, base: str) -> str:
        names = {r.name for r in self.rows}
        k = 0
        while f'{base}{k}' in names:
            k += 1
        return f'{base}{k}'


class SignalsTable(_ListTable):
    """The Signals Table: ports and internal signals. `kind` 'fsm' has the state machine columns
    (Category, Assign In, Expression, Scheme, Default, Reset), 'bd' the block diagram ones."""
    DEFAULT = FSM_SIGNALS_SHEET
    ENTRY = 'Signal'

    def __init__(self, parent=None, kind: str = 'fsm'):
        default = BD_SIGNALS_SHEET if kind == 'bd' else FSM_SIGNALS_SHEET
        super().__init__(parent, default, set(HEADERS) - {'pragma'})
        self.kind = kind

    def new_row(self, name: str | None):
        """A new data input (the legacy tool's new row: input, wire, Data)."""
        return Sig(name=name or self._free('sig'), mode='input', type='wire')

    def text(self, row: Sig, attr: str) -> str:
        if attr == 'category':
            return category_text(row)
        if attr == 'scheme':
            if row.mode not in ('output', 'local'):
                return ''
            return 'N/A' if row.scheme == 'none' else SCHEME_CHOICES.get(row.scheme, row.scheme)
        if attr == 'assign':
            if row.mode in ('output', 'local') and self.kind == 'fsm':
                return '<none>' if row.scheme == 'none' else '<auto>'
            return ''
        return super().text(row, attr)

    def set_value(self, row: Sig, attr: str, text: str) -> bool:
        if attr == 'category':
            set_category(row, text)
            return True
        if attr == 'scheme':
            row.scheme = {v: k for k, v in SCHEME_CHOICES.items() if v}.get(text, text.lower() or 'none')
            return True
        if attr == 'assign':                    # <none>: not assigned by the machine (no scheme)
            if text == '<none>':
                row.scheme = 'none'
            elif row.scheme == 'none':
                row.scheme = 'comb'
            return True
        if attr == 'mode':
            if text not in CHOICES['mode']:
                return False
            row.mode = text
            if text in ('output', 'local'):
                row.category, row.expression = 'data', ''
                if row.scheme == 'none' and self.kind == 'fsm':
                    row.scheme = 'comb'
            return True
        if attr == 'name' and self.kind == 'fsm' and row.category in ('clock', 'reset', 'enable'):
            old = row.name
            if not super().set_value(row, attr, text):
                return False
            row.expression = row.expression.replace(old, text)        # "posedge clk" follows the name
            return True
        return super().set_value(row, attr, text)

    def applies(self, row: Sig, attr: str) -> bool:
        """The legacy tool's grey cells: Scheme, Default and Reset of inputs; the Expression of data
        signals and outputs; the Category of outputs; the Reset of signals that are not clocked;
        Assign In (<auto> / <none>) only for outputs and locals; Scheme, Default and Reset of a
        signal not assigned (<none>) are N/A."""
        if self.kind != 'fsm':
            return True
        out = row.mode in ('output', 'local')
        if attr in ('scheme', 'default'):
            return out and row.scheme != 'none'
        if attr == 'reset':
            return out and row.scheme in ('clocked', 'registered')
        if attr == 'assign':
            return out
        if attr == 'expression':
            return not out and row.category != 'data'
        if attr == 'category':
            return row.mode != 'output'
        return True

    def choices(self, row, attr: str) -> list[str] | None:
        if attr == 'bounds':                           # the ranges already used, to pick one again
            return [''] + sorted({r.bounds for r in self.rows if r.bounds})
        return super().choices(row, attr)


class ParametersTable(_ListTable):
    """The Parameters Table: module parameters of the view (Group, Name | Value, Comment)."""
    DEFAULT = PARAMS_SHEET
    ENTRY = 'Parameter'

    def __init__(self, parent=None, kind: str = 'fsm'):
        super().__init__(parent, PARAMS_SHEET, {'group', 'name', 'value', 'comment', 'type'})
        self.kind = kind

    def new_row(self, name: str | None):
        """A new parameter PARAM<n> = 0."""
        return Parameter(name=name or self._free('PARAM'), value='0')

    def choices(self, row, attr: str) -> list[str] | None:
        if attr == 'type':
            return ['', 'integer', 'real', 'time', 'string']
        return None
