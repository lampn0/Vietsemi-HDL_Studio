"""Design Manager icons, drawn with QPainter: large launcher buttons for the
left "Main" bar, and small icons for design units, views and files in the
explorer trees. Same meaning and place as in the legacy tool, own artwork."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

_CACHE: dict[str, QIcon] = {}

GREEN, DARK_GREEN = QColor(0, 215, 0), QColor(0, 110, 0)
BLUE, NAVY = QColor(40, 110, 230), QColor(0, 0, 140)
YELLOW, RED = QColor(255, 225, 0), QColor(220, 20, 20)


def _page(p: QPainter, r: QRectF, fill=Qt.white):
    """Sheet of paper with a folded corner."""
    f = r.width() * 0.28
    p.setBrush(fill)
    p.setPen(QPen(QColor(60, 60, 60), max(1.0, r.width() / 14)))
    p.drawPolygon(QPolygonF([r.topLeft(), QPointF(r.right() - f, r.top()), QPointF(r.right(), r.top() + f),
                             r.bottomRight(), r.bottomLeft()]))
    p.drawPolyline(QPolygonF([QPointF(r.right() - f, r.top()), QPointF(r.right() - f, r.top() + f),
                              QPointF(r.right(), r.top() + f)]))


def _lines(p: QPainter, r: QRectF, color, n=3):
    """`n` horizontal text lines inside rectangle r (the "text" picture on page icons)."""
    p.setPen(QPen(color, max(1.0, r.height() / 12)))
    for k in range(n):
        y = r.top() + r.height() * (0.35 + 0.18 * k)
        p.drawLine(QPointF(r.left() + r.width() * 0.2, y), QPointF(r.right() - r.width() * 0.2, y))


def _block(p: QPainter, r: QRectF, fill=GREEN, pins=True):
    """Component symbol: a filled block with pins on both sides."""
    p.setBrush(fill)
    p.setPen(QPen(DARK_GREEN, max(1.0, r.width() / 12)))
    p.drawRect(r)
    if pins:
        p.setPen(QPen(Qt.black, max(1.0, r.width() / 14)))
        for k in (0.3, 0.7):
            y = r.top() + r.height() * k
            p.drawLine(QPointF(r.left() - r.width() * 0.3, y), QPointF(r.left(), y))
            p.drawLine(QPointF(r.right(), y), QPointF(r.right() + r.width() * 0.3, y))


CYAN = QColor(0, 220, 240)


def _chip(p: QPainter, pins: bool):
    """Tall green design unit block; with pins for a component."""
    p.setBrush(GREEN); p.setPen(QPen(DARK_GREEN, 1)); p.drawRect(QRectF(5, 1.5, 8, 13))
    p.setPen(QPen(QColor(0, 150, 0), 1))
    for y in (4, 7, 10):
        p.drawPoint(QPointF(11, y)); p.drawPoint(QPointF(11, y + 1.5))
    if pins:
        p.setPen(Qt.NoPen); p.setBrush(QColor(40, 40, 40))
        for y in (3.5, 10.5):
            p.drawPolygon(QPolygonF([QPointF(1, y - 1.8), QPointF(4.5, y), QPointF(1, y + 1.8)]))
        p.drawPolygon(QPolygonF([QPointF(13.5, 6.2), QPointF(16, 8), QPointF(13.5, 9.8)]))


def _draw_small(p: QPainter, name: str):
    """16x16 tree icons."""
    if name == 'unit_component':          # component: green block with pins (it has a symbol / graphics)
        _chip(p, pins=True)
    elif name == 'unit_module':           # HDL module without a symbol
        _chip(p, pins=False)
    elif name == 'unit_package':
        p.setBrush(QColor(210, 160, 90)); p.setPen(QPen(QColor(110, 70, 20), 1)); p.drawRect(QRectF(2, 5, 12, 9))
        p.drawLine(2, 8, 14, 8); p.drawLine(8, 5, 8, 14)
    elif name == 'unit_interface':
        p.setBrush(QColor(150, 210, 255)); p.setPen(QPen(NAVY, 1)); p.drawRect(QRectF(3, 3, 10, 10))
        p.drawLine(0, 8, 3, 8); p.drawLine(13, 8, 16, 8)
    elif name == 'unit_missing':
        p.setBrush(Qt.white); p.setPen(QPen(RED, 1.2, Qt.DashLine)); p.drawRect(QRectF(4, 2, 8, 12))
        p.setPen(QPen(RED, 1.6)); p.drawLine(6, 6, 10, 10); p.drawLine(10, 6, 6, 10)
    elif name == 'view_bd':               # block diagram: a tall block wired to two small blocks
        p.setPen(QPen(Qt.black, 1))
        p.drawPolyline(QPolygonF([QPointF(6, 4), QPointF(11, 4)]))
        p.drawPolyline(QPolygonF([QPointF(6, 11), QPointF(9, 11), QPointF(9, 12), QPointF(11, 12)]))
        p.drawLine(4, 13, 4, 15)
        p.setBrush(CYAN); p.setPen(QPen(QColor(0, 70, 120), 1)); p.drawRect(QRectF(1.5, 1.5, 4.5, 11))
        p.setBrush(GREEN); p.setPen(QPen(DARK_GREEN, 1)); p.drawRect(QRectF(10.5, 1.5, 4.5, 4.5))
        p.setBrush(CYAN); p.setPen(QPen(QColor(0, 70, 120), 1)); p.drawRect(QRectF(10.5, 10, 4.5, 4.5))
    elif name == 'view_fsm':              # state machine: two states on a ring
        p.setPen(QPen(Qt.black, 1.2)); p.setBrush(Qt.NoBrush); p.drawEllipse(QRectF(3, 3, 10, 10))
        p.setPen(QPen(Qt.black, 0.8))
        p.setBrush(QColor(0, 200, 60)); p.drawEllipse(QRectF(1, 1, 5.5, 5.5))
        p.setBrush(CYAN); p.drawEllipse(QRectF(9.5, 9.5, 5.5, 5.5))
    elif name == 'view_text':             # HDL module text: page with a yellow M tag
        _page(p, QRectF(3, 2, 11, 13))
        p.setPen(QPen(QColor(0, 130, 140), 1.2))
        for y in (8, 10.5, 13):
            p.drawLine(QPointF(5.5, y), QPointF(11.5, y))
        p.setBrush(YELLOW); p.setPen(QPen(QColor(150, 110, 0), 0.8)); p.drawRoundedRect(QRectF(0.5, 0.5, 8, 6), 1.5, 1.5)
        p.setPen(Qt.black); p.setFont(QFont('Arial', 5, QFont.Bold)); p.drawText(QRectF(0.5, 0.5, 8, 6), Qt.AlignCenter, 'M')
    elif name == 'view_symbol':
        _chip(p, pins=True)
    elif name == 'view_other':
        _page(p, QRectF(2, 1, 12, 14), QColor(225, 225, 225))
    elif name == 'folder':
        p.setBrush(QColor(255, 215, 90)); p.setPen(QPen(QColor(150, 110, 20), 1))
        p.drawPolygon(QPolygonF([QPointF(1, 4), QPointF(6, 4), QPointF(7, 6), QPointF(15, 6), QPointF(15, 14),
                                 QPointF(1, 14)]))
    elif name == 'design_files':          # book of source files
        p.setBrush(QColor(60, 60, 60)); p.setPen(Qt.NoPen); p.drawRect(QRectF(2, 3, 12, 11))
        p.setBrush(Qt.white); p.drawRect(QRectF(4, 4, 9, 7))
        p.setPen(QPen(BLUE, 1)); p.drawLine(5, 6, 12, 6); p.drawLine(5, 8, 12, 8)
    elif name == 'file_hdl':
        _page(p, QRectF(3, 1, 11, 14)); _lines(p, QRectF(3, 1, 11, 14), DARK_GREEN)
    elif name == 'file_error':
        _page(p, QRectF(3, 1, 11, 14), QColor(255, 225, 225)); _lines(p, QRectF(3, 1, 11, 14), RED)
    elif name == 'file_view':
        _page(p, QRectF(3, 1, 11, 14)); p.setBrush(GREEN); p.setPen(QPen(DARK_GREEN, 1))
        p.drawRect(QRectF(6, 6, 5, 6))
    elif name == 'file_lock':
        p.setPen(QPen(QColor(90, 90, 90), 1.6)); p.setBrush(Qt.NoBrush); p.drawArc(QRectF(5, 1, 6, 8), 0, 180 * 16)
        p.drawLine(5, 5, 5, 7); p.drawLine(11, 5, 11, 7)
        p.setBrush(YELLOW); p.setPen(QPen(QColor(130, 100, 0), 1)); p.drawRect(QRectF(3, 7, 10, 8))
    elif name == 'frame':                 # generate frame (FOR / IF) in the hierarchy
        p.setPen(QPen(DARK_GREEN, 1.2, Qt.DashLine)); p.setBrush(Qt.NoBrush); p.drawRect(QRectF(1, 2, 14, 12))
        _block(p, QRectF(6, 5, 4, 6), GREEN, pins=False)
    elif name == 'hierarchy_root':        # a small tree of blocks
        p.setPen(QPen(Qt.black, 1))
        p.drawLine(8, 6, 8, 9); p.drawLine(3, 9, 13, 9); p.drawLine(3, 9, 3, 11); p.drawLine(13, 9, 13, 11)
        p.setBrush(QColor(40, 110, 230)); p.setPen(QPen(NAVY, 0.8)); p.drawRect(QRectF(5.5, 1, 5, 5))
        p.setBrush(GREEN); p.setPen(QPen(DARK_GREEN, 0.8))
        p.drawRect(QRectF(0.5, 10.5, 5, 5)); p.drawRect(QRectF(10.5, 10.5, 5, 5))
    elif name == 'library':
        for k, c in enumerate((QColor(200, 60, 60), QColor(60, 120, 200), QColor(60, 160, 60))):
            p.setBrush(c); p.setPen(QPen(Qt.black, 0.8)); p.drawRect(QRectF(2 + 4 * k, 2, 4, 12))
    elif name == 'library_protected':
        _draw_small(p, 'library')
        p.setBrush(YELLOW); p.setPen(QPen(QColor(130, 100, 0), 1)); p.drawRect(QRectF(9, 9, 6, 6))
    elif name.startswith('tb_'):
        _draw_toolbar(p, name[3:])


def _lens(p: QPainter, cx: float, cy: float, r: float = 3.2):
    """Magnifying glass centred at (cx, cy) with its handle to the lower right."""
    p.setPen(QPen(QColor(40, 40, 40), 1.6)); p.drawLine(QPointF(cx + r * 0.7, cy + r * 0.7), QPointF(cx + r + 2.5, cy + r + 2.5))
    p.setBrush(QColor(200, 230, 255)); p.setPen(QPen(NAVY, 1.1)); p.drawEllipse(QPointF(cx, cy), r, r)


def _tick(p: QPainter, x: float, y: float, s: float = 1.0):
    """Green tick with its corner at (x, y)."""
    p.setPen(QPen(QColor(0, 160, 0), 1.8 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline(QPolygonF([QPointF(x - 3 * s, y - 3 * s), QPointF(x, y), QPointF(x + 6 * s, y - 8 * s)]))


def _draw_toolbar(p: QPainter, name: str):
    """16x16 icons of the Design Manager toolbars (dm_toolbar.py)."""
    if name == 'new':                     # page with a yellow spark
        _page(p, QRectF(3, 2, 11, 13))
        p.setBrush(YELLOW); p.setPen(QPen(QColor(200, 150, 0), 0.8)); p.drawEllipse(QPointF(4, 4), 3, 3)
    elif name == 'open':                  # open folder
        p.setBrush(QColor(255, 215, 90)); p.setPen(QPen(QColor(150, 110, 20), 1))
        p.drawPolygon(QPolygonF([QPointF(1, 3), QPointF(6, 3), QPointF(7, 5), QPointF(13, 5), QPointF(13, 7),
                                 QPointF(4, 7), QPointF(1, 14)]))
        p.setBrush(QColor(240, 190, 50))
        p.drawPolygon(QPolygonF([QPointF(4, 7), QPointF(15, 7), QPointF(12, 14), QPointF(1, 14)]))
    elif name == 'print':                 # printer
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 0.9)); p.drawRect(QRectF(4, 1.5, 8, 5))
        p.setBrush(QColor(190, 190, 190)); p.drawRect(QRectF(1.5, 6.5, 13, 6))
        p.setBrush(Qt.white); p.drawRect(QRectF(4, 10.5, 8, 4.5))
        p.setPen(QPen(DARK_GREEN, 1)); p.drawPoint(QPointF(12.5, 8.5))
    elif name == 'document':              # page with linked coloured views
        _page(p, QRectF(3, 1, 11, 14))
        for (x, y), c in zip(((6, 6), (10, 9), (6, 12)), (RED, GREEN, BLUE)):
            p.setBrush(c); p.setPen(QPen(Qt.black, 0.6)); p.drawEllipse(QPointF(x, y), 1.7, 1.7)
    elif name == 'cut':                   # scissors
        p.setPen(QPen(NAVY, 1.3)); p.drawLine(QPointF(5, 1.5), QPointF(10, 10)); p.drawLine(QPointF(11, 1.5), QPointF(6, 10))
        p.setBrush(Qt.NoBrush); p.drawEllipse(QPointF(5, 12.5), 2.3, 2.3); p.drawEllipse(QPointF(11, 12.5), 2.3, 2.3)
    elif name == 'copy':                  # two pages
        p.setBrush(Qt.white); p.setPen(QPen(NAVY, 1)); p.drawRect(QRectF(1.5, 1.5, 8, 9)); p.drawRect(QRectF(6.5, 5.5, 8, 9))
        p.setPen(QPen(NAVY, 0.8))
        for y in (8.5, 10.5, 12.5):
            p.drawLine(QPointF(8.5, y), QPointF(12.5, y))
    elif name == 'paste':                 # clipboard with a page
        p.setBrush(QColor(170, 120, 60)); p.setPen(QPen(QColor(90, 60, 20), 1)); p.drawRect(QRectF(2, 3, 10, 12))
        p.setBrush(QColor(200, 200, 200)); p.drawRect(QRectF(5, 1.5, 4, 3))
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 0.8)); p.drawRect(QRectF(7, 7, 7.5, 8))
    elif name == 'delete':                # dark red cross
        p.setPen(QPen(QColor(150, 0, 0), 2.2, Qt.SolidLine, Qt.RoundCap)); p.drawLine(3, 3, 13, 13); p.drawLine(13, 3, 3, 13)
    elif name == 'properties':            # form with a pointer
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 0.9)); p.drawRect(QRectF(1.5, 3.5, 11, 11))
        p.setPen(QPen(NAVY, 1))
        for y in (6.5, 9, 11.5):
            p.drawLine(QPointF(3.5, y), QPointF(5, y)); p.drawLine(QPointF(6.5, y), QPointF(10.5, y))
        p.setBrush(Qt.black); p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(11, 0.5), QPointF(15.5, 3), QPointF(13, 3.5), QPointF(12.5, 6)]))
    elif name == 'hierarchy':             # tree of blocks
        _draw_small(p, 'hierarchy_root')
    elif name == 'cross_highlight':       # pen over a yellow line
        p.setPen(QPen(YELLOW, 2.4)); p.drawLine(QPointF(1, 14), QPointF(15, 14))
        p.setPen(QPen(QColor(60, 60, 60), 1.6, Qt.SolidLine, Qt.RoundCap)); p.drawLine(QPointF(4, 11), QPointF(13, 2))
        p.setPen(QPen(NAVY, 1)); p.drawLine(QPointF(3, 12.5), QPointF(4, 11))
    elif name == 'explore':               # library book under a lens
        p.setBrush(QColor(255, 220, 60)); p.setPen(QPen(QColor(120, 90, 0), 0.9)); p.drawRect(QRectF(1.5, 2, 9, 11))
        p.setPen(QPen(NAVY, 0.8))
        for y in (5, 7, 9):
            p.drawLine(QPointF(3.5, y), QPointF(8.5, y))
        _lens(p, 9.5, 9, 3)
    elif name == 'explorer_view':         # window with list rows
        p.setBrush(Qt.white); p.setPen(QPen(NAVY, 1)); p.drawRect(QRectF(1.5, 1.5, 13, 13))
        p.setBrush(NAVY); p.drawRect(QRectF(1.5, 1.5, 13, 2.5))
        p.setBrush(BLUE); p.setPen(Qt.NoPen)
        for y in (6, 9, 12):
            p.drawRect(QRectF(3.5, y - 0.8, 2, 1.8))
        p.setPen(QPen(QColor(60, 60, 60), 1))
        for y in (6, 9, 12):
            p.drawLine(QPointF(7, y), QPointF(12.5, y))
    elif name == 'viewpoint':             # stacked cubes
        for (x, y), c in zip(((5, 1.5), (1.5, 7.5), (8.5, 7.5)), (YELLOW, CYAN, BLUE)):
            p.setBrush(c); p.setPen(QPen(NAVY, 0.9)); p.drawRect(QRectF(x, y, 6, 6))
    elif name == 'find':                  # binoculars
        p.setBrush(QColor(30, 30, 30)); p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(1.5, 4, 5.5, 10), 1.5, 1.5); p.drawRoundedRect(QRectF(9, 4, 5.5, 10), 1.5, 1.5)
        p.drawRect(QRectF(6, 6, 4, 3))
        p.setBrush(QColor(140, 180, 230)); p.drawEllipse(QPointF(4.2, 12), 1.6, 1.6); p.drawEllipse(QPointF(11.8, 12), 1.6, 1.6)
    elif name == 'components':            # green component block
        _chip(p, pins=True)
    elif name == 'designpad':             # note with a pencil
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 0.9, Qt.DotLine)); p.drawRect(QRectF(1.5, 3.5, 10, 11))
        p.setPen(QPen(RED, 2.2, Qt.SolidLine, Qt.FlatCap)); p.drawLine(QPointF(7, 10), QPointF(14, 2.5))
        p.setPen(QPen(Qt.black, 1)); p.drawLine(QPointF(6, 11.5), QPointF(7, 10))
    elif name == 'refresh':               # the shared Refresh icon (icons.draw_refresh)
        from .icons import draw_refresh
        draw_refresh(p, 16)
    elif name == 'convert':               # text page turning into blocks
        _page(p, QRectF(1, 1, 8, 10)); _lines(p, QRectF(1, 1, 8, 10), QColor(140, 140, 0))
        p.setPen(QPen(Qt.black, 1)); p.drawLine(QPointF(4, 11), QPointF(4, 14)); p.drawLine(QPointF(4, 14), QPointF(8, 14))
        p.setBrush(CYAN); p.setPen(QPen(NAVY, 0.8)); p.drawRect(QRectF(8, 11, 4, 4)); p.drawRect(QRectF(12, 8, 3.5, 4))
    elif name == 'visualize':             # person with a diagram page
        p.setBrush(QColor(80, 80, 80)); p.setPen(Qt.NoPen); p.drawEllipse(QPointF(4, 5), 2.5, 2.5)
        p.drawRoundedRect(QRectF(1, 8, 6, 6), 2, 2)
        _page(p, QRectF(7, 1, 8, 10)); _lines(p, QRectF(7, 1, 8, 10), NAVY)
        p.setBrush(GREEN); p.setPen(QPen(DARK_GREEN, 0.8)); p.drawRect(QRectF(9, 11, 3.5, 4))
    elif name == 'view_hdl':              # lens over an HDL page
        _page(p, QRectF(6, 1, 9, 11)); _lines(p, QRectF(6, 1, 9, 11), NAVY)
        _lens(p, 6, 8.5, 4)
        p.setPen(QPen(NAVY, 0.9))
        for y in (7.5, 9.5):
            p.drawLine(QPointF(4, y), QPointF(8, y))
    elif name == 'tasks':                 # window with a hammer
        p.setBrush(Qt.white); p.setPen(QPen(NAVY, 1)); p.drawRect(QRectF(1.5, 1.5, 13, 11))
        p.setBrush(NAVY); p.drawRect(QRectF(1.5, 1.5, 13, 2.5))
        p.setPen(QPen(QColor(140, 90, 40), 1.8)); p.drawLine(QPointF(7, 14.5), QPointF(12, 7.5))
        p.setBrush(QColor(90, 90, 90)); p.setPen(QPen(Qt.black, 0.8))
        p.drawPolygon(QPolygonF([QPointF(9.5, 6), QPointF(13, 4.5), QPointF(15, 7.5), QPointF(11.5, 9)]))
    elif name == 'check':                 # checked sheet
        _page(p, QRectF(2, 3, 10, 12)); _lines(p, QRectF(2, 3, 10, 12), QColor(150, 150, 150))
        _tick(p, 8, 11, 0.9)
    elif name == 'registers':             # register file: two bit cells
        p.setBrush(QColor(210, 210, 210)); p.setPen(QPen(Qt.black, 0.9)); p.drawRect(QRectF(1.5, 2.5, 13, 11))
        p.setBrush(GREEN); p.setPen(QPen(DARK_GREEN, 0.8)); p.drawRect(QRectF(6.5, 2.5, 3, 11))
    elif name == 'generate':              # pages with a pencil
        for k in range(3):
            p.setBrush(Qt.white); p.setPen(QPen(QColor(70, 70, 70), 0.8))
            p.drawRect(QRectF(1.5 + k * 1.5, 7 - k * 1.5, 9, 6))
        p.setPen(QPen(QColor(200, 150, 0), 2.2, Qt.SolidLine, Qt.FlatCap)); p.drawLine(QPointF(9, 9), QPointF(15, 1.5))
        p.setPen(QPen(Qt.black, 1)); p.drawLine(QPointF(8, 10.5), QPointF(9, 9))
    elif name == 'simulate':              # waveform
        p.setPen(QPen(RED, 1.6, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)); p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(1, 12), QPointF(4, 12), QPointF(4, 4), QPointF(8, 4), QPointF(8, 12),
                                  QPointF(11, 12), QPointF(11, 4), QPointF(15, 4)]))
    elif name == 'synthesize':            # gate driving a bubble
        p.setPen(QPen(Qt.black, 1)); p.drawLine(1, 5, 4, 5); p.drawLine(1, 11, 4, 11); p.drawLine(13, 8, 15, 8)
        p.setBrush(QColor(80, 140, 255)); p.setPen(QPen(NAVY, 1))
        p.drawPolygon(QPolygonF([QPointF(4, 2.5), QPointF(11, 8), QPointF(4, 13.5)]))
        p.setBrush(Qt.white); p.drawEllipse(QPointF(12, 8), 1.4, 1.4)


def _draw_large(p: QPainter, name: str):
    """40x40 launcher icons of the left Main bar."""
    if name == 'launch_new':              # new HDL design: page with a spark
        _page(p, QRectF(8, 4, 24, 32))
        p.setBrush(BLUE); p.setPen(Qt.NoPen); p.drawRect(QRectF(11, 14, 18, 9))
        p.setPen(Qt.white); p.setFont(QFont('Arial', 6, QFont.Bold)); p.drawText(QRectF(11, 14, 18, 9), Qt.AlignCenter, 'HDL')
        p.setBrush(YELLOW); p.setPen(QPen(QColor(200, 150, 0), 1))
        star = QPainterPath(); star.addEllipse(QPointF(9, 7), 5, 5); p.drawPath(star)
        p.setPen(QPen(QColor(200, 150, 0), 1.6)); p.drawLine(9, 2, 9, 12); p.drawLine(4, 7, 14, 7)
    elif name == 'launch_check':          # sheet with a green tick
        _page(p, QRectF(7, 5, 24, 30)); _lines(p, QRectF(7, 5, 24, 30), QColor(120, 120, 120))
        p.setPen(QPen(QColor(0, 160, 0), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(13, 21), QPointF(19, 28), QPointF(34, 8)]))
    elif name == 'launch_simulate':       # waveform
        p.setPen(QPen(RED, 3.5, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)); p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(3, 28), QPointF(10, 28), QPointF(10, 12), QPointF(18, 12), QPointF(18, 28),
                                  QPointF(25, 28), QPointF(25, 12), QPointF(33, 12), QPointF(33, 28), QPointF(37, 28)]))
    elif name == 'launch_synthesize':     # an AND and an OR gate driving a NOT gate
        blue_pen = QPen(NAVY, 1.4)
        p.setPen(QPen(Qt.black, 1.4))
        for y in (7, 13, 25, 31):                       # gate inputs
            p.drawLine(QPointF(1, y), QPointF(5, y))
        p.drawPolyline(QPolygonF([QPointF(15, 10), QPointF(19, 10), QPointF(19, 18), QPointF(22, 18)]))
        p.drawPolyline(QPolygonF([QPointF(16, 28), QPointF(19, 28), QPointF(19, 22), QPointF(22, 22)]))
        p.drawLine(QPointF(36, 20), QPointF(39, 20))
        p.setBrush(QColor(80, 140, 255)); p.setPen(blue_pen)
        and_g = QPainterPath(QPointF(5, 4)); and_g.lineTo(10, 4)
        and_g.arcTo(QRectF(5, 4, 10, 12), 90, -180); and_g.lineTo(5, 16); and_g.closeSubpath()
        p.drawPath(and_g)
        or_g = QPainterPath(QPointF(4, 22))
        or_g.quadTo(QPointF(13, 22), QPointF(17, 28)); or_g.quadTo(QPointF(13, 34), QPointF(4, 34))
        or_g.quadTo(QPointF(8, 28), QPointF(4, 22)); p.drawPath(or_g)
        # NOT: triangle with an output bubble; both gates feed its input
        p.setBrush(QColor(40, 110, 230))
        p.drawPolygon(QPolygonF([QPointF(22, 13), QPointF(33, 20), QPointF(22, 27)]))
        p.setBrush(Qt.white); p.drawEllipse(QPointF(34.5, 20), 2, 2)
    elif name == 'launch_document':       # linked views around a document
        p.setPen(QPen(QColor(90, 90, 90), 1.4)); p.setBrush(Qt.NoBrush); p.drawEllipse(QRectF(8, 8, 24, 24))
        for (x, y), c in zip(((20, 6), (32, 22), (8, 22)), (RED, GREEN, BLUE)):
            p.setBrush(c); p.setPen(QPen(Qt.black, 1)); p.drawRect(QRectF(x - 5, y - 5, 10, 10))
        _page(p, QRectF(15, 15, 10, 12))
    elif name == 'launch_registers':      # D flip-flop
        p.setPen(QPen(Qt.black, 1.6))
        p.drawLine(QPointF(2, 13), QPointF(10, 13))      # D in
        p.drawLine(QPointF(2, 28), QPointF(10, 28))      # clock in
        p.drawLine(QPointF(30, 13), QPointF(38, 13))     # Q out
        p.setBrush(YELLOW); p.setPen(QPen(QColor(120, 90, 0), 1.6)); p.drawRect(QRectF(10, 5, 20, 30))
        p.setBrush(Qt.white); p.setPen(QPen(Qt.black, 1.2))
        p.drawPolygon(QPolygonF([QPointF(10, 24), QPointF(15, 28), QPointF(10, 32)]))   # clock edge
        p.setPen(Qt.black); p.setFont(QFont('Arial', 8, QFont.Bold))
        p.drawText(QRectF(11, 7, 8, 12), Qt.AlignLeft | Qt.AlignVCenter, 'D')
        p.drawText(QRectF(21, 7, 8, 12), Qt.AlignRight | Qt.AlignVCenter, 'Q')


def dm_icon(name: str) -> QIcon:
    """The Design Manager icon `name`, drawn once and cached: 'launch_*' names are the 40x40
    buttons of the left bar, all others 16x16 tree icons.
    """
    if name in _CACHE:
        return _CACHE[name]
    large = name.startswith('launch_')
    size = 40 if large else 16
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    (_draw_large if large else _draw_small)(p, name)
    p.end()
    ic = QIcon(pm)
    if name.startswith('tb_'):
        ic.addPixmap(_disabled(pm), QIcon.Disabled)
    _CACHE[name] = ic
    return ic


def _disabled(pm: QPixmap) -> QPixmap:
    """Greyed look of a toolbar icon, as the legacy tool draws a button it cannot use: the icon in
    light grey (the style's own disabled look keeps dark colours dark)."""
    img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha():
                g = 150 + int(0.4 * (0.3 * c.red() + 0.59 * c.green() + 0.11 * c.blue()))
                img.setPixelColor(x, y, QColor(min(g, 235), min(g, 235), min(g, 235), c.alpha()))
    return QPixmap.fromImage(img)


ROOT_TEXT = QColor(0, 0, 220)          # name of the design root (and of its library) is blue


def _arrow(p: QPainter, x: float = 1):
    """Cyan arrow pointing right: the default view, or the design root."""
    p.setBrush(QColor(110, 210, 230)); p.setPen(QPen(QColor(0, 110, 140), 1))
    p.drawPolygon(QPolygonF([QPointF(x, 3), QPointF(x + 9, 8), QPointF(x, 13)]))


def _diamond(p: QPainter, cx: float):
    """Yellow diamond after the icon: the design root marker."""
    p.setBrush(YELLOW); p.setPen(QPen(QColor(140, 110, 0), 1))
    p.drawPolygon(QPolygonF([QPointF(cx, 2.5), QPointF(cx + 4, 8), QPointF(cx, 13.5), QPointF(cx - 4, 8)]))


def tree_icon(base: QIcon, default: bool = False, root: bool = False) -> QIcon:
    """40x16 icon for the explorer trees: a cyan arrow in front marks the default view
    or the design root, a yellow diamond behind the icon marks the design root."""
    key = f'tree:{base.cacheKey()}:{default}:{root}'
    if key in _CACHE:
        return _CACHE[key]
    pm = QPixmap(40, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if default or root:
        _arrow(p)
    p.drawPixmap(12, 0, base.pixmap(16, 16))
    if root:
        _diamond(p, 34)
    p.end()
    ic = QIcon(pm)
    _CACHE[key] = ic
    return ic


def library_icon(protected: bool = False, shared: bool = False, root: bool = False) -> QIcon:
    """Library row of the project tree: book, two people for a shared library, and the
    arrow + diamond when the library holds the design root."""
    key = f'lib:{protected}:{shared}:{root}'
    if key in _CACHE:
        return _CACHE[key]
    pm = QPixmap(48, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if root:
        _arrow(p)
    p.drawPixmap(12, 0, dm_icon('library_protected' if protected else 'library').pixmap(16, 16))
    x = 29
    if shared:                                   # two people: library from the shared project
        for dx in (0, 5):
            p.setBrush(NAVY); p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(x + dx, 3, 4, 4)); p.drawRoundedRect(QRectF(x + dx - 0.5, 8, 5, 6), 1.5, 1.5)
        x += 11
    if root:
        _diamond(p, x + 4)
    p.end()
    ic = QIcon(pm)
    _CACHE[key] = ic
    return ic


def _spark(p: QPainter, x: float = 3.5, y: float = 3.5):
    """Yellow spark: something new is created."""
    p.setPen(QPen(QColor(200, 150, 0), 1.2))
    p.drawLine(QPointF(x - 3, y), QPointF(x + 3, y)); p.drawLine(QPointF(x, y - 3), QPointF(x, y + 3))
    p.setBrush(YELLOW); p.setPen(QPen(QColor(200, 150, 0), 0.6)); p.drawEllipse(QPointF(x, y), 1.8, 1.8)


def project_icon(name: str) -> QIcon:
    """24x24 icons of the left Project page, drawn in a 16x16 space."""
    key = 'project:' + name
    if key in _CACHE:
        return _CACHE[key]
    pm = QPixmap(24, 24)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(1.5, 1.5)
    if name in ('new_project', 'new_library', 'explore_library', 'close_project'):
        p.save(); p.translate(2, 2); p.scale(0.85, 0.85); _draw_small(p, 'library'); p.restore()
    if name == 'new_project':
        p.setBrush(Qt.NoBrush); p.setPen(QPen(NAVY, 1)); p.drawRect(QRectF(1.5, 1.5, 14, 13.5))
        _spark(p)
    elif name == 'new_library':
        _spark(p)
    elif name == 'open_project':
        _draw_small(p, 'folder')
        p.setPen(QPen(DARK_GREEN, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(8, 11), QPointF(8, 2)]))
        p.drawPolyline(QPolygonF([QPointF(5, 5), QPointF(8, 2), QPointF(11, 5)]))
    elif name == 'edit_mappings':             # a library mapped to a folder, and a pencil
        _draw_small(p, 'folder')
        p.setPen(QPen(QColor(120, 70, 0), 1)); p.setBrush(YELLOW)
        p.drawPolygon(QPolygonF([QPointF(9, 13), QPointF(15, 7), QPointF(16, 8), QPointF(10, 14), QPointF(8.5, 14.5)]))
    elif name == 'set_default':
        _arrow(p, 4)
    elif name == 'explore_library':           # library and a magnifying glass
        p.setPen(QPen(QColor(60, 60, 60), 2)); p.drawLine(QPointF(12, 12), QPointF(15.5, 15.5))
        p.setBrush(QColor(220, 240, 255, 200)); p.setPen(QPen(QColor(60, 60, 60), 1.2))
        p.drawEllipse(QPointF(10, 10), 3.5, 3.5)
    elif name == 'new_add':
        _draw_small(p, 'file_hdl'); _spark(p)
    elif name == 'version':                   # stacked revisions of a file
        for k in (2, 1, 0):
            _page(p, QRectF(2 + 2 * k, 1 + 1.5 * k, 9, 11), QColor(255, 255, 255) if k == 0 else QColor(215, 215, 215))
        p.setBrush(BLUE); p.setPen(Qt.NoPen); p.drawEllipse(QPointF(12.5, 12.5), 3, 3)
        p.setPen(QPen(Qt.white, 1)); p.drawLine(QPointF(12.5, 10.8), QPointF(12.5, 12.5))
        p.drawLine(QPointF(12.5, 12.5), QPointF(14, 12.5))
    elif name == 'close_project':
        p.setPen(QPen(RED, 2.2, Qt.SolidLine, Qt.RoundCap)); p.drawLine(9, 9, 15, 15); p.drawLine(15, 9, 9, 15)
    p.end()
    ic = QIcon(pm)
    _CACHE[key] = ic
    return ic


def unit_icon(du) -> QIcon:
    """Icon for a design unit by what it is."""
    if du is None:
        return dm_icon('unit_missing')
    if du.type == 'Component':
        return dm_icon('unit_component')
    kind = du.hdl.kind if du.hdl else ''
    return dm_icon({'package': 'unit_package', 'interface': 'unit_interface'}.get(kind, 'unit_module'))


def view_icon(view) -> QIcon:
    """Tree icon of a view by its kind (block diagram, state diagram, text, symbol, other)."""
    return dm_icon({'bd': 'view_bd', 'fsm': 'view_fsm', 'text': 'view_text',
                    'symbol': 'view_symbol'}.get(view.kind, 'view_other'))
