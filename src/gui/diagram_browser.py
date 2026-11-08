"""The Diagram Browser of the diagram editors, drawn like the legacy tool: on the right of the
window, a "Structure Navigator" pane (the tables, the design unit and its parts) above a
"Content" pane, each with a title bar (blue while it has the focus, grey otherwise) and a small
button that gives the whole height to that pane; the "Content List" / "Flow Help" tabs at the
bottom; and a grey strip along the right edge with a vertical "Diagram Browser" tab that hides or
shows the browser.

The trees are drawn in the classic Windows look of the legacy tool: dotted branch lines, +/-
boxes, Tahoma 8, the selection only behind the text (blue, or grey when the tree has no focus).
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QSplitter, QStackedWidget, QStyle, QStyledItemDelegate,
                               QStyleFactory, QTabBar, QToolButton, QTreeWidget, QVBoxLayout, QWidget)

BLUE = QColor(0, 120, 215)              # title bar of the pane that has the focus, selection
FACE = QColor(240, 240, 240)
SHADOW = QColor(160, 160, 160)
DARK = QColor(100, 100, 100)
SELECTED_IDLE = QColor(128, 128, 128)   # selection of a tree without the focus


def _font(bold: bool = False) -> QFont:
    f = QFont('Tahoma')
    f.setPointSizeF(8)
    f.setBold(bold)
    return f


# -- icons --------------------------------------------------------------------------------------------
def _circle(p: QPainter, x: float, y: float, fill: QColor, r: float = 2.6):
    p.setPen(QPen(QColor(0, 60, 0) if fill.green() > 150 and fill.blue() < 100 else QColor(0, 70, 90), 1))
    p.setBrush(fill)
    p.drawEllipse(QPointF(x, y), r, r)


GREEN = QColor(40, 220, 40)
CYAN = QColor(30, 200, 230)


def _draw(p: QPainter, name: str):
    """Draw the 16 x 16 navigator icon `name`."""
    if name == 'signals':                   # a yellow sheet, a green cell at the bottom left
        p.fillRect(QRect(3, 1, 12, 12), QColor(255, 255, 120))
        p.fillRect(QRect(1, 9, 6, 6), QColor(40, 200, 40))
        p.setPen(QPen(Qt.black, 1))
        for k in range(4):
            p.drawLine(3 + 4 * k if k < 3 else 14, 1, 3 + 4 * k if k < 3 else 14, 13)
            p.drawLine(3, 1 + 4 * k if k < 3 else 13, 14, 1 + 4 * k if k < 3 else 13)
        p.drawRect(QRect(1, 9, 5, 5))
    elif name == 'params':                  # a yellow "P" over a green block
        p.fillRect(QRect(6, 6, 9, 9), QColor(40, 200, 40))
        p.setPen(QPen(Qt.black, 1)); p.drawRect(QRect(6, 6, 8, 8))
        p.fillRect(QRect(1, 1, 10, 11), QColor(255, 255, 0))
        p.drawRect(QRect(1, 1, 9, 10))
        f = QFont('Arial'); f.setPixelSize(10); f.setBold(True); p.setFont(f)
        p.drawText(QRect(1, 1, 10, 11), Qt.AlignCenter, 'P')
    elif name == 'unit':                    # a state machine: two linked states
        p.setPen(QPen(QColor(0, 0, 80), 1.2))
        p.drawLine(QPointF(5, 5), QPointF(11, 11))
        _circle(p, 5, 5, GREEN, 3.4)
        _circle(p, 11.5, 11.5, CYAN, 3.4)
    elif name in ('machine', 'concurrent'):     # four states, two by two
        p.setPen(QPen(QColor(0, 0, 80), 1))
        p.drawLine(QPointF(4.5, 4), QPointF(4.5, 12)); p.drawLine(QPointF(11.5, 4), QPointF(11.5, 12))
        for x in (4.5, 11.5):
            _circle(p, x, 3.5, GREEN)
            _circle(p, x, 12.5, CYAN)
    elif name == 'compdir':                 # [C]
        p.setPen(QPen(QColor(0, 0, 230), 1.6))
        p.drawPolyline(QPolygonF([QPointF(6, 3), QPointF(4, 3), QPointF(4, 13), QPointF(6, 13)]))
        p.setPen(QPen(Qt.black, 1))
        p.drawPolyline(QPolygonF([QPointF(11, 3), QPointF(13, 3), QPointF(13, 13), QPointF(11, 13)]))
        p.drawLine(1, 14, 15, 14)
        f = QFont('Arial'); f.setPixelSize(10); f.setBold(True); p.setFont(f)
        p.setPen(QColor(0, 0, 230)); p.drawText(QRect(4, 2, 9, 12), Qt.AlignCenter, 'C')
    elif name == 'decl':                    # a step with an arrow head
        p.setPen(QPen(QColor(0, 0, 200), 1.4))
        p.drawPolyline(QPolygonF([QPointF(3, 2), QPointF(3, 5), QPointF(7, 5), QPointF(7, 12), QPointF(12, 12)]))
        p.setPen(QPen(Qt.black, 1.2)); p.drawLine(QPointF(7, 6), QPointF(7, 12))
        p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 200))
        p.drawPolygon(QPolygonF([QPointF(11, 9), QPointF(15, 12), QPointF(11, 15)]))
        p.setBrush(QColor(0, 0, 200)); p.drawRect(QRectF(2, 1, 2, 3))
    elif name == 'block':                   # a block diagram unit: a blue block
        p.setPen(QPen(Qt.black, 1)); p.setBrush(QColor(110, 160, 255))
        p.drawRect(QRect(2, 3, 12, 10))
    elif name == 'embedded':
        p.setPen(QPen(Qt.black, 1)); p.setBrush(QColor(255, 255, 160))
        p.drawRect(QRect(2, 3, 12, 10))
        p.drawLine(4, 6, 12, 6); p.drawLine(4, 9, 10, 9)


_CACHE: dict[str, QIcon] = {}


def nav_icon(name: str) -> QIcon:
    """The icon of a navigator entry: signals, params, unit, machine, concurrent, compdir, decl,
    block, embedded."""
    if name not in _CACHE:
        pm = QPixmap(16, 16)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        _draw(p, name)
        p.end()
        _CACHE[name] = QIcon(pm)
    return _CACHE[name]


# -- trees --------------------------------------------------------------------------------------------
class _TextSelection(QStyledItemDelegate):
    """Draws an entry with the selection only behind its text, as the legacy tool does."""

    def paint(self, p: QPainter, option, index):
        opt = option.__class__(option)
        self.initStyleOption(opt, index)
        selected = bool(opt.state & QStyle.State_Selected)
        tree = self.parent()
        r = opt.rect
        p.save()
        x = r.left() + 2
        if not opt.icon.isNull():
            opt.icon.paint(p, QRect(x, r.top() + (r.height() - 16) // 2, 16, 16))
            x += 19
        p.setFont(opt.font)
        tw = p.fontMetrics().horizontalAdvance(opt.text) + 4
        tr = QRect(x, r.top() + 1, tw, r.height() - 2)
        if selected:
            p.fillRect(tr, BLUE if tree.hasFocus() else SELECTED_IDLE)
            p.setPen(Qt.white)
        else:
            p.setPen(Qt.black)
        p.drawText(tr.adjusted(2, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, opt.text)
        p.restore()

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width() + 8, 17)


def _classic_tree(tree: QTreeWidget, columns: int = 1):
    """The legacy look of a tree: dotted branch lines and +/- boxes, Tahoma 8."""
    style = QStyleFactory.create('Windows')
    if style is not None:
        style.setParent(tree)
        tree.setStyle(style)
    tree.setFont(_font())
    tree.setIndentation(17)
    tree.setRootIsDecorated(True)
    tree.setFrameShape(QTreeWidget.NoFrame)
    tree.setIconSize(QSize(16, 16))
    tree.setStyleSheet('QTreeWidget { background: white; } '
                       'QHeaderView::section { background: #f0f0f0; border: none; border-right: 1px solid #a0a0a0;'
                       ' border-bottom: 1px solid #a0a0a0; padding-left: 3px; font: 8pt "Tahoma"; }')
    if columns == 1:
        tree.setHeaderHidden(True)
        tree.setItemDelegate(_TextSelection(tree))


class _PaneTitle(QWidget):
    """The title bar of a pane: its name (white on blue while the pane has the focus) and a small
    ▲ button that gives the browser's whole height to that pane (again: back to both)."""
    toggled = Signal()

    def __init__(self, text: str):
        super().__init__()
        self.text = text
        self.active = False
        self.setFixedHeight(20)
        self.button = QToolButton(self)
        self.button.setArrowType(Qt.UpArrow)
        self.button.setFixedSize(14, 13)
        self.button.setStyleSheet('QToolButton { background: #f0f0f0; border: 1px solid; '
                                  'border-color: white #646464 #646464 white; }')
        self.button.clicked.connect(self.toggled.emit)

    def set_active(self, on: bool):
        if on != self.active:
            self.active = on
            self.update()

    def resizeEvent(self, e):
        self.button.move(self.width() - 17, 3)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), FACE)
        p.fillRect(QRect(0, 1, self.width(), self.height() - 2), BLUE if self.active else FACE)
        p.setPen(SHADOW)
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.setPen(Qt.white if self.active else Qt.black)
        p.setFont(_font(self.active))
        p.drawText(QRect(6, 0, self.width() - 26, self.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text)


class _Pane(QWidget):
    """A titled pane of the browser."""

    def __init__(self, title: str, body: QWidget):
        super().__init__()
        self.title = _PaneTitle(title)
        self.body = body
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.title)
        lay.addWidget(body)


