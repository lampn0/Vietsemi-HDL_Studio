"""Toolbar icons drawn with QPainter (no image files to ship)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF

_CACHE: dict[str, QIcon] = {}
S = 24


def _flag(p: QPainter, fill: QColor, letter: str = ''):
    """The flag shape of the link / reset / clock / enable icons, with an optional letter."""
    p.setBrush(fill)
    p.setPen(QPen(Qt.black, 1))
    p.drawPolygon(QPolygonF([QPointF(3, 7), QPointF(15, 7), QPointF(21, 12), QPointF(15, 17), QPointF(3, 17)]))
    if letter:
        p.setPen(QPen(QColor(200, 0, 0), 1))
        p.setFont(QFont('Arial', 8, QFont.Bold))
        p.drawText(QRectF(3, 7, 12, 10), Qt.AlignCenter, letter)


def _arrow(p: QPainter, x1, y1, x2, y2, color=Qt.black):
    """A line from (x1, y1) to (x2, y2) with an arrow head at the end."""
    p.setPen(QPen(color, 1.6))
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    import math
    a = math.atan2(y2 - y1, x2 - x1)
    p.setBrush(color)
    p.drawPolygon(QPolygonF([QPointF(x2, y2), QPointF(x2 - 6 * math.cos(a - 0.45), y2 - 6 * math.sin(a - 0.45)),
                             QPointF(x2 - 6 * math.cos(a + 0.45), y2 - 6 * math.sin(a + 0.45))]))


REFRESH_GREEN, REFRESH_DARK = QColor(40, 170, 40), QColor(0, 100, 0)


def draw_refresh(p: QPainter, size: float) -> None:
    """The Refresh icon of every window: two green arrows turning round, in a `size` square.
    Shared by the editors (icon('refresh')) and the Design Manager toolbar (dm_icons 'tb_refresh').
    """
    import math
    c, r = size / 2, size * 0.32
    width = max(1.6, size * 0.14)
    head = size * 0.2
    for start in (40, 220):                       # two arcs of 140 degrees, anticlockwise
        span = 140
        rect = QRectF(c - r, c - r, 2 * r, 2 * r)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(REFRESH_DARK, width + 1.2, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(rect, start * 16, span * 16)
        p.setPen(QPen(REFRESH_GREEN, width, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(rect, start * 16, span * 16)
        a = math.radians(start + span)            # arrow head at the end, pointing along the turn
        x, y = c + r * math.cos(a), c - r * math.sin(a)
        dx, dy = -math.sin(a), -math.cos(a)       # direction of the anticlockwise turn (y down)
        nx, ny = math.cos(a), -math.sin(a)        # outwards
        p.setBrush(REFRESH_GREEN)
        p.setPen(QPen(REFRESH_DARK, max(0.8, size / 24)))
        p.drawPolygon(QPolygonF([QPointF(x + dx * head, y + dy * head),
                                 QPointF(x + nx * head * 0.85, y + ny * head * 0.85),
                                 QPointF(x - nx * head * 0.85, y - ny * head * 0.85)]))


def icon(name: str) -> QIcon:
    """The toolbar icon called `name`, drawn once with QPainter (24x24) and cached. Each branch
    below draws one icon; an unknown name gives an empty (transparent) icon.
    """
    if name in _CACHE:
        return _CACHE[name]
    pm = QPixmap(S, S)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    cyan, yellow, red = QColor(0, 220, 255), QColor(255, 230, 0), QColor(220, 0, 0)
    if name == 'select':
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 1.2))
        p.drawPolygon(QPolygonF([QPointF(6, 3), QPointF(6, 19), QPointF(10, 15), QPointF(13, 21), QPointF(15, 20),
                                 QPointF(12, 14), QPointF(17, 14)]))
    elif name == 'state':
        p.setBrush(cyan); p.setPen(QPen(QColor(0, 90, 160), 1.4)); p.drawEllipse(QRectF(3, 3, 18, 18))
    elif name == 'transition':
        _arrow(p, 3, 19, 20, 5)
    elif name in ('junction_if', 'junction_case'):
        p.setBrush(QColor(230, 120, 230)); p.setPen(QPen(Qt.black, 1))
        p.drawPolygon(QPolygonF([QPointF(12, 3), QPointF(21, 12), QPointF(12, 21), QPointF(3, 12)]))
        p.setFont(QFont('Arial', 7, QFont.Bold)); p.setPen(Qt.black)
        p.drawText(QRectF(3, 3, 18, 18), Qt.AlignCenter, 'C' if name == 'junction_case' else 'IF')
    elif name == 'link':
        _flag(p, yellow)
    elif name == 'interrupt':
        _flag(p, QColor(255, 210, 0))
        p.setBrush(red); p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(8, 8), QPointF(13, 12), QPointF(10, 12), QPointF(15, 17), QPointF(7, 12),
                                 QPointF(10, 12)]))
    elif name == 'recovery':
        p.setBrush(red); p.setPen(Qt.NoPen); p.drawEllipse(QRectF(3, 3, 18, 18))
        p.setPen(QPen(Qt.white, 2.2)); p.drawLine(8, 8, 16, 16); p.drawLine(8, 16, 16, 8)
    elif name == 'reset':
        _flag(p, yellow, 'R')
    elif name == 'clock':
        _flag(p, yellow, 'C')
    elif name == 'save':
        p.setBrush(QColor(60, 90, 170)); p.setPen(QPen(Qt.black, 1)); p.drawRect(QRectF(3, 3, 18, 18))
        p.setBrush(Qt.white); p.drawRect(QRectF(7, 3, 10, 7)); p.drawRect(QRectF(6, 13, 12, 8))
    elif name == 'generate':
        p.setBrush(QColor(40, 150, 40)); p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(6, 3), QPointF(21, 12), QPointF(6, 21)]))
        p.setPen(Qt.white); p.setFont(QFont('Arial', 7, QFont.Bold)); p.drawText(QRectF(4, 6, 12, 12), Qt.AlignCenter, 'G')
    elif name == 'generate_open':
        p.setPen(QPen(QColor(40, 40, 40), 1)); p.setBrush(Qt.white); p.drawRect(QRectF(4, 2, 14, 19))
        p.setPen(QPen(QColor(40, 150, 40), 1.4))
        for y in (7, 11, 15):
            p.drawLine(7, y, 15, y)
    elif name in ('undo', 'redo'):
        p.setPen(QPen(QColor(40, 40, 120), 2)); p.setBrush(Qt.NoBrush)
        # half circle with an arrow head at the open end
        p.drawArc(QRectF(5, 6, 14, 12), 0, 180 * 16)
        if name == 'undo':
            _arrow(p, 5, 10, 5, 16, QColor(40, 40, 120))
        else:
            _arrow(p, 19, 10, 19, 16, QColor(40, 40, 120))
    elif name == 'fit':
        p.setPen(QPen(Qt.black, 1.4)); p.setBrush(Qt.NoBrush)
        for (x1, y1, x2, y2) in ((3, 8, 3, 3), (3, 3, 8, 3), (16, 3, 21, 3), (21, 3, 21, 8),
                                 (3, 16, 3, 21), (3, 21, 8, 21), (16, 21, 21, 21), (21, 21, 21, 16)):
            p.drawLine(x1, y1, x2, y2)
        p.drawEllipse(QRectF(8, 8, 8, 8))
    elif name in ('zoom_in', 'zoom_out'):
        p.setPen(QPen(Qt.black, 1.6)); p.setBrush(Qt.white); p.drawEllipse(QRectF(3, 3, 13, 13))
        p.drawLine(14, 14, 21, 21); p.drawLine(6, 9, 13, 9)
        if name == 'zoom_in':
            p.drawLine(9, 6, 9, 13)
    elif name == 'delete':
        p.setPen(QPen(red, 2.4)); p.drawLine(6, 6, 18, 18); p.drawLine(6, 18, 18, 6)
    elif name == 'component':
        p.setBrush(QColor(0, 220, 0)); p.setPen(QPen(QColor(0, 110, 0), 1.4)); p.drawRect(QRectF(6, 3, 12, 18))
        p.setPen(QPen(Qt.black, 1.2))
        for y in (8, 15):
            p.drawLine(2, y, 6, y); p.drawLine(18, y, 22, y)
    elif name == 'wire':
        p.setPen(QPen(Qt.black, 1.8)); p.drawPolyline(QPolygonF([QPointF(3, 18), QPointF(12, 18), QPointF(12, 6),
                                                                  QPointF(21, 6)]))
        p.setBrush(Qt.black); p.drawEllipse(QPointF(3, 18), 2, 2); p.drawEllipse(QPointF(21, 6), 2, 2)
    elif name in ('port_in', 'port_out'):
        p.setBrush(QColor(0, 0, 140)); p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(3, 8), QPointF(13, 8), QPointF(18, 12), QPointF(13, 16), QPointF(3, 16)]))
        p.setPen(QPen(Qt.black, 1.4))
        if name == 'port_in':
            p.drawLine(18, 12, 22, 12)
        else:
            p.drawLine(0, 12, 3, 12)
        p.setFont(QFont('Arial', 6, QFont.Bold)); p.setPen(Qt.white)
        p.drawText(QRectF(3, 8, 11, 8), Qt.AlignCenter, 'I' if name == 'port_in' else 'O')
    elif name == 'embedded':
        p.setBrush(QColor(255, 255, 150)); p.setPen(QPen(QColor(0, 0, 120), 1.2)); p.drawRect(QRectF(3, 4, 18, 16))
        p.setPen(QPen(Qt.black, 1))
        for y in (9, 13, 17):
            p.drawLine(6, y, 17, y)
    elif name == 'new':
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 1))
        p.drawPolygon(QPolygonF([QPointF(5, 2), QPointF(15, 2), QPointF(19, 6), QPointF(19, 22), QPointF(5, 22)]))
        p.setBrush(QColor(255, 210, 0)); p.setPen(Qt.NoPen); p.drawEllipse(QPointF(16, 5), 3, 3)
    elif name in ('back', 'forward'):
        if name == 'back':
            _arrow(p, 20, 12, 4, 12)
        else:
            _arrow(p, 4, 12, 20, 12)
    elif name == 'open_up':
        p.setBrush(QColor(240, 200, 60)); p.setPen(QPen(Qt.black, 1)); p.drawRect(QRectF(3, 8, 18, 12))
        _arrow(p, 12, 17, 12, 4)
    elif name == 'print':
        p.setBrush(QColor(200, 200, 200)); p.setPen(QPen(Qt.black, 1)); p.drawRect(QRectF(3, 10, 18, 8))
        p.setBrush(Qt.white); p.drawRect(QRectF(7, 3, 10, 7)); p.drawRect(QRectF(7, 15, 10, 6))
    elif name == 'cut':
        p.setPen(QPen(Qt.black, 1.4)); p.drawLine(8, 3, 15, 15); p.drawLine(16, 3, 9, 15)
        p.setBrush(Qt.NoBrush); p.drawEllipse(QPointF(7, 18), 3, 3); p.drawEllipse(QPointF(17, 18), 3, 3)
    elif name == 'copy':
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 1)); p.drawRect(QRectF(3, 3, 11, 13)); p.drawRect(QRectF(9, 8, 11, 13))
    elif name == 'paste':
        p.setBrush(QColor(200, 160, 90)); p.setPen(QPen(Qt.black, 1)); p.drawRect(QRectF(4, 4, 14, 17))
        p.setBrush(Qt.white); p.drawRect(QRectF(10, 9, 10, 12))
    elif name == 'find':
        p.setPen(QPen(Qt.black, 1.6)); p.setBrush(QColor(170, 200, 255))
        p.drawEllipse(QRectF(3, 8, 8, 8)); p.drawEllipse(QRectF(13, 8, 8, 8)); p.drawLine(11, 11, 13, 11)
    elif name == 'object_props':
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 1)); p.drawRect(QRectF(3, 3, 18, 18))
        p.setPen(QPen(QColor(40, 40, 120), 1.4))
        for y in (8, 12, 16):
            p.drawLine(6, y, 9, y); p.drawLine(11, y, 18, y)
    elif name == 'view_area':
        p.setPen(QPen(Qt.black, 1.2, Qt.DashLine)); p.setBrush(Qt.NoBrush); p.drawRect(QRectF(3, 5, 12, 10))
        p.setPen(QPen(Qt.black, 1.6)); p.drawEllipse(QRectF(11, 11, 8, 8)); p.drawLine(18, 18, 22, 22)
    elif name == 'pan':
        p.setBrush(QColor(255, 225, 190)); p.setPen(QPen(Qt.black, 1))
        p.drawRoundedRect(QRectF(6, 9, 12, 12), 3, 3)
        for x in (7, 10, 13, 16):
            p.drawRoundedRect(QRectF(x, 3, 2.5, 9), 1, 1)
    elif name == 'enable':
        _flag(p, QColor(255, 230, 0), 'E')
    elif name == 'hier_state':
        p.setBrush(QColor(0, 220, 255)); p.setPen(QPen(QColor(0, 90, 160), 1.4)); p.drawEllipse(QRectF(3, 3, 18, 18))
        p.setBrush(Qt.white); p.drawEllipse(QRectF(9, 9, 6, 6))
    elif name == 'wait_state':
        p.setBrush(QColor(0, 220, 255)); p.setPen(QPen(QColor(0, 90, 160), 1.4)); p.drawEllipse(QRectF(3, 3, 18, 18))
        p.drawEllipse(QRectF(6, 6, 12, 12))
    elif name == 'comment':
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 1)); p.drawRect(QRectF(3, 3, 18, 18))
        p.setFont(QFont('Times', 12, QFont.Bold)); p.drawText(QRectF(3, 3, 18, 18), Qt.AlignCenter, 'T')
    elif name == 'panel':
        p.setPen(QPen(QColor(200, 0, 0), 1.6)); p.setBrush(Qt.NoBrush); p.drawRect(QRectF(4, 5, 16, 14))
    elif name == 'drc':
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 1)); p.drawRect(QRectF(3, 3, 15, 18))
        p.setPen(QPen(QColor(0, 150, 0), 2.2)); p.drawLine(7, 13, 10, 17); p.drawLine(10, 17, 20, 6)
    elif name == 'highlight':
        p.setPen(QPen(QColor(255, 120, 0), 3)); p.drawPolyline(QPolygonF([QPointF(3, 18), QPointF(12, 18), QPointF(12, 6), QPointF(21, 6)]))
    elif name == 'clear_highlight':
        p.setPen(QPen(QColor(150, 150, 150), 2)); p.drawPolyline(QPolygonF([QPointF(3, 18), QPointF(12, 18), QPointF(12, 6), QPointF(21, 6)]))
        p.setPen(QPen(QColor(200, 0, 0), 2)); p.drawLine(5, 5, 19, 19)
    elif name == 'block':
        p.setBrush(QColor(80, 160, 255)); p.setPen(QPen(QColor(0, 60, 160), 1.4)); p.drawRect(QRectF(5, 3, 14, 18))
    elif name == 'moduleware':
        p.setBrush(QColor(255, 200, 80)); p.setPen(QPen(Qt.black, 1)); p.drawRect(QRectF(4, 4, 16, 16))
        p.setFont(QFont('Arial', 7, QFont.Bold)); p.drawText(QRectF(4, 4, 16, 16), Qt.AlignCenter, 'MW')
    elif name == 'external_ip':
        p.setBrush(QColor(200, 120, 255)); p.setPen(QPen(Qt.black, 1)); p.drawRect(QRectF(4, 4, 16, 16))
        p.setFont(QFont('Arial', 7, QFont.Bold)); p.drawText(QRectF(4, 4, 16, 16), Qt.AlignCenter, 'IP')
    elif name == 'frame':
        p.setPen(QPen(QColor(0, 120, 0), 1.4, Qt.DashLine)); p.setBrush(Qt.NoBrush); p.drawRect(QRectF(3, 3, 18, 18))
        p.setPen(Qt.black); p.setFont(QFont('Arial', 6, QFont.Bold)); p.drawText(QRectF(4, 4, 16, 8), Qt.AlignLeft, 'FOR')
    elif name == 'bus':
        p.setPen(QPen(Qt.black, 3.5)); p.drawPolyline(QPolygonF([QPointF(3, 18), QPointF(12, 18), QPointF(12, 6), QPointF(21, 6)]))
    elif name == 'bundle':
        p.setPen(QPen(QColor(0, 0, 160), 1.4))
        for d in (-3, 0, 3):
            p.drawPolyline(QPolygonF([QPointF(3, 18 + d), QPointF(12 + d, 18 + d), QPointF(12 + d, 6 + d), QPointF(21, 6 + d)]))
    elif name == 'global_connector':
        p.setBrush(QColor(255, 230, 0)); p.setPen(QPen(Qt.black, 1)); p.drawEllipse(QRectF(5, 5, 14, 14))
    elif name == 'open_down':
        p.setBrush(QColor(0, 200, 0)); p.setPen(QPen(Qt.black, 1)); p.drawRect(QRectF(3, 3, 12, 10))
        _arrow(p, 12, 10, 19, 20)
    elif name == 'refresh':
        draw_refresh(p, S)
    p.end()
    ic = QIcon(pm)
    _CACHE[name] = ic
    return ic
