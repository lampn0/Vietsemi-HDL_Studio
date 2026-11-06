"""Panels of the diagram editors (Add > Panel): named rectangles marking an area of a diagram,
drawn as a dark red frame with the name above it, as the legacy tool draws them. A panel is
picked by its frame (a click inside it reaches the objects under it), moved like the other
objects, viewed with View > View Panel and printed with Diagram > Panels > Print... .

    PanelItem                 the item of a model Panel (model.Panel)
    new_panel(panels, pos)    a Panel placed at `pos`, with the next free name
    PanelDialog               Diagram > Panels > Object Properties: name and size
    pick_panel(...)           choose one panel (View Panel, Delete Panel, ...)
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGraphicsItem, QInputDialog,
                               QLineEdit)

from model import Panel

PANEL_COLOR = QColor(160, 0, 0)
PANEL_FONT = QFont('Arial', 8, QFont.Bold)


class PanelItem(QGraphicsItem):
    """The frame of a panel. `changed()` is called after the user moved it; `snap(point)` puts a
    dragged position on the diagram grid; `locked()` (Protect All Panels, read-only diagram)
    keeps it where it is."""

    def __init__(self, obj: Panel, changed: Callable[[], None], snap: Callable[[QPointF], QPointF],
                 locked: Callable[[], bool]):
        super().__init__()
        self.obj = obj
        self._changed, self._snap, self._locked = changed, snap, locked
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setPos(obj.x, obj.y)
        self.setZValue(-1)                      # under the objects of the diagram

    def _frame(self) -> QRectF:
        return QRectF(0, 0, self.obj.w, self.obj.h)

    def boundingRect(self):
        fm = QFontMetricsF(PANEL_FONT)
        return self._frame().adjusted(-3, -fm.height() - 3, 3, 3)

    def shape(self):
        """The frame line and the name only: a click inside the panel goes to what is there."""
        path = QPainterPath()
        path.addRect(self._frame())
        stroke = QPainterPathStroker()
        stroke.setWidth(8)
        out = stroke.createStroke(path)
        fm = QFontMetricsF(PANEL_FONT)
        out.addRect(QRectF(0, -fm.height() - 2, fm.horizontalAdvance(self.obj.name) + 4, fm.height() + 2))
        return out

    def paint(self, p: QPainter, opt, widget=None):
        pen = QPen(PANEL_COLOR, 2 if self.isSelected() else 1.2)
        pen.setCosmetic(True)
        if self.isSelected():
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(self._frame())
        p.setFont(PANEL_FONT)
        p.drawText(QPointF(2, -4), self.obj.name)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            if self._locked():
                return self.pos()
            return self._snap(value) if self.scene() and self.scene().mouseGrabberItem() is self else value
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.obj.x, self.obj.y = self.pos().x(), self.pos().y()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        moved = event.buttonDownScenePos(Qt.LeftButton) != event.scenePos()
        super().mouseReleaseEvent(event)
        if moved:
            self._changed()

    def scene_rect(self) -> QRectF:
        return QRectF(self.obj.x, self.obj.y, self.obj.w, self.obj.h)


def new_panel(panels: list[Panel], new_id: str, pos: QPointF) -> Panel:
    """A panel with its top-left corner at `pos`, named Panel<n> with the lowest free n."""
    names = {p.name for p in panels}
    k = 0
    while f'Panel{k}' in names:
        k += 1
    return Panel(new_id, f'Panel{k}', pos.x(), pos.y())


def pick_panel(parent, panels: list[Panel], title: str, selected: list[Panel] | None = None) -> Panel | None:
    """The panel the user picks (the selected one when there is exactly one; None: cancelled)."""
    if selected and len(selected) == 1:
        return selected[0]
    if not panels:
        return None
    if len(panels) == 1:
        return panels[0]
    names = [p.name for p in panels]
    name, ok = QInputDialog.getItem(parent, title, 'Panel:', names, 0, False)
    return panels[names.index(name)] if ok else None


class PanelDialog(QDialog):
    """Diagram > Panels > Object Properties: the name and size of a panel."""

    def __init__(self, parent, panel: Panel, taken: set[str], readonly: bool = False):
        super().__init__(parent)
        self.setWindowTitle(f'Panel Properties - {panel.name}')
        self.panel, self.taken = panel, taken
        form = QFormLayout(self)
        self.name = QLineEdit(panel.name)
        self.w = QDoubleSpinBox(); self.w.setRange(20, 1e6); self.w.setValue(panel.w)
        self.h = QDoubleSpinBox(); self.h.setRange(20, 1e6); self.h.setValue(panel.h)
        form.addRow('Name:', self.name)
        form.addRow('Width:', self.w)
        form.addRow('Height:', self.h)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        box.button(QDialogButtonBox.Ok).setEnabled(not readonly)
        form.addRow(box)

    def accept(self):
        name = self.name.text().strip()
        if not name or name in self.taken:
            self.name.setFocus()
            self.name.selectAll()
            return
        self.panel.name, self.panel.w, self.panel.h = name, self.w.value(), self.h.value()
        super().accept()


class PanelCommands:
    """The panel commands of an editor window (mixed into the state and block diagram windows),
    which provide: `scene`, `canvas`, `toolbar_actions`, `panels_model()` (the list of panels of
    the diagram shown), `panel_new_id()`, `panels_reload()` (draw the diagram again) and
    `panels_changed()` (record one undoable change)."""

    def panel_items(self) -> list[PanelItem]:
        return [i for i in self.scene.items() if isinstance(i, PanelItem)]

    def selected_panels(self) -> list[Panel]:
        return [i.obj for i in self.scene.selectedItems() if isinstance(i, PanelItem)]

    def add_panel(self, pos: QPointF):
        """Add > Panel: a click puts a new panel's top-left corner there (resize it in Object Properties)."""
        p = new_panel(self.panels_model(), self.panel_new_id(), pos)
        self.panels_model().append(p)
        self.panels_reload()
        for it in self.panel_items():
            it.setSelected(it.obj is p)
        self.panels_changed()

    def view_panel(self):
        """View > View Panel / Diagram > Panels > Show Panel: zoom to a panel."""
        p = pick_panel(self, self.panels_model(), 'View Panel', self.selected_panels())
        if p is not None:
            self.canvas.view_rect(QRectF(p.x, p.y, p.w, p.h).adjusted(-20, -30, 20, 20))

    def delete_panel(self):
        """Diagram > Panels > Delete Panel: remove a panel (not what is inside it)."""
        p = pick_panel(self, self.panels_model(), 'Delete Panel', self.selected_panels())
        if p is not None:
            self.panels_model().remove(p)
            self.panels_reload()
            self.panels_changed()

    def panel_properties(self):
        """Diagram > Panels > Object Properties: name and size of a panel."""
        p = pick_panel(self, self.panels_model(), 'Panel Properties', self.selected_panels())
        if p is None:
            return
        taken = {q.name for q in self.panels_model() if q is not p}
        if PanelDialog(self, p, taken, self.scene.readonly).exec():
            self.panels_reload()
            self.panels_changed()

    def protect_panels(self, on: bool):
        """Diagram > Panels > Protect All Panels: panels cannot be moved while it is on."""
        self.scene.panels_locked = on

    def print_panel(self):
        """Diagram > Panels > Print...: print the area of a panel."""
        from .editor_common import print_area
        p = pick_panel(self, self.panels_model(), 'Print Panel', self.selected_panels())
        if p is not None:
            print_area(self, self.scene, QRectF(p.x, p.y, p.w, p.h))

    def build_panel_actions(self, act, ro: bool):
        """Create the panel actions with the editor's `act(key, text, slot, ...)` helper."""
        act('view_panel', 'View Panel', self.view_panel)
        act('panel_show', 'Show Panel', self.view_panel)
        act('panel_delete', 'Delete Panel', None if ro else self.delete_panel)
        act('panel_props', 'Object Properties', self.panel_properties)
        act('panel_print', 'Print...', self.print_panel)
        act('panels_protect', 'Protect All Panels', self.protect_panels, checkable=True, checked=False)

    def update_panel_states(self, ro: bool):
        """Panel commands need a panel."""
        has = bool(self.panels_model())
        for key in ('view_panel', 'panel_show', 'panel_props', 'panel_print'):
            self.toolbar_actions[key].setEnabled(has)
        self.toolbar_actions['panel_delete'].setEnabled(has and not ro)
