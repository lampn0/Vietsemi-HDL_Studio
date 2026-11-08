"""Commands shared by the diagram editors (state diagram: main_window.MainWindow, block diagram:
bd_editor.BdEditor), with the legacy tool's behaviour:

    print_diagram / copy_picture     File > Print... / Print Window..., Diagram > Copy Picture
    align / distribute               Edit > Align, Edit > Align > Distribute
    select_span / mark_text          the match Find Next shows (Edit > Find...: find_dialog.py)
    History                          Back / Forward: the diagram windows in the order they were used
    fill_windows_menu                the open windows at the end of the Window menu
    update_edit_states               Cut / Copy / Delete / Paste / Align ... greyed as in the legacy tool
    TooltipFilter                    View > Toolbars > Tooltips off: no tool tips on the toolbars
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QAction, QImage, QPainter
from PySide6.QtWidgets import (QApplication, QDialog, QGraphicsItem, QGraphicsScene, QGraphicsView, QMainWindow,
                               QMenu, QMessageBox)


# -- printing and pictures ------------------------------------------------------------------------
def _scene_rect(scene: QGraphicsScene) -> QRectF:
    """The part of the scene that has items, with a small margin."""
    r = scene.itemsBoundingRect()
    return r.adjusted(-20, -20, 20, 20)


def print_area(parent: QMainWindow, scene: QGraphicsScene, source: QRectF, title: str = 'Print') -> bool:
    """The system print dialog, then `source` (a scene rectangle) scaled onto one page. True when printed."""
    from PySide6.QtPrintSupport import QPrintDialog, QPrinter
    printer = QPrinter(QPrinter.HighResolution)
    dlg = QPrintDialog(printer, parent)
    dlg.setWindowTitle(title)
    if dlg.exec() != QDialog.Accepted:
        return False
    selected = scene.selectedItems()
    scene.clearSelection()                       # print without selection marks
    p = QPainter(printer)
    scene.render(p, QRectF(), source, Qt.KeepAspectRatio)
    p.end()
    for it in selected:
        it.setSelected(True)
    return True


def print_diagram(parent: QMainWindow, scene: QGraphicsScene, view: QGraphicsView | None = None) -> bool:
    """File > Print... (the whole diagram) or, with `view`, Print Window... (what the window shows):
    the system print dialog, then the diagram scaled onto one page. True when printed."""
    source = view.mapToScene(view.viewport().rect()).boundingRect() if view is not None else _scene_rect(scene)
    return print_area(parent, scene, source, 'Print Window' if view is not None else 'Print')


def render_picture(scene: QGraphicsScene, scale: float = 2.0, selection_only: bool = True) -> QImage:
    """The selected objects (else, or with `selection_only` False, the whole diagram) as a picture."""
    selected = scene.selectedItems()
    if selected and selection_only:
        r = QRectF()
        for it in selected:
            r = r.united(it.sceneBoundingRect())
        r = r.adjusted(-10, -10, 10, 10)
    else:
        r = _scene_rect(scene)
    img = QImage(max(1, int(r.width() * scale)), max(1, int(r.height() * scale)), QImage.Format_ARGB32)
    img.fill(Qt.white)
    scene.clearSelection()
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    scene.render(p, QRectF(img.rect()), r)
    p.end()
    for it in selected:
        it.setSelected(True)
    return img


def document_single_level(parent: QMainWindow, scene: QGraphicsScene, name: str, title: str,
                          hdl: str, start_dir: str = '') -> str | None:
    """File > Document And Visualize > Single Level: an HTML page of the diagram (its picture and the
    HDL generated from it) written to a folder the user picks, then opened. Returns the page path."""
    import html
    import os
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QFileDialog
    folder = QFileDialog.getExistingDirectory(parent, 'Document And Visualize - folder for the pages', start_dir)
    if not folder:
        return None
    render_picture(scene, 1.5, selection_only=False).save(os.path.join(folder, f'{name}.png'))
    page = os.path.join(folder, f'{name}.html')
    with open(page, 'w', encoding='utf-8') as f:
        f.write(f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Arial,sans-serif;margin:16px}} img{{max-width:100%;border:1px solid #ccc}}
pre{{background:#f6f6f6;padding:8px;overflow:auto;font-size:12px}}</style></head>
<body><h1>{html.escape(title)}</h1>
<h2>Diagram</h2><img src="{html.escape(name)}.png" alt="diagram">
<h2>Generated HDL</h2><pre>{html.escape(hdl)}</pre>
</body></html>
""")
    QDesktopServices.openUrl(QUrl.fromLocalFile(page))
    return page


