#Requires -Version 5.1
<#
.SYNOPSIS
    Builds ReportViewer.exe into bin\ReportViewer\
#>

$ErrorActionPreference = "Stop"

$ROOT   = $PSScriptRoot
$PYTHON = "C:/Users/TURCAR/AppData/Local/Programs/Python/Python313/python.exe"
$ENTRY  = "$ROOT\ReportViewer\report_viewer.py"
$DIST   = "$ROOT\bin"
$WORK   = "$ROOT\build\pyinstaller"
$SPEC   = "$ROOT"

Write-Host "==> Building ReportViewer..." -ForegroundColor Cyan

& $PYTHON -m PyInstaller `
    --noconfirm --clean --onedir --windowed `
    --distpath $DIST `
    --workpath $WORK `
    --specpath $SPEC `
    --name "ReportViewer" `
    --hidden-import=PyQt6.QtCore `
    --hidden-import=PyQt6.QtGui `
    --hidden-import=PyQt6.QtWidgets `
    --hidden-import=PyQt6.QtWebEngineWidgets `
    --hidden-import=PyQt6.QtNetwork `
    --hidden-import=PyQt6.QtPrintSupport `
    $ENTRY

if ($LASTEXITCODE -ne 0) {
    Write-Host "==> Build FAILED (exit $LASTEXITCODE)" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "==> Copying settings and README..." -ForegroundColor Cyan
Copy-Item "$ROOT\ReportViewer\ReportViewer.Settings.json" "$DIST\ReportViewer\" -Force
if (Test-Path "$ROOT\README.md") {
    Copy-Item "$ROOT\README.md" "$DIST\ReportViewer\" -Force
}

Write-Host "==> Done: $DIST\ReportViewer\ReportViewer.exe" -ForegroundColor Green
