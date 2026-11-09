#!/usr/bin/env bash
# =============================================================================================
# Build, pack and (optionally) release Vietsemi HDL Studio on Linux.
#
#     bash scripts/build_linux.sh              # build + tar.gz
#     bash scripts/build_linux.sh --clean      # clean build
#     bash scripts/build_linux.sh --release    # + GitHub release (upload to it when it exists)
#     bash scripts/build_linux.sh --no-venv    # use the active python3
#
# By default the build runs in the virtual environment .venv of the repository (created when
# missing), with the packages of requirements.txt and PyInstaller installed. The work itself is
# done by scripts/build.py (and scripts/release.py for --release); see scripts/README.md.
# Build on the oldest distribution you support (e.g. CentOS Stream 9): the result needs a glibc
# at least as new as the build machine's.
# Result: dist/HDLStudio/ and dist/HDLStudio-<version>-linux-x64.tar.gz (+ .sha256)
# =============================================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"       # repository root
cd "$ROOT"

CLEAN=() RELEASE=0 RELEASE_ARGS=() VENV=1
for arg in "$@"; do
    case "$arg" in
        --clean)   CLEAN=(--clean) ;;
        --release) RELEASE=1 ;;
        --draft)   RELEASE_ARGS+=(--draft) ;;
        --no-venv) VENV=0 ;;
        -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [ "$VENV" = 1 ]; then
    PY="$ROOT/.venv/bin/python"
    if [ ! -x "$PY" ]; then
        echo "Creating the virtual environment .venv"
        python3 -m venv .venv
    fi
    "$PY" -m pip install --quiet --upgrade pip
    "$PY" -m pip install --quiet -r requirements.txt pyinstaller
else
    PY=python3
fi

"$PY" scripts/build.py "${CLEAN[@]}"
if [ "$RELEASE" = 1 ]; then
    "$PY" scripts/release.py "${RELEASE_ARGS[@]}"
fi
