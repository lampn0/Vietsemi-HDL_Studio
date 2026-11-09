"""Block diagram editor: graphics items, the editing scene and the editor window.

Items (each holds its model object in `obj`; see bd_model):
    _Movable        base of the objects that are dragged on the grid
      InstanceItem  component instance (body, name lines, ports)
      FrameItem     FOR / IF / ELSE generate frame (dashed box, resize handles)
      CommentItem   a box of the title block
      JunctionItem  the dot where nets of one name meet
      EmbeddedItem  embedded HDL block (yellow frame) and its white Text view
      PortIoItem    a module port (input / output / inout arrow)
    WireItem        one net segment chain, with handles to move points and segments

BdScene holds the items of one BlockDiagram, implements the legacy editing rules (what follows
when an object moves, how nets attach and connect, the add tools, routing) and emits
`changed_model` after every change. BdEditorWindow is the window: canvas, Signals /
Parameters tables, Diagram Browser, menus and toolbars with the legacy tool's names, popup menus,
dialogs, copy / paste, undo, save and generation.

Routing helpers (route_net, _avoid, _pin_route, ...) compute orthogonal net paths on the
grid. Coordinates are scene units (legacy units / 75); GRID is the legacy tool's 1000-unit grid.
"""
from __future__ import annotations

from version import APP_NAME
from .branding import install_app_icon, show_about
import math
import os
import re

from PySide6.QtCore import QEvent, QLineF, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QActionGroup, QBrush, QColor, QFont, QFontMetricsF, QKeySequence, QPainter,
                           QPainterPath, QPainterPathStroker, QPen, QPolygonF)
from PySide6.QtWidgets import (QApplication, QGraphicsSimpleTextItem, QComboBox, QDialog, QDialogButtonBox, QDockWidget, QFormLayout, QGraphicsItem,
                               QGraphicsPathItem, QGraphicsScene, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QToolBar, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget, QCheckBox, QGroupBox)

from bd_model import (NAME_LINE_H, BdComment, BdEmbedded, BdFrame, BdInstance, BdJunction, BdPin, BdPortIo, BdWire,
                        BlockDiagram)
from codegen.bd_codegen import generate_bd
from model import LANGUAGES, Parameter, Signal as Sig
from .bd_dialogs import PortIoPropertiesDialog, port_label
from .bd_dialogs import ComponentPicker, ComponentPropertiesDialog, SignalPropertiesDialog, library_of_file
from .code_view import CodeView
from .diagram import FsmGraphicsView
from .icons import icon
from . import editor_common as EC
from .menus import arrange_menus, bd_menus, table_menus
from .panels import PanelCommands, PanelItem
from .toolbars import BD_KEYS, BD_TOOLBARS, build_toolbars, fill_toolbars_menu
from .tables import ParametersTable, SignalsTable
from .undo import SnapshotUndo, load_view_state, save_view_state

# Diagram text. legacy diagrams name "courier", which the legacy tool on Windows draws with its default font
# (Arial, the user preference defaultFont); HDL Studio draws it the same way. (The names are older than
# that choice: MONO is not monospaced.)
DIAGRAM_FONT = 'Arial'
MONO = QFont(DIAGRAM_FONT, 8)
BOLD = QFont(DIAGRAM_FONT, 8, QFont.Bold)
LANG_LABEL = {'systemverilog': 'SystemVerilog', 'verilog': 'Verilog 2005'}
BLOCK_FILL = QColor(0, 230, 0)
EMB_FILL = QColor(255, 255, 145)          # the legacy block fill 65535,65535,37120
EMB_LINE = QColor(0, 0, 128)              # its line (block and Text view), 2 pixels wide
# net drawing tools: Add Signal / Bus, and their "with a Port" variants
NET_MODES = ('wire', 'bus', 'wire_port', 'bus_port')
EMB_NEW_SIZE = (8000 / 75, 10000 / 75)   # a new embedded block: 8000 x 10000 legacy units, as the legacy tool adds it
SEL_PEN = QPen(QColor(255, 120, 0), 2.5)
PIN_GRAB = 6.0
from .diagram import GRID, TEXT_LINE      # the legacy grid (1000 database units), shared with the state diagram
PORT_EDGE = GRID    # half width of a PortIO: body + stub span two grid squares, nets attach at the stub end
HANDLE_PX = 6.0     # selection handles keep this size on screen, whatever the zoom
PIN_HALF = 0.375 * GRID     # a component port is a triangle 0.75 grid long, from the body edge outward
_OUT = {'left': (-1, 0), 'right': (1, 0), 'top': (0, -1), 'bottom': (0, 1)}


def pin_end(pin) -> list[float]:
    """Where a net meets a component port: the outer end of its triangle (base or apex)."""
    o = _OUT[pin.side]
    return [pin.x + o[0] * PIN_HALF, pin.y + o[1] * PIN_HALF]


def _handles_at(p: QPainter, r: QRectF):
    """Small red squares on the corners of a selected text (the legacy tool's text selection)."""
    hs = HANDLE_PX * _px(p) / 2
    p.save()
    p.setPen(Qt.NoPen); p.setBrush(QColor(220, 0, 0))
    for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
        p.drawRect(QRectF(c.x() - hs / 1.5, c.y() - hs / 1.5, hs * 1.33, hs * 1.33))
    p.restore()


def _px(painter_or_view) -> float:
    """Scene units per screen pixel for a painter (item paint) or a view."""
    t = painter_or_view.worldTransform() if hasattr(painter_or_view, 'worldTransform') \
        else painter_or_view.transform()
    return 1.0 / max(abs(t.m11()), 1e-6)


def _scene_px(scene) -> float:
    """Scene units per screen pixel in the first view of `scene` (1 when it has no view)."""
    views = scene.views() if scene is not None else []
    return _px(views[0]) if views else 1.0
PIN_STEP = GRID     # spacing of pins on new components, one grid apart as in the legacy editor


def _pen(color: str, width: float, style: str) -> QPen:
    """A pen of `color` / `width` / style 'solid' | 'dash' | 'dot'; width 0 draws no line."""
    if width <= 0:
        return QPen(Qt.NoPen)
    return QPen(QColor(color), width, {'dash': Qt.DashLine, 'dot': Qt.DotLine}.get(style, Qt.SolidLine))


_FILL = {'solid': Qt.SolidPattern, 'dense': Qt.Dense3Pattern, 'medium': Qt.Dense5Pattern,
         'sparse': Qt.Dense7Pattern, 'horizontal': Qt.HorPattern, 'vertical': Qt.VerPattern, 'cross': Qt.CrossPattern,
         'diagonal': Qt.BDiagPattern, 'diagonal cross': Qt.DiagCrossPattern}


def _fill(p: QPainter, rect: QRectF, fg: str, bg: str, style: str):
    """Fill pattern: foreground pattern over the background colour; 'none' is transparent."""
    if style == 'none':
        return
    if style != 'solid':
        p.fillRect(rect, QColor(bg))
    p.fillRect(rect, QBrush(QColor(fg), _FILL.get(style, Qt.SolidPattern)))


def _snap(v: float) -> float:
    """Round a coordinate to the grid."""
    return round(v / GRID) * GRID


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
class _Movable(QGraphicsItem):
    """Base of the movable items: snaps to the grid while dragged, writes the new position into its
    model object and lets the scene move what is attached (BdScene.object_moved). While the scene
    moves objects along with another (`following`) or as a group, positions are taken as given.
    """
    kind = ''

    def __init__(self, scene: 'BdScene', obj):
        """An item for model object `obj` at its position (set before geometry changes are reported,
        so loading never snaps it).
        """
        super().__init__()
        self.bd_scene = scene
        self.obj = obj
        self.setPos(obj.x, obj.y)       # before ItemSendsGeometryChanges: no snapping on load
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(2)

    def itemChange(self, change, value):
        """Snap the new position (refused when read-only); once moved, update the model and the
        attached objects.
        """
        if change == QGraphicsItem.ItemPositionChange:
            if self.bd_scene.readonly:
                return self.pos()
            if self.bd_scene.following or self.bd_scene.group:
                return value                # carried along by another object: keep its offset
            return QPointF(_snap(value.x()), _snap(value.y()))
        if change == QGraphicsItem.ItemPositionHasChanged:
            dx, dy = self.pos().x() - self.obj.x, self.pos().y() - self.obj.y
            if dx or dy:
                self.obj.x, self.obj.y = self.pos().x(), self.pos().y()
                if not self.bd_scene.following:
                    self.bd_scene.object_moved(self, dx, dy)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        """End of a drag: a port I/O is connected where it was dropped; one undo step is recorded."""
        moved = event.buttonDownScenePos(Qt.LeftButton) != event.scenePos()
        super().mouseReleaseEvent(event)
        if self.kind == 'pio':
            self.bd_scene.end_routing()
        if moved:
            if self.kind == 'pio':
                self.bd_scene.port_dropped.emit(self.obj)
            self.bd_scene.changed_model.emit()


class InstanceItem(_Movable):
    """Component instance. A click on one of its ports selects that port (Ctrl+click adds one);
    dragging the port slides it along the edge of the component, and its net follows. A selected
    component has eight handles: dragging one resizes the body."""
    kind = 'inst'

    def __init__(self, scene, obj):
        """The item of instance `obj`; no port or name drag in progress."""
        super().__init__(scene, obj)
        self._pin_drag = None       # (pin, press position, original x, y) while moving a port
        self._text_drag = None      # (press position, original text position) while moving the name text
        self._resize = None         # (handle, body at press, press position) while resizing
        self._outline: QRectF | None = None     # the new body (scene) shown while resizing
        self._own_press = False     # the press selected a port or port name: its release must not select the body
        self.setAcceptHoverEvents(True)

    def _handles(self) -> dict[str, QPointF]:
        """The eight resize handles (item coordinates), by name: tl t tr r br b bl l."""
        w, h = self.obj.w, self.obj.h
        return {'tl': QPointF(0, 0), 't': QPointF(w / 2, 0), 'tr': QPointF(w, 0), 'r': QPointF(w, h / 2),
                'br': QPointF(w, h), 'b': QPointF(w / 2, h), 'bl': QPointF(0, h), 'l': QPointF(0, h / 2)}

    def _handle_at(self, pos: QPointF) -> str | None:
        """The resize handle under item position `pos` (only on a selected component), or None."""
        if not self.isSelected() or self.scene() is None:
            return None
        tol = (HANDLE_PX / 2 + 2) * _scene_px(self.scene())
        return next((k for k, c in self._handles().items()
                     if abs(c.x() - pos.x()) <= tol and abs(c.y() - pos.y()) <= tol), None)

    def hoverMoveEvent(self, e):
        """The resize cursor over a handle of the selected component."""
        sc = self.bd_scene
        k = self._handle_at(e.pos()) if sc.mode == 'select' and not sc.readonly else None
        cursors = {'tl': Qt.SizeFDiagCursor, 'br': Qt.SizeFDiagCursor, 'tr': Qt.SizeBDiagCursor,
                   'bl': Qt.SizeBDiagCursor, 't': Qt.SizeVerCursor, 'b': Qt.SizeVerCursor,
                   'l': Qt.SizeHorCursor, 'r': Qt.SizeHorCursor}
        if k:
            self.setCursor(cursors[k])
        else:
            self.unsetCursor()
        super().hoverMoveEvent(e)

    def _resized(self, k: str, r0: QRectF, dx: float, dy: float) -> QRectF:
        """The body after handle `k` was dragged by (dx, dy): edges on the grid, never past the ports
        along them (each port stays on its edge) nor smaller than two grid squares."""
        o = self.obj
        ys = [p.y for p in o.pins if p.side in ('left', 'right')]
        xs = [p.x for p in o.pins if p.side in ('top', 'bottom')]
        half = GRID / 2
        left, top, right, bottom = r0.left(), r0.top(), r0.right(), r0.bottom()
        if 'l' in k:
            lim = min([right - 2 * GRID] + [x - half for x in xs])
            left = min(_snap(left + dx), max(left, math.floor(lim / GRID) * GRID))
        if 'r' in k:
            lim = max([left + 2 * GRID] + [x + half for x in xs])
            right = max(_snap(right + dx), min(right, math.ceil(lim / GRID) * GRID))
        if k.startswith('t'):
            lim = min([bottom - 2 * GRID] + [y - half for y in ys])
            top = min(_snap(top + dy), max(top, math.floor(lim / GRID) * GRID))
        if k.startswith('b'):
            lim = max([top + 2 * GRID] + [y + half for y in ys])
            bottom = max(_snap(bottom + dy), min(bottom, math.ceil(lim / GRID) * GRID))
        return QRectF(QPointF(left, top), QPointF(right, bottom))

    def _apply_resize(self, r: QRectF):
        """Give the body rectangle `r` (scene): the ports on a moved edge go with it, keeping their
        place along it and their distance outside it; their nets are re-routed."""
        o, sc = self.obj, self.bd_scene
        r0 = QRectF(o.x, o.y, o.w, o.h)
        moves = []
        for pin in o.pins:
            x, y = pin.x, pin.y
            if pin.side == 'left':
                x += r.left() - r0.left()
            elif pin.side == 'right':
                x += r.right() - r0.right()
            elif pin.side == 'top':
                y += r.top() - r0.top()
            else:
                y += r.bottom() - r0.bottom()
            moves.append((pin, x, y))
        self.prepareGeometryChange()
        o.w, o.h = r.width(), r.height()
        sc.following = True                 # the body moves alone: the ports are placed below
        try:
            self.setPos(r.left(), r.top())
        finally:
            sc.following = False
        o.x, o.y = r.left(), r.top()
        for pin, x, y in moves:
            dx, dy = x - pin.x, y - pin.y
            if not dx and not dy:
                continue
            pin.x, pin.y = x, y
            for w, which in list(sc._attached(f'pin:{o.id}:{pin.name}')):
                pts = w.points
                i, j = (0, 1) if which == 'start' else (len(pts) - 1, len(pts) - 2)
                if len(pts) >= 2:
                    a, b = pts[i], pts[j]
                    # the net leaves the port straight along the move and the end does not reach the
                    # next corner: it only gets longer / shorter, as in the legacy tool
                    along_x = dy == 0 and abs(a[1] - b[1]) < 0.01 and (b[0] - a[0] - dx) * (b[0] - a[0]) > 0
                    along_y = dx == 0 and abs(a[0] - b[0]) < 0.01 and (b[1] - a[1] - dy) * (b[1] - a[1]) > 0
                    if along_x or along_y:
                        pts[i] = [a[0] + dx, a[1] + dy]
                    else:
                        sc._route_from_pin(w, which, o, pin)
                if w.id in sc.wire_items:
                    sc.wire_items[w.id].refresh()
        self.update()

    def name_lines(self) -> list[tuple[str, str, QRectF]]:
        """Visible name lines ('library', 'unit', 'instance') and their boxes in item coordinates.
        The lines keep their slots: a hidden library line leaves its place empty, as in the legacy tool."""
        o = self.obj
        fm = QFontMetricsF(BOLD)
        lines = [('library', o.library, o.show_library), ('unit', o.unit, True), ('instance', o.name, o.show_instance)]
        out = []
        if o.text_pos is None:                  # not placed yet: centred at the top of the body
            y = 3
            for kind, text, shown in lines:
                if shown:
                    w = fm.horizontalAdvance(text)
                    out.append((kind, text, QRectF((o.w - w) / 2, y, w, NAME_LINE_H)))
                    y += 10
            return out
        x, y = o.text_pos
        for k, (kind, text, shown) in enumerate(lines):
            if shown:
                out.append((kind, text, QRectF(x, y + k * NAME_LINE_H, fm.horizontalAdvance(text) + 2, NAME_LINE_H)))
        return out

    def name_rect(self) -> QRectF:
        """Box around all the visible name lines."""
        r = QRectF()
        for _, _, box in self.name_lines():
            r = r.united(box)
        return r

    def pin_label_rect(self, pin: BdPin) -> QRectF:
        """Box of the name of component port `pin` (item coordinates), where paint() writes it."""
        o, fm = self.obj, QFontMetricsF(MONO)
        text = port_label(pin.name, 'wire', False, pin.bounds, '', o)
        tw, asc, desc = fm.horizontalAdvance(text), fm.ascent(), fm.descent()
        lx, ly, t = pin.x - o.x, pin.y - o.y, PIN_HALF
        gap = 10 if pin.clock else 0
        if pin.side in ('left', 'right'):
            base = ly + 300 / 75
            x = lx + t + GRID + gap if pin.side == 'left' else lx - t - GRID - gap - tw
            return QRectF(x, base - asc, tw, asc + desc)
        # top / bottom ports: the name reads upward, its baseline at lx + 3
        y = ly + 7 if pin.side == 'top' else ly - 7 - tw
        return QRectF(lx + 3 - asc, y, asc + desc, tw)

    def pin_label_at(self, scene_pos: QPointF) -> BdPin | None:
        """The port whose name is under a scene position, or None."""
        pos = self.mapFromScene(scene_pos)
        return next((pin for pin in self.obj.pins
                     if self.pin_label_rect(pin).adjusted(-1, -1, 1, 1).contains(pos)), None)

    def name_at(self, scene_pos: QPointF) -> str:
        """Which name line is under a scene position ('' for none)."""
        pos = self.mapFromScene(scene_pos)
        return next((kind for kind, _, r in self.name_lines() if r.adjusted(-1, -1, 1, 1).contains(pos)), '')

    def boundingRect(self):
        """The body, the port names around it, the parameter lines below it and the name text."""
        extra = len(self.obj.params) * 10 + 4 if self.obj.show_params else 0
        r = QRectF(-90, -6, self.obj.w + 180, self.obj.h + 12 + extra).united(self.name_rect().adjusted(-2, -2, 2, 2))
        if self._outline is not None:
            r = r.united(self._outline.translated(-self.obj.x, -self.obj.y).adjusted(-2, -2, 2, 2))
        return r

    def shape(self):
        """Clickable area: the body, the name text and a grab square around each port.
        The rectangles overlap (the name usually lies inside the body, a port square half over
        the edge). With Qt's default odd-even fill an overlap counts twice and becomes a hole,
        so clicks on the name text hit nothing: the winding fill makes the overlaps solid."""
        p = QPainterPath()
        p.setFillRule(Qt.WindingFill)
        p.addRect(QRectF(0, 0, self.obj.w, self.obj.h))
        p.addRect(self.name_rect())             # the name text can be dragged outside the body
        for pin in self.obj.pins:               # the ports stick out of the body: make them clickable
            p.addRect(QRectF(pin.x - self.obj.x - PIN_GRAB, pin.y - self.obj.y - PIN_GRAB, 2 * PIN_GRAB, 2 * PIN_GRAB))
        if self.isSelected() and self.scene() is not None:   # the resize handles reach outside the body
            t = (HANDLE_PX / 2 + 2) * _scene_px(self.scene())
            for c in self._handles().values():
                p.addRect(QRectF(c.x() - t, c.y() - t, 2 * t, 2 * t))
        return p

    def pin_at(self, pos: QPointF) -> BdPin | None:
        """The port whose grab square contains scene point `pos`, or None."""
        return next((pin for pin in self.obj.pins
                     if abs(pin.x - pos.x()) <= PIN_GRAB and abs(pin.y - pos.y()) <= PIN_GRAB), None)

    def pin_target(self, pin: BdPin, x0: float, y0: float, side0: str, dx: float, dy: float
                   ) -> tuple[float, float, str]:
        """Where a port dragged by (dx, dy) from (x0, y0) lands: on the nearest edge of the body
        (any of the four), on the grid, keeping its distance outside the edge."""
        o = self.obj
        gap = {'left': o.x - x0, 'right': x0 - (o.x + o.w), 'top': o.y - y0, 'bottom': y0 - (o.y + o.h)}[side0]
        px, py = _snap(x0 + dx), _snap(y0 + dy)
        inside_x = min(max(px, o.x + 4), o.x + o.w - 4)
        inside_y = min(max(py, o.y + 4), o.y + o.h - 4)
        dist = {'left': abs(px - o.x), 'right': abs(px - (o.x + o.w)), 'top': abs(py - o.y),
                'bottom': abs(py - (o.y + o.h))}
        side = min(dist, key=lambda k: (dist[k], k != side0))
        if side == 'left':
            return o.x - gap, inside_y, side
        if side == 'right':
            return o.x + o.w + gap, inside_y, side
        if side == 'top':
            return inside_x, o.y - gap, side
        return inside_x, o.y + o.h + gap, side

    def mousePressEvent(self, e):
        """Select tool: a press on a name line selects that line (and starts moving the name text), a
        press on a port selects that port (and starts sliding it); elsewhere the default (select /
        move the component).
        """
        sc = self.bd_scene
        k = self._handle_at(e.pos()) \
            if e.button() == Qt.LeftButton and sc.mode == 'select' and not sc.readonly else None
        if k is not None:
            # a handle of the selected component: resize it (an outline follows the mouse, the body
            # changes on release, as in the legacy tool)
            self._resize = (k, QRectF(self.obj.x, self.obj.y, self.obj.w, self.obj.h), e.scenePos())
            e.accept()
            return
        pin = self.pin_at(e.scenePos()) if e.button() == Qt.LeftButton and sc.mode == 'select' else None
        kind = self.name_at(e.scenePos()) if pin is None and e.button() == Qt.LeftButton and sc.mode == 'select' else ''
        label = self.pin_label_at(e.scenePos()) \
            if pin is None and not kind and e.button() == Qt.LeftButton and sc.mode == 'select' else None
        if label is not None:
            # A press on a port name selects that name on its own (red box), as the legacy tool does;
            # the component stays unselected and does not move.
            sc.clearSelection()
            sc.select_text(self, 'pin:' + label.name)
            self._own_press = True
            e.accept()
            return
        if kind:
            # A press on a name line (library / component / instance) selects that line only,
            # like the legacy tool: the body stays unselected and a drag moves the name text, not the component.
            sc.clearSelection()
            sc.select_text(self, kind)
            if not sc.readonly:
                # The drag works on text_pos, the top-left of the library line slot. A component
                # that was never placed has no text_pos yet: start from where it is drawn now
                # (centred lines), so the text does not jump when the drag begins.
                if self.obj.text_pos is None:
                    first_kind, _, r = self.name_lines()[0]
                    slot = ['library', 'unit', 'instance'].index(first_kind)
                    start = [r.x(), r.y() - slot * NAME_LINE_H]
                else:
                    start = list(self.obj.text_pos)
                self._text_drag = (e.scenePos(), start)
            e.accept()
            return
        if pin is None:
            return super().mousePressEvent(e)
        if e.modifiers() & Qt.ControlModifier:
            # Ctrl+click: add the port to the selection (or take it out), as the legacy tool does
            sc.select_pin(self, pin, toggle=True)
            self._own_press = True
            e.accept()
            return
        sc.clearSelection()
        sc.select_pin(self, pin)
        if not sc.readonly:
            self._pin_drag = (pin, e.scenePos(), pin.x, pin.y, pin.side)
        e.accept()

    def mouseMoveEvent(self, e):
        """Move the name text, or slide the dragged port to the nearest edge point (Shift: only
        horizontally or vertically).
        """
        if self._resize is not None:
            k, r0, p0 = self._resize
            d = e.scenePos() - p0
            self.prepareGeometryChange()
            self._outline = self._resized(k, r0, d.x(), d.y())
            self.update()
            return
        if self._text_drag is not None:
            p0, (x0, y0) = self._text_drag
            d = e.scenePos() - p0
            self.prepareGeometryChange()
            self.obj.text_pos = [_snap(x0 + d.x()), _snap(y0 + d.y())]
            self.update()
            return
        if self._pin_drag is None:
            return super().mouseMoveEvent(e)
        pin, p0, x0, y0, side0 = self._pin_drag
        d = e.scenePos() - p0
        if e.modifiers() & Qt.ShiftModifier:
            d = QPointF(d.x(), 0) if abs(d.x()) >= abs(d.y()) else QPointF(0, d.y())
        self.bd_scene.move_pin(self, pin, *self.pin_target(pin, x0, y0, side0, d.x(), d.y()))

    def mouseReleaseEvent(self, e):
        """End of a resize, name or port drag: record the change when something moved."""
        if self._own_press:
            self._own_press = False
            e.accept()
            return
        if self._resize is not None:
            r0, r = self._resize[1], self._outline
            self._resize = None
            self.prepareGeometryChange()
            self._outline = None
            if r is not None and r != r0:
                self._apply_resize(r)
                self.bd_scene.changed_model.emit()
            self.update()
            return
        if self._text_drag is not None:
            moved = e.scenePos() != self._text_drag[0]
            self._text_drag = None
            self.update()
            if moved:
                self.bd_scene.changed_model.emit()
            return
        if self._pin_drag is None:
            return super().mouseReleaseEvent(e)
        pin, _, x0, y0, _ = self._pin_drag
        self._pin_drag = None
        if (pin.x, pin.y) != (x0, y0):
            self.bd_scene.changed_model.emit()

    def paint(self, p: QPainter, opt, widget=None):
        """Draw the component as the legacy tool does: body (fill / line style), corner handles when selected,
        name lines (the selected one boxed in red), parameter values, and each port (a triangle
        pointing in for inputs / out for outputs, clock mark, label next to it; top / bottom port
        labels read upward). The selected port gets four small handles.
        """
        o = self.obj
        _fill(p, QRectF(0, 0, o.w, o.h), o.fg, o.bg, o.fill_style)
        p.setBrush(Qt.NoBrush)
        p.setPen(_pen(o.line_color, 1.5 * o.line_width, o.line_style))
        p.drawRect(QRectF(0, 0, o.w, o.h))
        if self.isSelected():
            # as the legacy tool: a selected component keeps its outline and gets eight resize handles
            p.save()
            p.setPen(Qt.NoPen); p.setBrush(Qt.black)
            hr = HANDLE_PX * _px(p) / 2
            for c in self._handles().values():
                p.drawRect(QRectF(c.x() - hr, c.y() - hr, 2 * hr, 2 * hr))
            p.restore()
        if self._outline is not None:           # the new body while a handle is dragged
            p.save()
            p.setPen(QPen(Qt.black, 0)); p.setBrush(Qt.NoBrush)
            p.drawRect(self._outline.translated(-o.x, -o.y))
            p.restore()
        p.setFont(BOLD)
        p.setPen(Qt.black)
        for _, text, r in self.name_lines():
            p.drawText(r, Qt.AlignLeft | Qt.AlignVCenter, text)
        sel = self.bd_scene.selected_text
        if sel is not None and sel[0] == o.id:
            # The selected name line: red box with a small handle at each corner, as in the legacy tool.
            box = next((r for kind, _, r in self.name_lines() if kind == sel[1]), None)
            sel_pin = next((q for q in o.pins if 'pin:' + q.name == sel[1]), None)
            if sel_pin is not None:
                # a port name: its box, and a red dashed line from the port to it (legacy tool)
                box = self.pin_label_rect(sel_pin)
                pen = QPen(QColor(220, 0, 0), 0, Qt.DashLine)
                p.setPen(pen)
                end = QPointF(box.left(), box.center().y()) if sel_pin.side == 'left' else \
                    QPointF(box.right(), box.center().y()) if sel_pin.side == 'right' else \
                    QPointF(box.center().x(), box.top() if sel_pin.side == 'top' else box.bottom())
                p.drawLine(QPointF(sel_pin.x - o.x, sel_pin.y - o.y), end)
            if box is not None:
                px = _px(p)                     # one screen pixel in item units (handles keep their size)
                p.setPen(QPen(QColor(220, 0, 0), 0)); p.setBrush(Qt.NoBrush)
                p.drawRect(box)
                h = 2 * px
                for c in (box.topLeft(), box.topRight(), box.bottomLeft(), box.bottomRight()):
                    p.drawRect(QRectF(c.x() - h, c.y() - h, 2 * h, 2 * h))
            p.setPen(Qt.black)
        p.setFont(MONO)
        fm = p.fontMetrics()
        if o.show_params and o.params:
            p.setPen(QColor(0, 0, 160))
            for k, prm in enumerate(o.params):
                p.drawText(QPointF(4, o.h + 10 + k * 10), f'{prm.name} = {prm.value}')
            p.setPen(Qt.black)
        for pin in o.pins:
            lx, ly = pin.x - o.x, pin.y - o.y
            p.setPen(QPen(QColor(0, 100, 0), 1))
            p.setBrush(QColor(0, 160, 0) if pin.net else QColor(255, 255, 255))
            if pin.clock:                       # clock input: edge triangle inside the body
                ex = min(max(lx, 0), o.w); ey = min(max(ly, 0), o.h)
                ix, iy = {'left': (1, 0), 'right': (-1, 0), 'top': (0, 1), 'bottom': (0, -1)}[pin.side]
                p.save(); p.setPen(QPen(QColor(0, 128, 0), 1)); p.setBrush(QColor(0, 255, 0))
                p.drawPolygon(QPolygonF([QPointF(ex - 5 * iy, ey - 5 * ix), QPointF(ex + 10 * ix, ey + 10 * iy),
                                         QPointF(ex + 5 * iy, ey + 5 * ix)]))
                p.restore()
            if pin.side in ('left', 'right'):
                inward = 1 if pin.side == 'left' else -1
                d = inward if pin.mode == 'input' else -inward      # inputs point into the body
                if pin.arrow in ('left', 'right'):
                    d = 1 if pin.arrow == 'right' else -1
                t = PIN_HALF
                p.drawPolygon(QPolygonF([QPointF(lx - t * d, ly - t), QPointF(lx + t * d, ly),
                                         QPointF(lx - t * d, ly + t)]))
                p.setPen(Qt.black)
                text = port_label(pin.name, 'wire', False, pin.bounds, '', o)
                gap = 10 if pin.clock else 0    # after the clock mark
                # as the legacy tool saves component ports: the name starts 1000 units (one grid step) past
                # the triangle, its baseline 300 units below the port's line
                g, base = GRID, 300 / 75
                if pin.side == 'left':
                    p.drawText(QPointF(lx + t + g + gap, ly + base), text)
                else:
                    p.drawText(QPointF(lx - t - g - gap - fm.horizontalAdvance(text), ly + base), text)
            else:
                inward = 1 if pin.side == 'top' else -1
                d = inward if pin.mode == 'input' else -inward
                if pin.arrow in ('up', 'down'):
                    d = 1 if pin.arrow == 'down' else -1
                t = PIN_HALF
                p.drawPolygon(QPolygonF([QPointF(lx - t, ly - t * d), QPointF(lx, ly + t * d),
                                         QPointF(lx + t, ly - t * d)]))
                p.setPen(Qt.black)
                text = port_label(pin.name, 'wire', False, pin.bounds, '', o)
                p.save()                        # names of top/bottom ports read upward inside the body (legacy "ro 270")
                if pin.side == 'top':                           # ends at the port
                    p.translate(lx + 3, ly + 7 + fm.horizontalAdvance(text))
                else:                                           # starts at the port
                    p.translate(lx + 3, ly - 7)
                p.rotate(-90)
                p.drawText(QPointF(0, 0), text)
                p.restore()
        for iid, name in self.bd_scene.selected_pins:
            pin = next((q for q in o.pins if q.name == name), None) if iid == o.id else None
            if pin is not None:
                px = _px(p)
                p.setPen(QPen(Qt.black, 0)); p.setBrush(Qt.white)
                lx, ly = pin.x - o.x, pin.y - o.y
                d, s = 6 * px, 4 * px
                for cx, cy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                    p.drawRect(QRectF(lx + cx * d - s / 2, ly + cy * d - s / 2, s, s))


# the outline colour of each frame kind while its Line Color is not set
_FRAME_COLORS = {'for': QColor(96, 96, 96), 'if': QColor(0, 90, 170), 'else': QColor(150, 60, 0)}


class FrameItem(_Movable):
    """Generate frame (FOR / IF / ELSE): dashed box with its title; picked by its border
    or title so the objects inside stay clickable. Moving it moves what is inside."""
    kind = 'frame'

    HANDLE = 5.0

    def __init__(self, scene, obj):
        """A frame item, drawn below everything else."""
        super().__init__(scene, obj)
        self.setZValue(0)
        self._resize = None         # (handle, original rect, press position) while resizing

    def _handles(self) -> dict[str, QPointF]:
        """The eight resize handle positions (item coordinates), by name: tl t tr r br b bl l."""
        w, h = self.obj.w, self.obj.h
        return {'tl': QPointF(0, 0), 't': QPointF(w / 2, 0), 'tr': QPointF(w, 0), 'r': QPointF(w, h / 2),
                'br': QPointF(w, h), 'b': QPointF(w / 2, h), 'bl': QPointF(0, h), 'l': QPointF(0, h / 2)}

    def _handle_at(self, pos: QPointF) -> str | None:
        """The resize handle under `pos` (only on a selected frame), or None."""
        if not self.isSelected():
            return None
        tol = (HANDLE_PX / 2 + 2) * _scene_px(self.scene())
        for k, c in self._handles().items():
            if abs(c.x() - pos.x()) <= tol and abs(c.y() - pos.y()) <= tol:
                return k
        return None

    def mousePressEvent(self, e):
        """A press on a handle starts a resize; elsewhere the default (select / move)."""
        k = self._handle_at(e.pos()) if e.button() == Qt.LeftButton and not self.bd_scene.readonly else None
        if k is None:
            return super().mousePressEvent(e)
        self._resize = (k, QRectF(self.obj.x, self.obj.y, self.obj.w, self.obj.h), e.scenePos())
        e.accept()

    def mouseMoveEvent(self, e):
        """Resize the frame from the dragged handle (on the grid, with a minimum size). The objects
        inside do not move while resizing.
        """
        if self._resize is None:
            return super().mouseMoveEvent(e)
        k, r0, p0 = self._resize
        dx, dy = _snap(e.scenePos().x() - p0.x()), _snap(e.scenePos().y() - p0.y())
        left, top, right, bottom = r0.left(), r0.top(), r0.right(), r0.bottom()
        if 'l' in k:
            left = min(left + dx, right - 40)
        if 'r' in k:
            right = max(right + dx, left + 40)
        if k.startswith('t'):
            top = min(top + dy, bottom - 30)
        if k.startswith('b'):
            bottom = max(bottom + dy, top + 30)
        self.prepareGeometryChange()
        o = self.obj
        o.w, o.h = right - left, bottom - top
        self.bd_scene.following = True          # resizing moves the frame, not what is inside
        try:
            self.setPos(left, top)
        finally:
            self.bd_scene.following = False
        o.x, o.y = left, top
        self.update()

    def mouseReleaseEvent(self, e):
        """End of a resize: record the change when the frame changed."""
        if self._resize is None:
            return super().mouseReleaseEvent(e)
        r0 = self._resize[1]
        self._resize = None
        if QRectF(self.obj.x, self.obj.y, self.obj.w, self.obj.h) != r0:
            self.bd_scene.changed_model.emit()

    def _title_rect(self) -> QRectF:
        """Rectangle of the title text above the frame."""
        return QRectF(0, -16, max(80.0, len(self.obj.title) * 7.0 + 10), 15)

    def boundingRect(self):
        """The frame, its title and the handles."""
        o = self.obj
        return QRectF(-6, -18, max(o.w, self._title_rect().width()) + 12, o.h + 24)

    def shape(self):
        """Clickable area: only the border, the title and the handles, so the objects inside the frame
        stay clickable.
        """
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)        # a handle over the title must not punch a hole in it
        if self.obj.show_label:
            path.addRect(self._title_rect())
        if self.isSelected():
            for c in self._handles().values():
                path.addRect(QRectF(c.x() - self.HANDLE, c.y() - self.HANDLE, 2 * self.HANDLE, 2 * self.HANDLE))
        stroke = QPainterPathStroker()
        stroke.setWidth(8)
        rect = QPainterPath()
        rect.addRect(QRectF(0, 0, self.obj.w, self.obj.h))
        return path.united(stroke.createStroke(rect))

    def paint(self, p: QPainter, opt, widget=None):
        """The frame as the legacy tool draws it: outline (grey dashed by default, Edit Appearance changes it),
        the sequence number box at the top left inside, the title above in plain black text; handles."""
        o = self.obj
        color = QColor(o.line_color) if o.line_color else _FRAME_COLORS.get(o.kind, QColor(96, 96, 96))
        style = {'solid': Qt.SolidLine, 'dash': Qt.DashLine, 'dot': Qt.DotLine}.get(o.line_style, Qt.DashLine)
        pen = QPen(color, max(o.line_width, 1), style)
        pen.setCosmetic(True)
        p.setPen(pen if o.line_width > 0 else Qt.NoPen)
        p.setBrush(QBrush(QColor(o.fg), _FILL[o.fill_style]) if o.fill_style in _FILL else Qt.NoBrush)
        p.drawRect(QRectF(0, 0, o.w, o.h))
        if o.show_number:
            p.setPen(Qt.black)
            p.setBrush(Qt.white)
            p.drawRect(QRectF(4, 4, 12, 12))
            p.setFont(MONO)
            p.drawText(QRectF(4, 4, 12, 12), Qt.AlignCenter, str(o.number))
        if o.show_label:
            p.setFont(MONO)
            p.setPen(Qt.black)
            p.drawText(QPointF(1, -4), o.title)
        if self.isSelected():                   # black handles, as in the legacy editor
            p.setPen(Qt.NoPen)
            p.setBrush(Qt.black)
            r = HANDLE_PX * _px(p) / 2
            for c in self._handles().values():
                p.drawRect(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r))

    def mouseDoubleClickEvent(self, e):
        """Double-click opens the frame's properties."""
        self.bd_scene.frame_edit_requested.emit(self.obj)


