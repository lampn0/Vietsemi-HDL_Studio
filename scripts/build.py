"""Build and pack Vietsemi HDL Studio for the platform this script runs on.

    python scripts/build.py              # build dist/HDLStudio/ and pack it
    python scripts/build.py --clean      # remove build/ and dist/HDLStudio/ first
    python scripts/build.py --no-pack    # build the folder only

Steps:
  1. check that PySide6 and PyInstaller are importable by this Python;
  2. run PyInstaller on scripts/HDLStudio.spec (work files in build/, result in dist/HDLStudio/);
  3. add LICENSE, README.md and VERSION to the folder;
  4. pack it as dist/HDLStudio-<version>-<os>-<arch>.zip (Windows) or .tar.gz (Linux) and write
     the SHA-256 of the archive next to it (<archive>.sha256).

The version is __version__ of src/version.py. PyInstaller does not cross-compile, so the Windows
archive is built on Windows and the Linux archive on Linux (build_windows.ps1 / build_linux.sh
prepare a virtual environment and call this script).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import runpy
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, 'scripts', 'HDLStudio.spec')
DIST = os.path.join(ROOT, 'dist')
BUILD = os.path.join(ROOT, 'build')
APP_DIR = os.path.join(DIST, 'HDLStudio')


def version() -> str:
    """__version__ of src/version.py (read without importing the application)."""
    return runpy.run_path(os.path.join(ROOT, 'src', 'version.py'))['__version__']


def target() -> tuple[str, str]:
    """(os, arch) of this machine as used in archive names: ('windows' | 'linux', 'x64' | 'arm64')."""
    osname = {'win32': 'windows', 'linux': 'linux', 'darwin': 'macos'}.get(sys.platform, sys.platform)
    arch = platform.machine().lower()
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64'}.get(arch, arch)
    return osname, arch


def archive_path() -> str:
    """Path of the archive this platform's build produces."""
    osname, arch = target()
    ext = '.zip' if osname == 'windows' else '.tar.gz'
    return os.path.join(DIST, f'HDLStudio-{version()}-{osname}-{arch}{ext}')


def check_tools() -> None:
    """Stop with a hint when PySide6 or PyInstaller is missing from this Python."""
    missing = []
    for mod, pkg in (('PySide6', 'PySide6'), ('PyInstaller', 'pyinstaller')):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        sys.exit(f'Missing in {sys.executable}: {", ".join(missing)}\n'
                 f'  {sys.executable} -m pip install -r requirements.txt pyinstaller')
    try:
        import pyslang  # noqa: F401
    except ImportError:
        print('note: pyslang is not installed; the build falls back to the regex HDL scanner')


def _rmtree(path: str) -> None:
    """Remove a folder, trying again while a virus scanner still holds files in it (Windows)."""
    for attempt in range(5):
        if not os.path.exists(path):
            return
        try:
            shutil.rmtree(path)
            return
        except OSError as e:
            print(f'cannot remove {path} yet ({e}); retrying')
            time.sleep(3)
    sys.exit(f'cannot remove {path}')


def run_pyinstaller() -> None:
    """Freeze the application into dist/HDLStudio/."""
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--distpath', DIST, '--workpath', BUILD, SPEC]
    print('>', ' '.join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)
    exe = os.path.join(APP_DIR, 'HDLStudio.exe' if sys.platform == 'win32' else 'HDLStudio')
    if not os.path.isfile(exe):
        sys.exit(f'PyInstaller finished but {exe} is missing')


def add_docs() -> None:
    """Copy LICENSE and README.md into the folder and write VERSION (the build's number and commit)."""
    for name in ('LICENSE', 'README.md'):
        shutil.copy2(os.path.join(ROOT, name), os.path.join(APP_DIR, name))
    try:
        commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = 'unknown'
    osname, arch = target()
    with open(os.path.join(APP_DIR, 'VERSION'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(f'{version()}\ncommit {commit}\n{osname}-{arch}, Python {platform.python_version()}\n')


def pack() -> str:
    """Pack dist/HDLStudio/ as this platform's archive (top folder HDLStudio/); return its path."""
    out = archive_path()
    if os.path.exists(out):
        os.remove(out)
    print('packing', out)
    if out.endswith('.zip'):
        for attempt in range(5):         # a virus scanner may still hold the new files open
            try:
                with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                    for folder, _, files in os.walk(APP_DIR):
                        for name in files:
                            path = os.path.join(folder, name)
                            z.write(path, os.path.relpath(path, DIST))
                break
            except PermissionError as e:
                print(f'packing failed (try {attempt + 1} of 5): {e}')
                time.sleep(5)
        else:
            sys.exit('packing failed')
    else:
        with tarfile.open(out, 'w:gz') as t:   # keeps the executable bits
            t.add(APP_DIR, arcname='HDLStudio')
    return out


def write_checksum(path: str) -> str:
    """Write <path>.sha256 in the `sha256sum -c` format; return the digest."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    digest = h.hexdigest()
    with open(path + '.sha256', 'w', encoding='utf-8', newline='\n') as f:
        f.write(f'{digest}  {os.path.basename(path)}\n')
    return digest


def main() -> int:
    """Parse the options and run the build."""
    ap = argparse.ArgumentParser(description='Build and pack Vietsemi HDL Studio for this platform.')
    ap.add_argument('--clean', action='store_true', help='remove build/ and dist/HDLStudio/ first')
    ap.add_argument('--no-pack', action='store_true', help='build dist/HDLStudio/ only, no archive')
    args = ap.parse_args()
    osname, arch = target()
    print(f'Vietsemi HDL Studio {version()} for {osname}-{arch} (Python {platform.python_version()})')
    check_tools()
    if args.clean:
        _rmtree(BUILD)
    _rmtree(APP_DIR)                     # never pack files left over from an earlier build
    run_pyinstaller()
    add_docs()
    if args.no_pack:
        print('Built', APP_DIR)
        return 0
    out = pack()
    digest = write_checksum(out)
    size = os.path.getsize(out) / (1 << 20)
    print(f'Built {out} ({size:.1f} MB)\n  sha256 {digest}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
