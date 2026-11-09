# -*- mode: python ; coding: utf-8 -*-
# =============================================================================================
# PyInstaller recipe for the Vietsemi HDL Studio desktop application.
#
# Normally run through scripts/build.py (or build_windows.ps1 / build_linux.sh), which also
# packs the result. By hand, from any folder:
#
#     pyinstaller --noconfirm --distpath dist --workpath build scripts/HDLStudio.spec
#
# Output: dist/HDLStudio/ (a folder with HDLStudio[.exe] and the Qt runtime).
# PyInstaller does not cross-compile: the Windows build is made on Windows, the Linux build
# on Linux. Paths below are relative to this file (SPECPATH is the folder holding the .spec).
# =============================================================================================
import os
import runpy
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))            # repository root
VERSION = runpy.run_path(os.path.join(ROOT, 'src', 'version.py'))
IMAGES = os.path.join(ROOT, 'resources', 'images')
ICON = os.path.join(IMAGES, 'Vietsemi_Logo_Only_on_Light.ico')


def _win_version_info():
    """Version resource of HDLStudio.exe (Explorer > Properties > Details), from src/version.py."""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo)
    nums = tuple(int(x) for x in VERSION['__version__'].split('.')) + (0,)       # 2026.12.001 -> (2026, 12, 1, 0)
    text = VERSION['__version__']
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[StringFileInfo([StringTable('040904B0', [
                  StringStruct('CompanyName', VERSION['VENDOR']),
                  StringStruct('FileDescription', VERSION['APP_NAME']),
                  StringStruct('FileVersion', text),
                  StringStruct('InternalName', 'HDLStudio'),
                  StringStruct('OriginalFilename', 'HDLStudio.exe'),
                  StringStruct('ProductName', VERSION['APP_NAME']),
                  StringStruct('ProductVersion', text)])]),
              VarFileInfo([VarStruct('Translation', [0x0409, 1200])])])


WINDOWS = sys.platform == 'win32'

a = Analysis(
    [os.path.join(ROOT, 'bin', 'hdlstudio.py')],   # entry point: the Design Manager
    pathex=[os.path.join(ROOT, 'src')],               # the application code (top-level modules)
    binaries=[],
    # icons are drawn in code; the only data files are the Vietsemi logos (About, splash, window icon)
    datas=[(os.path.join(IMAGES, 'Vietsemi_*.png'), os.path.join('resources', 'images'))],
    # pyslang is imported inside a try (src/hdl/parser.py): bundled when it is installed
    hiddenimports=['pyslang'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Qt parts the application never uses: keeps the folder much smaller
    excludes=['tkinter', 'unittest', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
              'PySide6.QtQuick', 'PySide6.QtQml', 'PySide6.Qt3DCore', 'PySide6.QtMultimedia'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HDLStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                    # UPX can break the Qt libraries; the archive is compressed anyway
    console=False,                # GUI application: no console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON if WINDOWS and os.path.isfile(ICON) else None,
    version=_win_version_info() if WINDOWS else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='HDLStudio',
)