def expand_title_text(text: str, bd: BlockDiagram) -> str:
    """Variables of the legacy title block, as shown on the diagram."""
    import getpass
    from datetime import datetime
    now = datetime.now()
    values = {'%project_name': bd.library, '%library': bd.library, '%unit': bd.unit, '%view': bd.view,
              '%language': 'SystemVerilog' if bd.language == 'systemverilog' else 'Verilog',
              '%user': getpass.getuser(), '%month': now.strftime('%b'), '%year': now.strftime('%Y'),
              '%dd': now.strftime('%d'), '%date': now.strftime('%d %b %Y'), '%time': now.strftime('%H:%M:%S')}
    for k in sorted(values, key=len, reverse=True):     # longest first: %date before %dd
        text = text.replace(k, values[k])
    return text


class CommentItem(_Movable):
    """Box of the title block (boxes of one group move together), or a free comment text."""
    kind = 'cmt'
    find_span = None                # (start, end) of the match Find Next shows (editor_common.mark_text)

    def boundingRect(self):
        """The box."""
        return QRectF(0, 0, self.obj.w, self.obj.h)

    def paint(self, p: QPainter, opt, widget=None):
        """Fill, border and the text with the title block variables expanded."""
        o = self.obj
        if o.fill:
            p.fillRect(self.boundingRect(), QColor(o.fill))
        if o.group or self.isSelected():
            # the boxes of the title block are framed; a free comment text only while selected
            p.setPen(SEL_PEN if self.isSelected() else QPen(QColor(0, 0, 0), 0))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.boundingRect())
        p.setFont(MONO)
        p.setPen(QColor(o.color))
        if self.find_span is not None and not o.group:
            # Find Next on a comment text: the match drawn on the selection blue
            from .editor_common import paint_text_lines
            fm = QFontMetricsF(MONO)
            lines = o.text.split(chr(10))
            top = (self.boundingRect().height() - fm.height() * len(lines)) / 2
            paint_text_lines(p, lines, 3, top, fm, self.find_span, QColor(o.color))
            return
        p.drawText(self.boundingRect().adjusted(3, 0, -2, 0), Qt.AlignLeft | Qt.AlignVCenter,
                   expand_title_text(o.text, self.bd_scene.bd))

    def mouseDoubleClickEvent(self, e):
        """A double-click on a free comment text edits it (the title block boxes are edited in their dialog)."""
        if not self.obj.group and not self.bd_scene.readonly:
            self.bd_scene.comment_edit_requested.emit(self.obj)
            return
        super().mouseDoubleClickEvent(e)

TEXT_LINE = 1000 / 75       # one line of the legacy text blocks (1000 units)
TEXT_BASE = 700 / 75        # baseline below the top of a line


def _decl_lines(bd: BlockDiagram, sigs, ports: bool) -> list[str]:
    """Declarations of the Ports: / Diagram Signals: sections, as the legacy block lists them:
    "wire [bounds]" padded to a column, the name, ";" and the comment."""
    rows = []
    for s in sorted(sigs, key=lambda s: s.name.lower()):         # by name, as the legacy block lists them
        if (s.mode in ('input', 'output', 'inout')) != ports:
            continue
        head = f'{s.type or "wire"} {s.bounds}'.rstrip()
        rows.append((head, s.name, s.comment))
    width = max((len(h) for h, _, _ in rows), default=0) + 3
    return [f'{h.ljust(width)}{n};' + (f' // {c}' if c else '') for h, n, c in rows]


class TextBlockItem(_Movable):
    """The Declarations or Compiler Directives block drawn on a block diagram, as the legacy tool shows them
    (model BdTextBlock): bold labels, the text under each, one line every 1000 units. It is moved like
    any object; Hide Text (popup) or Object Visibility hide it."""
    kind = 'txt'

    def lines(self) -> list[tuple[str, bool, float]]:
        """(text, bold, indent) of each line drawn."""
        bd, o = self.bd_scene.bd, self.obj
        out = []
        if o.id == 'decl':
            out.append(('Declarations', True, 0.0))
            if o.contents:
                out.append(('Ports:', True, 0.0))
                out += [(t, False, 2000 / 75) for t in _decl_lines(bd, bd.signals, True)]
                if bd.pre_user_declarations.strip():
                    out.append(('Pre User:', True, 0.0))
                    out += [(t, False, 2000 / 75) for t in bd.pre_user_declarations.strip('\n').split('\n')]
                out.append(('Diagram Signals:', True, 0.0))
                out += [(t, False, 2000 / 75) for t in _decl_lines(bd, bd.signals, False)]
                if bd.post_user_declarations.strip():
                    out.append(('Post User:', True, 0.0))
                    out += [(t, False, 2000 / 75) for t in bd.post_user_declarations.strip('\n').split('\n')]
        else:
            out.append(('Compiler Directives', True, 0.0))
            for label, text in (('Pre-module directives:', bd.pre_module_directives),
                                ('Post-module directives:', bd.post_module_directives),
                                ('End-module directives:', bd.end_module_directives)):
                out.append((label, True, 0.0))
                out += [(t, False, 0.0) for t in text.strip('\n').split('\n') if text.strip()]
        return out

    def boundingRect(self):
        """The lines of text."""
        w = 0.0
        for text, bold, indent in self.lines():
            w = max(w, indent + QFontMetricsF(BOLD if bold else MONO).horizontalAdvance(text))
        return QRectF(-2, -2, w + 4, len(self.lines()) * TEXT_LINE + 4)

    def paint(self, p: QPainter, opt, widget=None):
        """The labels in bold, the text in the normal font; a selected block shows its outline in red,
        as the legacy tool marks a selected text."""
        for k, (text, bold, indent) in enumerate(self.lines()):
            p.setFont(BOLD if bold else MONO)
            p.setPen(Qt.black)
            p.drawText(QPointF(indent, k * TEXT_LINE + TEXT_BASE), text)
        if self.isSelected():
            p.setPen(QPen(QColor(220, 0, 0), 0)); p.setBrush(Qt.NoBrush)
            r = self.boundingRect().adjusted(2, 2, -2, -2)
            first = QFontMetricsF(BOLD).horizontalAdvance(self.lines()[0][0])
            p.drawRect(QRectF(0, 0, first, TEXT_LINE))
            _handles_at(p, QRectF(0, 0, first, TEXT_LINE))


class JunctionItem(_Movable):
    """Dot where nets meet; the nets attached to it follow when it moves."""
    kind = 'jct'

    def boundingRect(self):
        """A small square around the dot."""
        return QRectF(-4, -4, 8, 8)

    def paint(self, p: QPainter, opt, widget=None):
        """A black dot (red when selected)."""
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(220, 0, 0) if self.isSelected() else Qt.black)
        p.drawEllipse(QPointF(0, 0), 3, 3)


def _text_file_icon(p: QPainter, r: QRectF):
    """The view icon of an embedded block with a Text view (the legacy TextFile icon, redrawn): a white
    page with a folded corner and a few lines of text, on a grey square."""
    p.save()
    p.setPen(QPen(QColor(90, 90, 90), 0)); p.setBrush(QColor(192, 192, 192))
    p.drawRect(r)
    m = r.width() * 0.18
    pg = r.adjusted(m, m * 0.6, -m, -m * 0.6)
    k = pg.width() * 0.35
    p.setBrush(Qt.white)
    p.drawPolygon(QPolygonF([pg.topLeft(), QPointF(pg.right() - k, pg.top()), QPointF(pg.right(), pg.top() + k),
                             pg.bottomRight(), pg.bottomLeft()]))
    p.setPen(QPen(Qt.black, 0))
    for i in range(1, 5):
        y = pg.top() + k * 0.6 + i * (pg.height() - k) / 5
        p.drawLine(QPointF(pg.left() + 2 * m / 3, y), QPointF(pg.right() - 2 * m / 3, y))
    p.restore()


class EmbeddedItem(_Movable):
    """Embedded HDL text block. Nets attach to it at points on its edge (wire end reference
    "emb:<id>"), not to ports. A press on one of those points drags the net end along the
    edge, as a component port is dragged; a press anywhere else moves the whole block."""
    kind = 'emb'

    def __init__(self, scene, obj):
        """The item of embedded block `obj`; no net end or Text view drag in progress."""
        super().__init__(scene, obj)
        # while a net end is dragged: (wire, 'start' | 'end', press position, end x, end y, side,
        # the net's points at the press)
        self._end_drag = None
        # while the Text view is moved or resized: ('move' | 'resize', press position, box at press)
        self._box_drag = None

    def _size(self) -> tuple[float, float]:
        """Size of the block (never smaller than 60 x 30)."""
        return max(self.obj.w, 60), max(self.obj.h, 30)

    def text_rect(self) -> QRectF | None:
        """The white Text view box in item coordinates; None while the block has no view.
        A block saved before text boxes existed but holding code shows it inside the frame."""
        o = self.obj
        if o.text_box:
            return QRectF(*o.text_box)
        if o.text.strip():
            w, h = self._size()
            return QRectF(13, 13, w - 26, h - 26)
        return None

    def boundingRect(self):
        """The block, the net triangles outside its edges, the name above it and the Text view."""
        # painted area: the body, the net triangles outside its edges, the name above it and
        # the text box (which may lie outside the body)
        w, h = self._size()
        m = 2 * PIN_HALF + 2
        r = QRectF(-m, -16, w + 2 * m, h + 16 + m)
        box = self.text_rect()
        return r.united(box.adjusted(-2, -2, 2, 2)) if box is not None else r

    def shape(self):
        """Clickable area: the block with the grab distance of its net ends, the Text view and its
        resize handle.
        """
        # clickable area: the body plus the grab distance of the net ends on its edge, and the
        # text box (winding fill: where the two overlap must not become a hole)
        w, h = self._size()
        p = QPainterPath()
        p.setFillRule(Qt.WindingFill)
        p.addRect(QRectF(-PIN_GRAB, -PIN_GRAB, w + 2 * PIN_GRAB, h + 2 * PIN_GRAB))
        box = self.text_rect()
        if box is not None:
            p.addRect(box)
            # the resize handle on the box corner reaches outside the box: grab all of it
            # (the same tolerance as _box_handle)
            t = (HANDLE_PX / 2 + 2) * _scene_px(self.scene()) if self.scene() is not None else 4
            c = box.bottomRight()
            p.addRect(QRectF(c.x() - t, c.y() - t, 2 * t, 2 * t))
        return p

    def in_text(self, scene_pos: QPointF) -> bool:
        """Whether a scene position is on the white Text view (else on the yellow block)."""
        box = self.text_rect()
        return box is not None and box.contains(self.mapFromScene(scene_pos))

    def body(self) -> QRectF:
        """The block in scene coordinates."""
        w, h = self._size()
        return QRectF(self.obj.x, self.obj.y, w, h)

    def end_at(self, pos: QPointF) -> tuple[BdWire, str] | None:
        """The net end attached to this block under a scene position (within the port grab
        distance), as (wire, 'start' | 'end'); None when there is none."""
        for w, which in self.bd_scene._attached(f'emb:{self.obj.id}'):
            if not w.points:
                continue
            x, y = w.points[0] if which == 'start' else w.points[-1]
            if abs(x - pos.x()) <= PIN_GRAB and abs(y - pos.y()) <= PIN_GRAB:
                return w, which
        return None

    def edge_side(self, x: float, y: float) -> str:
        """Edge of the block nearest to a point: left, right, top or bottom."""
        b = self.body()
        dist = {'left': abs(x - b.left()), 'right': abs(x - b.right()),
                'top': abs(y - b.top()), 'bottom': abs(y - b.bottom())}
        return min(dist, key=dist.get)

    def edge_point(self, x: float, y: float) -> tuple[float, float, str]:
        """The point of the block edge nearest to (x, y), on the grid along the edge and kept
        off the corners, with its side: where a net drawn to (x, y) attaches."""
        b = self.body()
        side = self.edge_side(x, y)
        ax = min(max(_snap(x), b.left() + 4), b.right() - 4)
        ay = min(max(_snap(y), b.top() + 4), b.bottom() - 4)
        return {'left': (b.left(), ay), 'right': (b.right(), ay), 'top': (ax, b.top()),
                'bottom': (ax, b.bottom())}[side] + (side,)

    def edge_target(self, x0: float, y0: float, side0: str, dx: float, dy: float) -> tuple[float, float, str]:
        """Where a net end dragged by (dx, dy) from (x0, y0) lands: on the grid, on the nearest
        edge of the block (it may turn a corner), keeping its distance off the edge (legacy
        diagrams sometimes end a net a little outside the block)."""
        b = self.body()
        gap = {'left': b.left() - x0, 'right': x0 - b.right(), 'top': b.top() - y0, 'bottom': y0 - b.bottom()}[side0]
        px, py = _snap(x0 + dx), _snap(y0 + dy)
        # stay off the corners, so the end clearly belongs to one edge
        inside_x = min(max(px, b.left() + 4), b.right() - 4)
        inside_y = min(max(py, b.top() + 4), b.bottom() - 4)
        side = self.edge_side(px, py)
        if side == 'left':
            return b.left() - gap, inside_y, side
        if side == 'right':
            return b.right() + gap, inside_y, side
        if side == 'top':
            return inside_x, b.top() - gap, side
        return inside_x, b.bottom() + gap, side

    def _box_handle(self, scene_pos: QPointF) -> bool:
        """Whether a scene position is on the resize handle (bottom-right corner) of the Text view."""
        box = self.text_rect()
        if box is None:
            return False
        p = self.mapFromScene(scene_pos)
        tol = (HANDLE_PX / 2 + 2) * _scene_px(self.scene())
        return abs(p.x() - box.right()) <= tol and abs(p.y() - box.bottom()) <= tol

    def mousePressEvent(self, e):
        """Select tool: a press on a net end starts sliding that end along the edge; a press on the
        Text view (or its corner handle) starts moving (resizing) the view; elsewhere the default
        (select / move the block).
        """
        sc = self.bd_scene
        hit = self.end_at(e.scenePos()) if e.button() == Qt.LeftButton and sc.mode == 'select' else None
        if hit is None and e.button() == Qt.LeftButton and sc.mode == 'select' and                 (self.in_text(e.scenePos()) or self._box_handle(e.scenePos())):
            # The Text view is anchored to the block but moves and resizes on its own (as in the legacy tool):
            # a drag on it moves the text box, a drag on its corner handle resizes it.
            sc.clearSelection(); self.setSelected(True)
            if not sc.readonly:
                box = self.text_rect()
                kind = 'resize' if self._box_handle(e.scenePos()) else 'move'
                self._box_drag = (kind, e.scenePos(), [box.x(), box.y(), box.width(), box.height()])
            e.accept()
            return
        if hit is None:
            return super().mousePressEvent(e)   # not on a net end: select / move the block
        w, which = hit
        sc.clearSelection()
        if w.id in sc.wire_items:
            sc.wire_items[w.id].setSelected(True)   # the dragged net shows as selected
        if not sc.readonly:
            x, y = w.points[0] if which == 'start' else w.points[-1]
            self._end_drag = (w, which, e.scenePos(), x, y, self.edge_side(x, y), [list(q) for q in w.points])
        e.accept()

    def mouseMoveEvent(self, e):
        """Move / resize the Text view, or slide the dragged net end along the edge (re-routing it
        from the points it had at the press; Shift: one axis only).
        """
        if getattr(self, '_box_drag', None) is not None:
            kind, p0, (bx, by, bw, bh) = self._box_drag
            d = e.scenePos() - p0
            self.prepareGeometryChange()
            if kind == 'move':
                self.obj.text_box = [_snap(bx + d.x()), _snap(by + d.y()), bw, bh]
            else:                               # resize, never smaller than 4 x 2 grid squares
                self.obj.text_box = [bx, by, max(4 * GRID, _snap(bw + d.x())), max(2 * GRID, _snap(bh + d.y()))]
            self.update()
            return
        if self._end_drag is None:
            return super().mouseMoveEvent(e)
        w, which, p0, x0, y0, side0, orig = self._end_drag
        d = e.scenePos() - p0
        if e.modifiers() & Qt.ShiftModifier:    # Shift: only along one axis
            d = QPointF(d.x(), 0) if abs(d.x()) >= abs(d.y()) else QPointF(0, d.y())
        x, y, side = self.edge_target(x0, y0, side0, d.x(), d.y())
        # Re-route the net from the new end point the same way a component port does: straight
        # out of the edge, then right angles to the rest of the net. _leave_edge only needs the
        # point and the side, so a throw-away BdPin carries them. Always start from the points the
        # net had at the press: routing the already re-routed net again would pile up stubs.
        w.points = [list(q) for q in orig]
        _leave_edge(w, which, BdPin('', x=x, y=y, side=side))
        sc = self.bd_scene
        if w.id in sc.wire_items:
            sc.wire_items[w.id].refresh()

    def mouseReleaseEvent(self, e):
        """End of a Text view or net end drag: tidy the net and record the change when it moved."""
        if getattr(self, '_box_drag', None) is not None:
            moved = e.scenePos() != self._box_drag[1]
            self._box_drag = None
            if moved:
                self.bd_scene.changed_model.emit()
            return
        if self._end_drag is None:
            return super().mouseReleaseEvent(e)
        w, which, p0, x0, y0, _, orig = self._end_drag
        self._end_drag = None
        end = w.points[0] if which == 'start' else w.points[-1]
        moved = bool(w.points) and (end[0], end[1]) != (x0, y0)
        # dropped back where it started: keep the net exactly as it was (no re-routed stub)
        w.points = _simplify(w.points) if moved else orig
        if w.id in self.bd_scene.wire_items:
            self.bd_scene.wire_items[w.id].refresh()
        if moved:
            self.bd_scene.changed_model.emit()

    def paint(self, p: QPainter, opt, widget=None):
        """Draw the yellow block (outline only for the Add preview), its name, the Text view with the
        code clipped to it (with the anchor line and resize handle when selected), the "no view" mark
        of an empty block, and the net direction triangles.
        """
        o = self.obj
        r = QRectF(0, 0, *self._size())
        if getattr(self, 'ghost', False):
            # the Add Embedded Block preview, as the legacy tool draws it: the outline only
            p.setBrush(Qt.NoBrush); p.setPen(QPen(Qt.black, 0))
            p.drawRect(r)
            return
        # the yellow block (where nets attach): dark blue line 2 pixels wide at any zoom, as the
        # legacy tool draws it (a selected block keeps its colours and shows handles)
        line = QPen(EMB_LINE, 2); line.setCosmetic(True); line.setJoinStyle(Qt.MiterJoin)
        p.setBrush(EMB_FILL)
        p.setPen(line)
        p.drawRect(r)
        box = self.text_rect()
        if box is None or not box.contains(r.center()):
            # No view inside the block (none yet, or the Text view beside it): name and number
            # in the middle of the block, as the legacy tool shows a new embedded block.
            p.setFont(BOLD); p.setPen(Qt.black)
            p.drawText(r, Qt.AlignCenter, f'{o.name}\n{o.number}')
        elif o.show_name:
            # the legacy tool: name and number in bold in the top-left corner of the block, inside it
            # (250 units in, baselines 700 and 1800 units below the top)
            p.setFont(BOLD); p.setPen(Qt.black)
            p.drawText(QPointF(250 / 75, 700 / 75), o.name)
            p.drawText(QPointF(250 / 75, 1800 / 75), str(o.number))
        if box is not None:
            # the Text view: white box with the HDL code, clipped to the box
            p.setBrush(Qt.white); p.setPen(line)
            p.drawRect(box)
            if self.isSelected():
                # selected: the anchor (dashed red line from the block to its Text view, when the
                # view is outside the block) and the resize handle of the view
                if not r.intersects(box):
                    p.setPen(QPen(QColor(220, 0, 0), 0, Qt.DashLine))
                    p.drawLine(r.center(), box.center())
                hs = HANDLE_PX * _px(p) / 2
                p.setPen(Qt.NoPen); p.setBrush(Qt.black)
                p.drawRect(QRectF(box.right() - hs, box.bottom() - hs, 2 * hs, 2 * hs))
            # the code as the legacy tool writes it: 200 units in from the box, one line every 900
            # units, the first baseline 900 units below the top
            p.save()
            p.setClipRect(box)
            p.setFont(MONO); p.setPen(Qt.black)
            y = box.top() + TEXT_LINE
            for text in o.text.strip('\n').split('\n'):
                if y > box.bottom() + TEXT_LINE:
                    break
                p.drawText(QPointF(box.left() + 200 / 75, y), text)
                y += TEXT_LINE
            p.restore()
            if box.contains(r.center()):
                # the view icon (a text file) in the bottom-left corner of the block
                _text_file_icon(p, QRectF(250 / 75, r.height() - 1750 / 75, 1500 / 75, 1500 / 75))
        if box is None:
            # no view yet: a small page with a red "?" in the bottom-left corner, where the legacy tool
            # shows its "no view" icon (HDL Studio's own drawing, not the legacy bitmap)
            icon_r = QRectF(3, r.height() - 16, 10, 13)
            p.setBrush(Qt.white); p.setPen(QPen(QColor(90, 90, 90), 0))
            p.drawRect(icon_r)
            f = QFont(BOLD); f.setPointSizeF(7); p.setFont(f); p.setPen(QColor(220, 0, 0))
            p.drawText(icon_r, Qt.AlignCenter, '?')
        if self.isSelected():
            # black handles on the corners and the middle of the edges, as the legacy tool shows a
            # selected block
            hs = HANDLE_PX * _px(p) / 2
            p.setPen(Qt.NoPen); p.setBrush(Qt.black)
            w, h = r.width(), r.height()
            for x, y in ((0, 0), (w / 2, 0), (w, 0), (w, h / 2), (w, h), (w / 2, h), (0, h), (0, h / 2)):
                p.drawRect(QRectF(x - hs, y - hs, 2 * hs, 2 * hs))
        self._paint_net_arrows(p)

    def _paint_net_arrows(self, p: QPainter):
        """A black triangle where each net attaches, like a component port: its base on the
        block edge, pointing out for an output, in for an input. As in the legacy tool, the direction is
        the way the net was drawn: a net that starts on the block leaves it (output), a net
        that ends on it enters it (input). The legacy tool stores no ports for an embedded block."""
        t = PIN_HALF
        p.setPen(Qt.NoPen); p.setBrush(Qt.black)
        b = self.body()
        for w, which in self.bd_scene._attached(f'emb:{self.obj.id}'):
            if not w.points:
                continue
            x, y = w.points[0] if which == 'start' else w.points[-1]
            side = self.edge_side(x, y)
            # the point on the edge, in item coordinates, and the outward unit vector
            ex = (b.left() if side == 'left' else b.right() if side == 'right' else x) - self.obj.x
            ey = (b.top() if side == 'top' else b.bottom() if side == 'bottom' else y) - self.obj.y
            ox, oy = {'left': (-1, 0), 'right': (1, 0), 'top': (0, -1), 'bottom': (0, 1)}[side]
            # output: base on the edge, tip 2t outside; input: base 2t outside, tip on the edge
            base, tip = (0.0, 2 * t) if which == 'start' else (2 * t, 0.0)
            bx, by = ex + ox * base, ey + oy * base
            p.drawPolygon(QPolygonF([QPointF(bx - oy * t, by - ox * t), QPointF(ex + ox * tip, ey + oy * tip),
                                     QPointF(bx + oy * t, by + ox * t)]))


class _InlineText(QPlainTextEdit):
    """Multi-line in-place editor (HDL text of an embedded block). Leaving it keeps the text
    (committed), Esc drops the edit; either way it closes itself."""
    committed = Signal(str)

    def __init__(self, text: str, parent):
        """An editor box on `parent` holding `text`."""
        super().__init__(parent)
        self.setPlainText(text)
        self.setFont(QFont('Courier New', 9))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setStyleSheet('QPlainTextEdit { border: 1px solid #000080; background: white; }')
        self._done = False

    def _close(self, keep: bool):
        """Close the box once; with `keep`, emit the text."""
        if self._done:
            return
        self._done = True
        text = self.toPlainText()
        self.hide(); self.deleteLater()        # hidden at once, deleted by the event loop
        if keep:
            self.committed.emit(text)

    def keyPressEvent(self, e):
        """Esc drops the edit."""
        if e.key() == Qt.Key_Escape:
            self._close(False)
            return
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        """Leaving the box keeps the text."""
        super().focusOutEvent(e)
        self._close(True)


class EmbeddedViewDialog(QDialog):
    """"Create Embedded View" (as in the legacy tool): which view an empty embedded block gets. HDL Studio writes
    the HDL text itself, so only Text is offered; the graphical kinds are shown greyed."""

    def __init__(self, block_name: str, parent=None):
        """Build the dialog for the block called `block_name`."""
        super().__init__(parent)
        self.setWindowTitle('Create Embedded View')
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f'Create a new view for:     Embedded Block: {block_name}'))
        lay.addWidget(QLabel('Select type of view to create:'))
        from PySide6.QtWidgets import QRadioButton
        for k, text in enumerate(('Text', 'State Diagram', 'Flow Chart', 'ASM', 'Truth Table')):
            r = QRadioButton(text)
            r.setChecked(k == 0)
            r.setEnabled(k == 0)
            if k:
                r.setToolTip('Not supported: an embedded block is written as Verilog text')
            lay.addWidget(r)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class PortIoItem(_Movable):
    """A module port drawn on the diagram. Its point shows the signal flow (an input points toward
    its net, an output away from it, an inout both ways) and its name is written on the side away
    from the net; the net attaches at the end of the stub.
    """
    kind = 'pio'

    def boundingRect(self):
        """Room for the body, the stub and a name on either side."""
        return QRectF(-260, -9, 520, 18)

    def shape(self):
        """Clickable area: the body and stub."""
        p = QPainterPath()
        h = 0.375 * GRID
        p.addRect(QRectF(-PORT_EDGE, -h, 2 * PORT_EDGE, 2 * h))
        return p

    def paint(self, p: QPainter, opt, widget=None):
        """Draw the port (outline only for the Add preview), the stub, the selection handles and the
        name with its declaration text (Text Visibility settings).
        """
        o = self.obj
        ghost = getattr(self, 'ghost', False)
        if ghost:
            # the Add Port preview, as the legacy tool draws it: an outline (white inside), no name
            p.setBrush(Qt.white)
            p.setPen(QPen(Qt.black, 0))
        else:
            p.setBrush(QBrush(QColor(o.fg), _FILL[o.fill_style]) if o.fill_style in _FILL else Qt.NoBrush)
            p.setPen(Qt.NoPen if o.line_color == '#000000' and o.fill_style == 'solid'
                     else _pen(o.line_color, o.line_width, o.line_style))
        e, h = PORT_EDGE, 0.375 * GRID
        side = self.bd_scene.port_side(o)           # the net is on this side: the stub points to it
        # The body takes the half away from the net plus a quarter; the stub the rest. As in the legacy tool
        # the point shows the signal flow: an input points towards its net (into the diagram),
        # an output away from it, an inout both ways.
        lo, hi = sorted((-e * side, e / 2 * side))
        if o.mode == 'inout':
            shape = [QPointF(lo, 0), QPointF(lo + h, -h), QPointF(hi - h, -h), QPointF(hi, 0),
                     QPointF(hi - h, h), QPointF(lo + h, h)]
        elif (side if o.mode == 'input' else -side) > 0:
            shape = [QPointF(lo, -h), QPointF(hi - h, -h), QPointF(hi, 0), QPointF(hi - h, h), QPointF(lo, h)]
        else:
            shape = [QPointF(hi, -h), QPointF(lo + h, -h), QPointF(lo, 0), QPointF(lo + h, h), QPointF(hi, h)]
        p.drawPolygon(QPolygonF(shape))
        stub = QPen(QColor(o.line_color), 1)
        stub.setCosmetic(True)
        p.setPen(stub)
        p.drawLine(QPointF(e / 2 * side, 0), QPointF(e * side, 0))
        if self.isSelected():
            # as the legacy tool: a selected port keeps its colour and gets small handles at its corners
            box = QPolygonF(shape).boundingRect()
            p.setPen(Qt.NoPen); p.setBrush(Qt.black)
            r = HANDLE_PX * _px(p) / 2
            for c in (box.topLeft(), box.topRight(), box.bottomLeft(), box.bottomRight()):
                p.drawRect(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r))
        if ghost:
            return
        sig = next((s for s in self.bd_scene.bd.signals if s.name == o.name), None)
        text = port_label(o.name, sig.type if sig else 'wire', bool(sig and sig.signed), sig.bounds if sig else '',
                          sig.delay if sig else '', dict(text_name=o.show_text, text_type=o.text_type,
                                                         text_type_name=o.text_type_name,
                                                         text_signed=o.text_signed, text_value=o.text_value))
        if not text:
            return
        p.setPen(Qt.black)
        p.setFont(MONO)
        w = p.fontMetrics().horizontalAdvance(text)
        # the name goes on the side away from the net
        if self.bd_scene.port_side(o) > 0:
            p.drawText(QPointF(-e - 3 - w, 3), text)
        else:
            p.drawText(QPointF(e + 3, 3), text)


class WireItem(QGraphicsPathItem):
    """One net segment chain. As in the legacy editor: drag moves the net (ends
    attached to pins/ports stay and the route stretches), Alt+drag moves only
    the segment under the cursor, and the square handles of a selected net move
    its route points. Double-click edits the net name in place."""

    def __init__(self, scene: 'BdScene', w: BdWire):
        """The item of wire `w`; no drag in progress."""
        super().__init__()
        self.bd_scene = scene
        self.obj = w
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setZValue(1)
        self._drag = None           # (kind, index, original points, press position)
        self._end_origin = None     # port under a dragged net end: (pin or None, x, y, side)
        self._net_ends = None       # component ports of a dragged net, with their start positions
        self._pio_start: dict[str, tuple[float, float]] = {}
        self.refresh()

    def refresh(self):
        """Rebuild the path from the wire's points (and repaint an embedded block at its ends, which
        draws the net's direction triangle).
        """
        self.prepareGeometryChange()
        path = QPainterPath()
        pts = self.obj.points
        if pts:
            path.moveTo(*pts[0])
            for x, y in pts[1:]:
                path.lineTo(x, y)
        self.setPath(path)
        self.setToolTip(self.obj.text)
        # an embedded block draws the direction triangle at this net's end: repaint it too
        for ref in (self.obj.start, self.obj.end):
            if ref.startswith('emb:') and self.scene() is not None:
                owner = self.bd_scene.owner_of(ref)
                if owner is not None:
                    owner.update()

    def label_rect(self) -> QRectF:
        """Box of the net name as drawn (empty when hidden). Horizontal names sit on their
        baseline; vertical ones (legacy "ro 270") read upward from it, glyphs left of it."""
        if not self.obj.show_text or not self.obj.points:
            return QRectF()
        fm = QFontMetricsF(MONO)
        width = fm.horizontalAdvance(self.obj.text)
        pos = self.label_pos(width)
        if self.is_label_vertical():
            return QRectF(pos.x() - fm.ascent(), pos.y() - width, fm.height(), width)
        return QRectF(pos.x(), pos.y() - fm.ascent(), width, fm.height())

    def shape(self):
        """Clickable area: an 8 unit band along the net plus its name."""
        # clickable: an 8-unit band along the net, plus its name, so a double-click on the
        # name edits the net (winding fill: where the two overlap must not become a hole)
        s = QPainterPathStroker()
        s.setWidth(8)
        path = s.createStroke(self.path())
        path.setFillRule(Qt.WindingFill)
        path.addRect(self.label_rect())
        return path

    def boundingRect(self):
        """The path, the handles and the name."""
        m = max(10.0, HANDLE_PX * _scene_px(self.scene()))
        return super().boundingRect().adjusted(-120, -m, 120, m).united(self.label_rect())

    def paint(self, p: QPainter, opt, widget=None):
        """Draw the net (bus thicker, highlighted net in magenta), the red connectors of dangling ends,
        the name (vertical names read upward), the box of a name selected on its own and the
        handles of a selected net.
        """
        bus = self.bd_scene.is_bus(self.obj.net)
        if self.bd_scene.highlight and self.obj.net == self.bd_scene.highlight:
            pen = QPen(QColor(255, 0, 200), 3)
        elif self.isSelected():
            pen = QPen(Qt.black, 2 if bus else 1)         # a selected net shows its handles, as in the legacy tool
        else:
            pen = QPen(Qt.black, 2 if bus else 1)
        pen.setCosmetic(True)                   # widths in screen pixels, like the legacy editor
        p.setPen(pen)
        p.save()
        p.setRenderHint(QPainter.Antialiasing, False)   # sharp 1 / 2 pixel lines, not smoothed, as the legacy editor
        p.drawPath(self.path())
        p.restore()
        pts = self.obj.points
        if not pts:
            return
        p.setFont(MONO)
        for end, ref in ((pts[0], self.obj.start), (pts[-1], self.obj.end)):
            if not ref:
                # dangling end: net connector
                p.setPen(QPen(QColor(220, 0, 0), 1))
                p.setBrush(Qt.white)
                p.drawEllipse(QPointF(*end), 3, 3)
        if self.obj.show_text:
            p.setPen(Qt.black)
            pos = self.label_pos(p.fontMetrics().horizontalAdvance(self.obj.text))
            if self.is_label_vertical():
                p.save()                        # reads upward from the baseline origin, as the legacy editor
                p.translate(pos); p.rotate(-90)
                p.drawText(QPointF(0, 0), self.obj.text)
                p.restore()
            else:
                p.drawText(pos, self.obj.text)

        if self.bd_scene.selected_label == self.obj.id and self.obj.show_text:
            # As in the legacy tool, the name selected on its own (a click on the name, not on the
            # net) gets a box with corner handles and a red leader to the start of the net,
            # the point its position is kept relative to. A selected net shows no box.
            box = self.label_rect()
            if not box.isEmpty():
                p.setPen(QPen(QColor(0, 0, 0), 0)); p.setBrush(Qt.NoBrush)
                p.drawRect(box)
                p.setPen(Qt.NoPen); p.setBrush(Qt.black)
                r = HANDLE_PX * _px(p) / 4
                for c in (box.topLeft(), box.topRight(), box.bottomLeft(), box.bottomRight()):
                    p.drawRect(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r))
                p.setPen(QPen(QColor(220, 0, 0), 0))
                p.drawLine(box.bottomLeft(), QPointF(*pts[0]))
        if self.isSelected():
            # route point handles (black squares, as in the legacy editor)
            p.setPen(Qt.NoPen)
            p.setBrush(Qt.black)
            r = HANDLE_PX * _px(p) / 2
            for x, y in pts:
                p.drawRect(QRectF(x - r, y - r, 2 * r, 2 * r))

    def itemChange(self, change, value):
        """A selected net is raised above the objects so its handles take the clicks."""
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.setZValue(6 if value else 1)   # a selected net's handles win over objects under them
        return super().itemChange(change, value)

    def _midway(self) -> tuple[list[float], list[float], float]:
        """The segment holding the point half way along the net, and that point's distance
        from the segment's first point."""
        pts = self.obj.points
        if len(pts) < 2:
            return pts[0], pts[0], 0.0
        lengths = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(pts, pts[1:])]
        half = sum(lengths) / 2
        for (a, b), n in zip(zip(pts, pts[1:]), lengths):
            if half <= n:
                return a, b, half
            half -= n
        return pts[-2], pts[-1], lengths[-1]

    def is_label_vertical(self) -> bool:
        """The name runs upward along a vertical segment: as stored for a placed name (legacy
        "ro 270"), else when the middle segment of the net is vertical (the legacy tool aligns the name
        with the net)."""
        if self.obj.label is not None:
            return self.obj.label_vertical
        a, b, _ = self._midway()
        return abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) > 0.01

    def label_pos(self, text_w: float) -> QPointF:
        """Baseline origin of the net name: the stored offset from the first point, else, as
        The legacy tool places a new net's name, centred half way along the net, just above a horizontal
        segment or just left of a vertical one (reading upward)."""
        pts = self.obj.points
        if self.obj.label is not None:
            return QPointF(pts[0][0] + self.obj.label[0], pts[0][1] + self.obj.label[1])
        a, b, d = self._midway()
        if abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) > 0.01:          # vertical
            y = a[1] + (d if b[1] > a[1] else -d)
            return QPointF(a[0] - 3, y + text_w / 2)
        x = a[0] + (d if b[0] >= a[0] else -d)
        return QPointF(x - text_w / 2, a[1] - 3)

    # dragging --------------------------------------------------------------------
    def _handle_at(self, pos: QPointF) -> int | None:
        """Index of the route point handle under `pos` (only on a selected net), or None."""
        if not self.isSelected():
            return None
        tol = (HANDLE_PX / 2 + 2) * _scene_px(self.scene())
        for k, (x, y) in enumerate(self.obj.points):
            if abs(x - pos.x()) <= tol and abs(y - pos.y()) <= tol:
                return k
        return None

    def _segment_at(self, pos: QPointF) -> int:
        """Index of the segment nearest `pos` (segment k joins points k and k + 1)."""
        best, idx = 1e9, 0
        for k, (a, b) in enumerate(zip(self.obj.points, self.obj.points[1:])):
            d = QLineF(QPointF(*a), QPointF(*b))
            if d.length() < 1e-6:
                continue
            t = max(0.0, min(1.0, QPointF.dotProduct(pos - d.p1(), d.p2() - d.p1()) / d.length() ** 2))
            dist = QLineF(pos, d.pointAt(t)).length()
            if dist < best:
                best, idx = dist, k
        return idx

    def mousePressEvent(self, e):
        """Start a drag: on the name (away from the line) it moves the name only; on a handle it moves
        that route point (or what an attached end is on); with Alt the segment under the cursor;
        otherwise the whole net.
        """
        super().mousePressEvent(e)
        if e.button() != Qt.LeftButton or self.bd_scene.readonly or self.bd_scene.mode != 'select' \
                or e.modifiers() & Qt.ControlModifier or len(self.obj.points) < 2:
            return
        pos = e.scenePos()
        k = self._handle_at(pos)
        # The name sits just above the net, so its box overlaps the line: a press on the line
        # itself is for the net, only a press on the name away from the line drags the name.
        on_line = any(QLineF(QPointF(*a), QPointF(*b)).length() > 1e-6 and
                      _dist_to_segment(pos, QPointF(*a), QPointF(*b)) <= 2.5
                      for a, b in zip(self.obj.points, self.obj.points[1:]))
        if k is None and not on_line and self.label_rect().contains(pos):
            # a press on the net name drags the name only (stored relative to the first point;
            # a name never placed starts from where it is drawn now)
            lp = self.label_pos(QFontMetricsF(MONO).horizontalAdvance(self.obj.text))
            first = self.obj.points[0]
            self.obj.label_vertical = self.is_label_vertical()    # keep the orientation it is drawn with
            self._drag = ('label', None, [lp.x() - first[0], lp.y() - first[1]], pos)
            # as the legacy tool, the name is selected on its own: the net itself is not
            self.bd_scene.clearSelection()
            self.bd_scene.select_label(self.obj.id)
            return
        if k is not None:
            kind = 'point'
        elif e.modifiers() & Qt.AltModifier:
            kind, k = 'segment', self._segment_at(pos)
        else:
            kind = 'net'
        self._drag = (kind, k, [list(q) for q in self.obj.points], pos)

    def mouseMoveEvent(self, e):
        """Apply the drag (grid steps; Shift: one axis). A whole net moves through its component
        ports when it has some (they slide along their components); otherwise it moves itself and
        carries its PortIOs, while ends on an embedded block slide along the block edge.
        """
        if self._drag is None:
            return super().mouseMoveEvent(e)
        kind, k, orig, start = self._drag
        dx, dy = _snap(e.scenePos().x() - start.x()), _snap(e.scenePos().y() - start.y())
        if e.modifiers() & Qt.ShiftModifier:       # constrain to horizontal or vertical
            dx, dy = (dx, 0.0) if abs(dx) >= abs(dy) else (0.0, dy)
        w = self.obj
        if kind == 'label':                         # orig is the name offset at the press
            self.prepareGeometryChange()
            w.label = [orig[0] + dx, orig[1] + dy]
            self.update()
            return
        if kind == 'point':
            pts = [list(q) for q in orig]
            ref = w.start if k == 0 else w.end if k == len(pts) - 1 else ''
            if ref:
                self._move_attached_end(ref, k, dx, dy, orig)
                return
            pts[k] = [_snap(orig[k][0] + dx), _snap(orig[k][1] + dy)]
            w.points = pts
        elif kind == 'segment':
            w.points = _move_segment(orig, k, dx, dy, bool(w.start), bool(w.end))
        else:
            ends = self._component_ends() if self._net_ends is None else self._net_ends
            self._net_ends = ends
            if ends:
                # the net is moved through the component ports it is on, as when moving those ports
                for owner, pin, x0, y0, side0 in ends:
                    self.bd_scene.move_pin(owner, pin, *owner.pin_target(pin, x0, y0, side0, dx, dy), carry=True)
            else:
                # No component port on the net: the whole net moves by (dx, dy). What is at
                # each end decides what happens there:
                #   PortIO              - carried along (it belongs to this net only);
                #   embedded block      - stays put: the end slides along the block's edge, as on
                #                         a component port (moving the block would pull the
                #                         other nets of the block off their places);
                #   nothing (connector) - just moves with the net.
                w.points = [[x + dx, y + dy] for x, y in orig]
                for which, ref in (('start', w.start), ('end', w.end)):
                    owner = self.bd_scene.owner_of(ref) if ref else None
                    if isinstance(owner, EmbeddedItem):
                        x0, y0 = orig[0] if which == 'start' else orig[-1]
                        x, y, side = owner.edge_target(x0, y0, owner.edge_side(x0, y0), dx, dy)
                        _leave_edge(w, which, BdPin('', x=x, y=y, side=side))
                    elif owner is not None:
                        ox, oy = self._pio_origin(owner)
                        self.bd_scene.following = True
                        try:
                            owner.setPos(QPointF(ox + dx, oy + dy))
                        finally:
                            self.bd_scene.following = False
        self.refresh()

    def _move_attached_end(self, ref: str, k: int, dx: float, dy: float, orig: list[list[float]]):
        """Dragging the end handle of a net that is attached to something:
          component port - moves that port along the component edge (its nets follow);
          embedded block - slides the net end along the block edge; the block stays;
          PortIO         - moves the PortIO (its nets follow).
        orig is the net's points at the press: the end is re-routed from them on every move,
        so repeated moves do not pile up route stubs."""
        sc = self.bd_scene
        owner = sc.owner_of(ref)
        if owner is None:
            return
        if isinstance(owner, EmbeddedItem):
            which = 'start' if k == 0 else 'end'
            x0, y0 = orig[k]
            x, y, side = owner.edge_target(x0, y0, owner.edge_side(x0, y0), dx, dy)
            self.obj.points = [list(q) for q in orig]
            _leave_edge(self.obj, which, BdPin('', x=x, y=y, side=side))
            self.refresh()
            return
        if self._end_origin is None:
            pin = next((q for q in owner.obj.pins if f'pin:{owner.obj.id}:{q.name}' == ref), None) \
                if isinstance(owner, InstanceItem) else None
            self._end_origin = (pin, pin.x, pin.y, pin.side) if pin is not None else \
                (None, owner.obj.x, owner.obj.y, '')
        pin, x0, y0, side0 = self._end_origin
        if pin is not None:
            sc.move_pin(owner, pin, *owner.pin_target(pin, x0, y0, side0, dx, dy))
        else:
            owner.setPos(QPointF(x0 + dx, y0 + dy))     # a PortIO: its nets follow it

    def _component_ends(self) -> list[tuple['InstanceItem', BdPin, float, float, str]]:
        """The component ports at the ends of the net, with their positions at the press."""
        sc, out = self.bd_scene, []
        for ref in (self.obj.start, self.obj.end):
            owner = sc.owner_of(ref) if ref.startswith('pin:') else None
            pin = next((q for q in owner.obj.pins if f'pin:{owner.obj.id}:{q.name}' == ref), None) if owner else None
            if pin is not None:
                out.append((owner, pin, pin.x, pin.y, pin.side))
        return out

    def _pio_origin(self, owner) -> tuple[float, float]:
        """Position of a PortIO at the start of the drag (remembered the first time it is asked)."""
        return self._pio_start.setdefault(owner.obj.id, (owner.obj.x, owner.obj.y))

    def mouseReleaseEvent(self, e):
        """End of a drag: tidy the points; a dragged end may connect where it was dropped; one undo step."""
        drag, self._drag = self._drag, None
        self._end_origin = None
        self._net_ends = None
        self._pio_start = {}
        super().mouseReleaseEvent(e)
        if drag is not None and drag[0] == 'label':
            if self.obj.label != drag[2]:
                self.bd_scene.changed_model.emit()
            return
        if drag is None or self.obj.points == drag[2]:
            return
        self.obj.points = _simplify(self.obj.points)
        self.refresh()
        if drag[0] == 'point':
            self.bd_scene.end_dropped.emit(self.obj)
        self.bd_scene.changed_model.emit()



# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------
class BdScene(QGraphicsScene):
    """The editing scene of one BlockDiagram (see the module docstring). Signals tell the window
    what to do next (rename / edit a net, a port or net end dropped, a component dropped from the
    Component Browser, a popup menu, ...); `changed_model` follows every model change.
    """
    changed_model = Signal()
    message = Signal(str)
    rename_net_requested = Signal(str)
    edit_net_requested = Signal(str, QPointF)      # in-place edit of a net name at a scene position
    port_dropped = Signal(object)                  # a port was moved (may land on a net end)
    frame_edit_requested = Signal(object)          # double-click on a frame title
    component_dropped = Signal(str, str, QPointF)  # library, unit, drop point (Component Browser)
    end_dropped = Signal(object)                   # a dangling net end was moved (may land on a pin/port)
    place_requested = Signal(QPointF)
    comment_edit_requested = Signal(object)      # a free comment text (BdComment) double-clicked
    context_requested = Signal(object, object, QPointF)     # item (or None), screen pos, scene pos

    def __init__(self, parent=None):
        """An empty scene; load() fills it. The attributes below hold the editing state (selected
        port / name line / net name, add preview, interactive routing, the net being drawn).
        """
        super().__init__(parent)
        self.setBackgroundBrush(QColor(255, 255, 255))      # legacy canvas: pure white
        self.bd = BlockDiagram()
        self.highlight = ''          # net drawn highlighted
        self.following = False       # True while objects are carried along by a move
        self.group: set = set()      # objects moved together with a frame
        # (instance id, port) of the component ports selected on their own (Ctrl+click adds / removes one)
        self.selected_pins: list[tuple[str, str]] = []
        # (instance id, 'library' | 'unit' | 'instance'): one name line of a component, selected on its own
        self.selected_text: tuple[str, str] | None = None
        self.selected_label: str | None = None      # wire id whose name is selected on its own
        self._ghost: tuple[str, QGraphicsItem] | None = None    # placement preview (kind, item)
        self.ghost_instance: BdInstance | None = None   # the component being added, for its preview
        self.route_mode = ROUTE_MODES[0]     # routing of the nets of a dragged PortIO ('z' changes it)
        self._routing: dict[str, tuple[BdWire, str, BdPortIo]] = {}
        self._hint = None
        self.readonly = False
        self.panels_locked = False                   # Diagram > Panels > Protect All Panels
        self.mode = 'select'
        self.items_by_id: dict[str, _Movable] = {}
        self.wire_items: dict[str, WireItem] = {}
        self._wire_start: tuple[str, QPointF] | None = None
        self._wire_pts: list[list[float]] = []
        self._rubber: QGraphicsPathItem | None = None

    # building ------------------------------------------------------------------
    def load(self, bd: BlockDiagram):
        """Rebuild every item from diagram `bd` (nets first, so objects are drawn over them), then make
        the net ends touch their ports exactly.
        """
        self._ghost = None                      # clear() below deletes the preview item too
        self.clear()
        self._hint = None
        self._routing = {}
        self._rubber = None
        self.bd = bd
        self.items_by_id.clear()
        self.wire_items.clear()
        for w in bd.wires:
            self._add_wire(w)
        for inst in bd.instances:
            self._add(InstanceItem(self, inst))
        for eb in bd.embedded:
            self._add(EmbeddedItem(self, eb))
        for pio in bd.port_ios:
            self._add(PortIoItem(self, pio))
        for fr in bd.frames:
            self._add(FrameItem(self, fr))
        for c in bd.comments:
            self._add(CommentItem(self, c))
        for j in bd.junctions:
            self._add(JunctionItem(self, j))
        for tb in bd.text_blocks:
            if tb.visible:
                self._add(TextBlockItem(self, tb))
        for pn in bd.panels:
            self.addItem(PanelItem(pn, self.changed_model.emit, lambda q: QPointF(_snap(q.x()), _snap(q.y())),
                                   lambda: self.readonly or self.panels_locked))
        self._attach_port_ends()
        self.setSceneRect(self.itemsBoundingRect().adjusted(-600, -600, 600, 600))

    def _add(self, item: _Movable):
        """Add an object item and index it by its model id."""
        self.addItem(item)
        self.items_by_id[item.obj.id] = item

    def _add_wire(self, w: BdWire):
        """Add the item of a wire and index it by wire id."""
        it = WireItem(self, w)
        self.addItem(it)
        self.wire_items[w.id] = it

    def is_bus(self, net: str) -> bool:
        """Drawn as a bus (thick): as set by Change Style, else when the net has bounds."""
        style = self.bd.net_styles.get(net)
        if style:
            return style == 'bus'
        return any(s.name == net and s.bounds for s in self.bd.signals)

    # geometry helpers ------------------------------------------------------------
    def _ref_of(self, item: _Movable) -> str:
        """The attachment prefix of an object: "pin:<inst id>" (followed by ":<pin>"), "pio:<id>", ..."""
        # wires reference instance pins as "pin:<instance id>:<pin>"
        return f'{"pin" if item.kind == "inst" else item.kind}:{item.obj.id}'

    def _attached(self, ref_prefix: str):
        """Yield (wire, 'start' | 'end') for every wire end attached to `ref_prefix` (an exact
        reference, or a prefix followed by ':' such as all pins of one instance).
        """
        for w in self.bd.wires:
            for which in ('start', 'end'):
                r = getattr(w, which)
                if r == ref_prefix or r.startswith(ref_prefix + ':'):
                    yield w, which

    # ports ---------------------------------------------------------------------
    def port_side(self, pio: BdPortIo) -> int:
        """+1 when the port's net leaves to the right, -1 to the left (no net: by mode)."""
        for w, which in self._attached(f'pio:{pio.id}'):
            pts = w.points
            if len(pts) > 1:
                nxt = pts[1] if which == 'start' else pts[-2]
                if abs(nxt[0] - pio.x) > 0.01:
                    return 1 if nxt[0] > pio.x else -1
        return 1 if pio.mode == 'input' else -1

    def port_edge(self, pio: BdPortIo, side: int | None = None) -> list[float]:
        """The point where a PortIO's net attaches: the end of its stub, on side `side` (+1 right,
        -1 left; default: the side of its net).
        """
        side = self.port_side(pio) if side is None else side
        return [pio.x + side * PORT_EDGE, pio.y]

    def _attach_port_ends(self):
        """Net ends attached to a port touch the port icon, and those on a component port
        touch the port (legacy diagrams leave a small gap). Done once, when the diagram is loaded."""
        for inst in self.bd.instances:
            for pin in inst.pins:
                for w, which in list(self._attached(f'pin:{inst.id}:{pin.name}')):
                    end = w.points[0] if which == 'start' else w.points[-1]
                    tip = pin_end(pin)
                    dx, dy = tip[0] - end[0], tip[1] - end[1]
                    if (abs(dx) > 0.01 or abs(dy) > 0.01) and abs(dx) + abs(dy) <= 3 * GRID:
                        _shift_end(w, which, dx, dy)
                        w.points = _simplify(w.points)
                        if which == 'start' and w.label is not None:
                            w.label = [w.label[0] - dx, w.label[1] - dy]
                        if w.id in self.wire_items:
                            self.wire_items[w.id].refresh()
        for pio in self.bd.port_ios:
            edge = self.port_edge(pio)
            for w, which in list(self._attached(f'pio:{pio.id}')):
                end = w.points[0] if which == 'start' else w.points[-1]
                dx, dy = edge[0] - end[0], edge[1] - end[1]
                if abs(dx) > 0.01 or abs(dy) > 0.01:
                    _shift_end(w, which, dx, dy)
                    w.points = _simplify(w.points)
                    if which == 'start' and w.label is not None:
                        w.label = [w.label[0] - dx, w.label[1] - dy]
                    if w.id in self.wire_items:
                        self.wire_items[w.id].refresh()

    def _carry(self, item: _Movable, dx: float, dy: float, skip: BdWire):
        """Move an object along with another; its other nets stretch."""
        self.following = True
        try:
            item.setPos(item.pos() + QPointF(dx, dy))
        finally:
            self.following = False
        for w, which in list(self._attached(self._ref_of(item))):
            if w is not skip:
                _shift_end(w, which, dx, dy)
                if w.id in self.wire_items:
                    self.wire_items[w.id].refresh()

    def _move_frame_contents(self, frame: 'FrameItem', dx: float, dy: float):
        """Objects (and free nets) that were inside the frame move with it."""
        o = frame.obj
        old = QRectF(o.x - dx, o.y - dy, o.w, o.h)
        inside = [it for it in self.items_by_id.values() if it is not frame and not it.isSelected()
                  and old.contains(QPointF(it.obj.x + getattr(it.obj, 'w', 0) / 2,
                                           it.obj.y + getattr(it.obj, 'h', 0) / 2))]
        free = [w for w in self.bd.wires if not w.start and not w.end
                and all(old.contains(QPointF(*q)) for q in w.points)]
        self.group = set(inside) | {frame}
        try:
            for it in inside:
                it.setPos(it.pos() + QPointF(dx, dy))
        finally:
            self.group = set()
        for w in free:
            w.points = [[x + dx, y + dy] for x, y in w.points]
            if w.id in self.wire_items:
                self.wire_items[w.id].refresh()

    def select_label(self, wire_id: str | None):
        """Select the name of one net on its own (or none), as the legacy tool does on a click on the name."""
        old, self.selected_label = self.selected_label, wire_id
        for wid in {old, wire_id} - {None}:
            if wid in self.wire_items:
                self.wire_items[wid].update()

    def select_text(self, item: 'InstanceItem | None', kind: str = ''):
        """Select one name line of a component (or none). As in the legacy tool, the line is selected on
        its own: the component body is not selected, so Delete does not remove the component."""
        old = self.selected_text
        self.selected_text = (item.obj.id, kind) if item is not None and kind else None
        # repaint the component that lost the selection and the one that got it
        for iid in {old[0] if old else None, self.selected_text[0] if self.selected_text else None} - {None}:
            if iid in self.items_by_id:
                self.items_by_id[iid].update()

    @property
    def selected_pin(self) -> tuple[str, str] | None:
        """The component port selected last (instance id, port), or None."""
        return self.selected_pins[-1] if self.selected_pins else None

    def select_pin(self, item: 'InstanceItem | None', pin: BdPin | None, toggle: bool = False):
        """Select one component port on its own (or none) and repaint the components concerned. With
        `toggle` (Ctrl+click, as in the legacy tool) the port is added to the ports already selected,
        or taken out of them when it is one of them."""
        old = list(self.selected_pins)
        key = (item.obj.id, pin.name) if item is not None and pin is not None else None
        if toggle and key is not None:
            if key in self.selected_pins:
                self.selected_pins.remove(key)
            else:
                self.selected_pins.append(key)
        else:
            self.selected_pins = [key] if key is not None else []
        for iid in {k[0] for k in old + self.selected_pins}:
            if iid in self.items_by_id:
                self.items_by_id[iid].update()

    def pins_selected(self) -> list[tuple[BdInstance, BdPin]]:
        """The selected component ports, as (instance, port)."""
        out = []
        for iid, name in self.selected_pins:
            it = self.items_by_id.get(iid)
            pin = next((q for q in it.obj.pins if q.name == name), None) if it is not None else None
            if pin is not None:
                out.append((it.obj, pin))
        return out

    def move_pin(self, item: 'InstanceItem', pin: BdPin, x: float, y: float, side: str | None = None,
                 carry: bool = False):
        """Put a component port at (x, y) on an edge of the body.
        Moving the port itself (carry=False) moves only the port: its nets stretch, keeping right
        angles, and leave a new edge straight out. Moving a net (carry=True) takes the PortIO or
        dangling connector at its other end along; nets to another component still stretch."""
        side = side or pin.side
        if (x, y, side) == (pin.x, pin.y, pin.side):
            return
        if any(q is not pin and abs(q.x - x) < 0.01 and abs(q.y - y) < 0.01 for q in item.obj.pins):
            return                              # another port is already there
        dx, dy = x - pin.x, y - pin.y
        turned = side != pin.side
        pin.x, pin.y, pin.side = x, y, side
        for w, which in list(self._attached(f'pin:{item.obj.id}:{pin.name}')):
            other = w.end if which == 'start' else w.start
            owner = self.owner_of(other)
            free = not other or (owner is not None and owner.kind == 'pio')
            if carry and free and turned:
                self._turn_net(w, which, pin, owner)
            elif carry and free:
                w.points = [[px + dx, py + dy] for px, py in w.points]
                if owner is not None:
                    self._carry(owner, dx, dy, w)
            else:
                self._route_from_pin(w, which, item.obj, pin)
            if w.id in self.wire_items:
                self.wire_items[w.id].refresh()
        item.prepareGeometryChange()
        item.update()

    def _route_from_pin(self, w: BdWire, which: str, inst: BdInstance, pin: BdPin):
        """Lay a net out from a component port: straight out of the edge (behind the arrow),
        right angles, round the component when the other end is behind it, into the other end
        from behind. Constant work per call, so dragging stays light."""
        far_ref = w.end if which == 'start' else w.start
        far = w.points[-1] if which == 'start' else w.points[0]
        owner = self.owner_of(far_ref) if far_ref else None
        db = None
        if isinstance(owner, InstanceItem):
            fp = next((q for q in owner.obj.pins if f'pin:{owner.obj.id}:{q.name}' == far_ref), None)
            if fp is not None:
                far, db = pin_end(fp), _OUT[fp.side]
        elif isinstance(owner, PortIoItem):
            side = 1 if pin.x >= owner.obj.x else -1
            far, db = [owner.obj.x + side * PORT_EDGE, owner.obj.y], (side, 0)
        route = _pin_route(pin_end(pin), _OUT[pin.side], far, db,
                           QRectF(inst.x, inst.y, inst.w, inst.h))
        w.points = route if which == 'start' else list(reversed(route))

    def _turn_net(self, w: BdWire, which: str, pin: BdPin, owner: '_Movable | None'):
        """A port moved to another edge: its net to a PortIO or connector is laid straight out of
        the new edge, as long as it was, with the PortIO at its end."""
        a, b = w.points[0], w.points[-1]
        length = max(abs(a[0] - b[0]) + abs(a[1] - b[1]), 4 * GRID)
        out = {'left': (-1, 0), 'right': (1, 0), 'top': (0, -1), 'bottom': (0, 1)}[pin.side]
        tip = pin_end(pin)
        end = [tip[0] + out[0] * length, tip[1] + out[1] * length]
        pts = [tip, end]
        w.points = pts if which == 'start' else list(reversed(pts))
        if owner is not None:                   # the PortIO touches the net end with its edge
            side = -1 if out[0] > 0 or out[0] == 0 else 1
            target = QPointF(end[0] - side * PORT_EDGE, end[1])
            d = target - owner.pos()
            self._carry(owner, d.x(), d.y(), w)

    # interactive routing while a PortIO is dragged --------------------------------------
    def _route_pio_net(self, w: BdWire, which: str, pio: BdPortIo, dx: float, dy: float):
        """A PortIO is being dragged: its net keeps its route and stretches (River mode) or is routed
        again in the current routing mode; the 'z' hint is shown.
        """
        self._routing[w.id] = (w, which, pio)
        if self.route_mode == 'River':
            _shift_end(w, which, dx, dy)        # keep the route, stretch it (loops allowed)
        else:
            self._reroute(w, which, pio)
        self._show_hint(pio)

    def _reroute(self, w: BdWire, which: str, pio: BdPortIo):
        """Route a PortIO's net again from its fixed end to the port, in the current routing mode,
        around the components.
        """
        fixed = w.points[-1] if which == 'start' else w.points[0]
        fixed_ref = w.end if which == 'start' else w.start
        side = 1 if fixed[0] >= pio.x else -1
        moving = [pio.x + side * PORT_EDGE, pio.y]
        route = route_net(self.route_mode, fixed, self._exit_dir(fixed_ref, fixed, moving), moving, (side, 0),
                          self._obstacles(fixed_ref, pio))
        w.points = list(reversed(route)) if which == 'start' else route

    def _exit_dir(self, ref: str, at: list[float], toward: list[float]) -> tuple[int, int]:
        """Direction a net leaves its fixed end: out of a component edge, else toward the other end."""
        owner = self.owner_of(ref) if ref else None
        if isinstance(owner, InstanceItem):
            pin = next((q for q in owner.obj.pins if f'pin:{owner.obj.id}:{q.name}' == ref), None)
            if pin is not None:
                return {'left': (-1, 0), 'right': (1, 0), 'top': (0, -1), 'bottom': (0, 1)}[pin.side]
        if abs(toward[0] - at[0]) >= abs(toward[1] - at[1]):
            return (1 if toward[0] >= at[0] else -1, 0)
        return (0, 1 if toward[1] >= at[1] else -1)

    def _obstacles(self, fixed_ref: str, pio: BdPortIo) -> list[QRectF]:
        """Rectangles the router must go around: components, embedded blocks, the other PortIOs."""
        out = []
        for it in self.items_by_id.values():
            o = it.obj
            if isinstance(it, (InstanceItem, EmbeddedItem)):
                out.append(QRectF(o.x, o.y, o.w, o.h))
            elif isinstance(it, PortIoItem) and o is not pio:
                out.append(QRectF(o.x - PORT_EDGE, o.y - 5, 2 * PORT_EDGE, 10))
        return out

    def cycle_route_mode(self) -> bool:
        """'z' while dragging a PortIO: next routing mode, applied at once."""
        if not self._routing:
            return False
        self.route_mode = ROUTE_MODES[(ROUTE_MODES.index(self.route_mode) + 1) % len(ROUTE_MODES)]
        for w, which, pio in self._routing.values():
            if self.route_mode != 'River':
                self._reroute(w, which, pio)
            if w.id in self.wire_items:
                self.wire_items[w.id].refresh()
        self._show_hint(next(iter(self._routing.values()))[2])
        return True

    def _show_hint(self, pio: BdPortIo):
        """Show the legacy tool's "Press 'z' to change routing" hint next to the dragged port."""
        if self._hint is None:
            self._hint = QGraphicsSimpleTextItem()
            self._hint.setBrush(QColor(220, 0, 0))
            self._hint.setFont(QFont('Courier New', 7, QFont.Bold))
            self._hint.setZValue(100)
            self._hint.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            self.addItem(self._hint)
        # the legacy wording (strings.vrf: tempInteractiveRoutingString)
        self._hint.setText(f"Press 'z' to change routing\nCurrent mode: {self.route_mode}")
        self._hint.setPos(pio.x + 40, pio.y + 15)
        self._hint.show()

    def end_routing(self):
        """End of a PortIO drag: tidy the routed nets and hide the hint."""
        for w, _, _ in self._routing.values():
            w.points = _simplify(w.points)
            if w.id in self.wire_items:
                self.wire_items[w.id].refresh()
        self._routing = {}
        if self._hint is not None:
            self._hint.hide()

    def owner_of(self, ref: str) -> _Movable | None:
        """Item a wire end is attached to ("pin:<inst>:<pin>", "pio:<id>", "emb:<id>")."""
        parts = ref.split(':')
        return self.items_by_id.get(parts[1]) if len(parts) > 1 else None

    def object_moved(self, item: _Movable, dx: float, dy: float):
        """Everything attached moves with the object (nets, net connectors and
        the ports at their other end), except nets whose other end is on another
        component or embedded block that stays: those stretch, keeping right angles."""
        if isinstance(item, InstanceItem):
            for pin in item.obj.pins:
                pin.x += dx
                pin.y += dy
        if isinstance(item, FrameItem):
            if not self.group:
                self._move_frame_contents(item, dx, dy)
            return
        if isinstance(item, CommentItem):
            if item.obj.group and not self.group:     # the other boxes of the title block follow
                sibs = [it for it in self.items_by_id.values() if isinstance(it, CommentItem) and it is not item
                        and it.obj.group == item.obj.group and not it.isSelected()]
                self.group = set(sibs) | {item}
                try:
                    for it in sibs:
                        it.setPos(it.pos() + QPointF(dx, dy))
                finally:
                    self.group = set()
            return
        moving = lambda it: it.isSelected() or it in self.group
        for w, which in list(self._attached(self._ref_of(item))):
            other = w.end if which == 'start' else w.start
            owner = self.owner_of(other)
            together = owner is not None and moving(item) and moving(owner)
            carry_port = owner is not None and owner.kind == 'pio' and not together and item.kind != 'pio'
            if together and which == 'end':
                continue                        # moved once already, from its start end
            if not other or together or carry_port:
                w.points = [[x + dx, y + dy] for x, y in w.points]
                if carry_port:
                    self._carry(owner, dx, dy, w)
            elif item.kind == 'pio' and not self.following:
                self._route_pio_net(w, which, item.obj, dx, dy)   # interactive routing (Press 'z')
            else:
                _shift_end(w, which, dx, dy)
            if w.id in self.wire_items:
                self.wire_items[w.id].refresh()


    def pin_at(self, pos: QPointF) -> tuple[str, QPointF, BdPin | None, BdPortIo | None] | None:
        """Connection point under the cursor: (ref, point, pin, port)."""
        for inst in self.bd.instances:
            for pin in inst.pins:
                if abs(pin.x - pos.x()) <= PIN_GRAB and abs(pin.y - pos.y()) <= PIN_GRAB:
                    return f'pin:{inst.id}:{pin.name}', QPointF(*pin_end(pin)), pin, None
        for pio in self.bd.port_ios:
            if abs(pio.x - pos.x()) <= PORT_EDGE + 3 and abs(pio.y - pos.y()) <= 7:
                attached = any(True for _ in self._attached(f'pio:{pio.id}'))
                side = self.port_side(pio) if attached else (1 if pos.x() >= pio.x else -1)
                return f'pio:{pio.id}', QPointF(*self.port_edge(pio, side)), None, pio
        # An embedded block takes a net anywhere on it: the end goes to the nearest point of
        # its edge (on the grid), like a port of a component.
        for it in self.items_by_id.values():
            if isinstance(it, EmbeddedItem) and it.body().adjusted(-PIN_GRAB, -PIN_GRAB, PIN_GRAB, PIN_GRAB).contains(pos):
                x, y, _ = it.edge_point(pos.x(), pos.y())
                return f'emb:{it.obj.id}', QPointF(x, y), None, None
        return None

    # modes -----------------------------------------------------------------------
    def set_mode(self, mode: str):
        """Switch tool ('select' or an add mode): cancel a half-drawn net and the add preview, set the
        drag mode and cursor of the views.
        """
        self.mode = mode
        self._cancel_wire()
        self._clear_ghost()
        for v in self.views():
            v.setDragMode(FsmGraphicsView.RubberBandDrag if mode == 'select' else FsmGraphicsView.NoDrag)
            v.viewport().setCursor(Qt.ArrowCursor if mode == 'select' else Qt.CrossCursor)

    def _cancel_wire(self):
        """Forget the net being drawn (start, corners, rubber line)."""
        self._wire_start = None
        self._wire_pts = []
        if self._rubber is not None:
            self.removeItem(self._rubber)
            self._rubber = None

    def mousePressEvent(self, e):
        """Clears a port / name line / net name selected on its own, then handles the add tools: a
        click places the object of the current mode (the window does it: place_requested); for the
        net tools the first click starts the net (on an object or in open space), clicks in open
        space add corners and a click on an object ends and connects the net.
        """
        if self.selected_pins and e.button() == Qt.LeftButton and not e.modifiers() & Qt.ControlModifier:
            self.select_pin(None, None)         # a port click selects it again below (Ctrl+click adds one)
        if self.selected_text is not None and e.button() == Qt.LeftButton:
            self.select_text(None)              # a click on a name line selects it again below
        if self.selected_label is not None and e.button() == Qt.LeftButton:
            self.select_label(None)             # a click on a net name selects it again below
        if self.mode == 'select' or e.button() != Qt.LeftButton or self.readonly:
            return super().mousePressEvent(e)
        pos = QPointF(_snap(e.scenePos().x()), _snap(e.scenePos().y()))
        if self.mode in ('component', 'port_in', 'port_out', 'port_inout', 'embedded', 'frame', 'frame_if',
                         'frame_else', 'comment', 'panel'):
            self.place_requested.emit(pos)
            return
        if self.mode in NET_MODES:
            # As in the legacy tool (checked on the legacy tool) a net starts on anything: a component port, a
            # PortIO, an embedded block, an existing net (joined with a dot) or open space.
            # A later click on one of those objects ends the net there and connects it; a
            # click in open space only adds a corner and the net goes on; a double-click ends
            # it in open space (a dangling end).
            hit = self.pin_at(e.scenePos()) or self.net_at(e.scenePos())
            if self._wire_start is None:
                if hit is None:
                    hit = ('', pos, None, None)          # open space: a dangling start
                self._wire_start = (hit[0], hit[1])
                self._wire_pts = []
                self._rubber = QGraphicsPathItem()
                self._rubber.setPen(QPen(QColor(0, 0, 0), 0))   # The legacy tool: a thin solid line
                self.addItem(self._rubber)
                return
            if hit is not None:
                self.finish_wire(hit)
            else:
                last = QPointF(*self._wire_pts[-1]) if self._wire_pts else self._wire_start[1]
                if QLineF(last, pos).length() > 0.01:    # the 2nd press of a double-click: nothing new
                    self._wire_pts += self._ortho_leg(pos)

    def contextMenuEvent(self, e):
        """Right click: select the object under the cursor (alone, unless already selected) and ask the
        window for its popup menu.
        """
        item = None
        for it in self.items(e.scenePos()):
            if isinstance(it, (_Movable, WireItem)):
                item = it
                break
        pin = item.pin_at(e.scenePos()) if isinstance(item, InstanceItem) else None
        if pin is not None:
            # on a component port: that port is selected (unless it is one of the ports already
            # selected) and the port popup menu is shown, as in the legacy tool
            if (item.obj.id, pin.name) not in self.selected_pins:
                self.clearSelection()
                self.select_pin(item, pin)
        elif item is not None and not item.isSelected():
            self.select_pin(None, None)
            self.clearSelection()
            item.setSelected(True)
        self.context_requested.emit(item, e.screenPos(), e.scenePos())

    def net_at(self, pos: QPointF) -> tuple[str, QPointF, None, None] | None:
        """An existing net under pos, as a connection point for a new net: ('net:<wire id>',
        the nearest point of that net on the grid, None, None). The caller joins the new net
        to it there with a junction dot, and the new net takes its name."""
        best = None
        for w in self.bd.wires:
            for a, b in zip(w.points, w.points[1:]):
                seg = QLineF(QPointF(*a), QPointF(*b))
                if seg.length() < 1e-6:
                    continue
                t = max(0.0, min(1.0, QPointF.dotProduct(pos - seg.p1(), seg.p2() - seg.p1()) / seg.length() ** 2))
                q = seg.pointAt(t)
                d = QLineF(pos, q).length()
                if d <= 4 and (best is None or d < best[0]):
                    # snap along the segment only (stay on the net)
                    q = QPointF(_snap(q.x()), q.y()) if abs(a[1] - b[1]) < 0.01 else QPointF(q.x(), _snap(q.y()))
                    best = (d, w, q)
        return (f'net:{best[1].id}', best[2], None, None) if best else None

    def _ortho_leg(self, to: QPointF) -> list[list[float]]:
        """Corner points from the last point of the net being drawn to `to`, with right angles
        as the legacy tool draws them: after a horizontal segment the net turns vertical first, and the
        other way round (the first leg starts horizontal). Returns [[x, y], ...] ending at `to`."""
        last = QPointF(*self._wire_pts[-1]) if self._wire_pts else self._wire_start[1]
        if abs(last.x() - to.x()) < 0.01 or abs(last.y() - to.y()) < 0.01:
            return [[to.x(), to.y()]]
        prev = QPointF(*self._wire_pts[-2]) if len(self._wire_pts) > 1 else \
            (self._wire_start[1] if self._wire_pts else None)
        horizontal_before = prev is not None and abs(prev.y() - last.y()) < 0.01
        corner = [last.x(), to.y()] if horizontal_before else [to.x(), last.y()]
        return [corner, [to.x(), to.y()]]

    def mouseDoubleClickEvent(self, e):
        """Net tools: a double-click ends the net in open space. Select tool: a double-click on a net
        or a PortIO edits the net name in place.
        """
        if self.mode in NET_MODES:
            # a double-click ends the net in open space, at the clicked point (a dangling end);
            # the corner(s) up to it are added here unless its first press already did
            if self._wire_start is not None:
                pos = QPointF(_snap(e.scenePos().x()), _snap(e.scenePos().y()))
                last = QPointF(*self._wire_pts[-1]) if self._wire_pts else self._wire_start[1]
                if QLineF(last, pos).length() > 0.01:
                    self._wire_pts += self._ortho_leg(pos)
                if self._wire_pts:
                    end = self._wire_pts.pop()
                    self.finish_wire(('', QPointF(*end), None, None))
            e.accept()
            return
        if self.mode == 'select' and e.button() == Qt.LeftButton:
            # Qt only gives a double-click to the item that took the first press; nets are
            # edited in place whichever net is under the cursor
            wire = next((it for it in self.items(e.scenePos()) if isinstance(it, WireItem)), None)
            top = next(iter(self.items(e.scenePos())), None)
            if isinstance(top, PortIoItem):
                # a port: edit the net it stands for (its name is the net name), at the click
                self.edit_net_requested.emit(top.obj.name, e.scenePos())
                return
            if wire is not None and (top is wire or not isinstance(top, _Movable)):
                # a net: the edit box goes over the net name, as in the legacy tool (else at the click)
                pos = e.scenePos()
                if wire.obj.show_text and wire.obj.points and not wire.is_label_vertical():
                    pos = wire.label_pos(QFontMetricsF(MONO).horizontalAdvance(wire.obj.net))
                self.edit_net_requested.emit(wire.obj.net, pos)
                return
        super().mouseDoubleClickEvent(e)

    # drops from the Component Browser ------------------------------------------------
    def _component_drop(self, e) -> tuple[str, str] | None:
        """(library, unit) carried by a Component Browser drag, or None for other drags."""
        from .component_browser import MIME_TYPE
        md = e.mimeData()
        if self.readonly or not md.hasFormat(MIME_TYPE):
            return None
        lib, _, unit = bytes(md.data(MIME_TYPE)).decode().partition('/')
        return (lib, unit) if unit else None

    def dragEnterEvent(self, e):
        """Accept drags from the Component Browser."""
        if self._component_drop(e) is not None:
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        """Keep accepting a Component Browser drag while it moves."""
        if self._component_drop(e) is not None:
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        """A unit dropped from the Component Browser: ask the window to add it at the grid point."""
        hit = self._component_drop(e)
        if hit is None:
            return super().dropEvent(e)
        e.acceptProposedAction()
        self.component_dropped.emit(hit[0], hit[1], QPointF(_snap(e.scenePos().x()), _snap(e.scenePos().y())))

    # placement preview ----------------------------------------------------------------
    def _update_ghost(self, pos: QPointF):
        """While adding a port or an embedded block, a faded copy of it follows the cursor (on
        the grid), as in the legacy tool. It is a real item drawn at low opacity that takes no clicks and is
        not part of the model; set_mode() removes it."""
        kind = {'port_in': 'input', 'port_out': 'output', 'port_inout': 'inout', 'embedded': 'emb'}.get(self.mode)
        if self.mode == 'component' and self.ghost_instance is not None:
            kind = 'comp'
        if kind is None or self.readonly:
            self._clear_ghost()
            return
        if self._ghost is None or self._ghost[0] != kind:
            self._clear_ghost()
            if kind == 'emb':
                n = max((e.number for e in self.bd.embedded), default=0) + 1
                item = EmbeddedItem(self, BdEmbedded('_ghost', f'eb{n}', n, '', 0, 0, *EMB_NEW_SIZE))
                item.ghost = True                  # drawn as an outline, as the legacy tool shows it
            elif kind == 'comp':
                item = InstanceItem(self, self.ghost_instance)
            else:
                item = PortIoItem(self, BdPortIo('_ghost', '', kind))
                item.ghost = True                  # drawn as an outline, as the legacy tool shows it
            item.setFlags(QGraphicsItem.GraphicsItemFlags())   # not selectable, not movable
            item.setAcceptedMouseButtons(Qt.NoButton)
            item.setOpacity(1.0 if kind != 'comp' else 0.35)
            item.setZValue(20)
            self.addItem(item)
            self._ghost = (kind, item)
        item = self._ghost[1]
        x, y = self.placement_origin(self.mode, pos)
        if kind == 'comp':
            # the instance's ports are stored in scene coordinates: move them with the body
            for pin in item.obj.pins:
                pin.x += x - item.obj.x
                pin.y += y - item.obj.y
        item.obj.x, item.obj.y = x, y
        item.setPos(x, y)

    def placement_origin(self, mode: str, cursor: QPointF) -> tuple[float, float]:
        """Model position (x, y) of a port or embedded block added at the cursor, on the grid,
        with the cursor where the legacy tool has it: at the tip of a port's stub (where its net
        attaches), at the bottom-left corner of an embedded block."""
        cx, cy = _snap(cursor.x()), _snap(cursor.y())
        if mode in ('port_in', 'port_out', 'port_inout'):
            # a free port shows its stub on this side (the preview's side); the centre is a
            # port half-width from the tip
            pmode = {'port_in': 'input', 'port_out': 'output', 'port_inout': 'inout'}[mode]
            probe = BdPortIo('_probe', '', pmode, 0.0, 0.0)
            tip = self.port_edge(probe)
            return cx - tip[0], cy - tip[1]
        if mode == 'embedded':
            return cx, cy - EMB_NEW_SIZE[1]
        if mode == 'component' and self.ghost_instance is not None:
            return cx, cy - self.ghost_instance.h          # a dropped component: same corner
        return cx, cy

    def _clear_ghost(self):
        """Remove the add preview."""
        if self._ghost is not None:
            self.removeItem(self._ghost[1])
            self._ghost = None

    def mouseMoveEvent(self, e):
        """Move the add preview and draw the net being drawn with the leg a click would add."""
        self._update_ghost(e.scenePos())
        if self._wire_start is not None and self._rubber is not None:
            # the net drawn so far, then the right-angled leg that a click would add
            path = QPainterPath(self._wire_start[1])
            for x, y in self._wire_pts:
                path.lineTo(x, y)
            cur = QPointF(_snap(e.scenePos().x()), _snap(e.scenePos().y()))
            for x, y in self._ortho_leg(cur):
                path.lineTo(x, y)
            self._rubber.setPath(path)
        super().mouseMoveEvent(e)

    def finish_wire(self, end_hit):
        """End the net being drawn at `end_hit` (ref, point, ...) and hand it to the window
        (wire_finished), which creates the net, names it and connects it.
        """
        start_ref, start_pt = self._wire_start
        bends = list(self._wire_pts)
        self._cancel_wire()
        end_ref, end_pt = end_hit[0], end_hit[1]
        if end_ref and end_ref == start_ref:
            return
        self.wire_finished.emit(start_ref, end_ref, [start_pt.x(), start_pt.y()], bends, [end_pt.x(), end_pt.y()])

    wire_finished = Signal(str, str, list, list, list)

    # deletion ----------------------------------------------------------------------
    def delete_selected(self) -> bool:
        """Delete the selected objects and nets (with the nets attached to deleted objects); a port
        loses its net name when no wire is left on it. Returns False when nothing was deleted.
        """
        if self.readonly:
            return False
        bd = self.bd
        sel = self.selectedItems()
        if not sel:
            return False
        dead_panels = {i.obj.id for i in sel if isinstance(i, PanelItem)}
        bd.panels = [p for p in bd.panels if p.id not in dead_panels]
        dead_wires = {i.obj.id for i in sel if isinstance(i, WireItem)}
        dead_objs = {i.obj.id: i for i in sel if isinstance(i, _Movable) and not isinstance(i, TextBlockItem)}
        for oid, it in dead_objs.items():
            for w, _ in self._attached(self._ref_of(it)):
                dead_wires.add(w.id)
        touched_pins = set()
        for w in bd.wires:
            if w.id in dead_wires:
                touched_pins.update(r for r in (w.start, w.end) if r.startswith('pin:'))
        bd.wires = [w for w in bd.wires if w.id not in dead_wires]
        bd.instances = [i for i in bd.instances if i.id not in dead_objs]
        bd.embedded = [e for e in bd.embedded if e.id not in dead_objs]
        bd.port_ios = [p for p in bd.port_ios if p.id not in dead_objs]
        bd.frames = [f for f in bd.frames if f.id not in dead_objs]
        bd.comments = [c for c in bd.comments if c.id not in dead_objs]
        bd.junctions = [j for j in bd.junctions if j.id not in dead_objs]
        # a pin keeps its net only while a wire is still attached to it
        still = {r for w in bd.wires for r in (w.start, w.end)}
        for inst in bd.instances:
            for pin in inst.pins:
                if f'pin:{inst.id}:{pin.name}' in touched_pins and f'pin:{inst.id}:{pin.name}' not in still:
                    pin.net = ''
        self.load(bd)
        self.changed_model.emit()
        return True