def copy_picture(scene: QGraphicsScene, scale: float = 2.0) -> QImage:
    """Diagram > Copy Picture: the selected objects (else the whole diagram) as a picture on the
    system clipboard. Returns the picture."""
    img = render_picture(scene, scale)
    QApplication.clipboard().setImage(img)
    return img


# -- align / distribute ------------------------------------------------------------------------------
def movable(items: list[QGraphicsItem]) -> list[QGraphicsItem]:
    """The items of `items` that are diagram objects the user can move."""
    return [i for i in items if i.flags() & QGraphicsItem.ItemIsMovable and getattr(i, 'obj', None) is not None]


def align(items: list[QGraphicsItem], how: str) -> bool:
    """Edit > Align > Align Left / Center / Right / Top / Middle / Bottom: line the selected objects up
    on the first selected one (the legacy tool aligns on the object selected first). True when moved."""
    items = movable(items)
    if len(items) < 2:
        return False
    ref = items[0].sceneBoundingRect()
    moved = False
    for it in items[1:]:
        r = it.sceneBoundingRect()
        dx = {'left': ref.left() - r.left(), 'center': ref.center().x() - r.center().x(),
              'right': ref.right() - r.right()}.get(how, 0.0)
        dy = {'top': ref.top() - r.top(), 'middle': ref.center().y() - r.center().y(),
              'bottom': ref.bottom() - r.bottom()}.get(how, 0.0)
        if dx or dy:
            it.setPos(it.pos().x() + dx, it.pos().y() + dy)
            moved = True
    return moved


def distribute(items: list[QGraphicsItem], horizontal: bool) -> bool:
    """Edit > Align > Distribute Horizontally / Vertically: equal gaps between the selected objects,
    the outer two staying where they are. True when moved."""
    items = movable(items)
    if len(items) < 3:
        return False
    key = (lambda i: i.sceneBoundingRect().center().x()) if horizontal else \
        (lambda i: i.sceneBoundingRect().center().y())
    items.sort(key=key)
    first, last = key(items[0]), key(items[-1])
    step = (last - first) / (len(items) - 1)
    moved = False
    for k, it in enumerate(items[1:-1], start=1):
        d = first + k * step - key(it)
        if abs(d) > 0.01:
            it.setPos(it.pos().x() + (d if horizontal else 0), it.pos().y() + (0 if horizontal else d))
            moved = True
    return moved


# -- Find: the match shown -------------------------------------------------------------------
FIND_HIGHLIGHT = '#0078d7'          # the legacy tool's selection blue, also while the Find dialog has the focus


def select_span(ed, span: tuple[int, int] | None) -> None:
    """Select `span` (start, end) of the text in an in-place editor (QLineEdit or QPlainTextEdit),
    drawn in the selection blue even while the window does not have the focus (the Find dialog
    has it), as the legacy tool shows the match Find Next found."""
    if span is None:
        return
    from PySide6.QtGui import QPalette
    pal = ed.palette()
    for role, colour in ((QPalette.Highlight, FIND_HIGHLIGHT), (QPalette.HighlightedText, '#ffffff')):
        for group in (QPalette.Active, QPalette.Inactive):
            pal.setColor(group, role, colour)
    ed.setPalette(pal)
    ed.setStyleSheet(ed.styleSheet() + f' selection-background-color: {FIND_HIGHLIGHT}; selection-color: white;')
    start, end = span
    if hasattr(ed, 'setSelection'):
        ed.setSelection(start, end - start)
    else:
        cur = ed.textCursor()
        cur.setPosition(start)
        cur.setPosition(end, cur.MoveMode.KeepAnchor)
        ed.setTextCursor(cur)
        ed.ensureCursorVisible()


_MARKED: list = []


def mark_text(item, span: tuple[int, int] | None) -> None:
    """Show the match on a text that has no in-place editor (a comment text): the matched characters
    are drawn on the selection blue (item.find_span, read by its paint); the mark shown before goes."""
    for old in _MARKED:
        try:
            old.find_span = None
            old.update()
        except RuntimeError:
            pass
    _MARKED.clear()
    if item is not None and span is not None:
        item.find_span = span
        item.update()
        _MARKED.append(item)


