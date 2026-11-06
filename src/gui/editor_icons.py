"""16x16 toolbar icons of the diagram editors (state diagram, block diagram), drawn with QPainter.

Same picture and place as the legacy editors' buttons (a yellow-starred page for New, binoculars
for Find, a cyan circle for Add State, ...), own artwork. Icons shared with the Design Manager
toolbar (New, Print, Cut, Copy, Paste, Find, the task flows, ...) are drawn by dm_icons; this module
adds the editor ones. Every icon has a light-grey disabled picture, as the legacy tool greys a
button it cannot use.

    editor_icon(key)    the icon of toolbar command `key` (the keys of toolbars.py)
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from . import dm_icons as D
from .icons import draw_refresh

_CACHE: dict[str, QIcon] = {}

CYAN, DARK_CYAN = QColor(0, 230, 255), QColor(0, 110, 150)
YELLOW, ORANGE = QColor(255, 235, 0), QColor(200, 150, 0)
RED, DARK_RED = QColor(230, 0, 0), QColor(140, 0, 0)
MAGENTA = QColor(230, 0, 230)
GREEN, DARK_GREEN = QColor(0, 220, 0), QColor(0, 110, 0)
NAVY, BLUE = QColor(0, 0, 140), QColor(30, 90, 220)
TEAL = QColor(0, 170, 170)

# toolbar keys drawn by the Design Manager's toolbar painter (dm_icons 'tb_<name>')
_FROM_DM = {'new': 'new', 'print': 'print', 'document': 'document', 'cut': 'cut', 'copy': 'copy',
            'paste': 'paste', 'find': 'find', 'object_props': 'properties', 'delete': 'delete',
            'check': 'check', 'registers': 'registers', 'generate': 'generate', 'simulate': 'simulate',
            'synthesize': 'synthesize', 'generate_open': 'view_hdl'}
# keys that share another key's picture
_ALIAS = {'select_text': 'select', 'select_shape': 'select', 'junction_case': 'junction_if',
          'document_hier': 'document', 'document_root': 'document',
          'highlight_hier': 'highlight', 'frame_if': 'frame', 'frame_else': 'frame', 'wire_port': 'wire',
          'bus_port': 'bus', 'bus_ripper': 'bus', 'bundle_ripper': 'bundle', 'port_out': 'port_in',
          'port_inout': 'port_in', 'port_buffer': 'port_in', 'port_master': 'port_in', 'port_slave': 'port_in',
          'net_highlight': 'highlight', 'net_clear_highlight': 'clear_highlight', 'comment': 'text',
          'check_design': 'drc'}


def _arrow(p: QPainter, x1, y1, x2, y2, color, width=1.4, head=3.5):
    """A line with a filled arrow head at (x2, y2)."""
    p.setPen(QPen(color, width, Qt.SolidLine, Qt.FlatCap))
    a = math.atan2(y2 - y1, x2 - x1)
    p.drawLine(QPointF(x1, y1), QPointF(x2 - head * 0.6 * math.cos(a), y2 - head * 0.6 * math.sin(a)))
    p.setBrush(color); p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(x2, y2),
                             QPointF(x2 - head * math.cos(a - 0.5), y2 - head * math.sin(a - 0.5)),
                             QPointF(x2 - head * math.cos(a + 0.5), y2 - head * math.sin(a + 0.5))]))


def _big_arrow(p: QPainter, left: bool, fill: QColor):
    """Thick Back / Forward arrow."""
    pts = [(1, 8), (7, 2.5), (7, 5.5), (15, 5.5), (15, 10.5), (7, 10.5), (7, 13.5)]
    if not left:
        pts = [(16 - x, y) for x, y in pts]
    p.setBrush(fill); p.setPen(QPen(fill.darker(160), 0.8))
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))


def _magnifier(p: QPainter, sign: str):
    """Zoom lens; `sign` '+', '-', 'area' (dashed square) or 'all' (a page) inside."""
    p.setPen(QPen(QColor(30, 30, 30), 2.2, Qt.SolidLine, Qt.RoundCap)); p.drawLine(QPointF(10, 10), QPointF(14.5, 14.5))
    p.setBrush(QColor(210, 235, 255)); p.setPen(QPen(NAVY, 1.3)); p.drawEllipse(QPointF(7, 6.5), 5, 5)
    p.setPen(QPen(NAVY, 1.4))
    if sign in '+-':
        p.drawLine(QPointF(4.5, 6.5), QPointF(9.5, 6.5))
        if sign == '+':
            p.drawLine(QPointF(7, 4), QPointF(7, 9))
    elif sign == 'area':
        p.setPen(QPen(NAVY, 0.9, Qt.DashLine)); p.setBrush(Qt.NoBrush); p.drawRect(QRectF(4.5, 4, 5, 5))
    else:
        p.setPen(QPen(NAVY, 0.9)); p.setBrush(Qt.white); p.drawRect(QRectF(5, 3.5, 4, 6))


def _pin(p: QPainter, fill: QColor, letter: str = ''):
    """Signal flag of the clock / reset / enable / interrupt / link buttons: a pointed tag on a
    stub, with a small letter above it."""
    p.setPen(QPen(Qt.black, 1)); p.drawLine(QPointF(10, 10.5), QPointF(15, 10.5))
    p.setBrush(fill); p.setPen(QPen(Qt.black, 0.8))
    p.drawPolygon(QPolygonF([QPointF(2, 8), QPointF(8, 8), QPointF(10.5, 10.5), QPointF(8, 13), QPointF(2, 13)]))
    if letter:
        p.setPen(Qt.black); p.setFont(QFont('Arial', 6))
        p.drawText(QRectF(2, -0.5, 8, 8), Qt.AlignCenter, letter)


def _state_circle(p: QPainter, fill: QColor, ring: QColor):
    """State bubble with two text lines, as drawn on the diagram."""
    p.setBrush(fill); p.setPen(QPen(ring, 1.2)); p.drawEllipse(QPointF(8, 8), 6.5, 6.5)
    p.setPen(QPen(ring, 0.8))
    p.drawLine(QPointF(4.5, 7.5), QPointF(11.5, 7.5)); p.drawLine(QPointF(5.5, 9.5), QPointF(10.5, 9.5))


def _wire(p: QPainter, width: float, color: QColor, end: QColor | None = None):
    """A net with one bend and an arrow end (Add Signal / Bus)."""
    p.setPen(QPen(color, width, Qt.SolidLine, Qt.FlatCap, Qt.MiterJoin)); p.setBrush(Qt.NoBrush)
    p.drawPolyline(QPolygonF([QPointF(1.5, 3), QPointF(8, 3), QPointF(8, 12.5), QPointF(12, 12.5)]))
    p.setBrush(end or BLUE); p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(12, 10), QPointF(15.5, 12.5), QPointF(12, 15)]))


def _table(p: QPainter, r: QRectF):
    """Small grid with a yellow header row (the IBD buttons)."""
    p.setBrush(Qt.white); p.setPen(QPen(QColor(60, 60, 60), 0.8)); p.drawRect(r)
    p.setBrush(YELLOW); p.drawRect(QRectF(r.left(), r.top(), r.width(), r.height() / 4))
    for k in (1, 2):
        x = r.left() + r.width() * k / 3
        p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
    for k in (2, 3):
        y = r.top() + r.height() * k / 4
        p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))


def _draw(p: QPainter, name: str):
    """Draw editor toolbar icon `name` (16x16)."""
    if name in ('back', 'forward'):
        _big_arrow(p, name == 'back', TEAL)
    elif name == 'open_up':                   # folder with an arrow up
        p.setBrush(QColor(255, 230, 110)); p.setPen(QPen(QColor(130, 100, 0), 0.9))
        p.drawPolygon(QPolygonF([QPointF(1.5, 4), QPointF(6, 4), QPointF(7, 5.5), QPointF(14.5, 5.5),
                                 QPointF(14.5, 14), QPointF(1.5, 14)]))
        _arrow(p, 8, 12.5, 8, 6.5, Qt.black, 1.4, 3.5)
        p.setPen(QPen(Qt.black, 1.4)); p.drawLine(QPointF(8, 12.5), QPointF(12, 12.5))
    elif name == 'save':                      # floppy disk
        p.setBrush(QColor(30, 30, 30)); p.setPen(Qt.NoPen); p.drawRect(QRectF(1.5, 1.5, 13, 13))
        p.setBrush(Qt.white); p.drawRect(QRectF(4, 1.5, 8, 5.5))
        p.setBrush(QColor(170, 170, 170)); p.drawRect(QRectF(4.5, 9.5, 7, 5))
        p.setBrush(QColor(30, 30, 30)); p.drawRect(QRectF(9.5, 2.5, 1.5, 3))
    elif name in ('undo', 'redo'):            # curved blue arrow
        path = QPainterPath(); path.moveTo(4, 11); path.cubicTo(4, 3, 13, 3, 13, 10)
        if name == 'redo':
            path = QPainterPath(); path.moveTo(12, 11); path.cubicTo(12, 3, 3, 3, 3, 10)
        p.setPen(QPen(BLUE, 1.7)); p.setBrush(Qt.NoBrush); p.drawPath(path)
        x = 4 if name == 'undo' else 12
        p.setBrush(BLUE); p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(x - 3.5, 9), QPointF(x + 3.5, 9), QPointF(x, 13.5)]))
    elif name == 'expression_builder':        # "fx" and a pencil
        p.setPen(NAVY); p.setFont(QFont('Times New Roman', 10, QFont.Bold, True))
        p.drawText(QRectF(0, 2, 11, 13), Qt.AlignCenter, 'fx')
        p.setPen(QPen(RED, 2.2, Qt.SolidLine, Qt.FlatCap)); p.drawLine(QPointF(9, 12), QPointF(15, 3))
        p.setPen(QPen(Qt.black, 1)); p.drawLine(QPointF(8, 13.5), QPointF(9, 12))
    elif name in ('zoom_in', 'zoom_out', 'view_area', 'fit'):
        _magnifier(p, {'zoom_in': '+', 'zoom_out': '-', 'view_area': 'area', 'fit': 'all'}[name])
    elif name == 'select':                    # pointer arrow
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 1))
        p.drawPolygon(QPolygonF([QPointF(4, 1.5), QPointF(4, 13), QPointF(6.8, 10.3), QPointF(9, 15),
                                 QPointF(10.8, 14.2), QPointF(8.7, 9.6), QPointF(12.5, 9.6)]))
    elif name == 'text':                      # serif A
        p.setPen(Qt.black); p.setFont(QFont('Times New Roman', 13, QFont.Bold))
        p.drawText(QRectF(0, -1, 16, 17), Qt.AlignCenter, 'A')
    elif name == 'pan':                       # open hand
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 0.9))
        for x, top in ((3.5, 5), (6, 2.5), (8.5, 2), (11, 3.5)):
            p.drawRoundedRect(QRectF(x, top, 2.4, 8), 1.2, 1.2)
        path = QPainterPath(); path.addRoundedRect(QRectF(3.5, 7.5, 9.9, 7.5), 2.5, 2.5)
        p.drawPath(path)
        p.setPen(Qt.NoPen); p.drawRect(QRectF(4, 7.5, 8.9, 2))
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 0.9))
        p.drawRoundedRect(QRectF(12.2, 7, 2.6, 4.5), 1.2, 1.2)
    # -- state diagram tools --
    elif name == 'clock':                     # clock signal tag with a waveform
        p.setBrush(QColor(255, 235, 150)); p.setPen(QPen(Qt.black, 0.8)); p.drawRoundedRect(QRectF(1.5, 5, 13, 7), 2, 2)
        p.setPen(QPen(Qt.black, 0.9)); p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(3, 10.5), QPointF(5, 10.5), QPointF(5, 6.5), QPointF(8, 6.5),
                                  QPointF(8, 10.5), QPointF(11, 10.5), QPointF(11, 6.5), QPointF(13, 6.5)]))
    elif name == 'reset':
        _pin(p, YELLOW, 'r')
    elif name == 'enable':
        _pin(p, YELLOW, 'e')
    elif name == 'interrupt':
        _pin(p, RED)
    elif name == 'link':
        _pin(p, YELLOW)
    elif name == 'recovery':                  # round stop sign with a white cross
        p.setBrush(RED); p.setPen(QPen(DARK_RED, 1)); p.drawEllipse(QPointF(8, 8), 6, 6)
        p.setPen(QPen(Qt.white, 1.8)); p.drawLine(QPointF(5.5, 5.5), QPointF(10.5, 10.5))
        p.drawLine(QPointF(10.5, 5.5), QPointF(5.5, 10.5))
    elif name == 'state':
        _state_circle(p, CYAN, DARK_CYAN)
    elif name == 'hier_state':                # dark ring round a state
        p.setBrush(QColor(30, 60, 200)); p.setPen(QPen(NAVY, 1)); p.drawEllipse(QPointF(8, 8), 7, 7)
        p.setBrush(CYAN); p.setPen(QPen(DARK_CYAN, 0.8)); p.drawEllipse(QPointF(8, 8), 4.5, 4.5)
    elif name == 'wait_state':                # state inside an octagon
        pts = [QPointF(8 + 7.2 * math.cos(math.radians(22.5 + 45 * k)), 8 + 7.2 * math.sin(math.radians(22.5 + 45 * k)))
               for k in range(8)]
        p.setBrush(QColor(230, 230, 230)); p.setPen(QPen(Qt.black, 0.9)); p.drawPolygon(QPolygonF(pts))
        _state_circle(p, CYAN, DARK_CYAN)
    elif name == 'transition':                # arrow with dashed motion lines
        _arrow(p, 4, 4, 13, 13, NAVY, 1.4, 4)
        p.setPen(QPen(NAVY, 1))
        p.drawLine(QPointF(2, 7), QPointF(6, 11)); p.drawLine(QPointF(7, 2), QPointF(11, 6))
    elif name == 'junction_if':               # magenta diamond
        p.setBrush(MAGENTA); p.setPen(QPen(QColor(110, 0, 110), 0.8))
        p.drawPolygon(QPolygonF([QPointF(8, 4), QPointF(12, 8), QPointF(8, 12), QPointF(4, 8)]))
    elif name == 'panel':                     # red-bordered page frame
        p.setBrush(Qt.white); p.setPen(QPen(DARK_RED, 1.4)); p.drawRect(QRectF(2, 2.5, 12, 11))
        p.setPen(QPen(QColor(120, 120, 120), 0.8)); p.drawLine(QPointF(2.5, 4.5), QPointF(13.5, 4.5))
    elif name == 'drc':                       # window with a red tick
        p.setBrush(Qt.white); p.setPen(QPen(NAVY, 1)); p.drawRect(QRectF(1.5, 2, 11, 11))
        p.setBrush(NAVY); p.drawRect(QRectF(1.5, 2, 11, 2.5))
        p.setPen(QPen(RED, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)); p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(6, 9.5), QPointF(9, 13), QPointF(15, 5)]))
    # -- block diagram tools --
    elif name == 'highlight':                 # pen over a net
        p.setPen(QPen(QColor(90, 90, 90), 1)); p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(1, 13.5), QPointF(5, 13.5), QPointF(5, 8), QPointF(9, 8)]))
        p.setPen(QPen(QColor(60, 60, 60), 2.2, Qt.SolidLine, Qt.FlatCap)); p.drawLine(QPointF(8, 11), QPointF(14.5, 3))
        p.setPen(QPen(Qt.black, 1)); p.drawLine(QPointF(7, 12.5), QPointF(8, 11))
    elif name == 'clear_highlight':           # highlighted nets crossed out
        p.setPen(QPen(YELLOW, 2.4)); p.drawLine(QPointF(1, 4), QPointF(15, 4)); p.drawLine(QPointF(1, 12), QPointF(15, 12))
        p.setPen(QPen(NAVY, 1)); p.drawLine(QPointF(1, 4), QPointF(15, 4)); p.drawLine(QPointF(1, 12), QPointF(15, 12))
        p.setPen(QPen(RED, 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(3, 2), QPointF(13, 14)); p.drawLine(QPointF(13, 2), QPointF(3, 14))
    elif name == 'block':                     # tall cyan block
        p.setBrush(CYAN); p.setPen(QPen(NAVY, 1)); p.drawRect(QRectF(4.5, 1.5, 7, 13))
        p.setPen(QPen(NAVY, 0.8)); p.drawLine(QPointF(6, 4), QPointF(10, 4))
    elif name == 'component':                 # green block with pins
        p.setPen(QPen(Qt.black, 1))
        for y in (5, 11):
            p.drawLine(QPointF(1, y), QPointF(4, y)); p.drawLine(QPointF(12, y), QPointF(15, y))
        p.setBrush(GREEN); p.setPen(QPen(DARK_GREEN, 1)); p.drawRect(QRectF(4, 1.5, 8, 13))
    elif name == 'moduleware':                # block with a lamp
        p.setBrush(CYAN); p.setPen(QPen(NAVY, 1)); p.drawRect(QRectF(2, 1.5, 12, 13))
        p.setBrush(YELLOW); p.setPen(QPen(ORANGE, 0.9)); p.drawEllipse(QPointF(8, 6.5), 3, 3)
        p.setBrush(QColor(150, 150, 150)); p.setPen(Qt.NoPen); p.drawRect(QRectF(6.5, 9.5, 3, 2.5))
    elif name == 'external_ip':               # "IP" and a block with a red arrow
        p.setPen(NAVY); p.setFont(QFont('Arial', 7, QFont.Bold)); p.drawText(QRectF(0, 0, 9, 8), Qt.AlignCenter, 'IP')
        p.setBrush(GREEN); p.setPen(QPen(DARK_GREEN, 0.9)); p.drawRect(QRectF(8.5, 4, 6, 10))
        _arrow(p, 2, 13, 8, 8, RED, 1.4, 3.5)
    elif name == 'embedded':                  # yellow text page
        p.setBrush(QColor(255, 245, 120)); p.setPen(QPen(QColor(90, 90, 0), 0.9)); p.drawRect(QRectF(3.5, 1.5, 9, 13))
        p.setPen(QPen(Qt.black, 0.8))
        for y in (4.5, 6.5, 8.5, 10.5):
            p.drawLine(QPointF(5, y), QPointF(11, y))
    elif name == 'frame':                     # dashed frame round two blocks
        p.setBrush(Qt.NoBrush); p.setPen(QPen(Qt.black, 0.9, Qt.DashLine)); p.drawRect(QRectF(1, 1.5, 14, 13))
        p.setBrush(GREEN); p.setPen(QPen(DARK_GREEN, 0.8)); p.drawRect(QRectF(3.5, 4, 4, 6))
        p.setBrush(CYAN); p.setPen(QPen(NAVY, 0.8)); p.drawRect(QRectF(8.5, 6, 4, 6))
    elif name == 'wire':
        _wire(p, 1.2, NAVY)
    elif name == 'bus':
        _wire(p, 2.6, NAVY)
    elif name == 'bundle':                    # two parallel nets
        p.setPen(QPen(Qt.black, 1)); p.setBrush(Qt.NoBrush)
        for d in (0, 3):
            p.drawPolyline(QPolygonF([QPointF(1.5, 3 + d), QPointF(10 - d, 3 + d), QPointF(10 - d, 13),
                                      QPointF(14.5, 13)]))
        p.setBrush(QColor(230, 230, 230)); p.setPen(QPen(Qt.black, 0.8)); p.drawRect(QRectF(9, 8, 6, 4))
    elif name == 'port_in':                   # port arrow on a stub
        p.setPen(QPen(Qt.black, 1)); p.drawLine(QPointF(9, 8), QPointF(15, 8))
        p.setBrush(NAVY); p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(1, 5.5), QPointF(6.5, 5.5), QPointF(9.5, 8), QPointF(6.5, 10.5), QPointF(1, 10.5)]))
    elif name == 'global_connector':          # yellow ball
        p.setBrush(YELLOW); p.setPen(QPen(ORANGE, 1)); p.drawEllipse(QPointF(8, 8), 5, 5)
    elif name == 'edit_ibd':                  # connectivity table
        _table(p, QRectF(1.5, 1.5, 13, 13))
    elif name == 'visualize_ibd':             # person and a table
        p.setBrush(QColor(80, 80, 80)); p.setPen(Qt.NoPen); p.drawEllipse(QPointF(4, 4.5), 2.3, 2.3)
        p.drawRoundedRect(QRectF(1, 7.5, 6, 6.5), 2, 2)
        _table(p, QRectF(6.5, 4, 8.5, 10))
    elif name == 'refresh':
        draw_refresh(p, 16)


def editor_icon(key: str) -> QIcon:
    """The 16x16 toolbar icon of editor command `key`, with its greyed (disabled) picture; drawn once
    and cached. An unknown key gives an empty icon."""
    if key in _CACHE:
        return _CACHE[key]
    name = _ALIAS.get(key, key)
    base, _, scope = name.partition('_')
    if base in ('check', 'generate', 'simulate', 'synthesize') and scope in ('blocks', 'components', 'root'):
        name = base                             # the Run ... entries of a task flow: the flow's picture
    if name in _FROM_DM:
        ic = D.dm_icon('tb_' + _FROM_DM[name])
    else:
        pm = QPixmap(16, 16)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        _draw(p, name)
        p.end()
        ic = QIcon(pm)
        ic.addPixmap(D._disabled(pm), QIcon.Disabled)
    _CACHE[key] = ic
    return ic
