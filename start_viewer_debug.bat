@echo off
setlocal
cd /d "%~dp0"
rem  DEBUG / TRIAL viewer: visible "quit" button, no key blocking, no registry change, no auto-restart
call pyenv.bat
if errorlevel 1 goto :fallback
if "%PILLOW_OK%"=="0" goto :deps
if "%TKINTER_OK%"=="0" goto :deps

echo DEBUG mode viewer: the red button "quit" in the top-right corner (or Ctrl+Q / Esc) closes it.
echo No hotkey blocking, no task-manager policy, no auto-restart. Use start_viewer.bat for the real kiosk.
echo Log file: "%~dp0viewer.log"
echo.
if exist "%PYW%" (
  start "" "%PYW%" watch.py --debug %*
) else (
  start "" "%PYCMD%" watch.py --debug %*
)
ping -n 4 127.0.0.1 >nul 2>nul
goto :end

:deps
echo.
echo [viewer] Python found, but this Python is missing the "pillow" (or tkinter) module.
echo        Run  setup.bat  on this PC first, then start_viewer_debug.bat again.
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
echo      press F11 for full screen.
echo.
pause

:end
