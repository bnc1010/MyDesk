@echo off
cd /d "%~dp0"
rem Remove the "start viewer at logon" task created by install_autostart.bat.
schtasks /delete /tn "mydesk-viewer" /f
if not errorlevel 1 goto :ok
echo [autostart] delete failed: run this file as Administrator.
goto :end
:ok
echo [autostart] logon task removed. Run stop_viewer.bat now if a viewer is still showing.
:end
