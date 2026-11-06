"""Telling the user what the tool is doing while the GUI thread is busy.

    SplashScreen     start-up window (the picture from branding.splash_picture()) with a
                     status line at the bottom, shown by bin/hdlstudio.py until the project is open
    StatusProgress   a text and a progress bar with a percentage, at the right of a window's
                     status bar; the Design Manager uses it while a project opens and its
                     libraries are scanned (Project.progress -> StatusProgress.scan_library)

Both repaint immediately (QApplication.processEvents), since the work runs in the GUI thread
and Qt would otherwise paint only when it is over.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QSplashScreen, QStatusBar

from .branding import splash_picture


def _repaint() -> None:
    """Let Qt paint what changed, without handling clicks or keys meanwhile."""
    QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)


class SplashScreen(QSplashScreen):
    """Start-up window: the Vietsemi splash picture and a status line below it."""

    def __init__(self):
        """Create the window from branding.splash_picture(); it stays above other windows."""
        super().__init__(splash_picture())
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

    def status(self, text: str) -> None:
        """Show `text` on the status line and repaint now."""
        self.showMessage('   ' + text, Qt.AlignLeft | Qt.AlignBottom, QColor('#333333'))
        _repaint()


class StatusProgress:
    """Progress at the right of a status bar: a text ("Scanning library X: 3/12 files") and a bar
    with the percentage. Hidden when idle.

    begin(text) / end() bracket a long operation and may nest (only the outermost end() hides
    the progress); step(text, done, total) moves the bar; scan_library() is the callback a
    Project calls while a library is scanned. `splash`, when set, also gets every message.
    """
    REPAINT_S = 0.05                    # repaint at most every 50 ms between forced repaints

    def __init__(self, bar: QStatusBar):
        """Add the (hidden) text and progress bar to `bar`."""
        self.label = QLabel()
        self.bar = QProgressBar()
        self.bar.setFixedWidth(220)
        self.bar.setMaximumHeight(16)
        self.bar.setTextVisible(True)
        self.bar.setFormat('%p%')
        self.bar.setAlignment(Qt.AlignCenter)
        bar.addPermanentWidget(self.label)
        bar.addPermanentWidget(self.bar)
        self.splash: SplashScreen | None = None
        self._depth = 0
        self._painted = 0.0
        self._show(False)

    # -- operation -----------------------------------------------------------------------
    def begin(self, text: str) -> None:
        """Start a long operation: show `text`, a busy bar (no percentage yet) and the wait cursor."""
        self._depth += 1
        if self._depth > 1:
            return
        self.label.setText(text)
        self.bar.setRange(0, 0)                         # busy until a step gives a size
        self._show(True)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self._paint(force=True)

    def step(self, text: str, done: int, total: int) -> None:
        """Show `text` and `done` of `total` on the bar (percentage). Outside begin()/end() the
        step that reaches `total` also hides the progress, so nothing is left at 100%.
        """
        self.label.setText(text)
        self.bar.setRange(0, max(total, 1))
        self.bar.setValue(min(done, max(total, 1)))
        self._show(True)
        # if self.splash is not None:
        #     pct = 100 * done // total if total else 100
        #     self.splash.status(f'{text} ({pct}%)')
        self._paint(force=done in (0, total))
        if self._depth == 0 and done >= total:
            self._show(False)

    def end(self) -> None:
        """End the operation started by the matching begin(); hide everything after the outermost."""
        self._depth = max(0, self._depth - 1)
        if self._depth:
            return
        self._show(False)
        if QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

    # -- callbacks -----------------------------------------------------------------------
    def scan_library(self, library: str, done: int, total: int) -> None:
        """Project.progress: library `library` has read `done` of its `total` HDL files."""
        self.step(f'Scanning library {library}: {done}/{total} files', done, total)

    # -- helpers -------------------------------------------------------------------------
    def _show(self, on: bool) -> None:
        """Show or hide the text and the bar together."""
        self.label.setVisible(on)
        self.bar.setVisible(on)

    def _paint(self, force: bool = False) -> None:
        """Repaint now when forced, else at most every REPAINT_S seconds."""
        now = time.monotonic()
        if force or now - self._painted > self.REPAINT_S:
            self._painted = now
            _repaint()
