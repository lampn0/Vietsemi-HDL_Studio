"""State diagram canvas: the graphics items of a state machine and the scene that edits it.

Items (all QGraphicsItem subclasses, each holding its model object in `obj`):
    NodeItem          base of every node transitions attach to (position, outline point)
      StateItem       state / wait state / hierarchical state
      JunctionItem    IF / CASE junction (diamond)
      LinkItem        link to a state (yellow arrow + target name)
      PointItem       clock / reset / enable / interrupt / recovery point
    _BoxItem          movable text box made of sections
      TransitionLabel the condition / actions box of a transition
      StateActionsBox the entry / state / exit actions of a state
    DeclBlockItem     a declaration block at the top of the diagram (Global Actions, ...)
    TransitionItem    the transition line (route points, end handles, priority circle)

FsmScene builds those items from a Machine (load), handles the add tools and the editing
gestures, writes every change into the model and emits `changed_model`. FsmGraphicsView is
the view widget: zoom, pan, View Area, grid, keyboard nudges.

Coordinates are scene units = legacy units * SCALE (1/75). When an object still has the geometry
read from the legacy file (the `orig` dicts of the model) it is drawn exactly as the legacy tool drew it;
once its text changes, HDL Studio lays it out itself.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QTransform, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPainterPathStroker, QPen,
                           QPolygonF)
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem, QGraphicsPathItem, QGraphicsPolygonItem, QGraphicsScene, QGraphicsView, QInputDialog,
                               QRubberBand)

from formats.import_sm import SCALE
from model import Junction, Link, Machine, Point, State, Transition, category_label

# The legacy editors' grid: 1000 database units. Everything placed or moved lands on it.
GRID = 1000 * SCALE


# View > Snap to Grid (on by default, as in the legacy tool)
SNAP_ON = [True]


def snap(v: float) -> float:
    """Round a coordinate to the legacy grid (1000 legacy units); unchanged with Snap to Grid off."""
    return round(v / GRID) * GRID if SNAP_ON[0] else v


def snap_point(p: QPointF) -> QPointF:
    """Round a point to the legacy grid."""
    return QPointF(snap(p.x()), snap(p.y()))

STATE_R = 28
STATE_FILL = QColor(0, 255, 255)        # The legacy tool 0,65535,65535
LINK_FILL = QColor(255, 255, 0)         # The legacy tool 65535,65535,0
LINK_TIP = 18       # a new link: its stub tip (where the legacy tool puts the cursor) this far left of its centre
JUNCTION_FILL = QColor(234, 156, 255)    # The legacy tool 59904,39936,65280
BOX_PEN = QPen(QColor(0, 120, 220), 1)
TRANS_BOX_COLOR = QColor(0, 128, 192)   # border of a transition's text box (as in the legacy tool)
ACTION_CELL = QColor(153, 217, 234)     # cells of entry / state / exit actions (as in the legacy tool)
ACTION_BORDER = QColor(156, 222, 255)   # border of a state's action block (the legacy tool 39936,56832,65280)
TEXT_LINE = 900 / 75                     # one text line of a legacy diagram (900 units, courier / Arial 8)
PRIO_R = 651 / 75                       # radius of a transition priority circle (as in the legacy tool)
ACTION_COLOR = QColor(0, 0, 0)          # transition / state action text: black (as in the legacy tool)
SEL_PEN = QPen(QColor(255, 120, 0), 2.5)
# diagram text in Arial, as the legacy tool on Windows draws its "courier" diagram fonts (see bd_editor)
TEXT_FONT = QFont('Arial', 8)
NAME_FONT = QFont('Arial', 8, QFont.Bold)
GRAB = 6.0          # pick distance for bend points, in scene units
MID_R = 4.0         # half size of the diamond in the middle of a selected transition's pieces of line


def _fm() -> QFontMetricsF:
    """Font metrics of the diagram text font."""
    return QFontMetricsF(TEXT_FONT)


# The legacy tool sizes (legacy units / 75): state radius 3000, junction diamond 3300, the arrow
# (pentagon) of links and points 2250 x 1000 with a 500 stub, recovery circle radius 900
DEFAULT_STATE_R = 3000 / 75
JUNCTION_HALF = 3300 / 75 / 2
PENT_W, PENT_H, STUB = 2250 / 75, 1000 / 75, 500 / 75
REC_R = 900 / 75
STATE_LINE = QColor(0, 128, 192)
HIER_FILL = QColor(117, 156, 255)        # hierarchical state (the legacy tool 29952,39936,65280)
HIER_LINE = QColor(0, 0, 128)
STATE_NAME_FONT = QFont('Arial', 10, QFont.Bold)
LABEL_FONT = QFont('Arial', 8)
LABEL_BOLD_FONT = QFont('Arial', 8, QFont.Bold)


def _pentagon() -> QPolygonF:
    """The yellow arrow of links and points, pointing right, centred on the origin."""
    w, h, t = PENT_W / 2, PENT_H / 2, PENT_H / 2
    return QPolygonF([QPointF(-w, -h), QPointF(w - t, -h), QPointF(w, 0), QPointF(w - t, h), QPointF(-w, h)])


def _geo_rect(g: list | None) -> QRectF | None:
    """A rectangle of a legacy geometry entry ([x0, y0, x1, y1, ...], relative to the node)."""
    return QRectF(QPointF(g[0], g[1]), QPointF(g[2], g[3])) if g else None


def _draw_geo_text(p: QPainter, g: list, text: str, font: QFont) -> None:
    """Draw a text where the legacy tool had it: on its saved baseline, left / centred / right in its
    saved extent as the legacy tool justified it (the font differs from the legacy tool's courier, so the justified
    edge is what stays where the legacy tool put it)."""
    fm = QFontMetricsF(font)
    x0, y0, x1, y1, ju, base = g
    p.setFont(font)
    for k, line in enumerate(text.split('\n')):
        w = fm.horizontalAdvance(line)
        x = (x0 + x1 - w) / 2 if ju == 0 else x1 - w if ju == 2 else x0
        y = (base if base is not None else y0 + 700 / 75) + k * TEXT_LINE
        p.drawText(QPointF(x, y), line)


def _handles(p: QPainter, r: QRectF) -> None:
    """Small black squares at the corners of a selected object (as in the legacy tool)."""
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(Qt.black)
    for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
        p.drawRect(QRectF(c.x() - 2.5, c.y() - 2.5, 5, 5))
    p.restore()


def _geo_sig(t, m) -> list:
    """See formats.import_sm._geo_sig: the line of a transition as read from the file."""
    from formats.import_sm import _geo_sig as sig
    return sig(t, m)


def _spline(path: QPainterPath, pts: list[QPointF]) -> None:
    """Continue `path` (at pts[0]) as a smooth curve through the points (Catmull-Rom spline as
    cubic Beziers), the way the legacy tool draws a transition with route points; two points: a line."""
    if len(pts) < 3:
        path.lineTo(pts[-1])
        return
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else pts[i + 1]
        c1 = p1 + (p2 - p0) / 6
        c2 = p2 - (p3 - p1) / 6
        path.cubicTo(c1, c2, p2)


def _spline_mid(pts: list[QPointF], i: int) -> QPointF:
    """The middle of piece `i` (pts[i] to pts[i + 1]) of the curve _spline draws through `pts`."""
    p1, p2 = pts[i], pts[i + 1]
    if len(pts) < 3:
        return (p1 + p2) / 2
    p0 = pts[i - 1] if i > 0 else p1
    p3 = pts[i + 2] if i + 2 < len(pts) else p2
    c1, c2 = p1 + (p2 - p0) / 6, p2 - (p3 - p1) / 6
    return (p1 + c1 * 3 + c2 * 3 + p2) / 8          # the cubic at t = 1/2


def _arc3(p: QPainter, a: QPointF, b: QPointF, c: QPointF, through_left: bool = True) -> None:
    """Draw the arc of the circle through a, b and c, from a to c the way that passes b (the legacy
    Arc2D, saved as three points)."""
    ax, ay, bx, by, cx, cy = a.x(), a.y(), b.x(), b.y(), c.x(), c.y()
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        p.drawLine(a, c)
        return
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    # Qt angles: degrees, counter-clockwise, y up
    ang = lambda q: math.degrees(math.atan2(-(q.y() - uy), q.x() - ux)) % 360
    sa, sb, sc = ang(a), ang(b), ang(c)
    span = (sc - sa) % 360                              # counter-clockwise from a to c
    if (sb - sa) % 360 > span:                          # b is not on that way: go clockwise
        span -= 360
    p.drawArc(QRectF(ux - r, uy - r, 2 * r, 2 * r), int(sa * 16), int(span * 16))


def _lines(text: str) -> list[str]:
    """Text as a list of lines without trailing blanks ([] for blank text)."""
    return [l.rstrip() for l in text.strip('\n').split('\n')] if text.strip() else []


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
class NodeItem(QGraphicsItem):
    """Base for every node that transitions can attach to."""

    def __init__(self, scene: 'FsmScene', obj):
        """An item for model node `obj`, placed at its position, movable and selectable."""
        super().__init__()
        self.fsm_scene = scene
        self.obj = obj
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setPos(obj.x, obj.y)
        self.setZValue(3)

    def itemChange(self, change, value):
        """Snap to the grid while dragged (refused in a read-only diagram) and, once moved, write the
        new position into the model and let the scene move what is attached.
        """
        if change == QGraphicsItem.ItemPositionChange:
            if self.fsm_scene.readonly:
                return self.pos()
            # on the grid only while the user drags it: a place read from a file stays exact
            return snap_point(value) if self.fsm_scene.mouseGrabberItem() is self else value
        if change == QGraphicsItem.ItemPositionHasChanged:
            dx, dy = self.pos().x() - self.obj.x, self.pos().y() - self.obj.y
            self.obj.x, self.obj.y = self.pos().x(), self.pos().y()
            self.fsm_scene.node_moved(self, dx, dy)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        """After a drag: tell the editor the model changed (one undo step)."""
        moved = event.buttonDownScenePos(Qt.LeftButton) != event.scenePos()
        super().mouseReleaseEvent(event)
        if moved:
            self.fsm_scene.changed_model.emit()

    def boundary(self, angle: float) -> QPointF:
        """Point on the outline in direction `angle` (radians, scene coordinates)."""
        r = self.radius()
        c = self.scenePos()
        return QPointF(c.x() + math.cos(angle) * r, c.y() + math.sin(angle) * r)

    def anchor(self, toward: QPointF) -> QPointF:
        """Point on the outline facing `toward` (scene coordinates)."""
        c = self.scenePos()
        return self.boundary(math.atan2(toward.y() - c.y(), toward.x() - c.x()))

    def radius(self) -> float:
        """Radius of the node outline (subclasses)."""
        return 10.0


class StateItem(NodeItem):
    """A state as the legacy tool draws it: a cyan circle with a blue outline (radius as saved by
    The legacy tool, 3000 units by default), the name in Arial 10 bold. A wait state is the circle inside
    an octagon, with its wait text ("wait 2") above the name."""

    def _font(self) -> QFont:
        """The name font: bold, at the size the legacy file gives (10 for a new state)."""
        f = QFont(STATE_NAME_FONT)
        f.setPointSizeF(self.obj.orig.get('font', 10))
        return f

    def radius(self):
        """Radius of the circle: as the legacy tool saved it, else the legacy tool's default grown to fit the name."""
        if self.obj.radius:
            return self.obj.radius          # as the legacy tool saved it (it sizes the circle itself)
        # a new state: the legacy tool's default radius, grown so a long name stays inside
        return max(DEFAULT_STATE_R, QFontMetricsF(self._font()).horizontalAdvance(self.obj.name) / 2 + 7)

    def _outer(self) -> float:
        """Half size of the octagon around a wait state (the legacy tool: 7058 units for a 3000 circle)."""
        return self.radius() * 7058 / 6000

    def boundary(self, angle):
        """Point on the outline (the octagon for a wait state) in direction `angle`."""
        if self.obj.is_wait:
            r = self._outer()
            c = self.scenePos()
            return QPointF(c.x() + math.cos(angle) * r, c.y() + math.sin(angle) * r)
        return super().boundary(angle)

    def boundingRect(self):
        """The circle (or octagon) plus room for the selection handles."""
        r = (self._outer() if self.obj.is_wait else self.radius()) + 3
        return QRectF(-r, -r, 2 * r, 2 * r)

    def name_rect(self) -> QRectF:
        """The state name, in item coordinates (centred in the circle, below the wait text)."""
        fm = QFontMetricsF(self._font())
        w = fm.horizontalAdvance(self.obj.name) + 4
        dy = fm.height() / 2 if self.obj.is_wait else 0
        return QRectF(-w / 2, -fm.height() / 2 + dy, w, fm.height())

    def mouseDoubleClickEvent(self, e):
        """Double-click on the name renames the state in place; elsewhere opens its properties."""
        # As the legacy tool: a double-click on the name edits it in place; elsewhere on the state
        # it opens the state's properties
        if self.name_rect().contains(e.pos()) and not self.fsm_scene.readonly:
            self.fsm_scene.rename_requested.emit(self)
        elif self.obj.hier:
            # a hierarchical state opens its own diagram (Open Down), as in the legacy tool
            self.fsm_scene.open_down_requested.emit(self.obj)
        else:
            self.fsm_scene.edit_requested.emit(self.obj)

    def paint(self, p: QPainter, opt, widget=None):
        """Draw the state as described in the class docstring (hierarchical: three blue circles)."""
        r = self.radius()
        p.setRenderHint(QPainter.Antialiasing)
        if self.obj.is_wait:
            o = self._outer()
            k = o * math.tan(math.pi / 8)
            p.setBrush(Qt.white)
            p.setPen(QPen(QColor(90, 90, 90), 0))
            p.drawPolygon(QPolygonF([QPointF(-k, -o), QPointF(k, -o), QPointF(o, -k), QPointF(o, k),
                                     QPointF(k, o), QPointF(-k, o), QPointF(-o, k), QPointF(-o, -k)]))
        if self.obj.hier:
            # a hierarchical state: three circles, blue (the legacy tool TripleCircle)
            p.setBrush(HIER_FILL)
            p.setPen(QPen(HIER_LINE, 2))
            for k in (1.0, 0.85, 0.7):
                p.drawEllipse(QPointF(0, 0), r * k, r * k)
        else:
            p.setBrush(STATE_FILL)
            p.setPen(QPen(STATE_LINE, 2))
            p.drawEllipse(QPointF(0, 0), r, r)
        p.setFont(self._font())
        p.setPen(Qt.black)
        if self.obj.is_wait:
            fm = QFontMetricsF(self._font())
            p.drawText(QRectF(-r, -fm.height(), 2 * r, fm.height()), Qt.AlignCenter | Qt.TextDontClip,
                       self.obj.wait or 'wait')
        p.drawText(self.name_rect(), Qt.AlignCenter | Qt.TextDontClip, self.obj.name)
        if self.isSelected():
            _handles(p, self.boundingRect().adjusted(3, 3, -3, -3))