def paint_text_lines(p, lines: list[str], x: float, top: float, fm, span, colour) -> None:
    """Draw `lines` from (x, top), one per font line, the characters of `span` (start, end counted
    over the whole text, lines joined by newlines) on the selection blue in white."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor
    pos = 0
    for k, line in enumerate(lines):
        base = top + fm.ascent() + k * fm.height()
        p.setPen(colour)
        p.drawText(QPointF(x, base), line)
        if span is not None:
            a, b = max(span[0] - pos, 0), min(span[1] - pos, len(line))
            if a < b:
                x0 = x + fm.horizontalAdvance(line[:a])
                w = fm.horizontalAdvance(line[a:b])
                p.fillRect(QRectF(x0, base - fm.ascent(), w, fm.height()), QColor(FIND_HIGHLIGHT))
                p.setPen(QColor('white'))
                p.drawText(QPointF(x0, base), line[a:b])
        pos += len(line) + 1


# -- Back / Forward ----------------------------------------------------------------------------------
class History:
    """The diagram windows in the order the user worked in them (one list per Design Manager, or per
    stand-alone window): Back goes to the previous one, Forward to the next, as the legacy tool's
    Back / Forward buttons."""
    _lists: dict[int, 'History'] = {}

    def __init__(self):
        self.windows: list[QMainWindow] = []
        self.pos = -1
        self._moving = False

    @classmethod
    def of(cls, owner: object) -> 'History':
        """The history shared by the windows of `owner` (a Design Manager or a window)."""
        return cls._lists.setdefault(id(owner), cls())

    def _alive(self):
        alive = []
        for w in self.windows:
            try:
                if w.isVisible():
                    alive.append(w)
            except RuntimeError:            # deleted window
                pass
        if len(alive) != len(self.windows):
            cur = self.windows[self.pos] if 0 <= self.pos < len(self.windows) else None
            self.windows = alive
            self.pos = alive.index(cur) if cur in alive else len(alive) - 1

    def visited(self, w: QMainWindow):
        """Window `w` became the active diagram window."""
        if self._moving:
            return
        self._alive()
        if 0 <= self.pos < len(self.windows) and self.windows[self.pos] is w:
            return
        del self.windows[self.pos + 1:]
        if w in self.windows:
            self.windows.remove(w)
        self.windows.append(w)
        self.pos = len(self.windows) - 1

    def can_go(self, step: int) -> bool:
        self._alive()
        return 0 <= self.pos + step < len(self.windows)

    def go(self, step: int):
        """Back (-1) / Forward (+1): bring that window to the front."""
        if not self.can_go(step):
            return
        self.pos += step
        w = self.windows[self.pos]
        self._moving = True
        try:
            w.show(); w.raise_(); w.activateWindow()
        finally:
            self._moving = False


# -- Window menu --------------------------------------------------------------------------------------
def fill_windows_menu(win: QMainWindow, menu: QMenu) -> None:
    """The open windows, numbered as the legacy tool lists them ("1 - Design Manager - ..."), the
    active one checked; picking one brings it to the front."""
    menu.clear()
    ctx = getattr(win, 'context', None)
    mgr = ctx.manager if ctx is not None else None
    wins = ([mgr] if mgr is not None else []) + \
        [w for w in (mgr.editors.values() if mgr is not None else [win]) if w.isVisible()]
    for k, w in enumerate(wins, start=1):
        a = menu.addAction(f'{k} - {w.windowTitle()}')
        a.setCheckable(True)
        a.setChecked(w is win)
        a.triggered.connect(lambda checked=False, x=w: (x.show(), x.raise_(), x.activateWindow()))


# -- greyed commands ----------------------------------------------------------------------------------
def update_edit_states(actions: dict[str, QAction], selected: list, can_paste: bool, readonly: bool) -> None:
    """Cut / Copy / Delete need a selection, Paste a clipboard, Align two objects and Distribute
    three, as the legacy tool greys them."""
    n = len(movable(selected))
    rules = {'cut': bool(selected) and not readonly, 'copy': bool(selected), 'delete': bool(selected) and not readonly,
             'paste': can_paste and not readonly}
    for k in ('align_left', 'align_center', 'align_right', 'align_top', 'align_middle', 'align_bottom'):
        rules[k] = n >= 2 and not readonly
    rules['distribute_h'] = rules['distribute_v'] = n >= 3 and not readonly
    for key, on in rules.items():
        a = actions.get(key)
        if a is not None and a.property('available') is not False:
            a.setEnabled(on)


class TooltipFilter(QObject):
    """Swallows the tool tips of a toolbar while View > Toolbars > Tooltips is off."""

    def __init__(self, win: QMainWindow):
        super().__init__(win)
        self.win = win

    def eventFilter(self, obj, e):
        if e.type() == QEvent.ToolTip and not getattr(self.win, 'toolbar_tooltips', True):
            return True
        return False


def install_tooltip_filter(win: QMainWindow, bars) -> None:
    """Let View > Toolbars > Tooltips turn the tool tips of `bars` (and their buttons) on and off."""
    f = TooltipFilter(win)
    for tb in bars:
        tb.installEventFilter(f)
        for child in tb.findChildren(QObject):
            if hasattr(child, 'installEventFilter') and child.isWidgetType():
                child.installEventFilter(f)


def not_available(parent, what: str) -> None:
    """Message for a command that exists in the legacy tool but has no counterpart here."""
    QMessageBox.information(parent, what, f'{what} is not available in this version.')


# -- Open Up -------------------------------------------------------------------------------------------
_PARENTS: dict[tuple[int, str], object] = {}


def remember_parent(manager, unit: str, parent_unit) -> None:
    """Open Down from `parent_unit`'s diagram to `unit`: Open Up there comes back to that parent."""
    _PARENTS[(id(manager), unit)] = parent_unit


