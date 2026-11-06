"""Start the state machine editor on its own (no project, no Design Manager).

    python bin/fsm_editor.py                 # opens the built-in example FSM (traffic light)
    python bin/fsm_editor.py path/to/fsm.sm  # opens a legacy state diagram (.sm)
    python bin/fsm_editor.py my.fsm.json     # opens a diagram saved by HDL Studio (.fsm.json)

Useful to look at or debug one diagram quickly. Inside a project, the Design Manager opens
the same editor window (gui.main_window.MainWindow) with locks, sessions and generation
settings of the project.
"""
import os
import sys

# Repository layout: <root>/bin/fsm_editor.py and <root>/src.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from PySide6.QtWidgets import QApplication  # noqa: E402  (import after the sys.path change)

from gui.branding import install_app_icon  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from version import APP_NAME, VENDOR  # noqa: E402


def main() -> int:
    """Create the application and one editor window, open the file given (if any), run Qt."""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(VENDOR)
    install_app_icon()
    win = MainWindow()
    if len(sys.argv) > 1:
        win.open_path(sys.argv[1])
    win.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