class _Strip(QWidget):
    """The grey strip on the right edge: a ► button at the top and the vertical "Diagram Browser"
    tab; a click on either hides or shows the browser."""
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedWidth(20)
        self.setCursor(Qt.ArrowCursor)
        self.open = True

    def tab_rect(self) -> QRect:
        f = _font(True)
        from PySide6.QtGui import QFontMetrics
        w = QFontMetrics(f).horizontalAdvance('Diagram Browser') + 12
        return QRect(2, 22, 16, w)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), SHADOW)
        b = QRect(2, 2, 15, 15)                     # the ► / ◄ button
        p.fillRect(b, FACE)
        p.setPen(Qt.white); p.drawLine(b.topLeft(), b.topRight()); p.drawLine(b.topLeft(), b.bottomLeft())
        p.setPen(DARK); p.drawLine(b.bottomLeft(), b.bottomRight()); p.drawLine(b.topRight(), b.bottomRight())
        p.setPen(Qt.NoPen); p.setBrush(Qt.black)
        c = b.center()
        if self.open:
            p.drawPolygon(QPolygonF([QPointF(c.x() - 1, c.y() - 4), QPointF(c.x() + 3, c.y()),
                                     QPointF(c.x() - 1, c.y() + 4)]))
        else:
            p.drawPolygon(QPolygonF([QPointF(c.x() + 2, c.y() - 4), QPointF(c.x() - 2, c.y()),
                                     QPointF(c.x() + 2, c.y() + 4)]))
        t = self.tab_rect()                         # the tab: white face, black edge on the right
        p.fillRect(t, Qt.white)
        p.setPen(QPen(Qt.black, 2))
        p.drawLine(t.right(), t.top(), t.right(), t.bottom())
        p.drawLine(t.left(), t.bottom(), t.right(), t.bottom())
        p.setPen(Qt.black)
        p.setFont(_font(True))
        p.translate(t.left() + 2, t.top() + 6)
        p.rotate(90)
        p.drawText(QRect(0, -13, t.height() - 10, 13), Qt.AlignLeft | Qt.AlignVCenter, 'Diagram Browser')
        # the ▸ mark half way down, as in the legacy tool
        p.resetTransform()
        y = self.height() // 2
        p.setPen(Qt.NoPen); p.setBrush(DARK)
        p.drawPolygon(QPolygonF([QPointF(7, y - 4), QPointF(12, y), QPointF(7, y + 4)]))


