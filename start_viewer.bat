@echo off
setlocal
cd /d "%~dp0"
call pyenv.bat
if errorlevel 1 goto :fallback
if "%PILLOW_OK%"=="0" goto :deps
if "%TKINTER_OK%"=="0" goto :deps

echo Viewer watchdog started.  Log file: "%~dp0viewer.log"
echo Stop it ONLY from the teacher PC (type end / open in its window), or with stop_viewer.bat
echo If you are just TRIALING this and need a quit button, use start_viewer_debug.bat instead.
echo.
if exist "%PYW%" (
  start "" "%PYW%" watch.py %*
) else (
  start "" "%PYCMD%" watch.py %*
)
ping -n 4 127.0.0.1 >nul 2>nul
goto :end

:deps
echo.
echo [viewer] Python found, but this Python is missing the "pillow" (or tkinter) module.
echo        Run  setup.bat  on this PC first, then start_viewer.bat again.
echo        If setup.bat cannot install it (no internet / Microsoft Store Python),
echo        see README section 6 (offline wheels, or install python.org Python 3.12).
echo.
pause
goto :end

:fallback
echo.
echo [viewer] No working Python on this PC. Two ways forward:
echo.
echo   A) Install Python 3.12 from https://www.python.org/downloads/  (tick "Add python.exe to PATH")
echo      then run setup.bat and this file again.
echo.
echo   B) Emergency browser mode (no Python at all): on this PC open
echo         http^://TEACHER-IP^:8765/view?key=TEACHER-KEY
echo      press F11 for full screen. NOTE: a browser cannot be forced "no-exit";
echo      use start_viewer.bat for the real kiosk behaviour.
echo.
pause

:end
