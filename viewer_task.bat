@echo off
rem viewer_task.bat - the command used by the "start at logon" scheduled task.
rem It runs the watchdog in the foreground so Windows can restart the task if it dies.
cd /d "%~dp0"
call pyenv.bat 1>nul 2>nul
if errorlevel 1 (
  echo [viewer_task] no usable Python found - run setup.bat first >> "%~dp0viewer.log"
  exit /b 1
)
if exist "%PYW%" (
  "%PYW%" watch.py
) else (
  "%PYCMD%" watch.py
)
