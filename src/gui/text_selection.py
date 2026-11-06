"""Selection drawn behind an item's text only, as in the legacy Design Explorer.

Qt highlights the whole row of a selected item (every column, the branch area, hover glow);
the legacy tool highlights only the text of the first column. apply(tree) gives a tree that look:

    TextSelectionDelegate   paints the highlight behind the first column's text, in the selected
                            text colour, and nothing in the other columns
    _NoRowSelectionStyle    keeps the style from filling the branch area / whole row
"""
from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QFontMetrics, QPalette
from PySide6.QtWidgets import (QApplication, QProxyStyle, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
                               QTreeWidget)

PAD = 2                                     # pixels of highlight left and right of the text
# colours of the legacy tool: blue in the pane with the focus, dark grey in the others (the
# Windows palette's inactive highlight is almost white, so a selection there looked lost)
ACTIVE, INACTIVE, SELECTED_TEXT = QColor(0, 120, 215), QColor(105, 105, 105), QColor(255, 255, 255)


class _NoRowSelectionStyle(QProxyStyle):
    """The application style, except that a selected row is not filled across (branch area)."""

    def styleHint(self, hint, option=None, widget=None, data=None):
        if hint == QStyle.SH_ItemView_ShowDecorationSelected:
            return 0
        return super().styleHint(hint, option, widget, data)


def highlight_rect(opt: QStyleOptionViewItem, widget, style) -> QRect:
    """Rectangle behind the text of a cell: the text and the style's text margins, within the cell."""
    text = style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget)
    margin = style.pixelMetric(QStyle.PM_FocusFrameHMargin, None, widget) + 1
    width = QFontMetrics(opt.font).horizontalAdvance(opt.text) + 2 * margin + 2 * PAD
    return QRect(text.left() - PAD, text.top(), min(width, text.width() + 2 * PAD), text.height())


class TextSelectionDelegate(QStyledItemDelegate):
    """Draws a selected item with the highlight behind the first column's text only."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        selected = bool(opt.state & QStyle.State_Selected)
        opt.state &= ~(QStyle.State_Selected | QStyle.State_MouseOver | QStyle.State_HasFocus)
        # the row has drawn its alternate background already; the cell drawing it again would
        # paint over the highlight (the selected text then vanishes on every other row)
        opt.features &= ~QStyleOptionViewItem.Alternate
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        if selected and index.column() == 0 and widget is not None:
            painter.fillRect(highlight_rect(opt, widget, style), ACTIVE if widget.hasFocus() else INACTIVE)
            opt.palette.setColor(QPalette.Text, SELECTED_TEXT)
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)


def apply(tree: QTreeWidget) -> None:
    """Give `tree` the text-only selection look."""
    style = _NoRowSelectionStyle(tree.style().name()) if tree.style() is not None else _NoRowSelectionStyle()
    style.setParent(tree)
    tree.setStyle(style)
    tree.setItemDelegate(TextSelectionDelegate(tree))
