@echo off
REM ==============================================================================
REM Install A2A Swarm Auto-start on Windows
REM Automatically starts A2A Node & Web Dashboard in the background on user logon.
REM ==============================================================================

set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set VBS_TARGET=%STARTUP_DIR%\start_a2a_services.vbs
set SCRIPT_DIR=%~dp0..
set LAUNCHER_PATH=%SCRIPT_DIR%\launcher.py

echo [*] Installing A2A Auto-starter to Windows Startup...
echo Set WshShell = CreateObject("WScript.Shell") > "%VBS_TARGET%"
echo WshShell.Run "python ""%LAUNCHER_PATH%""", 0, False >> "%VBS_TARGET%"

if exist "%VBS_TARGET%" (
    echo [OK] Auto-start script installed successfully at:
    echo      %VBS_TARGET%
    echo [*] Testing launcher execution...
    wscript.exe "%VBS_TARGET%"
    echo [DONE] A2A services will now automatically start on every boot/logon.
) else (
    echo [ERROR] Failed to create auto-start script.
)