class JunctionItem(NodeItem):
    """A junction as the legacy tool draws it: a lilac diamond (3300 units) with its symbol in the middle,
    "&" (AND), "if" or "case"; a CASE junction shows its expression below."""

    def radius(self):
        """Half size of the diamond (as saved by the legacy tool, else the default)."""
        s = self.obj.orig.get('shape')
        return (s[2] - s[0]) / 2 if s else JUNCTION_HALF

    def boundary(self, angle):
        """Point on the diamond outline in direction `angle`."""
        # diamond outline: |x| + |y| = r
        r = self.radius()
        c, s = math.cos(angle), math.sin(angle)
        k = r / (abs(c) + abs(s) or 1)
        return self.scenePos() + QPointF(c * k, s * k)

    def _symbol(self) -> str:
        """Text in the diamond: the saved symbol, else 'case' / 'if'."""
        if self.obj.symbol:
            return self.obj.symbol
        return 'case' if self.obj.kind == 'case' else 'if'

    def _expr_rect(self) -> QRectF:
        """Where the CASE expression is: as saved by the legacy tool, else centred under the diamond."""
        g = self.obj.orig.get('expr')
        if g:
            fm = QFontMetricsF(LABEL_BOLD_FONT)
            w = fm.horizontalAdvance(f'CASE: {self.obj.expr}')
            return QRectF(g[0], g[1], max(w, g[2] - g[0]), g[3] - g[1])
        return QRectF(-60, self.radius(), 120, 14)

    def boundingRect(self):
        """The diamond, plus the CASE expression for a case junction."""
        r = self.radius() + 3
        b = QRectF(-r, -r, 2 * r, 2 * r)
        if self.obj.kind == 'case':
            b = b.united(self._expr_rect().adjusted(-2, -2, 2, 2))
        return b

    def paint(self, p: QPainter, opt, widget=None):
        """Draw the diamond, its symbol and the CASE expression."""
        p.setRenderHint(QPainter.Antialiasing)
        h = self.radius()
        p.setBrush(JUNCTION_FILL)
        p.setPen(QPen(Qt.black, 0))
        p.drawPolygon(QPolygonF([QPointF(0, -h), QPointF(h, 0), QPointF(0, h), QPointF(-h, 0)]))
        p.setPen(Qt.black)
        g = self.obj.orig
        if g.get('symbol'):
            _draw_geo_text(p, g['symbol'], self._symbol(), LABEL_BOLD_FONT)
        else:
            p.setFont(STATE_NAME_FONT)
            p.drawText(QRectF(-h, -h, 2 * h, 2 * h), Qt.AlignCenter, self._symbol())
        if self.obj.kind == 'case':
            if g.get('expr'):
                _draw_geo_text(p, g['expr'], f'CASE: {self.obj.expr}', LABEL_BOLD_FONT)
            else:
                p.setFont(LABEL_BOLD_FONT)
                p.drawText(self._expr_rect(), Qt.AlignHCenter | Qt.AlignTop, f'CASE: {self.obj.expr}')
        if self.isSelected():
            _handles(p, QRectF(-h, -h, 2 * h, 2 * h))

    def mouseDoubleClickEvent(self, e):
        """Double-click on the CASE expression edits it in place; elsewhere opens the properties."""
        # the CASE expression is edited in place; elsewhere the junction's properties
        if self.obj.kind == 'case' and self._expr_rect().contains(e.pos()) and not self.fsm_scene.readonly:
            self.fsm_scene.text_edit_requested.emit(self, 'expr')
        else:
            self.fsm_scene.edit_requested.emit(self.obj)


class LinkItem(NodeItem):
    """A link as the legacy tool draws it: a yellow arrow (pentagon) with a short stub on its back, where
    transitions arrive, and the target state's name in bold on its right."""

    def _name_geo(self) -> list:
        """The target name's place: as saved by the legacy tool, else 250 units right of the arrow."""
        g = self.obj.orig.get('name')
        if g:
            return g
        x0 = PENT_W / 2 + 250 / 75
        return [x0, -450 / 75, x0 + QFontMetricsF(LABEL_BOLD_FONT).horizontalAdvance(self.obj.target),
                450 / 75, None, 250 / 75]

    def _turn(self) -> QTransform:
        """The arrow's direction: drawn pointing right, turned as the legacy tool saved it ("ro" 270 is
        right; 180 up, 90 left, 0 down, i.e. Qt's clockwise rotation ro - 270)."""
        return QTransform().rotate(self.obj.orig.get('ro', 270) - 270)

    def _name_rect(self) -> QRectF:
        """Rectangle of the target name (item coordinates), as justified by the legacy tool."""
        g = self._name_geo()
        w = QFontMetricsF(LABEL_BOLD_FONT).horizontalAdvance(self.obj.target)
        x0 = g[2] - w if g[4] == 2 else (g[0] + g[2] - w) / 2 if g[4] == 0 else g[0]
        return QRectF(min(x0, g[0]), g[1], max(w, g[2] - g[0]), g[3] - g[1])

    def boundingRect(self):
        """The turned arrow and stub plus the target name."""
        arrow = self._turn().mapRect(QRectF(-PENT_W / 2 - STUB, -PENT_H / 2, PENT_W + STUB, PENT_H))
        return arrow.united(self._name_rect()).adjusted(-2, -2, 2, 2)

    def paint(self, p: QPainter, opt, widget=None):
        """Draw the stub, the arrow (turned as saved) and the target name."""
        p.setRenderHint(QPainter.Antialiasing)
        p.save()
        p.setTransform(self._turn(), True)
        p.setPen(QPen(Qt.black, 0))
        p.drawLine(QPointF(-PENT_W / 2 - STUB, 0), QPointF(-PENT_W / 2, 0))
        p.setBrush(LINK_FILL)
        p.drawPolygon(_pentagon())
        if self.isSelected():
            _handles(p, QRectF(-PENT_W / 2, -PENT_H / 2, PENT_W, PENT_H))
        p.restore()
        p.setPen(Qt.black)
        _draw_geo_text(p, self._name_geo(), self.obj.target, LABEL_BOLD_FONT)

    def boundary(self, angle):
        """Transitions end at the tip of the stub, whatever the angle."""
        # transitions arrive at the end of the stub on the arrow's back
        return self.scenePos() + self._turn().map(QPointF(-PENT_W / 2 - STUB, 0))

    def mouseDoubleClickEvent(self, e):
        """Double-click on the target name edits it in place; elsewhere opens the properties."""
        # the target name is edited in place (as in the legacy tool); elsewhere the link's properties
        if self._name_rect().contains(e.pos()) and not self.fsm_scene.readonly:
            self.fsm_scene.text_edit_requested.emit(self, 'target')
        else:
            self.fsm_scene.edit_requested.emit(self.obj)


