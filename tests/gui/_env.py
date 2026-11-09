"""Shared set-up of the GUI tests.

Every GUI test runs the real application (Design Manager -> editors, visible windows) on a
throw-away copy of a few design units of a legacy project, with its own configuration
directory, so it never writes into the real project (no lock files, no saved views) nor into
the user's preferences.

    HDP, CFG, OUT = _env.setup()      # call before importing PySide6 / the application

Environment variables:
    HDLSTUDIO_TEST_SRC   the real project folder to copy from (read only), default D:/workspace/src
    HDLSTUDIO_TEST_OUT   where screenshots go, default tests/gui/out (ignored by git)
    HDLSTUDIO_TEST_TMP   the temporary folder to work in; run_all.py sets and deletes it, a test run
                    on its own makes one and prints it
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'src')   # the application's code
SRC = os.environ.get('HDLSTUDIO_TEST_SRC', r'D:\workspace\src')

# What the tests use from the real project: the top library's dynamo_core block diagram (a
# large legacy .bd with components, embedded blocks, ports, buses and frames), and the whole
# protocol_controller library (block diagrams, state machines, their HDL and hierarchy).
_FILES = [
    'dti_hbm.hdp',
    'hds/dynamo_core/struct.bd',
    'hds/dynamo_core/symbol.sb',
]
_TREES = ['libs/protocol_controller']     # copied whole (lock files left out)
_DIRS = ['hdl', 'include']          # folders the .hdp maps; empty in the copy


def make_project(dest: str) -> str:
    """Copy the files above from SRC into dest (same relative paths); return the .hdp path.
    Libraries of the .hdp whose folders are not copied simply show as missing."""
    for rel in _FILES:
        src = os.path.join(SRC, rel)
        if not os.path.exists(src):
            raise SystemExit(f'GUI tests need {src} (set HDLSTUDIO_TEST_SRC to the project folder)')
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target)
    for rel in _TREES:
        shutil.copytree(os.path.join(SRC, rel), os.path.join(dest, rel), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('*.lck'))
    for rel in _DIRS:
        os.makedirs(os.path.join(dest, rel), exist_ok=True)
    return os.path.join(dest, 'dti_hbm.hdp')


def setup() -> tuple[str, str, str]:
    """Make the project copy and the config dir, point the app at them; return (hdp, config
    dir, screenshot dir)."""
    import faulthandler
    faulthandler.enable()                        # a crash in Qt prints the Python stack (run_all shows it)
    root = os.environ.get('HDLSTUDIO_TEST_TMP')
    if not root:
        root = tempfile.mkdtemp(prefix='hdlstudio_gui_')
        print('test folder:', root, flush=True)
    project = os.path.join(root, 'project')
    hdp = os.path.join(project, 'dti_hbm.hdp')
    if not os.path.exists(hdp):
        make_project(project)
    cfg = os.path.join(root, 'config')
    os.makedirs(cfg, exist_ok=True)
    out = os.environ.get('HDLSTUDIO_TEST_OUT', os.path.join(HERE, 'out'))
    os.makedirs(out, exist_ok=True)
    os.environ['HDLSTUDIO_HOME'] = cfg           # preferences, session, autosave, caches
    if CODE_DIR not in sys.path:
        sys.path.insert(0, CODE_DIR)
    _guard_dialogs()
    return hdp, cfg, out


DIALOG_TIMEOUT_MS = 20000


def _guard_dialogs():
    """A test must never hang on a dialog nobody answers (a lock question, an error box...):
    every dialog opened with exec() is closed after DIALOG_TIMEOUT_MS if it is still open, and a
    FAIL line naming it is printed. Dialogs a test answers itself (with a timer) close long before."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QMessageBox

    def guard(cls):
        """Replace cls.exec with a version that closes the dialog after DIALOG_TIMEOUT_MS."""
        original = cls.exec

        def exec_guarded(dlg, *args):
            """exec() of a dialog, with the time limit armed."""
            def give_up():
                """The time is up: report the dialog as a FAIL and close it."""
                if dlg.isVisible():
                    print(f'FAIL unexpected dialog left open: "{dlg.windowTitle()}" '
                          f'{getattr(dlg, "text", lambda: "")()!r}', flush=True)
                    dlg.reject()
            QTimer.singleShot(DIALOG_TIMEOUT_MS, give_up)
            return original(dlg, *args)
        cls.exec = exec_guarded
    guard(QDialog)
    guard(QMessageBox)          # PySide binds QMessageBox.exec separately


def run_steps(script: str, steps: list[str]) -> int:
    """For tests that check what survives a restart (session, hierarchy): run the script once
    per step, each in a new process, all on the same project copy and config folder. Returns
    1 when a step failed."""
    import subprocess
    if not os.environ.get('HDLSTUDIO_TEST_TMP'):
        os.environ['HDLSTUDIO_TEST_TMP'] = tempfile.mkdtemp(prefix='hdlstudio_gui_')
        print('test folder:', os.environ['HDLSTUDIO_TEST_TMP'], flush=True)
    rc = 0
    for step in steps:
        print(f'-- step {step}', flush=True)
        rc |= subprocess.call([sys.executable, '-u', script, step], env=os.environ)
    return 1 if rc else 0


def legacy_bd(rel: str) -> str:
    """A legacy .bd of the real project, for tests that only import it (read, never written)."""
    return os.path.join(SRC, rel)


def finish(fails: int):
    """End a test: exit code 1 when a check failed. Qt's teardown is skipped (it can hang with
    editor windows still open, or crash while its DLLs are unloaded)."""
    sys.stdout.flush()
    sys.stderr.flush()
    code = 1 if fails else 0
    if sys.platform == 'win32':
        # end the process at once: unloading Qt's DLLs at exit sometimes crashes (0xc0000005)
        # after every check has passed, which run_all would report as a failed test
        # (the handle must be passed as a HANDLE: ctypes' default int cuts the pseudo handle -1 to
        # 32 bits, and TerminateProcess then fails with ERROR_INVALID_HANDLE)
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
        k32.TerminateProcess(k32.GetCurrentProcess(), code)
    os._exit(code)
