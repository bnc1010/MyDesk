@echo off
cd /d "%~dp0"

rem =========================================================================
rem  Hard stop for the viewer watchdog - last resort only.
rem  Normal way to stop viewing: teacher PC types  end  (or  open) in its window.
rem =========================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_viewer.ps1"

echo.
echo Viewers closed. If some page still shows, run this file again on that PC.
pause
