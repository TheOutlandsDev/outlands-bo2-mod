@echo off
setlocal EnableExtensions DisableDelayedExpansion
call "%~dp0play-lan-windows.cmd" --join %*
set "outlands_result=%errorlevel%"
if not "%outlands_result%"=="0" pause
exit /b %outlands_result%
