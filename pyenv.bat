@echo off
rem pyenv.bat - find a usable Python; sets PYCMD (console) and PYW (no console).
rem All ASCII only, CRLF line endings. Called by setup.bat / start_*.bat / viewer_task.bat
rem
rem Candidate order:
rem   1) MYDESK_PY (you set it)
rem   2) python.org installer dirs
rem   3) Microsoft Store package dir  (WindowsApps\python.exe is a stub that cannot run)
rem   4) py -3 launcher (ask it for the real interpreter path)
rem   5) python / python3 in PATH (ask them where they really live)
rem   6) where python.exe / where pythonw.exe
set "PYCMD="
set "PYW="

if defined MYDESK_PY call :try "%MYDESK_PY%"
if defined PYCMD goto :show

for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :try "%%d\python.exe"
if defined PYCMD goto :show
for /d %%d in ("C:\Program Files\Python3*") do call :try "%%d\python.exe"
if defined PYCMD goto :show
for /d %%d in ("C:\Program Files (x86)\Python3*") do call :try "%%d\python.exe"
if defined PYCMD goto :show
for /d %%d in ("C:\Python3*") do call :try "%%d\python.exe"
if defined PYCMD goto :show

rem Store edition: the runnable interpreter sits in a package folder
for /d %%d in ("%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3*") do call :try "%%d\python.exe"
if defined PYCMD goto :show

rem py launcher
set "TMPX=%TEMP%\mydesk_py.txt"
py -3 -c "import sys;print(sys.executable)" >"%TMPX%" 2>nul
set /p FOUND=<"%TMPX%" 2>nul
if defined FOUND call :try "%FOUND%"
set "FOUND="
if defined PYCMD goto :show

rem python / python3 in PATH
python -c "import sys;print(sys.executable)" >"%TMPX%" 2>nul
set /p FOUND=<"%TMPX%" 2>nul
if defined FOUND call :try "%FOUND%"
set "FOUND="
python3 -c "import sys;print(sys.executable)" >"%TMPX%" 2>nul
set /p FOUND=<"%TMPX%" 2>nul
if defined FOUND call :try "%FOUND%"
del "%TMPX%" >nul 2>nul
if defined PYCMD goto :show

rem last resort
for /f "delims=" %%p in ('where python.exe 2^>nul') do if not defined PYCMD call :try "%%p"
if defined PYCMD goto :show
for /f "delims=" %%p in ('where pythonw.exe 2^>nul') do if not defined PYCMD call :try "%%p"

:show
if not defined PYCMD goto :pyfail
if not defined PYW set "PYW=%PYCMD%"
echo [pyenv] interpreter  : %PYCMD%
if "%PYW%"=="%PYCMD%" (echo [pyenv] window mode  : %PYCMD%  [note] no pythonw.exe found: a console window will show) else echo [pyenv] window mode  : %PYW%
"%PYCMD%" -c "import sys;print('[pyenv] python   :',sys.version.split()[0])" 2>nul
set "TKINTER_OK=1"
set "PILLOW_OK=1"
"%PYCMD%" -c "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('tkinter') else 1)" >nul 2>nul
if errorlevel 1 (
  set "TKINTER_OK=0"
  echo [pyenv] tkinter  : MISSING - needs a python.org full install
) else (
  echo [pyenv] tkinter  : OK
)
"%PYCMD%" -c "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('PIL') else 1)" >nul 2>nul
if errorlevel 1 (
  set "PILLOW_OK=0"
  echo [pyenv] pillow   : MISSING - run setup.bat first
) else (
  echo [pyenv] pillow   : OK
)
exit /b 0

:pyfail
set "PYCMD="
set "PYW="
set "TKINTER_OK=0"
set "PILLOW_OK=0"
echo [pyenv] FAILED: no usable Python found.
echo   Fix 1: install Python 3.11+ from python.org, CHECK the box
echo          "Add python.exe to PATH" during the installer.
echo   Fix 2: or tell this folder where it is:  set MYDESK_PY=C:\Path\To\python.exe
echo   Fix 3: or test it interactively:         py -3 setup.bat
echo   No Python at all? Use the emergency browser page instead (teacher machine only):
echo          http://TEACHER-IP:8765/view?key=YOUR-PASSWORD
exit /b 1

:try
rem usage: call :try "path\to\python.exe"
set "CAND=%~1"
if "%CAND%"=="" exit /b 1
if not exist "%CAND%" exit /b 1
"%CAND%" -c "import sys;print(1)" >nul 2>nul
if errorlevel 1 exit /b 1
set "PYCMD=%CAND%"
set "CANDW=%~dp1pythonw.exe"
if exist "%CANDW%" set "PYW=%CANDW%"
exit /b 0