class PointItem(NodeItem):
    """Clock, reset, enable, interrupt and recovery state points, as the legacy tool draws them: a yellow
    arrow (pentagon) with a symbol in it (clock edge / reset / enable), the signal name on the
    left; the interrupt point is red with a flash; the recovery point is a red circle with an X."""

    def boundingRect(self):
        """The arrow (or recovery circle), the signal name on the left and the expression box."""
        if self.obj.kind == 'recovery':
            return QRectF(-REC_R - 2, -REC_R - 2, 2 * REC_R + 4, 2 * REC_R + 4)
        cap = self.fsm_scene.point_name(self.obj.kind)
        r = QRectF(-PENT_W / 2 - 2, -PENT_H / 2 - 2, PENT_W + STUB + 4, PENT_H + 4)
        if cap:
            g = self._name_geo(cap)
            w = QFontMetricsF(LABEL_FONT).horizontalAdvance(cap)
            r = r.united(QRectF(min(g[0], g[2] - w) - 2, g[1] - 2, max(w, g[2] - g[0]) + 4, g[3] - g[1] + 4))
        if self.obj.kind in ('clock', 'enable') and self.fsm_scene.point_caption(self.obj.kind):
            r = r.united(self._expr_rect().adjusted(-1, -1, 1, 1))
        return r

    def paint(self, p: QPainter, opt, widget=None):
        """Draw the point as described in the class docstring, with its signal name and, for clock /
        enable, the expression box.
        """
        p.setRenderHint(QPainter.Antialiasing)
        kind = self.obj.kind
        if kind == 'recovery':
            p.setBrush(QColor(255, 0, 0))
            p.setPen(QPen(Qt.black, 0))
            p.drawEllipse(QPointF(0, 0), REC_R, REC_R)
            d = REC_R * 0.6
            p.drawLine(QPointF(-d, -d), QPointF(d, d))
            p.drawLine(QPointF(-d, d), QPointF(d, -d))
            if self.isSelected():
                _handles(p, QRectF(-REC_R, -REC_R, 2 * REC_R, 2 * REC_R))
            return
        p.setPen(QPen(Qt.black, 0))
        p.setBrush(QColor(255, 0, 0) if kind == 'interrupt' else LINK_FILL)
        p.drawPolygon(_pentagon())
        x0, w, h = -PENT_W / 2, PENT_W, PENT_H
        if kind == 'interrupt':
            p.drawLine(QPointF(w / 2, 0), QPointF(w / 2 + STUB, 0))
            p.setBrush(QColor(255, 255, 0))
            p.drawPolygon(QPolygonF([QPointF(x0 + 3, -1), QPointF(x0 + 11, -4), QPointF(x0 + 10, -1),
                                     QPointF(x0 + 22, -2), QPointF(x0 + 13, 3), QPointF(x0 + 14, 0)]))
        else:
            # the legacy icon (positions in legacy units from the arrow's centre, as the legacy tool saves
            # them): the letter of the kind and the edge it acts on
            self._paint_icon(p, kind)
        cap = self.fsm_scene.point_name(kind)
        if cap:
            # the signal name, right-justified 850 units left of the arrow (as in the legacy tool)
            p.setPen(Qt.black)
            _draw_geo_text(p, self._name_geo(cap), cap, LABEL_FONT)
        expr = self.fsm_scene.point_caption(kind) if kind in ('clock', 'enable') else ''
        if expr:
            # the clock / enable expression in a box at the tip, as the legacy tool shows "posedge clk"
            r = self._expr_rect()
            p.setBrush(Qt.white)
            p.setPen(QPen(TRANS_BOX_COLOR, 0))
            p.drawRect(r)
            p.setPen(Qt.black)
            g = self.obj.orig.get('cond')
            if g:
                _draw_geo_text(p, g, expr, LABEL_FONT)
            else:
                _draw_geo_text(p, [r.left() + 100 / 75, r.top() + 100 / 75, r.right(), r.bottom(), None,
                                   r.top() + 800 / 75], expr, LABEL_FONT)
        if self.isSelected():
            _handles(p, QRectF(x0, -h / 2, w, h))

    def icon_state(self) -> tuple[str | None, bool]:
        """What the icon shows besides its letter: the edge ('rising' / 'falling', None when hidden)
        and the ring of a synchronous reset. As the legacy tool draws it: a clock shows its active edge
        (posedge: rising, negedge: falling); an asynchronous reset or an enable shows its active
        level as an edge (active low: falling, active high: rising); a synchronous reset shows a
        ring instead of the edge."""
        kind = self.obj.kind
        sig = next((s for s in self.fsm_scene.view_model.signals if s.category == kind), None)             if self.fsm_scene.view_model is not None else None
        if sig is None:                                 # no signal yet: the legacy tool's new point
            return ('falling' if kind == 'reset' else 'rising'), False
        label = category_label(sig)
        if 'Specify' in label or 'Gated' in label:      # an expression written by hand: no edge
            edge = None
        else:
            edge = 'falling' if label.endswith(('(Falling)', 'Low)')) else 'rising'
        return edge, kind == 'reset' and sig.sync

    def _paint_icon(self, p: QPainter, kind: str):
        """The letter (clock C, reset r, enable e), the edge and the ring of a synchronous reset."""
        u = 1 / 75                                      # one legacy unit
        pen = QPen(Qt.black, 0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        edge, ring = self.icon_state()
        if edge:
            # the edge: 300 units low / high, the step 74 units right of the centre
            y0, y1 = (300 * u, -300 * u) if edge == 'rising' else (-300 * u, 300 * u)
            xs = (-225 * u, 74 * u, 374 * u)
            p.drawPolyline(QPolygonF([QPointF(xs[0], y0), QPointF(xs[1], y0), QPointF(xs[1], y1),
                                      QPointF(xs[2], y1)]))
        if ring:
            p.drawEllipse(QPointF(74 * u, 0), 150 * u, 150 * u)
        if kind == 'clock':                             # "C": an arc open to the right
            _arc3(p, QPointF(-616 * u, 153 * u), QPointF(-871 * u, -153 * u), QPointF(-616 * u, -153 * u),
                  through_left=True)
        elif kind == 'reset':                           # "r": a stem and a short arm
            p.drawLine(QPointF(-876 * u, 175 * u), QPointF(-876 * u, -175 * u))
            p.drawLine(QPointF(-876 * u, -125 * u), QPointF(-776 * u, -175 * u))
        elif kind == 'enable':                          # "e": a bar and an arc round it
            p.drawLine(QPointF(-915 * u, -61 * u), QPointF(-606 * u, -61 * u))
            _arc3(p, QPointF(-630 * u, 138 * u), QPointF(-915 * u, -61 * u), QPointF(-576 * u, -61 * u),
                  through_left=True)

    def _name_geo(self, cap: str) -> list:
        """The signal name's place: as saved by the legacy tool, else right-justified 850 units left of
        the arrow, on the arrow's middle."""
        g = self.obj.orig.get('name')
        if g:
            return g
        x1 = -PENT_W / 2 - 850 / 75
        return [x1 - QFontMetricsF(LABEL_FONT).horizontalAdvance(cap), -600 / 75, x1, 300 / 75, 2, 100 / 75]

    def _expr_rect(self) -> QRectF:
        """The clock / enable expression box: as saved by the legacy tool, else on the arrow's tip,
        1200 units high, wide enough for the text."""
        expr = self.fsm_scene.point_caption(self.obj.kind)
        w = QFontMetricsF(LABEL_FONT).horizontalAdvance(expr) + 200 / 75
        g = _geo_rect(self.obj.orig.get('cond_box'))
        if g:
            return QRectF(g.left(), g.top(), max(w, g.width()), g.height())
        return QRectF(PENT_W / 2, -600 / 75, w, 1200 / 75)

    def mouseDoubleClickEvent(self, e):
        """Double-click on a clock / enable expression edits it in place; elsewhere the properties."""
        # the clock / enable expression is edited in place (as in the legacy tool); elsewhere the properties
        if self.obj.kind in ('clock', 'enable') and self.fsm_scene.point_caption(self.obj.kind)                 and self._expr_rect().contains(e.pos()) and not self.fsm_scene.readonly:
            self.fsm_scene.text_edit_requested.emit(self, 'expression')
        else:
            self.fsm_scene.edit_requested.emit(self.obj)

    def boundary(self, angle):
        """Transitions leave from the tip of the arrow (the edge of the recovery circle)."""
        if self.obj.kind == 'recovery':
            return self.scenePos() + QPointF(math.cos(angle) * REC_R, math.sin(angle) * REC_R)
        tip = PENT_W / 2 + (STUB if self.obj.kind == 'interrupt' else 0)
        return self.scenePos() + QPointF(tip, 0)      # transitions leave from the tip


# ---------------------------------------------------------------------------
# Comment texts
# ---------------------------------------------------------------------------
COMMENT_COLOR = QColor(0, 0, 128)


class CommentTextItem(QGraphicsItem):
    """Free comment text (Add > Comment Text): plain navy text, framed while selected; moved like
    the other objects, edited by a double-click."""

    def __init__(self, scene: 'FsmScene', obj):
        super().__init__()
        self.fsm_scene = scene
        self.obj = obj
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setPos(obj.x, obj.y)
        self.setZValue(4)

    def boundingRect(self):
        fm = QFontMetricsF(TEXT_FONT)
        lines = (self.obj.text or ' ').splitlines() or [' ']
        return QRectF(-2, -2, max(fm.horizontalAdvance(t) for t in lines) + 4, fm.height() * len(lines) + 4)

    find_span = None                # (start, end) of the match Find Next shows (editor_common.mark_text)

    def paint(self, p: QPainter, opt, widget=None):
        from .editor_common import paint_text_lines
        p.setFont(TEXT_FONT)
        fm = QFontMetricsF(TEXT_FONT)
        paint_text_lines(p, self.obj.text.splitlines(), 0, 0, fm, self.find_span, COMMENT_COLOR)
        if self.isSelected():
            p.setPen(QPen(Qt.black, 0, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.boundingRect().adjusted(0.5, 0.5, -0.5, -0.5))

    def itemChange(self, change, value):
        """On the grid while dragged (refused when read-only); the model follows the item."""
        if change == QGraphicsItem.ItemPositionChange:
            if self.fsm_scene.readonly:
                return self.pos()
            return snap_point(value) if self.fsm_scene.mouseGrabberItem() is self else value
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.obj.x, self.obj.y = self.pos().x(), self.pos().y()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        moved = event.buttonDownScenePos(Qt.LeftButton) != event.scenePos()
        super().mouseReleaseEvent(event)
        if moved:
            self.fsm_scene.changed_model.emit()

    def mouseDoubleClickEvent(self, e):
        if not self.fsm_scene.readonly:
            self.fsm_scene.comment_edit_requested.emit(self.obj)


# ---------------------------------------------------------------------------
# Text boxes
# ---------------------------------------------------------------------------
class _BoxItem(QGraphicsItem):
    """Movable text box made of sections separated by horizontal lines."""

    def __init__(self, scene: 'FsmScene'):
        """A movable, selectable text box above the nodes (z 4)."""
        super().__init__()
        self.fsm_scene = scene
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(4)
        self._size = QRectF()

    def sections(self) -> list[tuple[str, list[str]]]:
        """The box content: (tag, lines) per section; [] draws nothing (subclasses)."""
        return []

    def update_size(self):
        """Compute the box size from its sections (call after the text changed)."""
        self.prepareGeometryChange()
        fm = _fm()
        w, h = 20.0, 4.0
        for tag, lines in self.sections():
            for l in lines or ['']:
                w = max(w, fm.horizontalAdvance(l) + 10 + (16 if tag else 0))
            h += fm.height() * max(1, len(lines)) + 4
        self._size = QRectF(0, 0, w, h)

    def boundingRect(self):
        """The box plus a margin for the selection border."""
        return self._size.adjusted(-2, -2, 2, 2)

    def paint(self, p: QPainter, opt, widget=None):
        """Default drawing: white box, sections separated by lines, optional grey tags."""
        secs = self.sections()
        if not secs:
            return
        fm = _fm()
        p.setPen(SEL_PEN if self.isSelected() else BOX_PEN)
        p.setBrush(QColor(255, 255, 255, 230))
        p.drawRect(self._size)
        y = 2.0
        p.setFont(TEXT_FONT)
        for i, (tag, lines) in enumerate(secs):
            if i:
                p.setPen(BOX_PEN)
                p.drawLine(QPointF(0, y), QPointF(self._size.width(), y))
                y += 2
            x = 5.0
            if tag:
                p.setPen(QColor(150, 150, 150))
                p.drawText(QPointF(3, y + fm.ascent()), tag)
                x += 16
            p.setPen(Qt.black)
            for l in lines or ['']:
                p.drawText(QPointF(x, y + fm.ascent()), l)
                y += fm.height()
            y += 2

    def itemChange(self, change, value):
        """Snap while dragged, store the new place in the model and redraw the leader line."""
        if change == QGraphicsItem.ItemPositionChange:
            if self.fsm_scene.readonly:
                return self.pos()
            # on the grid only while the user drags it: a place read from a file stays exact
            return snap_point(value) if self.fsm_scene.mouseGrabberItem() is self else value
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.store()
            self.fsm_scene.update_leader(self)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        """After a drag: tell the editor the model changed."""
        moved = event.buttonDownScenePos(Qt.LeftButton) != event.scenePos()
        super().mouseReleaseEvent(event)
        if moved:
            self.fsm_scene.changed_model.emit()

    def store(self):
        """Write the box position into the model (subclasses)."""
        pass

    def section_at(self, y: float) -> int:
        """Index of the section (as sections() lists them) under item y."""
        fm = _fm()
        top = 2.0
        secs = self.sections()
        for i, (_tag, lines) in enumerate(secs):
            bottom = top + fm.height() * max(1, len(lines)) + 4
            if y < bottom:
                return i
            top = bottom
        return max(0, len(secs) - 1)

    def owner_point(self) -> QPointF | None:
        """Point on the owning state/transition that the dashed leader line goes to."""
        return None

    def owner_item(self) -> QGraphicsItem | None:
        """The item the box belongs to (its leader line is drawn to it)."""
        return None


class TransitionLabel(_BoxItem):
    """Condition above a line, actions below it."""

    def __init__(self, scene, owner: 'TransitionItem'):
        """The text box of transition `owner`."""
        super().__init__(scene)
        self.owner = owner
        self.obj = owner.obj

    def sections(self):
        """Condition (always shown when there are actions) and actions."""
        cond, acts = _lines(self.obj.cond), _lines(self.obj.actions)
        if not cond and not acts:
            return []
        return [('', cond or [''])] + ([('', acts)] if acts else [])

    def store(self):
        """Keep the box position in the transition (label_x / label_y)."""
        self.obj.label_x, self.obj.label_y = self.pos().x(), self.pos().y()

    def owner_point(self):
        """The point of the transition line nearest the box (end of the leader line)."""
        return self.owner.nearest_point(self.sceneBoundingRect().center())

    def owner_item(self):
        """The transition item."""
        return self.owner

    def mouseDoubleClickEvent(self, e):
        """Double-click edits the condition or the actions (the part under the cursor) in place."""
        # As the legacy tool: a double-click on the condition or on the actions edits that text in place
        if self.fsm_scene.readonly:
            return self.fsm_scene.edit_requested.emit(self.obj)
        field = 'actions' if self.obj.actions.strip() and self.section_at(e.pos().y()) == 1 else 'cond'
        self.fsm_scene.text_edit_requested.emit(self, field)

    def _orig(self) -> dict:
        """The geometry the legacy tool saved for this box, while its texts are still the ones it was
        saved with (else HDL Studio lays the box out)."""
        g = self.obj.orig
        return g if g.get('box_size') and g.get('sig') == [self.obj.cond, self.obj.actions] else {}

    def update_size(self):
        """Size as the legacy tool saved it while the texts are unchanged, else computed."""
        g = self._orig()
        if g:
            self.prepareGeometryChange()
            self._size = QRectF(0, 0, *g['box_size'])
        else:
            super().update_size()

    def paint(self, p: QPainter, opt, widget=None):
        """As the legacy tool draws a transition's text: a white box with a blue border, the
        condition centred, a line, then the actions. With the geometry of a legacy file, each
        text and the line are where the legacy tool put them. Selected: red border with corner handles."""
        secs = self.sections()
        if not secs:
            return
        g = self._orig()
        if g:
            r = self._size
            sel = self.isSelected()
            p.setBrush(Qt.white)
            p.setPen(QPen(QColor(220, 0, 0) if sel else TRANS_BOX_COLOR, 0))
            p.drawRect(r)
            p.setFont(TEXT_FONT)
            fm = _fm()
            p.setPen(Qt.black)
            for key, text in (('cond', self.obj.cond), ('acts', self.obj.actions)):
                if key in g and text.strip():
                    x, y = g[key]
                    for k, l in enumerate(_lines(text)):
                        p.drawText(QPointF(x, y + fm.ascent() + k * TEXT_LINE), l)
            if g.get('line') is not None:
                p.setPen(QPen(Qt.black, 0))
                p.drawLine(QPointF(3, g['line']), QPointF(r.width() - 3, g['line']))
            if sel:
                p.setPen(Qt.NoPen); p.setBrush(QColor(220, 0, 0))
                for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
                    p.drawRect(QRectF(c.x() - 2, c.y() - 2, 4, 4))
            return
        fm = _fm()
        r = self._size
        sel = self.isSelected()
        p.setBrush(Qt.white)
        p.setPen(QPen(QColor(220, 0, 0) if sel else TRANS_BOX_COLOR, 0))
        p.drawRect(r)
        p.setFont(TEXT_FONT)
        y = 2.0
        for i, (_tag, lines) in enumerate(secs):
            if i:
                p.setPen(QPen(Qt.black, 0))
                p.drawLine(QPointF(3, y), QPointF(r.width() - 3, y))
                y += 2
            for l in lines or ['']:
                if i == 0:
                    p.setPen(Qt.black)
                    p.drawText(QRectF(0, y, r.width(), fm.height()), Qt.AlignHCenter | Qt.AlignTop, l)
                else:
                    p.setPen(ACTION_COLOR)
                    p.drawText(QPointF(5, y + fm.ascent()), l)
                y += fm.height()
            y += 2
        if sel:
            p.setPen(Qt.NoPen); p.setBrush(QColor(220, 0, 0))
            for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
                p.drawRect(QRectF(c.x() - 2, c.y() - 2, 4, 4))


class StateActionsBox(_BoxItem):
    """Entry / in / exit actions of a state."""

    def __init__(self, scene, state_item: StateItem):
        """The action box of state item `state_item`."""
        super().__init__(scene)
        self.state_item = state_item
        self.obj = state_item.obj

    def store(self):
        """Keep the box position in the state (actions_x / actions_y)."""
        self.obj.actions_x, self.obj.actions_y = self.pos().x(), self.pos().y()

    def owner_point(self):
        """The point of the state outline facing the box."""
        return self.state_item.anchor(self.sceneBoundingRect().center())

    def owner_item(self):
        """The state item."""
        return self.state_item

    def mouseDoubleClickEvent(self, e):
        """Double-click edits the entry / state / exit actions under the cursor in place."""
        # the entry / state / exit actions under the cursor are edited in place (as in the legacy tool)
        if self.fsm_scene.readonly:
            return self.fsm_scene.edit_requested.emit(self.obj)
        secs = self.sections()
        tag = secs[self.section_at(e.pos().y())][0] if secs else ''
        field = {'en': 'entry_actions', 'ex': 'exit_actions'}.get(tag, 'in_actions')
        self.fsm_scene.text_edit_requested.emit(self, field)

    def sections(self):
        """Entry ('en'), state ('') and exit ('ex') actions that are not empty."""
        # the state actions are shown as they are; entry / exit actions keep a small tag
        s = self.obj
        return [(tag, _lines(t)) for tag, t in (('en', s.entry_actions), ('', s.in_actions),
                                                ('ex', s.exit_actions)) if t.strip()]

    def _orig(self) -> dict:
        """The geometry the legacy tool saved for the box, while the three action texts are unchanged."""
        s = self.obj
        g = s.orig
        return g if g.get('act_size') and g.get('sig') == [s.entry_actions, s.in_actions, s.exit_actions] else {}

    def update_size(self):
        """Size as the legacy tool saved it while the texts are unchanged, else computed."""
        g = self._orig()
        if g:
            self.prepareGeometryChange()
            self._size = QRectF(0, 0, *g['act_size'])
        else:
            super().update_size()

    def _paint_orig(self, p: QPainter, g: dict):
        """The action block exactly as the legacy tool saved it: with entry / exit actions a white box with
        a light blue border (width 2), the lines between the parts where they were, and the
        blue triangles on the left of the entry (pointing in) and exit (pointing out) texts;
        state actions alone: the text only."""
        s = self.obj
        r = self._size
        framed = bool(s.entry_actions.strip() or s.exit_actions.strip())
        fm = _fm()
        if framed:
            p.setBrush(Qt.white)
            p.setPen(QPen(ACTION_BORDER, 2))
            p.drawRect(r)
            for key in ('tline', 'bline'):
                if g.get(key) is not None:
                    p.drawLine(QPointF(1, g[key]), QPointF(r.width() - 1, g[key]))
        p.setFont(TEXT_FONT)
        for key, text in (('entry', s.entry_actions), ('in', s.in_actions), ('exit', s.exit_actions)):
            if key not in g or not text.strip():
                continue
            x, y = g[key]
            p.setPen(Qt.black)
            for k, l in enumerate(_lines(text)):
                p.drawText(QPointF(x + 1, y + fm.ascent() + k * TEXT_LINE), l)
            if key != 'in':
                # the triangle just outside the box, at the first line of the text
                cy = y + TEXT_LINE / 2
                t = 350 / 75
                tri = ([QPointF(-t, cy - t / 2), QPointF(0, cy), QPointF(-t, cy + t / 2)] if key == 'entry' else
                       [QPointF(0, cy - t / 2), QPointF(-t, cy), QPointF(0, cy + t / 2)])
                p.setPen(Qt.NoPen); p.setBrush(STATE_LINE)
                p.drawPolygon(QPolygonF(tri))
        if self.isSelected():
            p.setPen(QPen(QColor(220, 0, 0), 0)); p.setBrush(Qt.NoBrush)
            p.drawRect(r)

    def paint(self, p: QPainter, opt, widget=None):
        """As the legacy tool draws a state's actions. State actions alone: plain black text next to
        the state. With entry and / or exit actions: one light blue cell per kind (entry, state,
        exit, in that order), the entry and exit cells marked by a small tick on their left.
        Selected: a red border."""
        secs = self.sections()
        if not secs:
            return
        g = self._orig()
        if g:
            return self._paint_orig(p, g)
        fm = _fm()
        p.setFont(TEXT_FONT)
        cells = any(tag for tag, _ in secs)
        w = self._size.width()
        y = 2.0
        for tag, lines in secs:
            top = y - 1
            x = 18.0 if cells else 5.0
            p.setPen(ACTION_COLOR)
            for l in lines or ['']:
                p.drawText(QPointF(x, y + fm.ascent()), l)
                y += fm.height()
            if cells:
                p.setPen(QPen(ACTION_CELL, 0)); p.setBrush(Qt.NoBrush)
                p.drawRect(QRectF(14, top, w - 14, y - top + 1))
                if tag:
                    # the tick of an entry / exit cell (as in the legacy tool)
                    p.setPen(QPen(STATE_LINE, 0))
                    my = top + fm.height() / 2 + 1
                    p.drawLine(QPointF(7, my - 2), QPointF(11, my))
                    p.drawLine(QPointF(7, my + 2), QPointF(11, my))
            y += 2
        if self.isSelected():
            p.setPen(QPen(QColor(220, 0, 0), 0)); p.setBrush(Qt.NoBrush)
            p.drawRect(self._size)


# ---------------------------------------------------------------------------
# Declaration blocks (top of a legacy state diagram)
# ---------------------------------------------------------------------------
DECL_TITLE = QFont('Arial', 8, QFont.Bold)
DECL_TEXT = QFont('Arial', 8)
DECL_MONO = QFont('Courier New', 8)
DECL_COLOR = QColor(0, 0, 0)            # the user text of the blocks: black (as in the legacy tool)
# where the legacy tool puts the titles of a new diagram, in legacy units from the Global Actions title
_DECL_OFFSETS = {'global': (0, 0), 'concurrent': (9200, 0), 'module': (22100, 0), 'status': (35600, 0),
                 'statereg': (44300, 0), 'compdir': (0, 4000)}


class DeclBlockItem(QGraphicsItem):
    """One of the text blocks the legacy tool draws at the top of a state diagram: Global Actions (Pre /
    Post Actions), Concurrent Statements, Module Declarations (Pre / Post Decls), Signal Status
    (the outputs and locals with their default, reset and scheme), State Register Statements,
    Compiler Directives (Pre- / Post- / End-module directives). Each has a bold title and its
    text below; it can be moved (its place is kept in the view), a double-click opens the
    page where its text is edited."""
    KEYS = ('global', 'concurrent', 'module', 'status', 'statereg', 'compdir')
    TITLES = {'global': 'Global Actions', 'concurrent': 'Concurrent Statements',
              'module': 'Module Declarations', 'status': 'Signal Status',
              'statereg': 'State Register Statements', 'compdir': 'Compiler Directives'}

    def __init__(self, scene: 'FsmScene', view, key: str):
        """The block `key` (one of KEYS) of `view`, at its saved place."""
        super().__init__()
        self.fsm_scene, self.view, self.key = scene, view, key
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(3)
        self.setPos(QPointF(*self._place()))

    def _place(self) -> tuple[float, float]:
        """Saved place of the block, else the legacy tool's default layout above the diagram content."""
        if self.key in self.view.decl_pos:
            return tuple(self.view.decl_pos[self.key])
        # no place yet (a diagram made by HDL Studio): the legacy tool's layout, above the diagram content
        m = self.fsm_scene.machine
        nodes = list(m.states) + list(m.points) + list(m.junctions) + list(m.links)
        x0 = min((n.x for n in nodes), default=0.0) - 120
        y0 = min((n.y for n in nodes), default=0.0) - 220
        dx, dy = _DECL_OFFSETS[self.key]
        return x0 + dx / 75, y0 + dy / 75

    def rows(self) -> list[tuple[str, str]]:
        """(kind, text) lines: kind 'title' / 'label' (bold, black), 'text' (blue), 'mono'."""
        v = self.view
        out = [('title', self.TITLES[self.key])]

        def part(label, text):
            """Append an optional bold label and the lines of `text`."""
            if label:
                out.append(('label', label))
            out.extend(('text', l) for l in _lines(text))
        if self.key == 'global':
            part('Pre Actions:', v.global_pre_actions)
            part('Post Actions:', v.global_post_actions)
        elif self.key == 'concurrent':
            part('', v.concurrent_statements)
        elif self.key == 'module':
            part('Pre Decls', '')
            part('Post Decls', '')
        elif self.key == 'statereg':
            part('', v.state_register_statements)
        elif self.key == 'compdir':
            part('Pre-module directives:', v.pre_module_directives)
            part('Post-module directives:', v.post_module_directives)
            part('End-module directives:', v.end_module_directives)
        elif self.key == 'status':
            scheme = {'comb': 'COMB', 'clocked': 'CLKD', 'registered': 'REG'}
            rows = [(s.name, s.mode, s.default, s.reset, scheme.get(s.scheme, ''), s.comment)
                    for s in v.signals if s.mode in ('output', 'local') and s.scheme in scheme]
            head = ('SIGNAL', 'MODE', 'DEFAULT', 'RESET', 'SCHEME', 'COMMENT')
            w = [max(len(str(r[k])) for r in rows + [head]) + 1 for k in range(6)]
            for r in [head] + rows:
                out.append(('mono', ''.join(str(c).ljust(w[k]) for k, c in enumerate(r)).rstrip()))
        return out

    def _font(self, kind: str) -> QFont:
        """Font of a row kind."""
        return {'title': DECL_TITLE, 'label': DECL_TITLE, 'mono': DECL_MONO}.get(kind, DECL_TEXT)

    def boundingRect(self):
        """Size of all the rows."""
        w, h = 0.0, 0.0
        for kind, text in self.rows():
            fm = QFontMetricsF(self._font(kind))
            w = max(w, fm.horizontalAdvance(text))
            h += fm.height()
        return QRectF(-2, -2, w + 4, h + 4)

    def paint(self, p: QPainter, opt, widget=None):
        """Draw the rows (and a red frame when selected)."""
        y = 0.0
        for kind, text in self.rows():
            f = self._font(kind)
            fm = QFontMetricsF(f)
            p.setFont(f)
            p.setPen(Qt.black if kind in ('title', 'label') else DECL_COLOR)
            p.drawText(QPointF(0, y + fm.ascent()), text)
            y += fm.height()
        if self.isSelected():
            p.setPen(QPen(QColor(220, 0, 0), 0)); p.setBrush(Qt.NoBrush)
            p.drawRect(self.boundingRect().adjusted(1, 1, -1, -1))

    def itemChange(self, change, value):
        """Snap while dragged and keep the new place in view.decl_pos."""
        if change == QGraphicsItem.ItemPositionChange:
            if self.fsm_scene.readonly:
                return self.pos()
            # on the grid only while the user drags it: a place read from a file stays exact
            return snap_point(value) if self.fsm_scene.mouseGrabberItem() is self else value
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.view.decl_pos[self.key] = [self.pos().x(), self.pos().y()]
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, e):
        """After a drag: tell the editor the model changed."""
        moved = e.buttonDownScenePos(Qt.LeftButton) != e.scenePos()
        super().mouseReleaseEvent(e)
        if moved:
            self.fsm_scene.changed_model.emit()

    FIELDS = {'global': ['global_pre_actions', 'global_post_actions'], 'concurrent': ['concurrent_statements'],
              'statereg': ['state_register_statements'],
              'compdir': ['pre_module_directives', 'post_module_directives', 'end_module_directives']}

    def field_at(self, y: float) -> str:
        """The view field of the text under item y: the part whose label is above it."""
        fields = self.FIELDS.get(self.key, [])
        if not fields:
            return ''
        k, top = -1, 0.0
        for kind, _text in self.rows():
            h = QFontMetricsF(self._font(kind)).height()
            if kind == 'label' or (kind == 'title' and len(fields) == 1):
                k += 1
            if y < top + h:
                break
            top += h
        return fields[min(max(k, 0), len(fields) - 1)]

    def mouseDoubleClickEvent(self, e):
        """Double-click edits the text under the cursor in place; Signal Status (no text of its own)
        opens the Signals Table.
        """
        # a text block is edited in place (as in the legacy tool); the Signal Status is edited in the table
        field = self.field_at(e.pos().y())
        if field and not self.fsm_scene.readonly:
            self.fsm_scene.text_edit_requested.emit(self, field)
        else:
            self.fsm_scene.decl_edit_requested.emit(self.key)


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------
class TransitionItem(QGraphicsPathItem):
    """The line of a transition: a spline from the source outline through the route points to the
    destination outline, the arrow head, the priority circle and the condition / action box
    (self.label, a separate item). Only the handles are dragged (route points, the two ends,
    the priority circle); dropping an end handle on another node reconnects the transition.
    _drag holds what is being dragged: a route point index, -1 start, -2 end, -3 priority.
    """
    def __init__(self, scene: 'FsmScene', t: Transition):
        """The item of transition `t` (its label item is created too; the scene adds both)."""
        super().__init__()
        self.fsm_scene = scene
        self.obj = t
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setZValue(1)
        self.arrow = QPolygonF()
        self.ends = (QPointF(), QPointF())
        # the middle of each piece of the line between two handles: (index in obj.points where a
        # route point dragged from there goes, the point); shown as blue diamonds when selected
        self.mids: list[tuple[int, QPointF]] = []
        self.prio_pos = QPointF()
        self.show_prio = False
        self.label = TransitionLabel(scene, self)
        self._drag: int | None = None       # index into obj.points, or -1 start / -2 end
        self.refresh()

    # geometry ----------------------------------------------------------------
    def shape(self):
        """Hit area: a 10 unit wide band along the line, plus the priority circle."""
        s = QPainterPathStroker()
        s.setWidth(10)
        path = s.createStroke(self.path())
        if self.show_prio:
            path.addEllipse(self.prio_pos, PRIO_R + 1, PRIO_R + 1)
        return path

    def boundingRect(self):
        """The path plus room for the arrow head and handles."""
        return super().boundingRect().adjusted(-12, -12, 12, 12)

    def _endpoints(self, a: NodeItem, b: NodeItem) -> tuple[QPointF, QPointF]:
        """Start and end points on the node outlines: at the saved angles, else facing the first /
        last route point (or the other node).
        """
        t = self.obj
        pts = [QPointF(*p) for p in t.points]
        first = pts[0] if pts else b.scenePos()
        last = pts[-1] if pts else a.scenePos()
        start = a.boundary(t.start_angle) if t.start_angle is not None else a.anchor(first)
        end = b.boundary(t.end_angle) if t.end_angle is not None else b.anchor(last)
        return start, end

    def sm_geometry(self) -> dict:
        """What a legacy file needs of the line as drawn (formats.export_sm): its points
        (start, route points, end) and the centre of its priority circle, scene units."""
        s, e = self.ends
        return {'pts': [(s.x(), s.y()), *[tuple(p) for p in self.obj.points], (e.x(), e.y())],
                'prio': (self.prio_pos.x(), self.prio_pos.y())}

    def refresh(self):
        """Recompute the whole drawing from the model: path (a loop on the same state, a curve for a
        pair of opposite transitions, else the spline), arrow, priority circle position (exact the legacy tool
        place while the line is unchanged, else the saved fraction of the length) and label place.
        Call after anything the line depends on has changed.
        """
        sc = self.fsm_scene
        a, b = sc.item_for(self.obj.src), sc.item_for(self.obj.dst)
        if a is None or b is None:
            return
        self.prepareGeometryChange()
        t = self.obj
        path = QPainterPath()
        pts = [QPointF(*p) for p in t.points]
        if a is b and not pts and t.start_angle is None:
            r = a.radius()
            pa = a.scenePos()
            start, end = pa + QPointF(-r * 0.6, -r * 0.8), pa + QPointF(r * 0.6, -r * 0.8)
            path.moveTo(start)
            path.cubicTo(pa + QPointF(-r * 1.6, -r * 3), pa + QPointF(r * 1.6, -r * 3), end)
            before, mid = pa + QPointF(r * 1.6, -r * 3), pa + QPointF(0, -r * 2.4)
            mids = []                       # a loop on its state: no route point can be pulled out
        else:
            start, end = self._endpoints(a, b)
            path.moveTo(start)
            if not pts and sc.has_reverse(t) and t.start_angle is None:
                n = QLineF(start, end).normalVector().unitVector()
                off = QPointF(n.dx() * 30, n.dy() * 30)
                ctrl = (start + end) / 2 + off
                path.quadTo(ctrl, end)
                before, mid = ctrl, (start + end) / 2 + off / 2
                mids = [(0, mid)]
            else:
                # The legacy tool draws a transition as a spline: a smooth curve through its route points
                _spline(path, [start] + pts + [end])
                before = pts[-1] if pts else start
                seg = [start] + pts + [end]
                k = len(seg) // 2
                mid = (seg[k - 1] + seg[k]) / 2
                mids = [(i, _spline_mid(seg, i)) for i in range(len(seg) - 1)]
        self.setPath(path)
        self.ends = (start, end)
        self.mids = mids
        ang = math.atan2(end.y() - before.y(), end.x() - before.x())
        if isinstance(b, LinkItem):
            # The legacy tool: a transition into a link has no arrow head; the line runs into the
            # link's stub
            self.arrow = QPolygonF()
        else:
            self.arrow = QPolygonF([end, end - QPointF(math.cos(ang - 0.4) * 8, math.sin(ang - 0.4) * 8),
                                    end - QPointF(math.cos(ang + 0.4) * 8, math.sin(ang + 0.4) * 8)])
        # priority circle: shown as the legacy file says (else when the source has several
        # transitions), where it was (the legacy tool keeps it at a percentage of the line), else a little
        # way along the first segment
        self.show_prio = t.orig['prio_shown'] if 'prio_shown' in t.orig else len(sc.machine.outgoing(t.src)) > 1
        exact = 'prio_center' in t.orig and t.orig.get('geo_sig') == _geo_sig(t, sc.machine)
        if t.prio_at is None and 'prio_center' in t.orig:
            self.setPath(path)
            t.prio_at = self._fraction_at(QPointF(*t.orig['prio_center']))[0]
        if exact:
            # the line is still as the legacy tool saved it: its priority circle exactly where the legacy tool had it
            self.prio_pos = QPointF(*t.orig['prio_center'])
        elif t.prio_at is not None:
            self.prio_pos = path.pointAtPercent(path.percentAtLength(path.length() * min(1.0, max(0.0, t.prio_at))))
        else:
            nxt = pts[0] if pts else end
            d = QLineF(start, nxt)
            d.setLength(min(14.0, d.length() / 2))
            self.prio_pos = d.p2()
        # condition / action box
        self.label.update_size()
        if t.label_x is not None:
            self.label.setPos(t.label_x, t.label_y)
        else:
            self._auto_label(start, end, mid)
        cond, acts = t.cond.strip(), t.actions.strip()
        self.setToolTip(f'<b>{cond or "(always)"}</b><pre>{acts}</pre>' if acts else (cond or '(always)'))
        self.update()
        sc.update_leader(self.label)

    def _fraction_at(self, pos: QPointF) -> tuple[float, QPointF]:
        """Closest point of the path to `pos`, as (fraction of length, point)."""
        path = self.path()
        best, best_f, best_p = 1e18, 0.0, QPointF()
        for i in range(101):
            f = i / 100
            pt = path.pointAtPercent(path.percentAtLength(path.length() * f))
            d = QLineF(pt, pos).length()
            if d < best:
                best, best_f, best_p = d, f, pt
        return best_f, best_p

    def nearest_point(self, pos: QPointF) -> QPointF:
        """The point of the line nearest `pos`."""
        return self._fraction_at(pos)[1]

    def _auto_label(self, start, end, mid):
        """Place the label beside the middle of the line, on the upper side (no saved place yet)."""
        br = self.label.boundingRect()
        n = QLineF(start, end).normalVector().unitVector()
        nx, ny = n.dx(), n.dy()
        if ny > 0:
            nx, ny = -nx, -ny
        pos = mid + QPointF(nx * 8, ny * 8)
        if nx < 0:
            pos -= QPointF(br.width(), 0)
        if ny < -0.3:
            pos -= QPointF(0, br.height())
        self.label.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
        self.label.setPos(pos)
        self.label.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

    def paint(self, p: QPainter, opt, widget=None):
        """Draw the line, the arrow head, the priority circle and, when selected, the handles."""
        # The legacy tool: a thin line, one pixel at any zoom (a selected transition keeps its colour,
        # it gets handles); smoothed so curves do not look jagged
        pen = QPen(Qt.black, 1)
        pen.setCosmetic(True)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(self.path())
        p.setPen(QPen(Qt.black, 0))
        p.setBrush(Qt.black)
        p.drawPolygon(self.arrow)
        if self.show_prio:
            # The legacy tool: a white circle (radius 651, or as saved) with the priority in it
            pr = self.obj.orig.get('prio_r', PRIO_R)
            p.setBrush(Qt.white)
            p.setPen(QPen(Qt.black, 0))
            p.drawEllipse(self.prio_pos, pr, pr)
            p.setFont(TEXT_FONT)
            p.drawText(QRectF(self.prio_pos.x() - pr, self.prio_pos.y() - pr, 2 * pr, 2 * pr), Qt.AlignCenter,
                       str(self.obj.priority))
        if self.isSelected():
            # black square handles on the two ends and on each route point, and (the legacy tool) a
            # hollow blue diamond in the middle of each piece of line between them: dragging it
            # pulls a new route point out of the line
            p.setBrush(Qt.black)
            p.setPen(Qt.NoPen)
            for q in [QPointF(x, y) for x, y in self.obj.points] + list(self.ends):
                p.drawRect(QRectF(q.x() - 3, q.y() - 3, 6, 6))
            if not self.fsm_scene.readonly:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(0, 0, 255), 0))
                for _, q in self.mids:
                    p.drawPolygon(QPolygonF([q + QPointF(0, -MID_R), q + QPointF(MID_R, 0), q + QPointF(0, MID_R),
                                             q + QPointF(-MID_R, 0)]))

    # editing ---------------------------------------------------------------------
    def _hit(self, pos: QPointF) -> int | None:
        """Which handle is under `pos`: -3 priority circle, a route point index, -1 start, -2 end, or None."""
        if self.show_prio and QLineF(pos, self.prio_pos).length() <= PRIO_R + 1:
            return -3
        for i, (x, y) in enumerate(self.obj.points):
            if abs(pos.x() - x) <= GRAB and abs(pos.y() - y) <= GRAB:
                return i
        for k, e in ((-1, self.ends[0]), (-2, self.ends[1])):
            if QLineF(pos, e).length() <= GRAB:
                return k
        return None

    def _mid_hit(self, pos: QPointF) -> int | None:
        """Index in obj.points for a route point pulled from the middle diamond under `pos`, or None."""
        for k, q in self.mids:
            if abs(pos.x() - q.x()) + abs(pos.y() - q.y()) <= MID_R + 2:
                return k
        return None

    def _segment_at(self, pos: QPointF) -> int:
        """Index in obj.points where a new bend point at `pos` belongs."""
        seg = [self.ends[0]] + [QPointF(*p) for p in self.obj.points] + [self.ends[1]]
        best, idx = 1e18, 0
        for i in range(len(seg) - 1):
            ln = QLineF(seg[i], seg[i + 1])
            if ln.length() == 0:
                continue
            u = ((pos.x() - seg[i].x()) * ln.dx() + (pos.y() - seg[i].y()) * ln.dy()) / ln.length() ** 2
            u = max(0.0, min(1.0, u))
            proj = seg[i] + QPointF(ln.dx() * u, ln.dy() * u)
            d = QLineF(pos, proj).length()
            if d < best:
                best, idx = d, i
        return idx

    def mousePressEvent(self, e):
        """Start dragging the handle under the cursor (Select tool, editable diagram only)."""
        super().mousePressEvent(e)
        if e.button() != Qt.LeftButton or self.fsm_scene.readonly or self.fsm_scene.mode != 'select':
            return
        hit = self._hit(e.scenePos())
        # As the legacy tool: only the handles move (route points, the two ends, the priority, and
        # the diamonds in the middle of the line, which pull out a new route point); a drag
        # elsewhere on the line does nothing. Route points are also added from the right-click menu
        # (Add Route).
        self._inserted = False
        if hit is None and self.isSelected():
            k = self._mid_hit(e.scenePos())
            if k is not None:
                q = dict(self.mids)[k]
                self.obj.points.insert(k, [q.x(), q.y()])
                self._inserted = True
                hit = k
        self._drag = hit
        self._moved = False
        if hit is not None:
            self._freeze_label()

    def _freeze_label(self):
        """Give the label a fixed place before the line moves, so it does not jump with it."""
        if self.obj.label_x is None:
            self.obj.label_x, self.obj.label_y = self.label.pos().x(), self.label.pos().y()

    def mouseMoveEvent(self, e):
        """Drag the handle: priority along the line, a route point on the grid, an end around its node."""
        if self._drag is None:
            return super().mouseMoveEvent(e)
        pos = e.scenePos()
        self._moved = True
        if self._drag == -3:
            self.obj.prio_at = self._fraction_at(pos)[0]
        elif self._drag >= 0:
            p = snap_point(pos)
            self.obj.points[self._drag] = [p.x(), p.y()]
        else:
            node = self.fsm_scene.item_for(self.obj.src if self._drag == -1 else self.obj.dst)
            c = node.scenePos()
            ang = math.atan2(pos.y() - c.y(), pos.x() - c.x())
            if self._drag == -1:
                self.obj.start_angle = ang
            else:
                self.obj.end_angle = ang
        self.refresh()

    def mouseReleaseEvent(self, e):
        """End of a handle drag: reconnect when an end was dropped on another node, else redraw and
        record the change.
        """
        if self._drag is not None:
            drag, self._drag = self._drag, None
            if self._moved and drag in (-1, -2) and self._reconnect(drag, e.scenePos()):
                return
            if self._inserted and not self._moved:
                del self.obj.points[drag]          # a click on a diamond: no new route point
            self._inserted = False
            self.refresh()
            if self._moved:
                self.fsm_scene.changed_model.emit()
        super().mouseReleaseEvent(e)

    def itemChange(self, change, value):
        """A selected transition is raised above the states (its end handles lie on their edges)."""
        # a selected transition comes above the states: its end handles lie on a state edge
        # and must take the press (as in the legacy tool) rather than the state under them
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.setZValue(5 if value else 1)
        return super().itemChange(change, value)

    def _reconnect(self, which: int, pos: QPointF) -> bool:
        """An end handle dropped on another node moves that end there (the legacy tool: the transition is
        reconnected, drawn straight again with its text in the middle). The start can go to
        anything a transition may start from, the end to anything it may end on."""
        sc = self.fsm_scene
        node = next((it for it in sc.items(pos) if isinstance(it, NodeItem)), None)
        t = self.obj
        current = t.src if which == -1 else t.dst
        if node is None or node.obj.id == current:
            return False
        if which == -1 and isinstance(node, LinkItem):
            return False                        # a link only ends transitions
        if which == -2 and isinstance(node, PointItem):
            return False                        # clock / reset / recovery points only start them
        if which == -1:
            t.src, t.start_angle = node.obj.id, None
        else:
            t.dst, t.end_angle = node.obj.id, None
        t.points, t.label_x, t.label_y, t.prio_at = [], None, None, None
        sc.load(sc.view_model, sc.machine)
        sc.changed_model.emit()
        return True

    def contextMenuEvent(self, e):
        """The legacy transition menu: Add Route / Remove Route / Remove All Routes / Reverse
        Direction, Cut / Copy / Paste / Paste Special / Delete, Appearance... / Show Text /
        Object Properties... (entries HDL Studio does not have yet are disabled)."""
        from PySide6.QtWidgets import QMenu
        sc = self.fsm_scene
        if not self.isSelected():
            sc.clearSelection()
            self.setSelected(True)
        pos = e.scenePos()
        hit = self._hit(pos)
        ro = sc.readonly
        m = QMenu()
        a = m.addAction('Add Route', lambda: self.add_route(pos)); a.setEnabled(not ro)
        a = m.addAction('Remove Route', lambda: self.remove_route(hit))
        a.setEnabled(not ro and hit is not None and hit >= 0)
        a = m.addAction('Remove All Routes', self.remove_all_routes); a.setEnabled(not ro and bool(self.obj.points))
        a = m.addAction('Reverse Direction', self.reverse); a.setEnabled(not ro)
        m.addSeparator()
        for text in ('Cut', 'Copy', 'Paste'):           # no clipboard for diagram objects yet
            m.addAction(text).setEnabled(False)
        m.addMenu('Paste Special').addAction('Paste from system clipboard').setEnabled(False)
        a = m.addAction('Delete', sc.delete_selected); a.setEnabled(not ro)
        m.addSeparator()
        m.addAction('Appearance...').setEnabled(False)
        m.addAction('Show Text').setEnabled(False)
        m.addAction('Object Properties...', lambda: sc.edit_requested.emit(self.obj))
        m.exec(e.screenPos())

    def add_route(self, pos: QPointF):
        """Add Route: a route point at `pos` (on the grid), in the segment it is closest to."""
        p = snap_point(pos)
        self.obj.points.insert(self._segment_at(pos), [p.x(), p.y()])
        self.refresh()
        self.fsm_scene.changed_model.emit()

    def remove_route(self, k: int | None):
        """Remove Route: delete route point `k`."""
        if k is not None and 0 <= k < len(self.obj.points):
            del self.obj.points[k]
            self.refresh()
            self.fsm_scene.changed_model.emit()

    def remove_all_routes(self):
        """Remove All Routes: the line goes straight again."""
        self.obj.points = []
        self.refresh()
        self.fsm_scene.changed_model.emit()

    def reverse(self):
        """Diagram > Reverse Direction: source and destination swap, route points reversed."""
        t = self.obj
        t.src, t.dst = t.dst, t.src
        t.start_angle, t.end_angle = t.end_angle, t.start_angle
        t.points = list(reversed(t.points))
        sc = self.fsm_scene
        sc.load(sc.view_model, sc.machine)
        sc.changed_model.emit()

    def mouseDoubleClickEvent(self, e):
        """Double-click on a route point deletes it; elsewhere opens the transition's properties."""
        hit = self._hit(e.scenePos())
        if hit is not None and hit >= 0 and not self.fsm_scene.readonly:
            del self.obj.points[hit]
            self.refresh()
            self.fsm_scene.changed_model.emit()
        else:
            self.fsm_scene.edit_requested.emit(self.obj)


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------
class FsmScene(QGraphicsScene):
    """Edits one Machine. Emits changed_model whenever the model changes."""
    changed_model = Signal()
    message = Signal(str)
    edit_requested = Signal(object)
    condition_edit_requested = Signal(object)    # a new transition: type its condition in place
    rename_requested = Signal(object)            # a StateItem: edit its name in place
    decl_edit_requested = Signal(str)            # a declaration block (DeclBlockItem.KEYS)
    text_edit_requested = Signal(object, str)    # (item, field): edit a text in place
    popup_requested = Signal(object, object)     # (item or None for the diagram, QPoint on screen)
    comment_add_requested = Signal(QPointF)      # Add > Comment Text: a click at this scene point
    open_down_requested = Signal(object)         # a hierarchical state (model State) double-clicked
    panel_add_requested = Signal(QPointF)        # Add > Panel: a click at this scene point
    comment_edit_requested = Signal(object)      # a comment text (model Comment) double-clicked
    MODES = ('select', 'state', 'transition', 'junction_if', 'junction_case', 'link',
             'interrupt', 'recovery', 'reset', 'clock', 'enable', 'wait_state', 'hier_state', 'comment',
             'panel')

    def __init__(self, parent=None):
        """An empty scene; load() fills it."""
        super().__init__(parent)
        self.machine = Machine()
        self.view_model = None
        self.level = ''          # id of the hierarchical state whose inside is shown ('' = top level)
        self.panels_locked = False                   # Diagram > Panels > Protect All Panels
        self.mode = 'select'
        self.readonly = False
        self.items_by_id: dict[str, NodeItem] = {}
        self.trans_items: dict[str, TransitionItem] = {}
        self.action_boxes: dict[str, StateActionsBox] = {}
        self._pending_src: NodeItem | None = None
        self._rubber: QGraphicsPathItem | None = None
        self.setBackgroundBrush(QColor(255, 255, 255))      # legacy canvas: pure white
        self.leaders: dict[int, object] = {}
        self.selectionChanged.connect(self.update_all_leaders)

    # -- building -----------------------------------------------------------
    def load(self, view_model, machine: Machine):
        """Rebuild every item from `machine` at the level shown (`self.level`: the top level, or the
        inside of one hierarchical state) and, at the top level, the declaration blocks of
        `view_model` and the comment texts.
        """
        # forget the old items first: clear() deletes them and emits selectionChanged, whose
        # update_all_leaders would otherwise reach the deleted action boxes
        self.items_by_id.clear()
        self.trans_items.clear()
        self.action_boxes.clear()
        self.leaders = {}
        self.clear()
        self._state_ghost = None                    # removed by clear()
        self.view_model = view_model
        self.machine = machine
        # one level of the machine: what is inside a hierarchical state is drawn in its own
        # diagram (as in the legacy tool), so only the nodes of this level are here, with the
        # transitions between them
        if self.level and not any(s.id == self.level and s.hier for s in machine.states):
            self.level = ''                     # that hierarchical state is gone (undo, delete)
        lv = self.level
        for s in machine.states:
            if s.parent == lv:
                self._add_node_item(StateItem(self, s))
        for j in machine.junctions:
            if j.parent == lv:
                self._add_node_item(JunctionItem(self, j))
        for l in machine.links:
            if l.parent == lv:
                self._add_node_item(LinkItem(self, l))
        for pt in machine.points:
            if pt.parent == lv:
                self._add_node_item(PointItem(self, pt))
        for t in machine.transitions:
            self._add_transition_item(t)
        for c in (machine.comments if not lv else []):
            item = CommentTextItem(self, c)
            self.addItem(item)
            self.items_by_id[c.id] = item
        from .panels import PanelItem
        for pn in (machine.panels if not lv else []):
            self.addItem(PanelItem(pn, self.changed_model.emit, snap_point,
                                   lambda: self.readonly or self.panels_locked))
        if view_model is not None and not lv:
            for key in DeclBlockItem.KEYS:
                if key not in view_model.decl_hidden:     # hidden in the legacy tool: not drawn either
                    self.addItem(DeclBlockItem(self, view_model, key))
        r = self.itemsBoundingRect().adjusted(-400, -400, 400, 400)
        self.setSceneRect(r)
        self.update_all_leaders()

    def _add_node_item(self, item: NodeItem):
        """Add a node item (and, for a state, its action box) and index it by id."""
        self.addItem(item)
        self.items_by_id[item.obj.id] = item
        if isinstance(item, StateItem):
            self._sync_action_box(item)

    def _sync_action_box(self, item: StateItem):
        """Create, update or remove the action box of a state so it matches the state's actions.
        A new box goes right of the state.
        """
        s = item.obj
        box = self.action_boxes.get(s.id)
        has = any(t.strip() for t in (s.entry_actions, s.in_actions, s.exit_actions))
        if not has:
            if box is not None:
                self.removeItem(box)
                del self.action_boxes[s.id]
            return
        if box is None:
            box = StateActionsBox(self, item)
            self.addItem(box)
            self.action_boxes[s.id] = box
        box.update_size()
        if s.actions_x is None:
            r = item.radius()
            s.actions_x, s.actions_y = s.x + r + 12, s.y - box.boundingRect().height() / 2
        box.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
        box.setPos(s.actions_x, s.actions_y)
        box.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        box.update()
        self.update_leader(box)

    # dashed lines from each text box to the state/transition it belongs to
    def update_leader(self, box: '_BoxItem'):
        """Draw (or hide) the line from text box `box` to its owner: shown while the box is selected."""
        if not hasattr(self, 'leaders'):
            self.leaders = {}
        line = self.leaders.get(id(box))
        target = box.owner_point() if box.scene() is self else None
        # as the legacy tool: the line from a text box to its state / transition shows only while the box
        # is selected
        if target is None or not box.isVisible() or not box.sections() or not box.isSelected():
            if line is not None:
                line.hide()
            return
        if line is None:
            line = self.addLine(QLineF(), QPen(QColor(170, 170, 170), 0.8, Qt.DashLine))
            line.setZValue(0.5)
            self.leaders[id(box)] = line
        r = box.sceneBoundingRect()
        c = r.center()
        # leave the box from the side facing the owner
        start = QPointF(min(max(target.x(), r.left()), r.right()), min(max(target.y(), r.top()), r.bottom()))
        if r.contains(target):
            start = c
        line.setLine(QLineF(start, target))
        line.setPen(QPen(QColor(220, 0, 0), 0))
        line.show()

    def update_all_leaders(self):
        """Update the leader line of every text box (on selection changes)."""
        for box in list(self.action_boxes.values()) + [t.label for t in self.trans_items.values()]:
            self.update_leader(box)

    def _add_transition_item(self, t: Transition):
        """Add the items of transition `t` when both its ends are drawn on this scene."""
        if t.src in self.items_by_id and t.dst in self.items_by_id:
            it = TransitionItem(self, t)
            self.addItem(it)
            self.addItem(it.label)
            self.trans_items[t.id] = it
            self.update_leader(it.label)

    def item_for(self, node_id: str) -> NodeItem | None:
        """The node item of node `node_id`, or None."""
        return self.items_by_id.get(node_id)

    def has_reverse(self, t: Transition) -> bool:
        """True when another transition goes the opposite way between the same nodes."""
        return any(o.src == t.dst and o.dst == t.src for o in self.machine.transitions)

    def point_name(self, kind: str) -> str:
        """Name of the signal of a clock / reset / enable point (shown on its left, as the legacy tool)."""
        vm = self.view_model
        if vm is None or kind not in ('clock', 'reset', 'enable'):
            return ''
        s = next((s for s in vm.signals if s.category == kind), None)
        return s.name if s else ''

    def point_caption(self, kind: str) -> str:
        """Expression of the clock / reset / enable signal (shown in the point's box), else ''."""
        vm = self.view_model
        if vm is None:
            return ''
        if kind in ('clock', 'reset', 'enable'):
            s = next((s for s in vm.signals if s.category == kind), None)
            return s.expression if s else ''
        return ''

    # -- updates ----------------------------------------------------------------
    def node_moved(self, item: NodeItem, dx: float = 0.0, dy: float = 0.0):
        """A node moved by (dx, dy): its action box moves along and its transitions are redrawn."""
        box = self.action_boxes.get(item.obj.id)
        if box is not None and (dx or dy):
            s = item.obj
            s.actions_x, s.actions_y = s.actions_x + dx, s.actions_y + dy
            box.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
            box.setPos(s.actions_x, s.actions_y)
            box.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        if box is not None:
            self.update_leader(box)
        for t in self.machine.transitions:
            if item.obj.id in (t.src, t.dst) and t.id in self.trans_items:
                self.trans_items[t.id].refresh()

    def _reset_leaders(self):
        """Remove every leader line and draw them again."""
        for line in self.leaders.values():
            self.removeItem(line)
        self.leaders = {}
        self.update_all_leaders()

    def sm_geometry(self, tid: str) -> dict | None:
        """The drawn line of a transition, for writing a legacy file (None: not on this scene)."""
        it = self.trans_items.get(tid)
        return it.sm_geometry() if it is not None and getattr(it, 'ends', None) else None

    def refresh_all(self):
        """Redraw every node, action box and transition (after a change that may affect all of them)."""
        for it in self.items_by_id.values():
            if isinstance(it, StateItem):
                self._sync_action_box(it)
            it.prepareGeometryChange()
            it.update()
        for it in self.trans_items.values():
            it.refresh()
        self._reset_leaders()

    def refresh_node(self, obj):
        """Redraw one node (and its action box and transitions)."""
        it = self.items_by_id.get(obj.id)
        if it:
            it.prepareGeometryChange()
            if isinstance(it, StateItem):
                self._sync_action_box(it)
            it.update()
            self.node_moved(it)

    def refresh_transitions_from(self, node_id: str):
        """Redraw the transitions leaving `node_id` (their priorities / labels may have changed)."""
        for t in self.machine.transitions:
            if t.src == node_id and t.id in self.trans_items:
                self.trans_items[t.id].refresh()

    # -- editing ------------------------------------------------------------------
    def set_mode(self, mode: str):
        """Switch tool ('select' or one of the add modes): cancel a half-drawn transition and set
        the drag mode and cursor of the views.
        """
        self.mode = mode
        self._cancel_pending()
        self._clear_state_ghost()
        for v in self.views():
            v.setDragMode(QGraphicsView.RubberBandDrag if mode == 'select' else QGraphicsView.NoDrag)
            v.viewport().setCursor(Qt.ArrowCursor if mode == 'select' else Qt.CrossCursor)

    def _cancel_pending(self):
        """Forget a transition being drawn (its source and rubber-band line)."""
        self._pending_src = None
        if self._rubber is not None:
            self.removeItem(self._rubber)
            self._rubber = None

    def node_at(self, pos: QPointF) -> NodeItem | None:
        """The node item under scene point `pos`, or None."""
        for it in self.items(pos):
            if isinstance(it, NodeItem):
                return it
        return None

    def mousePressEvent(self, event):
        """The add tools. A click adds the object of the current mode at the grid point; for Add
        Transition the first click picks the source, clicks in open space add route points and a
        click on a node ends the transition there (then its condition is typed in place). In Select
        mode the default Qt behaviour (select / move) applies.
        """
        if self.mode == 'select' or event.button() != Qt.LeftButton or self.readonly:
            return super().mousePressEvent(event)
        pos = snap_point(event.scenePos())
        m = self.machine
        if self.mode == 'comment':
            self.comment_add_requested.emit(pos)
            return
        if self.mode == 'panel':
            self.panel_add_requested.emit(pos)
            return
        if self.mode in ('state', 'wait_state', 'hier_state'):
            s = State(id=m.new_id('s'), name=self._unique_state_name(), x=pos.x(), y=pos.y(),
                      is_wait=self.mode == 'wait_state', wait='wait 1' if self.mode == 'wait_state' else '',
                      hier=self.mode == 'hier_state', parent=self.level)
            m.states.append(s)
            item = StateItem(self, s)
            self._add_node_item(item)
            # as the legacy tool: the new state is selected (Add State stays active)
            self.clearSelection()
            item.setSelected(True)
        elif self.mode in ('junction_if', 'junction_case'):
            kind = 'case' if self.mode == 'junction_case' else 'if'
            j = Junction(id=m.new_id('j'), kind=kind, expr='expr' if kind == 'case' else '', x=pos.x(), y=pos.y(),
                         symbol=getattr(self.view_model, 'default_junction_symbol', ''), parent=self.level)
            m.junctions.append(j)
            item = JunctionItem(self, j)
            self._add_node_item(item)
            self.clearSelection(); item.setSelected(True)       # as the legacy tool: the new junction is selected
        elif self.mode == 'link':
            # As the legacy tool: no question asked, the link shows "Link" until its target state is
            # set (Object Properties / double-click); the cursor is on its stub tip
            lk = Link(id=m.new_id('l'), target='Link', x=pos.x() + LINK_TIP, y=pos.y(), parent=self.level)
            m.links.append(lk)
            item = LinkItem(self, lk)
            self._add_node_item(item)
            self.clearSelection(); item.setSelected(True)
        elif self.mode in ('interrupt', 'recovery', 'reset', 'clock', 'enable'):
            if self.mode in ('recovery', 'reset', 'clock', 'enable') and m.point(self.mode) is not None:
                self.message.emit(f'Only one {self.mode} point per machine')
                return
            pt = Point(id=m.new_id('p'), kind=self.mode, x=pos.x(), y=pos.y(), parent=self.level)
            m.points.append(pt)
            self._add_node_item(PointItem(self, pt))
        elif self.mode == 'transition':
            node = self.node_at(pos)
            if node is None:
                if self._pending_src is not None and self._rubber is not None:
                    # clicking on empty canvas while drawing adds a bend point
                    self._pending_pts.append([pos.x(), pos.y()])     # (already on the grid)
                return
            if self._pending_src is None:
                if isinstance(node, LinkItem):
                    return  # links are destinations only
                self._pending_src = node
                self._pending_pts: list[list[float]] = []
                self._rubber = QGraphicsPathItem()
                self._rubber.setPen(QPen(Qt.black, 0))      # The legacy tool: a thin solid line
                self.addItem(self._rubber)
                return
            src, pts = self._pending_src, list(self._pending_pts)
            self._cancel_pending()
            if isinstance(node, PointItem):
                self.message.emit('Reset, clock, interrupt and recovery points can only start a transition')
                return
            prio = len(m.outgoing(src.obj.id)) + 1
            t = Transition(id=m.new_id('t'), src=src.obj.id, dst=node.obj.id, priority=prio, points=pts)
            m.transitions.append(t)
            self._add_transition_item(t)
            self.refresh_transitions_from(src.obj.id)
            self.clearSelection()
            self.trans_items[t.id].setSelected(True)
            self.changed_model.emit()
            # as the legacy tool: the condition is typed in place right away
            self.condition_edit_requested.emit(t)
            return
        self.changed_model.emit()

    def _clear_state_ghost(self):
        """Remove the outline that follows the cursor while adding."""
        g = getattr(self, '_state_ghost', None)
        if g is not None:
            self.removeItem(g)
            self._state_ghost = None

    def _update_state_ghost(self, pos: QPointF):
        """While adding a state, a junction or a link, its outline (no fill) follows the cursor
        on the grid, as the legacy tool shows it: a circle / diamond centred on the cursor, a link with the
        tip of its stub on it. Not part of the model; set_mode() removes it."""
        kind = self.mode if self.mode in ('state', 'junction_if', 'junction_case', 'link') else None
        if kind == 'junction_case':
            kind = 'junction_if'
        g = getattr(self, '_state_ghost', None)
        if kind is None or self.readonly:
            self._clear_state_ghost()
            return
        if g is not None and g.data(0) != kind:
            self._clear_state_ghost()
            g = None
        if g is None:
            if kind == 'state':
                g = QGraphicsEllipseItem(-STATE_R, -STATE_R, 2 * STATE_R, 2 * STATE_R)
            elif kind == 'junction_if':
                g = QGraphicsPolygonItem(QPolygonF([QPointF(0, -9), QPointF(9, 0), QPointF(0, 9), QPointF(-9, 0)]))
            else:                       # the link body (as LinkItem) with its stub on the left
                path = QPainterPath()
                path.addPolygon(QPolygonF([QPointF(-12, -6), QPointF(6, -6), QPointF(12, 0), QPointF(6, 6),
                                           QPointF(-12, 6), QPointF(-12, -6)]))
                path.moveTo(-12, 0); path.lineTo(-LINK_TIP, 0)
                g = QGraphicsPathItem(path)
            g.setData(0, kind)
            g.setPen(QPen(Qt.black, 0)); g.setBrush(Qt.NoBrush)
            g.setAcceptedMouseButtons(Qt.NoButton)
            g.setZValue(50)
            self.addItem(g)
            self._state_ghost = g
        p = snap_point(pos)
        if kind == 'link':
            p = QPointF(p.x() + LINK_TIP, p.y())   # the stub tip on the cursor
        self._state_ghost.setPos(p)

    def mouseMoveEvent(self, event):
        """Move the add outline with the cursor and stretch the line of a transition being drawn."""
        self._update_state_ghost(event.scenePos())
        if self._pending_src is not None and self._rubber is not None:
            path = QPainterPath(self._pending_src.scenePos())
            for x, y in self._pending_pts:
                path.lineTo(x, y)
            path.lineTo(event.scenePos())
            self._rubber.setPath(path)
        super().mouseMoveEvent(event)

    def _unique_state_name(self) -> str:
        """Name of a new state, as legacy names it from the diagram's default-state template:
          - a template ending in a number ("s0", the template of a new legacy diagram): its prefix
            and the smallest free number from there ("s0", "s1", ...; "s0" again once renamed);
          - another template ("ST_"): the template itself, then "ST_1", "ST_2", ...;
          - no template (diagrams made by HDL Studio): as a new legacy diagram, "s0", "s1", ..."""
        import re
        names = {s.name for s in self.machine.states}
        base = getattr(getattr(self, 'view_model', None), 'default_state_name', '') or 's0'
        m = re.fullmatch(r'(.*?)(\d+)', base)
        if m:
            prefix, i = m.group(1), int(m.group(2))
            while f'{prefix}{i}' in names:
                i += 1
            return f'{prefix}{i}'
        if base not in names:
            return base
        i = 1
        while f'{base}{i}' in names:
            i += 1
        return f'{base}{i}'

    def contextMenuEvent(self, e):
        """Right click. A transition shows its own menu (TransitionItem.contextMenuEvent); on any
        other object, the object is selected (alone, unless it already is) and popup_requested
        asks the window for that object's legacy popup menu; on open space, the diagram's menu."""
        super().contextMenuEvent(e)
        if e.isAccepted():
            return
        top = None
        for it in self.items(e.scenePos()):
            # the selectable object a hit part belongs to (texts drawn inside an item, ...)
            while it is not None and not it.flags() & QGraphicsItem.ItemIsSelectable:
                it = it.parentItem()
            if it is not None:
                top = it
                break
        if top is not None and not top.isSelected():
            self.clearSelection()
            top.setSelected(True)
        elif top is None:
            self.clearSelection()
        self.popup_requested.emit(top, e.screenPos())
        e.accept()

    def delete_selected(self):
        """Delete the selected nodes and transitions from the model and the scene; the transitions of
        deleted nodes go too.
        """
        if self.readonly:
            return
        m = self.machine
        ids = set()
        for it in self.selectedItems():
            if isinstance(it, TransitionItem):
                m.transitions = [t for t in m.transitions if t.id != it.obj.id]
                self.removeItem(it.label)
                self.removeItem(it)
                self.trans_items.pop(it.obj.id, None)
            elif isinstance(it, NodeItem):
                ids.add(it.obj.id)
            elif isinstance(it, CommentTextItem):
                m.comments = [c for c in m.comments if c.id != it.obj.id]
                self.items_by_id.pop(it.obj.id, None)
                self.removeItem(it)
            elif type(it).__name__ == 'PanelItem':
                m.panels = [p for p in m.panels if p.id != it.obj.id]
                self.removeItem(it)
        if ids:
            # what is inside a deleted hierarchical state goes with it
            grew = True
            while grew:
                inner = {n.id for coll in (m.states, m.junctions, m.links, m.points) for n in coll
                         if n.parent in ids} - ids
                ids |= inner
                grew = bool(inner)
            for t in [t for t in m.transitions if t.src in ids or t.dst in ids]:
                m.transitions.remove(t)
                if t.id in self.trans_items:
                    ti = self.trans_items.pop(t.id)
                    self.removeItem(ti.label)
                    self.removeItem(ti)
            for coll in ('states', 'junctions', 'links', 'points'):
                setattr(m, coll, [n for n in getattr(m, coll) if n.id not in ids])
            for i in ids:
                box = self.action_boxes.pop(i, None)
                if box:
                    self.removeItem(box)
                it = self.items_by_id.pop(i, None)
                if it:
                    self.removeItem(it)
        self.refresh_all()
        self.changed_model.emit()


