"""The Vietsemi logo in the application.

    image_path, logo        the logo files (resources/images/Vietsemi_*.png) and pixmaps of them
    app_icon,               the window icon: the Vietsemi mark on every window, dialog and the
    install_app_icon        Windows taskbar
    splash_picture          the picture of the start-up splash screen (shown by gui/status.py)
    show_about              Help > About

The logo files are resources/images/Vietsemi_*.png in the repository; a PyInstaller build
bundles them at the same relative path (scripts/HDLStudio.spec). When a file cannot
be found the windows simply show no logo.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from version import APP_NAME, RELEASE, VENDOR, VENDOR_URL, about_text

LOGO_WIDE = 'Vietsemi_Logo_Landscape_on_Light.png'   # mark and name side by side
LOGO_MARK = 'Vietsemi_Logo_Only_on_Light.png'        # the mark alone (window icon)
SPLASH_SIZE = (560, 300)                              # width, height of the splash picture


def image_path(name: str) -> str:
    """Absolute path of resources/images/<name>, in the repository or in a frozen build."""
    base = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, 'resources', 'images', name)


def logo(name: str = LOGO_WIDE, width: int = 0) -> QPixmap:
    """The logo `name` as a pixmap, scaled smoothly to `width` pixels (0 = natural size); a null
    pixmap when the file is missing.
    """
    pm = QPixmap(image_path(name))
    if not pm.isNull() and width:
        pm = pm.scaledToWidth(width, Qt.SmoothTransformation)
    return pm


def app_icon() -> QIcon:
    """Window icon of every HDL Studio window (the Vietsemi mark)."""
    return QIcon(image_path(LOGO_MARK))


_installed: dict = {}                           # what install_app_icon() has done in this process


def install_app_icon() -> None:
    """Give every window and dialog of the application the Vietsemi mark: set it as the
    application icon (windows without an icon of their own use it) and, on Windows, give the
    process its own taskbar identity so the taskbar shows the mark instead of the Python icon.
    Called by each window that can be the first one (Design Manager, editors run on their own).
    """
    app = QApplication.instance()
    if app is None:
        return
    if app.windowIcon().cacheKey() != _installed.get('key'):
        icon = app_icon()
        app.setWindowIcon(icon)
        _installed['key'] = app.windowIcon().cacheKey()
    if sys.platform == 'win32' and not _installed.get('taskbar'):
        _installed['taskbar'] = True
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Vietsemi.HDLStudio')
        except Exception:
            pass                                # an older Windows: the taskbar keeps its icon


def splash_picture() -> QPixmap:
    """The start-up picture: a white card with the wide logo, the product name, the release and
    the vendor. The strip below the grey line is left for the splash screen's status line.
    """
    w, h = SPLASH_SIZE
    pm = QPixmap(w, h)
    pm.fill(QColor('white'))
    p = QPainter(pm)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor('#c8c8c8'))
    p.drawRect(0, 0, w - 1, h - 1)
    wide = logo(width=380)
    if not wide.isNull():
        p.drawPixmap((w - wide.width()) // 2, 36, wide)
    p.setPen(QColor('#1f2d5a'))
    f = QFont(); f.setPointSize(18); f.setBold(True)
    p.setFont(f)
    p.drawText(QRect(0, 150, w, 34), Qt.AlignHCenter, APP_NAME)
    f = QFont(); f.setPointSize(10)
    p.setFont(f)
    p.setPen(QColor('#555555'))
    p.drawText(QRect(0, 186, w, 20), Qt.AlignHCenter, f'Version {RELEASE}')
    p.drawText(QRect(0, 208, w, 20), Qt.AlignHCenter, f'(c) {VENDOR}')
    p.setPen(QColor('#e0e0e0'))
    p.drawLine(16, h - 34, w - 16, h - 34)
    p.end()
    return pm


def show_about(parent: QWidget | None, part: str = '') -> None:
    """Help > About: the wide logo on top, then the product name, version and vendor."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(f'About {APP_NAME}')
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(24, 20, 24, 16)
    pm = logo(width=340)
    if not pm.isNull():
        pic = QLabel(); pic.setPixmap(pm); pic.setAlignment(Qt.AlignHCenter)
        lay.addWidget(pic)
        lay.addSpacing(12)
    lines = about_text(part).split('\n')
    head, rest = lines[0], lines[1:]
    body = '<br>'.join(l if l else '&nbsp;' for l in rest)
    body = body.replace(VENDOR_URL, f'<a href="{VENDOR_URL}">{VENDOR_URL}</a>')
    text = QLabel(f'<b style="font-size:12pt">{head}</b><br><br>{body}')
    text.setTextFormat(Qt.RichText)
    text.setOpenExternalLinks(True)
    text.setAlignment(Qt.AlignHCenter)
    text.setWordWrap(True)
    lay.addWidget(text)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok)
    buttons.accepted.connect(dlg.accept)
    lay.addWidget(buttons)
    dlg.exec()
