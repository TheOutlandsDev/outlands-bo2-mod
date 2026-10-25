@echo off
setlocal EnableExtensions DisableDelayedExpansion
where powershell.exe >nul 2>&1
if errorlevel 1 (
    echo The Outlands BO2 Mod requires Windows PowerShell. 1>&2
    exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\play_lan_windows.ps1" %*
exit /b %errorlevel%