def apply_select_filter(scene: QGraphicsScene, what: str, is_text) -> None:
    """Select mode of the legacy editors: 'any' object, 'text' only or 'shape' only."""
    for it in scene.items():
        if not (it.flags() & QGraphicsItem.ItemIsMovable or isinstance(it, QGraphicsPathItem)):
            continue
        ok = what == 'any' or (what == 'text') == bool(is_text(it))
        it.setFlag(QGraphicsItem.ItemIsSelectable, ok)
        if not ok:
            it.setSelected(False)


class FsmGraphicsView(QGraphicsView):
    """Diagram canvas shared by the editors.

    Mouse and keys follow the legacy editors: Ctrl+wheel zoom, Shift+wheel
    horizontal scroll, middle-button pan, a View Area tool (drag a rectangle
    to view), a Panning tool (left-drag moves the diagram), Zoom Last,
    Ctrl+arrow nudges the selection one grid step, and the right button ends
    the current add command."""
    tool_done = Signal()            # the View Area drag finished
    end_command = Signal()          # right button while adding objects or using a view tool
    nudged = Signal()               # selection moved with Ctrl+arrow

    def __init__(self, scene: QGraphicsScene, parent=None):
        """A view on `scene` with rubber-band selection, zoom under the mouse and the legacy grid."""
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._pan = None
        self.tool = ''              # '' | 'area' | 'pan'
        self.grid = GRID
        self._zooms: list[tuple] = []
        self._band: QRubberBand | None = None
        self._band_from = None
        self._eat_menu = False
        self.show_grid = True

    # tools ---------------------------------------------------------------------
    def set_tool(self, tool: str):
        """Start a view tool: 'area' (View Area), 'pan' (Panning) or '' (none)."""
        self.tool = tool
        self._band_from = None
        cursor = {'area': Qt.CrossCursor, 'pan': Qt.OpenHandCursor}.get(tool)
        if cursor is not None:
            self.setDragMode(QGraphicsView.NoDrag)
            self.viewport().setCursor(cursor)

    def _remember(self):
        """Push the current zoom and centre for Zoom Last (20 kept)."""
        c = self.mapToScene(self.viewport().rect().center())
        self._zooms = (self._zooms + [(self.transform(), c)])[-20:]

    def zoom(self, factor: float):
        """Zoom by `factor` (remembered for Zoom Last)."""
        self._remember()
        self.scale(factor, factor)

    def zoom_last(self):
        """Zoom Last: back to the previous zoom and centre."""
        if self._zooms:
            t, c = self._zooms.pop()
            self.setTransform(t)
            self.centerOn(c)

    def view_rect(self, r: QRectF):
        """Fit scene rectangle `r` in the view (ignored when it is too small: a click, not a drag)."""
        if r.width() > 2 and r.height() > 2:
            self._remember()
            self.fitInView(r, Qt.KeepAspectRatio)

    # events --------------------------------------------------------------------
    def drawBackground(self, p: QPainter, rect: QRectF):
        """The white canvas with the grid dots (coarser when zoomed out, none below 35%)."""
        super().drawBackground(p, rect)
        if self.transform().m11() < 0.35:
            return
        step = self.grid
        while step * self.transform().m11() < 6:      # keep the dots apart when zoomed out
            step *= 2
        p.setPen(QPen(QColor(103, 103, 103), 0))      # legacy grid dots: one dark grey pixel
        x0 = math.floor(rect.left() / step) * step
        y0 = math.floor(rect.top() / step) * step
        nx, ny = int((rect.right() - x0) / step) + 2, int((rect.bottom() - y0) / step) + 2
        if self.show_grid and nx * ny < 200000:
            p.drawPoints([QPointF(x0 + i * step, y0 + j * step) for i in range(nx) for j in range(ny)])

    def wheelEvent(self, event):
        """Ctrl+wheel zooms, Shift+wheel scrolls horizontally, the wheel alone scrolls vertically."""
        mods = event.modifiers()
        delta = event.angleDelta().y() or event.angleDelta().x()
        if mods & Qt.ControlModifier:
            self.zoom(1.15 if delta > 0 else 1 / 1.15)
        elif mods & Qt.ShiftModifier:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - delta)
        else:
            super().wheelEvent(event)

    def _adding(self) -> bool:
        """True while an add command of the scene is active."""
        return getattr(self.scene(), 'mode', 'select') not in ('select', '')

    def mousePressEvent(self, event):
        """Middle button (or left with Panning) starts panning, left with View Area starts the
        rectangle, right button ends an add command or tool; anything else goes to the scene.
        """
        if event.button() == Qt.MiddleButton or (event.button() == Qt.LeftButton and self.tool == 'pan'):
            self._pan = event.position()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.LeftButton and self.tool == 'area':
            self._band_from = event.position().toPoint()
            if self._band is None:
                self._band = QRubberBand(QRubberBand.Rectangle, self.viewport())
            self._band.setGeometry(QRect(self._band_from, QSize()))
            self._band.show()
            return
        if event.button() == Qt.RightButton and (self.tool or self._adding()):
            self._eat_menu = True
            self.end_command.emit()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Pan the view, or stretch the View Area rectangle."""
        if self._pan is not None:
            d = event.position() - self._pan
            self._pan = event.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - d.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - d.y()))
            return
        if self._band_from is not None:
            self._band.setGeometry(QRect(self._band_from, event.position().toPoint()).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """End panning, or zoom to the View Area rectangle and report the tool done."""
        if self._pan is not None and event.button() in (Qt.MiddleButton, Qt.LeftButton):
            self._pan = None
            self.viewport().setCursor(Qt.OpenHandCursor if self.tool == 'pan' else
                                      Qt.CrossCursor if self._adding() else Qt.ArrowCursor)
            return
        if self._band_from is not None and event.button() == Qt.LeftButton:
            r = QRect(self._band_from, event.position().toPoint()).normalized()
            self._band_from = None
            self._band.hide()
            self.view_rect(self.mapToScene(r).boundingRect())
            self.tool_done.emit()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """No popup menu for the right click that ended an add command."""
        if self._eat_menu:
            self._eat_menu = False
            return
        super().contextMenuEvent(event)

    def keyPressEvent(self, event):
        """Ctrl+arrow moves the selection one grid step; Z cycles the routing mode of a PortIO drag
        (block diagram editor).
        """
        if event.key() == Qt.Key_Z and not event.modifiers() and hasattr(self.scene(), 'cycle_route_mode') \
                and self.scene().cycle_route_mode():
            return                              # routing mode changed while dragging a PortIO
        steps = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if event.key() in steps and event.modifiers() == Qt.ControlModifier:
            sel = [it for it in self.scene().selectedItems() if it.flags() & QGraphicsItem.ItemIsMovable]
            if sel and not getattr(self.scene(), 'readonly', False):
                dx, dy = steps[event.key()]
                for it in sel:
                    it.moveBy(dx * self.grid, dy * self.grid)
                self.nudged.emit()
                return
        super().keyPressEvent(event)

    def fit(self):
        """View All: fit every item in the view."""
        r = self.scene().itemsBoundingRect().adjusted(-40, -40, 40, 40)
        if r.isValid():
            self._remember()
            self.fitInView(r, Qt.KeepAspectRatio)

    # zoom/scroll position, saved per view between sessions
    def state(self) -> dict:
        """Zoom and centre of the view (saved per diagram between sessions)."""
        c = self.mapToScene(self.viewport().rect().center())
        return {'zoom': self.transform().m11(), 'cx': c.x(), 'cy': c.y()}

    def restore(self, st: dict | None) -> bool:
        """Restore a state() dict; False when it is missing or invalid."""
        try:
            z, cx, cy = float(st['zoom']), float(st['cx']), float(st['cy'])
        except (TypeError, KeyError, ValueError):
            return False
        self.resetTransform()
        self.scale(z, z)
        self.centerOn(cx, cy)
        return True