def open_up(win: QMainWindow) -> None:
    """File > Open > Open Up: open the diagram that instantiates this design unit. The diagram it
    was opened from (Open Down) first; else the units of the project that instantiate it (a choice
    when there are several)."""
    from PySide6.QtWidgets import QInputDialog
    ctx = getattr(win, 'context', None)
    if ctx is None or ctx.manager.project is None:
        return
    mgr, me = ctx.manager, ctx.unit
    parent = _PARENTS.get((id(mgr), me.name))
    if parent is None:
        found = []
        for lib in mgr.project.libraries:
            for du in lib.units.values():
                if du is not me and any(c[1] == me.name and c[2] in ('', me.library.name)
                                        for c in mgr.children_of(du)):
                    found.append(du)
        if not found:
            win.statusBar().showMessage(f'No design unit instantiates {me.name}', 5000)
            return
        parent = found[0]
        if len(found) > 1:
            names = [f'{du.library.name}/{du.name}' for du in found]
            pick, ok = QInputDialog.getItem(win, 'Open Up', f'{me.name} is instantiated in:', names, 0, False)
            if not ok:
                return
            parent = found[names.index(pick)]
    mgr.open_unit(parent)


def open_user_guide() -> None:
    """Help > Help and Manuals: the user guide (docs/user-guide.md) in the system viewer."""
    import os
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.join(root, 'docs', 'user-guide.md')))


REGEX_HELP = r"""<b>Regular expressions</b> (Find / Replace with "Regular expression" ticked)<br><br>
<table>
<tr><td><tt>.</tt></td><td>any character</td></tr>
<tr><td><tt>*  +  ?</tt></td><td>0 or more, 1 or more, 0 or 1 of the item before</td></tr>
<tr><td><tt>{m,n}</tt></td><td>m to n of the item before</td></tr>
<tr><td><tt>^  $</tt></td><td>start, end of the text</td></tr>
<tr><td><tt>[abc]  [^abc]  [a-z]</tt></td><td>one of, none of, a range of characters</td></tr>
<tr><td><tt>\d  \w  \s</tt></td><td>digit, word character, white space</td></tr>
<tr><td><tt>\b</tt></td><td>word boundary</td></tr>
<tr><td><tt>a|b</tt></td><td>a or b</td></tr>
<tr><td><tt>( )</tt></td><td>group; <tt>\1</tt> in Replace with is the text of group 1</td></tr>
</table>"""


def show_regex_help(parent) -> None:
    """Help > Regular Expressions: a short reference of the expressions Find / Replace accept."""
    QMessageBox.information(parent, 'Regular Expressions', REGEX_HELP)


__all__ = ['print_diagram', 'copy_picture', 'align', 'distribute', 'History',
           'fill_windows_menu', 'update_edit_states', 'install_tooltip_filter', 'movable', 'open_user_guide',
           'show_regex_help', 'not_available']
