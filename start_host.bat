@echo off
setlocal
cd /d "%~dp0"
call pyenv.bat
if errorlevel 1 goto :end

echo.
echo [host] streaming THIS desktop now. Viewer PCs just run start_viewer.bat.
echo [host] control page in a browser:  http://127.0.0.1:8765/  -- buttons for open / end.
echo [host] type  end  in this window to let every viewer PC close.
echo   extra options, type them after the bat name:
echo     start_host.bat --fps 12 --width 1024        slower, smoother on a big LAN
echo     start_host.bat --key yourpassword           viewers must use the same key
echo     start_host.bat --monitor 0                  merge all monitors into one picture
echo     start_host.bat --help                       full list
echo   LAN discovery uses UDP 5007; the stream uses TCP 8765 (setup_firewall.bat).
echo.
"%PYCMD%" host.py --port 8765 --fps 15 --width 1280 --quality 72 %*
:end