def _dist_to_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
    """Distance from p to the segment a-b."""
    seg = QLineF(a, b)
    t = max(0.0, min(1.0, QPointF.dotProduct(p - a, b - a) / seg.length() ** 2))
    return QLineF(p, seg.pointAt(t)).length()


def _shift_end(w: BdWire, which: str, dx: float, dy: float):
    """Move one end of a wire and keep its first/last segment horizontal or vertical."""
    pts = w.points
    if not pts:
        return
    i, j = (0, 1) if which == 'start' else (len(pts) - 1, len(pts) - 2)
    if len(pts) == 1:
        pts[0] = [pts[0][0] + dx, pts[0][1] + dy]
        return
    p, q = pts[i], pts[j]
    horizontal = abs(p[1] - q[1]) < 0.01
    vertical = abs(p[0] - q[0]) < 0.01
    pts[i] = [p[0] + dx, p[1] + dy]
    if len(pts) == 2:
        a, b = pts
        if abs(a[0] - b[0]) > 0.01 and abs(a[1] - b[1]) > 0.01:
            if horizontal or not vertical:
                mx = _snap((a[0] + b[0]) / 2)
                w.points = [a, [mx, a[1]], [mx, b[1]], b]
            else:
                my = _snap((a[1] + b[1]) / 2)
                w.points = [a, [a[0], my], [b[0], my], b]
        return
    if horizontal:
        pts[j] = [q[0], q[1] + dy]
    elif vertical:
        pts[j] = [q[0] + dx, q[1]]


def _leave_edge(w: BdWire, which: str, pin: BdPin):
    """Route a net end so that it leaves its port straight out of the component edge."""
    out = {'left': (-1, 0), 'right': (1, 0), 'top': (0, -1), 'bottom': (0, 1)}[pin.side]
    pts = w.points if which == 'start' else list(reversed(w.points))
    end = [pin.x, pin.y]
    stub = [pin.x + out[0] * 2 * GRID, pin.y + out[1] * 2 * GRID]
    rest = pts[1:] if len(pts) > 1 else [stub]
    route = _simplify(_orthogonal([end, stub] + rest))
    w.points = route if which == 'start' else list(reversed(route))


ROUTE_MODES = ['River', 'Avoidance', 'Diagonal', 'Dog Leg']   # legacy order; River is the default


def route_net(mode: str, a: list[float], da: tuple[int, int], b: list[float], db: tuple[int, int],
              obstacles: list[QRectF]) -> list[list[float]]:
    """Route from a (leaving in direction da) to b (entered from direction db).
    Diagonal: a straight line. Dog Leg: one corner, crossing objects if need be. Avoidance:
    right angles around components and ports. (River keeps the existing route: see _shift_end.)"""
    if mode == 'Diagonal':
        return [list(a), list(b)]
    if mode == 'Dog Leg':
        corner = [b[0], a[1]] if da[0] else [a[0], b[1]]
        return _simplify([list(a), corner, list(b)])
    path = _avoid(a, da, b, db, obstacles)
    return path if path else route_net('Dog Leg', a, da, b, db, obstacles)


def _avoid(a, da, b, db, obstacles: list[QRectF], limit: int = 40000) -> list[list[float]] | None:
    """Shortest right-angle route on the grid that keeps off the obstacles (few bends preferred).

    A* search on grid cells (integer coordinates, one cell = GRID). The search state is
    (cell, direction of arrival), so a change of direction can cost extra: each step costs 1,
    each bend 4 more, which makes routes with few corners win over equally long zig-zags. The
    heuristic is the Manhattan distance to the goal (admissible: never more than the real cost).
    Returns None when no route is found within `limit` expanded states (the caller then falls
    back to a Dog Leg route)."""
    g = GRID
    # start / goal cells: two grid steps out of each end, so the route leaves a port straight
    sa = (round((a[0] + da[0] * 2 * g) / g), round((a[1] + da[1] * 2 * g) / g))     # leave a stub at each end
    sb = (round((b[0] + db[0] * 2 * g) / g), round((b[1] + db[1] * 2 * g) / g))
    # obstacles grown by one grid step: a route never runs along the edge of a component
    blocked = [QRectF(r.x() - g, r.y() - g, r.width() + 2 * g, r.height() + 2 * g) for r in obstacles]
    # search window: the box around both ends plus a margin of 40 cells (bounds the search)
    lo_x, hi_x = min(sa[0], sb[0]) - 40, max(sa[0], sb[0]) + 40
    lo_y, hi_y = min(sa[1], sb[1]) - 40, max(sa[1], sb[1]) + 40

    def free(c):
        """True when grid cell `c` is inside the search window and outside every (enlarged) obstacle."""
        x, y = c[0] * g, c[1] * g
        return lo_x <= c[0] <= hi_x and lo_y <= c[1] <= hi_y and not any(r.contains(QPointF(x, y)) for r in blocked)

    import heapq
    start = (sa, None)
    best = {start: 0}           # (cell, arrival direction) -> lowest cost found so far
    prev = {}                   # (cell, direction) -> the state it was reached from
    heap = [(0, 0, sa, None)]   # (cost + heuristic, cost, cell, arrival direction)
    count = 0
    while heap and count < limit:
        f, cost, c, d = heapq.heappop(heap)
        count += 1
        if c == sb:
            # goal reached: walk the `prev` links back to the start, then turn the cells into
            # scene points between the two real end points
            node, cells = (c, d), [c]
            while node in prev:
                node = prev[node]
                cells.append(node[0])
            cells.reverse()
            pts = [list(a)] + [[x * g, y * g] for x, y in cells] + [list(b)]
            return _simplify(_orthogonal(pts))
        for nd in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c[0] + nd[0], c[1] + nd[1])
            if n != sb and not free(n):
                continue
            nc = cost + 1 + (4 if d is not None and nd != d else 0)
            key = (n, nd)
            if nc < best.get(key, 1 << 30):
                best[key] = nc
                prev[key] = (c, d)
                heapq.heappush(heap, (nc + abs(n[0] - sb[0]) + abs(n[1] - sb[1]), nc, n, nd))
    return None


def _pin_route(a: list[float], da: tuple[int, int], b: list[float], db: tuple[int, int] | None,
               body: QRectF) -> list[list[float]]:
    """Right-angle route from port a (leaving along da) to b (entered along -db when given),
    going round the component body when b lies behind the port."""
    m = 2 * GRID
    sa = [a[0] + da[0] * m, a[1] + da[1] * m]
    sb = [b[0] + db[0] * m, b[1] + db[1] * m] if db else list(b)
    pts = [list(a), sa]
    ahead = (sb[0] - sa[0]) * da[0] + (sb[1] - sa[1]) * da[1]
    if ahead < 0:
        # the other end is behind the port: go round the body, on the side nearer to it
        if da[0]:
            y = body.top() - m if sb[1] < body.center().y() else body.bottom() + m
            pts += [[sa[0], y], [sb[0], y]]
        else:
            x = body.left() - m if sb[0] < body.center().x() else body.right() + m
            pts += [[x, sa[1]], [x, sb[1]]]
    elif da[0]:
        mx = _snap((sa[0] + sb[0]) / 2) if db and db[0] else sb[0]
        pts += [[mx, sa[1]], [mx, sb[1]]]
    else:
        my = _snap((sa[1] + sb[1]) / 2) if db and db[1] else sb[1]
        pts += [[sa[0], my], [sb[0], my]]
    pts += [sb, list(b)]
    return _simplify(_orthogonal(pts))


def _join(a: list[float], b: list[float]) -> list[list[float]]:
    """Corner points that join a to b with horizontal/vertical segments."""
    if abs(a[0] - b[0]) < 0.01 or abs(a[1] - b[1]) < 0.01:
        return []
    mx = _snap((a[0] + b[0]) / 2)
    return [[mx, a[1]], [mx, b[1]]]


def _orthogonal(pts: list[list[float]]) -> list[list[float]]:
    """Insert corner points so every segment of `pts` is horizontal or vertical (see _join)."""
    out = [pts[0]]
    for q in pts[1:]:
        out += _join(out[-1], q) + [q]
    return out


def _simplify(pts: list[list[float]]) -> list[list[float]]:
    """Drop repeated points and route points that lie in line with their neighbours
    (a route point dragged into line with the next ones merges into the straight run)."""
    out: list[list[float]] = []
    for q in pts:
        if out and abs(out[-1][0] - q[0]) < 0.01 and abs(out[-1][1] - q[1]) < 0.01:
            continue
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            cross = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
            span = max(abs(q[0] - a[0]) + abs(q[1] - a[1]), 1.0)
            if abs(cross) / span < 0.5:         # b is on the line a-q
                out[-1] = q
                continue
        out.append(q)
    return out if len(out) >= 2 else [list(p) for p in pts[:1]] + [list(p) for p in pts[-1:]]


def _move_net(orig: list[list[float]], dx: float, dy: float, fixed_start: bool, fixed_end: bool):
    """Move a whole net; ends attached to pins/ports stay and are joined orthogonally."""
    moved = [[x + dx, y + dy] for x, y in orig]
    if fixed_start:
        moved[0] = list(orig[0])
    if fixed_end:
        moved[-1] = list(orig[-1])
    return _orthogonal(moved)


def _move_segment(orig: list[list[float]], k: int, dx: float, dy: float, fixed_start: bool, fixed_end: bool):
    """Move segment k across its direction; connected segments stretch."""
    pts = [list(q) for q in orig]
    a, b = pts[k], pts[k + 1]
    if abs(a[1] - b[1]) < 0.01:
        dx = 0.0                    # horizontal segment moves up/down
    elif abs(a[0] - b[0]) < 0.01:
        dy = 0.0                    # vertical segment moves left/right
    na, nb = [a[0] + dx, a[1] + dy], [b[0] + dx, b[1] + dy]
    head, tail = pts[:k], pts[k + 2:]
    if k == 0 and fixed_start:
        head = [a]
    if k + 1 == len(pts) - 1 and fixed_end:
        tail = [b]
    return _orthogonal(head + [na, nb] + tail)


def _route(a: list[float], bends: list[list[float]], b: list[float]) -> list[list[float]]:
    """Orthogonal polyline from a through the bend points to b."""
    pts = [a]
    for p in bends + [b]:
        last = pts[-1]
        if abs(last[0] - p[0]) > 0.01 and abs(last[1] - p[1]) > 0.01:
            if p is b and not bends:
                mx = _snap((last[0] + p[0]) / 2)
                pts += [[mx, last[1]], [mx, p[1]]]
            else:
                pts.append([p[0], last[1]])
        pts.append(p)
    return pts


