"""Start HDL Studio: the Design Manager window (projects, libraries, design units).

    python bin/hdlstudio.py                      # reopen the last session (project and windows)
    python bin/hdlstudio.py path/to/project.hdp  # open a project (its last windows too, if it
                                                   # was the last one opened)
    python bin/hdlstudio.py --new                # start empty, without the last session

This file is only a launcher: it puts ../src on the Python path, creates the Qt application
and the DesignManager window, then hands control to the Qt event loop. All the real work is
in src/. It is also the entry point PyInstaller freezes
(resources/scripts/HDLStudio.spec).
"""
import os
import sys

# Repository layout: <root>/bin/hdlstudio.py and <root>/src. When frozen by PyInstaller
# the package is already bundled and this path simply does not exist (harmless).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from PySide6.QtCore import QTimer  # noqa: E402  (import after the sys.path change)
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui.branding import install_app_icon  # noqa: E402
from gui.design_manager import DesignManager  # noqa: E402
from gui.status import SplashScreen  # noqa: E402
from version import APP_NAME, VENDOR  # noqa: E402


def main() -> int:
    """Create the application and the Design Manager, open the project / session, run Qt."""
    app = QApplication(sys.argv)
    # Name Qt shows in dialogs. Preferences and session do not depend on it: they live in
    # ~/hdl_studio/user/<release> (see src/homes.py).
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(VENDOR)
    app.setOrganizationDomain('vietsemi.org')
    install_app_icon()
    splash = SplashScreen()             # logo and a status line until the project is open
    splash.show()
    splash.status('Starting...')
    dm = DesignManager()
    dm.progress.splash = splash         # library scanning is also shown on the splash
    dm.show()
    # Positional arguments (not starting with --) are project files; only the first is used.
    args = [a for a in sys.argv[1:] if not a.startswith('--')]

    def start():
        """Open the project / session once the window has been painted (see the comment below)."""
        # --new (or "restore session" switched off in Options > Preferences): open only the
        # project given on the command line, if any. Otherwise restore the last session; a
        # project given on the command line replaces the last project of the session.
        try:
            if '--new' in sys.argv or not dm.prefs.restore_session:
                if args:
                    splash.status(f'Opening project {os.path.basename(args[0])}...')
                    dm.load_project(args[0])
            else:
                splash.status('Restoring the last session...')
                dm.restore_session(args[0] if args else '')
        finally:
            dm.progress.splash = None
            splash.finish(dm)
    QTimer.singleShot(0, start)          # paint the window first, then open the project
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
