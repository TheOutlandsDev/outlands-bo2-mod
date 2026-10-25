@echo off
setlocal
set "launcher=%~dp0runtime\downloads\plutonium.exe"
if not exist "%launcher%" (
    echo Download the official updater from https://cdn.plutonium.pw/updater/plutonium.exe
    echo Save it to "%launcher%", then run this file again.
    exit /b 1
)
start "Plutonium" /wait "%launcher%" %*