# ---------------------------------------------------------------------------
# Side panels and dialogs
# ---------------------------------------------------------------------------
class InstanceParamsPanel(QWidget):
    """Equivalent of "BD Object Properties - Component Parameters"."""

    def __init__(self, on_change):
        """Build the panel; `on_change()` is called after each edit of the instance."""
        super().__init__()
        self.on_change = on_change
        self.inst: BdInstance | None = None
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.editingFinished.connect(self._renamed)
        self.title = QLabel('<b>Select a component instance</b>')
        lay.addWidget(self.title)
        form.addRow('Instance name', self.name)
        lay.addLayout(form)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['Parameter', 'Value (override)'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._changed)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        b = QPushButton('Add'); b.clicked.connect(self._add); row.addWidget(b)
        b = QPushButton('Remove'); b.clicked.connect(self._remove); row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(QLabel('<small>Only parameters listed here are written as <tt>#( … )</tt>.</small>'))
        self._loading = False
        self.setEnabled(False)

    def show_instance(self, inst: BdInstance | None):
        """Show instance `inst` (None: nothing selected, the panel is disabled)."""
        self.inst = inst
        self.setEnabled(inst is not None)
        self._loading = True
        self.table.setRowCount(0)
        self.name.setText(inst.name if inst else '')
        self.title.setText(f'<b>{inst.library}.{inst.unit}</b>' if inst else '<b>Select a component instance</b>')
        for prm in (inst.params if inst else []):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(prm.name))
            self.table.setItem(r, 1, QTableWidgetItem(prm.value))
        self._loading = False

    def _renamed(self):
        """The instance name was edited: rename the instance."""
        if self.inst and self.name.text().strip() and self.name.text().strip() != self.inst.name:
            self.inst.name = self.name.text().strip()
            self.on_change()

    def _changed(self, *_):
        """The table was edited: rebuild the instance's parameter overrides from it."""
        if self._loading or not self.inst:
            return
        self.inst.params = []
        for r in range(self.table.rowCount()):
            n = self.table.item(r, 0).text().strip() if self.table.item(r, 0) else ''
            v = self.table.item(r, 1).text().strip() if self.table.item(r, 1) else ''
            if n:
                self.inst.params.append(Parameter(n, v))
        self.on_change()

    def _add(self):
        """Add an override row (PARAM = 0)."""
        self._loading = True
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem('PARAM'))
        self.table.setItem(r, 1, QTableWidgetItem('0'))
        self._loading = False
        self._changed()

    def _remove(self):
        """Remove the selected override rows."""
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)
        self._changed()


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------
class BdEditorWindow(QMainWindow, PanelCommands):
    """The block diagram editor window (layout as the legacy tool: one page at a time - diagram, Signal
    Table, Parameters Table, Compiler Directives - the Diagram Browser on the right, HDL Studio's
    own Properties / Messages docks hidden at start).

    Data flow is the same as in the state diagram editor (main_window.MainWindow): the window
    owns the BlockDiagram (`self.bd`), BdScene edits it and emits `changed_model`, changed()
    marks the window dirty, records an undo step and schedules regenerate(). Saving and
    generation go through the EditorContext given by the Design Manager.
    """
    def __init__(self, bd: BlockDiagram, context=None):
        """Build the window for diagram `bd`; `context` is the EditorContext of the Design Manager
        (None for a diagram opened on its own, e.g. by tests).
        """
        super().__init__()
        install_app_icon()                  # Vietsemi mark (also when run on its own)
        self.bd = bd
        self.context = context
        self.dirty = False
        self._pending_component: dict | None = None
        self._clipboard: list[dict] = []
        self.scene = BdScene(self)
        self.canvas = FsmGraphicsView(self.scene)
        # moves without a button pressed must reach the scene: the placement preview (faded
        # port / embedded block under the cursor) follows them
        self.canvas.viewport().setMouseTracking(True)
        self.signals_tab = SignalsTable(kind='bd')
        self.params_tab = ParametersTable(kind='bd')
        self.code = CodeView()
        self.emb_edit = QPlainTextEdit(); self.emb_edit.setFont(QFont('Courier New', 9))
        self.emb_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.emb_title = QLabel('<b>Select an embedded block</b>')
        emb_box = QWidget(); el = QVBoxLayout(emb_box); el.addWidget(self.emb_title); el.addWidget(self.emb_edit)
        self.emb_edit.setEnabled(False)
        self.emb: BdEmbedded | None = None
        self.emb_edit.textChanged.connect(self._emb_changed)

        directives = QWidget(); f = QFormLayout(directives)
        self.dir_edits = {}
        for label, attr in (('Pre-module directives', 'pre_module_directives'),
                            ('Post-module directives', 'post_module_directives'),
                            ('End-module directives', 'end_module_directives')):
            w = QPlainTextEdit(); w.setFont(QFont('Courier New', 9)); w.setMaximumHeight(90)
            w.textChanged.connect(lambda w=w, a=attr: self._directive_changed(a, w))
            self.dir_edits[attr] = w
            f.addRow(label, w)

        # As in the legacy tool the window shows one page at a time (the diagram, the Signal Table, the
        # Parameters Table, the directives); there is no tab bar, the pages are reached from the
        # Structure Navigator and the View / Diagram menus.
        self.tabs = QTabWidget()
        self.tabs.addTab(self.canvas, 'Block Diagram')
        self.tabs.addTab(self.signals_tab, 'Signal Table')
        self.tabs.addTab(self.params_tab, 'Parameters Table')
        self.tabs.addTab(directives, 'Compiler Directives')
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(lambda _i: (self.update_title(), self._sync_navigator()))
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.tabs)
        cb = QWidget(); cl = QVBoxLayout(cb); cl.setContentsMargins(0, 0, 0, 0)
        self.code_title = QLabel(); cl.addWidget(self.code_title); cl.addWidget(self.code)
        split.addWidget(cb)
        split.setSizes([1050, 550])
        cb.hide()                       # The legacy tool has no HDL pane in the diagram window (HDL > View Generated HDL)
        self.code_pane = cb
        self.setCentralWidget(split)

        # Diagram Browser (right, as in the legacy tool): the Structure Navigator of the diagram
        from .diagram_browser import DiagramBrowser
        self.browser = DiagramBrowser(['Name', 'Instance'])
        self.navigator = self.browser.navigator
        self.navigator.itemClicked.connect(self._navigator_clicked)
        nd = QDockWidget('Diagram Browser', self); nd.setObjectName('diagram_browser')
        nd.setTitleBarWidget(QWidget())             # the browser draws its own vertical tab
        nd.setWidget(self.browser); self.addDockWidget(Qt.RightDockWidgetArea, nd)
        self.browser_dock = nd

        # HDL Studio's own panels (component parameters, embedded block code, messages): kept, but
        # hidden at start so the window looks like the legacy tool; Edit Code / the legacy tool Log Window show them
        self.inst_panel = InstanceParamsPanel(self.changed)
        side = QTabWidget()
        side.addTab(self.inst_panel, 'Component')
        side.addTab(emb_box, 'Embedded Block')
        self.side_tabs = side
        d = QDockWidget('Properties', self); d.setObjectName('properties')
        d.setWidget(side); self.addDockWidget(Qt.LeftDockWidgetArea, d)
        self.props_dock = d
        self.log = QListWidget(); self.log.setFont(QFont('Courier New', 9))
        ld = QDockWidget('Messages', self); ld.setObjectName('messages')
        ld.setWidget(self.log); self.addDockWidget(Qt.BottomDockWidgetArea, ld)
        self.log_dock = ld
        self.resizeDocks([ld], [90], Qt.Vertical)
        self.resizeDocks([d, nd], [330, 300], Qt.Horizontal)
        d.hide()
        ld.hide()
        self._fill_navigator()

        self.undo_stack = SnapshotUndo(lambda: self.bd.to_json(), self._restore_snapshot, self)
        self._build_actions()
        self.undo_stack.changed.connect(self._update_undo)
        for k, text in enumerate(('Block Diagram', 'Signal Table', 'Parameters Table', 'Compiler Directives')):
            a = QAction(text, self)
            a.triggered.connect(lambda checked=False, k=k: self.tabs.setCurrentIndex(k))
            self.addAction(a)
        about = QAction(f'About {APP_NAME}', self)
        about.triggered.connect(lambda: show_about(self, 'Block diagram editor'))
        self.addAction(about)
        self._diagram_menus = lambda: bd_menus(toolbars=lambda m: fill_toolbars_menu(self, m),
                                               windows=lambda m: EC.fill_windows_menu(self, m))
        arrange_menus(self, self._diagram_menus())
        # the Signal / Parameters Table pages: their own menus and toolbars (table_page.py)
        from .table_page import TablePages
        self.table_pages = TablePages(
            self, 'bd', {'signals': self.signals_tab, 'parameters': self.params_tab}, self.canvas,
            self._diagram_menus,
            lambda: table_menus(False, toolbars=lambda m: fill_toolbars_menu(self, m),
                                windows=lambda m: EC.fill_windows_menu(self, m)),
            BD_KEYS)
        # The legacy tool shows "Ready" in the status bar when no message is shown
        self.statusBar().addWidget(QLabel('Ready'))

        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(250)
        self.timer.timeout.connect(self.regenerate)
        self.scene.selectionChanged.connect(self.on_selection)
        self.scene.changed_model.connect(self.on_scene_changed)
        self.scene.message.connect(lambda m: self.statusBar().showMessage(m, 5000))
        self.scene.place_requested.connect(self.place_at)
        self.scene.comment_edit_requested.connect(self.edit_comment)
        self.scene.wire_finished.connect(self.add_wire)
        self.scene.rename_net_requested.connect(self.rename_net)
        self.scene.edit_net_requested.connect(self.edit_net_inline)
        self.scene.port_dropped.connect(self.port_dropped)
        self.scene.frame_edit_requested.connect(self.frame_properties)
        self.scene.component_dropped.connect(self._component_dropped)
        self.scene.end_dropped.connect(self.end_dropped)
        self.scene.context_requested.connect(self.context_menu)
        self.signals_tab.changed.connect(self.changed)
        self.params_tab.changed.connect(self.changed)
        self.canvas.mouseDoubleClickEvent = self._double_click

        self._load(bd)
        if context is not None and context.readonly:
            self.scene.readonly = True
            for m, a in self.mode_actions.items():
                a.setEnabled(m == 'select')
            for t in (self.signals_tab, self.params_tab):
                t.set_readonly(True)
            self.inst_panel.setEnabled(False)
            self.emb_edit.setReadOnly(True)
            for w in self.dir_edits.values():
                w.setReadOnly(True)
        self.undo_stack.reset()
        self.update_title()
        self.resize(1700, 1000)
        QTimer.singleShot(0, self._restore_view_position)

    # -- actions --------------------------------------------------------------------
    def _act(self, menu, text, slot, key=None, icon_name=None):
        """key may be one shortcut or a list (first one is shown in menus)."""
        a = QAction(text, self)
        if icon_name:
            a.setIcon(icon(icon_name))
        if key:
            keys = [QKeySequence(k) for k in (key if isinstance(key, (list, tuple)) else [key])]
            a.setShortcuts(keys)
            a.setToolTip(f'{text.replace("&", "")}  ({", ".join(k.toString() for k in keys)})')
        a.triggered.connect(slot)
        if menu is not None:
            menu.addAction(a)
        return a

    def _build_actions(self):
        """The actions of the editor: file / edit / view commands, one checkable action per tool
        (Select, Add Component, Add Signal, Add Port, ...), the toolbar with the legacy tool's names and keys,
        the View and legacy menu commands, and the generation toolbar (language).
        """
        fm = self.menuBar().addMenu('&File')
        a_save = self._act(fm, '&Save', self.save, QKeySequence.Save, 'save')
        a_gen = self._act(fm, '&Generate HDL', self.generate, 'Shift+G', 'generate')
        a_open = self._act(fm, 'Open generated HDL', self.open_generated, 'Ctrl+G', 'generate_open')
        fm.addSeparator()
        self._act(fm, '&Close', self.close, QKeySequence.Close)
        em = self.menuBar().addMenu('&Edit')
        self.act_undo = self._act(em, '&Undo', self.undo_stack.undo, QKeySequence.Undo, 'undo')
        self.act_redo = self._act(em, '&Redo', self.undo_stack.redo, ['Ctrl+Y', 'Ctrl+Shift+Z'], 'redo')
        em.addSeparator()
        a_del = self._act(em, '&Delete', self.delete_selected, None, 'delete')
        self._act(em, 'Cu&t', self.cut, QKeySequence.Cut)
        self._act(em, '&Copy', self.copy, QKeySequence.Copy)
        self._act(em, '&Paste', lambda: self.paste(), QKeySequence.Paste)
        em.addSeparator()
        a_stubs = self._act(em, 'Add Signal Stubs', lambda: self._for_selected(self.add_signal_stubs))
        a_stubs_pio = self._act(em, 'Add Signal Stubs and PortIOs', lambda: self._for_selected(self.add_port_ios))
        a_disc = self._act(em, 'Disconnect', lambda: self._for_selected(self.disconnect))
        a_rename = self._act(em, 'Rename &net...', lambda: self.rename_net(self._selected_net()))
        a_all = self._act(em, 'Select All', self.select_all)
        vm = self.menuBar().addMenu('&View')
        a_fit = self._act(vm, 'View All', self.canvas.fit, None, 'fit')
        a_zin = self._act(vm, 'Zoom in', lambda: self.canvas.zoom(1.2), None, 'zoom_in')
        a_zout = self._act(vm, 'Zoom out', lambda: self.canvas.zoom(1 / 1.2), None, 'zoom_out')
        a_zlast = self._act(vm, 'Zoom Last', self.canvas.zoom_last)
        a_area = self._act(vm, 'View Area', self.view_area)
        a_down = self._act(vm, 'Open Down', self.open_down, None, 'open_down')

        group = QActionGroup(self); group.setExclusive(True)
        self.mode_group = group
        self.mode_actions = {}
        for mode, text in (('select', 'Select'), ('select_shape', 'Select Shapes'), ('pan', 'Panning'),
                           ('component', 'Add Component...'), ('wire', 'Add Signal'),
                           ('wire_port', 'Add Signal with a Port'), ('bus', 'Add Bus'),
                           ('bus_port', 'Add Bus with a Port'),
                           ('port_in', 'Add Input Port'), ('port_out', 'Add Output Port'),
                           ('port_inout', 'Add Inout Port'),
                           ('embedded', 'Add Embedded Block'), ('frame', 'Add Frame (FOR)'),
                           ('frame_if', 'Add Frame (IF)'), ('frame_else', 'Add Frame (ELSE)')):
            a = QAction(icon(mode), text, self); a.setCheckable(True)
            a.triggered.connect(lambda checked, m=mode: self.set_mode(m))
            group.addAction(a)
            self.mode_actions[mode] = a
        self.mode_actions['select'].setChecked(True)
        # Add > Component (F3) opens the floating Component Browser, as the legacy tool does (drag a unit
        # onto the diagram); set_mode('component') still places a picked component by a click
        comp = self.mode_actions['component']
        comp.triggered.disconnect()
        comp.triggered.connect(lambda checked=False: self.show_component_browser())
        a_props = QAction('Object Properties', self); a_props.triggered.connect(self.properties_of_selection)
        a_hl = QAction('Highlight Net (in diagram)', self); a_hl.triggered.connect(self.highlight_net)
        a_clr = QAction('Clear Net Highlighting', self); a_clr.triggered.connect(lambda: self.highlight_net(clear=True))
        a_drc = QAction('Run Design Rule Checks', self); a_drc.triggered.connect(self.run_checks)
        by_text = {x.text().replace('&', ''): x for x in self.findChildren(QAction)}
        self.toolbar_actions = {
            'save': a_save, 'cut': by_text.get('Cut'), 'copy': by_text.get('Copy'), 'paste': by_text.get('Paste'),
            'delete': a_del, 'select_all': a_all, 'edit_text': a_rename, 'undo': self.act_undo,
            'redo': self.act_redo, 'object_props': a_props, 'zoom_in': a_zin, 'zoom_out': a_zout,
            'zoom_last': a_zlast, 'view_area': a_area, 'fit': a_fit, 'open_down': a_down, 'highlight': a_hl,
            'clear_highlight': a_clr, 'generate_open': a_open, 'drc': a_drc, 'generate': a_gen,
            'add_stubs': a_stubs, 'add_stubs_ports': a_stubs_pio, 'disconnect': a_disc,
            **self.mode_actions,
        }
        if self.context is not None:
            for key, scope in (('generate_blocks', 'blocks'), ('generate_components', 'components'),
                               ('generate_root', 'root')):
                a = QAction(key, self)
                a.triggered.connect(lambda checked=False, sc=scope: self.context.generate_hierarchy(self.bd, self, sc))
                self.toolbar_actions[key] = a
        self.toolbar_actions = {k: v for k, v in self.toolbar_actions.items() if v is not None}
        # shortcuts of commands that are in no menu of the legacy layout (F2 rename, Ctrl+D open down)
        for a in (a_down, a_del, a_rename):
            self.addAction(a)
        self.canvas.end_command.connect(lambda: self.set_mode('select'))
        self.canvas.tool_done.connect(lambda: self.set_mode(self._mode_before_area))
        self.canvas.nudged.connect(self.scene.changed_model.emit)
        self.canvas.grid = GRID
        self._mode_before_area = 'select'
        self._once = False
        self._build_view_actions()
        self._build_menu_commands()
        self.toolbars = build_toolbars(self, self.toolbar_actions, BD_TOOLBARS, BD_KEYS)
        EC.install_tooltip_filter(self, self.toolbars)
        # this version draws net names and labels as part of their objects: no separate text objects
        self.toolbar_actions['select_text'].setToolTip('Select Text (no separate text objects in this version)')
        gt = QToolBar('Generation', self); gt.setObjectName('gen'); self.addToolBar(gt)
        self.lang = QComboBox(); [self.lang.addItem(LANG_LABEL[l], l) for l in LANGUAGES]
        self.lang.setToolTip('Target language')
        self.lang.currentIndexChanged.connect(self._lang_changed)
        gt.addWidget(self.lang)

    def view_area(self):
        """View Area: drag a rectangle on the diagram to view that area."""
        if self.canvas.tool != 'area':
            self._mode_before_area = 'pan' if self.canvas.tool == 'pan' else 'select'
        self.scene.set_mode('select')
        self.canvas.set_tool('area')
        self.statusBar().showMessage('Drag a rectangle around the area to view (Esc cancels)', 4000)

    def select_all(self):
        """Edit > Select All: select every selectable item."""
        for it in self.scene.items():
            if it.flags() & QGraphicsItem.ItemIsSelectable:
                it.setSelected(True)

    def highlight_net(self, clear: bool = False):
        """Highlight every wire of the selected net (or clear the highlight)."""
        net = '' if clear else self._selected_net()
        if not clear and not net:
            self.statusBar().showMessage('Select a wire to highlight its net', 4000)
            return
        self.scene.highlight = net
        self.scene.update()

    def run_checks(self):
        """Design rule check: connection warnings plus a syntax check of the generated HDL."""
        from hdl.parser import check_text
        text, warnings = generate_bd(self.bd)
        self.log.clear()
        for w in warnings:
            self.log.addItem(f'warning: {w}')
        ext = 'sv' if self.bd.language == 'systemverilog' else 'v'
        errors = [d for d in check_text(text, f'{self.bd.unit}.{ext}', self._include_dirs()) if d[1] == 'error']
        for line, _, msg in errors:
            self.log.addItem(f'error: generated HDL line {line}: {msg}')
        self.log.addItem(f'Design rule check: {len(errors)} error(s), {len(warnings)} warning(s)')

    def set_mode(self, mode: str):
        """Select/Panning tools and the Add commands. Add commands repeat until
        Esc or the right button (Main Settings > Toolbar Buttons: Remain active); Ctrl while
        choosing one toggles that for the command."""
        page = self.tabs.currentWidget()
        if mode == 'select' and hasattr(getattr(page, 'table', None), 'unselect'):
            page.table.unselect()           # Esc on a table page: no cell selected, the page stays
            return
        from prefs import Prefs
        ctrl = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        self._once = mode not in ('select', 'select_shape', 'pan') and \
            ctrl == Prefs.load().toolbar_remain_active
        if mode == 'component':
            choice = self._pick_component()
            if choice is None:
                return self.set_mode('select')
            self._pending_component = choice
            self.statusBar().showMessage(f'Click on the diagram to place {choice["library"]}.{choice["unit"]}')
        self.canvas.set_tool('')
        self.scene.set_mode('select' if mode in ('select_shape', 'pan') else mode)
        if mode == 'component':
            # the faded component that follows the cursor: same body and ports as the instance
            # that a click will add (the "ghosted rectangle" of the legacy tool)
            c = self._pending_component
            ghost = BdInstance('_ghost', c['unit'], c['library'], c['unit'])
            self._layout_pins(ghost, c['ports'])
            self.scene.ghost_instance = ghost
        if mode == 'pan':
            self.canvas.set_tool('pan')
        self.mode_actions[mode].setChecked(True)
        self.tabs.setCurrentWidget(self.canvas)

    def keyPressEvent(self, e):
        """Esc goes back to the Select tool."""
        if e.key() == Qt.Key_Escape:
            self.set_mode('select')
        super().keyPressEvent(e)

    # -- model <-> view ---------------------------------------------------------------
    def _load(self, bd: BlockDiagram):
        """Show diagram `bd`: scene, tables, directives, language; regenerate."""
        self.bd = bd
        self.scene.load(bd)
        self.signals_tab.set_rows(bd.signals, bd.signals_sheet)
        self.params_tab.set_rows(bd.parameters, bd.params_sheet)
        for attr, w in self.dir_edits.items():
            w.blockSignals(True); w.setPlainText(getattr(bd, attr)); w.blockSignals(False)
        self.lang.blockSignals(True); self.lang.setCurrentIndex(LANGUAGES.index(bd.language)); self.lang.blockSignals(False)
        self.on_selection()
        self.regenerate()

    def _restore_snapshot(self, text: str):
        """Put back an undo snapshot without moving the user's view."""
        st = self.canvas.state()
        self._load(BlockDiagram.from_json(text))
        self.canvas.restore(st)
        # back on the saved state (e.g. undo of every edit since the last save): no '*'
        self.dirty = not self.undo_stack.is_clean(text)
        self.update_title()

    def _update_undo(self):
        """Enable Undo / Redo according to the history."""
        self.act_undo.setEnabled(self.undo_stack.can_undo())
        self.act_redo.setEnabled(self.undo_stack.can_redo())

    def _view_key(self) -> str:
        """Key under which the zoom / scroll of this diagram is remembered."""
        if self.context is not None:
            return getattr(self.context, 'key', '') or self.context.view.path
        return ''

    def _restore_view_position(self):
        """Open where the user left the diagram: HDL Studio's own saved view first, then the view
        area the legacy tool saved in the diagram (shown at 100% from its top-left corner, as the legacy tool opens
        it), else the whole diagram."""
        if self.canvas.restore(load_view_state(self._view_key())):
            return
        if self.bd.view_area:
            # The legacy tool "100%" draws 72 diagram units per screen pixel; the import scale is 1/75, so
            # the same size on screen is a zoom of 75/72 (measured on the legacy tool: components
            # and the grid are 4% larger than HDL Studio at zoom 1)
            k = 75 / 72
            x0, y0, _x1, _y1 = self.bd.view_area
            self.canvas.resetTransform()
            self.canvas.scale(k, k)
            vp = self.canvas.viewport()
            self.canvas.centerOn(x0 + vp.width() / (2 * k), y0 + vp.height() / (2 * k))
            return
        self.canvas.fit()

    def on_scene_changed(self):
        """The scene changed the model: refresh the Signal Table (nets may have been added or renamed)."""
        self.signals_tab.set_rows(self.bd.signals, self.bd.signals_sheet)
        self.changed()

    def changed(self):
        """Called after every edit: dirty flag and title, delayed regeneration, undo step. An Add
        command used "once" goes back to Select here.
        """
        if self._once and self.scene.mode != 'select' and self.scene._wire_start is None:
            self._once = False
            QTimer.singleShot(0, lambda: self.set_mode('select'))
        self.dirty = True
        self.update_title()
        self.timer.start()
        self.undo_stack.note_change()
        self._update_undo()

    def _directive_changed(self, attr, w):
        """A Compiler Directives text was edited: store it."""
        setattr(self.bd, attr, w.toPlainText())
        self.changed()

    def _lang_changed(self, _):
        """The language of the generation toolbar changed: store it."""
        self.bd.language = self.lang.currentData()
        self.changed()

    def on_selection(self):
        """Show the selected component / embedded block in the Properties dock."""
        sel = self.scene.selectedItems()
        inst = next((i.obj for i in sel if isinstance(i, InstanceItem)), None)
        emb = next((i.obj for i in sel if isinstance(i, EmbeddedItem)), None)
        self.inst_panel.show_instance(inst)
        if inst:
            self.side_tabs.setCurrentIndex(0)
        self.emb = emb
        self.emb_edit.blockSignals(True)
        self.emb_edit.setPlainText(emb.text if emb else '')
        self.emb_edit.blockSignals(False)
        self.emb_edit.setEnabled(emb is not None)
        self.emb_title.setText(f'<b>Embedded block {emb.number}: {emb.name}</b>' if emb else
                               '<b>Select an embedded block</b>')
        if emb:
            self.side_tabs.setCurrentIndex(1)

    def _emb_changed(self):
        """The code of the selected embedded block was edited in the Properties dock: store it."""
        if self.emb is not None:
            self.emb.text = self.emb_edit.toPlainText()
            self.scene.update()
            self.changed()

    # -- editing operations ----------------------------------------------------------------
    # -- components --------------------------------------------------------------------
    def _project(self):
        """The project the diagram belongs to (None outside the Design Manager)."""
        return self.context.project if self.context is not None else None

    def _pick_component(self) -> dict | None:
        """Ask for a component; returns {library, unit, ports, params} or None."""
        proj = self._project()
        entries = []
        if proj is not None:
            for lib in proj.libraries:
                if not lib.scanned:
                    lib.scan(proj.cache)
                for u in sorted(lib.units.values(), key=lambda u: u.name):
                    if u.type != 'Package':
                        entries.append((lib.name, u.name, u.type))
        start = ''
        if proj is not None and proj.library(self.bd.library) is not None:
            start = proj.library(self.bd.library).main_hdl_dir
        dlg = ComponentPicker(entries, start, self)
        if not dlg.exec():
            return None
        if dlg.file_choice:
            return self._component_from_file(dlg.file_choice)
        choice = dlg.choice()
        if choice is None:
            return None
        lib, unit = choice
        du = proj.find_unit(unit, prefer=proj.library(lib)) if proj else None
        return self._component_info(lib, unit, du)

    def _place_component(self, info: dict, pos: QPointF) -> BdInstance:
        """Add a component as the legacy tool drops one from its Component Browser: the body's
        bottom-left corner at pos, the new instance selected."""
        inst = self._add_component(info, pos)
        dy = -inst.h
        inst.y += dy
        for pin in inst.pins:
            pin.y += dy
        self._reload_scene()
        self.scene.clearSelection()
        it = self.scene.items_by_id.get(inst.id)
        if it is not None:
            it.setSelected(True)
        self.changed()
        return inst

    def show_component_browser(self):
        """Add > Component (F3): the floating Component Browser, as in the legacy tool; a unit dragged
        from it onto the diagram is instantiated where it is dropped."""
        from .component_browser import ComponentBrowser
        proj = self._project()
        if getattr(self, '_browser', None) is None:
            self._browser = ComponentBrowser(proj, self.bd.library, self)
        else:
            self._browser.fill(proj, self.bd.library)
        self._browser.show()
        self._browser.raise_()
        self.set_mode('select')

    def _component_dropped(self, lib: str, unit: str, pos: QPointF):
        """A unit was dropped from the Component Browser at `pos`: instantiate it there."""
        proj = self._project()
        du = proj.find_unit(unit, prefer=proj.library(lib)) if proj else None
        self._place_component(self._component_info(lib, unit, du), pos)
        self.activateWindow()

    def _component_info(self, lib: str, unit: str, du) -> dict:
        """What a new instance of library.unit needs: {library, unit, ports, params, symbol}, read
        from the project's design unit `du` (ports from its HDL or graphical view).
        """
        from project.project import unit_ports
        params = du.hdl.params if du is not None and du.hdl is not None else []
        sym = next((v.path for v in du.views if v.kind == 'symbol' and v.path.endswith('.sb')), '') if du else ''
        return {'library': lib, 'unit': unit, 'ports': unit_ports(du) if du else [], 'params': params,
                'symbol': sym}

    def _component_from_file(self, path: str) -> dict | None:
        """The same information read straight from an HDL file (Add Component > From HDL file); asks
        which module when the file holds several. None when the file has no module.
        """
        from hdl.parser import parse_file
        parsed = parse_file(path, self._include_dirs())
        units = [u for u in parsed.units if u.kind in ('module', 'interface', 'program')]
        if not units:
            QMessageBox.warning(self, 'Add component', f'No module found in {path}.\n' + '\n'.join(parsed.errors[:5]))
            return None
        unit = units[0]
        if len(units) > 1:
            name, ok = QInputDialog.getItem(self, 'Add component', 'Module:', [u.name for u in units], 0, False)
            if not ok:
                return None
            unit = next(u for u in units if u.name == name)
        ports = []
        for prt in unit.ports:
            m = re.search(r'(\[[^\]]*\])', prt.type)
            ports.append((prt.name, prt.direction, m.group(1) if m else ''))
        lib = library_of_file(self._project(), path, self.bd.library)
        if parsed.errors:
            self.log.addItem(f'{os.path.basename(path)}: {len(parsed.errors)} parse error(s); ports may be incomplete')
        return {'library': lib, 'unit': unit.name, 'ports': ports, 'params': unit.params, 'source': path}

    def _include_dirs(self) -> list[str]:
        """Include folders of the diagram's library (for parsing HDL files and the syntax check)."""
        proj = self._project()
        lib = proj.library(self.bd.library) if proj else None
        return lib.include_dirs if lib else []

    def _interface(self, inst: BdInstance) -> dict | None:
        """Ports and parameters of an instance's module. As the legacy tool reconciles an instance with its
        child view: the unit's default view when it is a state / block diagram (its model in an open
        editor window, with the changes not saved yet, else the saved view), else its HDL; a unit
        outside the project: its source file."""
        proj = self._project()
        du = proj.find_unit(inst.unit, prefer=proj.library(inst.library)) if proj else None
        if du is not None:
            info = self._component_info(inst.library, inst.unit, du)
            child = self._child_ports(du)
            if child is not None:
                info['ports'] = child
            return info
        if inst.source and os.path.exists(inst.source):
            from hdl.parser import parse_file
            u = next((u for u in parse_file(inst.source, self._include_dirs()).units if u.name == inst.unit), None)
            if u is not None:
                ports = [(p.name, p.direction, (re.search(r'(\[[^\]]*\])', p.type) or [''])[0]) for p in u.ports]
                return {'library': inst.library, 'unit': u.name, 'ports': ports, 'params': u.params,
                        'source': inst.source}
        return None

    def _child_ports(self, du) -> list[tuple[str, str, str]] | None:
        """(name, mode, bounds) of the ports of a unit whose default view is a state or block diagram:
        from the editor window that has it open, else from the saved view; None for other units."""
        view = next((v for v in du.views if du.is_default(v)), None) or du.graphic_view()
        if view is None or view.kind not in ('fsm', 'bd'):
            return None
        model = None
        mgr = self.context.manager if self.context is not None else None
        if mgr is not None:
            from project.generate import native_path
            ed = mgr.editors.get(native_path(du.library, du.name, view.name, view.kind))
            model = next((m for m in (getattr(ed, 'view', None), getattr(ed, 'bd', None)) if hasattr(m, 'signals')),
                         None)
        if model is None:
            try:
                from project.generate import load_view
                model = load_view(du.library, du, view)
            except Exception:
                return None
        self._child_types = {s.name: s.type for s in model.signals}
        return [(s.name, s.mode, s.bounds) for s in model.signals if s.mode in ('input', 'output', 'inout')]

    def _symbol_params(self, inst: BdInstance) -> dict[str, list[tuple[str, str]]]:
        """{'symbol': the symbol's Parameters table, 'all': every parameter the module declares},
        each with its default declaration as written."""
        info = self._interface(inst)
        all_params = list(info['params']) if info else []
        symbol = []
        du = self._unit_of(inst)
        sym = next((v for v in du.views if v.kind == 'symbol'), None) if du is not None else None
        if sym is not None and sym.path.endswith('.sb'):
            try:
                from formats.import_sm import symbol_parameters
                symbol = symbol_parameters(sym.path)
            except Exception:
                symbol = []
        known = {n for n, _ in all_params}
        all_params += [p for p in symbol if p[0] not in known]
        return {'symbol': symbol or all_params, 'all': all_params}

    def place_at(self, pos: QPointF):
        """A click with an add tool at `pos`: place the pending component, a port (connected when its
        stub tip is on a net end, a component port or a net; else free and unnamed), a generate
        frame or a new empty embedded block. The new object is selected; Add commands stay active
        unless used "once".
        """
        mode = self.scene.mode
        bd = self.bd
        if mode in ('port_in', 'port_out', 'port_inout', 'embedded'):
            # where the preview is: the cursor on the port's stub tip / the block's bottom-left
            pos = QPointF(*self.scene.placement_origin(mode, pos))
        if mode == 'component' and self._pending_component:
            self._place_component(self._pending_component, pos)
            self.set_mode('select')
            return
        elif mode in ('port_in', 'port_out', 'port_inout'):
            pmode = {'port_in': 'input', 'port_out': 'output', 'port_inout': 'inout'}[mode]
            n = len(bd.port_ios)
            if not self._add_port_on_net(pos, pmode):
                # In open space: a free port. As in the legacy tool an unconnected port has no name; it takes
                # the name of the net it gets connected to (and is not a module port until then).
                bd.port_ios.append(BdPortIo(self._new_id('p'), '', pmode, pos.x(), pos.y()))
            # As the legacy tool does: the new port is selected and Add Port stays active (the
            # preview follows the cursor again) until Esc, unless the command acts once
            self._reload_scene()
            self.scene.clearSelection()
            for p in bd.port_ios[n:]:
                it = self.scene.items_by_id.get(p.id)
                if it is not None:
                    it.setSelected(True)
            self.changed()
            if self._once:
                self.set_mode('select')
            return
        elif mode in ('frame', 'frame_if', 'frame_else'):
            if not self._add_frame(mode, pos):
                return
        elif mode == 'panel':
            self.add_panel(pos)
            if self._once:
                self.set_mode('select')
            return
        elif mode == 'comment':
            # Add > Comment Text: a free text, typed at once; it stays where it was clicked
            self.add_comment(pos)
            if self._once:
                self.set_mode('select')
            return
        elif mode == 'embedded':
            # an empty block, as in the legacy tool: double-click it to create its view (Text). As the legacy tool
            # 2021.1 does, the new block is selected and Add Embedded Block stays active.
            n = max((e.number for e in bd.embedded), default=0) + 1
            eb = BdEmbedded(self._new_id('e'), f'eb{n}', n, '', pos.x(), pos.y(), *EMB_NEW_SIZE)
            bd.embedded.append(eb)
            self._reload_scene()
            self.scene.clearSelection()
            it = self.scene.items_by_id.get(eb.id)
            if it is not None:
                it.setSelected(True)
            self.changed()
            if self._once:
                self.set_mode('select')
            return
        else:
            return
        self._reload_scene()
        self.set_mode('select')

    def _add_port_on_net(self, pos: QPointF, pmode: str) -> bool:
        """Add a port at pos (where its faded preview is) if the port's wire end - the tip of its
        stub, as drawn on the preview, not its middle - is on something it can attach to. No
        name is asked: the port takes the net's name.
          a dangling net end - the end goes onto the tip;
          a component port   - a net from the component port to the tip, named after the
                               component port's net, or the component port itself;
          the body of a net  - a junction dot on the net, joined to the tip.
        The port stays where it is put; it then faces its net (port_side() follows the net).
        Returns False when the tip is on nothing (the caller adds a free, unnamed port)."""
        bd, sc = self.bd, self.scene
        pio = BdPortIo(self._new_id('p'), '', pmode, pos.x(), pos.y())
        tip = QPointF(*sc.port_edge(pio))       # no net yet: the side the preview shows
        # 1) a dangling net end
        hit = self._dangling_end_at(tip)
        if hit is not None:
            w, which, k = hit
            bd.port_ios.append(pio)
            _shift_end(w, which, tip.x() - w.points[k][0], tip.y() - w.points[k][1])
            w.points = _simplify(w.points)
            setattr(w, which, f'pio:{pio.id}')
            self._port_takes_net(pio, w.net)
            self._turn_port_to_end(pio, w.points[k])
            return True
        # 2) a component port
        pin_hit = sc.pin_at(tip)
        if pin_hit is not None and pin_hit[2] is not None:
            ref, pt, pin, _ = pin_hit
            net = pin.net or pin.name
            bd.port_ios.append(pio)
            pin.net = net
            w = BdWire(self._new_id('w'), net, _route([pt.x(), pt.y()], [], [tip.x(), tip.y()]), ref, f'pio:{pio.id}')
            w.show_text = False                 # the name is shown on the port
            bd.wires.append(w)
            self._ensure_port(net, pmode, pin.bounds)
            pio.name = net
            return True
        # 3) the body of a net
        net_hit = sc.net_at(tip)
        if net_hit is not None:
            net_wire = next(x for x in bd.wires if net_hit[0] == f'net:{x.id}')
            bd.port_ios.append(pio)
            self._attach_port_to_net(pio, tip, net_hit[1], net_wire)
            return True
        return False

    def _add_frame(self, mode: str, pos: QPointF) -> bool:
        """New generate frame at pos. FOR: "name: [left:right]" (instances inside become
        instance arrays); IF: "name: `ifdef MACRO" or "name: (expression)"; ELSE: pairs with
        an IF frame of the same name."""
        bd = self.bd
        n = max((f.number for f in bd.frames), default=0) + 1
        if mode == 'frame_else':
            names = [f.name for f in bd.frames if f.kind == 'if'
                     and not any(e.kind == 'else' and e.name == f.name for e in bd.frames)]
            if not names:
                QMessageBox.information(self, 'Add Frame (ELSE)', 'Add an IF frame first: an ELSE frame '
                                        'is the alternative of the IF frame with the same name.')
                return False
            name, ok = QInputDialog.getItem(self, 'Add Frame (ELSE)', 'Alternative of IF frame:', names, 0, False)
            if not ok:
                return False
            bd.frames.append(BdFrame(self._new_id('f'), 'else', name, '`else' if next(
                f for f in bd.frames if f.kind == 'if' and f.name == name).spec.startswith('`') else '',
                n, pos.x(), pos.y()))
            return True
        default = f'g{n - 1}: [7:0]' if mode == 'frame' else f'g{n - 1}: `ifdef MACRO'
        text, ok = QInputDialog.getText(self, 'Add Frame (FOR)' if mode == 'frame' else 'Add Frame (IF)',
                                        'Frame title (name: range)' if mode == 'frame'
                                        else 'Frame title (name: `ifdef MACRO or name: (condition))', text=default)
        parsed = self._parse_frame_title(text) if ok else None
        if parsed is None:
            return False
        bd.frames.append(BdFrame(self._new_id('f'), 'for' if mode == 'frame' else 'if', parsed[0], parsed[1], n,
                                 pos.x(), pos.y()))
        return True

    def _parse_frame_title(self, text: str) -> tuple[str, str] | None:
        """"name: spec" -> (name, spec); None (with a status message) when the text is not of that form."""
        m = re.match(r'\s*([A-Za-z_][\w$]*)\s*:\s*(.*\S)\s*$', text or '')
        if m is None:
            self.statusBar().showMessage('A frame title is "name: range" or "name: condition"', 5000)
            return None
        return m.group(1), m.group(2)

    def frame_properties(self, fr: BdFrame):
        """BD Object Properties - Frames (double-click the title, Alt+Enter or the popup menu)."""
        from .bd_dialogs import FramePropertiesDialog
        if_names = [f.name for f in self.bd.frames if f.kind == 'if' and f is not fr]
        dlg = FramePropertiesDialog(fr, if_names, self, apply=lambda v: self._apply_frame(fr, v))
        if dlg.exec() and not self.scene.readonly:
            self._apply_frame(fr, dlg.values())

    def _apply_frame(self, fr: BdFrame, v: dict):
        """Write the frame dialog values `v` into frame `fr` after checking them (a valid label, an IF
        condition, an IF frame for an ELSE frame); an ELSE frame stays paired with its IF frame.
        """
        if self.scene.readonly:
            return
        if not re.fullmatch(r'[A-Za-z_][\w$]*', v['name']):
            QMessageBox.warning(self, 'Frames', f'"{v["name"]}" is not a valid label')
            return
        if v['kind'] == 'if' and not v['spec']:
            QMessageBox.warning(self, 'Frames', 'An IF frame needs a condition')
            return
        if v['kind'] == 'else' and not any(f.kind == 'if' and f.name == v['name'] for f in self.bd.frames):
            QMessageBox.warning(self, 'Frames', f'No IF frame labelled "{v["name"]}" for this ELSE frame')
            return
        old = (fr.kind, fr.name)
        if v['kind'] == 'else':                 # an ELSE follows its IF frame's form
            twin = next(f for f in self.bd.frames if f.kind == 'if' and f.name == v['name'])
            v['spec'] = '`else' if twin.spec.startswith('`') else ''
        if all(getattr(fr, k) == val for k, val in v.items()):
            return
        for k, val in v.items():
            setattr(fr, k, val)
        if old[0] == 'if':                      # keep the ELSE frame paired with its IF frame
            for e in self.bd.frames:
                if e.kind == 'else' and e.name == old[1]:
                    e.name = fr.name
        self._reload_scene()

    def edit_frame(self, fr: BdFrame):
        """Edit a frame title ("name: spec") in a small dialog."""
        if self.scene.readonly:
            return
        text, ok = QInputDialog.getText(self, 'Frame', 'Frame title:', text=fr.title)
        parsed = self._parse_frame_title(text) if ok else None
        if parsed is None or parsed == (fr.name, fr.spec):
            return
        old = fr.name
        fr.name, fr.spec = parsed
        for e in self.bd.frames:                # keep the ELSE frame paired with its IF frame
            if fr.kind == 'if' and e.kind == 'else' and e.name == old:
                e.name = fr.name
        self._reload_scene()

    def _ensure_port(self, name: str, mode: str, bounds: str = ''):
        """Make `name` a module port of `mode` in the signal list (created when missing)."""
        sig = next((s for s in self.bd.signals if s.name == name), None)
        if sig is None:
            self.bd.signals.append(Sig(name, mode, 'wire', bounds))
        else:
            sig.mode = mode
            sig.bounds = sig.bounds or bounds

    def _reload_scene(self):
        """Rebuild the scene from the model after a command, and make the command one undo step."""
        self.scene.load(self.bd)
        self.signals_tab.set_rows(self.bd.signals, self.bd.signals_sheet)
        self.changed()
        self.undo_stack.flush()        # each command is its own undo step

    def _add_component(self, info: dict, pos: QPointF) -> BdInstance:
        """Create an instance of the component described by `info` at `pos` (named after the unit,
        then unit1, unit2 ... as the legacy tool does), with its ports laid out from its symbol when it has one.
        """
        unit, ports = info['unit'], info['ports']
        names = {i.name for i in self.bd.instances}
        # as legacy names a dropped component: the unit name, then unit1, unit2, ...
        name, k = unit, 0
        while name in names:
            k += 1
            name = f'{unit}{k}'
        inst = BdInstance(self._new_id('i'), name, info['library'], unit, x=pos.x(), y=pos.y(),
                          source=info.get('source', ''))
        self._layout_pins(inst, ports)
        if info.get('symbol'):
            self._symbol_layout(inst, info['symbol'])
        if not ports:
            self.log.addItem(f'{info["library"]}.{unit}: interface not found, the instance has no pins')
        self.bd.instances.append(inst)
        return inst

    @staticmethod
    def _symbol_layout(inst: BdInstance, path: str):
        """Body size and port places from the unit's symbol (.sb), as the legacy tool instantiates a
        component (the generic layout of _layout_pins is the fallback). The name lines start at
        the top of the body, 1800 units left of its middle (as the legacy tool placed them)."""
        try:
            from formats.import_bd import symbol_geometry
            geo = symbol_geometry(path)
        except Exception:
            geo = None
        if geo is None:
            return
        w, h, ports = geo
        old = {p.name: p for p in inst.pins}
        inst.w, inst.h = w, h
        inst.pins = []
        for name, mode, bounds, order, x, y, side in ports:
            # the triangle sits on the body edge (a port shape may be wider, e.g. with a bubble)
            if side == 'left':
                x = -PIN_HALF
            elif side == 'right':
                x = w + PIN_HALF
            elif side == 'top':
                y = -PIN_HALF
            else:
                y = h + PIN_HALF
            prev = old.get(name)
            inst.pins.append(BdPin(name, mode, prev.net if prev else '', order or len(inst.pins) + 1,
                                   inst.x + x, inst.y + y, side, bounds or (prev.bounds if prev else '')))
        inst.text_pos = [w / 2 - 1800 / 75, 0.0]

    @staticmethod
    def _layout_pins(inst: BdInstance, ports: list[tuple[str, str, str]]):
        """Inputs/inouts on the left, outputs on the right, 10 units apart."""
        ins = [p for p in ports if p[1] != 'output']
        outs = [p for p in ports if p[1] == 'output']
        longest = max([len(p[0]) for p in ports] + [len(inst.unit), 8])
        inst.w = _snap(max(140, longest * 12 + 40))
        inst.h = _snap(max(len(ins), len(outs)) * PIN_STEP + 3 * GRID)
        old = {p.name: p for p in inst.pins}
        inst.pins = []
        for side, group in (('left', ins), ('right', outs)):
            for i, (pname, mode, bounds) in enumerate(group):
                x = inst.x - PIN_HALF if side == 'left' else inst.x + inst.w + PIN_HALF
                prev = old.get(pname)
                inst.pins.append(BdPin(pname, mode, prev.net if prev else '', len(inst.pins) + 1, x,
                                       inst.y + 2 * GRID + i * PIN_STEP, side, bounds))

    # -- right-click menu ------------------------------------------------------------------
    def context_menu(self, item, screen_pos, scene_pos):
        """Right click on the diagram: the popup menu of the object under the cursor (component, net,
        port, frame, embedded block) or of the empty diagram.
        """
        m = QMenu(self)
        ro = self.scene.readonly
        if isinstance(item, InstanceItem) and item.pin_at(scene_pos) is not None:
            self._pin_menu(m, item.obj, ro)
        elif isinstance(item, InstanceItem):
            self._component_menu(m, item.obj, scene_pos, ro)
        elif isinstance(item, WireItem):
            self._net_menu(m, item, scene_pos, ro)
        elif isinstance(item, PortIoItem):
            self._port_menu(m, item, scene_pos, ro)
        elif isinstance(item, FrameItem):
            fr = item.obj
            for text, fn, key in (('Cu&t', self.cut, 'Ctrl+X'), ('&Copy', self.copy, 'Ctrl+C'),
                                  ('&Paste', lambda: self.paste(scene_pos), 'Ctrl+V'),
                                  ('&Delete', self.delete_selected, 'Del')):
                a = m.addAction(text, fn)
                a.setShortcut(QKeySequence(key)); a.setShortcutVisibleInContextMenu(True)
                a.setEnabled(text == '&Copy' or (not ro and (text != '&Paste' or bool(self._clipboard))))
            m.addSeparator()
            self._menu_item(m, '&Appearance...', lambda: self._small_dialog('appearance', fr))
            a = m.addAction('&Object Properties...', lambda: self.frame_properties(fr))
            a.setShortcut(QKeySequence('Alt+Return')); a.setShortcutVisibleInContextMenu(True)
        elif isinstance(item, TextBlockItem):
            self._text_block_menu(m, item.obj, ro)
        elif isinstance(item, EmbeddedItem):
            if item.in_text(scene_pos):
                self._embedded_text_menu(m, item, scene_pos, ro)
            else:
                self._embedded_menu(m, item, scene_pos, ro)
        else:
            self._diagram_menu(m, ro)
        m.exec(screen_pos)

    def _command(self, m: QMenu, text: str, key: str, shortcut: str = '', enabled: bool = True):
        """A popup entry that runs the window's command `key` (toolbar_actions), with its shortcut
        shown; disabled when the window has no such command or it is disabled."""
        a = self.toolbar_actions.get(key)
        return self._menu_item(m, text, a.trigger if a is not None else None, shortcut,
                               enabled and (a is None or a.isEnabled()))

    def _label(self, text: str):
        """Name the next undo step after a popup command (as the legacy popup shows "Undo (Cut)")."""
        self.undo_stack.pending_label = text.replace('&', '').replace('...', '').strip()

    def _submenu(self, m: QMenu, title: str, entries: list) -> QMenu:
        """A sub-menu of (text, function or None, shortcut) entries; '-' is a separator. Entries
        without a function are shown disabled (not in HDL Studio yet), as the legacy layout has them."""
        sub = m.addMenu(title)
        for e in entries:
            if e == '-':
                sub.addSeparator()
                continue
            text, fn, key = (tuple(e) + ('',))[:3]
            a = sub.addAction(text)
            if fn is not None:
                a.triggered.connect(lambda checked=False, t=f'{title} {text}': self._label(t))
                a.triggered.connect(fn)
            a.setEnabled(fn is not None)
            if key:
                a.setShortcut(QKeySequence(key)); a.setShortcutVisibleInContextMenu(True)
        return sub

    def _autoroute_menu(self, m: QMenu, ro: bool):
        """Autoroute sub-menu (component, embedded block)."""
        self._submenu(m, 'A&utoroute', [('Autoconnect', None), ('Autobundle', None),
                                        ('Connect By Name', None if ro else self.connect_by_name),
                                        ('Autoroute', None, 'Ctrl+R'), ('Autoroute Options...', None)])

    def _diagram_menu(self, m: QMenu, ro: bool):
        """The popup menu of the empty diagram, entries and order as in the legacy tool."""
        self._command(m, 'Signals Table', 'signals_table')
        self._command(m, 'Open Up', 'open_up', 'Ctrl+Shift+O')
        m.addSeparator()
        u, r = self.undo_stack.undo_label(), self.undo_stack.redo_label()
        self._command(m, f'Undo ({u})' if u else 'Undo', 'undo', 'Ctrl+Z')
        self._command(m, f'Redo ({r})' if r else 'Redo', 'redo', 'Ctrl+Y')
        m.addSeparator()
        self._command(m, 'Paste', 'paste', 'Ctrl+V', bool(self._clipboard) and not ro)
        m.addSeparator()
        self._command(m, 'View Area', 'view_area', 'Shift+Home')
        self._command(m, 'Zoom In', 'zoom_in', 'Shift+Up')
        self._command(m, 'Zoom Out', 'zoom_out', 'Shift+Down')
        self._command(m, 'Zoom Last', 'zoom_last')
        m.addSeparator()
        self._command(m, 'View Page', 'fit')
        self._command(m, 'Print Page...', 'print')
        m.addSeparator()
        self._menu_item(m, 'Object Visibility...', self.object_visibility)
        m.addSeparator()
        self._menu_item(m, 'Update Interface...', self.diagram_update_interface)
        self._menu_item(m, 'Update Where Used...', self.update_where_used,
                        enabled=self.context is not None)

    def _text_block_menu(self, m: QMenu, tb, ro: bool):
        """Popup of the Declarations / Compiler Directives block, as the legacy tool:
        Declarations: Appearance... / Show Text / Hide Text / Object Properties...;
        Compiler Directives: Compiler Directives... / Show Text / Hide Text / Appearance...."""
        if tb.id == 'decl':
            self._menu_item(m, 'Appearance...')
            self._menu_item(m, 'Show Text', lambda: self._set_text_block(tb, contents=True),
                            enabled=not ro and not tb.contents)
            self._menu_item(m, 'Hide Text', lambda: self._set_text_block(tb, visible=False), enabled=not ro)
            self._menu_item(m, 'Object Properties...', self._empty_properties, 'Alt+Return')
        else:
            self._menu_item(m, 'Compiler Directives...', self.compiler_directives_dialog)
            self._menu_item(m, 'Show Text')                 # every part is shown already
            self._menu_item(m, 'Hide Text', lambda: self._set_text_block(tb, visible=False), enabled=not ro)
            self._menu_item(m, 'Appearance...')

    def _set_text_block(self, tb, **values):
        """Show / hide a text block (or the Declarations contents)."""
        for k, v in values.items():
            setattr(tb, k, v)
        self._reload_scene()

    def _empty_properties(self):
        """Object Properties of the Declarations block: the legacy tool opens BD Object Properties with no
        object category of its own (only User Declarations / User Properties)."""
        from .bd_dialogs import ObjectPropertiesDialog
        dlg = ObjectPropertiesDialog('', self)
        dlg.setWindowTitle('BD Object Properties')
        dlg.exec()

    def compiler_directives_dialog(self):
        """Compiler Directives... (popup of the Compiler Directives block): the legacy "Verilog Compiler
        Directives" dialog: Pre-, Post- and End-Module Directives, and Visible (the block on the diagram)."""
        from PySide6.QtWidgets import QPlainTextEdit
        bd = self.bd
        tb = next(b for b in bd.text_blocks if b.id == 'dirs')
        dlg = QDialog(self)
        dlg.setWindowTitle('Verilog Compiler Directives')
        lay = QVBoxLayout(dlg)
        top = QHBoxLayout(); top.addWidget(QLabel('Compiler Directives:')); top.addStretch(1)
        vis = QCheckBox('Visible'); vis.setChecked(tb.visible); top.addWidget(vis)
        lay.addLayout(top)
        boxes = {}
        for title, attr in (('Pre-Module Directives', 'pre_module_directives'),
                            ('Post-Module Directives', 'post_module_directives'),
                            ('End-Module Directives', 'end_module_directives')):
            g = QGroupBox(title); gl = QVBoxLayout(g)
            ed = QPlainTextEdit(getattr(bd, attr)); ed.setLineWrapMode(QPlainTextEdit.NoWrap)
            ed.setFont(QFont('Courier New', 9)); ed.setReadOnly(self.scene.readonly)
            gl.addWidget(ed); boxes[attr] = ed
            lay.addWidget(g, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Help)
        bb.button(QDialogButtonBox.Help).setEnabled(False)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.resize(421, 557)
        if dlg.exec() and not self.scene.readonly:
            changed = vis.isChecked() != tb.visible
            tb.visible = vis.isChecked()
            for attr, ed in boxes.items():
                if ed.toPlainText() != getattr(bd, attr):
                    setattr(bd, attr, ed.toPlainText()); changed = True
            if changed:
                self._reload_scene()

    def object_visibility(self):
        """Object Visibility... (diagram popup): the legacy "Object Visibility Settings" list: Declarations
        shows the declared ports and diagram signals in the Declarations block, Compiler Directives the
        Compiler Directives block."""
        dlg = QDialog(self)
        dlg.setWindowTitle('Object Visibility Settings')
        lay = QHBoxLayout(dlg)
        lst = QListWidget()
        blocks = {b.id: b for b in self.bd.text_blocks}
        # Declarations: its sections (ports / diagram signals); Compiler Directives: the whole block
        for text, on in (('Declarations', blocks['decl'].visible and blocks['decl'].contents),
                         ('Compiler Directives', blocks['dirs'].visible)):
            it = QListWidgetItem(text)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if on else Qt.Unchecked)
            lst.addItem(it)
        lay.addWidget(lst, 1)
        bb = QDialogButtonBox(Qt.Vertical)
        bb.setStandardButtons(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Help)
        bb.button(QDialogButtonBox.Help).setEnabled(False)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.resize(380, 284)
        if dlg.exec() and not self.scene.readonly:
            decl_on = lst.item(0).checkState() == Qt.Checked
            dirs_on = lst.item(1).checkState() == Qt.Checked
            if decl_on:
                blocks['decl'].visible = True
            blocks['decl'].contents = decl_on
            blocks['dirs'].visible = dirs_on
            self._reload_scene()

    def diagram_update_interface(self):
        """Update Interface... (diagram popup): the legacy "Update Interface" dialog for the diagram itself:
        the selected component instances are checked against their interface; with none selected it
        says so (the diagram's own ports are its interface in HDL Studio)."""
        insts = self._sel(InstanceItem)
        if len(insts) == 1:
            return self.update_interface_dialog(insts[0])
        dlg = QDialog(self)
        dlg.setWindowTitle('Update Interface')
        lay = QVBoxLayout(dlg)
        top = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel('Interfaces are IDENTICAL.'))
        info = QPlainTextEdit(f'No instances selected on {self.bd.library}/{self.bd.unit}/{self.bd.view}.\n\n'
                              'Reconcile checks the interface of this view with\nthe component interface.')
        info.setReadOnly(True)
        left.addWidget(info, 1)
        top.addLayout(left, 3)
        right = QVBoxLayout()
        lab = QLabel('Instances'); lab.setEnabled(False)
        right.addWidget(lab)
        right.addWidget(QListWidget(), 1)
        opts = QPushButton('Options...'); opts.setEnabled(False)
        right.addWidget(opts)
        top.addLayout(right, 1)
        lay.addLayout(top, 1)
        from PySide6.QtWidgets import QRadioButton
        r1 = QRadioButton('Make active view consistent with its interface'); r1.setEnabled(False)
        r2 = QRadioButton('Make the component interface consistent with the active view')
        r2.setChecked(True); r2.setEnabled(False)
        lay.addWidget(r1); lay.addWidget(r2)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply |
                              QDialogButtonBox.Help)
        bb.button(QDialogButtonBox.Help).setEnabled(False)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.resize(550, 400)
        dlg.exec()

    def update_where_used(self):
        """Update Where Used... (diagram popup): the legacy "Where Used - Search" scope question, then the
        diagrams of the chosen libraries that instantiate this unit are listed."""
        from PySide6.QtWidgets import QRadioButton
        proj = self._project()
        if proj is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle('Where Used - Search')
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel('Please specify the scope for the updates:'))
        box = QGroupBox('Look in:'); h = QHBoxLayout(box)
        radios = QVBoxLayout()
        opts = [QRadioButton(t) for t in ('The libraries containing the specified objects only',
                                          'The default library only', 'All project libraries',
                                          'Specified libraries')]
        opts[0].setChecked(True)
        for r in opts:
            radios.addWidget(r)
        radios.addStretch(1)
        h.addLayout(radios, 1)
        libs = QListWidget()
        for l in proj.libraries:
            it = QListWidgetItem(l.name)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            libs.addItem(it)
        libs.setEnabled(False)
        opts[3].toggled.connect(libs.setEnabled)
        h.addWidget(libs, 1)
        lay.addWidget(box, 1)
        bb = QDialogButtonBox()
        start = bb.addButton('Start...', QDialogButtonBox.AcceptRole)
        bb.addButton(QDialogButtonBox.Cancel)
        hb = bb.addButton(QDialogButtonBox.Help); hb.setEnabled(False)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.resize(511, 309)
        if not dlg.exec():
            return
        own = proj.library(self.bd.library)
        if opts[0].isChecked() or opts[1].isChecked():
            chosen = [own] if own is not None else []
        elif opts[2].isChecked():
            chosen = list(proj.libraries)
        else:
            names = {libs.item(i).text() for i in range(libs.count()) if libs.item(i).checkState() == Qt.Checked}
            chosen = [l for l in proj.libraries if l.name in names]
        mgr = self.context.manager
        users = []
        for lib in chosen:
            if not lib.scanned:
                lib.scan(proj.cache, proj.progress)
            for du in lib.units.values():
                # children_of: (instance, unit, library, generate path) below the unit
                if any(c[1] == self.bd.unit for c in (mgr.children_of(du) or [])):
                    users.append(f'{lib.name}/{du.name}')
        QMessageBox.information(self, 'Where Used', '\n'.join(sorted(users)) if users else
                                f'{self.bd.unit} is not used in the libraries searched.')

    def _embedded_menu(self, m: QMenu, item: 'EmbeddedItem', pos: QPointF, ro: bool):
        """The popup menu of an embedded block (on its yellow frame), entries and order as in the legacy
        tool. On a connection point it also has Change Mode, which flips the net's direction (a net
        leaving the block is an output, one entering it an input)."""
        eb = item.obj
        self._submenu(m, '&Open', [('Embedded Text', lambda: self.edit_embedded_text_window(eb))])
        self._menu_item(m, 'Change Embedded &View...', lambda: self.change_embedded_view(eb),
                        enabled=not ro and item.text_rect() is not None)
        end = item.end_at(pos)
        if end is not None:
            w, which = end
            cm = m.addMenu('Change &Mode')
            cm.setEnabled(not ro)
            for text, out in (('&In', False), ('&Out', True)):
                a = cm.addAction(text, lambda out=out: self.set_embedded_port_mode(w, which, out))
                a.setCheckable(True)
                a.setChecked((which == 'start') == out)
        m.addSeparator()
        turn = None if ro else self.turn_embedded
        self._submenu(m, '&Rotate', [(t, turn and (lambda t=t: turn(eb, int(t)))) for t in ('90', '180', '270')])
        self._submenu(m, '&Flip', [('Vertical', turn and (lambda: turn(eb, 0, 'vertical'))),
                                   ('Horizontal', turn and (lambda: turn(eb, 0, 'horizontal')))])
        m.addSeparator()
        self._edit_items(m, pos, ro, can_copy=True)
        m.addSeparator()
        self._menu_item(m, 'C&onnect', None, 'Alt+C')
        self._menu_item(m, 'Disconnect', lambda: self.disconnect_embedded(eb), 'Shift+Alt+C', not ro)
        self._autoroute_menu(m, ro)
        m.addSeparator()
        self._submenu(m, 'S&hape', [('Editing Shape', None), ('Autowhisker', None), ('Autoshapes...', None)])
        self._menu_item(m, 'Appea&rance...')
        self._menu_item(m, 'Show Te&xt', lambda: self._show_embedded_text(eb), enabled=not ro)
        m.addSeparator()
        self._submenu(m, 'Re-&level', [('Add Hierarchy...', None)])
        self._menu_item(m, 'Update &Interface...')
        self._menu_item(m, '&Object Properties...', lambda: self.embedded_properties(eb), 'Alt+Return')

    def _embedded_text_menu(self, m: QMenu, item: 'EmbeddedItem', pos: QPointF, ro: bool):
        """The popup menu of an embedded block's Text view (the white box), as in the legacy tool."""
        eb = item.obj
        self._menu_item(m, '&Copy', self.copy, 'Ctrl+C')
        self._menu_item(m, '&Paste', lambda: self.paste(pos), 'Ctrl+V', bool(self._clipboard) and not ro)
        self._submenu(m, 'Paste &Special', [('Paste from system clipboard', None)])
        m.addSeparator()
        self._menu_item(m, 'Appea&rance...')
        self._menu_item(m, '&Hide Text')
        self._menu_item(m, 'Send to &Editor', lambda: self.edit_embedded_text_window(eb))
        self._menu_item(m, 'Finish Edit')
        self._menu_item(m, 'Finish All Edits')
        self._menu_item(m, '&Object Properties...', lambda: self.embedded_properties(eb), 'Alt+Return')

    def _show_embedded_text(self, eb: BdEmbedded):
        """Show Text (embedded block): its name and number in the frame."""
        if not eb.show_name:
            eb.show_name = True
            self._reload_scene()

    def disconnect_embedded(self, eb: BdEmbedded):
        """Disconnect (embedded block): as the legacy tool, the nets stay where they are; their ends on the
        block are only detached (they show the red unconnected mark)."""
        ref = f'emb:{eb.id}'
        for w in self.bd.wires:
            for which in ('start', 'end'):
                if getattr(w, which) == ref:
                    setattr(w, which, '')
        self._reload_scene()

    def turn_embedded(self, eb: BdEmbedded, turn: int = 0, flip: str = ''):
        """Rotate (90 / 180 / 270, clockwise) or Flip an embedded block about its centre, as the legacy tool:
        the block turns, the net ends on its edges go round with it; its Text view stays where it is."""
        cx, cy = eb.x + eb.w / 2, eb.y + eb.h / 2
        old_x, old_y = eb.x, eb.y

        def move(x, y):
            dx, dy = x - cx, y - cy
            if flip == 'vertical':
                dy = -dy
            elif flip == 'horizontal':
                dx = -dx
            for _ in range(turn // 90):
                dx, dy = -dy, dx
            return [cx + dx, cy + dy]

        ref = f'emb:{eb.id}'
        for w in self.bd.wires:
            for which, k in (('start', 0), ('end', -1)):
                if getattr(w, which) == ref and w.points:
                    w.points[k] = move(*w.points[k])
        if (turn // 90) % 2:
            eb.w, eb.h = eb.h, eb.w
            eb.x, eb.y = cx - eb.w / 2, cy - eb.h / 2
        if eb.text_box:                         # the Text view keeps its place on the diagram
            eb.text_box = [eb.text_box[0] + old_x - eb.x, eb.text_box[1] + old_y - eb.y, *eb.text_box[2:]]
        self._reload_scene()

    def edit_embedded_text_window(self, eb: BdEmbedded):
        """Open > Embedded Text / Send to Editor: the block's HDL in a text editor window (the legacy tool
        opens it in its text editor); OK writes it back into the block."""
        dlg = QDialog(self)
        dlg.setWindowTitle(f'{self.bd.unit}_{eb.name} (Embedded Text)')
        lay = QVBoxLayout(dlg)
        ed = QPlainTextEdit(eb.text.strip('\n'))
        ed.setFont(QFont('Courier New', 10))
        ed.setLineWrapMode(QPlainTextEdit.NoWrap)
        ed.setReadOnly(self.scene.readonly)
        lay.addWidget(ed, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.resize(966, 759)
        if dlg.exec() and not self.scene.readonly and ed.toPlainText() != eb.text.strip('\n'):
            eb.text = ed.toPlainText()
            if eb.text_box is None:
                w, h = max(eb.w, 60), max(eb.h, 30)
                eb.text_box = [13, 13, w - 26, h - 26]
            self._reload_scene()

    def embedded_properties(self, eb: BdEmbedded):
        """Object Properties of an embedded block: the legacy "BD Object Properties - Embedded Blocks"."""
        from .bd_dialogs import EmbeddedPropertiesDialog
        dlg = EmbeddedPropertiesDialog(eb, self)
        if self.scene.readonly:
            dlg.stack.setEnabled(False)
        dlg.exec()
        if dlg.applied and not self.scene.readonly:
            self._reload_scene()

    def _component_menu(self, m: QMenu, inst: BdInstance, pos: QPointF, ro: bool):
        """The component popup menu, entries and order as in the legacy tool (entries HDL Studio does not have yet are
        disabled).
        """
        du = self._unit_of(inst)
        views = [v for v in du.views if v.kind != 'symbol'] if du is not None else []
        # the views as the legacy tool lists them: "* unit(BLOCK_DIAGRAM)/struct.bd", * on the default view
        def view_text(v) -> str:
            kind = f'{(v.language or "verilog").upper()}_TEXT' if v.kind == 'text' else                 v.label.upper().replace(' ', '_')
            return f'{"* " if du.is_default(v) else ""}{du.name}({kind})/{os.path.basename(v.path)}'
        open_as = m.addMenu('Open &As')
        for v in views:
            open_as.addAction(view_text(v), lambda v=v: self.context.manager.open_view(du, v))
        open_as.addSeparator()
        open_as.addAction('New View...').setEnabled(False)
        open_as.addAction('Interface').setEnabled(False)
        open_as.setEnabled(du is not None and self.context is not None)
        if len(views) > 1:                  # the legacy tool lists it only for a unit with several views
            cdv = m.addMenu('Change Default &View')
            for v in views:
                cdv.addAction(view_text(v), lambda v=v: self._change_default_view(du, v))
            cdv.setEnabled(du.library.writable)
        on = None if ro else (lambda turn=0, flip='': self.turn_component(inst, turn, flip))
        self._submenu(m, '&Rotate', [(t, on and (lambda t=t: self.turn_component(inst, int(t))))
                                     for t in ('90', '180', '270')])
        self._submenu(m, '&Flip', [('Vertical', on and (lambda: self.turn_component(inst, 0, 'vertical'))),
                                   ('Horizontal', on and (lambda: self.turn_component(inst, 0, 'horizontal')))])
        m.addSeparator()
        self._edit_items(m, pos, ro, can_copy=True)
        m.addSeparator()
        self._menu_item(m, 'C&onnect', None if ro else (lambda: self.connect_component(inst)), 'Alt+C')
        self._menu_item(m, 'Disconnect', lambda: self.disconnect(inst), 'Shift+Alt+C', not ro)
        self._autoroute_menu(m, ro)
        self._menu_item(m, 'Add Signal Stu&bs...', lambda: self._ask_port_kinds('Add Signal Stubs', 'signal stubs',
                        lambda modes: self.add_signal_stubs(inst, modes)), 'Ctrl+F10', not ro)
        self._menu_item(m, 'Add Port&IO...', lambda: self._ask_port_kinds('Add PortIO', 'portIO',
                        lambda modes: self.add_port_ios(inst, modes)), 'Shift+F10', not ro)
        self._menu_item(m, '&Equidistant Ports', lambda: self.equidistant(inst), enabled=not ro)
        # Port Map Frame: Enable / Disable / Edit... (the legacy tool greys the one that does not apply)
        pmf = m.addMenu('Port &Map Frame')
        pmf.addAction('&Enable', lambda: self._set_portmap(inst, True)).setEnabled(not ro and not inst.portmap_frame)
        pmf.addAction('&Disable', lambda: self._set_portmap(inst, False)).setEnabled(not ro and inst.portmap_frame)
        pmf.addAction('&Edit...', lambda: self.component_properties(inst, 'portmap')).setEnabled(inst.portmap_frame)
        m.addSeparator()
        self._submenu(m, 'S&hape', [('Editing Shape', None), ('Autowhisker', None), ('Autoshapes...', None)])
        self._menu_item(m, 'Appea&rance...', lambda: self._small_dialog('appearance', inst))
        self._menu_item(m, 'Show Te&xt', lambda: self._show_component_text(inst), enabled=not ro)
        self._menu_item(m, 'Port Visibilit&y...', lambda: self._small_dialog('ports', inst))
        m.addSeparator()
        # Generics/Parameters: Edit Declarations (the parameters page) / Edit Mappings (the values
        # given to this instance)
        self._submenu(m, '&Generics/Parameters', [
            ('Edit Declarations', lambda: self.edit_declarations(inst)),
            ('Edit Mappings', lambda: self.component_properties(inst, 'parameters'))])
        self._submenu(m, 'Re-&level', [('Remove Hierarchy...', None if ro else (lambda: self.remove_hierarchy(inst))),
                                       ('Add Hierarchy...', None)])
        self._submenu(m, '&Update', [
            ('Interface...', None if ro else lambda: self.update_interface_dialog(inst)),
            ('Interface and Graphics', None if ro else lambda: self.update_interface(inst, 'graphics')),
            ('From Symbol', None if ro or not self._symbol_of(inst) else
             (lambda: self.update_interface(inst, 'symbol'))),
            ('Graphics To Symbol', None)])
        a = m.addAction('&Object Properties...', lambda: self.component_properties(inst, 'component'))
        a.setShortcut(QKeySequence('Alt+Return')); a.setShortcutVisibleInContextMenu(True)

    def _pin_menu(self, m: QMenu, inst: BdInstance, ro: bool):
        """The popup menu of the selected component ports, entries and order as in the legacy tool. The
        commands act on the selected ports only, without asking for the kinds of ports."""
        pins = self.scene.pins_selected()
        names = lambda i: {p.name for x, p in pins if x is i}
        insts = list({id(i): i for i, _ in pins}.values()) or [inst]

        def each(fn):
            """Run fn(instance, names of its selected ports) for each component concerned."""
            for i in insts:
                fn(i, names(i))
        self._menu_item(m, 'Disconnect', lambda: each(lambda i, n: self.disconnect(i, n)), 'Shift+Alt+C', not ro)
        self._menu_item(m, '&Equidistant Ports', lambda: each(lambda i, n: self.equidistant(i)), enabled=not ro)
        self._menu_item(m, 'Add Signal Stu&bs...', lambda: each(lambda i, n: self.add_signal_stubs(i, pins=n)),
                        'Ctrl+F10', not ro)
        self._menu_item(m, 'Add Port&IO...', lambda: each(lambda i, n: self.add_port_ios(i, pins=n)),
                        'Shift+F10', not ro)
        self._menu_item(m, 'Appea&rance...', lambda: self._small_dialog('appearance', inst))
        m.addSeparator()
        self._menu_item(m, 'Show Te&xt', lambda: each(lambda i, n: self._show_component_text(i)), enabled=not ro)
        a = m.addAction('&Object Properties...', lambda: self.component_properties(inst, 'component'))
        a.setShortcut(QKeySequence('Alt+Return')); a.setShortcutVisibleInContextMenu(True)

    def _small_dialog(self, kind: str, obj):
        """Appearance... (component, PortIO) or Port Visibility... (component): the legacy one-page dialog;
        OK / Apply redraw the diagram and record the change."""
        from .bd_dialogs import edit_appearance_dialog, port_display_dialog
        ro = self.scene.readonly
        redraw = None if ro else (lambda: self._reload_scene())
        make = edit_appearance_dialog if kind == 'appearance' else port_display_dialog
        dlg = make(obj, self, redraw)
        if ro:
            dlg.page.setEnabled(False)
        dlg.exec()

    def _unit_of(self, inst: BdInstance):
        """The project's design unit an instance instantiates, or None."""
        p = self._project()
        return p.find_unit(inst.unit, prefer=p.library(inst.library)) if p is not None else None

    def _change_default_view(self, du, view):
        """Change Default View (component menu): set the unit's default view and refresh the library tabs."""
        try:
            du.library.set_default_view(du.name, view)
        except OSError as e:
            QMessageBox.warning(self, 'Change Default View', str(e))
            return
        self.statusBar().showMessage(f'{du.name}: default view is now {view.name} ({view.label})', 5000)
        if self.context is not None:
            for ex in self.context.manager.explorers.values():
                ex.refresh()

    def _set_portmap(self, inst: BdInstance, on: bool):
        """Port Map Frame > Enable: switch the instance's port map frame on / off."""
        inst.portmap_frame = on
        self._reload_scene()

    def _show_component_text(self, inst: BdInstance):
        """Show Text: make the library, instance and port names of the instance visible."""
        inst.show_library = inst.show_instance = inst.text_name = True
        self._reload_scene()

    def _toggle_param_values(self, inst: BdInstance):
        """Generics/Parameters > Show Values: show / hide the parameter overrides on the diagram."""
        inst.show_params = not inst.show_params
        self._reload_scene()

    def port_properties(self, pio: BdPortIo, page: str = 'mode'):
        """Object Properties of a PortIO; a mode change goes through change_port_mode()."""
        dlg = PortIoPropertiesDialog(pio, page, self)
        dlg.exec()
        if dlg.applied and not self.scene.readonly:
            if dlg.mode() != pio.mode:
                self.change_port_mode(pio, dlg.mode())
            else:
                self._reload_scene()

    # -- net / port popup menus (same entries and order as the legacy editor) -----------
    def _menu_item(self, m: QMenu, text: str, fn=None, key: str = '', enabled: bool = True):
        """Add a popup menu entry with its shortcut shown; disabled without `fn` or when not `enabled`."""
        a = m.addAction(text)
        if fn is not None:
            a.triggered.connect(lambda checked=False, t=text: self._label(t))
            a.triggered.connect(fn)
        if key:
            a.setShortcut(QKeySequence(key))
            a.setShortcutVisibleInContextMenu(True)
        a.setEnabled(enabled and fn is not None)
        return a

    def _edit_items(self, m: QMenu, scene_pos: QPointF, ro: bool, can_copy: bool):
        """The Cut / Copy / Paste / Delete part of a popup menu."""
        self._menu_item(m, 'Cu&t', self.cut if can_copy else None, 'Ctrl+X', not ro)
        self._menu_item(m, '&Copy', self.copy if can_copy else None, 'Ctrl+C')
        self._menu_item(m, '&Paste', lambda: self.paste(scene_pos), 'Ctrl+V', bool(self._clipboard) and not ro)
        self._menu_item(m, '&Delete', self.delete_selected, 'Del', not ro)

    def _net_menu(self, m: QMenu, item: 'WireItem', pos: QPointF, ro: bool):
        """The net popup menu, entries and order as in the legacy tool: routes, Add Port I/O, Change Style, Goto
        Destination, edit, Disconnect, Highlight Net, text, comments, Object Properties.
        """
        w = item.obj
        net = w.net
        k = item._segment_at(pos)
        near = min(range(len(w.points)), key=lambda i: QLineF(pos, QPointF(*w.points[i])).length())
        interior = 0 < near < len(w.points) - 1 and QLineF(pos, QPointF(*w.points[near])).length() <= GRID
        self._menu_item(m, 'Add &Route', lambda: self.add_route(w, k, pos), enabled=not ro)
        self._menu_item(m, 'Re&move Route', lambda: self.remove_route(w, near), enabled=not ro and interior)
        self._menu_item(m, 'Remove &All Routes', lambda: self.remove_all_routes(w),
                        enabled=not ro and len(w.points) > 2)
        self._menu_item(m, 'Add Port &I/O', lambda: self.add_port_io_for(w), enabled=not ro and not (w.start and w.end))
        self._menu_item(m, '&Goto Destination ...', lambda: self.goto_destination(net))
        m.addSeparator()
        self._edit_items(m, pos, ro, can_copy=True)
        m.addSeparator()
        self._menu_item(m, 'C&onnect', None, 'Alt+C')
        self._menu_item(m, 'Disconnect', lambda: self.disconnect_wire(w), 'Shift+Alt+C',
                        enabled=not ro and bool(w.start or w.end))
        # the simulation sub-menus (breakpoints, probes) as the legacy tool lists them, greyed
        self._submenu(m, '&Breakpoints', [(t, None) for t in ('Add', 'Delete', 'Delete All', 'Disable',
                                                             'Disable All', 'Enable', 'Enable All', 'Report')])
        self._submenu(m, '&Probes', [(t, None) for t in ('Add', 'Delete', 'Delete All', 'Track Cursor')])
        self._autoroute_menu(m, ro)
        self._submenu(m, 'Highlight N&et', [('Single Level', lambda: self._highlight(net)), ('Hierarchical...', None),
                                           ('Clear All', lambda: self._highlight(''))])
        for title in ('&Insert Net', 'Remo&ve Net'):
            self._submenu(m, title, [('Single Level Up...', None), ('Single Level Down...', None),
                                     ('Hierarchical...', None)])
        m.addSeparator()
        # Change Style: the legacy tool turns the net into a bus (thick) or back into a signal at once
        bus = self.scene.is_bus(net)
        self._menu_item(m, 'Change St&yle', lambda: self.set_net_style(net, not bus), enabled=not ro)
        # Show Text: shows the net name when it is hidden (the legacy tool has no Hide Text here)
        self._menu_item(m, 'Show Te&xt', lambda: self.show_net_text(w), enabled=not ro)
        self._menu_item(m, 'Signal Visibilit&y...', None)
        self._menu_item(m, 'Appeara&nce...', None)
        m.addSeparator()
        scope = m.addMenu('Scope For Chan&ges')
        for text, on in (('Joined Wires in this diagram', False), ('Entire Net in diagram', True),
                         ('Entire Net in hierarchy', False)):
            a = scope.addAction(text)
            a.setCheckable(True)
            a.setChecked(on)
            a.setEnabled(on)
        self._menu_item(m, 'Co&mments...', lambda: self.net_comment(net), enabled=not ro)
        self._menu_item(m, 'A&ttributes...', None)
        self._menu_item(m, 'Object &Properties...', lambda: self.signal_properties(net), 'Alt+Return')

    def _port_menu(self, m: QMenu, item: 'PortIoItem', pos: QPointF, ro: bool):
        """The PortIO popup menu as in the legacy tool: Change Mode, text visibility, edit, Disconnect, Appearance,
        Object Properties.
        """
        pio = item.obj
        cm = m.addMenu('Change &Mode')
        for text, mode in (('&In', 'input'), ('&Out', 'output'), ('In&Out', 'inout')):
            a = cm.addAction(text, lambda mode=mode: self.change_port_mode(pio, mode))
            a.setCheckable(True)
            a.setChecked(pio.mode == mode)
            a.setEnabled(not ro)
        self._submenu(m, '&Rotate Port', [('90', None), ('180', None), ('270', None)])
        m.addSeparator()
        self._menu_item(m, 'PortIO Text &Visibility...', lambda: self.port_properties(pio, 'visibility'))
        self._menu_item(m, 'Show Te&xt', lambda: self.show_port_text(pio), enabled=not ro)
        m.addSeparator()
        self._edit_items(m, pos, ro, can_copy=True)
        m.addSeparator()
        self._menu_item(m, 'C&onnect', None, 'Alt+C')
        attached = [w for w, _ in self.scene._attached(f'pio:{pio.id}')]
        self._menu_item(m, 'Disconnect', lambda: [self.disconnect_wire(w, only=f'pio:{pio.id}') for w in attached],
                        'Shift+Alt+C', enabled=not ro and bool(attached))
        m.addSeparator()
        self._menu_item(m, 'Appeara&nce...', lambda: self._small_dialog('appearance', pio))
        m.addSeparator()
        self._menu_item(m, 'Object &Properties...', lambda: self.port_properties(pio), 'Alt+Return')

    # net / port commands
    def set_net_style(self, net: str, bus: bool):
        """Change Style: draw the net as a bus (thick) or a signal (thin). As in the legacy tool the style
        is only the look of the net; its declaration (bounds) is not changed."""
        self.bd.net_styles[net] = 'bus' if bus else 'signal'
        self._reload_scene()

    def set_embedded_port_mode(self, w: BdWire, which: str, out: bool):
        """Change Mode of a connection on an embedded block. The mode is the direction the net
        is drawn in (a net starting on the block is an output, ending on it an input), so a
        change reverses the net: points, ends and the name position (kept where it is)."""
        if (which == 'start') == out:
            return
        if w.label is not None and w.points:
            # the name offset is relative to the first point, which becomes the last
            fx, fy = w.points[0]
            lx, ly = w.points[-1]
            w.label = [w.label[0] + fx - lx, w.label[1] + fy - ly]
        w.points.reverse()
        w.start, w.end = w.end, w.start
        self._reload_scene()

    def change_embedded_view(self, eb: BdEmbedded):
        """Change Embedded View (as in the legacy tool): drop the existing view, then Create Embedded View."""
        if QMessageBox.warning(self, 'Change Embedded View',
                               'Only one view is allowed. Do you want to delete the current view?',
                               QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return
        eb.text, eb.text_box = '', None
        self._reload_scene()
        item = self.scene.items_by_id[eb.id]
        self.embedded_double_click(item, item.body().center())

    def add_route(self, w: BdWire, k: int, pos: QPointF):
        """Add Route: a new route point on segment k at the click (kept on the segment's line)."""
        a, b = w.points[k], w.points[k + 1]
        if abs(a[1] - b[1]) < 0.01:
            q = [_snap(pos.x()), a[1]]
        elif abs(a[0] - b[0]) < 0.01:
            q = [a[0], _snap(pos.y())]
        else:
            q = [_snap(pos.x()), _snap(pos.y())]
        w.points.insert(k + 1, q)          # a handle that can be dragged to reshape the net
        self._net_edited(w)

    def remove_route(self, w: BdWire, i: int):
        """Remove Route: delete route point i (the net is made orthogonal again)."""
        del w.points[i]
        w.points = _simplify(_orthogonal(w.points))
        self._net_edited(w)

    def remove_all_routes(self, w: BdWire):
        """Remove All Routes: a straight orthogonal route between the two ends."""
        w.points = _simplify(_orthogonal([w.points[0], w.points[-1]]))
        self._net_edited(w)

    def _net_edited(self, w: BdWire):
        """Redraw one net and record the change."""
        if w.id in self.scene.wire_items:
            self.scene.wire_items[w.id].refresh()
        self.scene.changed_model.emit()

    def add_port_io_for(self, w: BdWire):
        """Port at the dangling end of a net, named after the net, direction from its drivers."""
        which, k = ('end', -1) if not w.end else ('start', 0)
        drivers = [p for i in self.bd.instances for p in i.pins if p.net == w.net and p.mode == 'output']
        mode = 'output' if drivers else 'input'
        end, nxt = w.points[k], w.points[k + 1 if k == 0 else -2]
        side = -1 if nxt[0] > end[0] else 1           # the port sits beyond the end, its edge on the net
        pio = BdPortIo(self._new_id('p'), w.net, mode, end[0] - side * PORT_EDGE, end[1])
        self.bd.port_ios.append(pio)
        setattr(w, which, f'pio:{pio.id}')
        self._ensure_port(w.net, mode)
        self._reload_scene()

    def goto_destination(self, net: str):
        """Goto Destination: the legacy tool goes to where the net continues on another page of the diagram.
        HDL Studio's block diagram is one page, so it answers as the legacy tool does when there is none."""
        QMessageBox.information(self, 'Goto Destination', 'No destination found. Or destination is on this page')

    def disconnect_wire(self, w: BdWire, only: str = ''):
        """Detach the ends of a net (only the end on `only` when given); a component port loses its
        net name when no other net is on it.
        """
        for which in ('start', 'end'):
            ref = getattr(w, which)
            if not ref or (only and ref != only):
                continue
            pin = self._pin(ref)
            if pin is not None and not any(x is not w and ref in (x.start, x.end) for x in self.bd.wires):
                pin.net = ''
            setattr(w, which, '')
        self._reload_scene()

    def _highlight(self, net: str):
        """Highlight the net (or none with '')."""
        self.scene.highlight = net
        self.scene.update()

    def change_style(self, net: str):
        """Change Style (Diagram menu): make the net a bus (asks for its bounds) or a signal again."""
        sig = next((s for s in self.bd.signals if s.name == net), None)
        if sig is None:
            return
        if sig.bounds:
            sig.bounds = ''
        else:
            bounds, ok = QInputDialog.getText(self, 'Change Style', f'Bus bounds for {net}:', text='[7:0]')
            if not ok or not bounds.strip():
                return
            sig.bounds = bounds.strip()
        self._reload_scene()

    def show_net_text(self, w: BdWire):
        """Show Text (net popup): make the net name visible (nothing changes when it is shown)."""
        if not w.show_text:
            self.toggle_net_text(w)

    def show_port_text(self, pio: BdPortIo):
        """Show Text (PortIO popup): make the port name visible (nothing changes when it is shown)."""
        if not pio.show_text:
            self.toggle_port_text(pio)

    def toggle_net_text(self, w: BdWire):
        """Show / hide the name of a net."""
        w.show_text = not w.show_text
        self._net_edited(w)

    def toggle_port_text(self, pio: BdPortIo):
        """Show / hide the name of a PortIO."""
        pio.show_text = not pio.show_text
        self.scene.items_by_id[pio.id].update()
        self.scene.changed_model.emit()

    def net_comment(self, net: str):
        """Comments...: the legacy Comments dialog of the net's declaration. The end-of-line comment is kept
        (written after the declaration); HDL Studio keeps no comment before / after it, so those boxes
        are greyed."""
        from PySide6.QtWidgets import QDialogButtonBox, QPlainTextEdit
        sig = next((s for s in self.bd.signals if s.name == net), None)
        if sig is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle('Comments')
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel('A single line comment can be added at the end of the declaration line.\n'
                             'Multiple-line comments can be added before/after the declaration.\n'
                             'Comment characters will be added when appropriate.'))
        lay.addWidget(QLabel('End-of-line (single line comment):'))
        eol = QLineEdit(sig.comment)
        lay.addWidget(eol)
        for title in ('Before (multi-line comment):', 'After (multi-line comment):'):
            row = QHBoxLayout()
            row.addWidget(QLabel(title)); row.addStretch(1)
            chk = QCheckBox('Add comment characters'); chk.setChecked(True); chk.setEnabled(False)
            row.addWidget(chk)
            lay.addLayout(row)
            box = QPlainTextEdit(); box.setEnabled(False)
            lay.addWidget(box)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Help)
        bb.button(QDialogButtonBox.Help).setEnabled(False)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.resize(372, 409)
        if dlg.exec() and not self.scene.readonly and eol.text().strip() != sig.comment:
            sig.comment = eol.text().strip()
            self.signals_tab.set_rows(self.bd.signals, self.bd.signals_sheet)
            self.changed()

    def change_port_mode(self, pio: BdPortIo, mode: str):
        """Change Mode of a PortIO (and of the module port it stands for)."""
        pio.mode = mode
        self._ensure_port(pio.name, mode)
        self._reload_scene()

    def _for_selected(self, fn):
        """Call fn(instance) for every selected component."""
        for it in [i for i in self.scene.selectedItems() if isinstance(i, InstanceItem)]:
            fn(it.obj)

    def properties_of_selection(self):
        """Object Properties (Alt+Enter) of the first selected object."""
        sel = self.scene.selectedItems()
        if not sel:
            return
        it = sel[0]
        if isinstance(it, InstanceItem):
            self.component_properties(it.obj, 'component')
        elif isinstance(it, WireItem):
            self.signal_properties(it.obj.net)
        elif isinstance(it, PortIoItem):
            self.port_properties(it.obj)
        elif isinstance(it, FrameItem):
            self.frame_properties(it.obj)

    def _add_here(self, mode: str, pos: QPointF):
        """Add Component / Port / Embedded Block from the diagram popup menu, at the click."""
        self.set_mode(mode)
        if self.scene.mode == mode:
            self.place_at(QPointF(_snap(pos.x()), _snap(pos.y())))

    def component_properties(self, inst: BdInstance, page: str):
        """Object Properties of a component on page `page`; when its library / unit changed, offer to
        read the new interface.
        """
        libs = [l.name for l in self._project().libraries] if self._project() else [inst.library]
        old = (inst.library, inst.unit)
        conns = [(p.name, p.net) for p in sorted(inst.pins, key=lambda p: p.order) if p.net]
        dlg = ComponentPropertiesDialog(inst, libs, self._symbol_params(inst), page, self, conns)
        dlg.exec()
        if dlg.applied and not self.scene.readonly:
            if (inst.library, inst.unit) != old and QMessageBox.question(
                    self, 'Component changed',
                    f'Read the interface of {inst.library}.{inst.unit} and update the pins?') == QMessageBox.Yes:
                self.update_interface(inst)
            self._reload_scene()

    def rename_embedded(self, eb: BdEmbedded):
        """Rename an embedded block."""
        name, ok = QInputDialog.getText(self, 'Rename embedded block', 'Name:', text=eb.name)
        if ok and name.strip():
            eb.name = name.strip()
            self._reload_scene()

    def signal_properties(self, net: str):
        """Object Properties of a net (its declaration); a new name renames the net everywhere."""
        sig = next((s for s in self.bd.signals if s.name == net), None)
        dlg = SignalPropertiesDialog(sig or Sig(net, 'local', 'wire'), self)
        if not dlg.exec() or self.scene.readonly:
            return
        if sig is None:
            sig = dlg.sig
            self.bd.signals.append(sig)
        v = dlg.values()
        new_name = v.pop('name')
        for k, val in v.items():
            setattr(sig, k, val)
        if new_name and new_name != net:
            self._rename(net, new_name)
        self._reload_scene()

    # pins without a wire get a short stub (named net) or a port of the module
    def _free_pins(self, inst: BdInstance) -> list[BdPin]:
        """The ports of an instance with no net drawn on them."""
        attached = {r for w in self.bd.wires for r in (w.start, w.end)}
        return [p for p in inst.pins if f'pin:{inst.id}:{p.name}' not in attached]

    def add_signal_stubs(self, inst: BdInstance, modes: set | None = None, pins: set | None = None):
        """Add Signal Stubs: a short named net (the port's net name or its own name) on every free port
        (of the kinds in `modes`: input / output / inout; all when None; only the ports named in `pins`
        when given)."""
        n = 0
        for pin in self._free_pins(inst):
            if pins is not None and pin.name not in pins:
                continue
            if modes is not None and (pin.mode if pin.mode in ('input', 'output') else 'inout') not in modes:
                continue
            net = pin.net or pin.name
            pin.net = net
            if not any(s.name == net for s in self.bd.signals):
                self.bd.signals.append(Sig(net, 'local', 'wire', pin.bounds))
            tip, out = pin_end(pin), _OUT[pin.side]
            self.bd.wires.append(BdWire(self._new_id('w'), net, [tip, [_snap(tip[0] + out[0] * 4 * GRID),
                                                                      _snap(tip[1] + out[1] * 4 * GRID)]],
                                        f'pin:{inst.id}:{pin.name}', ''))
            n += 1
        self.statusBar().showMessage(f'Added {n} signal stub(s)', 4000)
        self._reload_scene()

    def connect_by_name(self):
        """Diagram > Autoroute > Connect By Name: every free port of the selected components (all
        components when none is selected) whose name is the name of a net or port of the diagram
        gets a stub on that net, so it is connected to it by name."""
        bd = self.bd
        names = {s.name for s in bd.signals} | {w.net for w in bd.wires if w.net} | {p.name for p in bd.port_ios if p.name}
        insts = self._sel(InstanceItem) or list(bd.instances)
        n = 0
        for inst in insts:
            for pin in self._free_pins(inst):
                net = pin.net if pin.net in names else pin.name if pin.name in names else ''
                if not net:
                    continue
                pin.net = net
                tip, out = pin_end(pin), _OUT[pin.side]
                bd.wires.append(BdWire(self._new_id('w'), net, [tip, [_snap(tip[0] + out[0] * 4 * GRID),
                                                                    _snap(tip[1] + out[1] * 4 * GRID)]],
                                       f'pin:{inst.id}:{pin.name}', ''))
                n += 1
        self.statusBar().showMessage(f'Connected {n} port(s) by name', 4000)
        if n:
            self._reload_scene()

    def add_port_ios(self, inst: BdInstance, modes: set | None = None, pins: set | None = None):
        """Add PortIO: a module port joined by a net to every free port of the instance (of the kinds in
        `modes`: input / output / inout; all when None; only the ports named in `pins` when given)."""
        n = 0
        for pin in self._free_pins(inst):
            if pins is not None and pin.name not in pins:
                continue
            if modes is not None and (pin.mode if pin.mode in ('input', 'output') else 'inout') not in modes:
                continue
            net = pin.net or pin.name
            pin.net = net
            mode = pin.mode if pin.mode in ('input', 'output', 'inout') else 'input'
            self._ensure_port(net, mode, pin.bounds)
            tip, out = pin_end(pin), _OUT[pin.side]
            pio = BdPortIo(self._new_id('p'), net, mode, _snap(tip[0] + out[0] * 8 * GRID),
                           _snap(tip[1] + out[1] * 8 * GRID))
            self.bd.port_ios.append(pio)
            px = pio.x - out[0] * PORT_EDGE if out[0] else pio.x - PORT_EDGE
            self.bd.wires.append(BdWire(self._new_id('w'), net, _orthogonal([tip, [px, pio.y]]),
                                        f'pin:{inst.id}:{pin.name}', f'pio:{pio.id}'))
            n += 1
        self.statusBar().showMessage(f'Added {n} port(s)', 4000)
        self._reload_scene()

    def disconnect(self, inst: BdInstance, pins: set | None = None):
        """Disconnect (component / port popup): as the legacy tool, every net on the component's ports (only
        the ports named in `pins` when given) stays where it is, its end is only detached from the port (it
        shows the red unconnected mark)."""
        mine = [p for p in inst.pins if pins is None or p.name in pins]
        refs = {f'pin:{inst.id}:{p.name}' for p in mine}
        for w in self.bd.wires:
            for which in ('start', 'end'):
                if getattr(w, which) in refs:
                    setattr(w, which, '')
        for p in mine:
            p.net = ''
        self._reload_scene()

    def connect_component(self, inst: BdInstance):
        """Connect (component popup): every unconnected net end lying on a port of the component is
        attached to that port (and the port takes the net), as the legacy tool joins them."""
        n = 0
        for p in inst.pins:
            tip = pin_end(p)
            for w in self.bd.wires:
                for which, k in (('start', 0), ('end', -1)):
                    if not getattr(w, which) and w.points and                             abs(w.points[k][0] - tip[0]) < 1 and abs(w.points[k][1] - tip[1]) < 1:
                        setattr(w, which, f'pin:{inst.id}:{p.name}')
                        p.net = w.net
                        n += 1
        self.statusBar().showMessage(f'Connected {n} net end(s)', 4000)
        if n:
            self._reload_scene()

    def turn_component(self, inst: BdInstance, turn: int = 0, flip: str = ''):
        """Rotate (90 / 180 / 270, clockwise) or Flip (vertical / horizontal) a component about its centre,
        as the legacy tool does: the body turns, the ports go round with it and the end of each net on them
        follows (the rest of the net stays, so the last piece may run askew)."""
        cx, cy = inst.x + inst.w / 2, inst.y + inst.h / 2
        sides_cw = ['left', 'top', 'right', 'bottom']

        def move(x, y, side):
            dx, dy = x - cx, y - cy
            if flip == 'vertical':
                dy = -dy
                side = {'top': 'bottom', 'bottom': 'top'}.get(side, side)
            elif flip == 'horizontal':
                dx = -dx
                side = {'left': 'right', 'right': 'left'}.get(side, side)
            for _ in range(turn // 90):
                dx, dy = -dy, dx
                side = sides_cw[(sides_cw.index(side) + 1) % 4]
            return cx + dx, cy + dy, side

        ends = {}
        for p in inst.pins:
            p.x, p.y, p.side = move(p.x, p.y, p.side)
            ends[f'pin:{inst.id}:{p.name}'] = pin_end(p)
        if (turn // 90) % 2:
            inst.w, inst.h = inst.h, inst.w
            inst.x, inst.y = cx - inst.w / 2, cy - inst.h / 2
        for w in self.bd.wires:
            for which, k in (('start', 0), ('end', -1)):
                end = ends.get(getattr(w, which))
                if end is not None and w.points:
                    w.points[k] = list(end)
        self._reload_scene()

    def _ask_port_kinds(self, title: str, what: str, run):
        """The legacy question of Add Signal Stubs / Add PortIO: which kinds of ports get one (Input,
        Output, InOut, all checked); OK runs `run(modes)`."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f'Please specify the type of ports that require {what}:'))
        boxes = {}
        for text, mode in (('Input', 'input'), ('Output', 'output'), ('InOut', 'inout')):
            boxes[mode] = QCheckBox(text); boxes[mode].setChecked(True)
            lay.addWidget(boxes[mode])
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec():
            modes = {m for m, b in boxes.items() if b.isChecked()}
            if modes:
                run(modes)

    def equidistant(self, inst: BdInstance):
        """Equidistant Ports: spread the left and right ports evenly down the body (nets follow)."""
        for side in ('left', 'right'):
            pins = sorted((p for p in inst.pins if p.side == side), key=lambda p: p.y)
            if not pins:
                continue
            step = max(PIN_STEP, _snap((inst.h - 40) / (len(pins) - 1))) if len(pins) > 1 else PIN_STEP
            for i, p in enumerate(pins):
                dy = inst.y + 30 + i * step - p.y
                if dy:
                    ref = f'pin:{inst.id}:{p.name}'
                    for w in self.bd.wires:
                        for which in ('start', 'end'):
                            if getattr(w, which) == ref:
                                _shift_end(w, which, 0, dy)
                    p.y += dy
        self._reload_scene()

    def edit_declarations(self, inst: BdInstance):
        """Generics/Parameters > Edit Declarations: as the legacy tool, open the component's HDL, where its
        parameters are declared, in the text editor."""
        du = self._unit_of(inst)
        path = du.hdl.file if du is not None and du.hdl is not None else inst.source
        if not path or not os.path.exists(path):
            QMessageBox.information(self, 'Edit Declarations', f'No HDL file found for {inst.library}.{inst.unit}.')
            return
        if self.context is not None:
            self.context.manager.open_text_file(path)
        else:
            QMessageBox.information(self, 'Edit Declarations', path)

    def remove_hierarchy(self, inst: BdInstance):
        """Re-level > Remove Hierarchy: the legacy tool flattens an instance whose view is a block diagram;
        for any other instance it answers with this message (HDL Studio does not flatten diagrams)."""
        du = self._unit_of(inst)
        if du is None or not any(v.kind == 'bd' for v in du.views):
            QMessageBox.warning(self, 'Remove Hierarchy', 'Can only remove hierarchy if instance is a Block Diagram.')
        else:
            QMessageBox.information(self, 'Remove Hierarchy', 'Remove Hierarchy is not available in this version.')

    def update_interface_dialog(self, inst: BdInstance):
        """Update > Interface...: the legacy "Update Interface" dialog. Its title line says whether the
        instance and the component interface are the same; the report lists the ports that differ
        ("The inconsistencies are caused by:-") and the component interface, by name, as the legacy tool
        writes them ("output reg [7:0] name"). OK / Apply make the instance consistent with it."""
        from PySide6.QtWidgets import QRadioButton
        self._child_types = {}
        info = self._interface(inst)
        diffs = []
        types = self._child_types

        def decl(name, mode, bounds):
            t = types.get(name) or ('reg' if mode == 'output' else 'wire')
            return f'  {mode:<6} {t} {bounds + " " if bounds else ""}{name}'
        if info:
            have = {p.name: p for p in inst.pins}
            want = {n: (d, b) for n, d, b in info['ports']}
            for n in sorted(have.keys() | want.keys(), key=str.lower):
                if n not in want:
                    diffs.append(decl(n, have[n].mode, have[n].bounds or ''))
                elif n not in have or have[n].mode != want[n][0] or (have[n].bounds or '') != (want[n][1] or ''):
                    diffs.append(decl(n, want[n][0], want[n][1] or ''))
        if not info:
            title = f'Interface of {inst.library}.{inst.unit} not found.'
            report = ''
        else:
            title = f'Instance {inst.name} :: The interfaces are {"DIFFERENT" if diffs else "IDENTICAL"}.'
            report = ''
            if diffs:
                report += 'The inconsistencies are caused by:-\n' + '\n'.join(diffs) + '\n\n'
            report += 'The instance interface is:-\n' + '\n'.join(
                decl(n, d, b or '') for n, d, b in sorted(info['ports'], key=lambda x: x[0].lower()))
        dlg = QDialog(self)
        dlg.setWindowTitle('Update Interface')
        lay = QVBoxLayout(dlg)
        top = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel(title))
        text = QPlainTextEdit(report)
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.NoWrap)
        left.addWidget(text, 1)
        top.addLayout(left, 3)
        right = QVBoxLayout()
        right.addWidget(QLabel('Instances'))
        inst_list = QListWidget(); inst_list.addItem(f'{inst.library}/{inst.name}'); inst_list.setCurrentRow(0)
        right.addWidget(inst_list, 1)
        opts = QPushButton('Options...'); opts.setEnabled(False)
        right.addWidget(opts)
        top.addLayout(right, 1)
        lay.addLayout(top, 1)
        r1 = QRadioButton('Make the instance consistent with component interface')
        r2 = QRadioButton('Make child view consistent with the instance')
        r1.setChecked(bool(diffs)); r2.setChecked(not diffs)
        r1.setEnabled(bool(diffs)); r2.setEnabled(False)
        lay.addWidget(r1); lay.addWidget(r2)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply |
                              QDialogButtonBox.Help)
        bb.button(QDialogButtonBox.Help).setEnabled(False)
        run = lambda: self.update_interface(inst) if diffs and r1.isChecked() else None
        bb.accepted.connect(lambda: (run(), dlg.accept()))
        bb.rejected.connect(dlg.reject)
        bb.button(QDialogButtonBox.Apply).clicked.connect(run)
        lay.addWidget(bb)
        dlg.resize(550, 400)
        dlg.exec()

    def _symbol_of(self, inst: BdInstance) -> str:
        """The legacy symbol file (.sb) of an instance's unit, or ''."""
        du = self._unit_of(inst)
        return next((v.path for v in du.views if v.kind == 'symbol' and v.path.endswith('.sb')), '') if du else ''

    def update_interface(self, inst: BdInstance, how: str = 'interface'):
        """Update an instance from its component's interface, as the legacy tool's Update sub-menu:
          'interface'  Update > Interface (OK in the Update Interface dialog): ports that are new in the
                       interface are added, ports no longer in it are removed (their nets stay, detached),
                       changed modes / bounds are taken; the other ports keep their places;
          'graphics'   Interface and Graphics: the same, keeping the instance size and port places; a new
                       port takes its place from the symbol when the unit has one;
          'symbol'     From Symbol: body and every port laid out as the symbol has them; the nets stay
                       connected and follow their ports.
        """
        info = self._interface(inst)
        if not info or not info['ports']:
            QMessageBox.warning(self, 'Update interface', f'Interface of {inst.library}.{inst.unit} not found.')
            return
        want = {n: (m, b) for n, m, b in info['ports']}
        before = {p.name: (p.x, p.y) for p in inst.pins}
        removed = [p.name for p in inst.pins if p.name not in want]
        added = [n for n, _, _ in info['ports'] if n not in before]
        sym = self._symbol_of(inst)
        # From Symbol: every port laid out as the symbol file has it. (Interface and Graphics keeps the
        # instance size and its ports' places: the legacy tool takes its graphics from the symbol it keeps up to
        # date in memory, which a symbol file not saved since does not show.)
        if how == 'symbol' and sym:
            nets = {p.name: p.net for p in inst.pins}
            self._layout_pins(inst, info['ports'])
            self._symbol_layout(inst, sym)
            # the symbol file may lag behind the child view: its ports that are gone are dropped, the
            # new ones go below the last port of their side
            inst.pins = [p for p in inst.pins if p.name in want]
            for p in inst.pins:
                p.mode, p.bounds, p.net = want[p.name][0], want[p.name][1] or p.bounds, nets.get(p.name, '')
            for name in [n for n, _, _ in info['ports'] if n not in {p.name for p in inst.pins}]:
                mode, bounds = want[name]
                side = 'right' if mode == 'output' else 'left'
                same = [q.y for q in inst.pins if q.side == side]
                y = (max(same) + PIN_STEP) if same else inst.y + 2 * GRID
                x = inst.x - PIN_HALF if side == 'left' else inst.x + inst.w + PIN_HALF
                inst.pins.append(BdPin(name, mode, '', len(inst.pins) + 1, x, y, side, bounds))
        else:
            geo = None
            if how == 'graphics' and sym:
                try:
                    from formats.import_bd import symbol_geometry
                    geo = symbol_geometry(sym)
                except Exception:
                    geo = None
            sym_place = {g[0]: g for g in geo[2]} if geo else {}
            inst.pins = [p for p in inst.pins if p.name in want]
            for p in inst.pins:
                p.mode, p.bounds = want[p.name][0], want[p.name][1]
            for name in added:
                mode, bounds = want[name]
                g = sym_place.get(name)
                if g is not None and abs(geo[0] - inst.w) < 1 and abs(geo[1] - inst.h) < 1:
                    side, gx, gy = g[6], g[4], g[5]
                    x = inst.x + ({'left': -PIN_HALF, 'right': inst.w + PIN_HALF}.get(side, gx))
                    y = inst.y + ({'top': -PIN_HALF, 'bottom': inst.h + PIN_HALF}.get(side, gy))
                else:
                    # below the last port of its side: inputs / inouts on the left, outputs on the right
                    side = 'right' if mode == 'output' else 'left'
                    same = [q.y for q in inst.pins if q.side == side]
                    y = (max(same) + PIN_STEP) if same else inst.y + 2 * GRID
                    x = inst.x - PIN_HALF if side == 'left' else inst.x + inst.w + PIN_HALF
                    if how == 'interface' and y > inst.y + inst.h - GRID:
                        inst.h = _snap(y - inst.y + 2 * GRID)        # the body grows to hold it
                inst.pins.append(BdPin(name, mode, '', len(inst.pins) + 1, x, y, side, bounds))
        order = {n: k for k, (n, _, _) in enumerate(info['ports'])}
        for p in inst.pins:
            p.order = order.get(p.name, p.order) + 1
        # nets on removed ports stay where they are, detached; the others follow their port
        gone = {f'pin:{inst.id}:{n}' for n in removed}
        pos = {f'pin:{inst.id}:{p.name}': pin_end(p) for p in inst.pins}
        for w in self.bd.wires:
            for which, idx in (('start', 0), ('end', -1)):
                r = getattr(w, which)
                if r in gone:
                    setattr(w, which, '')
                elif r in pos and w.points:
                    ex, ey = w.points[idx]
                    _shift_end(w, which, pos[r][0] - ex, pos[r][1] - ey)
        self.log.addItem(f'{inst.name}: {len(added)} pin(s) added, {len(removed)} removed')
        self.statusBar().showMessage(f'{inst.name}: {len(added)} port(s) added, {len(removed)} removed', 5000)
        self._reload_scene()

    # -- clipboard -------------------------------------------------------------------------
    # the kinds of objects Copy / Paste carries: item class, model list, id prefix, end reference kind
    _CLIP_KINDS = (('inst', 'instances', 'i', 'pin'), ('frame', 'frames', 'f', ''), ('emb', 'embedded', 'e', 'emb'),
                   ('pio', 'port_ios', 'p', 'pio'), ('comment', 'comments', 'c', ''), ('jct', 'junctions', 'j', 'jct'))

    def copy(self):
        """Edit > Copy (and the popup Copy): the selected components, frames, embedded blocks, PortIOs,
        comments, junctions and nets go to the editor's clipboard. A net end stays connected only to
        an object copied with it, as the legacy tool pastes it."""
        from dataclasses import asdict
        sel = self.scene.selectedItems()
        items = {InstanceItem: 'inst', FrameItem: 'frame', EmbeddedItem: 'emb', PortIoItem: 'pio',
                 CommentItem: 'comment', JunctionItem: 'jct'}
        clip = []
        for it in sel:
            kind = next((k for cls, k in items.items() if isinstance(it, cls)), None)
            if kind is not None:
                clip.append(dict(asdict(it.obj), _kind=kind))
        for it in sel:
            if isinstance(it, WireItem):
                clip.append(dict(asdict(it.obj), _kind='wire'))
        self._clipboard = clip
        self.statusBar().showMessage(f'Copied {len(clip)} object(s)', 3000)

    def cut(self):
        """Copy, then delete the selection."""
        self.copy()
        self.delete_selected()

    def paste(self, at: QPointF | None = None):
        """Paste the clipboard (at `at`, else offset by 40): new ids, unique instance / frame / embedded
        block names; nets keep their names (they join their net by name) and stay connected to the
        objects pasted with them; component ports not on a pasted net are left unconnected.
        """
        from bd_model import _build
        if not self._clipboard or self.scene.readonly:
            return
        bd = self.bd
        xs = [c['x'] for c in self._clipboard if 'x' in c and c['_kind'] != 'wire'] +              [p[0] for c in self._clipboard if c['_kind'] == 'wire' for p in c['points']]
        ys = [c['y'] for c in self._clipboard if 'y' in c and c['_kind'] != 'wire'] +              [p[1] for c in self._clipboard if c['_kind'] == 'wire' for p in c['points']]
        ox = _snap(at.x() - min(xs)) if at is not None and xs else 40.0
        oy = _snap(at.y() - min(ys)) if at is not None and ys else 40.0
        classes = {'inst': BdInstance, 'frame': BdFrame, 'emb': BdEmbedded, 'pio': BdPortIo,
                   'comment': BdComment, 'jct': BdJunction}
        new_ref = {}                            # old end reference -> new one
        pasted_pins = set()
        for kind, coll, prefix, ref in self._CLIP_KINDS:
            for data in (c for c in self._clipboard if c['_kind'] == kind):
                obj = _build(classes[kind], {k: v for k, v in data.items() if k != '_kind'})
                old = obj.id
                obj.id = self._new_id(prefix)
                obj.x, obj.y = obj.x + ox, obj.y + oy
                if kind == 'inst':
                    obj.name = self._unique(obj.name, {i.name for i in bd.instances})
                    for pin in obj.pins:
                        pin.x, pin.y = pin.x + ox, pin.y + oy
                        new_ref[f'pin:{old}:{pin.name}'] = f'pin:{obj.id}:{pin.name}'
                elif kind == 'frame':
                    obj.number = max((f.number for f in bd.frames), default=0) + 1
                    if obj.kind != 'else':
                        obj.name = self._unique(obj.name, {f.name for f in bd.frames})
                elif kind == 'emb':
                    obj.number = max((e.number for e in bd.embedded), default=0) + 1
                    obj.name = self._unique(obj.name, {e.name for e in bd.embedded})
                elif ref:
                    new_ref[f'{ref}:{old}'] = f'{ref}:{obj.id}'
                if kind == 'emb':
                    new_ref[f'emb:{old}'] = f'emb:{obj.id}'
                getattr(bd, coll).append(obj)
        for data in (c for c in self._clipboard if c['_kind'] == 'wire'):
            w = _build(BdWire, {k: v for k, v in data.items() if k != '_kind'})
            w.id = self._new_id('w')
            w.points = [[x + ox, y + oy] for x, y in w.points]
            w.start, w.end = new_ref.get(w.start, ''), new_ref.get(w.end, '')
            pasted_pins.update(r for r in (w.start, w.end) if r.startswith('pin:'))
            bd.wires.append(w)
        # component ports: connected only to the nets pasted with them
        for inst in bd.instances:
            for pin in inst.pins:
                ref = f'pin:{inst.id}:{pin.name}'
                if ref in new_ref.values() and ref not in pasted_pins:
                    pin.net = ''
                elif ref in pasted_pins:
                    pin.net = next(w.net for w in bd.wires if ref in (w.start, w.end))
        self._reload_scene()

    @staticmethod
    def _unique(name: str, taken: set) -> str:
        """`name`, or name_1, name_2 ... when it is taken."""
        base, k = name, 0
        while name in taken:
            k += 1
            name = f'{base}_{k}'
        return name

    def _new_id(self, prefix: str) -> str:
        """A new object id '<prefix>n<k>' not used by any object of the diagram."""
        used = {i.id for i in self.bd.instances} | {e.id for e in self.bd.embedded} | \
               {p.id for p in self.bd.port_ios} | {w.id for w in self.bd.wires} | {f.id for f in self.bd.frames} | \
               {j.id for j in self.bd.junctions} | {c.id for c in self.bd.comments} | {p.id for p in self.bd.panels}
        k = 1
        while f'{prefix}n{k}' in used:
            k += 1
        return f'{prefix}n{k}'

    def _pin(self, ref: str) -> BdPin | None:
        """The component port a "pin:<inst>:<pin>" reference points to, or None."""
        if not ref.startswith('pin:'):
            return None
        _, iid, pname = ref.split(':', 2)
        inst = next((i for i in self.bd.instances if i.id == iid), None)
        return next((p for p in inst.pins if p.name == pname), None) if inst else None

    def _pio(self, ref: str) -> BdPortIo | None:
        """The PortIO a "pio:<id>" reference points to, or None."""
        if not ref.startswith('pio:'):
            return None
        return next((p for p in self.bd.port_ios if p.id == ref[4:]), None)

    def _default_net_name(self, bus: bool) -> str:
        """legacy default name of a new net: sig0, sig1... for a signal, dbus0, dbus1... for a bus
        (the first number not used by a signal of the diagram)."""
        base = 'dbus' if bus else 'sig'
        used = {s.name for s in self.bd.signals} | {w.net for w in self.bd.wires}
        k = 0
        while f'{base}{k}' in used:
            k += 1
        return f'{base}{k}'

    def add_wire(self, start_ref: str, end_ref: str, a: list, bends: list, b: list):
        """A net drawn with Add Signal / Add Bus (and their "with a Port" variants), named as
        legacy names it, without asking:
          - an end on a net (component port net, PortIO, existing net) gives that net's name;
          - else an end on a component port gives the port's name and bounds;
          - else the default name sig<n> (a bus: dbus<n>, bounds [15:0]).
        Ends on two different nets are refused. An end on an existing net ("net:<wire id>") is
        joined to it with a junction dot. "with a Port": an open-space start gets an input
        port, an open-space end an output port, connected and named after the net."""
        bd, mode = self.bd, self.scene.mode
        bus = mode in ('bus', 'bus_port')
        refs = [start_ref, end_ref]
        pins = [self._pin(r) for r in refs]
        pios = [self._pio(r) for r in refs]
        joined = [next((w for w in bd.wires if r == f'net:{w.id}'), None) if r.startswith('net:') else None
                  for r in refs]
        nets = ({p.net for p in pins if p and p.net} | {p.name for p in pios if p and p.name}
                | {w.net for w in joined if w})
        if len(nets) > 1:
            QMessageBox.warning(self, 'Add wire', f'The two ends are already on different nets: {", ".join(sorted(nets))}')
            return
        first_pin = next((p for p in pins if p), None)
        if nets:
            net = nets.pop()
        elif first_pin is not None:
            net = first_pin.name                # the net takes the component port's name
        else:
            net = self._default_net_name(bus)
        points = _route(a, bends, b)
        if len(points) < 2 or points[0] == points[-1]:
            return                              # nothing drawn
        # As the legacy tool: a signal (not a bus) started or ended on a bus rips one element of it;
        # The legacy tool asks which ("Rip Element From Bus"). The new wire carries that slice of the bus.
        rip = ''
        bus_end = next((w for w in joined if w is not None and self.scene.is_bus(w.net)), None)
        if bus_end is not None and not bus:
            rip = self._ask_rip_element(bus_end.net)
            if rip is None:
                return                          # Cancel: nothing is drawn
        # an end on an existing net: a junction dot there, the new net attached to it
        for k, w in enumerate(joined):
            if w is None:
                continue
            pt = points[0] if k == 0 else points[-1]
            j = BdJunction(self._new_id('j'), pt[0], pt[1])
            bd.junctions.append(j)
            refs[k] = f'jct:{j.id}'
            # a dangling end of that net lying on the dot is joined to it as well
            for which, idx in (('start', 0), ('end', -1)):
                if not getattr(w, which) and w.points and w.points[idx] == pt:
                    setattr(w, which, f'jct:{j.id}')
        for p in pins:
            if p:
                p.net = net
        if not any(s.name == net for s in bd.signals):
            bounds = next((p.bounds for p in pins if p and p.bounds), '') or ('[15:0]' if bus else '')
            bd.signals.append(Sig(net, 'local', 'wire', bounds))
        for p in pios:
            if p is not None and not p.name:
                # a port that had no name yet takes the net's name and becomes a module port
                p.name = net
                self._ensure_port(net, p.mode)
        w = BdWire(self._new_id('w'), net, points, refs[0], refs[1], slice=rip)
        for p in pins:
            if p is not None and rip:
                p.slice = rip                   # the component port gets that element of the bus
        self._place_new_label(w)
        bd.wires.append(w)
        if mode in ('wire_port', 'bus_port'):
            for which, idx, nxt, pmode in (('start', 0, 1, 'input'), ('end', -1, -2, 'output')):
                if getattr(w, which):
                    continue
                # the port's edge on the open end, the port on the far side from the net
                ex, ey = points[idx]
                side = 1 if points[nxt][0] >= ex else -1
                pio = BdPortIo(self._new_id('p'), net, pmode, ex - side * PORT_EDGE, ey)
                bd.port_ios.append(pio)
                setattr(w, which, f'pio:{pio.id}')
                self._ensure_port(net, pmode)
        self.scene.load(bd)
        # as the legacy tool, the new net is left selected
        for it in self.scene.items():
            if isinstance(it, WireItem) and it.obj is w:
                it.setSelected(True)
        self.signals_tab.set_rows(bd.signals, bd.signals_sheet)
        self.changed()

    def _ask_rip_element(self, net: str) -> str | None:
        """The "Rip Element From Bus" dialog of the legacy tool: which element of the bus a signal drawn
        from it carries. Returns "[n]" ('' when nothing is typed) or None on Cancel. The
        elements are offered from the bus bounds, MSB first; any index expression can be typed."""
        import re
        sig = next((s for s in self.bd.signals if s.name == net), None)
        bounds = sig.bounds if sig else ''
        dlg = QDialog(self)
        dlg.setWindowTitle('Rip Element From Bus')
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel('Specify bus element to rip:'))
        lay.addWidget(QLabel(f'        Bus:   {sig.type if sig else "wire"} {bounds} {net}'))
        row = QHBoxLayout()
        row.addWidget(QLabel('Specify Element:'))
        elem = QComboBox(); elem.setEditable(True)
        m = re.fullmatch(r'\[\s*(\d+)\s*:\s*(\d+)\s*\]', bounds.strip())
        if m:
            hi, lo = int(m.group(1)), int(m.group(2))
            step = -1 if hi >= lo else 1
            elem.addItems([str(i) for i in range(hi, lo + step, step)])
        row.addWidget(elem, 1)
        row.addWidget(QLabel(':'))
        second = QComboBox(); second.setEnabled(False)      # the range end (not used for one element)
        row.addWidget(second, 1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Help)
        bb.button(QDialogButtonBox.Help).setEnabled(False)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if not dlg.exec():
            return None
        t = elem.currentText().strip()
        return f'[{t}]' if t else ''

    @staticmethod
    def _place_new_label(w: BdWire):
        """Name position of a new net, as the legacy tool places it (read back from diagrams it saved;
        legacy units, 75 per scene unit), from the start of the first segment:
          - right: baseline 200 above the net, text starting 2000 after the start;
          - left: baseline 200 above, text starting 3000 before the start;
          - down: text read upward, baseline 200 left of the net, its top 2000 below the start;
          - up: the same, its top 3000 above the start (by symmetry with left).
        The stored offset is the baseline origin relative to the first point (as imported)."""
        if len(w.points) < 2:
            return
        (x0, y0), (x1, y1) = w.points[0], w.points[1]
        u = 1 / 75                                   # one legacy unit in scene units
        if abs(y0 - y1) < 0.01:                      # horizontal
            w.label = [(2000 if x1 >= x0 else -3000) * u, -200 * u]
            w.label_vertical = False
        else:                                        # vertical: the baseline origin is the text's bottom end
            tw = QFontMetricsF(MONO).horizontalAdvance(w.net)
            w.label = [-200 * u, (2000 if y1 >= y0 else -3000) * u + tw]
            w.label_vertical = True

    def _selected_net(self) -> str:
        """Net name of the first selected wire ('' when none)."""
        w = next((i.obj for i in self.scene.selectedItems() if isinstance(i, WireItem)), None)
        return w.net if w else ''

    def edit_net_inline(self, net: str, pos: QPointF, select: tuple[int, int] | None = None):
        """Edit a net (or the port that stands for it) in place, in a box on the diagram, in the
        The legacy tool form "name : type[bounds]", e.g. "rc_write_enable_rt : wire[DC_ROUTE_NUM - 1:0]".
        pos is the baseline start of the net name on the diagram (or the click position): the box
        is laid over it so the text being edited sits where the name was drawn."""
        if not net or self.scene.readonly:
            return
        sig = next((s for s in self.bd.signals if s.name == net), None)
        kind = (sig.type if sig is not None and sig.type else 'wire') + (' signed' if sig is not None and sig.signed else '')
        ed = QLineEdit(f'{net} : {kind}{sig.bounds if sig is not None and sig.bounds else ""}', self.canvas.viewport())
        ed.setFont(QFont('Courier New', 9))
        ed.setMinimumWidth(max(160, ed.fontMetrics().horizontalAdvance(ed.text()) + 30))
        ed.adjustSize()
        # baseline -> top-left of the box: up by the box height less the descent, left by the frame
        ed.move(self.canvas.mapFromScene(pos) - QPoint(4, ed.height() - 4))
        ed.selectAll()
        EC.select_span(ed, select)                       # Find Next: the match in the name
        done = []

        def finish(apply: bool):
            """Close the edit box once; with `apply`, apply the typed text after the event (the scene is
            rebuilt, so not from inside the box's own signal).
            """
            if done:
                return
            done.append(1)
            text = ed.text().strip()
            ed.hide(); ed.deleteLater()        # hidden at once, deleted by the event loop
            if apply and text:
                QTimer.singleShot(0, lambda: self.apply_net_text(net, text))

        ed.returnPressed.connect(lambda: finish(True))
        ed.installEventFilter(self)
        self.canvas.viewport().installEventFilter(self)     # a click on the diagram cancels
        self._inline_editor = (ed, finish)
        ed.show()
        ed.setFocus()

    def embedded_double_click(self, item: 'EmbeddedItem', pos: QPointF):
        """Double-click on an embedded block, as in the legacy tool:
          on the white Text view   - edit the HDL text in place;
          on the yellow block      - with no view yet, "Create Embedded View" asks which view to
                                     create (only Text is supported); with a Text view, edit it.
        A new Text view starts as "// <name> <number>" in a box at the block's bottom-right
        corner (where the legacy tool puts it); it can then be edited right away."""
        eb = item.obj
        if item.text_rect() is None:
            dlg = EmbeddedViewDialog(eb.name, self)
            if not dlg.exec():
                return
            w, h = item._size()
            eb.text_box = [w, h, 240.0, 60.0]
            eb.text = f'// {eb.name} {eb.number}\n'
            self._reload_scene()
            item = self.scene.items_by_id[eb.id]     # the scene was rebuilt
        self.edit_embedded_text_inline(item)

    def edit_embedded_text_inline(self, item: 'EmbeddedItem', select: tuple[int, int] | None = None):
        """Edit the HDL text of an embedded block in a box over its Text view. As in the legacy tool a click
        elsewhere (focus leaves the box) keeps the text; Esc throws the edit away."""
        eb = item.obj
        box = item.text_rect()
        # the box on screen: the Text view mapped to the viewport, never smaller than 320 x 120
        r = self.canvas.mapFromScene(item.mapToScene(box)).boundingRect()
        ed = _InlineText(eb.text, self.canvas.viewport())
        ed.setGeometry(r.x(), r.y(), max(r.width(), 320), max(r.height(), 120))
        EC.select_span(ed, select)                       # Find Next: the match in the text

        def commit(text: str):
            """Store the edited HDL text and record the change (when it changed)."""
            if text != eb.text:
                eb.text = text
                self.scene.items_by_id[eb.id].update()
                self.scene.changed_model.emit()
        ed.committed.connect(commit)
        ed.show()
        ed.setFocus()

    def edit_component_text_inline(self, item: 'InstanceItem', kind: str,
                                   select: tuple[int, int] | None = None):
        """Double-click on a name line of a component: edit it in place, in a white box over
        the text, as the legacy tool does. Enter applies, Esc or a click elsewhere cancels.

        kind is the line that was double-clicked:
          'instance' - renames the instance (must be a new, valid Verilog identifier);
          'unit'     - makes the instance use another component of the same library;
          'library'  - makes the instance use the same component from another library.
        For 'unit' and 'library' the ports are read again from the new component's HDL
        (Update Interface), so nets on ports that no longer exist are removed."""
        inst = item.obj
        box = next(r for k, _, r in item.name_lines() if k == kind)
        old = {'instance': inst.name, 'unit': inst.unit, 'library': inst.library}[kind]
        ed = QLineEdit(old, self.canvas.viewport())
        ed.setFont(QFont('Courier New', 9, QFont.Bold))
        ed.setMinimumWidth(max(140, ed.fontMetrics().horizontalAdvance(old) + 30))
        ed.adjustSize()
        # place the box over the line: scene -> viewport coordinates of the line's top-left
        ed.move(self.canvas.mapFromScene(item.mapToScene(box.topLeft())) - QPoint(2, 3))
        ed.selectAll()
        EC.select_span(ed, select)               # Find Next: the match in the line
        done = []                               # finish() runs once (Enter, then focus loss)

        def finish(apply: bool):
            """Close the edit box once; with `apply`, rename the instance or switch it to the typed unit /
            library (checked first, see the method docstring).
            """
            if done:
                return
            done.append(1)
            text = ed.text().strip()
            ed.hide(); ed.deleteLater()        # hidden at once, deleted by the event loop
            if not apply or not text or text == old:
                return
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$]*', text):
                self.statusBar().showMessage(f'"{text}" is not a Verilog identifier', 5000)
                return
            if kind == 'instance':
                if any(i.name == text for i in self.bd.instances if i is not inst):
                    self.statusBar().showMessage(f'Instance {text} already exists', 5000)
                    return
                inst.name = text
            else:
                # Point the instance at the other component, then take its ports. If the new
                # component cannot be found, go back: an instance of an unknown unit would
                # generate HDL that does not compile.
                setattr(inst, kind, text)
                if not self._interface(inst):
                    setattr(inst, kind, old)
                    self.statusBar().showMessage(f'Component {inst.library}.{text if kind == "unit" else inst.unit} '
                                                 f'not found', 6000)
                    return
                # update_interface() rebuilds the scene: `item` is gone after it, do not touch it
                self.update_interface(inst)
                self.scene.changed_model.emit()
                return
            item.prepareGeometryChange(); item.update()
            self.scene.changed_model.emit()

        ed.returnPressed.connect(lambda: finish(True))
        ed.installEventFilter(self)
        self.canvas.viewport().installEventFilter(self)     # a click on the diagram cancels
        self._inline_editor = (ed, finish)
        ed.show()
        ed.setFocus()

    def _build_view_actions(self):
        """Entries of the legacy View menu that are not toolbar commands."""
        def act(key, text, slot=None, shortcut='', checkable=False, checked=False):
            """Create the View menu action `key` (a check box action when `checkable`; disabled without a slot)."""
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if checkable:
                a.setCheckable(True); a.setChecked(checked)
                if slot is not None:
                    a.toggled.connect(slot)
            elif slot is not None:
                a.triggered.connect(slot)
            else:
                a.setEnabled(False)
            self.toolbar_actions[key] = a
            return a
        a = act('refresh', '&Refresh', self._refresh_view, 'F5')
        a.setStatusTip('Redraws the active diagram')
        a.setIcon(icon('refresh'))
        self.build_panel_actions(act, self.scene.readonly)
        act('grid', '&Grid', self._show_grid, checkable=True, checked=True)
        tb = act('toolbars', '&Toolbars', lambda: None)
        menu = QMenu(self)
        menu.aboutToShow.connect(lambda: (menu.clear(), [menu.addAction(t.toggleViewAction())
                                                          for t in self.findChildren(QToolBar)]))
        tb.setMenu(menu)
        act('status_bar', '&Status Bar', lambda on: self.statusBar().setVisible(on), checkable=True, checked=True)
        self.object_tips = True
        act('object_tips', 'Object &Tips', lambda on: setattr(self, 'object_tips', on), checkable=True, checked=True)
        act('diagram_browser', '&Diagram Browser', lambda on: self.browser_dock.setVisible(on),
            checkable=True, checked=True)
        self.browser_dock.visibilityChanged.connect(self.toolbar_actions['diagram_browser'].setChecked)
        act('signals_table', 'Signals Table', lambda: self.tabs.setCurrentIndex(1))
        act('page_break', 'Page Break Preview')
        self.canvas.viewport().installEventFilter(self)

    # -- menu bar commands that act on the selection (the legacy tool File / Diagram / Options / Window) --
    def _sel(self, cls) -> list:
        """Model objects of the selected items of one kind (InstanceItem, WireItem, PortIoItem)."""
        return [i.obj for i in self.scene.selectedItems() if isinstance(i, cls)]

    def _build_menu_commands(self):
        """Commands of the legacy menu bar that the toolbar does not have. Each one works on the
        current selection like its entry in the right-click menus; update_menu_states enables
        them when a menu opens, from what is selected then (as the legacy tool greys its entries)."""
        def act(key, text, slot=None, shortcut=''):
            """Create the menu action `key` (disabled without a slot); its shortcut is added to the window."""
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
                self.addAction(a)                # the shortcut works without opening the menu
            if slot is not None:
                a.triggered.connect(slot)
            else:
                a.setEnabled(False)
            self.toolbar_actions[key] = a
            return a

        def each(cls, fn):
            """A slot that applies fn to every selected object of item class `cls`, then records one change."""
            # apply fn to every selected object of a kind; one undo step for all of them
            def run():
                """The slot itself."""
                for obj in self._sel(cls):
                    fn(obj)
                self.changed()
            return run

        def nets(fn):
            """A slot that applies fn once per selected net name, then records one change."""
            # apply fn once per selected net (a net drawn as several wires counts once)
            def run():
                """The slot itself."""
                for net in dict.fromkeys(w.net for w in self._sel(WireItem)):
                    fn(net)
                self.changed()
            return run

        ro = self.scene.readonly
        mgr = self.context.manager if self.context is not None else None
        # File
        act('close_window', 'Close Window', self.close)
        act('exit', 'Exit', QApplication.instance().closeAllWindows)
        act('page_setup', 'Page Setup...', (lambda: mgr.page_setup(self)) if mgr else None)
        # Diagram > Ports
        for key, text, mode in (('port_mode_in', 'In', 'input'), ('port_mode_out', 'Out', 'output'),
                                ('port_mode_inout', 'InOut', 'inout')):
            act(key, text, None if ro else each(PortIoItem, lambda p, m=mode: self.change_port_mode(p, m)))
        act('equidistant', 'Equidistant Ports', None if ro else each(InstanceItem, self.equidistant))
        # Diagram > Signals
        act('net_comment', 'Edit...', None if ro else nets(self.net_comment))
        act('net_highlight', 'Single Level', nets(self._highlight))
        act('net_clear_highlight', 'Clear All', lambda: self._highlight(''))
        act('net_change_style', 'Change Style', None if ro else nets(self.change_style))
        act('net_add_port_io', 'Add Port I/O',
            None if ro else each(WireItem, lambda w: None if (w.start and w.end) else self.add_port_io_for(w)))
        # Diagram > Text: show / hide the name of the selected nets and ports
        act('text_show', 'Show Text', None if ro else lambda: self._set_text_visible(True))
        act('text_hide', 'Hide Text', None if ro else lambda: self._set_text_visible(False))
        # Diagram: connect (not implemented), Port Map Frame, Update, Compiler Directives
        act('connect', 'Connect', None, 'Alt+C')
        act('portmap_enable', 'Enable', None if ro else each(InstanceItem, lambda i: self._set_portmap(i, True)))
        act('portmap_disable', 'Disable', None if ro else each(InstanceItem, lambda i: self._set_portmap(i, False)))
        act('portmap_edit', 'Edit...', lambda: [self.component_properties(i, 'portmap')
                                                for i in self._sel(InstanceItem)[:1]])
        act('update_interface', 'Interface...', None if ro else each(InstanceItem, self.update_interface))
        act('compiler_directives', 'Compiler Directives...', lambda: self.tabs.setCurrentIndex(3))
        act('check_design', 'Check Design', self.run_checks)
        # Standard toolbar / File: New, Back / Forward, Open Up, Print
        from PySide6.QtWidgets import QMenu as _QMenu
        hist = EC.History.of(mgr if mgr is not None else self)
        new_content = act('new_content', 'Design Content...', mgr.new_unit if mgr else None)
        new_tb = act('new_testbench', 'Test Bench...')
        a_new = act('new', 'New', mgr.new_unit if mgr else None)
        new_menu = _QMenu(self)
        new_menu.addAction(new_content); new_menu.addAction(new_tb)
        a_new.setMenu(new_menu)
        act('open_up', 'Open Up', (lambda: EC.open_up(self)) if mgr else None)
        act('back', 'Back', lambda: hist.go(-1))
        act('forward', 'Forward', lambda: hist.go(1))
        act('print', 'Print...', lambda: EC.print_diagram(self, self.scene))
        act('print_window', 'Print Window...', lambda: EC.print_diagram(self, self.scene, self.canvas))
        act('document', 'Single Level', lambda: EC.document_single_level(
            self, self.scene, self.bd.unit, f'{self.bd.library}/{self.bd.unit}/{self.bd.view}',
            generate_bd(self.bd)[0], ''))
        # Edit: Find / Replace, Align
        act('find', 'Find...', lambda: self.find_replace(False))
        act('replace', 'Replace...', lambda: self.find_replace(True))
        for key, text, how in (('align_left', 'Align Left', 'left'), ('align_center', 'Align Center', 'center'),
                               ('align_right', 'Align Right', 'right'), ('align_top', 'Align Top', 'top'),
                               ('align_middle', 'Align Middle', 'middle'),
                               ('align_bottom', 'Align Bottom', 'bottom')):
            act(key, text, None if ro else
                (lambda checked=False, h=how: self._moved(EC.align(self._ordered_selection(), h))))
        act('distribute_h', 'Distribute Horizontally',
            None if ro else (lambda: self._moved(EC.distribute(self.scene.selectedItems(), True))))
        act('distribute_v', 'Distribute Vertically',
            None if ro else (lambda: self._moved(EC.distribute(self.scene.selectedItems(), False))))
        # Diagram: Copy Picture, connectivity tables (IBD)
        act('copy_picture', 'Copy Picture', self.copy_picture)
        act('edit_ibd', 'Edit as IBD', lambda: self.connectivity_table(editable=not ro))
        act('visualize_ibd', 'Visualize as IBD', lambda: self.connectivity_table(editable=False))
        # Tasks: the checks of the diagram are the Check flow here
        act('check', 'Run Single', self.run_checks)
        act('connect_by_name', 'Connect By Name', None if ro else self.connect_by_name)
        act('paste_system', 'Paste from system clipboard', None if ro else self.paste_system)
        # Add > Comment Text, Add > Panel
        for mode, text in (('comment', 'Comment Text'), ('panel', 'Add Panel')):
            a = QAction(text, self)
            a.setCheckable(True)
            a.triggered.connect(lambda checked=False, m=mode: self.set_mode(m))
            a.setEnabled(not ro)
            self.mode_actions[mode] = a
            self.mode_group.addAction(a)
            self.toolbar_actions[mode] = a
        # Window / Help
        act('component_browser', 'Component Browser', self.show_component_browser)
        act('help_manuals', 'Help and Manuals', EC.open_user_guide, 'F1')
        act('regex_help', 'Regular Expressions', lambda: EC.show_regex_help(self))
        self._history = hist
        hist.visited(self)
        self.scene.selectionChanged.connect(self.update_menu_states)
        # Options / Window / Help: the Design Manager's dialogs and windows
        act('main_settings', 'Main...', (lambda: mgr.main_settings(self)) if mgr else None)
        act('verilog_options', 'Verilog...', (lambda: mgr.verilog_options(self)) if mgr else None)
        act('log_window', 'Log Window', lambda: (self.log_dock.show(), self.log_dock.raise_()))
        act('design_manager', 'Design Manager',
            (lambda: (mgr.show(), mgr.raise_(), mgr.activateWindow())) if mgr else None)
        act('shortcuts_help', 'Keyboard Shortcuts', (lambda: mgr._show_shortcuts(self)) if mgr else None)

    # -- panels (panels.PanelCommands) ---------------------------------------------------
    def panels_model(self) -> list:
        return self.bd.panels

    def panel_new_id(self) -> str:
        return self._new_id('pn')

    def panels_reload(self):
        self._reload_scene()

    def panels_changed(self):
        self.changed()

    # -- comment texts ------------------------------------------------------------------
    def add_comment(self, pos: QPointF):
        """Add > Comment Text: a free text at `pos`, typed in a dialog (empty: nothing added)."""
        text, ok = QInputDialog.getMultiLineText(self, 'Comment Text', 'Text:')
        if not ok or not text.strip():
            return
        c = BdComment(self._new_id('c'), text.rstrip())
        c.x, c.y = pos.x(), pos.y()
        self._size_comment(c)
        self.bd.comments.append(c)
        self._reload_scene()
        self.scene.clearSelection()
        it = self.scene.items_by_id.get(c.id)
        if it is not None:
            it.setSelected(True)
        self.changed()

    def paste_system(self):
        """Edit > Paste Special > Paste from system clipboard: the text on the system clipboard as a
        comment text in the middle of the window."""
        text = QApplication.clipboard().text().rstrip()
        if not text:
            return
        pos = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        c = BdComment(self._new_id('c'), text)
        c.x, c.y = _snap(pos.x()), _snap(pos.y())
        self._size_comment(c)
        self.bd.comments.append(c)
        self._reload_scene()
        self.scene.clearSelection()
        it = self.scene.items_by_id.get(c.id)
        if it is not None:
            it.setSelected(True)
        self.changed()

    @staticmethod
    def _size_comment(c: BdComment):
        """Box of a comment text: its widest line, one line height per line."""
        fm = QFontMetricsF(MONO)
        lines = c.text.split('\n')
        c.w = max(fm.horizontalAdvance(line) for line in lines) + 8
        c.h = fm.height() * len(lines) + 2

    def edit_comment(self, c: BdComment):
        """Double-click on a comment text: edit it (emptied: the comment goes)."""
        text, ok = QInputDialog.getMultiLineText(self, 'Comment Text', 'Text:', c.text)
        if not ok or text == c.text:
            return
        if text.strip():
            c.text = text.rstrip()
            self._size_comment(c)
        else:
            self.bd.comments.remove(c)
        self._reload_scene()

    # -- selection helpers, Align -------------------------------------------------------
    def _track_selection(self):
        """Keep the selected items in the order the user selected them (Align lines up on the first)."""
        sel = self.scene.selectedItems()
        order = [i for i in getattr(self, '_sel_order', []) if i in sel]
        order += [i for i in sel if i not in order]
        self._sel_order = order

    def _ordered_selection(self) -> list:
        self._track_selection()
        return list(self._sel_order)

    def _moved(self, moved: bool):
        """After Align / Distribute: nets follow, one undo step when something moved."""
        if moved:
            self._reload_scene()

    def copy_picture(self):
        """Diagram > Copy Picture: the selection (or the diagram) as a picture on the clipboard."""
        EC.copy_picture(self.scene)
        self.statusBar().showMessage('Picture copied to the clipboard', 3000)

    def changeEvent(self, e):
        """Activating the window records it in the Back / Forward history."""
        if e.type() == QEvent.ActivationChange and self.isActiveWindow() and getattr(self, '_history', None):
            self._history.visited(self)
            self.update_menu_states()
        super().changeEvent(e)

    # -- Find / Replace ---------------------------------------------------------------------
    def find_replace(self, replace: bool):
        """Edit > Find... / Replace...: the legacy Find and Replace dialog (find_dialog.py) over the
        texts of the diagram, by the legacy tool's object kinds: component instance / name / library
        and port names, nets (a net renamed here is renamed everywhere), embedded blocks, frames,
        comment texts, compiler directives, the Signal Table and the parameters. One dialog per
        window, kept between uses."""
        from .find_dialog import BD_KINDS, FindReplaceDialog
        dlg = getattr(self, '_find_dialog', None)
        if dlg is None:
            dlg = FindReplaceDialog(self, self._find_fields, self._find_done, BD_KINDS, self._diagram_name(),
                                    replace, self.scene.readonly)
            self._find_dialog = dlg
        dlg.open_tab(replace)

    def _diagram_name(self) -> str:
        return f'{self.bd.library}/{self.bd.unit}/{self.bd.view}'

    def _find_done(self):
        """After a replacement: draw the diagram again, one undo step."""
        self._reload_scene()
        self.signals_tab.set_rows(self.bd.signals, self.bd.signals_sheet)
        self.changed()

    def _find_fields(self) -> list:
        """The texts Find and Replace searches, as find_dialog.TextField records."""
        from .find_dialog import TextField
        bd = self.bd

        def select(oid):
            def run(add=False):
                it = self.scene.items_by_id.get(oid) or self.scene.wire_items.get(oid)
                if it is not None:
                    self.tabs.setCurrentIndex(0)
                    if not add:
                        self.scene.clearSelection()
                    it.setSelected(True)
                    self.canvas.centerOn(it)
            return run

        def attr(obj, name):
            return (lambda: str(getattr(obj, name) or '')), (lambda v: setattr(obj, name, v))

        def field(kind, name, obj, a, oid, writable=True, editor=None):
            """A text of object `oid`; `editor(item, span)` opens it in place with the match selected."""
            g, w = attr(obj, a)
            sel = select(oid)

            def show(span):
                EC.mark_text(None, None)
                sel(False)
                item = self.scene.items_by_id.get(oid)
                if item is None:
                    return
                if editor is not None and not self.scene.readonly:
                    self.activateWindow()
                    editor(item, span)
                elif hasattr(item, 'find_span'):
                    EC.mark_text(item, span)
            return TextField(kind, name, g, w if writable else None, show, sel)

        def line(kind):
            return lambda item, span: self.edit_component_text_inline(item, kind, span)

        out = []
        for i in bd.instances:
            out.append(field('Component Instance', f'Instance {i.name} ({i.unit})', i, 'name', i.id,
                             editor=line('instance')))
            out.append(field('Component Name', f'Component of {i.name}', i, 'unit', i.id, False, line('unit')))
            out.append(field('Component Library', f'Library of {i.name}', i, 'library', i.id, False,
                             line('library')))
            for p in i.pins:
                out.append(field('Component Port Name', f'Port {p.name} of {i.name}', p, 'name', i.id, False))
                if p.bounds:
                    out.append(field('Component Port Type/Range', f'Range of port {p.name} of {i.name}', p,
                                     'bounds', i.id, False))
            for prm in i.params:
                out.append(field('Component Generic Interface', f'Parameter {prm.name} of {i.name}', prm,
                                 'value', i.id))
            if getattr(i, 'portmap_text', ''):
                out.append(field('Component Port Map Frame', f'Port map frame of {i.name}', i, 'portmap_text',
                                 i.id))
        seen = set()
        for w in bd.wires:
            if w.net and w.net not in seen:
                seen.add(w.net)
                sel = select(w.id)

                def show_net(span, wid=w.id, net=w.net, sel=sel):
                    EC.mark_text(None, None)
                    sel(False)
                    wi = self.scene.wire_items.get(wid)
                    if wi is None or self.scene.readonly:
                        return
                    self.activateWindow()
                    pos = wi.label_pos(QFontMetricsF(MONO).horizontalAdvance(net))
                    self.edit_net_inline(net, pos, span)
                out.append(TextField('Signal Name', f'Signal {w.net}', lambda n=w.net: n,
                                     lambda v, n=w.net: self._rename(n, v), show_net, sel))
        for e in bd.embedded:
            out.append(field('Embedded Block Name', f'Embedded block {e.name}', e, 'name', e.id))
            out.append(field('Embedded Block Number', f'Number of embedded block {e.name}', e, 'number', e.id,
                             False))
            out.append(field('Embedded Block Text', f'Text of embedded block {e.name}', e, 'text', e.id,
                             editor=(lambda item, span: self.edit_embedded_text_inline(item, span)
                                     if item.text_rect() is not None else EC.mark_text(None, None))))
        for fr in bd.frames:
            out.append(field('Frame', f'Frame {fr.name}', fr, 'name', fr.id))
            out.append(field('Frame', f'Frame {fr.name} range / condition', fr, 'spec', fr.id))
        for c in bd.comments:
            if not c.group:
                out.append(field('Comment text', 'Comment text', c, 'text', c.id))
        for a, name in (('pre_module_directives', 'Pre-module directives'),
                        ('post_module_directives', 'Post-module directives'),
                        ('end_module_directives', 'End-module directives')):
            if getattr(bd, a):
                g, w = attr(bd, a)
                out.append(TextField('Compiler Directives', name, g, w,
                                     lambda span: self.tabs.setCurrentIndex(3), None))

        def table(k):
            return lambda span: self.tabs.setCurrentIndex(k)
        for s in bd.signals:
            for a, kind in (('name', 'Signals Name Column'), ('mode', 'Signals Mode Column'),
                            ('type', 'Signals Type Column'), ('bounds', 'Signals Bounds Column'),
                            ('comment', 'Signals Comment Column'), ('value', 'Signals Initial Column'),
                            ('delay', 'Signals Delay Column'), ('group', 'Group Column/Row')):
                if not getattr(s, a, ''):
                    continue
                g, w = attr(s, a)
                if a == 'name':
                    w = (lambda v, n=s.name: self._rename(n, v))
                elif a == 'mode':
                    w = None
                out.append(TextField(kind, f'{kind} ({s.name})', g, w, table(1), None))
        for prm in bd.parameters:
            for a, kind in (('name', 'Generics Name Column'), ('value', 'Generics Value Column'),
                            ('type', 'Generics Type Column'), ('comment', 'Generics Comment Column')):
                if getattr(prm, a, ''):
                    g, w = attr(prm, a)
                    out.append(TextField(kind, f'{kind} ({prm.name})', g, w, table(2), None))
        return out

    # -- connectivity table (IBD) ------------------------------------------------------------
    def connectivity_rows(self) -> list[tuple[str, str, str, str]]:
        """One row per net: (net, bounds, what drives it, what it goes to), as the interface-based
        view lists the connections of a diagram."""
        bd = self.bd
        nets: dict[str, dict] = {}

        def row(net):
            return nets.setdefault(net, {'bounds': '', 'from': [], 'to': []})
        for s in bd.signals:
            row(s.name)['bounds'] = s.bounds
        for i in bd.instances:
            for p in i.pins:
                if p.net:
                    side = 'from' if p.mode == 'output' else 'to'
                    row(p.net)[side].append(f'{i.name}.{p.name}')
                    if p.mode == 'inout':
                        row(p.net)['from'].append(f'{i.name}.{p.name}')
        for p in bd.port_ios:
            if p.name:
                r = row(p.name)
                (r['from'] if p.mode == 'input' else r['to']).append(f'port {p.name} ({p.mode})')
        for w in bd.wires:
            if w.net and (w.start.startswith('emb:') or w.end.startswith('emb:')):
                e = next((e for e in bd.embedded if f'emb:{e.id}' in (w.start, w.end)), None)
                if e is not None:
                    row(w.net)['to'].append(f'embedded {e.name}')
        return [(n, d['bounds'], ', '.join(dict.fromkeys(d['from'])), ', '.join(dict.fromkeys(d['to'])))
                for n, d in sorted(nets.items(), key=lambda kv: kv[0].lower())]

    def connectivity_table(self, editable: bool):
        """Diagram > Edit as IBD / Visualize as IBD: the connectivity of the diagram as a table, one row
        per net (name, bounds, drivers, loads). In Edit as IBD a net is renamed by editing its name."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTableWidget, QTableWidgetItem, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(('Edit as IBD' if editable else 'Visualize as IBD') + f' - {self.bd.unit}')
        lay = QVBoxLayout(dlg)
        rows = self.connectivity_rows()
        t = QTableWidget(len(rows), 4)
        t.setHorizontalHeaderLabels(['Net', 'Bounds', 'Driven by', 'Connects to'])
        for r, vals in enumerate(rows):
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c != 0 or not editable:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        t.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(t)
        box = QDialogButtonBox(QDialogButtonBox.Ok | (QDialogButtonBox.Cancel if editable else QDialogButtonBox.NoButton))
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        lay.addWidget(box)
        dlg.resize(820, 480)
        if dlg.exec() and editable:
            changed = False
            for r, vals in enumerate(rows):
                new = t.item(r, 0).text().strip()
                if new and new != vals[0]:
                    self._rename(vals[0], new)
                    changed = True
            if changed:
                self._reload_scene()
                self.signals_tab.set_rows(self.bd.signals, self.bd.signals_sheet)
                self.changed()

    def _set_text_visible(self, on: bool):
        """Diagram > Text > Show / Hide Text for the selected nets and ports."""
        for w in self._sel(WireItem):
            if w.show_text != on:
                self.toggle_net_text(w)
        for p in self._sel(PortIoItem):
            if p.show_text != on:
                self.toggle_port_text(p)

    def update_menu_states(self):
        """Grey the selection commands that have nothing to act on, as the legacy tool does: Cut / Copy /
        Delete without a selection, Paste with nothing copied, Align with fewer than two objects, Back /
        Forward at the ends of the window history, then the Diagram commands by what is selected."""
        acts = self.toolbar_actions
        sel = self._ordered_selection()
        EC.update_edit_states(acts, sel, bool(getattr(self, '_clipboard', None)), self.scene.readonly)
        copyable = any(isinstance(i, (InstanceItem, FrameItem)) for i in sel)
        acts['copy'].setEnabled(copyable)
        acts['cut'].setEnabled(copyable and not self.scene.readonly)
        hist = getattr(self, '_history', None)
        if hist is not None:
            acts['back'].setEnabled(hist.can_go(-1))
            acts['forward'].setEnabled(hist.can_go(1))
        acts['paste_system'].setEnabled(not self.scene.readonly and bool(QApplication.clipboard().text().strip()))
        self.update_panel_states(self.scene.readonly)
        if self.scene.readonly:
            return
        ports, wires, insts = self._sel(PortIoItem), self._sel(WireItem), self._sel(InstanceItem)
        enable = {
            'port_mode_in': ports, 'port_mode_out': ports, 'port_mode_inout': ports,
            'equidistant': insts, 'net_comment': wires, 'net_highlight': wires, 'net_change_style': wires,
            'net_add_port_io': [w for w in wires if not (w.start and w.end)],
            'text_show': wires or ports, 'text_hide': wires or ports,
            'portmap_enable': insts, 'portmap_disable': insts, 'portmap_edit': insts, 'update_interface': insts,
        }
        for key, objs in enable.items():
            a = self.toolbar_actions.get(key)
            if a is not None:
                a.setEnabled(bool(objs))
        # Change Mode shows the mode of the selected port as a check mark
        mode = ports[0].mode if len(ports) == 1 else None
        for key, m in (('port_mode_in', 'input'), ('port_mode_out', 'output'), ('port_mode_inout', 'inout')):
            a = self.toolbar_actions[key]
            a.setCheckable(True)
            a.setChecked(mode == m)

    def _refresh_view(self):
        """View > Refresh: rebuild the scene and repaint."""
        self._reload_scene()
        self.canvas.viewport().update()

    def _show_grid(self, on: bool):
        """View > Grid: show / hide the grid dots."""
        self.canvas.show_grid = on
        self.canvas.viewport().update()

    def eventFilter(self, obj, e):
        """Object Tips off: no tool tips on the canvas. While an in-place editor is open: a click on the
        canvas, focus loss or Esc cancels it (Esc is kept from the window's Select shortcut).
        """
        if obj is self.canvas.viewport() and e.type() == QEvent.ToolTip and not getattr(self, 'object_tips', True):
            return True                         # Object Tips off
        ie = getattr(self, '_inline_editor', None)
        if ie and obj is self.canvas.viewport() and e.type() == QEvent.MouseButtonPress:
            ie[1](False)
            self._inline_editor = None
        if ie and obj is ie[0]:
            if e.type() == QEvent.ShortcutOverride and e.key() == Qt.Key_Escape:
                e.accept()              # Esc belongs to the editor, not to the window's Select shortcut
                return True
            if e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape:
                ie[1](False)
                return True
            if e.type() == QEvent.FocusOut and e.reason() != Qt.ActiveWindowFocusReason:
                # clicking elsewhere cancels, as in the legacy editor; another window taking the focus
                # (the Find dialog) leaves the box open with its selection
                ie[1](False)
        return super().eventFilter(obj, e)

    # -- connecting by dragging -------------------------------------------------------
    def _dangling_end_at(self, p: QPointF) -> tuple[BdWire, str, int] | None:
        """The dangling net end (red circle) nearest to p within the port grab distance, as
        (wire, 'start' | 'end', point index)."""
        best = None
        for w in self.bd.wires:
            for which, k in (('start', 0), ('end', -1)):
                if getattr(w, which) or not w.points:
                    continue
                ex, ey = w.points[k]
                d = abs(ex - p.x()) + abs(ey - p.y())
                if abs(ex - p.x()) <= PIN_GRAB and abs(ey - p.y()) <= PIN_GRAB and (best is None or d < best[0]):
                    best = (d, w, which, k)
        return best[1:] if best else None

    def _turn_port_to_end(self, pio: BdPortIo, end: list[float]):
        """After a net end is put on a port's wire end: the port faces its net (port_side()),
        which may be the other side than before; shift the port so that its wire end on that
        side is exactly on the net end (the port "turns" around the net end, as in the legacy tool)."""
        side = self.scene.port_side(pio)
        pio.x, pio.y = end[0] - side * PORT_EDGE, end[1]

    def port_dropped(self, pio: BdPortIo):
        """A free port dragged so that its wire end (the tip of its stub, not its middle) lands
        on a dangling net end or on the body of a net connects to that net and takes its name.
        The port stays where it was dropped: the net comes to the tip."""
        if any(True for _ in self.scene._attached(f'pio:{pio.id}')):
            return
        tip = QPointF(*self.scene.port_edge(pio))
        hit = self._dangling_end_at(tip)
        if hit is not None:
            # the dangling end moves onto the tip (its last segment keeps its right angle)
            w, which, k = hit
            _shift_end(w, which, tip.x() - w.points[k][0], tip.y() - w.points[k][1])
            w.points = _simplify(w.points)
            setattr(w, which, f'pio:{pio.id}')
            self._port_takes_net(pio, w.net)
            self._turn_port_to_end(pio, w.points[k])
        else:
            net = self.scene.net_at(tip)
            if net is None:
                return
            net_wire = next(x for x in self.bd.wires if net[0] == f'net:{x.id}')
            self._attach_port_to_net(pio, tip, net[1], net_wire)
        self.statusBar().showMessage(f'Port connected to net {pio.name}', 4000)
        QTimer.singleShot(0, self._reload_scene)

    def end_dropped(self, w: BdWire):
        """A dangling net end dropped on a free pin or on a port connects to it.
        On a port, the net takes the port's name."""
        for which, k in (('start', 0), ('end', -1)):
            if getattr(w, which):
                continue
            hit = self.scene.pin_at(QPointF(*w.points[k]))
            if hit is None:
                continue
            ref, pt, pin, pio = hit
            if pin is not None:
                if pin.net not in ('', w.net):
                    self.statusBar().showMessage(f'Pin {pin.name} is already on net {pin.net}', 5000)
                    continue
                pin.net = w.net
            setattr(w, which, ref)
            w.points[k] = [pt.x(), pt.y()]
            w.points = _simplify(_orthogonal(w.points))
            if pio is not None and not pio.name:
                self._port_takes_net(pio, w.net)        # a port with no name yet takes the net's
            elif pio is not None and pio.name != w.net:
                self._rename(w.net, pio.name)
                self._ensure_port(pio.name, pio.mode)
            QTimer.singleShot(0, self._reload_scene)

    def _attach_port_to_net(self, pio: BdPortIo, tip: QPointF, q: QPointF, net_wire: BdWire):
        """Connect a port whose wire end is at tip to the body of an existing net at q (the
        point of the net nearest to the tip): a junction dot on the net at q, and a net from the
        tip to the dot (none to see when the tip is on the net). The port does not move. The
        port takes the net's name; the short net shows no name of its own (the net's name is
        already on the net and on the port)."""
        j = BdJunction(self._new_id('j'), q.x(), q.y())
        self.bd.junctions.append(j)
        a, b = [tip.x(), tip.y()], [q.x(), q.y()]
        w = BdWire(self._new_id('w'), net_wire.net, _route(a, [], b) if a != b else [a, b],
                   f'pio:{pio.id}', f'jct:{j.id}')
        w.show_text = False
        self.bd.wires.append(w)
        self._port_takes_net(pio, net_wire.net)

    def _port_takes_net(self, pio: BdPortIo, net: str):
        """Rename a port to the net it is connected to; the net becomes a port of the module."""
        old = pio.name
        pio.name = net
        sig = next((s for s in self.bd.signals if s.name == net), None)
        old_sig = next((s for s in self.bd.signals if s.name == old), None)
        if sig is None:
            self._ensure_port(net, pio.mode, old_sig.bounds if old_sig else '')
        else:
            sig.mode = pio.mode
        if old != net and not any(p.name == old for p in self.bd.port_ios) \
                and not any(w.net == old for w in self.bd.wires):
            self.bd.signals = [s for s in self.bd.signals if s.name != old]

    def apply_net_text(self, old: str, text: str):
        """Apply the text typed for a net. Accepted forms:
            name                      rename only
            name[msb:lsb]             rename, and make the net that bus
            name : type[msb:lsb]      the legacy form; type is wire, reg, logic... optionally "signed"
        A part left out keeps its current value. A new name that already exists joins the two
        nets after a confirmation."""
        m = re.fullmatch(r'\s*([A-Za-z_][\w$]*)\s*(?::\s*([A-Za-z_]\w*(?:\s+signed)?)?\s*)?(\[[^\]]*\])?\s*', text)
        if m is None:
            self.statusBar().showMessage(f'"{text}" is not "name : type[bounds]"', 5000)
            return
        new, kind, bounds = m.group(1), m.group(2), m.group(3)
        sig = next((s for s in self.bd.signals if s.name == old), None)
        changed = False
        if kind and sig is not None:
            base, signed = kind.split()[0], kind.endswith('signed')
            if (sig.type, sig.signed) != (base, signed):
                sig.type, sig.signed = base, signed
                changed = True
        if bounds is not None and sig is not None and sig.bounds != bounds:
            sig.bounds = bounds
            changed = True
        if new != old:
            if any(s.name == new for s in self.bd.signals) and not QMessageBox.question(
                    self, 'Rename net', f'A signal "{new}" already exists. Connect the two nets?') == QMessageBox.Yes:
                return
            self._rename(old, new)
            changed = True
        if changed:
            self._reload_scene()

    def rename_net(self, old: str):
        """Rename a net through a dialog (F2 / Edit > Rename net); an existing name joins the two nets
        after confirmation.
        """
        if not old or self.scene.readonly:
            return
        new, ok = QInputDialog.getText(self, 'Rename net', f'New name for net "{old}":', text=old)
        new = new.strip()
        if not ok or not new or new == old:
            return
        if any(s.name == new for s in self.bd.signals) and not QMessageBox.question(
                self, 'Rename net', f'A signal "{new}" already exists. Connect the two nets?') == QMessageBox.Yes:
            return
        self._rename(old, new)
        self._reload_scene()

    def _rename(self, old: str, new: str):
        """Rename a net everywhere: wires, pins, ports and the signal table."""
        bd = self.bd
        for w in bd.wires:
            if w.net == old:
                w.net = new
        for inst in bd.instances:
            for p in inst.pins:
                if p.net == old:
                    p.net = new
        for p in bd.port_ios:
            if p.name == old:
                p.name = new
        if any(s.name == new for s in bd.signals):
            bd.signals = [s for s in bd.signals if s.name != old]
        else:
            for s in bd.signals:
                if s.name == old:
                    s.name = new

    def delete_selected(self):
        """Delete the selection and refresh the Signal Table."""
        if self.scene.delete_selected():
            self.signals_tab.set_rows(self.bd.signals, self.bd.signals_sheet)

    def _double_click(self, e):
        """Double-click on the canvas: an embedded block opens / creates its Text view, a component
        name line is edited in place, elsewhere on a component its unit is opened (Open Down); the
        rest goes to the scene.
        """
        item = self.canvas.itemAt(e.position().toPoint())
        at = self.canvas.mapToScene(e.position().toPoint())
        if self.scene.mode == 'select':
            # a port name, even under a net drawn over it: it comes from the component's interface,
            # so as in the legacy tool it stays selected and cannot be edited here
            for it in self.canvas.items(e.position().toPoint()):
                label = it.pin_label_at(at) if isinstance(it, InstanceItem) else None
                if label is not None and not it.name_at(at):
                    self.scene.clearSelection()
                    self.scene.select_text(it, 'pin:' + label.name)
                    self.statusBar().showMessage('Cannot edit read-only text', 5000)
                    return
        if isinstance(item, EmbeddedItem) and self.scene.mode == 'select' and not self.scene.readonly:
            self.embedded_double_click(item, self.canvas.mapToScene(e.position().toPoint()))
            return
        if isinstance(item, InstanceItem) and self.scene.mode == 'select':
            # On a name line: edit that line in place. Elsewhere on the component: open it.
            kind = item.name_at(at)
            if kind and not self.scene.readonly:
                self.edit_component_text_inline(item, kind)
            else:
                self.open_instance(item.obj)
            return
        FsmGraphicsView.mouseDoubleClickEvent(self.canvas, e)

    def open_down(self):
        """Open Down (Ctrl+D): open the unit of the selected component."""
        inst = next((i.obj for i in self.scene.selectedItems() if isinstance(i, InstanceItem)), None)
        if inst:
            self.open_instance(inst)

    def open_instance(self, inst: BdInstance):
        """Open the unit an instance instantiates (through the Design Manager)."""
        if self.context is not None:
            EC.remember_parent(self.context.manager, inst.unit, self.context.unit)
            self.context.manager.open_unit_by_name(inst.unit, inst.library)

    # -- output ------------------------------------------------------------------------
    def regenerate(self):
        """Generate the HDL in memory and show it with the generator's warnings."""
        self.log.clear()
        text, warnings = generate_bd(self.bd)
        self.code.set_code(text)
        ext = 'sv' if self.bd.language == 'systemverilog' else 'v'
        self.code_title.setText(f'<b>Generated HDL</b> — {self.bd.unit}.{ext} ({LANG_LABEL[self.bd.language]}) '
                                f'— {len(self.bd.instances)} instances, {text.count(chr(10))} lines')
        for w in warnings:
            self.log.addItem(w)
        if not warnings:
            self.log.addItem('Generation OK - no warnings')

    def update_title(self):
        """legacy title: "Project p: lib/unit/view * (Block Diagram)", the '*' right after the view
        when there are unsaved changes; the page shown replaces "(Block Diagram)", e.g.
        "(Signals for struct)"."""
        b = self.bd
        ro = ' (Read-only)' if self.context is not None and self.context.readonly else ''
        proj = f'Project {self.context.project_name}: ' if self.context is not None else ''
        page = {1: f'Signals for {b.view}', 2: f'Parameters for {b.view}'}.get(
            self.tabs.currentIndex() if hasattr(self, 'tabs') else 0, 'Block Diagram')
        self.setWindowTitle(f'{proj}{b.library}/{b.unit}/{b.view}{" *" if self.dirty else ""}{ro} ({page})')

    # -- Structure Navigator (Diagram Browser) -------------------------------------------
    def _fill_navigator(self):
        """The legacy tool Structure Navigator tree: Signal Table, Parameters Table, then the diagram
        with its Declarations/Statements (Declarations, User Declarations, Compiler Directives)
        and its Embedded Diagrams (one entry per embedded block)."""
        nav = self.navigator
        nav.clear()

        from .diagram_browser import nav_icon

        def node(parent, text, target, bold=False, icon_name=None):
            """Add a navigator entry under `parent` that leads to `target` (('page', n) or ('embedded', id))."""
            it = QTreeWidgetItem(parent, [text])
            it.setData(0, Qt.UserRole, target)
            if icon_name:
                it.setIcon(0, nav_icon(icon_name))
            if bold:
                f = it.font(0); f.setBold(True); it.setFont(0, f)
            return it
        node(nav, 'Signal Table', ('page', 1), True, 'signals')
        node(nav, 'Parameters Table', ('page', 2), True, 'params')
        top = node(nav, self.bd.unit, ('page', 0), True, 'block')
        decl = node(top, 'Declarations/Statements', ('page', 3))
        node(decl, 'Declarations', ('page', 1), icon_name='decl')
        node(decl, 'User Declarations', ('page', 3), icon_name='decl')
        node(decl, 'Compiler Directives', ('page', 3), icon_name='compdir')
        emb = node(top, 'Embedded Diagrams', ('page', 0), icon_name='embedded')
        for eb in sorted(self.bd.embedded, key=lambda e: e.number):
            node(emb, eb.name, ('embedded', eb.id), icon_name='embedded')
        top.setExpanded(True)
        self._sync_navigator()

    def _navigator_clicked(self, item, _col):
        """A click in the Structure Navigator: show that page, or select and centre that embedded block."""
        kind, target = item.data(0, Qt.UserRole) or (None, None)
        if kind == 'page':
            self.tabs.setCurrentIndex(target)
        elif kind == 'embedded':
            # show the diagram and select / centre the embedded block
            self.tabs.setCurrentIndex(0)
            it = self.scene.items_by_id.get(target)
            if it is not None:
                self.scene.clearSelection()
                it.setSelected(True)
                self.canvas.centerOn(it)

    def _sync_navigator(self):
        """Highlight the navigator entry of the page shown (as the legacy tool does)."""
        if not hasattr(self, 'navigator'):
            return
        want = self.tabs.currentIndex()
        self.navigator.blockSignals(True)
        if want in (1, 2):                  # a table page: nothing selected, as in the legacy tool
            self.navigator.setCurrentItem(None)
            self.navigator.clearSelection()
        else:
            self.navigator.setCurrentItem(self.navigator.topLevelItem(2))
        self.navigator.blockSignals(False)
        self.browser.show_content(want not in (1, 2))

    def save(self):
        """File > Save through the project; clears the '*' when saved."""
        if self.context is not None and self.context.save(self.bd, self):
            self.dirty = False
            self.undo_stack.mark_clean()        # undo back to here shows no '*'
            self.update_title()

    def generate(self):
        """Tasks > Generate this diagram's HDL (from the model in memory)."""
        if self.context is not None:
            self.context.generate(self.bd, self)

    def open_generated(self):
        """HDL > View Generated HDL: open the generated file in the text editor."""
        if self.context is not None:
            self.context.open_generated(self.bd)

    def closeEvent(self, e):
        """Ask Save / Discard / Cancel for unsaved changes, remember the view position, release the locks."""
        if self.dirty:
            r = QMessageBox.question(self, 'Unsaved changes', 'Save changes to this block diagram?',
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                e.ignore()
                return
            if r == QMessageBox.Save:
                self.save()
        save_view_state(self._view_key(), self.canvas.state())
        if self.context is not None:
            self.context.release()
        e.accept()
