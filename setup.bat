@echo off
setlocal
cd /d "%~dp0"
call pyenv.bat
if errorlevel 1 goto :nopython

rem pip must run with python.exe (pythonw.exe has no console, so its output is invisible)
set "PIPPY=%PYCMD%"
if /i "%PIPPY:~-11%"=="pythonw.exe" (
  set "SIB=%PIPPY:pythonw.exe=python.exe%"
  if exist "%SIB%" "%SIB%" -c "import sys" >nul 2>nul && set "PIPPY=%SIB%"
)

echo.
echo [setup] python  : %PYCMD%
echo [setup] pip tool: %PIPPY%

rem ---- attempt 1: plain install -----------------------------------------------
echo [setup] installing pillow + mss ...
"%PIPPY%" -m pip install -r requirements.txt
if not errorlevel 1 goto :verify

rem ---- attempt 2: user site-packages (Store Python / permission issues) ------
echo.
echo [setup] retrying with --user ...
"%PIPPY%" -m pip install --user -r requirements.txt
if not errorlevel 1 goto :verify

rem ---- attempt 3: CN mirror (pypi.org often slow or blocked) -----------------
echo.
echo [setup] retrying through a Chinese mirror ...
"%PIPPY%" -m pip install --user -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
if not errorlevel 1 goto :verify
"%PIPPY%" -m pip install --user -i https://mirrors.aliyun.com/pypi/simple -r requirements.txt
if not errorlevel 1 goto :verify

rem ---- attempt 4: the pip alias on the command line (Store Python style) -----
pip3 --version >nul 2>nul
if not errorlevel 1 (
  echo.
  echo [setup] retrying with the pip3 command from PATH ...
  pip3 install --user -r requirements.txt
  if not errorlevel 1 goto :verify
)

rem ---- maybe pillow was already there (mss optional) -------------------------
"%PIPPY%" -c "import PIL;print('[setup] pillow already installed - mss is optional, that is enough.')" >nul 2>nul
if not errorlevel 1 goto :verify
goto :pipfail

:verify
echo.
"%PIPPY%" -c "import PIL,tkinter;print('[setup] pillow OK, tkinter OK')"
if errorlevel 1 (
  echo [setup] PROBLEM: pillow or tkinter still not importable with %PYCMD%
  echo         see README section 6 (offline wheels) or install python.org Python 3.12.
  pause
  exit /b 1
)
echo [setup] OK. Next steps:
echo   teacher PC : start_host.bat
echo   viewer  PC : start_viewer.bat
echo   if the .bat ever picks the wrong Python:  set MYDESK_PY=C:\path\to\python.exe
exit /b 0

:pipfail
echo.
echo [setup] pip install FAILED. Read the pip error above; the usual causes:
echo.
echo   1 - pypi.org is slow or blocked here. The mirror attempt above already tried
echo       https://pypi.tuna.tsinghua.edu.cn/simple . If you need another mirror:
echo         "%PIPPY%" -m pip install -i https://mirrors.aliyun.com/pypi/simple pillow mss
echo       or a proxy:  set HTTPS_PROXY=http://proxy-address:port  then re-run setup.bat
echo.
echo   2 - no internet on this PC. On a PC that HAS internet, run:
echo         pip download -r requirements.txt -d wheels
echo       copy the "wheels" folder into this directory, then:
echo         "%PIPPY%" -m pip install --no-index --find-links=wheels pillow mss
echo.
echo   3 - Microsoft Store Python blocks pip. Install python.org Python 3.12
echo       (tick "Add python.exe to PATH"), then:
echo         set MYDESK_PY=C:\Users\you\AppData\Local\Programs\Python\Python312\python.exe
echo         setup.bat
echo.
echo   mss is optional: host.py can capture the screen with pillow alone.
echo   Pillow version must match the Python version, so install with THIS python.
pause
exit /b 1

:nopython
echo.
echo [setup] No usable Python found on this PC.
echo   Install Python 3.12 from https://www.python.org/downloads/
echo   and CHECK the box "Add python.exe to PATH" while installing, then run setup.bat again.
echo   (If Python is installed somewhere unusual: set MYDESK_PY=C:\Path\To\python.exe )
pause
exit /b 1
