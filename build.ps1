param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $Python -m venv .venv
}

$py = Join-Path $root ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt
& $py -m pip install -r requirements-build.txt

& $py -m PyInstaller --noconfirm --clean --onedir --windowed --name SimpleCubeLauncher --icon "assets\icon.ico" --add-data "assets;assets" --version-file "version_info.txt" gui.py

Write-Host ""
Write-Host "Build complete: dist\SimpleCubeLauncher\SimpleCubeLauncher.exe"
Write-Host "Zip the dist\SimpleCubeLauncher folder for a release."
