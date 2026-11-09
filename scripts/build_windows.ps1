# =============================================================================================
# Build, pack and (optionally) release Vietsemi HDL Studio on Windows.
#
#     powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1            # build + zip
#     powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -Clean     # clean build
#     powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -Release   # + GitHub release
#     powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -NoVenv    # use the active Python
#
# By default the build runs in the virtual environment .venv of the repository (created when
# missing), with the packages of requirements.txt and PyInstaller installed. The work itself is
# done by scripts\build.py (and scripts\release.py for -Release); see scripts\README.md.
# Result: dist\HDLStudio\ and dist\HDLStudio-<version>-windows-x64.zip (+ .sha256)
# =============================================================================================
param(
    [switch]$Clean,
    [switch]$Release,
    [switch]$Draft,
    [switch]$NoVenv
)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')           # repository root
Set-Location $root

if ($NoVenv) {
    $py = 'python'
} else {
    $py = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path $py)) {
        Write-Host 'Creating the virtual environment .venv'
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    & $py -m pip install --quiet --upgrade pip
    & $py -m pip install --quiet -r requirements.txt pyinstaller
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$buildArgs = @()
if ($Clean) { $buildArgs += '--clean' }
& $py scripts\build.py @buildArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Release) {
    $relArgs = @()
    if ($Draft) { $relArgs += '--draft' }
    & $py scripts\release.py @relArgs
    exit $LASTEXITCODE
}
