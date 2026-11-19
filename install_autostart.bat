@echo off
cd /d "%~dp0"

rem =========================================================================
rem  install_autostart.bat  --  run ONCE ON EACH VIEWER PC, as Administrator.
rem  Creates a "start at logon" task that launches the read-only viewer.
rem  Deliberately ONE onlogon task only: a every-minute watchdog task would
rem  undo  open / end  issued from the teacher PC.
rem  If a viewer is killed it comes back at the next logon, or by running
rem  start_viewer.bat; for a strict machine also disable booting into Safe Mode
rem  and remove the student's admin rights.
rem  Remove again with:  uninstall_autostart.bat
rem =========================================================================
net session >nul 2>nul
if errorlevel 1 (
  echo Run this file as Administrator:  right click, "Run as administrator".
  pause
  exit /b 1
)

call pyenv.bat
if errorlevel 1 goto :end

set "TASKTR=\"%~dp0viewer_task.bat\""
echo [autostart] creating logon task mydesk-viewer, command is %TASKTR%
schtasks /create /tn "mydesk-viewer" /tr %TASKTR% /sc onlogon /rl highest /f
if not errorlevel 1 goto :ok
echo [autostart] schtasks failed. Alternative: put a shortcut to start_viewer.bat in
echo             shell:startup   (Run dialog: shell:startup)
goto :end

:ok
echo.
echo [autostart] done. The viewer will open by itself at the next logon.
echo             Remove it with uninstall_autostart.bat

:end
