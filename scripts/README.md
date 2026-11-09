# scripts

Build, packaging and release scripts of Vietsemi HDL Studio.

| File | What it does |
|---|---|
| `build_windows.ps1` | Windows entry point: prepares `.venv`, runs `build.py`, optionally `release.py` |
| `build_linux.sh` | Linux entry point: the same steps |
| `build.py` | builds `dist/HDLStudio/` with PyInstaller and packs it with a SHA-256 checksum |
| `release.py` | creates the tag `v<version>` and the GitHub release, or uploads more files to it |
| `HDLStudio.spec` | PyInstaller recipe: entry point, data files, icon, Windows version resource |

The version comes from `__version__` in [`src/version.py`](../src/version.py)
(`YYYY.MM.NNN`, e.g. `2026.12.001`). It names the archives and the tag.

## Requirements

* Python 3.10 or newer (the builds are made with 3.12). PySide6, pyslang and PyInstaller are
  installed into `.venv` by the entry scripts.
* For `release.py`: git, and [GitHub CLI](https://cli.github.com) logged in (`gh auth login`)
  with write access to the repository.
* PyInstaller does not cross-compile. Build the Windows archive on Windows and the Linux archive
  on Linux.
* On Linux, build on the oldest distribution you support (CentOS Stream 9). The result runs on
  that glibc and any newer one. Qt also needs the usual X11/xcb libraries on the target
  (`dnf install libxkbcommon-x11 xcb-util-cursor xcb-util-wm xcb-util-keysyms xcb-util-image xcb-util-renderutil`).

## Build and pack

Windows (PowerShell):

```
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Linux:

```
bash scripts/build_linux.sh
```

Options:

| Windows | Linux | Effect |
|---|---|---|
| `-Clean` | `--clean` | remove `build/` before building |
| `-NoVenv` | `--no-venv` | use the active Python instead of `.venv` (its packages must be installed) |
| `-Release` | `--release` | publish to GitHub after the build (see below) |
| `-Draft` | `--draft` | with release: create the release as a draft |

`dist/HDLStudio/` is always removed and rebuilt, so the archive never carries files left over
from an earlier build. With an environment that is already set up, `build.py` can be run
directly:

```
python scripts/build.py [--clean] [--no-pack]
```

### Output

| Path | Content |
|---|---|
| `dist/HDLStudio/` | the application: `HDLStudio.exe` (Windows) or `HDLStudio` (Linux), the Python and Qt runtime, the logos, `LICENSE`, `README.md`, `VERSION` |
| `dist/HDLStudio-<version>-windows-x64.zip` | Windows archive |
| `dist/HDLStudio-<version>-linux-x64.tar.gz` | Linux archive (executable bits kept) |
| `<archive>.sha256` | checksum, in the format of `sha256sum -c` |

`VERSION` holds the version, the git commit and the platform of the build. `build/` holds
PyInstaller's work files. Both `build/` and `dist/` are ignored by git.

## Release

A release is published from `main`, after the version has been bumped in `src/version.py`
and the commit has been pushed:

1. On Windows: `scripts\build_windows.ps1 -Release`. `release.py` checks the repository,
   creates and pushes the annotated tag `v<version>`, and creates the GitHub release
   "Vietsemi HDL Studio \<version\>" with the Windows zip and its checksum.
2. On Linux, at the same commit: `bash scripts/build_linux.sh --release`. The release
   already exists, so the Linux tar.gz and its checksum are uploaded to it.

The order does not matter: the first run creates the release and the next one adds its files.
Running again on the same platform replaces that platform's files (`gh release upload --clobber`).

`release.py` stops before changing anything when:

* `gh` is missing or not logged in;
* the current branch is not `main`;
* tracked files have uncommitted changes (untracked files are allowed);
* `HEAD` is not on `origin/main`, i.e. it has not been pushed;
* the tag `v<version>` already exists on another commit, which means the version was not bumped;
* `dist/` holds no archive of this version.

Other options, by running the script directly:

```
python scripts/release.py --dry-run                # print the steps, change nothing
python scripts/release.py --notes-file notes.md    # own release notes instead of GitHub's generated notes
python scripts/release.py --prerelease
```

A tag and a release are public as soon as they are pushed. Use `--draft` (or `--dry-run`)
when in doubt; a draft is published later from the GitHub release page.

## Installing a release

* **Windows**: unzip and run `HDLStudio\HDLStudio.exe`. No installer is needed, and settings
  are kept in `%USERPROFILE%\hdl_studio`.
* **Linux**: `tar xzf HDLStudio-<version>-linux-x64.tar.gz`, then run `HDLStudio/HDLStudio`
  (optionally with a project file: `HDLStudio/HDLStudio path/to/project.hdp`). Settings are
  kept in `~/hdl_studio`.

To check a download, run `sha256sum -c HDLStudio-<version>-linux-x64.tar.gz.sha256` on Linux,
or `Get-FileHash <zip>` in PowerShell and compare the result with the `.sha256` file.
