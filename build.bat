@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%build.ps1"

if not exist "%PS1%" (
    echo ERROR: build.ps1 not found at "%PS1%"
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
exit /b %ERRORLEVEL%
