# -*- mode: python ; coding: utf-8 -*-
# =============================================================================================
# PyInstaller recipe for the HDL Studio desktop application.
#
# Build (from the repository root, with PyInstaller installed in the active Python):
#
#     pyinstaller --noconfirm resources/scripts/HDLStudio.spec
#
# or simply run resources/scripts/build_windows.ps1 (Windows) / build_linux.sh (CentOS 9).
# Output: dist/HDLStudio/ (a folder with HDLStudio[.exe] and the Qt runtime).
#
# Paths below are relative to this file (SPECPATH is set by PyInstaller to the folder
# holding the .spec), so the build works from any current directory.
# =============================================================================================
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, '..', '..'))      # repository root

a = Analysis(
    [os.path.join(ROOT, 'bin', 'hdlstudio.py')],   # entry point: the Design Manager
    pathex=[os.path.join(ROOT, 'src')],               # the application code (top-level modules)
    binaries=[],
    # icons are drawn in code; the only data files are the Vietsemi logos (About, splash, window icon)
    datas=[(os.path.join(ROOT, 'resources', 'images', 'Vietsemi_*.png'), os.path.join('resources', 'images'))],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    upx=True,
    console=False,                # GUI application: no console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HDLStudio',
)
