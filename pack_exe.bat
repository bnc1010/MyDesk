@echo off
setlocal
cd /d "%~dp0"

rem =========================================================================
rem  pack_exe.bat  --  build standalone .exe files, so viewer PCs do not
rem  need Python installed at all.  Run it on a PC that HAS Python + internet.
rem  Result: dist\host.exe  dist\viewer.exe  dist\watch.exe
rem  Ship those three files in one folder; run watch.exe on the viewer PC.
rem =========================================================================
call pyenv.bat
if errorlevel 1 goto :end

echo [pack] installing PyInstaller ...
"%PYCMD%" -m pip install pyinstaller
if errorlevel 1 goto :end

echo.
echo [pack] building host.exe ...
"%PYCMD%" -m PyInstaller --noconfirm --clean --onefile --name host host.py

echo [pack] building viewer.exe ...
"%PYCMD%" -m PyInstaller --noconfirm --clean --onefile --noconsole --name viewer viewer.py

echo [pack] building watch.exe ...
"%PYCMD%" -m PyInstaller --noconfirm --clean --onefile --noconsole --name watch watch.py

echo.
echo [pack] look in the dist\ folder. viewer.exe + watch.exe go to the viewer PCs.
echo [pack] note: a standalone exe is easier to block from quitting, but it still
echo        cannot stop Ctrl+Alt+Del or a shutdown. Keep the teacher "end" command
echo        as the normal way to let a viewer PC go back to normal use.
:end