class DiagramBrowser(QWidget):
    """The Diagram Browser: `navigator` (the Structure Navigator tree) above `content` (the
    Content tree), the Content List / Flow Help tabs, the strip with the vertical tab."""

    def __init__(self, content_columns: list[str]):
        super().__init__()
        self.columns = content_columns
        self.navigator = QTreeWidget()
        _classic_tree(self.navigator)
        self.content = QTreeWidget()
        _classic_tree(self.content, 2)
        self.content.setHeaderLabels(content_columns)
        self.content.header().setMinimumHeight(20)
        self.content.setColumnWidth(0, 120)
        self.content.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_pane = _Pane('Structure Navigator', self.navigator)
        self.content_pane = _Pane('Content', self.content)
        self.split = QSplitter(Qt.Vertical)
        self.split.setHandleWidth(3)
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(self.nav_pane)
        self.split.addWidget(self.content_pane)
        self.split.setSizes([400, 450])
        self.nav_pane.title.toggled.connect(lambda: self._maximise(self.nav_pane))
        self.content_pane.title.toggled.connect(lambda: self._maximise(self.content_pane))
        self.nav_pane.title.set_active(True)

        help_page = QLabel()
        help_page.setStyleSheet('background: white;')
        self.pages = QStackedWidget()
        self.pages.addWidget(self.split)
        self.pages.addWidget(help_page)
        self.tabbar = QTabBar()
        self.tabbar.setShape(QTabBar.RoundedSouth)
        self.tabbar.setFont(_font())
        self.tabbar.setDrawBase(False)
        self.tabbar.addTab('Content List')
        self.tabbar.addTab('Flow Help')
        self.tabbar.setStyleSheet(
            'QTabBar::tab { background: #a0a0a0; color: white; padding: 1px 6px; border: 1px solid #646464;'
            ' border-top: none; } QTabBar::tab:selected { background: #f0f0f0; color: black; }')
        self.tabbar.currentChanged.connect(self.pages.setCurrentIndex)

        self.panel = QWidget()
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        pl.addWidget(self.pages, 1)
        bar = QWidget()
        bar.setStyleSheet('background: #a0a0a0;')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(2, 0, 0, 2)
        bl.addWidget(self.tabbar)
        bl.addStretch(1)
        pl.addWidget(bar)
        self.strip = _Strip()
        self.strip.clicked.connect(self.toggle)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.panel, 1)
        lay.addWidget(self.strip)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().focusChanged.connect(self._focus_changed)

    def _focus_changed(self, _old, new):
        """The title bar of the pane with the focus is blue."""
        if new is self.navigator or new is self.content:
            self.nav_pane.title.set_active(new is self.navigator)
            self.content_pane.title.set_active(new is self.content)
        self.navigator.viewport().update()

    def _maximise(self, pane: _Pane):
        """The ▲ button: the whole height to that pane, again: both panes."""
        other = self.content_pane if pane is self.nav_pane else self.nav_pane
        if other.body.isVisible():
            other.body.hide()
            sizes = [10000, other.title.height()] if pane is self.nav_pane else [other.title.height(), 10000]
        else:
            other.body.show()
            sizes = [400, 450]
        self.split.setSizes(sizes)

    def toggle(self):
        """The strip: hide the browser down to the strip, or show it again."""
        self.strip.open = not self.strip.open
        self.panel.setVisible(self.strip.open)
        dock = self.parentWidget()
        if dock is not None and hasattr(dock, 'setMinimumWidth'):
            if self.strip.open:
                dock.setMinimumWidth(0)
                dock.setMaximumWidth(16777215)
            else:
                dock.setFixedWidth(self.strip.width())
        self.strip.update()

    def show_content(self, on: bool):
        """The Content pane is empty, without column names, while a table page is shown."""
        self.content.setHeaderLabels(self.columns if on else ['', ''])
